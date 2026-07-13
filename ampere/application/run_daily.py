"""The daily use-case + headless entrypoint (SPEC §2, §8a; SC6, SC8).

Pipeline:  fetch -> resolve -> effective_price -> dedup-cheapest-per-SKU -> score -> frontier
           -> diff vs prior snapshot -> persist (idempotent + transactional per snapshot_date).

This is the single code path the OS scheduler (launchd/cron) AND the UI's fallback "Run now" both
call; launch-time catch-up (SC8) lands here too. Orchestration only — every scoring/resolution/
frontier decision lives in ``ampere.domain`` (pure), reached through the injected ports (invariant
#1). The ``UnitOfWork`` owns the transaction so a failed run leaves the prior snapshot intact (SC6).
"""

from __future__ import annotations

from datetime import date

from ampere.config import (
    DEFAULT_KEYWORD,
    DEFAULT_PRICE_MAX,
    DEFAULT_PRICE_MIN,
    PERFORMANCE_WEIGHTS,
    SCORING_VERSION,
)
from ampere.domain.dedup import dedup_cheapest_per_sku
from ampere.domain.diff import compute_diff
from ampere.domain.frontier import pareto_frontier
from ampere.domain.models import (
    Candidate,
    Condition,
    Confidence,
    Listing,
    RawListing,
    RunResult,
    Score,
    Weights,
)
from ampere.domain.pricing import effective_price, price_confidence
from ampere.domain.resolve import resolve
from ampere.domain.scoring import battery, capability, performance, value
from ampere.ports.repositories import UnitOfWork
from ampere.ports.search_source import SearchSource

_PERF_METRICS = tuple(PERFORMANCE_WEIGHTS)


def _build_listing(
    raw: RawListing, snapshot_date: date, uow: UnitOfWork, threshold: float
) -> Listing:
    """Resolve + price a raw listing into a ``Listing`` (confidence is set later by scoring)."""
    resolved = resolve(raw.title, uow.devices, uow.aliases, threshold=threshold)
    condition = resolved.cleaned.condition
    # M3 assumption (SPEC Appendix A): with no condition word in the title, a Mall listing is the
    # practical "new" proxy. The resolver deliberately leaves this UNKNOWN (title tokens only).
    if condition is Condition.UNKNOWN and raw.is_mall:
        condition = Condition.NEW
    return Listing(
        shopee_id=raw.shopee_id, snapshot_date=snapshot_date, title=raw.title,
        device_id=resolved.device_id, condition=condition, list_price=raw.list_price,
        effective_price=effective_price(raw), price_confidence=price_confidence(raw),
        shipping_est=raw.shipping_est, voucher_est=raw.voucher_est, cashback_est=raw.cashback_est,
        is_mall=raw.is_mall, seller_rating=raw.seller_rating,
        seller_review_count=raw.seller_review_count, is_star_seller=raw.is_star_seller,
        seller_location=raw.shop_location, url=raw.url, confidence=Confidence.UNMATCHED,
    )


def _score_listing(listing: Listing, uow: UnitOfWork, weights: Weights) -> Score | None:
    """Score one matched listing, or ``None`` if it can't be scored (needs catalog data — §5.4).

    Never fabricates: a missing benchmark re-weights the present metrics and marks ``partial``
    (done inside ``performance``); a device with no chipset/benchmarks/battery at all is simply
    unscoreable and is excluded from the frontier rather than guessed (invariant #4).
    """
    if listing.device_id is None:
        return None
    device = uow.devices.get(listing.device_id)
    if device is None or device.chipset_id is None:
        return None
    chipset = uow.chipsets.get(device.chipset_id)
    if chipset is None:
        return None
    try:
        perf = performance(chipset, device.throttle_modifier)
        batt = battery(device)
        cap = capability(perf, batt, weights)
        val = value(cap, listing.effective_price)
    except ValueError:
        return None  # zero benchmarks / no battery bound / non-positive price — not scoreable

    all_perf_present = all(getattr(chipset, m) is not None for m in _PERF_METRICS)
    confidence = Confidence.FULL if all_perf_present else Confidence.PARTIAL
    return Score(
        listing_id=listing.shopee_id, snapshot_date=listing.snapshot_date, performance=perf,
        battery=batt, capability=cap, value=val, is_frontier=False, confidence=confidence,
        scoring_version=SCORING_VERSION,
    )


def run_daily(
    *,
    source: SearchSource,
    uow: UnitOfWork,
    snapshot_date: date,
    keyword: str = DEFAULT_KEYWORD,
    price_min: int = DEFAULT_PRICE_MIN,
    price_max: int = DEFAULT_PRICE_MAX,
    mall_only: bool = False,
    weights: Weights | None = None,
    threshold: float = 85.0,
) -> RunResult:
    """Run one idempotent daily snapshot. Re-running the same date replaces, never duplicates."""
    weights = weights or Weights()
    run_id = uow.runs.start(snapshot_date, source.kind)  # 'running' marker (autocommitted)
    try:
        # Diff baseline: the most recent snapshot strictly before today (so a same-date re-run
        # still diffs against the prior day, not itself).
        prior_date = uow.listings.latest_snapshot_before(snapshot_date)
        prior = uow.listings.for_snapshot(prior_date) if prior_date else []

        # 1. fetch  2. resolve + effective price
        raws = source.search(keyword, price_min, price_max, mall_only=mall_only)
        listings = [_build_listing(raw, snapshot_date, uow, threshold) for raw in raws]

        # 3. score matched listings; a scoreable listing's confidence mirrors its score.
        scores_by_id: dict[str, Score] = {}
        sku_of: dict[str, tuple[str, str]] = {}
        scoreable: list[Listing] = []
        for listing in listings:
            score = _score_listing(listing, uow, weights)
            if score is None:
                continue
            listing.confidence = score.confidence
            scores_by_id[listing.shopee_id] = score
            device = uow.devices.get(listing.device_id)  # not None: scoring succeeded
            sku_of[listing.device_id] = (device.model, device.variant)  # type: ignore[index]
            scoreable.append(listing)

        # 4. dedup to cheapest-per-SKU (§5.8), then 5. Pareto frontier over that deduped set.
        best_listings, rollups = dedup_cheapest_per_sku(scoreable, lambda d: sku_of[d])
        candidates = [
            Candidate(
                listing_id=listing.shopee_id, model=sku_of[listing.device_id][0],  # type: ignore[index]
                variant=sku_of[listing.device_id][1], condition=listing.condition,  # type: ignore[index]
                effective_price=listing.effective_price,
                capability=scores_by_id[listing.shopee_id].capability,
            )
            for listing in best_listings
        ]
        frontier_ids = pareto_frontier(candidates)
        for listing_id in frontier_ids:
            scores_by_id[listing_id].is_frontier = True

        # 6. diff vs the prior snapshot (over all listings, keyed on shopee_id).
        diff = compute_diff(prior, listings, snapshot_date=snapshot_date, prior_date=prior_date)

        # 7. persist atomically: all-or-nothing for this snapshot_date (SC6).
        with uow.transaction():
            uow.listings.replace_snapshot(snapshot_date, listings)
            uow.scores.replace_snapshot(snapshot_date, list(scores_by_id.values()))
            uow.sku_rollup.replace_snapshot(snapshot_date, rollups)
            uow.runs.finish(run_id, status="ok", listing_count=len(listings))

        return RunResult(
            snapshot_date=snapshot_date, status="ok", source_kind=source.kind,
            listing_count=len(listings),
            matched_count=sum(listing.device_id is not None for listing in listings),
            frontier_size=len(frontier_ids), diff=diff,
        )
    except Exception:
        # The data write rolled back (if it had started); record the failure for observability.
        uow.runs.finish(run_id, status="failed", listing_count=0)
        raise


def main() -> int:
    """Headless entrypoint (``ampere-run-daily``) for the OS scheduler + launch-time catch-up."""
    raise NotImplementedError("M6: wire config + adapters, then call run_daily()")

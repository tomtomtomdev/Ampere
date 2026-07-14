"""The daily use-case + headless entrypoint (SPEC §2, §8a; SC6, SC8).

Pipeline:  fetch -> resolve -> effective_price -> dedup-cheapest-per-SKU -> score -> frontier
           -> diff vs prior snapshot -> persist (idempotent + transactional per snapshot_date).

This is the single code path the OS scheduler (launchd/cron) AND the UI's fallback "Run now" both
call; launch-time catch-up (SC8) lands here too. Orchestration only — every scoring/resolution/
frontier decision lives in ``ampere.domain`` (pure), reached through the injected ports (invariant
#1). The scoring/dedup/frontier pass is shared with the web read models via ``score_snapshot`` so
the dashboard at the default weights reproduces exactly what is persisted (SC3). The ``UnitOfWork``
owns the transaction so a failed run leaves the prior snapshot intact (SC6).
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date

from ampere.application.snapshot import score_snapshot
from ampere.config import (
    DEFAULT_KEYWORD,
    DEFAULT_PRICE_MAX,
    DEFAULT_PRICE_MIN,
)
from ampere.domain.diff import compute_diff
from ampere.domain.models import (
    Condition,
    Confidence,
    Listing,
    RawListing,
    RunResult,
    Weights,
)
from ampere.domain.pricing import effective_price, price_confidence
from ampere.domain.resolve import resolve
from ampere.ports.repositories import UnitOfWork
from ampere.ports.search_source import SearchSource

logger = logging.getLogger("ampere.run_daily")


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

        # 3-5. score matched listings, dedup cheapest-per-SKU, flag the Pareto frontier (shared
        # with the web read models). A scoreable listing's confidence mirrors its score.
        scored = score_snapshot(listings, uow, weights)
        for listing in listings:
            score = scored.scores_by_id.get(listing.shopee_id)
            if score is not None:
                listing.confidence = score.confidence

        # 6. diff vs the prior snapshot (over all listings, keyed on shopee_id).
        diff = compute_diff(prior, listings, snapshot_date=snapshot_date, prior_date=prior_date)

        # 7. persist atomically: all-or-nothing for this snapshot_date (SC6).
        with uow.transaction():
            uow.listings.replace_snapshot(snapshot_date, listings)
            uow.scores.replace_snapshot(snapshot_date, list(scored.scores_by_id.values()))
            uow.sku_rollup.replace_snapshot(snapshot_date, scored.rollups)
            uow.runs.finish(run_id, status="ok", listing_count=len(listings))

        return RunResult(
            snapshot_date=snapshot_date, status="ok", source_kind=source.kind,
            listing_count=len(listings),
            matched_count=sum(listing.device_id is not None for listing in listings),
            frontier_size=len(scored.frontier_ids), diff=diff,
        )
    except Exception:
        # The data write rolled back (if it had started); record the failure for observability.
        uow.runs.finish(run_id, status="failed", listing_count=0)
        raise


def catch_up(
    uow: UnitOfWork,
    source: SearchSource,
    *,
    today: date,
    keyword: str = DEFAULT_KEYWORD,
    price_min: int = DEFAULT_PRICE_MIN,
    price_max: int = DEFAULT_PRICE_MAX,
    mall_only: bool = False,
    weights: Weights | None = None,
) -> RunResult | None:
    """Run today's snapshot unless one already succeeded today (SPEC §8a launch-time catch-up, SC8).

    Guarded so a machine that was asleep at the scheduled time still gets exactly one run for the
    date (via startup), while a machine that already ran skips — never zero, never a duplicate, and
    never a redundant hit on the fragile source. A *failed* today still retries (``last_successful``
    only counts ``ok``)."""
    last = uow.runs.last_successful()
    if last is not None and last >= today:
        logger.info("catch-up: %s already has a successful run — skipping", today)
        return None
    logger.info("catch-up: running the daily snapshot for %s", today)
    return run_daily(
        source=source, uow=uow, snapshot_date=today, keyword=keyword,
        price_min=price_min, price_max=price_max, mall_only=mall_only, weights=weights,
    )


@dataclass
class RunConfig:
    """Headless-run configuration, read from the environment by the OS scheduler (SPEC §8a).

    The default source is ``fixture`` so a bare invocation is safe + offline; point it at a live
    source with ``AMPERE_SOURCE=affiliate`` (preferred, ToS-safe) or ``internal`` (best-effort)."""

    source_kind: str = "fixture"
    keyword: str = DEFAULT_KEYWORD
    price_min: int = DEFAULT_PRICE_MIN
    price_max: int = DEFAULT_PRICE_MAX
    mall_only: bool = False
    db_path: str | None = None  # None → the adapter's DEFAULT_DB_PATH
    cache_dir: str | None = None  # JsonFileCache dir for a live source ("cache hard", §6)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> RunConfig:
        env = os.environ if env is None else env
        flag = env.get("AMPERE_MALL_ONLY", "").strip().lower() in {"1", "true", "yes", "on"}
        return cls(
            source_kind=env.get("AMPERE_SOURCE", cls.source_kind),
            keyword=env.get("AMPERE_KEYWORD", cls.keyword),
            price_min=int(env.get("AMPERE_PRICE_MIN", cls.price_min)),
            price_max=int(env.get("AMPERE_PRICE_MAX", cls.price_max)),
            mall_only=flag,
            db_path=env.get("AMPERE_DB") or None,
            cache_dir=env.get("AMPERE_CACHE_DIR") or None,
        )


def main() -> int:
    """Headless entrypoint (``ampere-run-daily``) for the OS scheduler + launch-time catch-up (SC8).

    Composition root for the daily job: wires the SQLite UoW, the configured ``SearchSource`` (with
    an on-disk cache for live sources), and the real catalog seed around ``catch_up``. Adapter
    imports are local so the module's use-case logic stays adapter-free (invariant #1). A failed run
    is transactional (SC6): it leaves no partial snapshot and exits non-zero for the scheduler."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    from ampere.adapters.repos import db
    from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
    from ampere.adapters.sources import build_source
    from ampere.adapters.sources._common import JsonFileCache
    from ampere.application.catalog_seed import load_seed

    config = RunConfig.from_env()
    conn = db.connect(config.db_path or db.DEFAULT_DB_PATH)
    db.create_schema(conn)
    uow = SqliteUnitOfWork(conn)
    try:
        if not uow.devices.all():  # first run on this DB → load the real reference catalog (§6)
            chips, devs = load_seed(uow)
            logger.info("seeded catalog: %d chipsets, %d devices", chips, devs)

        source_kwargs: dict = {}
        if config.cache_dir and config.source_kind != "fixture":
            source_kwargs["cache"] = JsonFileCache(config.cache_dir)
        source = build_source(config.source_kind, **source_kwargs)

        result = catch_up(
            uow, source, today=date.today(), keyword=config.keyword,
            price_min=config.price_min, price_max=config.price_max, mall_only=config.mall_only,
        )
        if result is None:
            logger.info("already ran today — nothing to do")
        else:
            logger.info(
                "run %s: %d listings, %d matched, frontier %d",
                result.snapshot_date, result.listing_count, result.matched_count,
                result.frontier_size,
            )
        return 0
    except Exception:
        logger.exception("daily run failed (transactional — no partial snapshot written)")
        return 1
    finally:
        uow.close()

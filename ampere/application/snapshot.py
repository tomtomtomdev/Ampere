"""Score a snapshot's listings — the shared core of the persist path AND the read models.

``run_daily`` (M3) computes scores once and persists them at the default weights; the M4 web read
models re-run this same computation on demand at UI-tuned weights ("sliders re-score live"). Both
call ``score_snapshot`` so the two paths can never diverge: the dashboard at the default weights
reproduces exactly what was persisted (deterministic, SC3).

Orchestration only — every number comes from ``ampere.domain`` (pure), reached through the injected
``UnitOfWork`` ports (invariant #1). Nothing here is fabricated: a listing whose device lacks a
chipset/benchmarks/battery is simply unscoreable and dropped from the frontier (invariant #4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ampere.config import PERFORMANCE_WEIGHTS, SCORING_VERSION
from ampere.domain.dedup import dedup_cheapest_per_sku
from ampere.domain.frontier import pareto_frontier
from ampere.domain.models import (
    Candidate,
    Confidence,
    Listing,
    Score,
    SkuRollup,
    Weights,
)
from ampere.domain.scoring import battery, capability, performance, value
from ampere.ports.repositories import UnitOfWork

_PERF_METRICS = tuple(PERFORMANCE_WEIGHTS)


@dataclass
class ScoredSnapshot:
    """Everything the persist path and the read models need from one scoring pass."""

    scores_by_id: dict[str, Score] = field(default_factory=dict)  # scoreable; frontier flag set
    sku_of: dict[str, tuple[str, str]] = field(default_factory=dict)  # device_id -> model, variant
    best_listings: list[Listing] = field(default_factory=list)  # deduped cheapest-per-SKU
    rollups: list[SkuRollup] = field(default_factory=list)
    frontier_ids: set[str] = field(default_factory=set)


def score_listing(listing: Listing, uow: UnitOfWork, weights: Weights) -> Score | None:
    """Score one matched listing, or ``None`` if it can't be scored (needs catalog data — §5.4).

    Never fabricates: a missing benchmark re-weights the present metrics and marks ``partial``
    (inside ``performance``); a device with no chipset/benchmarks/battery is simply unscoreable and
    returns ``None`` (excluded from the frontier rather than guessed — invariant #4).
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


def score_snapshot(
    listings: list[Listing],
    uow: UnitOfWork,
    weights: Weights,
    *,
    blended: bool = False,
) -> ScoredSnapshot:
    """Score matched listings, dedup to cheapest-per-SKU (§5.8), flag the Pareto frontier (§5.3).

    ``blended`` unions all conditions into one frontier; the default keeps per-condition frontiers
    (a used ex-flagship can't silently dominate every new budget phone). Listing iteration order is
    preserved into ``scores_by_id`` so persisted output is stable across re-runs (SC3).
    """
    scores_by_id: dict[str, Score] = {}
    sku_of: dict[str, tuple[str, str]] = {}
    scoreable: list[Listing] = []
    for listing in listings:
        score = score_listing(listing, uow, weights)
        if score is None:
            continue
        scores_by_id[listing.shopee_id] = score
        device = uow.devices.get(listing.device_id)  # not None: scoring succeeded
        sku_of[listing.device_id] = (device.model, device.variant)  # type: ignore[index]
        scoreable.append(listing)

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
    frontier_ids = pareto_frontier(candidates, blended=blended)
    for listing_id in frontier_ids:
        scores_by_id[listing_id].is_frontier = True

    return ScoredSnapshot(
        scores_by_id=scores_by_id, sku_of=sku_of, best_listings=best_listings,
        rollups=rollups, frontier_ids=frontier_ids,
    )

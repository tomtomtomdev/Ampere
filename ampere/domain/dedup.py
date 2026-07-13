"""Dedup to cheapest-per-SKU — SPEC §5.8. PURE, deterministic, zero I/O.

Before the frontier, collapse listings to one row per ``(model, variant, condition)`` = the
lowest-effective-price instance, keeping a ``duplicate_count``. Without this the frontier plots
listing noise and one mispriced outlier can define it (§5.8). ``shopee_id`` dedup alone is
insufficient — it only catches exact re-posts, not the many sellers carrying the same SKU.

Unmatched listings (no ``device_id``) have no known SKU, so they are excluded here and never reach
the frontier; they are stored + surfaced in the needs-mapping queue instead (§5.4).
"""

from __future__ import annotations

from collections.abc import Callable

from ampere.domain.models import Condition, Listing, SkuRollup


def dedup_cheapest_per_sku(
    listings: list[Listing],
    sku_of: Callable[[str], tuple[str, str]],
) -> tuple[list[Listing], list[SkuRollup]]:
    """Collapse to the cheapest listing per ``(device_id, condition)`` (== SKU).

    ``sku_of`` maps a ``device_id`` to its canonical ``(model, variant)`` for the rollup text —
    since ``device_id`` uniquely determines model + variant, it is the equivalent, cleaner SKU key.
    Returns ``(best_listings, rollups)`` both sorted deterministically by ``(model, variant,
    condition)``. Ties on effective price break on the lowest ``shopee_id`` so runs are stable.
    """
    groups: dict[tuple[str, Condition], list[Listing]] = {}
    for listing in listings:
        if listing.device_id is None:
            continue  # unmatched -> no known SKU (§5.4)
        groups.setdefault((listing.device_id, listing.condition), []).append(listing)

    by_id: dict[str, Listing] = {}
    rollups: list[SkuRollup] = []
    for (device_id, condition), members in groups.items():
        best = min(members, key=lambda listing: (listing.effective_price, listing.shopee_id))
        model, variant = sku_of(device_id)
        by_id[best.shopee_id] = best
        rollups.append(
            SkuRollup(
                snapshot_date=best.snapshot_date,
                model=model,
                variant=variant,
                condition=condition,
                best_listing_id=best.shopee_id,
                duplicate_count=len(members),
            )
        )

    rollups.sort(key=lambda r: (r.model, r.variant, r.condition))
    best_listings = [by_id[r.best_listing_id] for r in rollups]  # same deterministic order
    return best_listings, rollups

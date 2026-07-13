"""Snapshot diff — SPEC G5, §8 "Changes". PURE, deterministic, zero I/O.

Compares the current snapshot against the most recent prior one and surfaces what a watcher cares
about: new arrivals, disappeared listings, and effective-price moves (drops vs increases). Keyed on
``shopee_id``; prices compared are ``effective_price`` (the value-axis price, §5.7).
"""

from __future__ import annotations

from datetime import date

from ampere.domain.models import Listing, PriceChange, SnapshotDiff


def compute_diff(
    prior: list[Listing],
    current: list[Listing],
    *,
    snapshot_date: date,
    prior_date: date | None,
) -> SnapshotDiff:
    """Diff ``current`` against ``prior``. With no prior, every current listing is a new arrival."""
    prior_by_id = {listing.shopee_id: listing for listing in prior}
    current_by_id = {listing.shopee_id: listing for listing in current}

    new_arrivals = sorted(current_by_id.keys() - prior_by_id.keys())
    removed = sorted(prior_by_id.keys() - current_by_id.keys())

    price_drops: list[PriceChange] = []
    price_increases: list[PriceChange] = []
    for shopee_id in sorted(current_by_id.keys() & prior_by_id.keys()):
        was = prior_by_id[shopee_id].effective_price
        now = current_by_id[shopee_id].effective_price
        if now == was:
            continue
        change = PriceChange(
            shopee_id=shopee_id, prior_effective_price=was, current_effective_price=now
        )
        (price_drops if now < was else price_increases).append(change)

    return SnapshotDiff(
        snapshot_date=snapshot_date,
        prior_date=prior_date,
        new_arrivals=new_arrivals,
        removed=removed,
        price_drops=price_drops,
        price_increases=price_increases,
    )

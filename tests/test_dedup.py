"""M3 — dedup to cheapest-per-SKU (SPEC §5.8), written test-first. Pure, deterministic.

Sellers spam the same phone; before the frontier we collapse to one row per
``(model, variant, condition)`` = the lowest-effective-price instance, keeping a
``duplicate_count``. Unmatched listings (no ``device_id``) have no known SKU → excluded here
(they're stored + surfaced in the needs-mapping queue, never on the frontier — §5.4).
"""

from __future__ import annotations

from datetime import date

from ampere.domain.dedup import dedup_cheapest_per_sku
from ampere.domain.models import Condition, Listing

_D = date(2026, 7, 13)

# device_id -> (model, variant); the rollup needs the canonical SKU text.
_SKU = {
    "dev-rn13": ("Redmi Note 13", "8/256"),
    "dev-a15": ("Galaxy A15", "8/256"),
}


def _listing(shopee_id, device_id, price, condition=Condition.NEW) -> Listing:
    return Listing(
        shopee_id=shopee_id, snapshot_date=_D, title=shopee_id, device_id=device_id,
        condition=condition, list_price=price, effective_price=price,
    )


def _sku_of(device_id: str) -> tuple[str, str]:
    return _SKU[device_id]


def test_collapses_same_sku_to_cheapest():
    listings = [
        _listing("A", "dev-rn13", 1_899_000),
        _listing("B", "dev-rn13", 1_799_000),  # cheapest
        _listing("C", "dev-rn13", 1_850_000),
    ]
    best, rollups = dedup_cheapest_per_sku(listings, _sku_of)
    assert [b.shopee_id for b in best] == ["B"]
    assert len(rollups) == 1
    r = rollups[0]
    assert r.best_listing_id == "B"
    assert r.duplicate_count == 3
    assert (r.model, r.variant, r.condition) == ("Redmi Note 13", "8/256", Condition.NEW)


def test_different_condition_is_a_different_sku():
    # A used unit does NOT collapse into the new one (SPEC §5.3 per-condition frontier).
    listings = [
        _listing("A", "dev-rn13", 1_899_000, Condition.NEW),
        _listing("B", "dev-rn13", 1_420_000, Condition.USED),
    ]
    best, rollups = dedup_cheapest_per_sku(listings, _sku_of)
    assert {b.shopee_id for b in best} == {"A", "B"}
    assert len(rollups) == 2


def test_unmatched_listings_are_excluded():
    listings = [
        _listing("A", "dev-rn13", 1_899_000),
        _listing("U", None, 1_550_000),  # unmatched -> not a known SKU
    ]
    best, rollups = dedup_cheapest_per_sku(listings, _sku_of)
    assert [b.shopee_id for b in best] == ["A"]
    assert len(rollups) == 1


def test_price_tie_is_broken_deterministically():
    listings = [
        _listing("B", "dev-rn13", 1_800_000),
        _listing("A", "dev-rn13", 1_800_000),
    ]
    best, _ = dedup_cheapest_per_sku(listings, _sku_of)
    assert [b.shopee_id for b in best] == ["A"]  # lowest shopee_id wins the tie


def test_distinct_skus_both_survive_and_output_is_sorted():
    listings = [
        _listing("Z", "dev-rn13", 1_899_000),
        _listing("A", "dev-a15", 1_999_000),
    ]
    best, rollups = dedup_cheapest_per_sku(listings, _sku_of)
    assert {b.shopee_id for b in best} == {"Z", "A"}
    # deterministic ordering by (model, variant, condition)
    assert [r.model for r in rollups] == ["Galaxy A15", "Redmi Note 13"]

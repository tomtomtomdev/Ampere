"""M3 — snapshot diff (SPEC G5, §8 "Changes"), written test-first. Pure, deterministic.

New arrivals + price drops vs the most recent prior snapshot. Diff is keyed on ``shopee_id`` and
compares ``effective_price`` (the value-axis price, §5.7).
"""

from __future__ import annotations

from datetime import date

from ampere.domain.diff import compute_diff
from ampere.domain.models import Condition, Listing

_TODAY = date(2026, 7, 13)
_YDAY = date(2026, 7, 12)


def _listing(shopee_id, price) -> Listing:
    return Listing(
        shopee_id=shopee_id, snapshot_date=_TODAY, title=shopee_id, device_id="d",
        condition=Condition.NEW, list_price=price, effective_price=price,
    )


def test_no_prior_makes_everything_a_new_arrival():
    current = [_listing("A", 1_500_000), _listing("B", 1_600_000)]
    d = compute_diff([], current, snapshot_date=_TODAY, prior_date=None)
    assert set(d.new_arrivals) == {"A", "B"}
    assert d.removed == [] and d.price_drops == [] and d.price_increases == []
    assert d.prior_date is None


def test_new_arrival_and_price_drop():
    prior = [_listing("A", 1_899_000), _listing("B", 1_600_000)]
    current = [_listing("A", 1_799_000), _listing("C", 1_400_000)]  # A dropped, B gone, C new
    d = compute_diff(prior, current, snapshot_date=_TODAY, prior_date=_YDAY)

    assert d.new_arrivals == ["C"]
    assert d.removed == ["B"]
    assert [pc.shopee_id for pc in d.price_drops] == ["A"]
    drop = d.price_drops[0]
    assert (drop.prior_effective_price, drop.current_effective_price) == (1_899_000, 1_799_000)
    assert drop.delta == -100_000
    assert d.price_increases == []
    assert d.prior_date == _YDAY


def test_price_increase_is_tracked_separately():
    prior = [_listing("A", 1_500_000)]
    current = [_listing("A", 1_650_000)]
    d = compute_diff(prior, current, snapshot_date=_TODAY, prior_date=_YDAY)
    assert d.price_drops == []
    assert [pc.shopee_id for pc in d.price_increases] == ["A"]
    assert d.price_increases[0].delta == 150_000


def test_unchanged_price_is_not_reported():
    prior = [_listing("A", 1_500_000)]
    current = [_listing("A", 1_500_000)]
    d = compute_diff(prior, current, snapshot_date=_TODAY, prior_date=_YDAY)
    assert d.new_arrivals == [] and d.price_drops == [] and d.price_increases == []


def test_outputs_are_sorted_for_determinism():
    prior = [_listing("A", 1_000_000), _listing("B", 1_000_000)]
    current = [
        _listing("Z", 1_000_000), _listing("M", 1_000_000),  # new
        _listing("A", 900_000), _listing("B", 800_000),  # both dropped
    ]
    d = compute_diff(prior, current, snapshot_date=_TODAY, prior_date=_YDAY)
    assert d.new_arrivals == ["M", "Z"]
    assert [pc.shopee_id for pc in d.price_drops] == ["A", "B"]

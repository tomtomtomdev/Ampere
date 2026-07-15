"""M7 — wiring the optional longevity bonus (§11.1) + trust penalty (§5.6) into ``score_snapshot``.

Both are OFF by default so the persisted daily scores + ``SCORING_VERSION`` are unchanged (SC3); a
caller (the web read models) opts in per request, like the weight sliders. The longevity bonus is
added to ``capability`` (so it also moves the value axis + frontier); the trust penalty multiplies
``value`` only. Listings are built by hand over the demo catalog so the deltas are exact and
hand-checkable — the demo device ``dev-a15-8-256`` promises 4 OS-update years, ``dev-rn13-8-256`` 3.
"""

from __future__ import annotations

from datetime import date

import pytest
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.application.demo_seed import seed_catalog
from ampere.application.snapshot import score_snapshot
from ampere.config import TRUST_PENALTY_FACTOR
from ampere.domain.longevity import longevity_bonus
from ampere.domain.models import Condition, Listing, Weights

_DAY = date(2026, 7, 14)


@pytest.fixture
def uow() -> SqliteUnitOfWork:
    conn = db.connect(":memory:")
    db.create_schema(conn)
    u = SqliteUnitOfWork(conn)
    seed_catalog(u)  # catalog only — we supply listings by hand
    return u


def _listing(
    shopee_id: str, device_id: str, *, price: int = 1_500_000, is_mall: bool = True,
    rating: float | None = 4.9, condition: Condition = Condition.NEW,
) -> Listing:
    return Listing(
        shopee_id=shopee_id, snapshot_date=_DAY, title=shopee_id, device_id=device_id,
        condition=condition, list_price=price, effective_price=price, is_mall=is_mall,
        seller_rating=rating,
    )


class TestLongevityWiring:
    def test_bonus_adds_to_capability_by_exactly_the_os_years_bonus(self, uow):
        listings = [_listing("A", "dev-a15-8-256")]  # os_updates_years == 4 in the demo catalog
        w = Weights()
        base = score_snapshot(listings, uow, w).scores_by_id["A"]
        boosted = score_snapshot(listings, uow, w, longevity_enabled=True).scores_by_id["A"]
        assert longevity_bonus(4) > 0  # sanity: this device actually earns a bonus
        assert boosted.capability == pytest.approx(base.capability + longevity_bonus(4))

    def test_value_rises_with_capability(self, uow):
        listings = [_listing("A", "dev-a15-8-256")]
        w = Weights()
        base = score_snapshot(listings, uow, w).scores_by_id["A"]
        boosted = score_snapshot(listings, uow, w, longevity_enabled=True).scores_by_id["A"]
        assert boosted.value > base.value  # value = capability / price, and capability went up

    def test_off_by_default(self, uow):
        listings = [_listing("A", "dev-a15-8-256")]
        w = Weights()
        default = score_snapshot(listings, uow, w).scores_by_id["A"]
        off = score_snapshot(listings, uow, w, longevity_enabled=False).scores_by_id["A"]
        assert default.capability == off.capability


class TestTrustPenaltyWiring:
    def test_penalizes_low_trust_non_mall_value_only(self, uow):
        listings = [_listing("A", "dev-rn13-8-256", is_mall=False, rating=4.0)]
        w = Weights()
        base = score_snapshot(listings, uow, w).scores_by_id["A"]
        pen = score_snapshot(listings, uow, w, trust_penalty_enabled=True).scores_by_id["A"]
        assert pen.value == pytest.approx(base.value * TRUST_PENALTY_FACTOR)
        assert pen.capability == base.capability  # the penalty is on value, never capability

    def test_no_penalty_for_mall(self, uow):
        listings = [_listing("A", "dev-rn13-8-256", is_mall=True, rating=4.0)]
        w = Weights()
        base = score_snapshot(listings, uow, w).scores_by_id["A"]
        pen = score_snapshot(listings, uow, w, trust_penalty_enabled=True).scores_by_id["A"]
        assert pen.value == base.value

    def test_no_penalty_for_high_rating(self, uow):
        listings = [_listing("A", "dev-rn13-8-256", is_mall=False, rating=4.9)]
        w = Weights()
        base = score_snapshot(listings, uow, w).scores_by_id["A"]
        pen = score_snapshot(listings, uow, w, trust_penalty_enabled=True).scores_by_id["A"]
        assert pen.value == base.value

    def test_off_by_default(self, uow):
        listings = [_listing("A", "dev-rn13-8-256", is_mall=False, rating=4.0)]
        w = Weights()
        default = score_snapshot(listings, uow, w).scores_by_id["A"]
        off = score_snapshot(listings, uow, w, trust_penalty_enabled=False).scores_by_id["A"]
        assert default.value == off.value


class TestDefaultsUnchanged:
    def test_defaults_match_both_off(self, uow):
        # SC3: the persist path (run_daily) calls score_snapshot with defaults; those must equal
        # explicit both-off so persisted scores + SCORING_VERSION never move when the toggles ship.
        listings = [
            _listing("A", "dev-a15-8-256", is_mall=False, rating=4.0),
            _listing("B", "dev-rn13-8-256"),
        ]
        w = Weights()
        default = score_snapshot(listings, uow, w)
        off = score_snapshot(listings, uow, w, longevity_enabled=False, trust_penalty_enabled=False)
        assert default.scores_by_id == off.scores_by_id
        assert default.frontier_ids == off.frontier_ids

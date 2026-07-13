"""M3 — SQLite repos + UnitOfWork, written test-first. These are the I/O adapters behind the
``ports.repositories`` Protocols; the pipeline (``run_daily``) composes them transactionally.

Uses in-memory SQLite (one shared connection). Focus: model round-trips, ``replace_snapshot``
idempotency (SC3/SC6 — no duplicate rows), ``latest_snapshot_before`` for diffing, run tracking,
and the ``transaction()`` commit/rollback boundary (SC6).
"""

from __future__ import annotations

from datetime import date

import pytest
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.domain.models import (
    Chipset,
    Condition,
    Confidence,
    Device,
    Listing,
    PriceConfidence,
    Score,
    SkuRollup,
)
from ampere.ports.repositories import UnitOfWork

_D1 = date(2026, 7, 12)
_D2 = date(2026, 7, 13)


@pytest.fixture
def uow() -> SqliteUnitOfWork:
    conn = db.connect(":memory:")
    db.create_schema(conn)
    return SqliteUnitOfWork(conn)


@pytest.fixture
def luow(uow: SqliteUnitOfWork) -> SqliteUnitOfWork:
    """A UoW with a chipset + device seeded so ``listings.device_id`` FK is satisfied."""
    uow.chipsets.upsert(Chipset(id="c", name="Test SoC"))
    uow.devices.upsert(Device(id="dev-rn13", brand="Xiaomi", model="Redmi Note 13",
                              variant="8/256", chipset_id="c"))
    return uow


def _listing(shopee_id, price, snapshot=_D2, device_id="dev-rn13") -> Listing:
    return Listing(
        shopee_id=shopee_id, snapshot_date=snapshot, title=f"title {shopee_id}",
        device_id=device_id, condition=Condition.NEW, list_price=price, effective_price=price,
        price_confidence=PriceConfidence.PARTIAL, is_mall=True, seller_rating=4.8,
        confidence=Confidence.FULL,
    )


def _score(listing_id, snapshot=_D2) -> Score:
    return Score(
        listing_id=listing_id, snapshot_date=snapshot, performance=60.0, battery=55.0,
        capability=57.75, value=32.1, is_frontier=True, confidence=Confidence.FULL,
        scoring_version="v2.1.0",
    )


def test_uow_satisfies_the_port(uow):
    assert isinstance(uow, UnitOfWork)


class TestCatalogRepos:
    def test_chipset_round_trip(self, uow):
        c = Chipset(id="sd4g2", name="Snapdragon 4 Gen 2", vendor="Qualcomm",
                    gb6_single=900, gb6_multi=2000, antutu=450_000, wildlife=850)
        uow.chipsets.upsert(c)
        assert uow.chipsets.get("sd4g2") == c
        assert uow.chipsets.all() == [c]

    def test_device_round_trip_and_candidates(self, uow):
        uow.chipsets.upsert(Chipset(id="sd4g2", name="Snapdragon 4 Gen 2"))
        d = Device(id="poco-m6-5g-6-128", brand="Xiaomi", model="Poco M6 5G", variant="6/128",
                   chipset_id="sd4g2", active_use_hours=13.5)
        uow.devices.upsert(d)
        assert uow.devices.get("poco-m6-5g-6-128") == d
        # candidates_for powers the resolver (DeviceCatalogPort) — "brand model variant".
        expected = [("poco-m6-5g-6-128", "Xiaomi Poco M6 5G 6/128")]
        assert uow.devices.candidates_for("Xiaomi") == expected
        assert uow.devices.candidates_for(None) == expected
        assert uow.devices.candidates_for("Samsung") == []

    def test_alias_remember_and_lookup(self, uow):
        uow.chipsets.upsert(Chipset(id="c", name="Test SoC"))
        uow.devices.upsert(Device(id="dev-rn13", brand="Xiaomi", model="Redmi Note 13",
                                  variant="8/256", chipset_id="c"))
        assert uow.aliases.lookup("some raw title") is None
        uow.aliases.remember("some raw title", "dev-rn13")
        assert uow.aliases.lookup("some raw title") == "dev-rn13"


class TestListingRepo:
    def test_replace_snapshot_round_trip(self, luow):
        with luow.transaction():
            luow.listings.replace_snapshot(
                _D2, [_listing("A", 1_899_000), _listing("B", 1_799_000)]
            )
        got = {listing.shopee_id: listing for listing in luow.listings.for_snapshot(_D2)}
        assert set(got) == {"A", "B"}
        assert got["A"].effective_price == 1_899_000
        assert got["A"] == _listing("A", 1_899_000)  # full round-trip fidelity

    def test_replace_snapshot_is_idempotent_no_duplicates(self, luow):
        for _ in range(3):
            with luow.transaction():
                luow.listings.replace_snapshot(_D2, [_listing("A", 1_899_000)])
        assert len(luow.listings.for_snapshot(_D2)) == 1  # SC6: re-run replaces, never duplicates

    def test_replace_snapshot_isolates_other_dates(self, luow):
        with luow.transaction():
            luow.listings.replace_snapshot(_D1, [_listing("OLD", 1_500_000, snapshot=_D1)])
        with luow.transaction():
            luow.listings.replace_snapshot(_D2, [_listing("NEW", 1_600_000, snapshot=_D2)])
        assert [listing.shopee_id for listing in luow.listings.for_snapshot(_D1)] == ["OLD"]
        assert [listing.shopee_id for listing in luow.listings.for_snapshot(_D2)] == ["NEW"]

    def test_latest_snapshot_before(self, luow):
        assert luow.listings.latest_snapshot_before(_D2) is None
        with luow.transaction():
            luow.listings.replace_snapshot(_D1, [_listing("A", 1_500_000, snapshot=_D1)])
        assert luow.listings.latest_snapshot_before(_D2) == _D1
        assert luow.listings.latest_snapshot_before(_D1) is None  # strictly earlier only


class TestScoreAndRollupRepos:
    def test_score_round_trip_and_idempotent(self, uow):
        with uow.transaction():
            uow.scores.replace_snapshot(_D2, [_score("A")])
        with uow.transaction():
            uow.scores.replace_snapshot(_D2, [_score("A")])
        got = uow.scores.for_snapshot(_D2)
        assert len(got) == 1 and got[0] == _score("A")

    def test_rollup_round_trip(self, uow):
        r = SkuRollup(snapshot_date=_D2, model="Redmi Note 13", variant="8/256",
                      condition=Condition.NEW, best_listing_id="B", duplicate_count=3)
        with uow.transaction():
            uow.sku_rollup.replace_snapshot(_D2, [r])
        assert uow.sku_rollup.for_snapshot(_D2) == [r]


class TestRunRepo:
    def test_start_finish_and_last_successful(self, uow):
        assert uow.runs.last_successful() is None
        run_id = uow.runs.start(_D2, "fixture")
        assert uow.runs.last_successful() is None  # 'running', not yet successful
        uow.runs.finish(run_id, status="ok", listing_count=7)
        assert uow.runs.last_successful() == _D2

    def test_start_is_idempotent_per_date(self, uow):
        first = uow.runs.start(_D2, "fixture")
        uow.runs.finish(first, status="ok", listing_count=7)
        # a re-run of the same date resets the row rather than creating a duplicate (UNIQUE date).
        uow.runs.start(_D2, "fixture")
        assert uow.runs.last_successful() is None  # reset back to 'running'
        rows = uow._conn.execute("SELECT COUNT(*) FROM runs WHERE snapshot_date=?",
                                 (_D2.isoformat(),)).fetchone()[0]
        assert rows == 1


class TestTransactionBoundary:
    def test_rollback_discards_writes(self, luow):
        with luow.transaction():
            luow.listings.replace_snapshot(_D1, [_listing("KEEP", 1_500_000, snapshot=_D1)])
        with pytest.raises(RuntimeError), luow.transaction():
            luow.listings.replace_snapshot(_D1, [_listing("GONE", 999_000, snapshot=_D1)])
            raise RuntimeError("boom mid-write")
        # the prior snapshot is untouched — the failed write rolled back cleanly (SC6).
        assert [listing.shopee_id for listing in luow.listings.for_snapshot(_D1)] == ["KEEP"]

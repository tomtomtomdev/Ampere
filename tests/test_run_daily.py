"""M3 — the daily use-case (SPEC §2, §5.8, SC3/SC6), written test-first.

Wires FixtureSource -> resolve -> effective_price -> dedup cheapest-per-SKU -> score -> frontier
-> diff -> persist, idempotently + transactionally per ``snapshot_date``. Tests run against
``FixtureSource`` + in-memory SQLite + a small seeded catalog (numbers are ILLUSTRATIVE test data,
not real benchmarks — the real catalog is M6). The three DoD scenarios: correct diff across two
runs; re-run = identical scores + no duplicate rows; a forced mid-run failure leaves the prior
snapshot untouched.
"""

from __future__ import annotations

from datetime import date

import pytest
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.adapters.sources.fixture_source import FixtureSource
from ampere.application.run_daily import run_daily
from ampere.domain.models import (
    BatteryMetricKind,
    Chipset,
    Condition,
    Confidence,
    Device,
    RawListing,
)

_D1 = date(2026, 7, 12)
_D2 = date(2026, 7, 13)

# (chipset_id, gb6_single, gb6_multi, antutu_v10, wildlife_extreme) — illustrative test values.
_CHIPSETS = [
    ("dimensity-6080", 760, 1990, 410_000, 790),
    ("snapdragon-4-gen-2", 900, 2050, 450_000, 850),
    ("helio-g99", 730, 1950, 400_000, 760),
    ("helio-g85", 520, 1620, 360_000, 720),
    ("dimensity-6300", 780, 2100, 430_000, 820),
    ("exynos-1330", 900, 2100, 410_000, 800),
]
# (device_id, brand, model, variant, chipset_id, active_use_hours)
_DEVICES = [
    ("dev-rn13-8-256", "Xiaomi", "Redmi Note 13", "8/256", "dimensity-6080", 15.0),
    ("dev-pocom6-6-128", "Xiaomi", "Poco M6 5G", "6/128", "snapdragon-4-gen-2", 13.5),
    ("dev-hot40pro-8-256", "Infinix", "Hot 40 Pro", "8/256", "helio-g99", 16.0),
    ("dev-a15-8-256", "Samsung", "Galaxy A15", "8/256", "exynos-1330", 14.0),
    ("dev-r13c-8-256", "Xiaomi", "Redmi 13C", "8/256", "helio-g85", 13.0),
    ("dev-rn13r-8-256", "Xiaomi", "Redmi Note 13R", "8/256", "dimensity-6300", 14.5),
]


def _seed_catalog(uow: SqliteUnitOfWork) -> None:
    for cid, s, m, a, w in _CHIPSETS:
        uow.chipsets.upsert(
            Chipset(id=cid, name=cid, gb6_single=s, gb6_multi=m, antutu=a, wildlife=w)
        )
    for did, brand, model, variant, cid, hours in _DEVICES:
        uow.devices.upsert(
            Device(id=did, brand=brand, model=model, variant=variant, chipset_id=cid,
                   active_use_hours=hours, battery_metric_kind=BatteryMetricKind.ACTIVE_USE_V2)
        )


@pytest.fixture
def uow() -> SqliteUnitOfWork:
    conn = db.connect(":memory:")
    db.create_schema(conn)
    u = SqliteUnitOfWork(conn)
    _seed_catalog(u)
    return u


def _run(uow, source, snapshot_date):
    return run_daily(
        source=source, uow=uow, snapshot_date=snapshot_date,
        keyword="android", price_min=1_000_000, price_max=2_000_000,
    )


class TestPipeline:
    def test_persists_resolves_scores_and_flags_frontier(self, uow):
        result = _run(uow, FixtureSource(), _D2)

        listings = uow.listings.for_snapshot(_D2)
        assert len(listings) == 9  # full in-band fixture, incl. 2 unmatched
        assert result.listing_count == 9
        assert result.matched_count == 7  # L22/L23 don't resolve
        assert result.status == "ok" and result.source_kind == "fixture"

        by_id = {listing.shopee_id: listing for listing in listings}
        assert by_id["L01"].device_id == "dev-rn13-8-256"
        assert by_id["L01"].confidence is Confidence.FULL
        # unmatched listing is stored but unscored, device_id NULL (needs-mapping queue, §5.4)
        assert by_id["L22"].device_id is None
        assert by_id["L22"].confidence is Confidence.UNMATCHED

        scores = uow.scores.for_snapshot(_D2)
        assert len(scores) == 7  # only matched listings are scored
        assert result.frontier_size >= 1
        assert any(s.is_frontier for s in scores)
        assert all(s.scoring_version for s in scores)

    def test_effective_price_applies_voucher(self, uow):
        _run(uow, FixtureSource(), _D2)
        l01 = {listing.shopee_id: listing for listing in uow.listings.for_snapshot(_D2)}["L01"]
        assert l01.effective_price == 1_899_000 - 50_000  # voucher_est applied (§5.7)

    def test_mall_listing_without_condition_word_is_treated_as_new(self, uow):
        # SPEC Appendix A: Mall filter is the practical "new" proxy — an M3 assumption, applied
        # here (the resolver leaves it UNKNOWN from title tokens alone).
        raw = RawListing(shopee_id="M1", title="Xiaomi Redmi Note 13 8/256 Garansi Resmi",
                         brand="Xiaomi", variant_raw="8/256", list_price=1_800_000, is_mall=True)
        _run(uow, FixtureSource([raw]), _D2)
        listing = uow.listings.for_snapshot(_D2)[0]
        assert listing.condition is Condition.NEW

    def test_per_condition_sku_rollup(self, uow):
        # L01 (Mall->new) and L04 (used) share a device but are distinct SKUs by condition (§5.3).
        _run(uow, FixtureSource(), _D2)
        rn13 = [r for r in uow.sku_rollup.for_snapshot(_D2) if r.model == "Redmi Note 13"]
        assert {r.condition for r in rn13} == {Condition.NEW, Condition.USED}


class TestIdempotencyAndDeterminism:
    def test_rerun_same_date_is_identical_no_duplicates(self, uow):
        _run(uow, FixtureSource(), _D1)  # an identical prior day
        first = _run(uow, FixtureSource(), _D2)
        scores_1 = uow.scores.for_snapshot(_D2)
        second = _run(uow, FixtureSource(), _D2)  # re-run the same date
        scores_2 = uow.scores.for_snapshot(_D2)

        assert len(uow.listings.for_snapshot(_D2)) == 9  # SC6: no duplicate rows on re-run
        assert scores_1 == scores_2  # SC3: identical scores (deterministic, pinned version)
        # a re-run diffs against the PRIOR day (D1), not itself — identical prior day => no changes.
        assert second.diff.prior_date == _D1
        assert first.diff.new_arrivals == second.diff.new_arrivals == []
        assert first.matched_count == second.matched_count


class TestDiff:
    def _raw(self, shopee_id, title, price, is_mall=True):
        return RawListing(shopee_id=shopee_id, title=title, brand="Xiaomi", variant_raw="8/256",
                          list_price=price, is_mall=is_mall)

    def test_new_arrivals_and_price_drops_across_two_days(self, uow):
        day1 = FixtureSource([
            self._raw("A", "Xiaomi Redmi Note 13 8/256 Garansi Resmi", 1_899_000),
            self._raw("B", "Xiaomi Redmi 13C 8/256 Garansi Resmi", 1_450_000),
        ])
        day2 = FixtureSource([
            self._raw("A", "Xiaomi Redmi Note 13 8/256 Garansi Resmi", 1_799_000),  # price drop
            self._raw("C", "Xiaomi Redmi Note 13R 8/256 Garansi Resmi", 1_750_000),  # new; B gone
        ])
        _run(uow, day1, _D1)
        result = _run(uow, day2, _D2)

        assert result.diff.prior_date == _D1
        assert result.diff.new_arrivals == ["C"]
        assert result.diff.removed == ["B"]
        assert [pc.shopee_id for pc in result.diff.price_drops] == ["A"]
        assert result.diff.price_drops[0].delta == -100_000

    def test_first_ever_run_is_all_new_arrivals(self, uow):
        result = _run(uow, FixtureSource(), _D2)
        assert result.diff.prior_date is None
        assert len(result.diff.new_arrivals) == 9


class TestTransactionalFailure:
    def test_forced_mid_run_failure_leaves_prior_snapshot_untouched(self, uow):
        _run(uow, FixtureSource(), _D1)  # a good prior snapshot
        prior_listings = uow.listings.for_snapshot(_D1)
        prior_scores = uow.scores.for_snapshot(_D1)
        assert prior_listings and prior_scores

        def boom(*_a, **_k):
            raise RuntimeError("simulated disk failure mid-write")

        uow.scores.replace_snapshot = boom  # fail after listings are written, inside the tx

        with pytest.raises(RuntimeError):
            _run(uow, FixtureSource(), _D2)

        # SC6: the failed run rolled back — no partial D2 snapshot, prior D1 intact.
        assert uow.listings.for_snapshot(_D2) == []
        assert uow.listings.for_snapshot(_D1) == prior_listings
        assert uow.scores.for_snapshot(_D1) == prior_scores
        # observability: D1 still successful, D2 recorded as failed.
        assert uow.runs.last_successful() == _D1
        d2_status = uow._conn.execute(
            "SELECT status FROM runs WHERE snapshot_date = ?", (_D2.isoformat(),)
        ).fetchone()["status"]
        assert d2_status == "failed"

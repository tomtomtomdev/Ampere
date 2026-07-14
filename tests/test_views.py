"""M4 — read-model view builders (SPEC §8), written test-first.

These assemble what each of the five screens shows, recomputing scores/dedup/frontier from the
stored snapshot + catalog at UI-tuned weights (the "sliders re-score live" path). All numbers come
from the domain layer via ``score_snapshot``; the builders only shape them for transport. Run
against ``FixtureSource`` + in-memory SQLite + the demo catalog (illustrative data — real catalog
is M6).
"""

from __future__ import annotations

from datetime import date

import pytest
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.application import views
from ampere.application.demo_seed import bootstrap
from ampere.application.views import ViewParams
from ampere.domain.models import Weights

_TODAY = date(2026, 7, 14)
_YESTERDAY = date(2026, 7, 13)


@pytest.fixture
def uow() -> SqliteUnitOfWork:
    conn = db.connect(":memory:")
    db.create_schema(conn)
    u = SqliteUnitOfWork(conn)
    bootstrap(u, today=_TODAY)
    return u


class TestCurrentSnapshot:
    def test_current_snapshot_is_last_successful_run(self, uow):
        assert views.current_snapshot(uow) == _TODAY

    def test_none_when_no_runs(self):
        conn = db.connect(":memory:")
        db.create_schema(conn)
        assert views.current_snapshot(SqliteUnitOfWork(conn)) is None


class TestDashboard:
    def test_points_cover_the_deduped_matched_skus(self, uow):
        view = views.build_dashboard(uow, _TODAY, ViewParams())
        # 7 matched fixture listings collapse to 7 distinct SKUs (L01 new / L04 used are separate).
        assert len(view.points) == 7
        assert {p.shopee_id for p in view.points} >= {"L01", "L04"}
        assert all(p.capability is not None and p.value is not None for p in view.points)

    def test_at_least_one_frontier_point_and_verdict_labels(self, uow):
        view = views.build_dashboard(uow, _TODAY, ViewParams())
        frontier = [p for p in view.points if p.is_frontier]
        assert frontier
        assert all(p.verdict == "ON FRONTIER" for p in frontier)
        assert all(p.verdict == "dominated" for p in view.points if not p.is_frontier)

    def test_top_frontier_ranked_by_value_desc(self, uow):
        view = views.build_dashboard(uow, _TODAY, ViewParams())
        vals = [r.value for r in view.top_frontier]
        assert vals == sorted(vals, reverse=True)
        assert all(r.rank == i + 1 for i, r in enumerate(view.top_frontier))

    def test_weight_slider_re_scores_live(self, uow):
        perf_heavy = views.build_dashboard(uow, _TODAY, ViewParams(weights=Weights(w_perf=0.9)))
        batt_heavy = views.build_dashboard(uow, _TODAY, ViewParams(weights=Weights(w_perf=0.1)))
        cap = {v.shopee_id: v.capability for v in perf_heavy.points}
        cap2 = {v.shopee_id: v.capability for v in batt_heavy.points}
        # Changing the weighting must change capability for at least one device (not a no-op).
        assert cap["L01"] != pytest.approx(cap2["L01"])

    def test_default_weights_reproduce_persisted_scores(self, uow):
        # Determinism (SC3): the read model at default weights == what run_daily persisted.
        view = views.build_dashboard(uow, _TODAY, ViewParams())
        persisted = {s.listing_id: s for s in uow.scores.for_snapshot(_TODAY)}
        for p in view.points:
            assert p.capability == pytest.approx(persisted[p.shopee_id].capability)
            assert p.is_frontier == persisted[p.shopee_id].is_frontier


class TestListings:
    def test_rows_are_deduped_matched_skus_with_display_fields(self, uow):
        view = views.build_listings(uow, _TODAY, ViewParams())
        assert len(view.rows) == 7
        row = {r.shopee_id: r for r in view.rows}["L01"]
        assert row.model == "Redmi Note 13"
        assert row.chip == "Snapdragon 685"
        assert row.effective_price == 1_899_000 - 50_000  # voucher applied (§5.7)
        assert row.duplicate_count == 1
        assert row.confidence in {"full", "partial"}

    def test_unmatched_listings_are_not_in_the_table(self, uow):
        view = views.build_listings(uow, _TODAY, ViewParams())
        assert "L22" not in {r.shopee_id for r in view.rows}  # unmatched -> Catalog queue only


class TestCatalog:
    def test_chipsets_carry_used_by_device_counts(self, uow):
        view = views.build_catalog(uow, _TODAY)
        by_name = {c.name: c for c in view.chipsets}
        assert by_name["Helio G99"].used_by == 2  # Hot 40 Pro + Note 40 (SC7)
        assert by_name["Snapdragon 685"].gb6_single == 900

    def test_needs_mapping_queue_holds_the_unmatched(self, uow):
        view = views.build_catalog(uow, _TODAY)
        ids = {n.shopee_id for n in view.needs_mapping}
        assert ids == {"L22", "L23"}
        assert all(n.title for n in view.needs_mapping)

    def test_devices_listed_with_chipset_name(self, uow):
        view = views.build_catalog(uow, _TODAY)
        dev = {d.model: d for d in view.devices}
        assert dev["Galaxy A15"].chip == "Exynos 1330"
        assert dev["Galaxy A15"].os_updates_years == 4


class TestChanges:
    def test_price_drops_and_new_arrivals_vs_prior_day(self, uow):
        view = views.build_changes(uow, _TODAY, ViewParams())
        assert view.prior_date == _YESTERDAY
        dropped = {d.shopee_id for d in view.price_drops}
        assert {"L01", "L09"} <= dropped
        assert all(d.delta < 0 for d in view.price_drops)
        assert "L18" in {a.shopee_id for a in view.new_arrivals}

    def test_dropped_rows_are_enriched_with_model_and_capability(self, uow):
        view = views.build_changes(uow, _TODAY, ViewParams())
        l01 = {d.shopee_id: d for d in view.price_drops}["L01"]
        assert l01.model == "Redmi Note 13"
        assert l01.capability is not None


class TestSettings:
    def test_exposes_query_weights_and_schedule(self, uow):
        view = views.build_settings(uow, _TODAY, ViewParams(weights=Weights(w_perf=0.6)))
        assert view.weights.w_perf == pytest.approx(0.6)
        assert view.weights.w_batt == pytest.approx(0.4)
        assert view.keyword == "android"
        assert (view.price_min, view.price_max) == (1_000_000, 2_000_000)
        assert view.scoring_version == "v2.1.0"
        assert "fixture" in view.sources
        assert view.schedule.last_run == _TODAY


class TestMeta:
    def test_stats_and_nav_badges(self, uow):
        view = views.build_dashboard(uow, _TODAY, ViewParams())
        meta = view.meta
        assert meta.snapshot_date == _TODAY
        assert meta.stats.raw == 9  # all in-band fixture listings incl. the 2 unmatched
        assert meta.stats.deduped == 7
        assert meta.stats.matched_pct == 78  # round(7/9*100)
        assert meta.nav_badges.catalog == 2  # needs-mapping count

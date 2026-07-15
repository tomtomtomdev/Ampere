"""M9 — static shareable frontier report (SPEC §11.2), written test-first.

§11.2: "keep the frontier/report shareable (a static public page later)". This is the publishable
sibling of the M8 push: a *self-contained* HTML snapshot of the current frontier + best-value pick
+ an inline-SVG scatter, with outbound/affiliate links. It reuses the M4 dashboard read model
(``build_dashboard``) so the published numbers are exactly what the UI shows (deterministic, SC3);
``render_report`` is pure (a fabricated / mutated DTO in → HTML string out), so it is fully offline.
"""

from __future__ import annotations

from datetime import date

import pytest
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.application.demo_seed import bootstrap
from ampere.application.report import _scale, build_report, render_report
from ampere.application.run_daily import RunConfig
from ampere.application.views import current_snapshot

_TODAY = date(2026, 7, 15)


@pytest.fixture
def uow() -> SqliteUnitOfWork:
    conn = db.connect(":memory:")
    db.create_schema(conn)
    u = SqliteUnitOfWork(conn)
    bootstrap(u, today=_TODAY)  # demo catalog + snapshot (has a real frontier)
    return u


class TestBuildReport:
    def test_reuses_dashboard_frontier_and_maps_urls(self, uow):
        report = build_report(uow, current_snapshot(uow), source_kind="affiliate")
        assert report.points  # scored, deduped points
        assert report.top_frontier and report.top_frontier[0].rank == 1
        assert report.meta.source_kind == "affiliate"
        # the frontier table is exactly the is_frontier points from the dashboard
        f_ids = {r.shopee_id for r in report.top_frontier}
        assert f_ids == {p.shopee_id for p in report.points if p.is_frontier}
        # a url slot exists for every point (value may be None — never fabricated)
        assert all(p.shopee_id in report.url_by_id for p in report.points)

    def test_empty_when_no_snapshot(self, uow):
        report = build_report(uow, None)
        assert report.points == [] and report.top_frontier == []


class TestRenderReport:
    def test_is_a_self_contained_html_document(self, uow):
        html = render_report(build_report(uow, current_snapshot(uow)))
        assert html.lstrip().lower().startswith("<!doctype html")
        assert "</html>" in html
        assert "<style>" in html  # CSS is inlined
        # no external assets -> the file is publishable as-is
        assert 'rel="stylesheet"' not in html
        assert "<script src=" not in html
        assert "<link " not in html

    def test_shows_band_date_version_and_every_frontier_model(self, uow):
        report = build_report(uow, current_snapshot(uow))
        html = render_report(report)
        assert report.meta.band_label in html
        assert _TODAY.isoformat() in html
        assert report.meta.scoring_version in html
        for row in report.top_frontier:
            assert row.model in html

    def test_inline_svg_scatter_has_one_circle_per_point(self, uow):
        report = build_report(uow, current_snapshot(uow))
        html = render_report(report)
        assert "<svg" in html
        assert html.count("<circle") == len(report.points)

    def test_outbound_affiliate_link_renders_as_an_anchor(self, uow):
        report = build_report(uow, current_snapshot(uow))
        sid = report.top_frontier[0].shopee_id
        report.url_by_id[sid] = "https://s.shopee.co.id/aff-XYZ"  # §11.2 outbound link
        html = render_report(report)
        assert 'href="https://s.shopee.co.id/aff-XYZ"' in html

    def test_escapes_html_in_dynamic_text(self, uow):
        report = build_report(uow, current_snapshot(uow))
        report.top_frontier[0].model = "Pwn<script>alert(1)</script>"
        html = render_report(report)
        assert "<script>alert(1)</script>" not in html
        assert "&lt;script&gt;" in html

    def test_empty_report_renders_without_crashing(self, uow):
        html = render_report(build_report(uow, None))
        assert html.lstrip().lower().startswith("<!doctype html")
        assert html.count("<circle") == 0


class TestScatterScaling:
    def test_scale_maps_endpoints(self):
        assert _scale(0.0, 0.0, 10.0, 0.0, 100.0) == pytest.approx(0.0)
        assert _scale(10.0, 0.0, 10.0, 0.0, 100.0) == pytest.approx(100.0)
        assert _scale(5.0, 0.0, 10.0, 0.0, 100.0) == pytest.approx(50.0)

    def test_scale_handles_zero_range_without_dividing_by_zero(self):
        # all points share one price/capability -> centre them instead of NaN/inf
        mid = _scale(5.0, 5.0, 5.0, 0.0, 100.0)
        assert mid == pytest.approx(50.0)


class TestReportConfig:
    def test_report_path_defaults_off(self):
        assert RunConfig.from_env({}).report_path is None

    def test_report_path_from_env(self):
        assert RunConfig.from_env({"AMPERE_REPORT_PATH": "/tmp/ampere.html"}).report_path == (
            "/tmp/ampere.html"
        )

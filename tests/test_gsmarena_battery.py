"""M6 — GSMArena battery scraper (SPEC Appendix B, ``gsmarena-device-data`` skill), test-first.

The battery ranking (``battery-test-v2.php3``) is server-rendered HTML — a table of device →
**Active Use Score** shown like ``15:23h`` (15 h 23 min → 15.38 decimal hours, higher = better).
No API, no anti-bot: the fragile bit is only the HTTP fetch, injected as ``fetch(url) -> html`` so
parsing is offline (invariant #2). We store the metric kind (``active_use_v2``) so it is never
mixed with the legacy Endurance rating (§5.1). Numbers are read, never fabricated (invariant #4).

NOTE: Appendix B's HAR captured no page body, so the exact ranking-table markup is *assumed* and
isolated in ``parse_battery_html`` — the one place to adjust once a live page is captured (same
posture as ``AffiliateFeedSource.parse_offer`` in M5).
"""

from __future__ import annotations

from ampere.adapters.scrapers.gsmarena_battery import (
    GsmArenaBatterySource,
    parse_active_use,
    parse_battery_html,
)
from ampere.domain.models import BatteryMetricKind


def _rank_row(name: str, active_use: str) -> str:
    return (
        '<tr class="battery-row">'
        f'<td class="name"><a href="/x.php">{name}</a></td>'
        f'<td class="active-use">{active_use}</td>'
        "</tr>"
    )


RANKING_HTML = (
    "<html><body><table class='battery-ranking'>"
    "<tr><th>Phone</th><th>Active use</th></tr>"
    + _rank_row("Redmi Note 13", "15:23h")
    + _rank_row("Galaxy A15", "13:42h")
    + _rank_row("Infinix Hot 40 Pro", "18:30h")
    + _rank_row("Broken Row", "—")  # unparseable active-use → dropped, not stored as 0
    + "</table></body></html>"
)


class TestParseActiveUse:
    def test_hh_mm_to_decimal_hours(self):
        assert parse_active_use("15:23h") == 15.38  # 15 + 23/60, 2dp
        assert parse_active_use("13:42h") == 13.70
        assert parse_active_use("18:30h") == 18.5

    def test_bare_hours_and_decimal(self):
        assert parse_active_use("17h") == 17.0
        assert parse_active_use("16.9") == 16.9

    def test_unparseable_is_none(self):
        assert parse_active_use("—") is None
        assert parse_active_use("") is None


class TestParseBatteryHtml:
    def test_reads_device_and_hours(self):
        rows = parse_battery_html(RANKING_HTML)
        by_device = {r.device: r for r in rows}
        assert by_device["Redmi Note 13"].active_use_hours == 15.38
        assert by_device["Infinix Hot 40 Pro"].active_use_hours == 18.5

    def test_metric_kind_is_active_use_v2(self):
        rows = parse_battery_html(RANKING_HTML)
        assert all(r.metric_kind is BatteryMetricKind.ACTIVE_USE_V2 for r in rows)

    def test_skips_unparseable_rows(self):
        # The "—" row is dropped rather than stored as a fabricated 0 (invariant #4).
        rows = parse_battery_html(RANKING_HTML)
        assert "Broken Row" not in {r.device for r in rows}
        assert len(rows) == 3


class TestGsmArenaBatterySource:
    def test_fetch_battery_over_injected_transport(self):
        calls: list[str] = []

        def fake_fetch(url: str) -> str:
            calls.append(url)
            return RANKING_HTML

        source = GsmArenaBatterySource(fetch=fake_fetch, ranking_urls=["https://gsmarena/b.php3"])
        readings = source.fetch_battery()

        assert calls == ["https://gsmarena/b.php3"]
        assert {r.device for r in readings} == {"Redmi Note 13", "Galaxy A15", "Infinix Hot 40 Pro"}

    def test_merges_pages_and_dedups_by_device_first_wins(self):
        pages = {
            "p1": "<table>" + _rank_row("Redmi Note 13", "15:23h") + "</table>",
            "p2": "<table>" + _rank_row("Redmi Note 13", "99:00h")  # a dup later in the ranking
            + _rank_row("Poco M6", "16:00h") + "</table>",
        }
        source = GsmArenaBatterySource(fetch=lambda u: pages[u], ranking_urls=["p1", "p2"])
        by_device = {r.device: r for r in source.fetch_battery()}
        assert by_device["Redmi Note 13"].active_use_hours == 15.38  # first wins
        assert by_device["Poco M6"].active_use_hours == 16.0

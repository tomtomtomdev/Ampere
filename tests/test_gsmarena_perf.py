"""M6 — GSMArena performance scraper (SPEC Appendix C, gsmarena-device-data skill), test-first.

Pure parse against a saved-shape HTML fixture (no network, per invariant #2): the review
"benchmarks" sub-page renders each benchmark as a ``div.benchmark-widget`` whose tabs are separate
``div.phones`` containers *in tab order* — the gotcha the skill warns about (grabbing only the first
``.phones`` silently drops multi-core / v11 / etc.). We assert the parser reads *all* tabs, strips
the value to an int, and lifts chipset + memory; and that the per-chipset rollup takes the median
across devices sharing a SoC (SC7) using v10 (not v11) and Wild Life Extreme Highest.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ampere.adapters.scrapers.gsmarena_perf import (
    GsmArenaPerfSource,
    parse_review_html,
    rollup_chipsets,
    slugify,
)


def _row(name: str, chipset: str, memory: str, value: int, *, full: bool = False) -> str:
    bar = ' style="width: 100%;"' if full else ' style="width: 60%;"'
    return (
        '<div class="flex-row">'
        f'<img src="x.jpg"><span class="name">{name}</span>'
        '<div class="flex-column result">'
        f'<div class="bar"{bar}><span class="value">{value}</span></div>'
        '<div class="flex-row">'
        f'<span class="chipset">{chipset}</span><span class="memory">{memory}</span>'
        "</div></div></div>"
    )


def _widget(title: str, tabs: list[str], tab_rows: list[list[str]]) -> str:
    tab_lis = "".join(f"<li><span>{t}</span></li>" for t in tabs)
    phones = "".join(f'<div class="phones">{"".join(rows)}</div>' for rows in tab_rows)
    return (
        '<div class="benchmark-widget bar-chart">'
        f"<h3>{title}</h3>"
        f'<ul class="tabs">{tab_lis}</ul>'
        f"{phones}</div>"
    )


_SD = "Snapdragon 7 Gen 4"
_DIM = "Dimensity 7300"

# A DOM-accurate fixture: two chipsets, one shared by two phones (the <1% spread the skill cites),
# every widget carrying more tabs than we use (multi-core, v11, WLE-lowest, Solar Bay) so the
# "read every .phones" contract is under test.
REVIEW_HTML = "<html><body>" + "".join(
    [
        _widget(
            "GeekBench 6",
            ["Single-core", "Multi-core"],
            [
                [  # tab 0: single-core
                    _row("Phone A", _SD, "256GB, 8GB RAM", 1336, full=True),
                    _row("Phone B", _SD, "128GB, 8GB RAM", 1325),
                    _row("Phone C", _DIM, "256GB, 8GB RAM", 1050),
                ],
                [  # tab 1: multi-core
                    _row("Phone A", _SD, "256GB, 8GB RAM", 4132, full=True),
                    _row("Phone B", _SD, "128GB, 8GB RAM", 4100),
                    _row("Phone C", _DIM, "256GB, 8GB RAM", 3047),
                ],
            ],
        ),
        _widget(
            "AnTuTu",
            ["v10", "v11"],
            [
                [  # tab 0: v10 (the one we keep)
                    _row("Phone A", _SD, "256GB, 8GB RAM", 1129370, full=True),
                    _row("Phone C", _DIM, "256GB, 8GB RAM", 656811),
                ],
                [  # tab 1: v11 — MUST NOT leak into antutu
                    _row("Phone A", _SD, "256GB, 8GB RAM", 1400000, full=True),
                ],
            ],
        ),
        _widget(
            "3DMark",
            ["Wild Life Extreme (Highest)", "Wild Life Extreme (Lowest)", "Solar Bay"],
            [
                [  # tab 0: WLE highest (the one we keep)
                    _row("Phone A", _SD, "256GB, 8GB RAM", 2080, full=True),
                    _row("Phone C", _DIM, "256GB, 8GB RAM", 854),
                ],
                [_row("Phone A", _SD, "256GB, 8GB RAM", 1750, full=True)],  # WLE lowest — ignore
                [_row("Phone A", _SD, "256GB, 8GB RAM", 5000, full=True)],  # Solar Bay — ignore
            ],
        ),
    ]
) + "</body></html>"


class TestParseReviewHtml:
    def test_reads_every_tab_not_just_the_first(self):
        # The gotcha: a naive parser grabs only the first .phones (single-core) and drops the rest.
        rows = parse_review_html(REVIEW_HTML)
        tabs = {r.tab for r in rows}
        assert "gb6_single" in tabs and "gb6_multi" in tabs
        assert "antutu_v10" in tabs and "antutu_v11" in tabs
        assert "wildlife_extreme_high" in tabs

    def test_lifts_device_chipset_memory_and_int_value(self):
        rows = parse_review_html(REVIEW_HTML)
        a_single = next(
            r for r in rows if r.tab == "gb6_single" and r.device == "Phone A"
        )
        assert a_single.chipset == _SD
        assert a_single.memory == "256GB, 8GB RAM"
        assert a_single.score == 1336
        assert isinstance(a_single.score, int)

    def test_strips_thousands_separators(self):
        rows = parse_review_html(REVIEW_HTML)
        antutu = next(r for r in rows if r.tab == "antutu_v10" and r.device == "Phone A")
        assert antutu.score == 1129370

    def test_empty_html_yields_no_rows(self):
        assert parse_review_html("<html><body></body></html>") == []


class TestSlugify:
    def test_slug(self):
        assert slugify("Snapdragon 7 Gen 4") == "snapdragon-7-gen-4"
        assert slugify("Dimensity 8500 Extreme") == "dimensity-8500-extreme"


class TestRollupChipsets:
    def _by_id(self):
        rows = parse_review_html(REVIEW_HTML)
        chips = rollup_chipsets(rows, source="gsmarena_review:test", fetched_at=None)
        return {c.id: c for c in chips}

    def test_median_across_shared_soc(self):
        # SC7: one chipset row rolls up every phone that carries the SoC (median).
        sd = self._by_id()["snapdragon-7-gen-4"]
        assert sd.gb6_single == 1330.5  # median(1336, 1325)
        assert sd.gb6_multi == 4116  # median(4132, 4100)

    def test_uses_v10_not_v11_and_wle_highest(self):
        sd = self._by_id()["snapdragon-7-gen-4"]
        assert sd.antutu == 1129370  # v10, not the 1_400_000 v11 value
        assert sd.wildlife == 2080  # WLE highest, not lowest/solar

    def test_second_chipset_from_single_reading(self):
        dim = self._by_id()["dimensity-7300"]
        assert dim.gb6_single == 1050
        assert dim.gb6_multi == 3047
        assert dim.antutu == 656811
        assert dim.wildlife == 854

    def test_provenance_recorded(self):
        chips = rollup_chipsets(parse_review_html(REVIEW_HTML), source="gsmarena_review:test")
        assert all(c.source == "gsmarena_review:test" for c in chips)
        assert all(c.name for c in chips)


class TestGsmArenaPerfSource:
    def test_fetch_chipsets_over_injected_transport(self):
        # Transport seam: inject fetch(url)->html so all parsing is offline (invariant #2).
        calls: list[str] = []

        def fake_fetch(url: str) -> str:
            calls.append(url)
            return REVIEW_HTML

        clock = lambda: datetime(2026, 7, 14, tzinfo=UTC)  # noqa: E731
        source = GsmArenaPerfSource(
            fetch=fake_fetch, review_urls=["https://gsmarena.com/review-1.php"], clock=clock
        )
        chips = source.fetch_chipsets()

        assert calls == ["https://gsmarena.com/review-1.php"]
        by_id = {c.id: c for c in chips}
        assert by_id["snapdragon-7-gen-4"].gb6_single == 1330.5
        assert by_id["snapdragon-7-gen-4"].fetched_at == datetime(2026, 7, 14, tzinfo=UTC)

    def test_merges_rows_across_multiple_pages(self):
        pages = {
            "u1": _page_html([("Phone A", _SD, 1336), ("Phone B", _SD, 1325)]),
            "u2": _page_html([("Phone D", _SD, 1330)]),
        }
        source = GsmArenaPerfSource(fetch=lambda u: pages[u], review_urls=["u1", "u2"])
        sd = {c.id: c for c in source.fetch_chipsets()}["snapdragon-7-gen-4"]
        assert sd.gb6_single == 1330  # median(1336, 1325, 1330) across both pages


def _page_html(single_rows: list[tuple[str, str, int]]) -> str:
    """A minimal one-widget (GB6 single-core only) page for the multi-page merge test."""
    rows = [_row(name, chip, "256GB, 8GB RAM", val, full=(i == 0))
            for i, (name, chip, val) in enumerate(single_rows)]
    return "<html><body>" + _widget("GeekBench 6", ["Single-core"], [rows]) + "</body></html>"

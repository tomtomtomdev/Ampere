"""GSMArena performance scraper (SPEC Appendix C, ``gsmarena-device-data`` skill).

One review "benchmarks" sub-page (``…-review-XXXXpN.php``) yields GeekBench 6, AnTuTu and 3DMark
rows for ~16 comparison devices, each tagged with its **chipset** — so a handful of pages populate
the whole per-SoC benchmark table (§5.5, SC7). Like the battery source this is server-rendered HTML
with no API and no anti-bot; the fragile bit is only the HTTP fetch, which is injected as a
``fetch(url) -> html`` transport so every line of parsing/rollup is pure and unit-tested offline
against a saved-shape fixture (invariant #2). Benchmarks are read, never invented (invariant #4).

DOM gotcha (the one the skill flags): each benchmark widget renders every tab as its **own**
``div.phones`` container, in tab order — not a flat list. A parser that reads only the first
``.phones`` silently keeps just tab 0 (e.g. GB6 single-core) and drops the rest. We iterate all of
them; the Nth container is the Nth tab.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from ampere.adapters.sources._common import SourceFetchError, logger
from ampere.domain.catalog import chipset_id, chipset_vendor
from ampere.domain.catalog import slugify as slugify  # noqa: PLC0414 — re-export for callers/tests
from ampere.domain.models import Chipset

# Canonical metric key per (widget title, tab index) — see SPEC Appendix C tab→metric table.
TAB_CANON: dict[str, list[str]] = {
    "GeekBench 6": ["gb6_single", "gb6_multi"],
    "AnTuTu": ["antutu_v10", "antutu_v11"],  # keep v10; v11 runs higher — never mix (§5.1)
    "3DMark": ["wildlife_extreme_high", "wildlife_extreme_low", "solar_bay"],
}

# Which parsed tab feeds which Chipset benchmark field. Tabs not listed here (v11, WLE-lowest,
# Solar Bay) are parsed but deliberately excluded from the rollup so metrics never mix (§5.1).
_TAB_TO_FIELD: dict[str, str] = {
    "gb6_single": "gb6_single",
    "gb6_multi": "gb6_multi",
    "antutu_v10": "antutu",
    "wildlife_extreme_high": "wildlife",
}

@dataclass
class BenchRow:
    """One parsed benchmark reading (before per-chipset rollup)."""

    benchmark: str  # widget title, e.g. "GeekBench 6"
    tab: str  # canonical metric key, e.g. "gb6_single"
    device: str
    chipset: str
    memory: str
    score: int


def _soup(html: str):
    """Prefer lxml if installed (more lenient on real GSMArena markup); else stdlib html.parser."""
    from bs4 import BeautifulSoup

    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # lxml not installed → stdlib parser is fine for the shapes we handle
        return BeautifulSoup(html, "html.parser")


def parse_review_html(html: str) -> list[BenchRow]:
    """Parse a review benchmarks page into ``BenchRow``\\ s. Pure; skips malformed rows."""
    soup = _soup(html)
    out: list[BenchRow] = []

    for widget in soup.find_all("div", class_="benchmark-widget"):
        h3 = widget.find("h3")
        title = h3.get_text(strip=True) if h3 else ""
        canon = TAB_CANON.get(title)
        tab_labels = [t.get_text(strip=True) for t in widget.select("ul.tabs li")]

        # Each tab renders as its OWN div.phones, in tab order — iterate ALL of them (the gotcha).
        for tab_idx, phones in enumerate(widget.find_all("div", class_="phones")):
            if canon and 0 <= tab_idx < len(canon):
                tab_key = canon[tab_idx]
            elif 0 <= tab_idx < len(tab_labels):
                tab_key = tab_labels[tab_idx]
            else:
                tab_key = f"tab{tab_idx}"

            for val_el in phones.select("span.value"):
                result = val_el.find_parent("div", class_="result")
                row = result.find_parent("div", class_="flex-row") if result else None
                if not (result and row):
                    continue
                name_el = row.find("span", class_="name")
                digits = re.sub(r"[^\d]", "", val_el.get_text())
                if not (name_el and digits):
                    continue
                chip_el = result.find("span", class_="chipset")
                mem_el = result.find("span", class_="memory")
                out.append(
                    BenchRow(
                        benchmark=title,
                        tab=tab_key,
                        device=name_el.get_text(strip=True),
                        chipset=chip_el.get_text(strip=True) if chip_el else "",
                        memory=mem_el.get_text(strip=True) if mem_el else "",
                        score=int(digits),
                    )
                )
    return out


def rollup_chipsets(
    rows: list[BenchRow],
    *,
    source: str,
    fetched_at: datetime | None = None,
) -> list[Chipset]:
    """Collapse device-level rows to one ``Chipset`` per SoC, median-per-metric (SC7, §5.5).

    Benchmarks are a property of the chipset (a Dimensity 7300 scores the same in any phone), so
    multiple device readings for one SoC are rolled up by median — robust to the <1% spread the
    skill documents. Only the canonical metrics in ``_TAB_TO_FIELD`` contribute; v11 / WLE-lowest /
    Solar Bay are dropped so versions never mix (§5.1). Chipset-variant suffixes ("Extreme",
    "Ultra") stay distinct rows (different ``slugify`` → different id).
    """
    by_chip: dict[str, dict[str, list[int]]] = {}
    for r in rows:
        field = _TAB_TO_FIELD.get(r.tab)
        if field is None or not r.chipset:
            continue
        by_chip.setdefault(r.chipset, {}).setdefault(field, []).append(r.score)

    out: list[Chipset] = []
    for name in sorted(by_chip):
        metrics = by_chip[name]
        out.append(
            Chipset(
                id=chipset_id(name),
                name=name,
                vendor=chipset_vendor(name),
                gb6_single=_median(metrics.get("gb6_single")),
                gb6_multi=_median(metrics.get("gb6_multi")),
                antutu=_median(metrics.get("antutu")),
                wildlife=_median(metrics.get("wildlife")),
                source=source,
                fetched_at=fetched_at,
            )
        )
    return out


def _median(values: list[int] | None) -> float | None:
    return float(statistics.median(values)) if values else None


class _HttpxReviewFetcher:
    """Best-effort live transport (plain ``httpx`` GET of a review page). Not exercised in tests.

    GSMArena is polite-scrapeable (real UA, backoff, monthly cadence, cache hard); no anti-bot SDK,
    unlike Shopee. Swap in a Cloudflare-aware fetcher here if a challenge appears — the parser above
    does not change.
    """

    _UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    )

    def __init__(self, *, timeout: float = 20.0) -> None:
        self._timeout = timeout

    def __call__(self, url: str) -> str:
        import httpx  # lazy: only the live path needs it

        try:
            resp = httpx.get(url, headers={"User-Agent": self._UA}, timeout=self._timeout)
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as exc:
            raise SourceFetchError(str(exc)) from exc


class GsmArenaPerfSource:
    """A ``PerfCatalogSource``: scrape N review pages → one median row per chipset (Appendix C).

    ``fetch`` (``url -> html``) is injected so parsing/rollup are offline-testable; the default is a
    best-effort ``httpx`` fetcher. ``clock`` stamps ``fetched_at`` provenance and is injected for
    deterministic tests.
    """

    def __init__(
        self,
        *,
        review_urls: list[str],
        fetch: Callable[[str], str] | None = None,
        source_label: str = "gsmarena_review",
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._urls = review_urls
        self._fetch = fetch or _HttpxReviewFetcher()
        self._source_label = source_label
        self._clock = clock or (lambda: datetime.now(UTC))

    def fetch_chipsets(self) -> list[Chipset]:
        rows: list[BenchRow] = []
        for url in self._urls:
            rows.extend(parse_review_html(self._fetch(url)))
        chipsets = rollup_chipsets(rows, source=self._source_label, fetched_at=self._clock())
        logger.info(
            "gsmarena perf: %d pages -> %d rows -> %d chipsets",
            len(self._urls), len(rows), len(chipsets),
        )
        return chipsets

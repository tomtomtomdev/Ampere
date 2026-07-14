"""GSMArena battery scraper (SPEC Appendix B, ``gsmarena-device-data`` skill).

The battery ranking (``battery-test-v2.php3``) is a server-rendered HTML table of device → **Active
Use Score** (hours, higher = better; displayed like ``15:23h``). This is the *simple* source: plain
GET + parse, no API, no anti-bot/session (unlike Shopee). The HTTP fetch is injected as a
``fetch(url) -> html`` transport so parsing is pure and offline-tested (invariant #2); the default
is a best-effort ``httpx`` fetcher. Battery numbers are read, never invented (invariant #4).

Metric honesty (§5.1): every reading is tagged ``active_use_v2``; the legacy Endurance rating is a
different, non-comparable number and must never be silently mixed in.

Assumed markup: Appendix B's HAR stored no page body, so the exact ranking-table selectors are a
best guess, deliberately confined to ``parse_battery_html`` / ``parse_active_use`` — adjust those
two once a live page is captured (the same posture as ``AffiliateFeedSource.parse_offer``, M5).
"""

from __future__ import annotations

import re
from collections.abc import Callable

from ampere.adapters.sources._common import SourceFetchError, logger
from ampere.domain.models import BatteryMetricKind, BatteryReading

# "15:23h" → 15 h 23 min; also accept a bare "17h" / decimal "16.9".
_HH_MM_RE = re.compile(r"(\d+)\s*:\s*(\d+)")
_DECIMAL_RE = re.compile(r"(\d+(?:\.\d+)?)")


def parse_active_use(text: str) -> float | None:
    """Parse GSMArena's Active Use figure to decimal hours (``"15:23h"`` → ``15.38``), else None."""
    hh_mm = _HH_MM_RE.search(text)
    if hh_mm:
        hours, minutes = int(hh_mm.group(1)), int(hh_mm.group(2))
        return round(hours + minutes / 60, 2)
    decimal = _DECIMAL_RE.search(text)
    if decimal:
        return round(float(decimal.group(1)), 2)
    return None


def _soup(html: str):
    from bs4 import BeautifulSoup

    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def parse_battery_html(html: str) -> list[BatteryReading]:
    """Parse a battery-ranking page into ``BatteryReading``\\ s. Pure; skips unparseable rows."""
    soup = _soup(html)
    out: list[BatteryReading] = []
    for row in soup.select("tr.battery-row"):
        name_el = row.select_one(".name")
        value_el = row.select_one(".active-use")
        if not (name_el and value_el):
            continue
        hours = parse_active_use(value_el.get_text(strip=True))
        device = name_el.get_text(strip=True)
        if hours is None or not device:  # never store a fabricated 0 for a missing value (#4)
            continue
        out.append(
            BatteryReading(
                device=device,
                active_use_hours=hours,
                metric_kind=BatteryMetricKind.ACTIVE_USE_V2,
            )
        )
    return out


class _HttpxRankingFetcher:
    """Best-effort live transport (plain ``httpx`` GET). Not exercised in tests (no CI network)."""

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


class GsmArenaBatterySource:
    """A ``BatteryCatalogSource``: scrape the Active Use ranking page(s) → ``BatteryReading``\\ s.

    Pages are merged and deduped by device name (first occurrence wins — the ranking lists a
    device once; a later dup is defensive). ``fetch`` (``url -> html``) is injected for tests.
    """

    def __init__(
        self,
        *,
        ranking_urls: list[str],
        fetch: Callable[[str], str] | None = None,
    ) -> None:
        self._urls = ranking_urls
        self._fetch = fetch or _HttpxRankingFetcher()

    def fetch_battery(self) -> list[BatteryReading]:
        seen: dict[str, BatteryReading] = {}
        for url in self._urls:
            for reading in parse_battery_html(self._fetch(url)):
                seen.setdefault(reading.device, reading)  # first wins
        logger.info("gsmarena battery: %d pages -> %d devices", len(self._urls), len(seen))
        return list(seen.values())

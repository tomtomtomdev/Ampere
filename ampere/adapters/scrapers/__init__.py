"""Monthly, manual-assisted catalog scrapers (M6). GSMArena first — one review page maps
device->chipset AND supplies GB6/AnTuTu/Wild Life per chipset (``gsmarena_perf``); the battery
ranking supplies per-device Active Use hours (``gsmarena_battery``) — SPEC §6, Appendices B/C.

Each scraper is a ``*CatalogSource`` (``ampere.ports.catalog_source``) the ``refresh_catalog``
use-case consumes. Following the M5 source pattern, the fragile bit — the HTTP fetch — is injected
as a ``fetch(url) -> html`` transport so all parsing/rollup is pure and unit-tested offline against
saved-shape fixtures (invariant #2); the ``httpx`` fetchers are best-effort defaults, not tested.
Benchmarks/battery are read, never invented (invariant #4). ``beautifulsoup4`` is the parser dep
(optional ``scrape`` extra); lxml is used if present, else the stdlib ``html.parser``.

The original pure-parse core still lives in the ``gsmarena-device-data`` skill
(``.claude/skills/gsmarena-device-data/scripts/gsmarena_perf_parser.py``) as the source of record.
"""

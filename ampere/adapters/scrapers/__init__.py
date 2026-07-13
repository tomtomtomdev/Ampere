"""Monthly, manual-assisted catalog scrapers (M6). GSMArena first (device->chipset + battery),
then GB6/AnTuTu/Wild Life onto chipset rows (SPEC §6, Appendices B/C).

The shipped pure-parse core (``gsmarena_perf_parser.py``, fixture-testable) lives in the
``gsmarena-device-data`` skill (``.claude/skills/gsmarena-device-data/scripts/``). In M6, bring it
into this package with tests + a declared ``beautifulsoup4`` dep, and wire a thin fetcher around it.
"""

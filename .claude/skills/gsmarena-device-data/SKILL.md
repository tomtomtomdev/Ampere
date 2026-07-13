---
name: gsmarena-device-data
description: Extract phone benchmark and battery reference data from GSMArena — GeekBench 6 (single/multi), AnTuTu, 3DMark, the Active Use battery score, AND each device's chipset. Use whenever you need trustworthy per-device or per-chipset performance/battery numbers — building a phone catalog, scoring phones, looking up a SoC's benchmarks, or cross-referencing marketplace listings against real specs. Trigger this for GSMArena scraping, phone benchmark lookups, chipset-to-score mapping, battery-life reference data, or GSMArena HAR/HTML parsing — even if the user just says "get the benchmarks" or "how does phone X perform". GSMArena has no API; this covers the HTML structure and the parsing gotchas that make naive scrapers silently wrong.
---

# GSMArena Device Data — Battery & Performance

GSMArena is the practical single source for phone **battery** and **performance** reference data,
and it also maps each device to its **chipset** — which lets you key benchmarks on the SoC (a
Dimensity 7300 scores the same in any phone), cutting catalog maintenance dramatically. There is
**no API**: everything is server-rendered HTML. No anti-bot tokens, no login — a plain `GET` +
BeautifulSoup works. Be polite: real User-Agent, delay + backoff, cache hard, monthly cadence
(these numbers barely move). Occasional Cloudflare challenge, nothing more.

## Two page types

### 1. Battery — `battery-test-v2.php3`
Paginated ranking table of device → **Active Use Score** (hours, higher = better; shown like
`15:23h`). This is the v2 test. The **legacy "Endurance rating"** from the old test is a different
number and NOT comparable — store which test produced each value (`active_use_v2` vs
`endurance_legacy`) and normalize them separately. Per-device pages carry the detailed breakdown if
you want sub-scores.

### 2. Performance — review "benchmarks" sub-page (`…-review-XXXXpN.php`)
A single review's benchmarks page yields **GeekBench 6, AnTuTu, and 3DMark for ~16 comparison
devices at once**, each row tagged with its **chipset** and memory. Scraping ~20–30 review pages
covers essentially every chipset in a given price band, with overlap for cross-checking. This one
source populates an entire chipset benchmark table.

A ready-to-use parser for the performance page is bundled: **`scripts/gsmarena_perf_parser.py`**.
It's a pure function (`parse_review_html(html) -> list[BenchRow]`) — unit-test it against a saved
HTML/HAR fixture, then wire it to a thin fetcher. Run it directly on a HAR to emit a per-chipset
seed CSV. Read `references/dom_notes.md` before modifying it.

## The DOM structure (and the gotcha)

Each benchmark is a `<div class="benchmark-widget bar-chart">` with an `<h3>` title
(`GeekBench 6` | `AnTuTu` | `3DMark`) and an `<ul class="tabs">`. **The critical, easy-to-miss
fact: each tab renders as its OWN `<div class="phones">` container, in tab order** — not a flat
list, not `data-tab` attributes. A parser that grabs only the first `.phones` silently captures
just the first tab (e.g. GB6 single-core) and drops the rest (multi-core). Iterate over *all*
`.phones` children; the Nth one is the Nth tab. Each row inside carries `span.name`, `span.value`,
`span.chipset`, `span.memory`.

## Tab → metric mapping (and metric caveats)

| Widget | Tabs (in order) | Use |
|--------|-----------------|-----|
| GeekBench 6 | Single-core, Multi-core | both |
| AnTuTu | v10, v11 | pick ONE (default v10); v11 runs higher — never mix versions |
| 3DMark | Wild Life Extreme (Highest), Wild Life Extreme (Lowest), Solar Bay | Extreme (Highest) |

Two traps that make cross-device comparisons wrong:
- GSMArena reports **3DMark Wild Life EXTREME**, not standard Wild Life. Extreme is a harder test
  with much lower numbers (budget SoCs ~850–1000, flagships ~6000+). If you set reference bounds for
  standard Wild Life, every phone clusters at the bottom.
- AnTuTu appears as **v10 and v11**. Standardize on one; v11 scores are higher and not comparable
  to v10.

## Chipset keying works (empirically)

On one review page, Snapdragon 7 Gen 4 appeared in four different phones with GeekBench 6
single-core of 1336 / 1334 / 1333 / 1325 — under 1% spread. Benchmarks are a property of the SoC,
so key the catalog on chipset and roll up multiple device readings (median) per chipset. Keep
chipset-variant suffixes distinct: "Dimensity 8500 Extreme", "8500 Ultra", and plain "8500" are
different parts — do not collapse them.

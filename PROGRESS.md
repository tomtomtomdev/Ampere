# Ampere — PROGRESS

Living status. Update every session. Newest entry on top.

## Current state

**Phase:** M2 done — entity resolution implemented **test-first** and green (ruff clean + 69
tests: 4 smoke, scoring+frontier as before, 30 resolve). `domain/scoring.py`, `domain/frontier.py`
and `domain/resolve.py` are all live, pure, deterministic, zero I/O. `application/` (`run_daily`,
`refresh_catalog`) + all `adapters/repos` remain stubbed awaiting M3.
**Next action:** M3 (persistence + daily use-case — SQLite repos behind the `ports`, then wire
`run_daily`: FixtureSource → resolve → effective_price → **dedup cheapest-per-SKU** (§5.8) → score
→ persist → diff vs prior snapshot). Idempotent + transactional per `snapshot_date` (SC6). TDD
against `FixtureSource` + in-memory SQLite.
**Env:** Python venv at `.venv` (Python 3.14 available; target 3.12). `uv pip install -e ".[dev,web]"`.

## Milestone tracker

| ID | Milestone                         | Status  | Notes |
|----|-----------------------------------|---------|-------|
| M0 | Skeleton + framework docs         | ✅ done  | repo, schema, FixtureSource, stubs, design shell — green |
| M1 | Scoring core (pure)               | ✅ done  | normalize/perf/batt/cap/value + Pareto frontier; TDD, deterministic, ruff-clean |
| M2 | Entity resolution                 | ✅ done  | clean_title + resolve; 100% on 21-title golden set (≥85% SC2); alias override + needs-mapping |
| M3 | Persistence + daily use-case      | ☐ todo  | snapshot diffing; new arrivals/price drops |
| M4 | Web UI (5 menu screens)           | ☐ todo  | Pareto scatter; weight sliders live re-score |
| M5 | Real Shopee source                | ☐ todo  | affiliate feed preferred; internal best-effort |
| M6 | Catalog refresh + schedule + skill| ☐ todo  | monthly scrapers; cron→/run; id-android-market |

## Decisions log

- **M2 entity resolution done (2026-07-13):**
  - `clean_title` + `resolve` in `domain/resolve.py`, **test-first** from SPEC §7 (30 tests,
    `tests/test_resolve.py`). Pure/deterministic/zero-I/O; `DeviceCatalogPort`/`AliasCatalogPort`
    injected so the domain stays clean.
  - **New data module `ampere/domain/lexicon.py`** = runtime transcription of the
    `id-android-market` skill refs (brands/lexicon). The **skill stays the source of record**
    (CLAUDE.md); lexicon.py is the config.py-style *data* counterpart so resolve.py holds no
    hard-coded brand regexes. Grow rules in the skill first, reflect them here.
  - **Pipeline:** condition-**first** (precedence refurb>used>new; default `unknown` — never
    assume new, skill pitfall) → collapse multi-word brand phrases → strip spec phrases
    (`Snapdragon 4 Gen 2`/`Helio G99`/`108MP`/`5000mAh`/`99%`) so embedded digits don't leak →
    extract variant → classify remaining tokens (noise/trust/color/qualifier/brand) → model =
    identity residue.
  - **Variant:** RAM vs ROM by **magnitude not position** (`256/8`→`8/256`); `+`/`gb`/`ram..rom`
    forms normalized; qualifiers `5G`/`NFC` appended to the variant; bare ROM → partial `?/256`
    (never invent RAM — invariant #4).
  - **Matching:** `rapidfuzz.token_sort_ratio` (NOT token_set — token_set collapses a subset like
    `Note 13`→`Note 13 Pro` to 100; skill pitfall #4), over **dedup'd tokens** (neutralizes the
    brand-repeat artifact from `realme realme C67` / a query that re-prepends the brand). Brand
    narrows candidates, **widening to all on an empty bucket**. Threshold 85 (arg). Alias override
    short-circuits fuzzy (score 100). **Sub-brands** Redmi/POCO → brand `Xiaomi` but the token is
    kept in the model so the family still matches.
  - **`match_score`** = best candidate score (accepted match, or top near-miss for a UI hint),
    `None` if no candidates. `device_id=None` ⇒ needs-mapping queue.
  - **Golden set = the 23 design listings** (L01–L23, `design/Ampere.dc.html`): 21 matchable +
    2 deliberately unresolvable. **100% correct** on the 21 (clears the ≥85% SC2/DoD bar), both
    "HP Android …"/"Smartphone Android …" → `None`. Condition asserted from **title tokens only**
    (Mall→new is an M3 assumption, not the resolver's).
  - Removed the M0 smoke stub-guard for `resolve.*` (now implemented). Not committed (awaiting user).
- **M1 scoring core done (2026-07-13):**
  - Ported the scoring/frontier math from `design/Ampere.dc.html` **test-first** (not pasted):
    `domain/scoring.py` (`normalize`, `performance`, `battery`, `capability`, `value`) +
    `domain/frontier.py` (`pareto_frontier`). All pure, deterministic, zero I/O; bounds/weights
    read from `ampere.config` (no magic numbers → SC3/R4).
  - **`performance()` implements §5.4 re-weighting** the prototype skips: missing metrics drop out
    and the present metrics' weights renormalize to sum 1 (never fabricate — invariant #4). Zero
    metrics → `ValueError` (caller marks `unmatched`). `throttle_modifier` scales each normed
    value before the blend (§5.5).
  - **`battery()` is active_use_v2-only for now.** Legacy endurance has **no configured reference
    bound**; rather than invent one (invariant #4, "never mix silently" §5.1) it raises. Deferred
    to a deliberate bound later (see open question below).
  - **`value()` guards `effective_price <= 0`** (raises) instead of emitting inf/negative.
  - **Frontier tie semantics:** domination requires strictly-better on ≥1 axis, so identical
    (price, capability) points both stay on the frontier. Per-condition by default; `blended=True`
    unions all conditions (tested: a cheaper+better *used* phone does NOT drop a *new* one unless
    blended). Self-exclusion is by object identity (`o is not r`), robust to duplicate coords.
  - Repointed the M0 smoke stub-guard from scoring/frontier → `resolve.*` (the still-stubbed M2
    surface). Tests split into `test_scoring.py` / `test_frontier.py`. Not committed (awaiting user).
- **M0 scaffold + design applied (2026-07-12):**
  - Clean-Architecture package `ampere/` created (`domain`/`application`/`ports`/`adapters`/`web`)
    + `tests/`, `pyproject.toml` (ruff + pytest, hatchling), `.gitignore`, `README.md`. `git init`
    (branch `main`, **not committed** — awaiting user).
  - SQLite `schema.sql` from PLAN data model (benchmarks on `chipsets`; `runs.snapshot_date UNIQUE`
    for SC6). `db.connect()`/`create_schema()` idempotent. Fixed reference bounds + weights in
    `ampere/config.py`, `SCORING_VERSION="v2.1.0"`.
  - `FixtureSource` returns 9 canned in-band listings (subset of the design's 23, incl. 2 unmatched);
    conforms to `SearchSource` Protocol. Scoring/frontier/resolve are **stubs** (TDD is M1/M2).
  - `chipsets_seed.csv` → `data/seed/`. Premature copy of `gsmarena_perf_parser.py` **removed** from
    the package (undeclared bs4 dep + lint debt); it stays in the `gsmarena-device-data` skill and
    is brought into `adapters/scrapers/` with tests in M6.
  - **Skills installed** to `.claude/skills/` (id-android-market, shopee-marketplace,
    gsmarena-device-data) so they **auto-trigger**; `.skill` archives kept in `skills/`. CLAUDE.md
    updated to document them + the scaffold/workflow.
  - **Design applied:** `Design for spec.zip` → `design/`. Tokens ported to
    `ampere/web/static/styles.css`; app shell (sidebar/topbar/nav, no run button) in `index.html`.
    Five screens render from the API in M4. `design/SPEC.md` is an older snapshot — root `SPEC.md`
    is authoritative (see `design/NOTES.md`).
  - **Frontend lib decided:** the prototype hand-rolls the Pareto scatter as inline **SVG, no chart
    lib** — M4 follows that (zero build, matches the terminal aesthetic). Supersedes the Plotly/Chart
    open question. Stack = FastAPI + vanilla JS + hand-rolled SVG.
- Codename **Ampere**.
- Battery is a **co-equal pillar** (default W_BATT = 0.45), not a tiebreaker. — per user.
- Performance blend is **all-round**, even 0.25 weights across GB6-single/GB6-multi/AnTuTu/
  Wild Life. — per user.
- Primary UX is a **menu-driven local web UI** (FastAPI + static SPA), not a CLI. — per user.
- Reference bounds are **fixed + versioned**; no cohort normalization (avoids score drift).
- `SearchSource` interface with Affiliate / Internal / Fixture impls; affiliate feed preferred.
- **v2 (gap review):**
  - Benchmarks attach to **chipset**, not device; `throttle_modifier` per device. — per user (#1).
  - **GSMArena is the primary catalog source** (device→chipset + specs + battery). — per user (#1).
  - **Shopee Mall** added as first-class trust filter; detection **pending Shopee API tech docs**.
    Lightweight `condition` flag kept alongside (Mall ≠ full condition axis). — per user (#2).
  - **Effective price** (ongkir − voucher − cashback; ignore harga coret) on the value axis. — (#4).
  - **Seller trust** (rating/Mall/Star) = filter + column; optional soft value penalty (off default).
  - **Dedup to cheapest-per-SKU** before frontier. — per user (#5).
  - **Idempotent + transactional daily runs** per snapshot_date (SC6). — per user (#6).
  - **Software-update longevity** field added; **affiliate output** kept as biz/monetization path,
    scoring stays commission-independent. — per user (business gap).
  - Frontier computed **per condition class** by default (blended view is a toggle).
- **HAR-verified (2026-07-12), see SPEC Appendix A:**
  - Endpoint `GET /api/v4/search/search_items`; Mall + price band via `fe_filter_options`
    (`SHOP_TYPE=OFFICIAL_MALL`, `PRICE_RANGE=1000000▶◀2000000`); paging = `limit=60` + `newest` offset.
  - Prices are micro-units (÷100000). `tier_variations` gives RAM/ROM directly. Mall = `is_official_shop`.
  - Condition is NOT in the search payload → Mall filter is the "new" proxy; used inferred from title.
  - Shipping/voucher sparse in search → `effective_price` usually `partial` in v1.
  - Anti-bot signed headers expire → `InternalEndpointSource` should drive a real browser session
    (Playwright + persisted profile), not forge headers.
- **battery.har (2026-07-12), see SPEC Appendix B:** GSMArena battery = server-rendered HTML,
  **no JSON API** — plain GET + BeautifulSoup, no anti-bot/session. Ranking at
  `battery-test-v2.php3` (Active Use Score, hours, higher=better). This capture held only
  ad-tech traffic — no live Active Use values extracted; re-capture "with content" or scrape in M6.
  `GsmArenaBatterySource` is the low-risk counterpart to the fragile Shopee source.
- **performance.har (2026-07-12), see SPEC Appendix C:** GSMArena **review** pages carry GB6
  (single+multi), AnTuTu (v10+v11), 3DMark (**Wild Life Extreme**) AND device→chipset mapping —
  one source populates the whole chipset table. HTML, no API/anti-bot. Parser built
  (`gsmarena_perf_parser.py`): each tab = its own `div.phones`. One page → 95 rows / ~16 devices;
  seeded `chipsets_seed.csv` (13 SoCs). Chipset model validated (SD 7 Gen 4 ×4 phones, <1% spread).
  Corrected §5.1 bounds: Wild Life **Extreme** (not std), AnTuTu **v10**.
- **Seed data on disk:** `chipsets_seed.csv` (real GB6/AnTuTu-v10/WildLifeExtreme per chipset).
  `gsmarena_perf_parser.py` = reusable M6 scraper core (pure parse, fixture-testable).
- **Skills built + packaged + installed** (`.skill` archives in `skills/`; active copies auto-trigger
  from `.claude/skills/`):
  - `id-android-market` — entity resolution (brand/model aliases, RAM/ROM variant rules, ID noise
    tokens, condition lexicon). Unblocks M2. Analogue of `id-vehicle-market`.
  - `shopee-marketplace` — search_items contract, fe_filter_options (Mall + price ▶◀), micro-unit
    pricing, item_basic field map, anti-bot/browser-session reality. Backs Appendix A / M5.
  - `gsmarena-device-data` — battery (Active Use v2) + performance (GB6/AnTuTu/3DMark) HTML scraping,
    the per-tab `div.phones` gotcha, metric caveats, bundles `gsmarena_perf_parser.py`. Backs
    Appendices B/C / M6.
  - Not skilled (deliberately): scoring/frontier logic → lives in `domain/`, covered by existing
    value-investing skills.
- **Scheduling decided (per user):** daily fetch is **automatic, not a manual button**. OS
  scheduler on the `run_daily` entrypoint — launchd LaunchAgent on macOS (primary), cron on Linux
  — + launch-time catch-up if today's run is missing (safe via idempotency). Run-now button
  demoted to fallback. See SPEC §8a, SC8.

## Open questions

- [ ] **#3 residual:** chipset-sharing pushes most listings to `full`; is a per-metric imputation
      fallback wanted for the rare SoC with zero Wild Life data, or just mark `partial`? (default: mark partial)
- [ ] **Legacy battery bound (from M1):** `battery()` currently supports only Active-Use-v2;
      legacy-endurance-only devices raise (no configured bound, don't fabricate). Do we need a
      legacy `REFERENCE_BOUNDS` window (bumps `scoring_version`), or are all in-band devices v2 so
      legacy can stay unsupported? (default: stay v2-only until a real legacy device appears)
- [x] ~~Shopee Mall/condition detection~~ — **resolved from HAR** (Appendix A).
- [x] ~~Scheduler: cron vs APScheduler~~ — **decided:** OS scheduler (launchd/cron) + catch-up, automatic daily.
- [ ] `InternalEndpointSource`: Playwright-driven browser session (robust, recommended) vs
      affiliate-feed-only for v1? (default: build affiliate first, Playwright source in M5)
- [x] ~~Frontend lib: Plotly.js vs Chart.js~~ — **resolved:** design hand-rolls the scatter as inline
      SVG, **no chart lib**. M4 follows suit (FastAPI + vanilla JS + SVG).
- [ ] Scheduler: cron→/run (default) vs in-process APScheduler?
- [ ] Telegram daily push (Relay/Courier style) in M6, or defer to v2?
- [ ] Confirm affiliate access (Involve Asia / Accesstrade) for Shopee ID feed.
- [ ] Seed the initial `chipsets` + `devices` catalog — which ~30–50 models (and their SoCs) to prioritize?

## Reference-bound tuning notes

Starting bounds are in SPEC §5.1. After the first catalog load, sanity-check that real phones
in the band spread across ~30–90 on each normed metric (not all clustered at one end); adjust
REF_MIN/REF_MAX and bump `scoring_version` if so.

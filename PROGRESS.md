# Ampere — PROGRESS

Living status. Update every session. Newest entry on top.

## Current state

**Phase:** M5 done — real Shopee sources implemented **test-first** and green (ruff clean + 192
tests: +61 for M5 — 32 `test_internal_endpoint`, 21 `test_affiliate_feed`, 8 `test_source_contract`).
Two live `SearchSource` impls behind the port, each with the **live transport injected** as a
`fetch` callable so all parsing/pagination/filtering is unit-tested offline (no network in CI):
`InternalEndpointSource` (HAR-verified `search_items` — `fe_filter_options` Mall + price `▶◀` band,
micro-unit `÷100000`, `item_basic` field map, harga-coret dropped) and `AffiliateFeedSource` (ToS-
safe/preferred but narrower — clean price + affiliate `tracking_link`, no fabricated Mall/trust).
Shared `_common.py` gives caching (`InMemoryCache`/`JsonFileCache`), bounded `fetch_with_backoff`,
and one `SourceFetchError`. New `sources.build_source(kind)` registry is the composition-root
selector. **SC4 verified end-to-end** (scratch check): an `InternalEndpointSource` with a fake
transport drove the **unmodified** `run_daily` — payload → ÷100000 price → resolve → Mall→new →
`full` score → frontier — zero scoring/UI changes.
**Next action:** M6 (catalog refresh + scheduling + skill) — GSMArena-first monthly scrapers
(`gsmarena_perf_parser.py` is ready in the skill), seed the real `chipsets`/`devices` catalog,
`os/security_updates_years`, and the launchd/cron automatic daily scheduler + launch-time catch-up
(SC8). `run_daily.main()` is still the `NotImplementedError("M6: wire config + adapters")` stub —
M6 wires `build_source` + config + a `JsonFileCache` there. To point the web/daily job at a live
source today it's a one-liner: `source_factory=lambda: build_source("affiliate")` (default stays
`FixtureSource` so the demo runs offline).
**Env:** Python venv at `.venv` (Python 3.14 available; target 3.12). `uv pip install -e ".[dev,web]"`.
Run the UI: `.venv/bin/uvicorn ampere.web.api:app --reload` (seeds the demo DB on first start).

## Milestone tracker

| ID | Milestone                         | Status  | Notes |
|----|-----------------------------------|---------|-------|
| M0 | Skeleton + framework docs         | ✅ done  | repo, schema, FixtureSource, stubs, design shell — green |
| M1 | Scoring core (pure)               | ✅ done  | normalize/perf/batt/cap/value + Pareto frontier; TDD, deterministic, ruff-clean |
| M2 | Entity resolution                 | ✅ done  | clean_title + resolve; 100% on 21-title golden set (≥85% SC2); alias override + needs-mapping |
| M3 | Persistence + daily use-case      | ✅ done  | SQLite repos + UoW; run_daily pipeline; idempotent+transactional (SC6); snapshot diff |
| M4 | Web UI (5 menu screens)           | ✅ done  | FastAPI + vanilla-JS SPA; inline-SVG scatter; sliders re-score server-side; browser-verified |
| M5 | Real Shopee source                | ✅ done  | InternalEndpointSource (HAR contract) + AffiliateFeedSource behind injected transport; shared contract suite; SC4 verified |
| M6 | Catalog refresh + schedule + skill| ☐ todo  | monthly scrapers; cron→/run; id-android-market |

## Decisions log

- **M5 real Shopee sources done (2026-07-14):**
  - **Transport seam is the key decision.** The fragile/networked part of each source (Shopee's
    expiring anti-bot headers; affiliate auth) is injected as a `fetch(params)->dict` callable, so
    **all parsing/pagination/filtering/dedup/cache/backoff logic is pure and unit-tested offline**
    against saved-shape payloads — never touching Shopee (skill guidance, invariant #2). Live
    fetchers (`_HttpxPageFetcher`/`_HttpxFeedFetcher`) are best-effort defaults, **not exercised in
    tests** (no network in CI).
  - **`InternalEndpointSource`** (`kind="internal"`) = the HAR-verified `search_items` contract
    (SPEC Appendix A): `fe_filter_options` builds `SHOP_TYPE=OFFICIAL_MALL` (only when `mall_only`)
    + `PRICE_RANGE` with the literal `▶◀` delimiter in whole IDR; `newest` is an **offset** cursor
    (`limit=60`); pagination stops on `nomore` / `offset>=total_count` / empty / `max_pages` cap
    (one bounded burst). Pure `parse_item`: price `÷100000`, **`price_before_discount` never read**
    (harga coret, §5.7), `tier_variations` → normalized RAM/ROM across axis-name/format variants
    (color axes ignored), `is_official_shop|show_official_shop_label`→`is_mall`,
    `item_rating.rating_star`/`rating_count[0]`/`is_preferred_plus_seller`→trust, URL from
    `shopid`/`itemid`. Client-side band re-filter is **defensive** (variant price ranges can leak
    out of band). Dedup by `shopee_id` (first wins).
  - **`AffiliateFeedSource`** (`kind="affiliate"`) = the **preferred, ToS-safe** path (SPEC §6) and
    the monetization channel (`tracking_link` = outbound affiliate URL, §11.2). Deliberately
    **narrower**: whole-IDR price (NOT micro-units), prefers `sale_price` over list, brand — but
    **no Mall/trust** (left unset, never fabricated — invariant #4). `mall_only` is a documented
    no-op. **Schema is *assumed*** (`{data:{data:[...],current_page,last_page}}`) since affiliate
    access is still an open question; the whole mapping is isolated in `parse_offer` = the one place
    to adjust once a real feed is captured.
  - **Shared infra** (`adapters/sources/_common.py`): `Cache` Protocol + `InMemoryCache` (default)
    + `JsonFileCache` (on-disk "cache hard", SPEC §6); `fetch_with_backoff` (exp backoff on
    `SourceFetchError`, **injected `sleep`** so tests don't wait; non-`SourceFetchError` propagates
    as a bug); `logging` provenance (source_kind, band, pages, raw/in-band counts).
  - **`build_source(kind, **kw)` registry** in `sources/__init__.py` = the composition-root source
    selector (SPEC §8 "source selection", SC4). Web default stays `FixtureSource` (offline demo
    intact); swapping is one line. **`run_daily`/scoring/UI unchanged** — proven by the SC4 scratch
    check (internal source → run_daily end-to-end).
  - **No Playwright dependency added.** The robust internal transport (logged-in Playwright session
    per Appendix A) is a drop-in `fetch` impl later; adding the browser dep now is unjustified while
    the seam already isolates it. `httpx` (existing dep) backs the best-effort default, imported
    lazily inside the fetchers.
  - Not committed (awaiting user).
- **M4 Web UI done (2026-07-14):**
  - **Live re-score without divergence:** extracted the scoring+dedup+frontier pass out of
    `run_daily` into `application/snapshot.py:score_snapshot(listings, uow, weights, *, blended)`
    (returns `ScoredSnapshot`: `scores_by_id` / `sku_of` / `best_listings` / `rollups` /
    `frontier_ids`). **Both** `run_daily` (persist path) and the read models call it, so the
    dashboard at default weights reproduces exactly what was persisted (SC3, test-asserted).
    `run_daily` refactor is behavior-preserving — the 8 M3 tests stayed green untouched.
  - **Read models** (`application/views.py`): one `build_*` per screen returning pydantic DTOs.
    They **recompute** from the stored snapshot + catalog at the request's weights (the
    slider-re-score path) rather than reading persisted `Score` rows — deterministic + keeps the
    persisted rows as the audit record. A single `_load_ctx` computes the scored set + diff once per
    request; `_meta` builds the shared chrome (stats, nav badges). Unmatched listings never enter
    the scored tables — they surface only in the Catalog needs-mapping queue (invariant #4).
  - **Boundary decision — where the math stops:** the server returns domain numbers + frontier
    membership; the **browser JS only does pixel geometry, client-side filter/sort, and the tooltip**
    (no scoring in JS, unlike the `design/Ampere.dc.html` prototype which scored in-browser). Weight
    + "blend conditions" are server params (re-fetch → re-score); brand/cond/conf/mall-only/
    frontier-only/sort are pure client-side view filters (no round-trip). Frontier membership is
    computed over the full deduped in-band set, so client filters never change it.
  - **FastAPI wiring** (`web/api.py`): `create_app(uow_factory, source_factory=FixtureSource,
    clock=date.today, on_startup=None)` — composition root injects a **per-request UoW** (fresh
    SQLite conn, `check_same_thread=False`, closed in a `finally`) so it's thread-safe under the
    Starlette threadpool and fully testable with a temp DB. `Depends()` stays in the **default
    value** not an `Annotated` marker (with `from __future__ import annotations`, FastAPI evals
    annotations against module globals where the `get_uow` closure is invisible → 422); B008 is
    silenced via `ruff … flake8-bugbear.extend-immutable-calls=["fastapi.Depends"]`.
  - **Endpoints:** `GET /api/{dashboard,listings,catalog,changes,settings}` (read),
    `POST /api/run` (manual fallback — SPEC §8/§8a, daily fetch is automatic), `POST /api/catalog/map`
    (needs-mapping resolver → `aliases.remember(alias_key(title), device_id)`; added public
    `resolve.alias_key` so the alias is stored under the exact key `resolve` looks it up by).
    Demo bootstrap runs only on real startup via a lifespan hook (no import-time / test side effects).
  - **Frontend** is the `design/Ampere.dc.html` prototype ported to fetch-based vanilla JS + the
    ported design tokens in `styles.css`; hash-based deep-linking (`#listings` etc., refresh-safe).
    Stack confirmed: FastAPI + vanilla JS + hand-rolled inline SVG, **no chart lib, no build step**.
  - **`trust_score` stays deferred** (open question) — M4 shows seller rating/Mall/Star as
    filters + columns only, off `capability` (§5.6). No composition formula fabricated.
  - Not committed (awaiting user).
- **M3 persistence + daily use-case done (2026-07-13):**
  - **New pure-domain modules** (test-first, zero I/O): `domain/pricing.py` (`effective_price` §5.7
    + `price_confidence`), `domain/dedup.py` (`dedup_cheapest_per_sku` §5.8), `domain/diff.py`
    (`compute_diff` → `SnapshotDiff`). **New models:** `SkuRollup`, `PriceChange`, `SnapshotDiff`,
    `RunResult`.
  - **Ports grown:** `SkuRollupRepo`; `UnitOfWork` (`@runtime_checkable`, bundles the 6 repos +
    owns the transaction boundary); `ListingRepo.latest_snapshot_before` (diff baseline).
    `SqliteDeviceRepo`/`SqliteAliasRepo` also satisfy the resolver's `DeviceCatalogPort` /
    `AliasCatalogPort` structurally, so `run_daily` passes them straight to `resolve`.
  - **SQLite adapters** (`adapters/repos/sqlite_repos.py`): all 6 repos + `SqliteUnitOfWork`.
    Connection runs **autocommit** (`isolation_level=None`); single writes (catalog upserts,
    `runs.start`/`finish`) autocommit immediately, while the daily replace
    (`listings`+`scores`+`sku_rollup`+`runs.finish`) is made **atomic inside
    `SqliteUnitOfWork.transaction()`** (explicit `BEGIN`/`COMMIT`/`ROLLBACK`). **Repos never
    self-commit** → they compose cleanly inside that boundary.
  - **SC6 pattern:** `runs.start` writes the `running` marker (autocommitted, survives a later
    rollback) → data write in a tx → on failure the tx rolls back the partial snapshot and
    `runs.finish('failed')` is recorded outside the tx (observability survives). Verified by the
    forced-mid-run-failure test (patched `scores.replace_snapshot` raises after `listings` written).
  - **Persistence shape:** ALL resolved listings (matched + unmatched) go to `listings`;
    `sku_rollup` holds the cheapest-per-SKU collapse (`best_listing_id` + `duplicate_count`). Score
    **all matched+scoreable** listings; `is_frontier` set only on the best-per-SKU points on the
    Pareto frontier. Unmatched → stored, unscored, `device_id NULL` (needs-mapping queue, §5.4).
  - **SKU key = `(device_id, condition)`** (device_id ⇒ model+variant); the rollup's model/variant
    text is derived from the device. **Mall→new proxy** applied in `run_daily` (application), NOT
    the resolver (title-tokens-only stays pure): `condition UNKNOWN` + `is_mall` ⇒ `NEW` (Appendix A).
  - **`price_confidence`** = `full` only when all three cost components are present (>0), else
    `partial` — `partial` is the v1 norm (search payload is sparse, Appendix A). **`trust_score`
    deferred → `None`** (SPEC §5.6 gives no composition formula; don't fabricate weights — see open
    question). A matched device lacking chipset/benchmarks/battery is **unscoreable → excluded from
    the frontier** (no fabrication, invariant #4); won't occur with a seeded catalog.
  - **Diff** is over ALL listings keyed on `shopee_id`, compared on `effective_price`; baseline =
    `latest_snapshot_before(snapshot_date)` (strictly earlier) so a **same-date re-run diffs vs the
    prior day, not itself**.
  - **Test seed catalog is test-local + illustrative** (6 chipsets / 6 devices covering the 7
    matchable fixture listings). The real on-disk catalog seed is M6 (open question stands).
  - Not committed (awaiting user).
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

- [ ] **`trust_score` composition (from M3):** §5.6 folds rating / Mall / Star into a `trust_score`
      but gives no weights, so M3 leaves it `None` (stored raw fields suffice for filtering). Define
      a formula in M4/M5 when the UI/source need is concrete — filter + column, off `capability`
      (§5.6), no fabricated weights. (default: derive when M4 wires the Listings/Settings filters)
- [ ] **#3 residual:** chipset-sharing pushes most listings to `full`; is a per-metric imputation
      fallback wanted for the rare SoC with zero Wild Life data, or just mark `partial`? (default: mark partial)
- [ ] **Legacy battery bound (from M1):** `battery()` currently supports only Active-Use-v2;
      legacy-endurance-only devices raise (no configured bound, don't fabricate). Do we need a
      legacy `REFERENCE_BOUNDS` window (bumps `scoring_version`), or are all in-band devices v2 so
      legacy can stay unsupported? (default: stay v2-only until a real legacy device appears)
- [x] ~~Shopee Mall/condition detection~~ — **resolved from HAR** (Appendix A).
- [x] ~~Scheduler: cron vs APScheduler~~ — **decided:** OS scheduler (launchd/cron) + catch-up, automatic daily.
- [x] ~~`InternalEndpointSource`: Playwright vs affiliate-feed-only for v1~~ — **resolved (M5):**
      built BOTH behind an injected `fetch` transport seam. Playwright is a drop-in `fetch` impl
      (no browser dep added now); `httpx` best-effort default meanwhile. Affiliate remains preferred.
- [x] ~~Frontend lib: Plotly.js vs Chart.js~~ — **resolved:** design hand-rolls the scatter as inline
      SVG, **no chart lib**. M4 follows suit (FastAPI + vanilla JS + SVG).
- [ ] Scheduler: cron→/run (default) vs in-process APScheduler?
- [ ] Telegram daily push (Relay/Courier style) in M6, or defer to v2?
- [ ] Confirm affiliate access (Involve Asia / Accesstrade) for Shopee ID feed. **Now blocks
      validating `AffiliateFeedSource.parse_offer` against a real feed** — the schema is currently
      assumed; capture one page (like the Shopee/GSMArena HARs) to confirm field names before live use.
- [ ] Seed the initial `chipsets` + `devices` catalog — which ~30–50 models (and their SoCs) to prioritize?

## Reference-bound tuning notes

Starting bounds are in SPEC §5.1. After the first catalog load, sanity-check that real phones
in the band spread across ~30–90 on each normed metric (not all clustered at one end); adjust
REF_MIN/REF_MAX and bump `scoring_version` if so.

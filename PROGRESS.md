# Ampere — PROGRESS

Living status. Update every session. Newest entry on top.

## Current state

**Latest (2026-07-16):** M8/M9 **SPA share/report buttons** follow-up done — the Settings screen
now has a **SHARE** section: "Open report ↗" (opens `GET /api/report` in a new tab, always
available) + "Share now" (`POST /api/notify`, enabled only when a push channel is wired). A new
`notify_configured: bool` rides through `ViewParams`→`SettingsView` (a composition-root fact, like
`source_kind`) so the button honestly reflects config and never posts into the void. **Test-first**
(+2 `test_web` settings tests), ruff-clean, **310 tests**; end-to-end verified (default → button
disabled + notify reports off; wired → button enabled + push sends). Endpoints unchanged (existed
since M8/M9); only the JS/HTML/CSS + the `notify_configured` surface are new. Un-committed.

**Phase:** M9 (v2 backlog) done + **committed `b5f7494`** — **static shareable frontier report**
(SPEC §11.2), **test-first** and green (ruff clean; M9 added +13 — 12 `test_report`, 1 `test_web`). The
publishable sibling of the M8 push: a **self-contained HTML page** (inline CSS + an inline-SVG
capability-vs-price scatter, **no external assets**) of the best-value pick + the Pareto frontier,
carrying each listing's outbound/affiliate link. New `application/report.py` = a read model that
**reuses the M4 dashboard** (`build_dashboard`) — so the published numbers are exactly what the UI
shows / `run_daily` persisted (SC3, no third math site) — plus a **pure `render_report`** (DTO →
HTML string; escapes all dynamic text) and a pure `_scatter_svg` (one `<circle>` per point, frontier
filled / dominated greyed; the legend lives in HTML so the circle count == point count; `_scale`
guards a zero-width range). `ReportView` reuses `views.Meta`/`Point`/`FrontierRow` + a
`url_by_id` outbound-link map (URLs never touch scoring, §11.2). **Off by default:** `run_daily.
main()` writes the page to `AMPERE_REPORT_PATH` after a run via `_write_report` (the only I/O is the
file write in the composition root — `render_report` is pure, so the app layer stays adapter-free;
**failure-isolated** like the push). Web: `GET /api/report` serves the same page live (`HTMLResponse`).
No schema change, no new deps. **End-to-end verified (scratch):** demo snapshot → a 5.2 KB valid HTML
doc (7 points / 7 `<circle>`s / 4-row frontier / 0 external assets); `ampere-run-daily
AMPERE_REPORT_PATH=…` on the pre-refresh real seed writes a valid page with an empty frontier (frontier
0) and exits 0.
**Prior:** M8 done — daily push notification (§11.2): `Notifier` port +
`application/notify.py` digest read model (pure `render_digest`) + Telegram/stdout adapters behind
`build_notifier`, wired into `main()` + `POST /api/notify`, off by default + failure-isolated,
injected transport (committed `c455215`). M7 done — trust composition (§5.6) + longevity bonus (§11.1)
behind off-by-default toggles, `SCORING_VERSION` v2.1.0 unchanged (SC3). M6 done — GSMArena scrapers +
`refresh_catalog` + real seed + `main()`/`catch_up` (SC8) + launchd/cron. (Full detail in the
decisions log.)
**Next action:** commit the SPA share/report buttons follow-up. The remaining v2 backlog is gated on
**external access** (not buildable offline): (1) a real Telegram bot token + chat id to confirm
`TelegramNotifier` posts (payload asserted, no live call yet); (2) capture a real affiliate feed to
confirm `AffiliateFeedSource.parse_offer`, then the first **live** GSMArena `refresh_catalog` (fills
the ID-band SoC benchmarks → the push + report start carrying a real frontier). Offline follow-ups if
wanted: expand `devices_seed.csv` + resolve the open #3 imputation question. Un-automated UI steps to
click-through in a browser: the two M7 Settings toggles, and the new SHARE buttons ("Open report" is
wired to a real page; "Share now" needs a channel configured to light up).
**Env:** Python venv at `.venv` (Python 3.14 available; target 3.12).
`uv pip install --python .venv -e ".[dev,web]"` (the `dev` extra self-references `ampere[scrape]` =
`beautifulsoup4`; lxml optional, stdlib `html.parser` fallback). Headless run:
`AMPERE_SOURCE=fixture .venv/bin/ampere-run-daily`. Daily push (off by default): add
`AMPERE_NOTIFY=telegram AMPERE_TELEGRAM_TOKEN=… AMPERE_TELEGRAM_CHAT_ID=…` (or `AMPERE_NOTIFY=stdout`
to dry-run). Shareable report (off by default): add `AMPERE_REPORT_PATH=…/frontier.html` (or hit
`GET /api/report`). Web UI: `.venv/bin/uvicorn ampere.web.api:app --reload` (seeds the demo DB on
first start, then catches up).

## Milestone tracker

| ID | Milestone                         | Status  | Notes |
|----|-----------------------------------|---------|-------|
| M0 | Skeleton + framework docs         | ✅ done  | repo, schema, FixtureSource, stubs, design shell — green |
| M1 | Scoring core (pure)               | ✅ done  | normalize/perf/batt/cap/value + Pareto frontier; TDD, deterministic, ruff-clean |
| M2 | Entity resolution                 | ✅ done  | clean_title + resolve; 100% on 21-title golden set (≥85% SC2); alias override + needs-mapping |
| M3 | Persistence + daily use-case      | ✅ done  | SQLite repos + UoW; run_daily pipeline; idempotent+transactional (SC6); snapshot diff |
| M4 | Web UI (5 menu screens)           | ✅ done  | FastAPI + vanilla-JS SPA; inline-SVG scatter; sliders re-score server-side; browser-verified |
| M5 | Real Shopee source                | ✅ done  | InternalEndpointSource (HAR contract) + AffiliateFeedSource behind injected transport; shared contract suite; SC4 verified |
| M6 | Catalog refresh + schedule + skill| ✅ done  | GSMArena perf+battery scrapers (injected transport) + refresh_catalog + real seed loader + `main()`/catch-up (SC8) + launchd/cron assets; skill was M2 |
| M7 | Trust composition + longevity bonus| ✅ done  | v2 backlog: `trust_score`/`trust_value_factor` (§5.6) + `longevity_bonus` (§11.1), pure + wired behind off-by-default per-request toggles; persisted scores/version unchanged (SC3); TDD |
| M8 | Daily push notification            | ✅ done  | v2 backlog: `Notifier` port + `application/notify.py` (digest read model, pure `render_digest`) + Telegram/stdout adapters behind `build_notifier`; wired into `main()` + `POST /api/notify`, off by default, failure-isolated; injected-transport seam; TDD (§11.2) |
| M9 | Static shareable report            | ✅ done  | v2 backlog: `application/report.py` reuses `build_dashboard`; pure `render_report` → self-contained HTML (inline CSS + inline-SVG scatter, no external assets) + outbound links; wired into `main()` (`AMPERE_REPORT_PATH`) + `GET /api/report`, off by default, failure-isolated; TDD (§11.2) |

## Decisions log

- **SPA share/report buttons done (2026-07-16):**
  - **Closes the M8/M9 UI gap.** The `POST /api/notify` (M8) and `GET /api/report` (M9) endpoints
    existed but had no SPA affordance ("the JS was left untouched"). Added a **SHARE** section to the
    Settings screen — the same "manual counterpart to the automatic daily" family as the existing
    "Run now" button, so it lives next to it. "Open report ↗" `window.open`s the report; "Share now"
    POSTs the digest and reflects the response (`sent:true` → "✓ pushed", `sent:false` → "nothing to
    send — empty frontier").
  - **`notify_configured` is a composition-root fact, surfaced like `source_kind`.** Added
    `notify_configured: bool` to `ViewParams`→`SettingsView`; the `/api/settings` endpoint sets it
    from `notifier_factory is not None`. The button is `disabled` when no channel is wired, so it
    can't post into the void (matches M8's off-by-default posture — the endpoint still reports
    cleanly rather than 500ing). This is the one **TDD-able** surface of an otherwise pure-JS change
    (2 new `test_web` settings tests, red→green); the JS itself is `node --check`ed + driven
    end-to-end (default → disabled/off; wired → enabled + 1 message sent).
  - **No new endpoints, no schema change, no new deps.** Only `notify_configured` + the SPA
    JS/HTML/CSS are new. `render_report` stays pure; the report opens even with an empty frontier.
    Un-committed.
- **M9 static shareable report done (2026-07-15):**
  - **The other half of §11.2.** M8 built the push *channel*; M9 builds the shareable *artifact* —
    "keep the frontier/report shareable (a static public page later)". A `GET /api/report` serves it
    live and `AMPERE_REPORT_PATH` writes it to disk after each run, so it can be hosted anywhere
    (static host / synced folder). Chosen as M9 because it was the strongest *offline-buildable*
    milestone left (the remaining backlog — real Telegram post, real affiliate feed, live GSMArena
    refresh — all need external access).
  - **Reuse over a third math site.** `build_report` calls **`build_dashboard`** rather than
    re-deriving points/frontier/chip-names, so the report, the dashboard, and the persisted snapshot
    can't diverge (SC3). It adds only a `url_by_id` outbound-link map (from the listings) on top.
    (Contrast M8's `notify.py`, which reimplemented a small frontier ranking; the dashboard already
    gives ranked `top_frontier` + all `points` for the scatter, so reuse was the clean call here.)
  - **`render_report` is pure + self-contained.** DTO → one HTML document, inline `<style>`, an
    inline-SVG scatter, **zero external assets** (asserted: no `<link>`/`<script src>`/stylesheet) so
    the file publishes as-is under a strict host. All dynamic text is `html.escape`d (an XSS test
    pins it — a hostile listing title can't inject markup into a published page). URLs ride through
    as `rel="nofollow noopener"` anchors; scoring never reads them (§11.2).
  - **Scatter invariant:** exactly one `<circle>` per point (frontier filled, dominated greyed); the
    legend swatches are HTML spans, not SVG circles, so `count("<circle") == len(points)` holds (the
    test pins it). `_scale` centres a zero-width range instead of dividing by zero (degenerate
    single-point / all-same-price snapshots).
  - **Off by default + failure-isolated**, same posture as M8: `main()._write_report` writes only
    when `AMPERE_REPORT_PATH` is set, and a write error is logged + swallowed so it never fails an
    already-persisted run. The only I/O is the file write in the composition root — `render_report`
    is pure, so the application layer stays adapter-free (invariant #1). Nothing special is needed for
    an empty frontier: the page renders a "no frontier yet" table + a scatter with 0 circles.
  - **No schema change, no new deps.** `NOTIFY_FRONTIER_LIMIT` unchanged (the report lists the full
    frontier, not a top-N). Not committed (awaiting user).
- **M8 daily push notification done (2026-07-15):**
  - **Off-by-default is again the load-bearing invariant** (like M7's toggles). No push happens
    unless the *composition root* wires a channel from env (`AMPERE_NOTIFY`); the use-case never
    builds a notifier. So a bare `ampere-run-daily` / a plain `uvicorn` behaves exactly as before —
    the push is purely additive.
  - **Same injected-transport seam as M5/M6.** The fragile part (the Telegram Bot API POST) is an
    injected `transport` on `TelegramNotifier`; the pure part (URL + payload construction) is
    asserted offline, and the live httpx path is best-effort/untested (no network in CI). The
    content selection (`build_push_digest`) and rendering (`render_digest`) are 100% pure/offline.
  - **`notify.py` is a read model for the push channel, not new scoring** — the sibling of
    `views.py`. It calls the **same `score_snapshot` at default weights / toggles off**, so the
    pushed frontier is byte-for-byte what `run_daily` persisted and the dashboard shows (SC3, no
    second math site — the divergence guard we used for weights/longevity/trust). No `scoring_version`
    change; no schema change.
  - **Layering (invariant #1 held):** `ports/notifier.py` (Protocol: `kind` + `send(text)`) ←
    `application/notify.py` (pure, imports only ports/domain/config) ← adapters
    (`Telegram`/`Stdout` + `build_notifier`). The notifier is constructed only in the composition
    roots — `run_daily.main()._push_daily_digest` (local adapter import, like `build_source`) and
    `web.create_app(notifier_factory=…)`. The application layer imports **zero** adapters.
  - **Failure isolation:** `notify_daily` lets a `send` error propagate (clean, testable contract);
    `main()` wraps it in try/except + logs, so a push outage never fails an already-persisted run.
    `notify_daily` sends **nothing** (returns `None`) when there is no snapshot or the frontier is
    empty — so a pre-refresh real seed (frontier 0) or a dead day doesn't spam an empty push.
  - **Render is plain text on purpose** — no Markdown, so no channel-specific escaping (Telegram
    MarkdownV2) can corrupt affiliate URLs; Telegram auto-links bare URLs anyway, and
    `disable_web_page_preview=True` stops N link unfurls per push.
  - **`POST /api/notify`** is the manual counterpart to the scheduled push (mirrors `POST /api/run`
    vs the automatic daily fetch, §8/§8a); off by default (no `notifier_factory` → reports "not
    configured"). No SPA button yet — the JS was left untouched in M8 (a "share now" button is a
    small follow-up).
  - **New config:** `NOTIFY_FRONTIER_LIMIT = 5` (how many frontier points a push lists). No
    bool flag needed — "configured" *is* the on-switch. **No new deps.** Not committed (awaiting user).
- **M7 trust composition + longevity bonus done (2026-07-15):**
  - **Off-by-default is the load-bearing invariant.** Both effects ship as per-request toggles that
    default to the config flags (`LONGEVITY_BONUS_ENABLED`/`TRUST_PENALTY_ENABLED`, both `False`).
    `score_listing`/`score_snapshot` gained `longevity_enabled`/`trust_penalty_enabled` kwargs with
    those defaults, so `run_daily` (which passes neither) persists byte-identical scores and
    `SCORING_VERSION` stays **v2.1.0** — SC3 holds without a version bump. Asserted by
    `test_snapshot.py::TestDefaultsUnchanged` (defaults == explicit both-off).
  - **Longevity → capability, trust penalty → value.** Per §11.1 the longevity bonus is *added to*
    `capability` (so it also moves the value axis and the frontier — the frontier's y-axis is
    capability); per §5.6 the trust penalty *multiplies* `value` only (never capability). Both live
    in the one place capability/value are computed (`score_listing`), reached from the read models
    via the same `score_snapshot` — so the slider-re-score path applies them without a second math
    site (no divergence, like weights).
  - **`longevity_bonus`** (`domain/longevity.py`): `LONGEVITY_BONUS_MAX` (5.0) × `normalize(years,
    0..LONGEVITY_OS_YEARS_BOUND)/100`; `None`→0.0 (never fabricated — invariant #4), clamped above
    the window (a 7-yr pledge doesn't out-score the 5-yr top). Reuses `scoring.normalize`.
  - **`trust_score`/`trust_value_factor`** (`domain/trust.py`): 0–100 composite over rating (norm
    4.0–5.0) / log10(reviews+1) (0–4) / Mall / Star, **re-weighted over affirmatively-present
    signals** (a missing rating or non-Mall/non-Star is *dropped*, not scored 0 — invariant #4);
    `None` only when there is no signal at all; Mall alone reads as trustworthy. `trust_value_factor`
    = `TRUST_PENALTY_FACTOR` (0.85) only when `!is_mall AND rating known AND < 4.5` (a missing rating
    never invents risk), else 1.0. Weights/bounds are versioned data in `ampere.config`.
  - **`trust_score` is a seller property, not a score.** Computed **once** in `run_daily._build_listing`
    (weight-independent) and persisted — the `listings.trust_score` column + repo round-trip already
    existed (added in M3, left `None`); this just fills it. Surfaced as `ListingRow.trust_score`; the
    read models don't recompute it. (Resolves the M3 "trust_score composition" open question.)
  - **Web:** `ViewParams` + `?longevity=`/`?trust_penalty=` query params (default = config) on the
    four re-scoring endpoints; `build_settings` now reports the **per-request** flags (was the raw
    config const). Frontend: `state.longevity`/`state.trust_penalty` + `serverParams()` carry them
    to every screen; the two Settings toggles became interactive (id + onchange → `load("settings")`),
    mirroring the dashboard `blended` toggle. FastAPI/Pydantic coerces `?longevity=true|false` (the
    exact `URLSearchParams` shape) — covered by the TestClient tests.
  - **Not formally in PLAN** (PLAN stops at M6); this is the top v2-backlog item. No new deps, no
    schema change, ruff-clean. Committed 2026-07-15.
- **M6 catalog refresh + scheduling done (2026-07-14):**
  - **Same transport seam as M5, applied to scrapers.** Each GSMArena scraper injects a
    `fetch(url)->html` callable, so `parse_review_html`/`rollup_chipsets` and
    `parse_battery_html`/`parse_active_use` are pure + unit-tested offline against DOM-accurate
    fixtures (invariant #2). The `_Httpx*Fetcher` defaults are best-effort and **not exercised in
    tests** (no CI network). GSMArena is the low-risk counterpart to Shopee — no anti-bot/session.
  - **`gsmarena_perf`:** ported the skill's `gsmarena_perf_parser.py` into the package and **cleaned
    it** — the stale "flat concatenated" docstring/`_bar_is_full` (unused) removed; the code already
    iterated one `div.phones` **per tab** (the documented gotcha) and now says so. Added
    `rollup_chipsets` = median-per-metric per SoC, keeping only canonical tabs (**v10**, **WildLife
    Extreme Highest**) so versions never mix (§5.1). Chipset id = `slugify(name)`; variant suffixes
    ("Extreme"/"Ultra") stay distinct rows.
  - **`gsmarena_battery`:** Active Use `HH:MMh` → decimal hours; unparseable rows dropped (never a
    fabricated 0 — invariant #4); tagged `active_use_v2` so legacy Endurance is never mixed. The
    ranking-table markup is **assumed** (Appendix B's HAR had no page body) and confined to
    `parse_battery_html`/`parse_active_use` — the one place to adjust once a live page is captured
    (same posture as M5's `AffiliateFeedSource.parse_offer`).
  - **New pure-domain module `domain/catalog.py`** (`chipset_id`/`chipset_vendor`/`device_id`,
    `slugify`) so the scraper adapters AND the application seed loader derive ids identically
    **without the application importing an adapter** (invariant #1). `gsmarena_perf` re-exports
    `slugify` for its existing callers.
  - **New ports `catalog_source.py`** (`PerfCatalogSource`/`BatteryCatalogSource`) → the
    `refresh_catalog` use-case depends on Protocols, not scrapers. Benchmarks attach to the
    **chipset** (one row covers every phone with that SoC — SC7); battery attaches per **model**
    (cell/display/tuning don't change across RAM/ROM variants, so one reading fills all variant
    rows). An unmatched battery reading is **surfaced** in the result, not guessed onto a device.
    A battery refresh must **not** touch `os/security_updates_years`/`update_source` (§11.1 is
    separate provenance) — asserted.
  - **Real catalog seed (`catalog_seed.py` + `devices_seed.csv`).** `chipsets_seed.csv` (the one
    real scraped artifact, 13 high-band SoCs) loads as-is; `devices_seed.csv` = 10 confident ID
    1–2jt phones with **factual** device→chipset mappings + brand-tier update-longevity (flagged
    pledge/estimate in `update_source`). **No fabricated benchmark/battery numbers**: the device-band
    SoCs get "pending refresh" chipset stubs (name+vendor only) — those listings are matched but
    unscoreable until the first `refresh_catalog` fills the numbers (exactly the SPEC build order).
    So a fresh headless run today = 9 listings / 7 matched / **frontier 0**; after a refresh filling
    those SoCs, the same run scores 6 / frontier 3 (verified). `demo_seed` (illustrative, for the
    offline UI) is unchanged and separate.
  - **`main()` wired + `catch_up()` (SC8).** `RunConfig.from_env` reads `AMPERE_SOURCE`/`_KEYWORD`/
    `_PRICE_MIN`/`_MAX`/`_MALL_ONLY`/`_DB`/`_CACHE_DIR` (default source `fixture` = safe/offline).
    `main()` is the composition root — adapter imports are **local** so the module's use-case logic
    stays adapter-free (invariant #1); it seeds the real catalog on first run, builds the source
    (with a `JsonFileCache` for live kinds), and calls the **guarded** `catch_up` (skip if today
    already `ok` — never zero, never a duplicate, never a redundant Shopee hit). A failed run stays
    transactional (SC6) and exits non-zero. Web startup also calls `catch_up` (three catch-up paths;
    the guard makes them idempotent).
  - **Scheduling assets shipped in `deploy/`** (not a code dep): launchd plist (`StartCalendarInterval`
    06:00 + `RunAtLoad` catch-up) + cron (`0 6 * * *` + `@reboot`) + install README. A `plistlib`
    test asserts the schedule + entrypoint so a broken plist fails CI.
  - **The `id-android-market` skill was already built/installed in M2** — PLAN's "package the skill"
    M6 item was satisfied early; nothing new needed here.
  - **Deps:** added a `scrape` extra (`beautifulsoup4`); `dev` self-references `ampere[scrape]` so
    tests get it. No lxml hard dep (parser prefers lxml if present, falls back to `html.parser`). No
    Playwright (the robust Shopee transport is still a drop-in `fetch`, per M5).
  - Not committed (awaiting user).
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

- [x] ~~**`trust_score` composition (from M3):**~~ **resolved (M7):** `domain/trust.py:trust_score`
      = 0–100 composite over rating/log10(reviews)/Mall/Star, re-weighted over present signals only
      (no fabricated 0s), `None` when no signal; a column + filter, **off `capability`** (§5.6).
      Computed once in `_build_listing`, persisted. Optional soft `value` penalty
      (`trust_value_factor`) ships behind the off-by-default `trust_penalty` toggle.
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
- [x] ~~Scheduler: cron→/run vs in-process APScheduler~~ — **resolved (M6):** neither — a headless
      `ampere-run-daily` entrypoint driven by an **OS scheduler** (launchd plist + cron shipped in
      `deploy/`), plus a guarded `catch_up()` on web startup / RunAtLoad / @reboot. Survives restarts,
      no web server required, one code path with the UI's Run-now.
- [x] ~~Telegram daily push (Relay/Courier style)~~ — **done (M8):** `Notifier` port +
      `application/notify.py` digest read model + `Telegram`/`Stdout` adapters behind
      `build_notifier`, wired into `main()` + `POST /api/notify`, **off by default**, injected
      transport, TDD (§11.2). Remaining is **live-only**: a real bot token + chat id to confirm
      `TelegramNotifier` posts (payload asserted, no live call yet — same posture as the httpx
      fetchers). The affiliate `tracking_link` rides inline in the push (already shareable).
- [ ] Confirm affiliate access (Involve Asia / Accesstrade) for Shopee ID feed. **Still blocks
      validating `AffiliateFeedSource.parse_offer` against a real feed** — the schema is assumed;
      capture one page (like the Shopee/GSMArena HARs) to confirm field names before live use.
- [~] **Seed the real `chipsets` + `devices` catalog** — **partially done (M6):** `devices_seed.csv`
      has 10 confident ID 1–2jt phones (factual device→chipset + brand-tier update years);
      `chipsets_seed.csv` has 13 real GSMArena SoC benchmark rows. Remaining: run the first **live**
      `refresh_catalog` (needs GSMArena network) to fill the ID-band SoC benchmarks + battery, and
      expand `devices_seed.csv` toward ~30–50 as review pages are scraped. Which further models to
      prioritize is still open. (default: grow it from the keyword's actual daily needs-mapping queue)

## Reference-bound tuning notes

Starting bounds are in SPEC §5.1. After the first catalog load, sanity-check that real phones
in the band spread across ~30–90 on each normed metric (not all clustered at one end); adjust
REF_MIN/REF_MAX and bump `scoring_version` if so.

# Ampere — PLAN

Spec-driven TDD, vertical slices, Clean Architecture. Each milestone is shippable and testable
end-to-end. Cold-session resumability is a non-negotiable invariant.

---

## Stack

- **Core:** Python 3.12, `httpx`, `pydantic` (models), `SQLite` (via `sqlite3`/`aiosqlite`),
  `rapidfuzz` (matching), `pytest` (+ `pytest-asyncio`), `ruff`.
- **UI:** `FastAPI` backend serving a small single-page frontend. Frontend = vanilla JS +
  a chart lib for the Pareto scatter (Plotly.js or Chart.js scatter — no build step).
  Swap to React later if the UI grows; the API contract stays the same.
  > This matches "menu-driven UI, not CLI". A scheduled runner (APScheduler or cron hitting a
  > `/run` endpoint) drives the daily job; the UI has a manual **Run now** button too.

## Architecture (Clean, dependency rule points inward)

```
domain/        pure logic, no I/O
  models.py        Listing, Device, Chipset, Variant, Benchmark, Battery, Score, Frontier
  scoring.py       normalize(), performance() [chipset+throttle], battery(), capability(), value()
  frontier.py      pareto_frontier(candidates) -> set   [per-condition by default]
  resolve.py       title-clean + match interfaces (pure), given an alias/catalog port

application/    use-cases orchestrating domain + ports
  run_daily.py     fetch -> resolve -> score -> diff -> persist
  refresh_catalog.py

ports/          interfaces (Protocols)
  search_source.py     SearchSource: search(keyword, price_min, price_max) -> [RawListing]
  benchmark_repo.py / device_repo.py / listing_repo.py / score_repo.py

adapters/       concrete I/O
  sources/  affiliate_feed.py  internal_endpoint.py  fixture_source.py
  repos/    sqlite_*.py
  scrapers/ geekbench.py antutu.py threedmark.py gsmarena.py   (monthly, manual-assisted)

web/            FastAPI app + static frontend
  api.py        /dashboard /listings /catalog /changes /settings /run
  static/       index.html, app.js, styles.css
```

## Data model (SQLite)

```
chipsets(id, name, vendor, gb6_single, gb6_multi, antutu, wildlife, source, fetched_at)
devices(id, brand, model, variant, chipset_id, throttle_modifier DEFAULT 1.0,
        active_use_hours, legacy_endurance, battery_metric_kind,
        os_updates_years, security_updates_years, update_source,
        scoring_notes, created_at)
aliases(raw_pattern, device_id)                         -- learned resolutions
listings(id, snapshot_date, shopee_id, title, list_price, effective_price, price_confidence,
         shipping_est, voucher_est, cashback_est,
         condition, is_mall, seller_rating, seller_review_count, is_star_seller, trust_score,
         seller, url, device_id NULL, confidence)
sku_rollup(snapshot_date, model, variant, condition, best_listing_id, duplicate_count)
price_history(shopee_id, snapshot_date, list_price, effective_price)
scores(listing_id, snapshot_date, performance, battery, capability, value,
       is_frontier, confidence, scoring_version)
runs(id, snapshot_date UNIQUE, started_at, finished_at, source_kind, listing_count, status)
```

Notes:
- **Benchmarks live on `chipsets`, not devices** (§5.5). `devices.chipset_id` is the join;
  `throttle_modifier` is the only per-device perf adjustment.
- Battery stays per-device (cell size + display + tuning, not just SoC).
- `snapshot_date` everywhere → reproducible, diffable runs. `runs.snapshot_date UNIQUE` +
  transactional writes give idempotency (SC6): a re-run deletes-then-rewrites that date atomically.
- `sku_rollup` is the deduped cheapest-per-SKU set the frontier is computed over (§5.8).

---

## Milestones (vertical slices)

### M0 — Skeleton + framework docs
- Repo, `PROJECT-FRAMEWORK` four docs, ruff/pytest config, SQLite schema + migrations.
- `FixtureSource` returning a canned listing set; empty domain modules with signatures.
- **DoD:** `pytest` runs green on empty stubs; schema creates.

### M1 — Scoring core (pure, no I/O) ← highest-value, do first
- TDD `normalize`, `performance`, `battery`, `capability`, `value` against SPEC §5 with fixed
  reference bounds and known hand-computed expectations.
- TDD `pareto_frontier` with adversarial cases (ties, single point, all-dominated, duplicates).
- **DoD:** given a list of `(price, benchmarks, battery)`, produces stable scores + correct
  frontier. `scoring_version` pinned. This slice is fully testable with zero network.

### M2 — Entity resolution
- Title-clean ruleset + brand/model/variant extraction + rapidfuzz match to a seeded catalog.
- Alias table read/write; "needs mapping" bucket for misses.
- **DoD:** on a fixture of ~50 real ID titles, ≥85% resolve correctly; misses land in the queue.

### M3 — Persistence + daily use-case
- SQLite repos; `run_daily` wires FixtureSource → resolve → compute effective_price → **dedup to
  cheapest-per-SKU** (§5.8) → score → persist → diff vs prior snapshot (new arrivals, price drops).
- **Idempotent + transactional per `snapshot_date`** (SC6): begin tx → delete existing rows for
  that date → write → commit; failure rolls back leaving the prior snapshot intact.
- **DoD:** two consecutive fixture runs produce a correct changes diff; re-run = identical scores
  and no duplicate rows; a forced mid-run failure leaves the previous snapshot untouched.

### M4 — Web UI
- FastAPI endpoints backed by repos; static SPA with the five menu screens.
- Dashboard Pareto scatter (frontier highlighted, dominated greyed); Listings table; Catalog
  editor with "needs mapping" resolver; Changes; Settings (weights, band, keyword, Run now).
- **DoD:** full loop usable in the browser against fixture data; weight sliders re-score live.

### M5 — Real Shopee source
- Implement `AffiliateFeedSource` (preferred) and `InternalEndpointSource` (best-effort) behind
  `SearchSource`. Caching, backoff, one-burst-per-keyword, provenance logging.
- **DoD:** real listings flow through the exact M4 pipeline with no scoring/UI changes (SC4).

### M6 — Catalog refresh + scheduling + skill
- Manual-assisted monthly scrapers, **GSMArena first** (device→chipset mapping + specs + battery),
  then GB6/AnTuTu/Wild Life attached to *chipset* rows. Provenance + last-refreshed in Catalog.
- Populate `os_updates_years` / `security_updates_years` per device (§11.1).
- **Automatic daily scheduler (not a manual button):** OS-level trigger on the `run_daily`
  entrypoint — launchd LaunchAgent (`StartCalendarInterval`) on macOS, cron on Linux. Same code
  path as the UI's fallback Run-now. Plus launch-time catch-up: on startup, if no successful run
  exists for today, run once (safe — idempotent per snapshot_date). Ship the LaunchAgent plist +
  crontab line as install assets. (§8a, SC8)
- Package ID-market domain knowledge as reusable `id-android-market` skill.
- **DoD:** end-to-end daily run on real data; one chipset entry covers all its phones (SC7);
  catalog verifiably refreshable; skill installable.

---

## Testing strategy

- Domain layer: pure unit tests, hand-computed expectations, property tests for frontier.
- Application: use-case tests against `FixtureSource` + in-memory SQLite.
- Adapters: contract tests per `SearchSource` impl (same test suite runs against each).
- Golden snapshot: a pinned fixture snapshot → pinned expected scores; guards `scoring_version`.
- No network in CI; real-source tests are opt-in / marked.

## Open decisions to confirm before M4

- Frontend: ~~Plotly.js vs Chart.js~~ **Resolved** — the design prototype hand-rolls the Pareto
  scatter as inline **SVG with no chart lib** (`design/Ampere.dc.html`); M4 follows suit
  (FastAPI + vanilla JS + SVG, zero build, matches the terminal aesthetic).
- Scheduler: APScheduler in-process vs system cron. Default: **cron → /run** (simpler, survives
  restarts, matches your self-hosted habits).
- Telegram push of the daily frontier (Relay/Courier style) — deferred to v2 unless wanted in M6.

# Ampere

**Caliper for Android phones.** Daily Shopee ID listings (keyword + price band) → resolved to a
canonical model/variant → joined to a chipset benchmark + battery reference DB → two-axis value
score (Capability vs Value) → Pareto frontier → menu-driven local web UI.

## Install

```bash
git clone <this repo> && cd Ampere
./install.sh                 # venv + deps + verify + a seeded local DB (offline, no network)
```

That is the whole install: it finds Python ≥ 3.12 (preferring `uv`), creates `.venv`, installs the
project editable with the `[dev,web]` extras, runs the test suite and ruff, then seeds a local DB
with one offline run so the UI has data on first start.

```bash
./install.sh --schedule      # ...and automate the daily fetch (launchd on macOS, cron on Linux)
./install.sh --dry-run       # print the plan, change nothing
./install.sh --help          # --home DIR, --no-test, --no-seed
```

It is safe to re-run: an existing venv is reused, runs are idempotent per `snapshot_date` (SC6),
and the scheduler install **appends** to your crontab rather than replacing it. The data home
defaults to `$HOME/ampere` (`--home` to move it).

Then start the UI:

```bash
AMPERE_DB=$HOME/ampere/data/ampere.db .venv/bin/uvicorn ampere.web.api:app --reload
# http://127.0.0.1:8000 — 5 screens; sliders re-score server-side
```

## Read these first (in order)

1. [`SPEC.md`](SPEC.md) — the system spec (problem, scoring math §5, sources, HAR appendices). **Authoritative.**
2. [`PLAN.md`](PLAN.md) — stack, Clean-Architecture layout, data model, milestones.
3. [`PROGRESS.md`](PROGRESS.md) — living status. Update every session (cold-session resumable, SC5).
4. [`CLAUDE.md`](CLAUDE.md) — conventions & non-negotiable invariants for any session.

The UI design of record is in [`design/`](design/) (see [`design/NOTES.md`](design/NOTES.md)).

## Layout (Clean Architecture — dependency rule points inward)

```
ampere/
  domain/       pure logic + pydantic models — no I/O
                  scoring · frontier · resolve · pricing · dedup · diff · trust · longevity · catalog
  application/  use-cases orchestrating domain + ports
                  run_daily · refresh_catalog · catalog_seed · snapshot · views · notify · report
  ports/        interfaces (Protocols) — the only way I/O enters
                  search_source · catalog_source · repositories · notifier
  adapters/     concrete I/O
                  sources/ (fixture + affiliate + internal Shopee) · repos/ (SQLite)
                  scrapers/ (GSMArena perf + battery) · notify/ (Telegram + stdout)
  web/          thin FastAPI + static SPA (design system in web/static/)
tests/          pytest — domain + parsing fully testable with zero network (336 tests)
data/seed/      chipsets_seed.csv + devices_seed.csv (real SoC benchmarks + ID-band device→chipset)
deploy/         OS-scheduler assets — launchd plist + crontab (automatic daily fetch, SC8)
skills/         installable .skill packages (active copies auto-load from .claude/skills/)
install.sh      one-step installer (venv, deps, verify, seed, optional scheduler)
```

## Dev

```bash
.venv/bin/pytest                        # 336 tests, no network
.venv/bin/ruff check ampere tests       # ruff-clean is an invariant
```

Write the failing test from SPEC first (invariant #2). Live transports (Shopee `search_items`,
GSMArena HTML) are injected as `fetch` callables, so all parsing stays pure and offline-tested.

## Run the daily job

```bash
# Headless entrypoint the OS scheduler + the UI's "Run now" both call (idempotent per snapshot_date):
AMPERE_SOURCE=fixture .venv/bin/ampere-run-daily          # offline default; first run seeds the catalog
AMPERE_SOURCE=affiliate AMPERE_DB=~/ampere/data/ampere.db .venv/bin/ampere-run-daily   # live (ToS-safe)
```

The daily fetch is **automatic once per day** via an OS scheduler + launch-time catch-up (SPEC §8a,
SC8) — `./install.sh --schedule`, or see [`deploy/README.md`](deploy/README.md) to install by hand.
The monthly reference-data refresh (GSMArena → per-chipset benchmarks + per-device battery) runs
through `application/refresh_catalog.py`.

### Share the result (both off by default)

- **Daily push** — a digest of the best-value pick + the frontier, with outbound links inline.
  Configure it in the UI (Settings → NOTIFICATIONS: channel, bot token, chat id — persisted, with a
  "Send test" button), or by env (`AMPERE_NOTIFY=telegram|stdout` + `AMPERE_TELEGRAM_TOKEN`
  + `AMPERE_TELEGRAM_CHAT_ID`). DB settings override env.
- **Shareable report** — a self-contained HTML page (inline CSS + inline-SVG scatter, no external
  assets). Set `AMPERE_REPORT_PATH=…/frontier.html` to write it after each run, or hit
  `GET /api/report` for it live. Settings → SHARE has both buttons.

Neither can fail the run: the snapshot is persisted first, and both are failure-isolated. Full env
var table in [`deploy/README.md`](deploy/README.md).

## Status

**M0–M9 done and green** (336 tests, ruff-clean). Full pipeline: real Shopee source → resolve →
effective price → dedup → score → Pareto frontier → persisted + diffed → web UI; GSMArena catalog
scrapers + refresh; automatic daily scheduling; trust + longevity scoring; daily push; shareable
report.

The remaining backlog is gated on **external access**, not code: confirm a real affiliate feed
(validates `AffiliateFeedSource.parse_offer` against a live schema), run the first live GSMArena
`refresh_catalog` (fills the ID-band SoC benchmarks — until then the frontier is empty), and
confirm a real Telegram post lands. See [`PROGRESS.md`](PROGRESS.md).

# Ampere

**Caliper for Android phones.** Daily Shopee ID listings (keyword + price band) → resolved to a
canonical model/variant → joined to a chipset benchmark + battery reference DB → two-axis value
score (Capability vs Value) → Pareto frontier → menu-driven local web UI.

## Read these first (in order)

1. [`SPEC.md`](SPEC.md) — the system spec (problem, scoring math §5, sources, HAR appendices). **Authoritative.**
2. [`PLAN.md`](PLAN.md) — stack, Clean-Architecture layout, data model, milestones M0–M6.
3. [`PROGRESS.md`](PROGRESS.md) — living status. Update every session (cold-session resumable, SC5).
4. [`CLAUDE.md`](CLAUDE.md) — conventions & non-negotiable invariants for any session.

The UI design of record is in [`design/`](design/) (see [`design/NOTES.md`](design/NOTES.md)).

## Layout (Clean Architecture — dependency rule points inward)

```
ampere/
  domain/       pure logic + pydantic models — no I/O   (scoring, frontier, resolve, catalog, models)
  application/  use-cases orchestrating domain + ports  (run_daily, refresh_catalog, catalog_seed, snapshot, views)
  ports/        interfaces (Protocols) — the only way I/O enters
  adapters/     concrete I/O: sources/ (fixture + real Shopee), repos/ (SQLite), scrapers/ (GSMArena)
  web/          thin FastAPI + static SPA (design system in web/static/)
tests/          pytest — domain + parsing are fully testable with zero network (242 tests)
data/seed/      chipsets_seed.csv + devices_seed.csv (real SoC benchmarks + ID-band device→chipset)
deploy/         OS-scheduler install assets — launchd plist + cron (automatic daily fetch, SC8)
skills/         installable .skill packages (active copies auto-load from .claude/skills/)
```

## Dev

```bash
uv venv .venv && uv pip install --python .venv -e ".[dev,web]"   # dev pulls the `scrape` extra (bs4)
.venv/bin/pytest                        # 242 tests, no network
.venv/bin/ruff check ampere tests
uvicorn ampere.web.api:app --reload     # full 5-screen UI; seeds a demo DB, then catches up today
```

## Run the daily job

```bash
# Headless entrypoint the OS scheduler + the UI's "Run now" both call (idempotent per snapshot_date):
AMPERE_SOURCE=fixture .venv/bin/ampere-run-daily          # offline default; first run seeds the catalog
AMPERE_SOURCE=affiliate AMPERE_DB=~/ampere/data/ampere.db .venv/bin/ampere-run-daily   # live (ToS-safe)
```

The daily fetch is **automatic once per day** via an OS scheduler + launch-time catch-up (SPEC §8a,
SC8) — see [`deploy/README.md`](deploy/README.md) to install the launchd agent (macOS) or crontab
(Linux). The monthly reference-data refresh (GSMArena → per-chipset benchmarks + per-device battery)
runs through `application/refresh_catalog.py`.

## Status

**M0–M6 done and green** (242 tests, ruff-clean). Full pipeline: real Shopee source →
resolve → effective price → dedup → score → Pareto frontier → persisted + diffed → web UI;
GSMArena catalog scrapers + refresh; automatic daily scheduling. See PROGRESS for the v2 backlog
(confirm affiliate feed access; first live GSMArena refresh; optional Telegram push).

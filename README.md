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
  domain/       pure logic + pydantic models — no I/O        (scoring, frontier, resolve, models)
  application/  use-cases (run_daily) orchestrating domain + ports
  ports/        interfaces (Protocols) — the only way I/O enters
  adapters/     concrete I/O: sources/ (fixture + real), repos/ (SQLite), scrapers/ (M6)
  web/          thin FastAPI + static SPA (design system in web/static/)
tests/          pytest — domain is fully testable with zero network
data/seed/      chipsets_seed.csv (real GB6/AnTuTu-v10/WildLifeExtreme per SoC)
skills/         installable .skill packages (active copies auto-load from .claude/skills/)
```

## Dev

```bash
uv venv .venv && uv pip install --python .venv -e ".[dev,web]"
.venv/bin/pytest            # M0: green on the skeleton
.venv/bin/ruff check ampere tests
uvicorn ampere.web.api:app --reload   # serves the static shell (data endpoints land in M4)
```

## Status

M0 (skeleton + schema + FixtureSource + design shell) is in place and green. **M1 (scoring core,
TDD, zero network) is next** — see PROGRESS.

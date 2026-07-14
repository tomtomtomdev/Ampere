# Ampere — CLAUDE

Conventions and invariants for any Claude Code session working on this project. Read SPEC + PLAN
+ PROGRESS first, then this. `README.md` is the entry point; `design/` is the UI design of record
(see `design/NOTES.md`).

## What this project is

"Caliper for Android phones." Daily Shopee ID listings (keyword + price band) → resolved to
canonical model/variant → joined to a benchmark + battery reference DB → two-axis value score
(Capability vs Value) → Pareto frontier → menu-driven local web UI.

## Non-negotiable invariants

1. **Clean Architecture dependency rule.** `domain` imports nothing from `adapters`/`web`.
   I/O only through `ports` (Protocols). If scoring needs the network, the design is wrong.
2. **Spec-driven TDD.** Write the failing test from SPEC before the implementation. No untested
   scoring or frontier logic — ever.
3. **Deterministic scoring.** Same snapshot + same `scoring_version` = identical scores.
   Reference bounds are FIXED and versioned; never cohort-normalize (SPEC §5.1).
4. **Never fabricate benchmark data.** Missing metric → re-weight available pillars, mark
   `partial`. Unmatched device → `needs mapping`, excluded from frontier. No made-up numbers.
5. **`SearchSource` is swappable.** Scoring/UI must not know or care which source produced a
   listing. Every source impl passes the same contract test suite.
6. **Cold-session resumable.** State lives in the DB + the four docs. Update PROGRESS every
   session. Don't hold context in your head; write it down.

## Source honesty

Shopee has no official public search API. Prefer the **affiliate feed** (ToS-safe). The
internal-endpoint source is fragile, anti-bot, and ToS-violating — best-effort only, wrapped,
cached, low-volume (daily cadence is the safety margin). Benchmark sources (GB6, AnTuTu, 3DMark,
GSMArena) have no APIs either: monthly manual-assisted refresh, store provenance, cache hard.

## Scoring quick reference (authoritative math in SPEC §5)

```
norm(x)      = clamp((x-REF_MIN)/(REF_MAX-REF_MIN)*100, 0, 100)
performance  = 0.25*(gb6_single + gb6_multi + antutu + wildlife)   # normed, all-round
battery      = norm(active_use_hours)   # co-equal pillar, NOT a tiebreaker
capability   = W_PERF*performance + W_BATT*battery   # default 0.55 / 0.45, UI-tunable
value        = capability / price_juta
frontier     = non-dominated (price↓, capability↑) points
```

## Style

- pydantic models for all boundary data; typed everywhere; ruff clean.
- SQLite with `snapshot_date` on time-varying tables for reproducibility + diffing.
- Small pure functions in `domain`; orchestration in `application`; I/O in `adapters`.
- Web layer is thin: endpoints call use-cases/repos, no business logic in `web/`.

## Project layout & workflow

Clean-Architecture package under `ampere/` (`domain` → `application` → `ports` → `adapters` →
`web`); tests in `tests/`; SQLite schema in `ampere/adapters/repos/schema.sql`; seed data in
`data/seed/`; OS-scheduler install assets in `deploy/`. **M0–M6 are done and green** (242 tests,
ruff-clean) — the full pipeline runs end-to-end; see PROGRESS for the v2 backlog.

```bash
uv venv .venv && uv pip install --python .venv -e ".[dev,web]"
.venv/bin/pytest && .venv/bin/ruff check ampere tests   # keep both green (ruff-clean is an invariant)
```

The domain math (`scoring.py`, `frontier.py`, `resolve.py`) was ported **test-first** from
`design/Ampere.dc.html` (never pasted). When extending, keep the workflow: write the failing test
from SPEC first (invariant #2). The live transports (Shopee `search_items`, GSMArena HTML) are
injected as `fetch` callables so all parsing stays pure + offline-tested; the `httpx` fetchers are
best-effort and not exercised in CI.

## Skills (installed under `.claude/skills/` — they auto-trigger)

Three project skills carry the domain knowledge and auto-load when their triggers match. **Prefer
extending a skill's ruleset/reference over hard-coding rules in `ampere/`.** Distributable `.skill`
archives live in `skills/`; the active copies (what triggers) are in `.claude/skills/`.

- **`id-android-market`** — ID-market entity resolution: brand/model aliases, RAM/ROM variant
  rules, noise-token lexicon, new-vs-used condition words. Triggers on parsing/normalizing/matching
  Indonesian phone listings. Backs M2 (`domain/resolve.py`); mirrors Caliper's `id-vehicle-market`.
- **`shopee-marketplace`** — the `search_items` contract: `fe_filter_options` (Mall + price `▶◀`),
  micro-unit pricing (÷100000), `item_basic` field map, anti-bot/browser-session reality. Backs
  M5 + SPEC Appendix A.
- **`gsmarena-device-data`** — GSMArena battery (Active Use v2) + performance (GB6/AnTuTu/3DMark)
  HTML scraping, the per-tab `div.phones` gotcha, metric caveats; bundles `gsmarena_perf_parser.py`.
  Backs M6 + SPEC Appendices B/C.

## Definition of done (any slice)

Tests written first and green · deterministic · Clean-Architecture-respecting · PROGRESS updated
· no fabricated data · source-agnostic.

"""Ampere — caliper for Android phones (Shopee ID value scanner).

Layers follow the Clean Architecture dependency rule (see CLAUDE.md invariant #1):

    domain      -> pure logic, no I/O, imports nothing outward
    application -> use-cases orchestrating domain + ports
    ports       -> interfaces (Protocols) — the only way I/O enters
    adapters    -> concrete I/O (sources, repos, scrapers)
    web         -> thin FastAPI + static SPA

Read SPEC.md + PLAN.md + PROGRESS.md + CLAUDE.md before changing anything.
"""

__version__ = "0.1.0"

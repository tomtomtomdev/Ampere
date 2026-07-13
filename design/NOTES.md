# Design bundle — provenance & authority

This folder is the **UI design of record**, imported from `Design for spec.zip` (2026-07-12).

- **`README.md`** — the UI handoff: design tokens, screen specs, interactions, scoring math to port
  verbatim, sample data. This is authoritative for the **look, layout, and behavior** of the web UI.
- **`Ampere.dc.html`** — the working design prototype. Open in a browser to interact. Its logic
  class is a faithful, runnable reference of the SPEC scoring/dedup/frontier math — in M1 port it
  **test-first** into `ampere/domain/` (do not paste it in; CLAUDE.md invariant #2).
- **`support.js`** — prototype runtime **only**. Do NOT port, do NOT ship (README §"About").
- **`SPEC.md`** — a *snapshot* of the system spec that shipped inside the design bundle. It predates
  the current repo spec (no SC8 / §8a scheduling). **The authoritative spec is the repo-root
  [`../SPEC.md`](../SPEC.md).** Kept here only for bundle provenance.

The design tokens (colors, type, geometry) are ported into `ampere/web/static/styles.css`; the app
shell (sidebar/topbar/nav) is scaffolded in `ampere/web/static/index.html`. The five screens are
rendered from the API in **M4**.

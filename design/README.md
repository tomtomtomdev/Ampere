# Handoff: Ampere — phone value scanner dashboard

## Overview
Ampere is a local, menu-driven web dashboard that scores Shopee Indonesia phone listings
(default keyword `android`, price band 1jt–2jt IDR) against a benchmark + battery reference DB
and surfaces the **Pareto frontier** (non-dominated price/capability points). It is the UI layer
of the system described in `SPEC.md` (read that file first — it is the source of truth for the
data model, scoring math, sources, and success criteria). This bundle documents the **UI**; the
SPEC documents the **system**.

Five screens: **Dashboard** (hero — Pareto scatter + frontier table + weight sliders),
**Listings** (sortable/filterable table), **Catalog** (reference DB + needs-mapping queue),
**Watchlist** (price drops / new arrivals), **Settings**.

## About the Design Files
`Ampere.dc.html` is a **design reference created in HTML** — a working prototype that shows the
intended look, layout, data model, and interactions. It is **not production code to ship**. It
uses an internal streaming-component runtime (`support.js`) that is a prototyping tool, not a
production dependency — **do not copy `support.js` into the target codebase**.

The task is to **recreate this design in the target codebase's environment** using its established
patterns and libraries. If no codebase exists yet, this is a data-heavy analytics dashboard —
a sensible default stack is **React + a charting lib for the scatter** (Recharts/visx/D3) with a
Python/SQLite backend for the daily job (see SPEC §8 "PLAN"), but use whatever the project already
standardizes on. All scoring/dedup/frontier logic in the prototype is a faithful, runnable
reference implementation of the SPEC — port the math verbatim.

## Fidelity
**High-fidelity.** Final colors, typography, spacing, and interaction behavior are all intended as
shown. Recreate pixel-closely, then swap the prototype's inline styles for the codebase's styling
system (CSS modules / Tailwind / styled-components / etc.).

## Aesthetic direction — "instrument / caliper readout"
Dark, dense, terminal-like. Everything is monospace. One signal color (electric lime) marks
"good": frontier points, positive deltas, active nav, highlights. Warm-neutral dark greys, thin
hairline borders, no rounded corners, no gradients, no shadows except tooltip. The feel is a
precision measurement tool, not a consumer app.

## Design Tokens

### Color
| Token | Hex | Use |
|-------|-----|-----|
| bg / app | `#0a0b0a` | app background, deepest wells |
| panel | `#0d0f0d` | cards, sidebar, header, table bodies |
| panel-raised | `#101310` / `#131711` | table header rows, active nav bg, hover row |
| border | `#1c211a` | primary hairline borders |
| border-2 | `#262b22` | stronger dividers, input borders, header underline |
| border-accent | `#2a3024` / `#3a4a1e` | accent-tinted borders (chips, frontier badge) |
| divider-faint | `#141811` (~10% via `#14181110`) | row separators inside tables |
| text | `#dfe4d8` | primary body values |
| text-bright | `#f2f5ec` | model names, headings, emphasis |
| text-dim | `#8a9081` | secondary labels |
| text-muted | `#6b7164` | tertiary / captions |
| text-faint | `#565b50` | 4th-level / meta |
| **accent (lime)** | `#c6ff3a` | frontier, positive delta, active state, RUN/schedule dot, primary numbers |
| accent-hover | `#dfff8a` | link hover |
| warn (amber) | `#f2b545` | `partial` confidence, STAR+ seller, LEGACY battery flag, needs-mapping header |
| warn-border | `#4a3f1e` | amber chip border |
| danger (red) | `#ff6b6b` | "dominated" verdict text in tooltip |
| dominated-fill | `#20261c` | greyed scatter point fill |
| dominated-stroke | `#3a4033` | greyed scatter point stroke (new); `#8a9081` for used |

### Typography
- **Font:** `IBM Plex Mono` (weights 400/500/600) everywhere. `IBM Plex Sans` is loaded but the
  final design uses Mono throughout — you may drop Sans.
- Base body: 13px. Screen `<h1>`: 15px/600, letter-spacing 0.5px.
- Section labels (uppercase): 11px, letter-spacing 0.8px, color `#8a9081`.
- Table cells: 12px. Table headers: 10px, letter-spacing 0.5px. Sub-captions: 9.5–10px.
- Big value numbers (frontier value, deltas): 13px/600, lime.
- Chart axis labels: 10px, letter-spacing 1.5px, `#6b7164`; tick labels 10px `#565b50`.

### Spacing / geometry
- **border-radius: 0 everywhere** (except tiny status dots which are circles).
- No box-shadows except the hover tooltip: `0 8px 24px #000a`.
- Sidebar width **236px**; top bar height **52px**; content padding `24px 26px 60px`.
- Hairline borders `1px solid`. Table rows ~`10px 14px` padding.
- Chip padding `5px 11px`; small badges `1px 4–6px`.

### Motion
- `@keyframes blink`: `0%,60%{opacity:1} 61%,100%{opacity:0.25}` at `2.4s infinite` — used on the
  logo dot and the AUTO/schedule status dots.
- Scatter point opacity transition `0.12s`.

## App Shell (persistent chrome)

### Sidebar (236px, `#0d0f0d`, right border `#1c211a`)
- **Brand block** (padded 22/20/18, bottom border): 11×11px lime square with blink + glow
  (`box-shadow:0 0 10px #c6ff3a`), "AMPERE" 17px/600 letter-spacing 2px `#f2f5ec`; subtitle
  "caliper for phones · Shopee ID" 10.5px `#6b7164`.
- **Nav** (5 items, gap 2px): each is a full-width button, left-aligned, with a 5×16px left bar
  (lime when active, transparent otherwise), label 12.5px, and a right-aligned badge (count).
  Active item: bg `#131711`, text `#f2f5ec`, bar + badge lime. Inactive: transparent, text
  `#8a9081`, badge `#565b50`.
  - Dashboard (no badge) · Listings (badge = filtered SKU count) · Catalog (badge = needs-mapping
    count) · Watchlist (badge = price-drops + new-arrivals count) · Settings (no badge).
- **Footer** (top border, 10px, `#565b50`): `snapshot 2026-07-12`, `scoring v2.1.0`,
  `frontier per-condition`.

### Top bar (52px, `#0d0f0d`, bottom border)
- **Left — query chips** (11.5px): `keyword: <lime value>` (bordered), `band: 1.00jt–2.00jt`,
  `Shopee.co.id`.
- **Right — stats + schedule:** `raw 23` · `deduped <n>` · `matched <n>%` (lime) ·
  `last run 06:00 WIB` · **AUTO schedule pill**: bordered box with a blinking lime dot, "AUTO",
  and "next run in `Xh Ym`" (live countdown to next 06:00 WIB). **There is no manual run button** —
  the job runs unattended once per day (SPEC §4, §9).

## Screens

### 1. Dashboard (hero)
Header row: `Pareto frontier — capability vs effective price` + three inline checkbox toggles
(right-aligned, 11px, `accent-color:#c6ff3a`): **frontier only** (default ON), **blend conditions**
(default OFF), **Mall only** (default OFF).

Two-column body (`display:flex; gap:20px`):

**Left — chart panel** (fixed 772px, `#0d0f0d`, border, position:relative):
- SVG **760×430** (viewBox `0 0 760 430`, `overflow:visible`). Plot area: left pad 56, top pad 20,
  plot width 680, plot height 366.
  - X axis = **effective price** (`bandMin`..`bandMax`), Y axis = **capability** (0–100).
  - Y gridlines at 0/20/40/60/80/100 (`#1a1f17`), right-aligned tick labels `#565b50`.
  - X gridlines at 1.00/1.25/1.50/1.75/2.00 jt (`#141912`), centered tick labels.
  - Axis titles: "EFFECTIVE PRICE (IDR)" bottom center; "CAPABILITY" left, rotated -90°.
  - **Frontier polyline(s)**: lime `#c6ff3a`, 1.5px, connecting frontier points sorted by price.
    Per-condition by default (new = solid opacity 0.9; used = dashed `4 3` opacity 0.5). Blended
    mode = single line.
  - **Points** (circles): frontier → r5.5, fill+stroke lime, opacity 1. Dominated → r4, fill
    `#20261c`, stroke `#3a4033` (new) / `#8a9081` (used), opacity 0.72. Used condition → stroke
    `stroke-dasharray:2 2`, stroke-width 1.4. `cursor:pointer`, opacity transition 0.12s.
  - **Hover tooltip** (absolutely positioned at point's cx/cy, `translate(-50%,-108%)`): bg
    `#14181f`, border `#2f3a24`, `0 8px 24px #000a`, min-width 172px. Shows model (12px/600 bright),
    sub-line `variant · chipset · new|used[· Mall]` (10.5px dim), then rows: capability (lime),
    eff. price, value, and verdict ("ON FRONTIER" lime / "dominated" red).
- **Legend** (below svg, 10px `#8a9081`): lime dot = frontier · hollow dot = dominated · dashed
  dot = used/second.

**Right column** (flex:1, gap 16px):
- **Top-of-frontier table** (`#0d0f0d`): header "TOP OF FRONTIER — VALUE RANKED" / "cap / juta"
  (lime). Rows (top 7 by value): rank `01`.. (`#565b50`), model+variant, `chipset · effPrice`
  caption, right side big lime **value** + `cap NN.N` caption.
- **Capability weighting panel**: label "CAPABILITY WEIGHTING". Range slider (0–1, step 0.05,
  `accent-color`/thumb lime, track `#262b22`) bound to **W_PERF**; shows `performance <wPerf>` and
  `battery endurance <1-wPerf>`. Caption explains perf blend = GB6×2 / AnTuTu / Wild Life Extreme
  evenly weighted; battery is co-equal.

### 2. Listings
`<h1>` "Listings — N deduped SKUs". Filter chip row: brand chips (ALL, Xiaomi, Samsung, Infinix,
realme, OPPO, vivo, Tecno) | condition chips (ANY/NEW/USED) | confidence chips (ALL/FULL/PARTIAL),
separated by 1px `#262b22` dividers. Chip active = lime bg + `#0a0b0a` text + 600; inactive =
`#101310` bg, `#8a9081` text, `#262b22` border.

Table (CSS grid, columns `2.4fr 0.8fr 1.3fr 0.9fr 0.8fr 0.85fr 1.1fr 0.5fr`):
- **Header row** (38px, bg `#101310`, bottom border `#262b22`): clickable sort buttons — MODEL/
  LISTING, CHIPSET, EFF. PRICE, CAP, VALUE, CONF, SELLER, (blank). Active sort key text `#dfe4d8`
  with lime `▲`/`▼`; others `#6b7164`. (CONF/SELLER/last are not sortable.)
- **Rows** (12px, hover bg `#101310`, separator `#14181110`):
  - Col 1: model (bright) + variant (muted); inline badges — `FRONTIER` (lime, bordered) if on
    frontier, `×N` dup count if >1; second line = raw listing title (10px `#565b50`, truncated).
  - Chipset (dim). Eff. price (bright) with `▼ <drop>jt` lime sub-line if price dropped.
  - Cap (lime 500). Value (bright). Confidence badge: `full` lime-bordered / `partial`
    amber-bordered.
  - Seller: `★<rating>` + `MALL` badge (lime) + `STAR+` (amber) as applicable; location sub-line.
  - `open →` link (lime) — in production this is the outbound Shopee/affiliate URL (SPEC §11.2).

### 3. Catalog
`<h1>` "Catalog — reference DB". Two columns.

**Left (flex 1.4):**
- **CHIPSET BENCHMARKS** table ("one row per SoC · refreshed 2026-06 · GSMArena"). Grid
  `1.6fr .9fr .9fr 1fr .9fr .6fr`: CHIPSET, GB6 S, GB6 M, AnTuTu v10, WLE Hi (all right-aligned
  numbers), "used by" count (lime). Sorted by GB6 single desc.
- **DEVICE ROWS** table ("battery + update longevity are per-device"). Grid
  `1.6fr 1.3fr .9fr .9fr .9fr`: DEVICE (model+variant), CHIPSET, ACTIVE USE (`NN.Nh` + `v2` faint /
  `LEGACY` amber-bordered badge), OS/SEC yr (`3/4`), SOURCE (`GSMArena`).

**Right (flex 1):**
- **NEEDS MAPPING QUEUE** (amber header, border `#2a2513`). Each unresolved listing: full title,
  then an "assign model…" text input + lime "map" button. Footer note: mapped aliases are
  remembered in the `id-android-market` ruleset (SPEC §7).

### 4. Watchlist
`<h1>` "Watchlist — vs snapshot 2026-07-11". Two columns.
- **PRICE DROPS** (lime header): rows with model+variant, `chipset · cap NN.N`, current eff price +
  struck-through previous price, and a lime `▼ <drop>jt` on the right.
- **NEW ARRIVALS** (dim header): lime dot, model+variant, `chipset · effPrice`, optional
  "ON FRONTIER" badge, big lime value on the right.

### 5. Settings (max-width 720px)
Stacked cards (1px `#1c211a` gaps):
- **QUERY**: keyword text input (lime text), price min / price max IDR inputs.
- **SCORING WEIGHTS** ("scoring_version v2.1.0"): W_PERF range slider (same as Dashboard); read-only
  chips for the four fixed 0.25 perf sub-weights + `W_BATT battery ·<1-wPerf>`.
- **FILTERS & TOGGLES** (checkboxes): Mall only (SHOP_TYPE=OFFICIAL_MALL — practical "new" proxy) ·
  Blend conditions in frontier · Longevity bonus (fold OS-update years into capability) · Trust
  penalty on value.
- **SOURCE**: chips AffiliateFeed / InternalEndpoint / Fixture (SPEC §6). Bottom row: description of
  unattended idempotent/transactional daily runs + a **SCHEDULE ACTIVE** status box (blinking lime
  dot, "daily 06:00 WIB · next in Xh Ym"). No manual run trigger.

## Interactions & Behavior
- **Nav**: clicking a sidebar item sets the active screen and clears any hover state.
- **Sort** (Listings): click a sortable header → set sort key; clicking the active key toggles
  asc/desc (default desc). `model` sorts as string (localeCompare), all others numeric.
- **Filters**: brand / condition / confidence chips and the Mall-only toggle filter the deduped,
  in-band set. `frontier only` (Dashboard) additionally hides dominated points. All filters and
  weight changes **recompute scoring, dedup, and frontier live**.
- **W_PERF slider**: recomputes `capability` for every row → re-scores value, re-derives frontier,
  re-lays-out the scatter, in real time.
- **Toggles**: `blended` switches frontier between per-condition and single blended;
  `longevity` folds OS-update years into capability; `trustPenalty` soft-penalizes value for
  low-trust non-Mall listings (see math below).
- **Scatter hover**: mouseenter a point → tooltip; mouseleave → hide.
- **Schedule countdown**: `next run in` is computed from now to the next 06:00 WIB (UTC+7).
- **No manual "run"** anywhere — the daily job is unattended (SPEC §4/§9).

## State Management
Prototype state (port to your store — the UI is a pure function of it):
`screen` ('dashboard'|'listings'|'catalog'|'changes'|'settings'), `wPerf` (0–1, default 0.55),
`bandMin`/`bandMax` (IDR, default 1_000_000 / 2_000_000), `keyword` ('android'),
`brand`/`cond`/`conf` filter selections ('all'|…), `mallOnly` (false), `frontierOnly` (true),
`blended` (false), `longevity` (false), `trustPenalty` (false), `source`
('affiliate'|'internal'|'fixture'), `sortKey` ('value'), `sortDir` ('desc'), `hover` (point|null).

**Data flow (per SPEC §2 — this is the whole daily pipeline):**
`fetch listings → resolve each to canonical (model,variant) → JOIN to devices/chipsets reference →
score → dedup to cheapest-per-SKU → Pareto frontier → diff vs yesterday`. In production the
reference DB (chipsets, devices) is a slowly-changing monthly refresh; only listings are daily.

## Scoring math (port verbatim — matches SPEC §5; reference impl in `Ampere.dc.html` logic class)
```
norm(x, MIN, MAX) = clamp((x - MIN)/(MAX - MIN) * 100, 0, 100)
Reference bounds (versioned): GB6 single 500–3000, GB6 multi 1500–9000,
  AnTuTu v10 300000–2600000, Wild Life Extreme (Highest) 700–7000, Active Use hours 6.0–20.0
performance = 0.25*norm(gb6_single) + 0.25*norm(gb6_multi) + 0.25*norm(antutu) + 0.25*norm(wildlife)
battery     = norm(active_use_hours)          # per-DEVICE, not per-chipset
capability  = W_PERF*performance + (1-W_PERF)*battery      # default W_PERF 0.55
  longevity bonus (toggle): capability = capability*0.94 + norm(os_update_years,0,5)*0.06
effective_price = list_price + shipping_est - voucher_est - cashback_est   # ignore harga-coret
value       = capability / (effective_price / 1_000_000)
  trust penalty (toggle): if !is_mall && seller_rating < 4.5 → value *= 0.85
```
- **Benchmarks belong to the CHIPSET** (SPEC §5.5): a score entered once for a SoC applies to every
  device with it. Battery/OS-updates stay per-device.
- **Confidence**: `full` (all metrics present) / `partial` (some missing, re-weight — expected
  default in this band) / `unmatched` (excluded from frontier → needs-mapping queue). Never
  fabricate a benchmark.
- **Dedup** (SPEC §5.8): collapse to one row per (model, variant, condition) = lowest effective
  price; keep `duplicate_count`. Do this *before* the frontier.
- **Pareto frontier** (SPEC §5.3): over the deduped in-band set, a point is **dominated** if another
  exists with `eff ≤` AND `cap ≥` (strictly better on ≥1 axis). Frontier = non-dominated set.
  Computed **within a condition class** by default (new vs new, used vs used); `blended` unions them.

## Sample data
The prototype ships 23 real 1jt–2jt IDR listings across Redmi Note 13 / Poco M6·X6 / Infinix
Note 40·Hot 40 Pro / Samsung A15·A05s / realme C67·12 / OPPO A60 / vivo Y28 / Tecno Spark 20 Pro
(+ 2 deliberately unmatched titles for the needs-mapping queue), mapped to 10 chipsets with
plausible GB6/AnTuTu/Wild-Life-Extreme numbers and per-device battery/OS-update data. These are
**illustrative** — production data comes from the sources in SPEC §6 / Appendices A–C. Do not treat
the exact numbers as authoritative.

## Assets
None. No images or icon fonts — all glyphs are Unicode (`▲ ▼ ★ ▼ · →`) and CSS shapes. Only external
dependency is the IBM Plex Mono webfont (Google Fonts) — substitute your codebase's mono if it has
one.

## Files
- `Ampere.dc.html` — the full design reference (template + logic). Open in a browser to interact.
  Everything above is implemented here; read the logic class for the exact scoring/dedup/frontier
  code and the sample dataset.
- `SPEC.md` — **the system spec** (problem, scoring model, data sources, entity resolution, success
  criteria, verified HAR appendices for the Shopee + GSMArena endpoints). Authoritative for backend.
- `support.js` — prototype runtime **only**. Do NOT port; do NOT ship.

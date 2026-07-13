# Ampere — SPEC (v2)

> Android-phone value scanner for the Indonesian Shopee market.
> "Caliper for phones": messy marketplace listings in → normalized model/variant →
> joined to a **chipset** benchmark + battery reference DB → two-axis value score → Pareto frontier out.

**v2 changelog (post gap-review):**
- Benchmarks now hang off **chipset**, not device (§5.5, §7a). ~5–10× less catalog upkeep + fixes coverage.
- **GSMArena is the primary catalog source** for device→chipset mapping, specs, and battery (§6).
- **Condition** restored as a filter/flag; **Shopee Mall** added as a trust signal (§5.6). Mall
  detection is **resolved from HAR**: `SHOP_TYPE=OFFICIAL_MALL` filter + per-item `is_official_shop`
  (see Appendix A).
- **Effective price** (ongkir/voucher/cashback-adjusted) replaces raw price on the value axis (§5.7).
- **Seller trust** (rating / Mall / Star) is a first-class value input (§5.6).
- **Dedup to cheapest-per-SKU** before frontier (§5.8).
- **Idempotent, transactional daily runs** per snapshot_date (§9, SC6).
- **Software-update longevity** added to the device catalog; **affiliate output** noted as biz path (§11).

---

## 1. Problem

Buying a phone in the 1jt–2jt Shopee segment is a mess of near-identical listings, promo
noise, and specs you can't trust from the title alone. The buyer's real question is:
**for my rupiah, which phone gives the most capability — and which listings are objectively
dominated (something cheaper is also better)?**

Ampere answers that daily, for a configurable keyword + price band, by cross-referencing each
listing against real benchmark and battery data instead of the seller's marketing copy.

## 2. Core insight (read this before designing anything)

**Only the listings are "daily". Everything else is a slowly-changing reference DB.**

A Redmi Note 13's Geekbench 6, AnTuTu, 3DMark Wild Life, and GSMArena battery numbers do not
move day to day. So the daily job is cheap:

```
fetch listings → resolve each to canonical (model, variant) → JOIN to devices reference
→ score → diff vs yesterday → surface frontier + new arrivals + price drops
```

The "cross-check four sources" work is a **monthly catalog refresh**, not a daily cost.

## 3. Goals

- G1. Daily fetch of Shopee listings for a configurable keyword (default `android`) within a
  configurable price band (default `min 1_000_000`, `max 2_000_000`, IDR).
- G2. Resolve each listing to a canonical **model + variant** (e.g. `Redmi Note 13 Pro 5G` `8/256`).
- G3. Score every candidate on two axes: **Capability** (all-round performance + battery
  endurance) and **Value** (capability per juta).
- G4. Compute and highlight the **Pareto frontier** — non-dominated (price, capability) points.
- G5. Track price + score history per listing; surface **new arrivals** and **price drops**.
- G6. Present all of this through a **local web UI with menu navigation** (no CLI as primary UX).

## 4. Non-goals (v1)

- Not a general "best phone" oracle — scoped to the configured keyword + price band + Shopee ID.
- Not real-time; one scheduled run per day is the design point (and it protects the source).
- No purchasing, cart, or checkout automation.
- Not multi-marketplace at launch (Tokopedia/Lazada are v2 behind the same source interface).

## 5. The scoring model

### 5.1 Normalization (stable, not cohort-relative)

Every raw benchmark is normalized 0–100 against **fixed reference bounds**, NOT against the
daily cohort. Cohort-relative scores drift every day and become uncomparable over time.

```
norm(x) = clamp( (x - REF_MIN) / (REF_MAX - REF_MIN) * 100 , 0, 100 )
```

Reference bounds live in config and are versioned (`scoring_version`). Suggested starting bounds
(tune after first catalog load):

| Metric                  | REF_MIN | REF_MAX | Source            |
|-------------------------|---------|---------|-------------------|
| GB6 single-core         | 500     | 3000    | GSMArena review (per Appendix C) |
| GB6 multi-core          | 1500    | 9000    | GSMArena review   |
| AnTuTu **v10** total    | 300000  | 2600000 | GSMArena review (v10 tab; v11 runs higher — pick one, stay consistent) |
| 3DMark **Wild Life Extreme** (Highest) | 700 | 7000 | GSMArena review |
| GSMArena Active Use (h) | 6.0     | 20.0    | GSMArena battery  |

> **Corrected from HAR (Appendix C):** GSMArena reports 3DMark **Wild Life Extreme**, not standard
> Wild Life — a harder test with much lower numbers (budget SoCs ~850–1000, flagships ~6000+).
> Bounds above are set for Extreme (Highest). AnTuTu is available as **v10 and v11** tabs; standardize
> on v10 for now. All four perf metrics come from one GSMArena review page (see Appendix C), which
> also supplies the device→chipset mapping — so a single source populates the whole chipset table.

> GSMArena note: current metric is **Active Use Score** in hours (test revised 2023). Older
> phones may only have the legacy **Endurance rating**. Store which one, normalize separately,
> never mix the two silently. Flag legacy-only devices in the UI.

### 5.2 Two pillars → Capability

All-round performance blend (even weights, tunable in UI):

```
performance = 0.25*norm(gb6_single)
            + 0.25*norm(gb6_multi)
            + 0.25*norm(antutu)
            + 0.25*norm(wildlife)
```

Battery is a **co-equal pillar**, not a tiebreaker:

```
battery = norm(active_use_hours)     # or norm(legacy_endurance) if that's all we have

capability = W_PERF * performance + W_BATT * battery
             where default W_PERF = 0.55, W_BATT = 0.45   (both exposed as sliders)
```

### 5.3 Value axis + frontier

```
value = capability / effective_price_juta    # capability per adjusted 1,000,000 IDR (see §5.7)
```

Then the value-investor move: over today's candidate set (already deduped to cheapest-per-SKU,
§5.8), compute the **Pareto frontier** on (effective_price ↓ better, capability ↑ better). A
listing is **dominated** if another exists that is cheaper-or-equal AND higher-or-equal capability
(strictly better on at least one). The frontier is the "margin of safety" set; dominated listings
are filtered by default (toggle to show).

> Frontier is computed **within a condition class** by default (§5.6): new phones compete with
> new, used with used. A single blended frontier is available as a toggle, but the default avoids
> a used ex-flagship silently dominating every new budget phone.

### 5.4 Confidence / data-quality flag

Each score carries a confidence enum: `full` (all 4 perf + battery present), `partial` (some
missing, pillar re-weighted), `unmatched` (couldn't resolve to a device — excluded from frontier,
shown in a "needs mapping" bucket). Never fabricate a benchmark number to fill a gap; re-weight
the available metrics and mark `partial`. **In this price band `partial` is the expected default,
not the exception** — the chipset model (§5.5) is what pushes most listings toward `full`.

### 5.5 Benchmarks belong to the chipset, not the device

GB6 / AnTuTu / Wild Life scores are properties of the **SoC**. A Dimensity 7200 scores the same
in a Redmi, a Poco, or an Infinix. Therefore:

- Benchmarks attach to a `chipset` row, not a `device` row.
- `devices` reference a chipset; a score found for *any* phone with that SoC covers *all* of them.
- Optional per-device `throttle_modifier` (0.85–1.0) for known thermal/sustained-perf differences;
  default 1.0. Applied after normalization, before the performance blend.

This cuts catalog maintenance ~5–10× and largely resolves the coverage problem (§5.4). Battery
stays per-device (it depends on cell size + display + tuning, not just the SoC).

### 5.6 Condition + seller trust

Two listings at the same price are not the same purchase. Capture:

- `condition` enum: `new` | `used` | `refurbished` | `unknown`. Extracted from title/attributes
  (`second`, `bekas`, `mulus`, `ex-inter`, `refurbish`, `BNIB`, `segel`). Default frontier is
  per-condition (§5.3).
- `is_mall` (Shopee Mall) — strong trust signal (official stores, genuine-new, low scam risk).
  **Resolved from HAR (Appendix A):** request-side filter is `fe_filter_options` group
  `SHOP_TYPE=OFFICIAL_MALL`; item-side flags are `is_official_shop` + `show_official_shop_label`.
- `seller_rating`, `seller_review_count`, `is_star_seller` — folded into a `trust_score`. From
  HAR these map to `item_rating.rating_star`, `item_rating.rating_count[0]`, `is_preferred_plus_seller`.

Trust does **not** enter capability. It appears as a filter + a column, and optionally as a soft
penalty on `value` for low-trust/high-scam-risk listings (config toggle, off by default so the
raw value stays legible). Mall/trust is a first-order concern in the ID market, not a footnote.

### 5.7 Effective price (not raw price)

The value axis uses `effective_price`, a best-effort true cost:

```
effective_price = list_price + shipping_est - voucher_est - cashback_est
```

Ignore strikethrough "harga coret" anchor prices entirely (marketing fiction). Each adjustment is
optional and flagged; when a component is unknown it's zero and the listing is marked
`price_confidence = partial`. Raw `list_price` is always stored alongside for auditability.

### 5.8 Dedup to cheapest-per-SKU (before the frontier)

Sellers spam the same phone many times; many sellers carry the same SKU. Before scoring the
frontier, collapse listings to **one row per (model, variant, condition)** = the
lowest-effective-price instance, keeping a `duplicate_count` and links to the alternates. Without
this the frontier plots listing noise and one mispriced outlier can define it. `shopee_id` dedup
alone is insufficient (it only catches exact re-posts).

## 6. Data sources & honesty about them

| Source        | Access reality                                                        | Cadence  |
|---------------|----------------------------------------------------------------------|----------|
| Shopee search | **No official public search API.** Affiliate feed (Involve Asia / Accesstrade) is ToS-safe but narrower; internal app endpoints are undocumented, anti-bot, ToS-violating, fragile. Wrap behind an interface; treat as breakable. | daily |
| **GSMArena**  | **Primary catalog source.** Gives device→**chipset** mapping, full specs, AND battery (Active Use / legacy endurance). This is the spine of the reference DB — seed devices + chipset links here first. Scrape/manual, no API. | monthly |
| Geekbench 6   | Per-**chipset** GB6 single/multi — Geekbench Browser, scrape/manual, no API | monthly |
| AnTuTu        | Per-**chipset** total — ranking pages, scrape/manual, no API          | monthly  |
| 3DMark        | Per-**chipset** Wild Life — device list, scrape/manual, no API        | monthly  |

**Catalog build order:** GSMArena first (it maps each device to its SoC and supplies battery),
then attach GB6/AnTuTu/Wild Life to the *chipset* rows GSMArena revealed. Because benchmarks are
per-chipset (§5.5), the benchmark scrapers only need one entry per SoC, not per phone.

**Design consequence:** `SearchSource` is an interface with at least two implementations
(`AffiliateFeedSource`, `InternalEndpointSource`) plus a `FixtureSource` for tests/offline dev.
The daily cadence is a *feature* for the fragile path — low volume, aggressive caching, one
burst per keyword looks nothing like abuse — but never assume it's stable.

## 7. Entity resolution — this is where the real effort goes

Most of the build time is here, not in scoring. A title like:

```
"Xiaomi Redmi Note 13 Pro 5G 8/256 NFC Garansi Resmi HP Murah Promo COD"
```

must resolve to `model = "Redmi Note 13 Pro 5G"`, `variant = "8/256"`. Pipeline:

1. **Title clean** — strip promo/noise tokens (`promo`, `murah`, `cod`, `garansi resmi`, emoji,
   seller boilerplate) via a maintained ID-market ruleset.
2. **Brand + model extraction** — regex/alias table (`redmi note 13 pro`, `poco x6`, `infinix
   note 40`, `realme c67`, `samsung a15`, `tecno spark`, …).
3. **Variant extraction** — RAM/ROM pattern `\d+\s*/\s*\d+`, plus `5G`/`NFC` qualifiers that
   change the SKU.
4. **Fuzzy match** to `devices` catalog (rapidfuzz), threshold + manual-override table for the
   long tail.
5. **Unmatched → "needs mapping" queue** surfaced in the UI so the human closes the gap once,
   and the alias is remembered.

Encode the ID-market domain knowledge (brand aliases, common variants, noise tokens) in a
reusable `id-android-market` skill, mirroring `id-vehicle-market` from Caliper.

## 8. UI — menu-driven local web app

Local web dashboard (see PLAN for stack). Menu / screens:

1. **Dashboard** — Pareto scatter (x = price, y = capability), frontier points highlighted,
   dominated points greyed. Hover = model/variant/price/score. Top-N frontier table beneath.
2. **Listings** — sortable/filterable table (price, model, capability, value, confidence,
   seller, link out to Shopee). Filter by price band, brand, confidence, frontier-only.
3. **Catalog** — the `devices` reference DB. View/verify/edit benchmark + battery numbers,
   see data source + last-refreshed date, resolve "needs mapping" queue.
4. **Watchlist / Changes** — today's new arrivals, price drops vs yesterday, score changes.
5. **Settings** — keyword, price min/max, scoring weights (W_PERF/W_BATT + per-metric),
   condition filter, **Mall-only toggle**, min seller trust, source selection, run-now button,
   schedule status.

## 9. Success criteria

- SC1. A daily run for the default keyword/band produces a scored, deduped candidate set with a
  correctly computed Pareto frontier, reproducible from stored snapshots.
- SC2. ≥85% of listings in the default band auto-resolve to a device without manual mapping,
  after the catalog + alias table are seeded.
- SC3. Re-running scoring on an unchanged snapshot yields identical scores (deterministic;
  pinned `scoring_version`).
- SC4. Swapping `SearchSource` implementation requires zero changes to scoring/UI layers.
- SC5. Cold-session resumable: another engineer (or a fresh Claude session) can read the four
  docs + DB and continue with no lost context.
- SC6. **Daily runs are idempotent + transactional per `snapshot_date`:** a run that fails
  mid-way leaves no partial snapshot, and re-running the same date replaces rather than
  duplicates — so price-drop / new-arrival diffs never corrupt.
- SC7. A benchmark entered once for a chipset is reflected on **every** device sharing that SoC,
  with no duplicate data entry.

## 10. Risks

- R1. Shopee source breaks / gets blocked. → interface + FixtureSource + affiliate fallback;
  daily cadence minimizes exposure.
- R2. Benchmark scraping is brittle / ToS-sensitive. → manual-assisted monthly refresh, cache
  hard, store provenance; catalog is small and slow-moving so manual entry is viable.
- R3. Entity resolution long tail. → human-in-the-loop "needs mapping" + persistent alias table.
- R4. Score drift from changing reference bounds. → version bounds; never cohort-normalize.
- R5. Legal/ToS. → prefer affiliate feed; document that internal-endpoint mode is at user's risk.

## 11. Business layer

### 11.1 Software-update longevity = the sharpest value differentiator

Years of guaranteed Android + security updates hugely affect true cost-of-ownership and resale,
and split sharply by brand in this band (Samsung's budget update policy vs typical Infinix/Tecno).
It's arguably the single field that most separates "cheap" from "good value." Add to `devices`:

- `os_updates_years` (major Android versions promised)
- `security_updates_years`
- `update_source` (provenance — manufacturer pledge vs estimate)

Surface it in the Catalog + Listings, and optionally fold a small **longevity bonus** into
`capability` behind a config toggle (off by default, so the core score stays benchmark-pure).

### 11.2 Affiliate output is a monetization path, not just the safe data source

The affiliate feed (Involve Asia / Accesstrade) that's the ToS-safe source is *also* a revenue
channel: the natural output — "best-value phone in the band this week + the frontier" — carries
affiliate links for free. Design the output layer so a listing's outbound URL can be an affiliate
link, and keep the frontier/report shareable (a static public page later). Even as a personal
tool this framing costs nothing now and preserves the option to publish. Keep scoring **honest
and source-independent** — value ranking must never be influenced by commission, or the tool loses
the credibility that makes it worth publishing.

---

## Appendix A — Shopee `search_items`, verified from HAR (2026-07-12)

Captured from a real session (`shopee_co_id.har`). This is the concrete contract behind the
`InternalEndpointSource`. Treat as reverse-engineered + breakable (see auth note); prefer the
affiliate feed where it suffices.

### Endpoint
`GET https://shopee.co.id/api/v4/search/search_items`

### Query params (the exact keyword + Mall + price-band + paging scenario)
| Param | Value / meaning |
|-------|-----------------|
| `keyword` | `android` |
| `limit` | `60` (page size) |
| `newest` | offset: `0`, `60`, `120`, … (pagination cursor) |
| `by` / `order` | `relevancy` / `desc` |
| `page_type`, `scenario`, `source`, `version` | `search`, `PAGE_GLOBAL_SEARCH`, `SRP`, `2` |
| `fe_filter_options` | JSON array of filter groups — see below |

**`fe_filter_options`** (URL-encoded JSON) is where Mall + price live:
```json
[
  {"group_name":"SHOP_TYPE","values":["OFFICIAL_MALL"]},
  {"group_name":"PRICE_RANGE","values":["1000000▶◀2000000"]}
]
```
> Price-range delimiter is the literal `▶◀` (U+25B6 U+25C0), min-then-max, **in whole IDR**.
> Drop the `SHOP_TYPE` group to include non-Mall (used/marketplace) listings.

### Response
Top level: `total_count` (e.g. 680 → `ceil(680/60)=12` pages), `nomore` (stop flag), `items[]`.
Each `items[i].item_basic` (~109 fields). Fields that map to our model:

| Our field | `item_basic` source | Note |
|-----------|--------------------|------|
| listing id / shop id | `itemid`, `shopid` | dedup + URL build |
| title | `name` | feed to entity resolver |
| brand | `brand` | resolver hint (may be blank) |
| **variant (RAM/ROM)** | `tier_variations[].options` | field name varies: `STORAGE` / `PENYIMPANAN` / `Kapasitas`; format varies: `8/256`, `4GB/128GB`, `4/64` — normalize |
| `list_price` | `price` ÷ **100000** | prices are micro-units (`185900000000` = Rp 1,859,000) |
| harga-coret (ignore) | `price_before_discount` ÷ 100000 | often marketing fiction (Rp 3,299,000 "before" on a 1.86jt phone) → do NOT use |
| `is_mall` | `is_official_shop`, `show_official_shop_label` | Mall = official store |
| trust | `item_rating.rating_star`, `item_rating.rating_count[0]`, `is_preferred_plus_seller`, `shopee_verified` | → `trust_score` |
| popularity | `historical_sold`, `sold`, `global_sold_count` | context column |
| location | `shop_location` | Jabodetabek relevance |
| COD | `can_use_cod` | |
| shipping / voucher | `free_shipping_info`, `show_free_shipping`, `voucher_info` | **sparse/empty in search payload** |

### Two consequences for the design
1. **`condition` is NOT a first-class search field.** With the Mall filter every result is
   effectively new, so **Mall filter is our practical "new" proxy**; for used, drop the Mall
   filter and infer condition from the title (§5.6). Confirms Mall ≠ full condition axis.
2. **`effective_price` will usually be `partial`.** Shipping/voucher/cashback are largely
   absent from the search payload — they live in item-detail / checkout. v1: compute
   `effective_price` from what's present (mostly = `list_price`), flag `partial`, and only fetch
   item-detail for the frontier shortlist if it proves worth the extra calls.

### Auth / anti-bot reality (this is the fragility, quantified)
The request carries signed, device-fingerprinted headers minted by Shopee's anti-bot SDK:
`af-ac-enc-dat`, `af-ac-enc-sz-token`, `sz-token`, `x-sap-ri`, `x-sap-sec`, `x-sz-sdk-version`,
`x-csrftoken`, plus session cookies. These are generated client-side by obfuscated JS and expire.

**Implication:** hand-forging headers is a losing game. The robust `InternalEndpointSource`
should **drive a real logged-in browser session** (e.g. Playwright with a persisted profile) so
the tokens are minted for you, then read the `search_items` JSON responses — rather than
replaying static headers. This keeps the daily job working across token rotations, at the cost
of running a headless browser. Still ToS-sensitive; affiliate feed remains the clean path.

---

## Appendix B — GSMArena battery source, verified from HAR (2026-07-12)

Captured from `battery.har` (page: `battery-test-v2.php3`). Unlike Shopee, **GSMArena exposes no
JSON API** — the battery ranking is server-rendered HTML in the page document.

- **Approach:** plain HTTP `GET` + HTML parse (BeautifulSoup). No anti-bot SDK, no signed/expiring
  headers, no logged-in session, no browser automation required. This is the *simple* source.
- **Ranking page:** `https://www.gsmarena.com/battery-test-v2.php3` — paginated table of
  device → **Active Use Score** (hours, higher = better; displayed like `15:23h`). This is the v2
  test (confirmed by the captured page title "Battery life test v2.0").
- **Per-device page:** each phone's own GSMArena page has the detailed battery breakdown if the
  sub-scores are wanted later.
- **Metric handling:** store `battery_metric_kind` = `active_use_v2` vs legacy `endurance` and
  normalize separately (§5.1). Never mix the two.
- **Etiquette:** real User-Agent, polite delay + backoff, cache hard, monthly cadence. Occasional
  Cloudflare challenge; no token machinery otherwise.
- **Note on this capture:** the HAR's 173 entries were all ad-tech/analytics; the page document
  body (with the table) was not stored by DevTools, so no live Active Use values were extracted
  here. Re-capture with "Save all as HAR with content" or scrape live during M6. **Do not
  fabricate Active Use numbers** to fill the gap.

Net: `GsmArenaBatterySource` is a thin HTML scraper — the low-risk counterpart to the fragile
Shopee `InternalEndpointSource` in Appendix A.

---

## Appendix C — GSMArena performance source, verified from HAR (2026-07-12)

Captured from `performance.har` (page `…-review-XXXXpN.php`, the "benchmarks" sub-page of a
review). **This one source supplies all three perf benchmarks AND the device→chipset mapping** —
it is the backbone of the chipset table (§5.5). Like battery, it's server-rendered HTML, no API,
no anti-bot. Parser shipped as `gsmarena_perf_parser.py`.

### DOM structure (per benchmark)
`<div class="benchmark-widget bar-chart">` containing:
- `<h3>` title: `GeekBench 6` | `AnTuTu` | `3DMark`
- `<ul class="tabs">` naming sub-metrics
- **one `<div class="phones">` per tab, in tab order** (this is the key: each tab is its own
  container — not a flat list, not data-attributes). Each row inside carries `span.name`,
  `span.value`, `span.chipset`, `span.memory`.

### Tab → metric mapping
| Widget | Tabs (in order) | We use |
|--------|-----------------|--------|
| GeekBench 6 | Single-core, Multi-core | both |
| AnTuTu | v10, v11 | **v10** |
| 3DMark | Wild Life Extreme (Highest), Wild Life Extreme (Lowest), Solar Bay | **Extreme Highest** |

### What one page yields
A single review page returned **95 benchmark rows across ~16 comparison devices**, each tagged
with chipset + memory. Rolled up to a per-chipset seed table (`chipsets_seed.csv`, 13 SoCs).
Scraping ~20–30 review pages covers essentially every chipset in the 1jt–2jt band, with heavy
overlap that lets values be cross-checked.

### Validation of the chipset model (§5.5)
Snapdragon 7 Gen 4 appeared in 4 different phones on one page; GB6 single-core was
1336 / 1334 / 1333 / 1325 — a <1% spread. Benchmarks are a property of the SoC; keying the
catalog on chipset is correct and de-duplicates data entry.

### Caveats now baked into §5.1
- GSMArena's 3DMark is **Wild Life Extreme**, not standard Wild Life (much lower numbers) →
  reference bounds updated.
- AnTuTu is **v10 or v11** → standardize on v10; v11 runs higher and must not be mixed.
- Scores carry chipset-variant suffixes ("Dimensity 8500 Extreme", "8500 Ultra") — treat as
  distinct chipset rows; do not collapse.

### Parser recipe (implemented)
For each `benchmark-widget`: read `h3` title → for each `div.phones` (index = tab) → for each
`span.value`, walk up to `.result`/`.flex-row` for name + chipset + memory. Emit
`{benchmark, tab, device, chipset, memory, score}`. Pure function, unit-testable against a saved
HTML fixture; wire to a thin fetcher in M6. Net: `GsmArenaPerfSource` is a low-risk HTML scraper,
same class as the battery source (Appendix B) and unlike the fragile Shopee source (Appendix A).

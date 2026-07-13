---
name: shopee-marketplace
description: Query and parse Shopee (Indonesia / shopee.co.id) product search data via the internal search_items JSON endpoint. Use whenever fetching, filtering, paginating, or parsing Shopee listings — keyword search, price-range filtering, Shopee Mall / official-store filtering, seller-trust extraction, or decoding Shopee's item_basic fields and micro-unit prices. Trigger this for any Shopee scraping, Shopee HAR analysis, building a Shopee price/listing tracker, or when the user mentions Shopee search, search_items, fe_filter_options, Shopee Mall, or Shopee anti-bot/token issues — even if they don't name the endpoint. Note — Shopee has no official public search API; this covers the reverse-engineered internal endpoint and its constraints.
---

# Shopee Marketplace — Search & Parse (Indonesia)

Shopee exposes **no official public keyword-search API** (the Open/Partner API is seller-side).
The clean, ToS-safe path for product feeds is the **Shopee Affiliate** program (Involve Asia /
Accesstrade) — prefer it where it covers your need. This skill documents the **internal**
`search_items` endpoint the Shopee web app itself calls, for cases where you must read live search
results. Treat it as reverse-engineered and breakable, and respect Shopee's ToS and rate limits.

## Endpoint

```
GET https://shopee.co.id/api/v4/search/search_items
```

Key query params:

| Param | Meaning |
|-------|---------|
| `keyword` | search term (e.g. `android`) |
| `limit` | page size (60 is what the web app uses) |
| `newest` | pagination OFFSET: 0, 60, 120, … (not a page index) |
| `by` / `order` | sort, e.g. `relevancy` / `desc` |
| `page_type`, `scenario`, `source`, `version` | `search`, `PAGE_GLOBAL_SEARCH`, `SRP`, `2` |
| `fe_filter_options` | URL-encoded JSON array of filter groups (Mall + price live here) |

### Filters (`fe_filter_options`)

Mall + price-range are NOT separate params — they go inside `fe_filter_options`:

```json
[
  {"group_name":"SHOP_TYPE","values":["OFFICIAL_MALL"]},
  {"group_name":"PRICE_RANGE","values":["1000000▶◀2000000"]}
]
```

- **Shopee Mall filter** = `SHOP_TYPE=OFFICIAL_MALL`. Drop this group to include ordinary
  (non-Mall) sellers.
- **Price range** = `PRICE_RANGE` with the literal delimiter `▶◀` (U+25B6 U+25C0), **min then max,
  in whole rupiah** (`1000000▶◀2000000` = Rp 1jt–2jt).

## Response

Top level: `total_count`, `nomore` (stop-paging flag), `items[]`. Pages needed =
`ceil(total_count / limit)`. Each `items[i].item_basic` holds ~100+ fields. The field map and the
critical gotchas are in `references/search_items_fields.md` — read it before writing a parser.

The two things that bite people immediately:

- **Prices are micro-units.** Divide by **100000**: `185900000000` = Rp 1,859,000.
- **`price_before_discount` is usually marketing fiction** ("harga coret" strikethrough) — do NOT
  use it as a real price.

## Auth / anti-bot reality (why this is fragile)

`search_items` requests carry signed, device-fingerprinted headers minted by Shopee's anti-bot
SDK: `af-ac-enc-dat`, `af-ac-enc-sz-token`, `sz-token`, `x-sap-ri`, `x-sap-sec`,
`x-sz-sdk-version`, `x-csrftoken`, plus session cookies. These are generated client-side by
obfuscated JavaScript and **expire**.

**Do not try to hand-forge these headers** — it's a losing game across token rotations. The robust
approach is to **drive a real logged-in browser session** (e.g. Playwright with a persisted
profile) so Shopee mints the tokens for you, then read the `search_items` JSON responses off the
page. Keep volume low, cache hard, one burst per keyword; a daily cadence looks nothing like abuse.
This is still ToS-sensitive — the affiliate feed remains the clean path.

## Practical guidance

- Wrap the source behind an interface with a fixture/offline implementation so parsing and
  downstream logic can be tested without hitting Shopee.
- Analyze a saved HAR (`shopee_co_id.*.har`) offline to build and unit-test the parser before ever
  making live calls.
- Never log or share captured cookies/tokens — a Shopee HAR contains a live login session.

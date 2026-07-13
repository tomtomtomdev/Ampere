# Shopee `search_items` → `item_basic` Field Map

Reference for `shopee-marketplace`. Verified from a real shopee.co.id search HAR. The `item_basic`
object on each result carries 100+ fields; these are the ones that matter for listing/price/trust
work. Field availability varies by listing — always code defensively.

## Identity & title

| Field | Meaning |
|-------|---------|
| `itemid` | listing id (with `shopid`, builds the product URL) |
| `shopid` | seller/shop id |
| `name` | listing title (noisy — feed to an entity resolver like `id-android-market`) |
| `brand` | brand string (often blank; a hint, not authoritative) |
| `catid` | category id |

## Variants (RAM/ROM etc.)

| Field | Meaning |
|-------|---------|
| `tier_variations[]` | array of variation axes; `.name` + `.options[]` |

`tier_variations` frequently contains the RAM/ROM directly — but the axis name varies
(`STORAGE`, `PENYIMPANAN`, `Kapasitas`, `RAM`, `Warna`/color) and option formats vary
(`8/256`, `8GB/256GB`, `4/64`). Normalize; do not assume a fixed label or format.

## Price (MICRO-UNITS — divide by 100000)

| Field | Meaning |
|-------|---------|
| `price` | current price ×100000. `185900000000` → Rp 1,859,000 |
| `price_min`, `price_max` | range when variants differ in price (÷100000) |
| `price_before_discount` | strikethrough "harga coret" — usually inflated marketing fiction; do NOT treat as a real anchor |
| `raw_discount` | advertised discount % |

## Mall / trust / seller signals

| Field | Meaning |
|-------|---------|
| `is_official_shop` | **Shopee Mall / official store** (primary Mall signal) |
| `show_official_shop_label` | render-time Mall label (corroborates `is_official_shop`) |
| `is_preferred_plus_seller` | "Star+/Preferred" seller — trust signal |
| `shopee_verified` | verified shop |
| `item_rating.rating_star` | average star rating |
| `item_rating.rating_count[0]` | total number of ratings (index 0 = total) |
| `shop_location` | e.g. "Jakarta Utara" — useful for regional (Jabodetabek) relevance |

Fold rating + Mall + preferred flags into a single `trust_score`. Trust is a filter/column and an
optional soft value penalty — it should NOT enter a device's raw capability score.

## Effective-price components (often sparse)

| Field | Meaning |
|-------|---------|
| `show_free_shipping` | boolean free-shipping badge |
| `free_shipping_info` | free-shipping detail (frequently empty in search payload) |
| `voucher_info` | voucher detail (frequently empty in search payload) |
| `can_use_cod` | cash-on-delivery available |

Shipping/voucher/cashback are largely **absent** from the search payload — they live in item-detail
/ checkout. So an `effective_price` computed from search alone is usually just `list_price`; mark
it `partial` and only fetch item-detail for a shortlist if the extra calls are worth it.

## Popularity / context

| Field | Meaning |
|-------|---------|
| `sold`, `historical_sold`, `global_sold_count` | units sold (popularity) |
| `stock` | remaining stock |
| `liked_count` | wishlist count |

## Condition

There is **no reliable first-class condition (new/used) field** in the search payload. With the
`OFFICIAL_MALL` filter applied, results are effectively new — so the Mall filter is the practical
"new" proxy. For used/marketplace listings, drop the Mall filter and infer condition from `name`
(see the `id-android-market` condition lexicon).

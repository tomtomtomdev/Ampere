---
name: id-android-market
description: Resolve messy Indonesian (Jabodetabek/ID) online marketplace phone listings into canonical brand, model, variant, and condition. Use whenever parsing, normalizing, deduplicating, or matching Android phone listings from Shopee, Tokopedia, Lazada, or similar Indonesian marketplaces — e.g. turning a noisy promo-laden title like "Redmi Note 13 Pro 5G 8/256 NFC Garansi Resmi HP Murah COD" into {brand, model, variant, condition}. Trigger this for phone entity resolution, RAM/ROM variant extraction, Indonesian phone-market slang/noise-token cleaning, new-vs-used condition detection, or building a phone catalog/alias table for the ID market, even if the user does not say "entity resolution" explicitly.
---

# Indonesian Android Phone Market — Entity Resolution

Turn a raw marketplace listing title (usually Indonesian, keyword-stuffed, promo-heavy) into a
clean canonical record. This is the hard, high-leverage step in any ID phone-market tool: scoring,
deduplication, and cross-referencing all depend on resolving the title correctly first.

Target output for every listing:

```
{ brand, model, variant (RAM/ROM + qualifiers), condition, leftover_tokens }
```

Aim for ≥85% auto-resolution on the common price bands before falling back to a human "needs
mapping" queue. Never silently guess a model when the title is genuinely ambiguous — emit low
confidence and queue it.

## Pipeline (apply in order)

1. **Lowercase + strip noise.** Remove promo/marketing/logistics tokens (see
   `references/lexicon.md`). These carry no identity information and only confuse matching.
2. **Detect condition FIRST, before stripping condition words.** Words like `bekas`, `second`,
   `mulus`, `ex-inter` set `condition=used`; `bnib`, `segel`, `baru` suggest `new`. Do this before
   step 1 removes them, or capture condition tokens during the strip. Default `condition=unknown`
   (do NOT assume new — see the pitfalls).
3. **Extract brand + model.** Match against the alias table (`references/brands.md`). Indonesian
   sellers write the same model many ways; the alias table maps them to one canonical model.
4. **Extract variant.** RAM/ROM plus SKU-changing qualifiers (`5G`, `NFC`). Formats vary wildly —
   see the variant rules below.
5. **Fuzzy match** the (brand, model, variant) against your device catalog (rapidfuzz or similar),
   with a learned alias table for the long tail so each manual resolution is remembered.
6. **Whatever is left** goes into `leftover_tokens` for auditing — useful for discovering new noise
   words and new models.

## Variant extraction rules

RAM/ROM is the main variant axis and the format is inconsistent. Normalize everything to
`RAM/ROM` in GB (e.g. `8/256`).

- `8/256`, `8 / 256`, `8+256` → `8/256`
- `8GB/256GB`, `8gb 256gb`, `RAM 8 ROM 256` → `8/256`
- `8/256GB`, `256GB 8GB RAM` (reversed) → detect which number is RAM (smaller, ≤16) vs ROM
  (larger, ≥32) rather than trusting order
- A bare `256GB` with no RAM → ROM known, RAM unknown; keep partial, don't invent RAM
- `5G` and `NFC` are SKU-relevant qualifiers on many models (e.g. `Redmi Note 13 Pro 5G` is a
  different device from the 4G version) — keep them on the model/variant, don't discard as noise
- Colors (`hitam`, `biru`, `midnight black`) are NOT variants for scoring — strip to
  `leftover_tokens`

See `references/lexicon.md` for the full noise-token and condition lexicons, and
`references/brands.md` for the brand + model alias tables. Read both when building or debugging a
resolver; they are the parts most likely to need extension over time.

## Common pitfalls (these cause silent wrong matches)

- **Do not assume `new`.** The mid/low price bands are full of used, refurbished, and ex-inter
  units. Defaulting unknown condition to new makes a used ex-flagship look like a bargain new
  phone. When condition can't be determined, mark `unknown`, not `new`.
- **`garansi resmi` ≠ condition.** It means "official warranty" (a trust/market signal), not new.
  Treat it as a trust token, not a condition.
- **Reversed RAM/ROM.** `256/8` almost always means 256GB ROM + 8GB RAM; decide by magnitude, not
  position.
- **Model families with confusable members.** `Redmi Note 13` vs `13 Pro` vs `13 Pro+` vs `13 Pro
  5G` are four different devices; a fuzzy match that ignores the suffix will collapse them. Weight
  the suffix and 5G/NFC qualifiers heavily.
- **Sub-brands.** POCO and Redmi are Xiaomi sub-brands but must stay distinct models; iQOO vs
  vivo, Infinix/Tecno/itel (all Transsion) likewise. Keep the marketed brand, not the parent.
- **Fuzzy threshold too low** merges distinct models; too high sends everything to manual. Tune on
  a real sample and lean on the alias table for the tail rather than loosening the threshold.

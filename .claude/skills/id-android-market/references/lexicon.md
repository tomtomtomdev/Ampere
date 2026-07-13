# Lexicon — Noise Tokens & Condition Words (Indonesian Marketplace)

Reference for `id-android-market`. These are Indonesian-market-specific and extend over time.

## Noise / promo / logistics tokens (strip to `leftover_tokens`)

These carry no device identity. Strip before matching (but detect condition + trust tokens first).

```
promo, murah, murмеriah, termurah, diskon, cuci gudang, flash sale, big sale, gratis, free,
bonus, cashback, voucher, cod, bayar di tempat, kirim, ongkir, free ongkir, ready, ready stock,
stok, stock, terlaris, best seller, laris, original, ori, 100% ori, asli, amanah, terpercaya,
grosir, distributor, toko, official store, promo spesial, limited, viral, new arrival, hp,
handphone, smartphone, ponsel, gadget, cellular, celuler, unit, fullset, full set, dus, box,
lengkap, komplit
```

Notes:
- `hp`, `handphone`, `smartphone`, `ponsel` are generic "phone" words — strip.
- `original` / `ori` / `asli` are authenticity claims, not identity — strip (or keep as a weak
  trust hint if useful, but never as condition).
- Emoji, star symbols, brackets full of promo text, and repeated punctuation → strip.

## Trust / warranty tokens (NOT condition — capture separately if useful)

```
garansi resmi   → official warranty (trust signal, implies new-ish but NOT proof of new)
garansi toko    → shop warranty
garansi 1 tahun → 1-year warranty
resmi           → official
sein            → Samsung official-warranty slang
tam / ibox      → distributor/authorized-reseller markers
```

Treat these as trust/market metadata, never as `condition`.

## Condition lexicon (detect BEFORE stripping)

New:
```
baru, brand new, bnib (box new in box), segel, segelan, new, belum dibuka, unsealed? (no → sealed)
```

Used / second-hand:
```
bekas, second, seken, 2nd, sc, mulus, like new, likenew, minus (has a defect), normal (working
used), ex, ex-inter, ex inter, inter, garansi habis (warranty expired → used), fullset bekas
```

Refurbished:
```
refurbish, refurbished, refurb, rekondisi, recondition, rekon
```

Rules:
- `ex-inter` / `inter` = ex-international unit (grey market, effectively used) → `condition=used`.
- `minus` flags a known defect — keep condition `used` and note the defect in leftover.
- If both new-ish and used tokens appear (e.g. "bekas seperti baru"), the used token wins →
  `used`.
- No condition token at all → `condition=unknown` (NOT new). In official-store / Mall listings you
  may treat unknown as effectively new, but record it as an assumption, not a fact.

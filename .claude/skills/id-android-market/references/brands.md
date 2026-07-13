# Brand + Model Aliases — Indonesian Android Market

Reference for `id-android-market`. Extend as new models appear. The goal is to map the many ways
Indonesian sellers write a model onto one canonical `brand` + `model` string.

## Brands present in the ID market (canonical → aliases / notes)

- **Xiaomi** — `xiaomi`, `mi`. Sub-brands **Redmi** and **POCO** are marketed separately; keep them
  as their own brand label (a buyer searches "poco x6", not "xiaomi poco x6").
- **Redmi** — `redmi`. Series: Note, Note Pro, Note Pro+, A-series, plain number series.
- **POCO** — `poco`, `poco phone`. Series: X, M, F, C.
- **Samsung** — `samsung`, `sam`, `sein` (slang for official-warranty Samsung). Series: Galaxy
  A0x/A1x/A2x/A3x (budget→mid), M-series, F-series, S-series (flagship, appears used in mid bands).
- **OPPO** — `oppo`. Series: A-series, Reno, Find.
- **vivo** — `vivo`. Series: Y-series, V-series, T-series. **iQOO** is vivo's sub-brand — keep
  distinct.
- **realme** — `realme`, `real me`. Series: C-series (budget), number series, Narzo, GT.
- **Infinix** — `infinix`. Series: Hot, Note, Smart, Zero, GT. (Transsion)
- **Tecno** — `tecno`, `techno` (common misspelling). Series: Spark, Pova, Camon, Phantom.
  (Transsion)
- **itel** — `itel`. Budget entry. (Transsion)
- **Honor** — `honor`. Series: X-series, number series.
- **Nothing** — `nothing`, `nothing phone`. `Phone (2a)`, `(3a)`, etc.
- **ASUS** — `asus`, `rog`, `zenfone`.
- **Motorola** — `motorola`, `moto`. Series: Edge, G-series, E-series.

## Model naming rules

- Canonical form: `<Series> <Number> <Tier> <Radio>` e.g. `Redmi Note 13 Pro 5G`,
  `POCO X6 Pro 5G`, `Galaxy A15 5G`, `Infinix Note 40 Pro`, `realme C67`, `Tecno Spark 20 Pro`.
- Tier tokens that change identity: `Pro`, `Pro+` / `Pro Plus`, `Ultra`, `Max`, `Prime`, `GT`,
  `Turbo`, `Neo`, `Ace`, `FE`, `Lite`.
- Radio/feature tokens that change SKU: `5G`, `4G` (usually implicit), `NFC` (some listings treat
  NFC vs non-NFC as different SKUs).
- Number-only phones (e.g. `Redmi 13C`, `realme C55`) — keep the letter suffix; it's part of the
  model, not a variant.

## Alias examples (raw seller text → canonical model)

```
redmi note 13 pro 5g            → Redmi Note 13 Pro 5G
rn13 pro / rn 13 pro            → Redmi Note 13 Pro          (verify 5G/NFC separately)
poco x6 pro / pocox6pro         → POCO X6 Pro 5G
samsung a15 / sm a155 / a15 5g  → Samsung Galaxy A15 5G
galaxy a05s                     → Samsung Galaxy A05s
infinix note 40 / note40 pro    → Infinix Note 40 Pro
realme c67 / real me c 67       → realme C67
tecno spark 20 / techno spark20 → Tecno Spark 20
itel p55                        → itel P55
```

When a raw token can't be confidently mapped, do NOT force it — return low confidence and route to
the manual "needs mapping" queue, then add the learned mapping back here (or into the runtime alias
table) so it resolves automatically next time.

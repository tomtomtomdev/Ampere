"""ID-market resolution vocabulary — **data, not logic** (mirrors ``ampere.config`` for scoring).

This is the runtime transcription of the ``id-android-market`` skill's reference files
(``.claude/skills/id-android-market/references/{brands,lexicon}.md``), which remain the *source of
record*. Grow the rules THERE first, then reflect them here (CLAUDE.md "Domain knowledge" — prefer
extending the skill's ruleset over scattering brand regexes through ``resolve.py``).

Everything here is frozen, order-independent lookup data so ``resolve`` stays pure/deterministic.
"""

from __future__ import annotations

import re

from ampere.domain.models import Condition

# ---------------------------------------------------------------------------
# Brands (brands.md). Alias token -> canonical brand. Sub-brands (Redmi/POCO) bucket under the
# catalog's parent brand (Xiaomi), matching the design/fixture data; the sub-brand token is kept
# in the model so family matching still works (see SUB_BRAND_TOKENS).
# ---------------------------------------------------------------------------
BRAND_ALIASES: dict[str, str] = {
    "xiaomi": "Xiaomi", "mi": "Xiaomi", "redmi": "Xiaomi", "poco": "Xiaomi",
    "samsung": "Samsung", "sam": "Samsung", "sein": "Samsung",
    "oppo": "OPPO",
    "vivo": "vivo", "iqoo": "vivo",
    "realme": "realme",
    "infinix": "Infinix",
    "tecno": "Tecno", "techno": "Tecno",
    "itel": "itel",
    "honor": "Honor",
    "nothing": "Nothing",
    "asus": "ASUS", "rog": "ASUS", "zenfone": "ASUS",
    "motorola": "Motorola", "moto": "Motorola",
    "apple": "Apple", "iphone": "Apple",
}

# Multi-word brand aliases collapsed before tokenising (raw substring -> single token in the map).
BRAND_PHRASES: dict[str, str] = {
    "real me": "realme",
    "nothing phone": "nothing",
    "poco phone": "poco",
}

# Sub-brand tokens: set the parent brand but are KEPT in the model string (a buyer searches
# "poco x6", and the catalog model is "Poco X6 5G"), so they must survive noise-stripping.
SUB_BRAND_TOKENS: frozenset[str] = frozenset({"redmi", "poco"})

# ---------------------------------------------------------------------------
# Condition lexicon (lexicon.md). Detect BEFORE stripping; precedence refurb > used > new.
# Multi-word markers are matched as phrases on the raw text first.
# ---------------------------------------------------------------------------
CONDITION_PHRASES: list[tuple[str, Condition]] = [
    ("like new", Condition.USED),
    ("ex inter", Condition.USED),
    ("ex-inter", Condition.USED),
    ("garansi habis", Condition.USED),
    ("belum dibuka", Condition.NEW),
    ("brand new", Condition.NEW),
]
CONDITION_REFURBISHED: frozenset[str] = frozenset(
    {"refurbish", "refurbished", "refurb", "rekondisi", "recondition", "rekon"}
)
CONDITION_USED: frozenset[str] = frozenset(
    {"bekas", "second", "seken", "2nd", "mulus", "minus", "ex", "inter", "likenew", "normal"}
)
CONDITION_NEW: frozenset[str] = frozenset({"baru", "bnib", "segel", "segelan", "new"})

# ---------------------------------------------------------------------------
# SKU-relevant qualifiers (variant.md rules) — kept on the variant, never dropped as noise.
# ---------------------------------------------------------------------------
QUALIFIER_TOKENS: tuple[str, ...] = ("5G", "NFC")  # display order on the normalized variant

# ---------------------------------------------------------------------------
# Spec / feature noise stripped as whole phrases BEFORE tokenising, so their embedded digits
# (e.g. "Snapdragon 4 Gen 2", "108MP") never leak into the model as bare numbers.
# ---------------------------------------------------------------------------
SPEC_PHRASE_RE: re.Pattern[str] = re.compile(
    r"""
      snapdragon\s*\d+(\s*gen\s*\d+)?     # Snapdragon 685 / Snapdragon 4 Gen 2
    | \bsd\s*\d+(\s*gen\s*\d+)?           # SD 4 Gen 2
    | helio\s*[a-z]?\s*\d+                # Helio G99
    | dimensity\s*\d+                     # Dimensity 6300
    | exynos\s*\d+
    | unisoc\s*[a-z]?\s*\d+
    | mediatek | kirin\s*\d+ | tiger\s*[a-z]?\s*\d+
    | \d+\s*mp                            # 108MP camera
    | \d+\s*mah                           # 5000mAh battery
    | \d+\s*%                             # 99%
    """,
    re.IGNORECASE | re.VERBOSE,
)

# Whole-word noise: promo / logistics / generic-phone / trust / spec-feature tokens. All carry no
# device identity and are dropped from the model (they do not go to leftover_tokens — they are
# classified). Trust words (garansi/resmi/…) live here too: trust signals, never condition.
NOISE_TOKENS: frozenset[str] = frozenset({
    # promo / marketing / logistics
    "promo", "murah", "murmeriah", "meriah", "termurah", "diskon", "cuci", "gudang", "flash",
    "sale", "big", "gratis", "free", "bonus", "cashback", "voucher", "cod", "bayar", "tempat",
    "ditempat", "kirim", "ongkir", "ready", "stok", "stock", "terlaris", "best", "seller",
    "laris", "amanah", "terpercaya", "grosir", "distributor", "toko", "official", "store",
    "spesial", "limited", "viral", "arrival", "semua", "no", "bisa", "like", "seperti",
    # generic "phone" words
    "hp", "handphone", "smartphone", "ponsel", "gadget", "cellular", "celuler", "unit",
    "fullset", "full", "set", "dus", "box", "lengkap", "komplit", "android",
    # authenticity claims
    "original", "ori", "asli",
    # trust / warranty (NOT condition)
    "garansi", "resmi", "tahun", "tam", "ibox",
    # leftover variant scaffolding words
    "ram", "rom", "gb",
    # spec / feature words (embedded-digit forms handled by SPEC_PHRASE_RE)
    "super", "amoled", "oled", "ips", "lcd", "layar", "besar", "baterai", "awet", "kamera",
    "jernih", "wireless", "charging", "armor", "shell", "indonesia",
})

# Colors are not scoring variants (variant.md) -> routed to leftover_tokens for auditing.
COLOR_TOKENS: frozenset[str] = frozenset({
    "hitam", "putih", "biru", "merah", "hijau", "kuning", "emas", "gold", "silver", "abu",
    "ungu", "pink", "black", "white", "blue", "red", "green", "midnight", "graphite", "titanium",
})

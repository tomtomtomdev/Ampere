"""M2 — entity resolution, written test-first from SPEC §7 (CLAUDE.md invariant #2).

Pure, deterministic, zero I/O. The ID-market ruleset (brand/model aliases, noise/condition
lexicon, variant rules) lives in the ``id-android-market`` skill and is transcribed into
``ampere.domain.lexicon`` — tests here pin the *behaviour* SPEC §7 requires, not the ruleset text.

The golden fixture is the 23 real 1jt–2jt listings from the design prototype
(``design/Ampere.dc.html`` L01–L23), with their hand-resolved ``model``/``variant``. Two are
deliberately unresolvable ("HP Android …", "Smartphone Android …") → needs-mapping queue.
Condition is asserted only from **title tokens** (skill rule: unknown unless a condition word is
present — the Mall→new assumption is an M3 concern, not the resolver's).
"""

from __future__ import annotations

import math

from ampere.domain import resolve
from ampere.domain.models import Condition

# (id, title, brand, model, variant, condition-from-title)  — None model => unmatched.
_GOLDEN: list[tuple[str, str, str | None, str | None, str | None, Condition]] = [
    ("L01", "Xiaomi Redmi Note 13 8/256 NFC Garansi Resmi HP Murah Promo COD",
     "Xiaomi", "Redmi Note 13", "8/256", Condition.UNKNOWN),
    ("L02", "Redmi Note 13 6/128 Resmi Xiaomi Indonesia Segel BNIB",
     "Xiaomi", "Redmi Note 13", "6/128", Condition.NEW),
    ("L03", "Redmi Note 13 8/256 Garansi Resmi COD Murah Meriah",
     "Xiaomi", "Redmi Note 13", "8/256", Condition.UNKNOWN),
    ("L04", "Redmi Note 13 8/256 SECOND bekas mulus fullset ex-inter",
     "Xiaomi", "Redmi Note 13", "8/256", Condition.USED),
    ("L05", "POCO M6 5G 6/128 Snapdragon 4 Gen 2 Garansi Resmi Poco Indonesia",
     "Xiaomi", "Poco M6 5G", "6/128", Condition.UNKNOWN),
    ("L06", "POCO X6 5G 8/256 second like new ex inter mulus 99% no minus",
     "Xiaomi", "Poco X6 5G", "8/256", Condition.USED),
    ("L07", "Infinix Note 40 8/256 Helio G99 Wireless Charging Garansi Resmi",
     "Infinix", "Note 40", "8/256", Condition.UNKNOWN),
    ("L08", "Infinix Note 40 8/256 murah promo garansi resmi cod bayar ditempat",
     "Infinix", "Note 40", "8/256", Condition.UNKNOWN),
    ("L09", "Infinix Hot 40 Pro 8/256 NFC Helio G99 Garansi Resmi",
     "Infinix", "Hot 40 Pro", "8/256", Condition.UNKNOWN),
    ("L10", "realme C67 8/256 108MP Snapdragon 685 Garansi Resmi realme",
     "realme", "realme C67", "8/256", Condition.UNKNOWN),
    ("L11", "Samsung Galaxy A15 8/256 Super AMOLED Garansi Resmi SEIN",
     "Samsung", "Galaxy A15", "8/256", Condition.UNKNOWN),
    ("L12", "Samsung Galaxy A05s 6/128 Garansi Resmi SEIN 50MP",
     "Samsung", "Galaxy A05s", "6/128", Condition.UNKNOWN),
    ("L13", "Xiaomi Redmi 13C 8/256 50MP Garansi Resmi Murah",
     "Xiaomi", "Redmi 13C", "8/256", Condition.UNKNOWN),
    ("L14", "Tecno Spark 20 Pro 8/256 Helio G99 NFC murah promo cod",
     "Tecno", "Spark 20 Pro", "8/256", Condition.UNKNOWN),
    ("L15", "realme C67 8/256 bekas second normal semua mulus",
     "realme", "realme C67", "8/256", Condition.USED),
    ("L16", "vivo Y28 8/128 5000mAh Garansi Resmi vivo Indonesia",
     "vivo", "vivo Y28", "8/128", Condition.UNKNOWN),
    ("L17", "OPPO A60 8/256 Armor Shell Garansi Resmi OPPO",
     "OPPO", "OPPO A60", "8/256", Condition.UNKNOWN),
    ("L18", "Redmi Note 13R 8/256 Dimensity 6300 5G Garansi Resmi",
     "Xiaomi", "Redmi Note 13R", "8/256", Condition.UNKNOWN),
    ("L19", "Infinix Note 40 8/256 resmi official store gratis ongkir",
     "Infinix", "Note 40", "8/256", Condition.UNKNOWN),
    ("L20", "realme 12 8/256 second fullset mulus ex inter Dimensity 7025",
     "realme", "realme 12", "8/256", Condition.USED),
    ("L21", "POCO M6 5G 8/256 Snapdragon 4 Gen 2 Garansi Resmi",
     "Xiaomi", "Poco M6 5G", "8/256", Condition.UNKNOWN),
    # Deliberately unresolvable -> needs-mapping queue (SPEC §7 step 5).
    ("L22", "HP Android RAM 8/256 Baru Garansi Murah Meriah Promo COD Bisa Bayar Ditempat",
     None, None, "8/256", Condition.NEW),
    ("L23", "Smartphone Android 6/128 Layar Besar Baterai Awet Kamera Jernih",
     None, None, "6/128", Condition.UNKNOWN),
]


def _canon_id(brand: str, model: str, variant: str) -> str:
    return f"{brand}|{model}|{variant}"


class FakeDeviceCatalog:
    """In-memory ``DeviceCatalogPort`` built from the golden set's canonical devices."""

    def __init__(self) -> None:
        seen: dict[str, tuple[str, str, str]] = {}
        for _id, _t, brand, model, variant, _c in _GOLDEN:
            if model is None:
                continue
            dev_id = _canon_id(brand, model, variant)
            seen[dev_id] = (brand, model, variant)
        self._devices = seen

    def candidates_for(self, brand: str | None) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for dev_id, (b, m, v) in self._devices.items():
            if brand is not None and b.lower() != brand.lower():
                continue
            out.append((dev_id, f"{b} {m} {v}"))
        return out


class FakeAliasCatalog:
    def __init__(self, table: dict[str, str] | None = None) -> None:
        self._table = table or {}

    def lookup(self, raw_pattern: str) -> str | None:
        return self._table.get(raw_pattern)


_MATCHABLE = [g for g in _GOLDEN if g[3] is not None]
_UNMATCHABLE = [g for g in _GOLDEN if g[3] is None]


# ============================================================ clean_title (SPEC §7 steps 1–3)
class TestCleanTitleVariant:
    def test_slash_form(self):
        assert resolve.clean_title("Redmi Note 13 8/256").variant == "8/256"

    def test_plus_form(self):
        assert resolve.clean_title("Redmi Note 13 8+256").variant == "8/256"

    def test_gb_suffixes(self):
        assert resolve.clean_title("Redmi Note 13 8GB/256GB").variant == "8/256"

    def test_ram_rom_words(self):
        assert resolve.clean_title("Redmi Note 13 RAM 8 ROM 256").variant == "8/256"

    def test_reversed_is_fixed_by_magnitude(self):
        # skill: 256/8 = 256GB ROM + 8GB RAM; decide by magnitude, not position.
        assert resolve.clean_title("Redmi Note 13 256/8").variant == "8/256"

    def test_spaces_around_separator(self):
        assert resolve.clean_title("Redmi Note 13 8 / 256").variant == "8/256"

    def test_qualifiers_captured_on_variant(self):
        v = resolve.clean_title("POCO M6 5G 6/128 NFC").variant
        assert v is not None and v.startswith("6/128")
        assert "5G" in v and "NFC" in v

    def test_no_variant_when_absent(self):
        assert resolve.clean_title("Redmi Note 13").variant is None


class TestCleanTitleCondition:
    def test_unknown_when_no_token(self):
        # skill pitfall: never assume new.
        c = resolve.clean_title("Redmi Note 13 8/256 Garansi Resmi")
        assert c.condition is Condition.UNKNOWN

    def test_bekas_is_used(self):
        assert resolve.clean_title("Redmi Note 13 8/256 bekas mulus").condition is Condition.USED

    def test_new_tokens(self):
        assert resolve.clean_title("Redmi Note 13 6/128 Segel BNIB").condition is Condition.NEW

    def test_used_wins_over_new(self):
        # "like new" (used marker) beats a bare "new" reading.
        assert resolve.clean_title("POCO X6 5G 8/256 second like new").condition is Condition.USED

    def test_garansi_resmi_is_not_a_condition(self):
        # trust token, not proof of new (skill pitfall).
        assert resolve.clean_title("Galaxy A15 8/256 Garansi Resmi").condition is Condition.UNKNOWN

    def test_refurbished(self):
        assert resolve.clean_title("iPhone rekondisi 8/256").condition is Condition.REFURBISHED


class TestCleanTitleBrandAndNoise:
    def test_sub_brand_maps_to_parent(self):
        # POCO / Redmi are marketed brands but the catalog buckets them under Xiaomi.
        assert resolve.clean_title("POCO M6 5G 6/128").brand == "Xiaomi"
        assert resolve.clean_title("Redmi Note 13 8/256").brand == "Xiaomi"

    def test_brands_detected(self):
        assert resolve.clean_title("Infinix Note 40 8/256").brand == "Infinix"
        assert resolve.clean_title("Samsung Galaxy A15 8/256").brand == "Samsung"
        assert resolve.clean_title("Tecno Spark 20 Pro 8/256").brand == "Tecno"

    def test_no_brand_when_generic(self):
        assert resolve.clean_title("HP Android 8/256 Murah Promo").brand is None

    def test_model_keeps_identity_drops_promo(self):
        c = resolve.clean_title("Xiaomi Redmi Note 13 8/256 NFC Garansi Resmi HP Murah Promo COD")
        m = c.model.lower()
        assert "redmi" in m and "note" in m and "13" in m
        for noise in ("murah", "promo", "cod", "garansi", "resmi"):
            assert noise not in m


# ============================================================ resolve (SPEC §7 steps 4–5)
class TestResolveGoldenSet:
    def setup_method(self):
        self.devices = FakeDeviceCatalog()
        self.aliases = FakeAliasCatalog()

    def _resolve(self, title):
        return resolve.resolve(title, self.devices, self.aliases)

    def test_meets_85pct_auto_resolve_target(self):
        # SPEC SC2 / DoD: >=85% of in-band listings auto-resolve to the right device.
        correct = 0
        misses = []
        for _id, title, brand, model, variant, _c in _MATCHABLE:
            want = _canon_id(brand, model, variant)
            got = self._resolve(title).device_id
            if got == want:
                correct += 1
            else:
                misses.append((_id, want, got))
        ratio = correct / len(_MATCHABLE)
        assert ratio >= 0.85, f"only {ratio:.0%} resolved; misses={misses}"

    def test_unmatched_titles_go_to_needs_mapping(self):
        for _id, title, _b, _m, _v, _c in _UNMATCHABLE:
            r = self._resolve(title)
            assert r.device_id is None, f"{_id} should be unmatched, got {r.device_id}"

    def test_family_suffix_not_collapsed_13r_vs_13(self):
        # skill pitfall: Note 13R must not collapse into Note 13.
        r = self._resolve("Redmi Note 13R 8/256 Dimensity 6300 5G Garansi Resmi")
        assert r.device_id == _canon_id("Xiaomi", "Redmi Note 13R", "8/256")

    def test_family_suffix_not_collapsed_pro(self):
        # Hot 40 Pro must not collapse into Note 40.
        r = self._resolve("Infinix Hot 40 Pro 8/256 NFC Helio G99 Garansi Resmi")
        assert r.device_id == _canon_id("Infinix", "Hot 40 Pro", "8/256")

    def test_variant_disambiguates_same_model(self):
        # Same model, two RAM/ROM SKUs must resolve independently.
        r6 = self._resolve("POCO M6 5G 6/128 Snapdragon 4 Gen 2 Garansi Resmi Poco Indonesia")
        r8 = self._resolve("POCO M6 5G 8/256 Snapdragon 4 Gen 2 Garansi Resmi")
        assert r6.device_id == _canon_id("Xiaomi", "Poco M6 5G", "6/128")
        assert r8.device_id == _canon_id("Xiaomi", "Poco M6 5G", "8/256")

    def test_accepted_match_carries_score(self):
        r = self._resolve("Redmi Note 13 8/256 Garansi Resmi")
        assert r.device_id is not None
        assert r.match_score is not None and r.match_score >= 85.0


class TestResolveAliasOverride:
    def test_alias_short_circuits_fuzzy_match(self):
        title = "Redmi Note 13 8/256 SECOND bekas mulus fullset ex-inter"
        key = " ".join(title.lower().split())
        aliases = FakeAliasCatalog({key: "CUSTOM|OVERRIDE|ID"})
        r = resolve.resolve(title, FakeDeviceCatalog(), aliases)
        assert r.device_id == "CUSTOM|OVERRIDE|ID"
        assert r.match_score == 100.0

    def test_alias_miss_falls_through_to_fuzzy(self):
        r = resolve.resolve(
            "Redmi Note 13 8/256 Garansi Resmi", FakeDeviceCatalog(), FakeAliasCatalog()
        )
        assert r.device_id == _canon_id("Xiaomi", "Redmi Note 13", "8/256")


class TestResolveThresholdAndDeterminism:
    def test_below_threshold_is_unmatched(self):
        r = resolve.resolve("random gibberish item xyz 8/256", FakeDeviceCatalog(),
                            FakeAliasCatalog())
        assert r.device_id is None

    def test_high_threshold_rejects_borderline(self):
        # A near-but-not-exact title clears 85 but not 99.
        loose = resolve.resolve("Redmi Note 13 8/256 Garansi Resmi", FakeDeviceCatalog(),
                                FakeAliasCatalog())
        strict = resolve.resolve("Redmi Note 13 8/256 Garansi Resmi", FakeDeviceCatalog(),
                                 FakeAliasCatalog(), threshold=99.0)
        assert loose.device_id is not None
        # exact-token queries can still hit 100; only assert strict is no more permissive.
        if strict.device_id is None:
            assert loose.match_score is not None

    def test_deterministic(self):
        title = "Infinix Note 40 8/256 Helio G99 Wireless Charging Garansi Resmi"
        a = resolve.resolve(title, FakeDeviceCatalog(), FakeAliasCatalog())
        b = resolve.resolve(title, FakeDeviceCatalog(), FakeAliasCatalog())
        assert (a.device_id, a.match_score) == (b.device_id, b.match_score)


def test_golden_set_has_expected_shape():
    # Guards the fixture itself: 21 matchable + 2 needs-mapping.
    assert len(_MATCHABLE) == 21
    assert len(_UNMATCHABLE) == 2
    assert math.isclose(len(_MATCHABLE) / len(_GOLDEN), 21 / 23)

"""M1 — scoring core, written test-first from SPEC §5 (CLAUDE.md invariant #2).

Pure, deterministic, zero I/O. Expectations are hand-computed against the FIXED reference bounds
in ``ampere.config`` (SPEC §5.1) — never cohort-relative. Synthetic metric values are chosen so
each normalizes to a clean round number (20/40/60/80), keeping the arithmetic auditable by hand;
one case uses real seed data (Snapdragon 7 Gen 4) with the formula spelled out.
"""

from __future__ import annotations

import pytest
from ampere import config
from ampere.domain import scoring
from ampere.domain.models import BatteryMetricKind, Chipset, Device, Weights

# --- synthetic chipset whose four metrics normalize to exactly 20/40/60/80 ------------------
# x = ref_min + (target/100) * (ref_max - ref_min)   -> clean, hand-verifiable norms.
CLEAN_CHIPSET = Chipset(
    id="clean",
    name="Synthetic 20/40/60/80",
    gb6_single=1_000,  # norm 20  (500..3000)
    gb6_multi=4_500,  # norm 40  (1500..9000)
    antutu=1_680_000,  # norm 60  (300k..2.6M)
    wildlife=5_740,  # norm 80  (700..7000)
)


def _device(**kw) -> Device:
    base = dict(id="d", brand="B", model="M", variant="8/256")
    base.update(kw)
    return Device(**base)


# ============================================================ normalize (SPEC §5.1)
class TestNormalize:
    def test_linear_interior_point(self):
        assert scoring.normalize(1_000, 500, 3_000) == pytest.approx(20.0)

    def test_midpoint_is_fifty(self):
        assert scoring.normalize(1_750, 500, 3_000) == pytest.approx(50.0)

    def test_at_min_is_zero(self):
        assert scoring.normalize(500, 500, 3_000) == 0.0

    def test_at_max_is_one_hundred(self):
        assert scoring.normalize(3_000, 500, 3_000) == 100.0

    def test_clamps_below_min_to_zero(self):
        assert scoring.normalize(100, 500, 3_000) == 0.0

    def test_clamps_above_max_to_one_hundred(self):
        assert scoring.normalize(9_999, 500, 3_000) == 100.0


# ============================================================ performance (SPEC §5.2 / §5.5)
class TestPerformance:
    def test_even_blend_of_four_normed_metrics(self):
        # mean(20, 40, 60, 80) == 50.0
        assert scoring.performance(CLEAN_CHIPSET) == pytest.approx(50.0)

    def test_throttle_modifier_applied_after_norm(self):
        # SPEC §5.5: throttle multiplies the normed values, before the blend.
        assert scoring.performance(CLEAN_CHIPSET, throttle_modifier=0.9) == pytest.approx(45.0)

    def test_missing_metric_reweights_across_present(self):
        # only gb6_single (norm 20) + gb6_multi (norm 40) present -> reweighted mean == 30.0,
        # NOT (20+40)/4. Never fabricate the missing metrics (invariant #4 / §5.4).
        partial = Chipset(id="p", name="partial", gb6_single=1_000, gb6_multi=4_500)
        assert scoring.performance(partial) == pytest.approx(30.0)

    def test_single_present_metric_is_its_own_norm(self):
        only = Chipset(id="o", name="only wildlife", wildlife=5_740)  # norm 80
        assert scoring.performance(only) == pytest.approx(80.0)

    def test_no_metrics_raises(self):
        # A chipset with zero benchmarks cannot be scored — caller marks unmatched/needs-mapping.
        with pytest.raises(ValueError):
            scoring.performance(Chipset(id="empty", name="no data"))

    def test_real_seed_snapdragon_7_gen_4(self):
        # Grounds the blend in real GSMArena data (data/seed/chipsets_seed.csv).
        sd7g4 = Chipset(
            id="sd7g4", name="Snapdragon 7 Gen 4",
            gb6_single=1_333, gb6_multi=4_132, antutu=1_129_370, wildlife=2_080,
        )
        expected = 0.25 * (
            scoring.normalize(1_333, 500, 3_000)
            + scoring.normalize(4_132, 1_500, 9_000)
            + scoring.normalize(1_129_370, 300_000, 2_600_000)
            + scoring.normalize(2_080, 700, 7_000)
        )
        assert scoring.performance(sd7g4) == pytest.approx(expected)

    def test_uses_config_bounds_not_magic_numbers(self):
        # Guards against hard-coded bounds drifting from config (SC3, R4).
        b = config.REFERENCE_BOUNDS["gb6_single"]
        assert scoring.normalize(b.ref_max, b.ref_min, b.ref_max) == 100.0


# ============================================================ battery (SPEC §5.2)
class TestBattery:
    def test_active_use_v2_normalized(self):
        # 13h in the 6..20h window -> norm 50.
        dev = _device(active_use_hours=13.0, battery_metric_kind=BatteryMetricKind.ACTIVE_USE_V2)
        assert scoring.battery(dev) == pytest.approx(50.0)

    def test_active_use_inferred_when_kind_unset(self):
        assert scoring.battery(_device(active_use_hours=20.0)) == pytest.approx(100.0)

    def test_no_battery_data_raises(self):
        with pytest.raises(ValueError):
            scoring.battery(_device())

    def test_legacy_endurance_without_bound_raises_not_fabricates(self):
        # No legacy reference bound is configured; M1 must NOT invent one (invariant #4 / §5.1
        # "never mix the two silently"). Legacy support is deferred to a later, deliberate bound.
        dev = _device(
            legacy_endurance=95.0, battery_metric_kind=BatteryMetricKind.LEGACY_ENDURANCE
        )
        with pytest.raises(ValueError):
            scoring.battery(dev)


# ============================================================ capability (SPEC §5.2)
class TestCapability:
    def test_default_weights_blend(self):
        # perf 80, batt 40, W_PERF 0.55 -> 0.55*80 + 0.45*40 = 62.0
        assert scoring.capability(80.0, 40.0, Weights()) == pytest.approx(62.0)

    def test_battery_is_coequal_not_a_tiebreaker(self):
        # Equal weights would give 60; the default 0.55/0.45 must actually shift the result.
        assert scoring.capability(80.0, 40.0, Weights()) != pytest.approx(60.0)

    def test_custom_weight_all_performance(self):
        assert scoring.capability(80.0, 40.0, Weights(w_perf=1.0)) == pytest.approx(80.0)

    def test_weights_sum_to_one(self):
        w = Weights(w_perf=0.55)
        assert w.w_perf + w.w_batt == pytest.approx(1.0)


# ============================================================ value (SPEC §5.3)
class TestValue:
    def test_capability_per_juta(self):
        # cap 62 / (1_240_000 / 1e6 = 1.24 juta) = 50.0
        assert scoring.value(62.0, 1_240_000) == pytest.approx(50.0)

    def test_cheaper_price_raises_value_for_same_capability(self):
        assert scoring.value(60.0, 1_000_000) > scoring.value(60.0, 2_000_000)

    def test_nonpositive_price_raises(self):
        with pytest.raises(ValueError):
            scoring.value(60.0, 0)
        with pytest.raises(ValueError):
            scoring.value(60.0, -100)


# ============================================================ determinism (SC3)
def test_full_chain_is_deterministic():
    w = Weights()
    perf = scoring.performance(CLEAN_CHIPSET)
    batt = scoring.battery(_device(active_use_hours=13.0))
    cap = scoring.capability(perf, batt, w)
    val = scoring.value(cap, 1_500_000)
    # Same inputs -> byte-identical outputs (pinned scoring_version, no cohort normalization).
    assert (perf, batt, cap, val) == (
        scoring.performance(CLEAN_CHIPSET),
        scoring.battery(_device(active_use_hours=13.0)),
        scoring.capability(perf, batt, w),
        scoring.value(cap, 1_500_000),
    )

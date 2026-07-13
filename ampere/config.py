"""Scoring configuration — fixed, versioned reference bounds and default weights.

These are **data**, not logic (SPEC §5.1): benchmarks are normalized against FIXED reference
bounds, never against the daily cohort. Bounds are versioned by ``SCORING_VERSION``; changing a
bound MUST bump the version (SC3 determinism, R4 score-drift). The scoring functions in
``ampere.domain.scoring`` consume these constants — they are defined here so the domain layer has
no hard-coded magic numbers to drift.
"""

from __future__ import annotations

from typing import NamedTuple

# Bump whenever any reference bound or default weight below changes (SPEC §5.1, SC3).
SCORING_VERSION = "v2.1.0"


class Bound(NamedTuple):
    """A fixed [min, max] normalization window for one raw metric."""

    ref_min: float
    ref_max: float


# Reference bounds per SPEC §5.1 (corrected from HAR Appendix C: Wild Life *Extreme*, AnTuTu v10).
REFERENCE_BOUNDS: dict[str, Bound] = {
    "gb6_single": Bound(500, 3000),
    "gb6_multi": Bound(1500, 9000),
    "antutu": Bound(300_000, 2_600_000),  # AnTuTu v10 total — do NOT mix with v11.
    "wildlife": Bound(700, 7000),  # 3DMark Wild Life Extreme (Highest).
    "active_use_hours": Bound(6.0, 20.0),  # GSMArena Active Use Score (v2), in hours.
}

# Even all-round performance blend (SPEC §5.2). Sum == 1.0. UI-tunable per-metric later.
PERFORMANCE_WEIGHTS: dict[str, float] = {
    "gb6_single": 0.25,
    "gb6_multi": 0.25,
    "antutu": 0.25,
    "wildlife": 0.25,
}

# Capability = W_PERF*performance + W_BATT*battery. Battery is a CO-EQUAL pillar (SPEC §5.2).
DEFAULT_W_PERF = 0.55
DEFAULT_W_BATT = 0.45  # == 1 - DEFAULT_W_PERF; both exposed as UI sliders.

# Default query (SPEC G1). IDR, whole rupiah.
DEFAULT_KEYWORD = "android"
DEFAULT_PRICE_MIN = 1_000_000
DEFAULT_PRICE_MAX = 2_000_000

# Optional bonuses/penalties — OFF by default so the core score stays benchmark-pure
# (SPEC §11.1 longevity bonus, §5.6 trust penalty).
LONGEVITY_BONUS_ENABLED = False
LONGEVITY_OS_YEARS_BOUND = Bound(0, 5)
TRUST_PENALTY_ENABLED = False
TRUST_PENALTY_FACTOR = 0.85  # applied to value when !is_mall and seller_rating < 4.5
TRUST_PENALTY_RATING_THRESHOLD = 4.5

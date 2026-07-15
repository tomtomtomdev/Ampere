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
# (SPEC §11.1 longevity bonus, §5.6 trust penalty). Both are UI-tunable per request (like weights):
# defaults-off means the persisted scores are unchanged, so SCORING_VERSION stays v2.1.0 (SC3).
LONGEVITY_BONUS_ENABLED = False
LONGEVITY_OS_YEARS_BOUND = Bound(0, 5)
LONGEVITY_BONUS_MAX = 5.0  # max capability points added at full OS-update-years support (§11.1)
TRUST_PENALTY_ENABLED = False
TRUST_PENALTY_FACTOR = 0.85  # applied to value when !is_mall and seller_rating < 4.5
TRUST_PENALTY_RATING_THRESHOLD = 4.5

# Trust-score composition (SPEC §5.6) — a 0–100 seller-trust column + filter, NOT part of
# capability. v1 heuristic; weights are data (tunable). Only affirmatively-present signals count
# (a missing rating / not-Mall / non-Star is dropped, never scored as a fabricated 0 — invariant
# #4); the present components' weights renormalize to sum 1. None when there is no signal at all.
TRUST_WEIGHTS: dict[str, float] = {"rating": 0.5, "reviews": 0.2, "mall": 0.2, "star": 0.1}
TRUST_RATING_BOUND = Bound(4.0, 5.0)  # ID ratings cluster 4.5–5.0; <4.0 reads as a red flag
# log10(review_count+1): 0 → ~10k reviews = full confidence.
TRUST_REVIEWS_LOG_BOUND = Bound(0.0, 4.0)

# Daily push notification (SPEC §11.2). OFF by default: no channel is pushed unless the composition
# root wires a Notifier (env AMPERE_NOTIFY). This only bounds how many frontier points a push lists.
NOTIFY_FRONTIER_LIMIT = 5

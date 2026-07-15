"""Software-update longevity bonus (SPEC §11.1). PURE, deterministic, zero I/O.

Years of guaranteed OS + security updates are "arguably the single field that most separates cheap
from good value" (§11.1). This folds promised OS-update years into a small **additive** capability
bonus, scaled 0..``LONGEVITY_BONUS_MAX`` over the configured OS-years window. It is OFF by default
at the call sites (§11.1: the core score stays benchmark-pure); unknown longevity contributes 0,
never a fabricated value (invariant #4). Bounds/max are versioned data in ``ampere.config``.
"""

from __future__ import annotations

from ampere.config import LONGEVITY_BONUS_MAX, LONGEVITY_OS_YEARS_BOUND
from ampere.domain.scoring import normalize


def longevity_bonus(os_updates_years: int | None) -> float:
    """Capability points for ``os_updates_years`` of updates — 0..``LONGEVITY_BONUS_MAX``.

    ``None`` (unknown longevity) → ``0.0`` (never fabricated — invariant #4). The bonus rises
    linearly with promised years and saturates at ``LONGEVITY_BONUS_MAX`` once years reach the top
    of ``LONGEVITY_OS_YEARS_BOUND`` (clamped above it — a 7-year pledge never out-scores the
    window).
    """
    if os_updates_years is None:
        return 0.0
    lo, hi = LONGEVITY_OS_YEARS_BOUND.ref_min, LONGEVITY_OS_YEARS_BOUND.ref_max
    return LONGEVITY_BONUS_MAX * normalize(os_updates_years, lo, hi) / 100.0

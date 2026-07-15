"""M7 — software-update longevity bonus (SPEC §11.1), test-first.

A small additive capability bonus from promised OS-update years — "arguably the single field that
most separates cheap from good value." Off by default (§11.1: core score stays benchmark-pure); when
enabled it adds up to ``LONGEVITY_BONUS_MAX`` points, scaled over the configured OS-years window.
Unknown longevity contributes 0 (never fabricated — invariant #4).
"""

from __future__ import annotations

from ampere.config import LONGEVITY_BONUS_MAX, LONGEVITY_OS_YEARS_BOUND
from ampere.domain.longevity import longevity_bonus


class TestLongevityBonus:
    def test_none_is_zero(self):
        assert longevity_bonus(None) == 0.0

    def test_zero_years_is_zero(self):
        assert longevity_bonus(0) == 0.0

    def test_full_years_is_max_bonus(self):
        assert longevity_bonus(int(LONGEVITY_OS_YEARS_BOUND.ref_max)) == LONGEVITY_BONUS_MAX

    def test_monotonic(self):
        assert longevity_bonus(2) < longevity_bonus(4)

    def test_clamped_above_the_bound(self):
        assert longevity_bonus(99) == LONGEVITY_BONUS_MAX

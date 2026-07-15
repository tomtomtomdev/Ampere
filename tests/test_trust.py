"""M7 — trust-score composition (SPEC §5.6) + the optional value penalty, test-first.

`trust_score` folds seller rating / review count / Mall / Star into a 0–100 column (NOT capability).
It re-weights over affirmatively-present signals — a missing rating or a non-Mall/non-Star seller is
dropped, never scored as a fabricated 0 (invariant #4) — and is None only when there is no signal at
all. `trust_value_factor` is the soft value penalty for low-trust non-Mall listings (§5.6), off by
default at the call sites.
"""

from __future__ import annotations

from ampere.config import TRUST_PENALTY_FACTOR
from ampere.domain.trust import trust_score, trust_value_factor


class TestTrustScore:
    def test_high_rating_many_reviews_mall_star_scores_high(self):
        t = trust_score(seller_rating=4.9, seller_review_count=5000, is_mall=True,
                        is_star_seller=True)
        assert t is not None and t >= 90

    def test_low_rating_few_reviews_non_mall_scores_low(self):
        t = trust_score(seller_rating=4.1, seller_review_count=8, is_mall=False,
                        is_star_seller=False)
        assert t is not None and t < 35

    def test_mall_only_with_no_rating_is_trusted(self):
        # Mall is itself the strongest trust signal in the ID market; a Mall store with no shown
        # rating should still read as trustworthy, not None.
        t = trust_score(seller_rating=None, seller_review_count=None, is_mall=True,
                        is_star_seller=False)
        assert t is not None and t >= 90

    def test_no_signal_at_all_is_none(self):
        # Not Mall, not Star, no rating, no reviews -> genuinely no information -> None (not 0).
        assert trust_score(seller_rating=None, seller_review_count=None, is_mall=False,
                           is_star_seller=False) is None

    def test_missing_rating_does_not_drag_score_down_vs_present_low_rating(self):
        # Dropping a missing rating (re-weight) must score higher than an actually-low rating.
        no_rating = trust_score(seller_rating=None, seller_review_count=200, is_mall=True,
                                is_star_seller=False)
        low_rating = trust_score(seller_rating=4.0, seller_review_count=200, is_mall=True,
                                 is_star_seller=False)
        assert no_rating > low_rating

    def test_bounded_0_100(self):
        hi = trust_score(seller_rating=5.0, seller_review_count=10_000_000, is_mall=True,
                         is_star_seller=True)
        lo = trust_score(seller_rating=0.0, seller_review_count=0, is_mall=False,
                         is_star_seller=False)
        assert 0.0 <= lo <= hi <= 100.0

    def test_deterministic(self):
        args = dict(seller_rating=4.7, seller_review_count=350, is_mall=False, is_star_seller=True)
        assert trust_score(**args) == trust_score(**args)


class TestTrustValueFactor:
    def test_penalizes_low_rated_non_mall(self):
        assert trust_value_factor(is_mall=False, seller_rating=4.2) == TRUST_PENALTY_FACTOR

    def test_no_penalty_for_mall(self):
        assert trust_value_factor(is_mall=True, seller_rating=3.0) == 1.0

    def test_no_penalty_for_high_rating(self):
        assert trust_value_factor(is_mall=False, seller_rating=4.8) == 1.0

    def test_no_penalty_when_rating_unknown(self):
        # Can't assess trust with no rating -> don't penalize (don't invent risk — invariant #4).
        assert trust_value_factor(is_mall=False, seller_rating=None) == 1.0

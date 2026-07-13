"""M1 — Pareto frontier, written test-first from SPEC §5.3 (CLAUDE.md invariant #2).

Adversarial cases: empty, single point, ties/duplicate coordinates, all-dominated-but-one, and the
per-condition-vs-blended distinction that stops a used ex-flagship from silently dominating every
new budget phone. Pure, deterministic, zero I/O.
"""

from __future__ import annotations

from ampere.domain.frontier import pareto_frontier
from ampere.domain.models import Candidate, Condition


def _c(listing_id: str, eff: int, cap: float, cond: Condition = Condition.NEW) -> Candidate:
    return Candidate(
        listing_id=listing_id, model="M", variant="8/256",
        condition=cond, effective_price=eff, capability=cap,
    )


class TestDegenerate:
    def test_empty_yields_empty(self):
        assert pareto_frontier([]) == set()

    def test_single_point_is_always_on_frontier(self):
        assert pareto_frontier([_c("A", 1_500_000, 60.0)]) == {"A"}


class TestDomination:
    def test_dominated_points_excluded_frontier_kept(self):
        cands = [
            _c("A", 1_000_000, 50.0),  # cheap + decent  -> frontier
            _c("B", 1_500_000, 80.0),  # priciest + best -> frontier
            _c("C", 1_200_000, 40.0),  # A is cheaper AND higher-cap -> dominated
            _c("D", 1_800_000, 30.0),  # dominated by both A and B
        ]
        assert pareto_frontier(cands) == {"A", "B"}

    def test_equal_price_lower_capability_is_dominated(self):
        cands = [_c("A", 1_000_000, 70.0), _c("B", 1_000_000, 50.0)]
        # B: same price as A but strictly lower capability -> dominated.
        assert pareto_frontier(cands) == {"A"}

    def test_equal_capability_higher_price_is_dominated(self):
        cands = [_c("A", 1_000_000, 60.0), _c("B", 1_400_000, 60.0)]
        # B: same capability as A but strictly more expensive -> dominated.
        assert pareto_frontier(cands) == {"A"}


class TestTiesAndDuplicates:
    def test_identical_coordinates_both_survive(self):
        # Neither dominates the other (domination requires strictly-better on >=1 axis, §5.3),
        # so tied points both stay on the frontier.
        cands = [_c("A", 1_000_000, 50.0), _c("B", 1_000_000, 50.0)]
        assert pareto_frontier(cands) == {"A", "B"}

    def test_tie_on_the_frontier_alongside_a_distinct_winner(self):
        cands = [
            _c("A", 1_000_000, 50.0),
            _c("B", 1_000_000, 50.0),  # tie with A
            _c("C", 1_500_000, 90.0),  # distinct frontier point
            _c("D", 1_600_000, 40.0),  # dominated by A/B
        ]
        assert pareto_frontier(cands) == {"A", "B", "C"}


class TestConditionClasses:
    def test_default_is_per_condition_used_does_not_dominate_new(self):
        # A used phone that is cheaper AND higher-capability must NOT knock a new phone off the
        # frontier by default — they compete within their own condition class (§5.3, §5.6).
        cands = [
            _c("NEW", 1_500_000, 60.0, Condition.NEW),
            _c("USED", 1_200_000, 80.0, Condition.USED),  # dominates NEW on raw axes
        ]
        assert pareto_frontier(cands) == {"NEW", "USED"}

    def test_blended_true_unions_conditions_and_used_dominates(self):
        cands = [
            _c("NEW", 1_500_000, 60.0, Condition.NEW),
            _c("USED", 1_200_000, 80.0, Condition.USED),
        ]
        assert pareto_frontier(cands, blended=True) == {"USED"}

    def test_within_condition_domination_still_applies(self):
        cands = [
            _c("N1", 1_000_000, 50.0, Condition.NEW),
            _c("N2", 1_200_000, 40.0, Condition.NEW),  # dominated by N1
            _c("U1", 1_100_000, 70.0, Condition.USED),
        ]
        assert pareto_frontier(cands) == {"N1", "U1"}

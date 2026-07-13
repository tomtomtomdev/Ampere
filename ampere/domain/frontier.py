"""Pareto frontier — SPEC §5.3. PURE, deterministic, zero I/O.

STATUS: M1 stub. TDD first (CLAUDE.md invariant #2), with adversarial cases: ties, single point,
all-dominated, duplicates. Reference impl: ``frontierSet()`` in ``design/Ampere.dc.html``.
"""

from __future__ import annotations

from collections.abc import Iterable

from ampere.domain.models import Candidate


def pareto_frontier(candidates: Iterable[Candidate], *, blended: bool = False) -> set[str]:
    """Return the set of ``listing_id`` on the non-dominated frontier.

    A candidate is *dominated* if another exists with ``effective_price <=`` AND
    ``capability >=`` and is strictly better on at least one axis (SPEC §5.3). Tied points
    (identical price and capability) therefore both survive — neither strictly beats the other.

    By default the frontier is computed **within a condition class** (new vs new, used vs used)
    so a used ex-flagship can't silently dominate every new budget phone; ``blended=True`` unions
    all conditions into a single frontier.
    """
    cands = list(candidates)

    if blended:
        groups: list[list[Candidate]] = [cands]
    else:
        by_condition: dict[str, list[Candidate]] = {}
        for c in cands:
            by_condition.setdefault(c.condition, []).append(c)
        groups = list(by_condition.values())

    frontier: set[str] = set()
    for group in groups:
        for r in group:
            dominated = any(
                o is not r
                and o.effective_price <= r.effective_price
                and o.capability >= r.capability
                and (o.effective_price < r.effective_price or o.capability > r.capability)
                for o in group
            )
            if not dominated:
                frontier.add(r.listing_id)
    return frontier

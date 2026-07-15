"""Seller-trust composition (SPEC §5.6). PURE, deterministic, zero I/O.

Trust does **not** enter capability (§5.6) — it is a 0–100 column + filter, and (optionally) a soft
penalty on ``value`` for low-trust, non-Mall listings. ``trust_score`` blends the signals the
Shopee payload actually carries (rating / review count / Mall / Star), re-weighting over the ones
that are affirmatively present so a missing rating or a non-Mall seller is *dropped*, never scored
as a fabricated 0 (invariant #4). Weights/bounds are versioned data in ``ampere.config``.
"""

from __future__ import annotations

from math import log10

from ampere.config import (
    TRUST_PENALTY_FACTOR,
    TRUST_PENALTY_RATING_THRESHOLD,
    TRUST_RATING_BOUND,
    TRUST_REVIEWS_LOG_BOUND,
    TRUST_WEIGHTS,
)
from ampere.domain.scoring import normalize


def trust_score(
    *,
    seller_rating: float | None,
    seller_review_count: int | None,
    is_mall: bool,
    is_star_seller: bool,
) -> float | None:
    """A 0–100 seller-trust composite, or ``None`` if no trust signal is present at all (§5.6).

    Only affirmatively-present signals contribute: a missing rating / non-Mall / non-Star seller is
    dropped (not a 0), and the present components' weights renormalize to sum 1. Mall on its own is
    a strong signal — a Mall store with no shown rating still reads as trustworthy.
    """
    components: list[tuple[float, float]] = []  # (weight, value in 0..1)
    if seller_rating is not None:
        rating = normalize(seller_rating, TRUST_RATING_BOUND.ref_min, TRUST_RATING_BOUND.ref_max)
        components.append((TRUST_WEIGHTS["rating"], rating / 100.0))
    if seller_review_count is not None:
        confidence = normalize(
            log10(seller_review_count + 1),
            TRUST_REVIEWS_LOG_BOUND.ref_min,
            TRUST_REVIEWS_LOG_BOUND.ref_max,
        )
        components.append((TRUST_WEIGHTS["reviews"], confidence / 100.0))
    if is_mall:
        components.append((TRUST_WEIGHTS["mall"], 1.0))
    if is_star_seller:
        components.append((TRUST_WEIGHTS["star"], 1.0))

    if not components:
        return None
    total_weight = sum(weight for weight, _ in components)
    return 100.0 * sum(weight * value for weight, value in components) / total_weight


def trust_value_factor(*, is_mall: bool, seller_rating: float | None) -> float:
    """Soft multiplier on ``value`` for low-trust, non-Mall listings (§5.6); ``1.0`` (no-op) else.

    Only fires when the rating is *known* and below the threshold and the seller is not a Mall
    store — a missing rating is never treated as risk (invariant #4). Gated off by default at the
    call sites so the raw value stays legible unless the user opts in.
    """
    if not is_mall and seller_rating is not None and seller_rating < TRUST_PENALTY_RATING_THRESHOLD:
        return TRUST_PENALTY_FACTOR
    return 1.0

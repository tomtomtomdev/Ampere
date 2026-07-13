"""Scoring core — SPEC §5. PURE functions, deterministic, zero I/O.

STATUS: M1 stubs. Per CLAUDE.md invariant #2 (spec-driven TDD), the failing tests come FIRST,
then these bodies. A faithful, runnable reference implementation of every function below exists in
``design/Ampere.dc.html`` (the ``build()`` method) — port it *test-first*, do not paste it in.

Reference bounds + weights come from ``ampere.config`` (fixed + versioned, never cohort-relative).
"""

from __future__ import annotations

from ampere.config import PERFORMANCE_WEIGHTS, REFERENCE_BOUNDS
from ampere.domain.models import BatteryMetricKind, Chipset, Device, Weights

# The four perf metrics, in blend order. Each maps 1:1 to a REFERENCE_BOUNDS + PERFORMANCE_WEIGHTS
# key; the Chipset attribute name matches the key (§5.1/§5.2). Kept as data, not magic numbers.
_PERF_METRICS: tuple[str, ...] = ("gb6_single", "gb6_multi", "antutu", "wildlife")


def normalize(x: float, ref_min: float, ref_max: float) -> float:
    """clamp((x - ref_min) / (ref_max - ref_min) * 100, 0, 100) — SPEC §5.1.

    Fixed, versioned bounds (never cohort-relative), so the same input always yields the same
    output regardless of the daily cohort (SC3, R4).
    """
    scaled = (x - ref_min) / (ref_max - ref_min) * 100
    return max(0.0, min(100.0, scaled))


def performance(chipset: Chipset, throttle_modifier: float = 1.0) -> float:
    """Even 0.25 blend of normed GB6-single/GB6-multi/AnTuTu/Wild-Life — SPEC §5.2.

    Missing metrics are re-weighted across what's present (never fabricated — §5.4): the blend is
    a weighted mean over only the metrics the chipset actually has, so the weights of present
    metrics are renormalized to sum to 1. ``throttle_modifier`` scales each normed value after
    normalization and before the blend (§5.5). Raises ``ValueError`` if the chipset carries no
    benchmark at all — the caller marks that listing ``unmatched``/needs-mapping (§5.4).
    """
    present = {m: getattr(chipset, m) for m in _PERF_METRICS if getattr(chipset, m) is not None}
    if not present:
        raise ValueError(f"chipset {chipset.id!r} has no performance benchmarks to score (§5.4)")

    total_weight = sum(PERFORMANCE_WEIGHTS[m] for m in present)
    blended = 0.0
    for metric, raw in present.items():
        bound = REFERENCE_BOUNDS[metric]
        normed = normalize(raw, bound.ref_min, bound.ref_max) * throttle_modifier
        blended += (PERFORMANCE_WEIGHTS[metric] / total_weight) * normed
    return blended


def battery(device: Device) -> float:
    """norm(active_use_hours) against the fixed Active-Use-v2 window — SPEC §5.2.

    Never mixes the two metric kinds silently (§5.1): a device whose only battery figure is the
    legacy endurance rating raises, because no legacy reference bound is configured and M1 must
    not fabricate one (invariant #4). Support for the legacy scale is a later, deliberate bound.
    """
    if device.battery_metric_kind is BatteryMetricKind.LEGACY_ENDURANCE or (
        device.active_use_hours is None and device.legacy_endurance is not None
    ):
        raise ValueError(
            f"device {device.id!r} has only a legacy endurance rating; no legacy reference bound "
            "is configured (M1 supports active_use_v2 only — SPEC §5.1)"
        )
    if device.active_use_hours is None:
        raise ValueError(f"device {device.id!r} has no active_use_hours to score (§5.2)")
    bound = REFERENCE_BOUNDS["active_use_hours"]
    return normalize(device.active_use_hours, bound.ref_min, bound.ref_max)


def capability(performance_score: float, battery_score: float, weights: Weights) -> float:
    """W_PERF*performance + W_BATT*battery — SPEC §5.2. Battery is a co-equal pillar."""
    return weights.w_perf * performance_score + weights.w_batt * battery_score


def value(capability_score: float, effective_price: int) -> float:
    """capability / (effective_price / 1_000_000) — capability per juta (SPEC §5.3).

    ``effective_price`` must be positive; a non-positive adjusted price is nonsensical on the
    value axis and would blow up the ratio, so it raises rather than emit ``inf``/negative value.
    """
    if effective_price <= 0:
        raise ValueError(f"effective_price must be positive, got {effective_price}")
    return capability_score / (effective_price / 1_000_000)

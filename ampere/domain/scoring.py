"""Scoring core — SPEC §5. PURE functions, deterministic, zero I/O.

STATUS: M1 stubs. Per CLAUDE.md invariant #2 (spec-driven TDD), the failing tests come FIRST,
then these bodies. A faithful, runnable reference implementation of every function below exists in
``design/Ampere.dc.html`` (the ``build()`` method) — port it *test-first*, do not paste it in.

Reference bounds + weights come from ``ampere.config`` (fixed + versioned, never cohort-relative).
"""

from __future__ import annotations

from ampere.domain.models import Chipset, Device, Weights


def normalize(x: float, ref_min: float, ref_max: float) -> float:
    """clamp((x - ref_min) / (ref_max - ref_min) * 100, 0, 100) — SPEC §5.1."""
    raise NotImplementedError("M1: TDD from SPEC §5.1")


def performance(chipset: Chipset, throttle_modifier: float = 1.0) -> float:
    """Even 0.25 blend of normed GB6-single/GB6-multi/AnTuTu/Wild-Life — SPEC §5.2.

    Missing metrics are re-weighted across what's present (never fabricated — §5.4).
    ``throttle_modifier`` is applied after normalization, before the blend (§5.5).
    """
    raise NotImplementedError("M1: TDD from SPEC §5.2 / §5.5")


def battery(device: Device) -> float:
    """norm(active_use_hours) — or norm(legacy_endurance) if that's all we have (SPEC §5.2).

    Never mix the two metric kinds silently (§5.1).
    """
    raise NotImplementedError("M1: TDD from SPEC §5.2")


def capability(performance_score: float, battery_score: float, weights: Weights) -> float:
    """W_PERF*performance + W_BATT*battery — SPEC §5.2."""
    raise NotImplementedError("M1: TDD from SPEC §5.2")


def value(capability_score: float, effective_price: int) -> float:
    """capability / (effective_price / 1_000_000) — capability per juta (SPEC §5.3)."""
    raise NotImplementedError("M1: TDD from SPEC §5.3")

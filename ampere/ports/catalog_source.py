"""Catalog-source ports — the monthly reference-data feeds (SPEC §6, Appendices B/C).

Interfaces (Protocols) the ``refresh_catalog`` use-case depends on, so the application layer never
imports a scraper directly (invariant #1). Concrete impls live in ``ampere.adapters.scrapers``
(GSMArena today); a fixture impl or a different vendor drops in behind the same contract, exactly
like ``SearchSource`` for the daily path (SC4-style swappability).
"""

from __future__ import annotations

from typing import Protocol

from ampere.domain.models import BatteryReading, Chipset


class PerfCatalogSource(Protocol):
    """Yields one benchmark row per chipset (benchmarks belong to the SoC — §5.5, SC7)."""

    def fetch_chipsets(self) -> list[Chipset]: ...


class BatteryCatalogSource(Protocol):
    """Yields per-device battery readings (Active Use hours; battery stays per-device — §5.5)."""

    def fetch_battery(self) -> list[BatteryReading]: ...

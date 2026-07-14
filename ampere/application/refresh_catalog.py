"""The monthly catalog-refresh use-case (SPEC §6, Appendices B/C; M6).

"Only the listings are daily; everything else is a slowly-changing reference DB" (§2). This is that
slow path: pull per-chipset benchmarks and per-device battery from the injected catalog sources
(GSMArena today) and upsert them into the reference DB with provenance. Orchestration only — the
parsing lives in ``ampere.adapters.scrapers`` (I/O) and is reached through the ``PerfCatalogSource``
/ ``BatteryCatalogSource`` ports (invariant #1). Nothing is fabricated: a battery reading with no
matching device is *surfaced*, not guessed onto some device (invariant #4).

Benchmarks attach to the **chipset** (one row covers every phone with that SoC — §5.5, SC7); Active
Use hours attach per **model** (cell + display + tuning don't change across RAM/ROM variants), so
one reading fills all of a model's variant rows. Upserts autocommit (the reference DB is not the
atomic daily-snapshot path — that's ``run_daily``); a re-run is naturally idempotent.
"""

from __future__ import annotations

from ampere.domain.models import CatalogRefreshResult
from ampere.ports.catalog_source import BatteryCatalogSource, PerfCatalogSource
from ampere.ports.repositories import UnitOfWork


def _norm(name: str) -> str:
    """Case/whitespace-fold a phone name for matching (lowercase, collapse runs of whitespace)."""
    return " ".join(name.lower().split())


def refresh_catalog(
    *,
    uow: UnitOfWork,
    perf_source: PerfCatalogSource | None = None,
    battery_source: BatteryCatalogSource | None = None,
) -> CatalogRefreshResult:
    """Refresh the reference DB from the injected sources. Either source may be omitted."""
    chipsets_upserted = 0
    if perf_source is not None:
        for chipset in perf_source.fetch_chipsets():
            uow.chipsets.upsert(chipset)  # provenance (source/fetched_at) is set by the source
            chipsets_upserted += 1

    devices_updated = 0
    unmatched: list[str] = []
    if battery_source is not None:
        readings = battery_source.fetch_battery()
        # Index readings by every name form we might match a device on: bare model AND brand+model.
        reading_by_name = {}
        for reading in readings:
            reading_by_name.setdefault(_norm(reading.device), reading)

        matched_names: set[str] = set()
        for device in uow.devices.all():
            keys = (_norm(device.model), _norm(f"{device.brand} {device.model}"))
            reading = next((reading_by_name[k] for k in keys if k in reading_by_name), None)
            if reading is None:
                continue
            matched_names.add(_norm(reading.device))
            uow.devices.upsert(
                device.model_copy(
                    update={
                        "active_use_hours": reading.active_use_hours,
                        "battery_metric_kind": reading.metric_kind,
                    }
                )
            )
            devices_updated += 1

        # Surface readings we couldn't place rather than dropping them (invariant #4 / R3).
        unmatched = [r.device for r in readings if _norm(r.device) not in matched_names]

    return CatalogRefreshResult(
        chipsets_upserted=chipsets_upserted,
        devices_battery_updated=devices_updated,
        battery_unmatched=unmatched,
    )

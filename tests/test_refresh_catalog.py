"""M6 — the monthly catalog-refresh use-case (SPEC §6, Appendices B/C; SC7), test-first.

``refresh_catalog`` orchestrates the (injected) GSMArena perf + battery sources into the reference
DB: it upserts per-chipset benchmarks (with provenance) and attaches Active Use hours to devices by
name. Tested against fixture sources + in-memory SQLite (no network — invariant #2). The headline
assertion is SC7: a benchmark entered ONCE for a chipset is reflected on EVERY device sharing that
SoC, with no duplicate data entry.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.application.refresh_catalog import refresh_catalog
from ampere.application.snapshot import score_listing
from ampere.domain.models import (
    BatteryMetricKind,
    BatteryReading,
    Chipset,
    Device,
    Listing,
    Weights,
)


class FakePerfSource:
    def __init__(self, chipsets: list[Chipset]) -> None:
        self._chipsets = chipsets

    def fetch_chipsets(self) -> list[Chipset]:
        return self._chipsets


class FakeBatterySource:
    def __init__(self, readings: list[BatteryReading]) -> None:
        self._readings = readings

    def fetch_battery(self) -> list[BatteryReading]:
        return self._readings


@pytest.fixture
def uow() -> SqliteUnitOfWork:
    conn = db.connect(":memory:")
    db.create_schema(conn)
    return SqliteUnitOfWork(conn)


def _listing(shopee_id: str, device_id: str) -> Listing:
    from datetime import date

    return Listing(
        shopee_id=shopee_id, snapshot_date=date(2026, 7, 14), title="t",
        device_id=device_id, list_price=1_800_000, effective_price=1_800_000,
    )


class TestPerfRefresh:
    def test_upserts_chipsets_with_provenance(self, uow):
        chip = Chipset(
            id="dimensity-7300", name="Dimensity 7300", vendor="MediaTek",
            gb6_single=1050, gb6_multi=3047, antutu=656_811, wildlife=854,
            source="gsmarena_review:test", fetched_at=datetime(2026, 7, 14, tzinfo=UTC),
        )
        result = refresh_catalog(uow=uow, perf_source=FakePerfSource([chip]))

        assert result.chipsets_upserted == 1
        stored = uow.chipsets.get("dimensity-7300")
        assert stored is not None
        assert stored.gb6_single == 1050
        assert stored.source == "gsmarena_review:test"
        assert stored.fetched_at == datetime(2026, 7, 14, tzinfo=UTC)

    def test_sc7_one_chipset_row_scores_every_device_sharing_the_soc(self, uow):
        # Two phones, same SoC, chipset row exists as a stub (no benchmarks yet) -> unscoreable.
        uow.chipsets.upsert(Chipset(id="dimensity-6300", name="Dimensity 6300"))
        for did, variant in [("dev-a", "8/256"), ("dev-b", "6/128")]:
            uow.devices.upsert(Device(
                id=did, brand="Xiaomi", model="Redmi Note 13R", variant=variant,
                chipset_id="dimensity-6300", active_use_hours=15.0,
                battery_metric_kind=BatteryMetricKind.ACTIVE_USE_V2,
            ))
        assert score_listing(_listing("l-a", "dev-a"), uow, Weights()) is None

        # Enter the chipset benchmark ONCE.
        refresh_catalog(uow=uow, perf_source=FakePerfSource([Chipset(
            id="dimensity-6300", name="Dimensity 6300", gb6_single=740, gb6_multi=2060,
            antutu=435_000, wildlife=1050,
        )]))

        # ...and BOTH devices are now scoreable with identical performance (SC7).
        sa = score_listing(_listing("l-a", "dev-a"), uow, Weights())
        sb = score_listing(_listing("l-b", "dev-b"), uow, Weights())
        assert sa is not None and sb is not None
        assert sa.performance == sb.performance


class TestBatteryRefresh:
    def _seed_devices(self, uow):
        # chipset_id left NULL: battery matching is independent of the SoC.
        uow.devices.upsert(Device(id="dev-rn13-8-256", brand="Xiaomi", model="Redmi Note 13",
                                  variant="8/256"))
        uow.devices.upsert(Device(id="dev-rn13-6-128", brand="Xiaomi", model="Redmi Note 13",
                                  variant="6/128"))
        uow.devices.upsert(Device(id="dev-a15", brand="Samsung", model="Galaxy A15",
                                  variant="8/256"))

    def test_attaches_active_use_to_all_variants_of_a_model(self, uow):
        # Battery is per-model (cell + display + tuning), not per RAM/ROM variant: one reading for
        # "Redmi Note 13" fills every variant device row.
        self._seed_devices(uow)
        result = refresh_catalog(uow=uow, battery_source=FakeBatterySource([
            BatteryReading(device="Redmi Note 13", active_use_hours=15.38),
        ]))

        assert result.devices_battery_updated == 2
        for did in ("dev-rn13-8-256", "dev-rn13-6-128"):
            d = uow.devices.get(did)
            assert d.active_use_hours == 15.38
            assert d.battery_metric_kind is BatteryMetricKind.ACTIVE_USE_V2

    def test_matches_by_brand_and_model_when_reading_carries_brand(self, uow):
        self._seed_devices(uow)
        refresh_catalog(uow=uow, battery_source=FakeBatterySource([
            BatteryReading(device="Samsung Galaxy A15", active_use_hours=16.9),
        ]))
        assert uow.devices.get("dev-a15").active_use_hours == 16.9

    def test_unmatched_reading_surfaced_not_dropped_silently(self, uow):
        self._seed_devices(uow)
        result = refresh_catalog(uow=uow, battery_source=FakeBatterySource([
            BatteryReading(device="Some Phone We Don't Stock", active_use_hours=14.0),
        ]))
        assert result.devices_battery_updated == 0
        assert result.battery_unmatched == ["Some Phone We Don't Stock"]

    def test_does_not_clobber_longevity_fields(self, uow):
        # A battery refresh must not touch os/security update years (§11.1 provenance is separate).
        uow.devices.upsert(Device(id="dev-a15", brand="Samsung", model="Galaxy A15",
                                  variant="8/256", os_updates_years=4,
                                  security_updates_years=5, update_source="manufacturer policy"))
        refresh_catalog(uow=uow, battery_source=FakeBatterySource([
            BatteryReading(device="Galaxy A15", active_use_hours=16.9),
        ]))
        d = uow.devices.get("dev-a15")
        assert d.os_updates_years == 4 and d.security_updates_years == 5
        assert d.update_source == "manufacturer policy"
        assert d.active_use_hours == 16.9


class TestIdempotency:
    def test_rerun_is_idempotent(self, uow):
        chip = Chipset(id="c", name="C", gb6_single=1000, gb6_multi=3000, antutu=500_000,
                       wildlife=1000)
        uow.devices.upsert(Device(id="d", brand="Xiaomi", model="Redmi Note 13", variant="8/256"))
        readings = [BatteryReading(device="Redmi Note 13", active_use_hours=15.0)]

        r1 = refresh_catalog(uow=uow, perf_source=FakePerfSource([chip]),
                             battery_source=FakeBatterySource(readings))
        r2 = refresh_catalog(uow=uow, perf_source=FakePerfSource([chip]),
                             battery_source=FakeBatterySource(readings))

        assert r1 == r2
        assert len(uow.chipsets.all()) == 1  # no duplicate chipset rows
        assert uow.devices.get("d").active_use_hours == 15.0

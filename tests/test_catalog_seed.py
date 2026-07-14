"""M6 — real catalog seed loader (SPEC §6 "catalog build order", §11.1), test-first.

Loads the on-disk seed into the reference DB: ``chipsets_seed.csv`` (real GSMArena benchmarks) +
``devices_seed.csv`` (real ID-band device→chipset mappings + update-longevity). The seed carries NO
battery or benchmark numbers for devices — those are read from GSMArena by ``refresh_catalog`` and
never fabricated here (invariant #4). Device rows whose SoC isn't in the benchmark seed get a
chipset **stub** (name only) so the FK holds and the monthly refresh fills the numbers.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.application.catalog_seed import (
    SEED_DIR,
    load_chipset_seed,
    load_device_seed,
    load_seed,
)


@pytest.fixture
def uow() -> SqliteUnitOfWork:
    conn = db.connect(":memory:")
    db.create_schema(conn)
    return SqliteUnitOfWork(conn)


def _write(tmp_path: Path, name: str, text: str) -> Path:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


class TestLoadChipsetSeed:
    def test_loads_benchmarks_and_maps_antutu_v10(self, uow, tmp_path):
        csv = _write(tmp_path, "chipsets.csv",
            "chipset,gb6_single,gb6_multi,antutu_v10,wildlife_extreme,n_devices,sample_device,source\n"
            "Dimensity 7300,1050,3047,656811,854,1,Edge 60,gsmarena_review:x\n")
        n = load_chipset_seed(uow, csv)

        assert n == 1
        chip = uow.chipsets.get("dimensity-7300")
        assert chip.name == "Dimensity 7300"
        assert chip.vendor == "MediaTek"
        assert chip.gb6_single == 1050
        assert chip.antutu == 656811  # antutu_v10 column -> antutu field
        assert chip.wildlife == 854
        assert chip.source == "gsmarena_review:x"

    def test_blank_metric_is_none_not_zero(self, uow, tmp_path):
        csv = _write(tmp_path, "chipsets.csv",
            "chipset,gb6_single,gb6_multi,antutu_v10,wildlife_extreme,n_devices,sample_device,source\n"
            "Helio G85,,,,,1,Redmi 13C,src\n")
        load_chipset_seed(uow, csv)
        chip = uow.chipsets.get("helio-g85")
        assert chip.gb6_single is None  # never coerced to a fabricated 0 (invariant #4)


class TestLoadDeviceSeed:
    _CSV = (
        "brand,model,variant,chipset_name,os_updates_years,security_updates_years,update_source\n"
        "Xiaomi,Redmi Note 13,8/256,Snapdragon 685,2,3,Xiaomi budget tier (est.)\n"
        "realme,C67,8/256,Snapdragon 685,2,2,realme C-series (est.)\n"
    )

    def test_creates_devices_with_longevity_and_no_fabricated_battery(self, uow, tmp_path):
        n = load_device_seed(uow, _write(tmp_path, "devices.csv", self._CSV))
        assert n == 2

        dev = uow.devices.get("xiaomi-redmi-note-13-8-256")
        assert dev.brand == "Xiaomi" and dev.model == "Redmi Note 13" and dev.variant == "8/256"
        assert dev.chipset_id == "snapdragon-685"
        assert dev.os_updates_years == 2 and dev.security_updates_years == 3
        assert dev.update_source == "Xiaomi budget tier (est.)"
        assert dev.active_use_hours is None  # battery comes from refresh, not the seed
        assert dev.battery_metric_kind is None

    def test_stubs_missing_chipset_so_fk_holds_and_refresh_can_fill(self, uow, tmp_path):
        load_device_seed(uow, _write(tmp_path, "devices.csv", self._CSV))
        chip = uow.chipsets.get("snapdragon-685")
        assert chip is not None  # stub created
        assert chip.name == "Snapdragon 685"
        assert chip.vendor == "Qualcomm"
        assert chip.gb6_single is None  # benchmarks pending the monthly refresh
        assert "pending" in (chip.source or "").lower()

    def test_two_devices_share_one_chipset_row(self, uow, tmp_path):
        # SC7 flavour: two phones on Snapdragon 685 => one chipset row, not two.
        load_device_seed(uow, _write(tmp_path, "devices.csv", self._CSV))
        assert len(uow.chipsets.all()) == 1
        assert len(uow.devices.all()) == 2

    def test_does_not_overwrite_an_already_benchmarked_chipset(self, uow, tmp_path):
        # Chipset seed loaded first (with real numbers); device seed must not clobber it to a stub.
        chip_csv = _write(tmp_path, "chipsets.csv",
            "chipset,gb6_single,gb6_multi,antutu_v10,wildlife_extreme,n_devices,sample_device,source\n"
            "Snapdragon 685,900,2050,430000,720,1,Redmi Note 13,real\n")
        load_chipset_seed(uow, chip_csv)
        load_device_seed(uow, _write(tmp_path, "devices.csv", self._CSV))

        chip = uow.chipsets.get("snapdragon-685")
        assert chip.gb6_single == 900  # preserved
        assert chip.source == "real"


class TestRealSeedFiles:
    def test_shipped_seed_loads_cleanly(self, uow):
        chips, devs = load_seed(uow)
        assert chips > 0 and devs > 0

        # Every seeded device references an existing chipset (FK holds; no orphans).
        chip_ids = {c.id for c in uow.chipsets.all()}
        for d in uow.devices.all():
            assert d.chipset_id in chip_ids
            assert d.os_updates_years is not None
            assert d.security_updates_years is not None
            assert d.update_source  # provenance always recorded (§11.1)

        # SC7: within the device band, several phones share a SoC — fewer distinct chipsets than
        # devices (the chipsets table also holds the real high-band benchmark seed, unused as yet).
        device_socs = {d.chipset_id for d in uow.devices.all()}
        assert len(device_socs) < len(uow.devices.all())

    def test_seed_dir_points_at_the_repo_data_seed(self):
        assert SEED_DIR.name == "seed" and (SEED_DIR / "chipsets_seed.csv").exists()

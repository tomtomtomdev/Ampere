"""Load the on-disk reference-data seed into the catalog (SPEC §6 "catalog build order", §11.1).

This is the *real* catalog bootstrap (as opposed to ``demo_seed``'s illustrative numbers for the
offline UI demo). Two CSVs under ``data/seed/``:

- ``chipsets_seed.csv`` — real GSMArena per-SoC benchmarks (the one scraped artifact shipped in the
  repo; produced by the perf parser, SPEC Appendix C).
- ``devices_seed.csv`` — real ID-band device→chipset mappings + software-update longevity (§11.1).
  It carries **no** battery or benchmark numbers: battery comes from ``refresh_catalog`` scraping
  GSMArena, benchmarks from the chipset seed / refresh — never fabricated here (invariant #4).

A device whose SoC has no benchmark row yet gets a chipset **stub** (name + vendor only, benchmarks
``None``, ``source`` flagged "pending") so the foreign key holds and the monthly refresh fills the
numbers. Loading never downgrades an already-benchmarked chipset to a stub. Upserts autocommit; the
loaders are idempotent (re-running replaces by primary key).
"""

from __future__ import annotations

import csv
from pathlib import Path

from ampere.domain.catalog import chipset_id, chipset_vendor, device_id
from ampere.domain.models import Chipset, Device
from ampere.ports.repositories import UnitOfWork

SEED_DIR = Path(__file__).resolve().parents[2] / "data" / "seed"
CHIPSETS_SEED = "chipsets_seed.csv"
DEVICES_SEED = "devices_seed.csv"

_STUB_SOURCE = "pending: gsmarena refresh"


def _num(value: str | None) -> float | None:
    """Parse a CSV cell to float, or ``None`` for blank — never a fabricated 0 (invariant #4)."""
    value = (value or "").strip()
    return float(value) if value else None


def _int(value: str | None) -> int | None:
    value = (value or "").strip()
    return int(value) if value else None


def load_chipset_seed(uow: UnitOfWork, path: str | Path) -> int:
    """Upsert real per-SoC benchmarks from ``chipsets_seed.csv``. Returns the row count."""
    count = 0
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            name = row["chipset"].strip()
            uow.chipsets.upsert(
                Chipset(
                    id=chipset_id(name),
                    name=name,
                    vendor=chipset_vendor(name),
                    gb6_single=_num(row.get("gb6_single")),
                    gb6_multi=_num(row.get("gb6_multi")),
                    antutu=_num(row.get("antutu_v10")),  # v10 column → antutu field (§5.1)
                    wildlife=_num(row.get("wildlife_extreme")),
                    source=(row.get("source") or "").strip() or None,
                )
            )
            count += 1
    return count


def load_device_seed(uow: UnitOfWork, path: str | Path) -> int:
    """Upsert real device→chipset + update-longevity rows, stubbing unknown SoCs. Returns count."""
    count = 0
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            brand = row["brand"].strip()
            model = row["model"].strip()
            variant = row["variant"].strip()
            chipset_name = row["chipset_name"].strip()
            cid = chipset_id(chipset_name)

            # Ensure the SoC row exists so the FK holds; stub it ONLY if unknown (don't clobber
            # real benchmarks already loaded from the chipset seed).
            if uow.chipsets.get(cid) is None:
                uow.chipsets.upsert(
                    Chipset(id=cid, name=chipset_name, vendor=chipset_vendor(chipset_name),
                            source=_STUB_SOURCE)
                )

            uow.devices.upsert(
                Device(
                    id=device_id(brand, model, variant),
                    brand=brand, model=model, variant=variant, chipset_id=cid,
                    os_updates_years=_int(row.get("os_updates_years")),
                    security_updates_years=_int(row.get("security_updates_years")),
                    update_source=(row.get("update_source") or "").strip() or None,
                    # active_use_hours / battery_metric_kind intentionally unset — battery is
                    # filled by refresh_catalog from GSMArena (never fabricated).
                )
            )
            count += 1
    return count


def load_seed(uow: UnitOfWork, seed_dir: str | Path = SEED_DIR) -> tuple[int, int]:
    """Load both shipped seed files. Returns ``(chipsets_loaded, devices_loaded)``.

    Chipsets first so devices link to real benchmark rows where available; devices then stub any
    remaining SoCs for the monthly refresh to fill.
    """
    seed_dir = Path(seed_dir)
    chips = load_chipset_seed(uow, seed_dir / CHIPSETS_SEED)
    devs = load_device_seed(uow, seed_dir / DEVICES_SEED)
    return chips, devs

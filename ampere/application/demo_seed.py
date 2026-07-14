"""Dev/demo bootstrap — a small illustrative catalog + two fixture snapshots so the M4 web UI
shows real, server-computed data out of the box.

This is NOT the real catalog: the authoritative on-disk ``chipsets``/``devices`` seed (real
GSMArena benchmarks + battery, ~30–50 models) is M6. The numbers here are illustrative (mirroring
``design/Ampere.dc.html``) and cover exactly the ``FixtureSource`` listings, plus one extra device
sharing a chipset so the Catalog screen demonstrates SC7 (one SoC row → many devices). Reused by
``tests/test_views.py`` / ``tests/test_web.py`` so the demo path is itself under test.
"""

from __future__ import annotations

from datetime import date, timedelta

from ampere.adapters.sources.fixture_source import FixtureSource
from ampere.application.run_daily import run_daily
from ampere.domain.models import BatteryMetricKind, Chipset, Device, RunResult
from ampere.ports.repositories import UnitOfWork
from ampere.ports.search_source import SearchSource

# (id, name, vendor, gb6_single, gb6_multi, antutu_v10, wildlife_extreme) — illustrative (design).
_CHIPSETS = [
    ("sd685", "Snapdragon 685", "Qualcomm", 900, 2050, 430_000, 720),
    ("sd4g2", "Snapdragon 4 Gen 2", "Qualcomm", 1010, 2880, 575_000, 1120),
    ("helio_g99", "Helio G99", "MediaTek", 735, 1980, 405_000, 760),
    ("helio_g85", "Helio G85", "MediaTek", 410, 1450, 270_000, 340),
    ("d6300", "Dimensity 6300", "MediaTek", 740, 2060, 435_000, 1050),
    ("exynos1330", "Exynos 1330", "Samsung", 975, 2210, 505_000, 1200),
]
# (id, brand, model, variant, chipset_id, active_use_hours, os_years, sec_years)
_DEVICES = [
    ("dev-rn13-8-256", "Xiaomi", "Redmi Note 13", "8/256", "sd685", 18.2, 3, 4),
    ("dev-pocom6-6-128", "Xiaomi", "Poco M6 5G", "6/128", "sd4g2", 16.8, 2, 3),
    ("dev-hot40pro-8-256", "Infinix", "Hot 40 Pro", "8/256", "helio_g99", 18.5, 2, 3),
    ("dev-a15-8-256", "Samsung", "Galaxy A15", "8/256", "exynos1330", 16.9, 4, 5),
    ("dev-r13c-8-256", "Xiaomi", "Redmi 13C", "8/256", "helio_g85", 17.0, 2, 3),
    ("dev-rn13r-8-256", "Xiaomi", "Redmi Note 13R", "8/256", "d6300", 18.0, 2, 3),
    # Extra device sharing Helio G99 with Hot 40 Pro — Catalog shows "used by 2" (SC7 flavour).
    ("dev-note40-8-256", "Infinix", "Note 40", "8/256", "helio_g99", 19.1, 2, 3),
]


def seed_catalog(uow: UnitOfWork) -> None:
    """Idempotently upsert the illustrative chipset + device reference data."""
    for cid, name, vendor, s, m, a, w in _CHIPSETS:
        uow.chipsets.upsert(
            Chipset(id=cid, name=name, vendor=vendor, gb6_single=s, gb6_multi=m, antutu=a,
                    wildlife=w, source="GSMArena (demo)")
        )
    for did, brand, model, variant, cid, hours, os_y, sec_y in _DEVICES:
        uow.devices.upsert(
            Device(id=did, brand=brand, model=model, variant=variant, chipset_id=cid,
                   active_use_hours=hours, battery_metric_kind=BatteryMetricKind.ACTIVE_USE_V2,
                   os_updates_years=os_y, security_updates_years=sec_y,
                   update_source="GSMArena (demo)")
        )


def _prior_day_source() -> SearchSource:
    """Yesterday's fixture: two prices bumped up + one listing withheld, so *today* shows two
    price drops and one new arrival on the Changes screen."""
    base = FixtureSource().search("android", 0, 1_000_000_000)
    prior = []
    for raw in base:
        if raw.shopee_id == "L18":
            continue  # absent yesterday -> new arrival today
        if raw.shopee_id in ("L01", "L09"):
            prior.append(raw.model_copy(update={"list_price": raw.list_price + 100_000}))
        else:
            prior.append(raw)
    return FixtureSource(prior)


def bootstrap(uow: UnitOfWork, *, today: date, source: SearchSource | None = None) -> RunResult:
    """Seed the catalog and run yesterday + today (idempotent). Returns today's ``RunResult``."""
    seed_catalog(uow)
    run_daily(source=_prior_day_source(), uow=uow, snapshot_date=today - timedelta(days=1))
    return run_daily(source=source or FixtureSource(), uow=uow, snapshot_date=today)

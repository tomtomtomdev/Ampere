"""SQLite adapters for the ``ports.repositories`` Protocols + a ``SqliteUnitOfWork`` (SPEC §9, SC6).

Concrete I/O for the daily pipeline. Rows are (de)serialized to/from the pydantic boundary models
in ``ampere.domain.models``; enums are stored by value, dates as ISO-8601 text (schema uses TEXT
everywhere so snapshots stay diffable and reproducible — SC5).

**Transaction discipline (SC6):** the connection runs in autocommit mode, so single writes
(catalog upserts, run start/finish) persist immediately, while a set of writes made atomic — the
daily ``listings``/``scores``/``sku_rollup``/``runs.finish`` replace — is wrapped by the caller in
``SqliteUnitOfWork.transaction()`` (explicit ``BEGIN``/``COMMIT``/``ROLLBACK``). Repos never
commit on their own, so they compose cleanly inside that boundary.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime

from ampere.domain.models import (
    BatteryMetricKind,
    Chipset,
    Condition,
    Confidence,
    Device,
    Listing,
    PriceConfidence,
    Score,
    SkuRollup,
)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _opt_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


# ---------------------------------------------------------------------------
# Reference DB (slowly-changing; upserts autocommit)
# ---------------------------------------------------------------------------
class SqliteChipsetRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, chipset_id: str) -> Chipset | None:
        row = self._conn.execute("SELECT * FROM chipsets WHERE id = ?", (chipset_id,)).fetchone()
        return self._to_model(row) if row else None

    def all(self) -> list[Chipset]:
        rows = self._conn.execute("SELECT * FROM chipsets ORDER BY id").fetchall()
        return [self._to_model(r) for r in rows]

    def upsert(self, chipset: Chipset) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO chipsets "
            "(id, name, vendor, gb6_single, gb6_multi, antutu, wildlife, source, fetched_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                chipset.id, chipset.name, chipset.vendor, chipset.gb6_single, chipset.gb6_multi,
                chipset.antutu, chipset.wildlife, chipset.source,
                chipset.fetched_at.isoformat() if chipset.fetched_at else None,
            ),
        )

    @staticmethod
    def _to_model(row: sqlite3.Row) -> Chipset:
        return Chipset(
            id=row["id"], name=row["name"], vendor=row["vendor"], gb6_single=row["gb6_single"],
            gb6_multi=row["gb6_multi"], antutu=row["antutu"], wildlife=row["wildlife"],
            source=row["source"],
            fetched_at=datetime.fromisoformat(row["fetched_at"]) if row["fetched_at"] else None,
        )


class SqliteDeviceRepo:
    """Also satisfies the resolver's ``DeviceCatalogPort`` via ``candidates_for``."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, device_id: str) -> Device | None:
        row = self._conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
        return self._to_model(row) if row else None

    def all(self) -> list[Device]:
        rows = self._conn.execute("SELECT * FROM devices ORDER BY id").fetchall()
        return [self._to_model(r) for r in rows]

    def upsert(self, device: Device) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO devices "
            "(id, brand, model, variant, chipset_id, throttle_modifier, active_use_hours, "
            "legacy_endurance, battery_metric_kind, os_updates_years, security_updates_years, "
            "update_source, scoring_notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                device.id, device.brand, device.model, device.variant, device.chipset_id,
                device.throttle_modifier, device.active_use_hours, device.legacy_endurance,
                device.battery_metric_kind.value if device.battery_metric_kind else None,
                device.os_updates_years, device.security_updates_years, device.update_source,
                device.scoring_notes, _now(),
            ),
        )

    def candidates_for(self, brand: str | None) -> list[tuple[str, str]]:
        if brand is None:
            rows = self._conn.execute(
                "SELECT id, brand, model, variant FROM devices ORDER BY id"
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, brand, model, variant FROM devices WHERE brand = ? ORDER BY id",
                (brand,),
            ).fetchall()
        return [(r["id"], f"{r['brand']} {r['model']} {r['variant']}") for r in rows]

    @staticmethod
    def _to_model(row: sqlite3.Row) -> Device:
        kind = row["battery_metric_kind"]
        return Device(
            id=row["id"], brand=row["brand"], model=row["model"], variant=row["variant"],
            chipset_id=row["chipset_id"], throttle_modifier=row["throttle_modifier"],
            active_use_hours=row["active_use_hours"], legacy_endurance=row["legacy_endurance"],
            battery_metric_kind=BatteryMetricKind(kind) if kind else None,
            os_updates_years=row["os_updates_years"],
            security_updates_years=row["security_updates_years"],
            update_source=row["update_source"], scoring_notes=row["scoring_notes"],
        )


class SqliteAliasRepo:
    """Learned raw-pattern -> device_id overrides; also the resolver's ``AliasCatalogPort``."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def lookup(self, raw_pattern: str) -> str | None:
        row = self._conn.execute(
            "SELECT device_id FROM aliases WHERE raw_pattern = ?", (raw_pattern,)
        ).fetchone()
        return row["device_id"] if row else None

    def remember(self, raw_pattern: str, device_id: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO aliases (raw_pattern, device_id) VALUES (?, ?)",
            (raw_pattern, device_id),
        )


class SqliteSettingsRepo:
    """Key-value app settings (the UI-configurable push channel lives here — §11.2)."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def get(self, key: str) -> str | None:
        row = self._conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def set(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM settings WHERE key = ?", (key,))


# ---------------------------------------------------------------------------
# Daily data (replaced per snapshot inside a transaction — SC6)
# ---------------------------------------------------------------------------
class SqliteListingRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def for_snapshot(self, snapshot_date: date) -> list[Listing]:
        rows = self._conn.execute(
            "SELECT * FROM listings WHERE snapshot_date = ? ORDER BY id",
            (snapshot_date.isoformat(),),
        ).fetchall()
        return [self._to_model(r) for r in rows]

    def latest_snapshot_before(self, snapshot_date: date) -> date | None:
        row = self._conn.execute(
            "SELECT MAX(snapshot_date) AS d FROM listings WHERE snapshot_date < ?",
            (snapshot_date.isoformat(),),
        ).fetchone()
        return _opt_date(row["d"])

    def replace_snapshot(self, snapshot_date: date, listings: list[Listing]) -> None:
        iso = snapshot_date.isoformat()
        self._conn.execute("DELETE FROM listings WHERE snapshot_date = ?", (iso,))
        self._conn.executemany(
            "INSERT INTO listings "
            "(id, snapshot_date, title, list_price, effective_price, price_confidence, "
            "shipping_est, voucher_est, cashback_est, condition, is_mall, seller_rating, "
            "seller_review_count, is_star_seller, trust_score, seller_location, url, device_id, "
            "confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    m.shopee_id, m.snapshot_date.isoformat(), m.title, m.list_price,
                    m.effective_price, m.price_confidence.value, m.shipping_est, m.voucher_est,
                    m.cashback_est, m.condition.value, int(m.is_mall), m.seller_rating,
                    m.seller_review_count, int(m.is_star_seller), m.trust_score, m.seller_location,
                    m.url, m.device_id, m.confidence.value,
                )
                for m in listings
            ],
        )

    @staticmethod
    def _to_model(row: sqlite3.Row) -> Listing:
        return Listing(
            shopee_id=row["id"], snapshot_date=date.fromisoformat(row["snapshot_date"]),
            title=row["title"], device_id=row["device_id"], condition=Condition(row["condition"]),
            list_price=row["list_price"], effective_price=row["effective_price"],
            price_confidence=PriceConfidence(row["price_confidence"]),
            shipping_est=row["shipping_est"], voucher_est=row["voucher_est"],
            cashback_est=row["cashback_est"], is_mall=bool(row["is_mall"]),
            seller_rating=row["seller_rating"], seller_review_count=row["seller_review_count"],
            is_star_seller=bool(row["is_star_seller"]), trust_score=row["trust_score"],
            seller_location=row["seller_location"], url=row["url"],
            confidence=Confidence(row["confidence"]),
        )


class SqliteScoreRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def for_snapshot(self, snapshot_date: date) -> list[Score]:
        rows = self._conn.execute(
            "SELECT * FROM scores WHERE snapshot_date = ? ORDER BY listing_id",
            (snapshot_date.isoformat(),),
        ).fetchall()
        return [self._to_model(r) for r in rows]

    def replace_snapshot(self, snapshot_date: date, scores: list[Score]) -> None:
        iso = snapshot_date.isoformat()
        self._conn.execute("DELETE FROM scores WHERE snapshot_date = ?", (iso,))
        self._conn.executemany(
            "INSERT INTO scores "
            "(listing_id, snapshot_date, performance, battery, capability, value, is_frontier, "
            "confidence, scoring_version) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    m.listing_id, m.snapshot_date.isoformat(), m.performance, m.battery,
                    m.capability, m.value, int(m.is_frontier), m.confidence.value,
                    m.scoring_version,
                )
                for m in scores
            ],
        )

    @staticmethod
    def _to_model(row: sqlite3.Row) -> Score:
        return Score(
            listing_id=row["listing_id"], snapshot_date=date.fromisoformat(row["snapshot_date"]),
            performance=row["performance"], battery=row["battery"], capability=row["capability"],
            value=row["value"], is_frontier=bool(row["is_frontier"]),
            confidence=Confidence(row["confidence"]), scoring_version=row["scoring_version"],
        )


class SqliteSkuRollupRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def for_snapshot(self, snapshot_date: date) -> list[SkuRollup]:
        rows = self._conn.execute(
            "SELECT * FROM sku_rollup WHERE snapshot_date = ? ORDER BY model, variant, condition",
            (snapshot_date.isoformat(),),
        ).fetchall()
        return [self._to_model(r) for r in rows]

    def replace_snapshot(self, snapshot_date: date, rollups: list[SkuRollup]) -> None:
        iso = snapshot_date.isoformat()
        self._conn.execute("DELETE FROM sku_rollup WHERE snapshot_date = ?", (iso,))
        self._conn.executemany(
            "INSERT INTO sku_rollup "
            "(snapshot_date, model, variant, condition, best_listing_id, duplicate_count) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    m.snapshot_date.isoformat(), m.model, m.variant, m.condition.value,
                    m.best_listing_id, m.duplicate_count,
                )
                for m in rollups
            ],
        )

    @staticmethod
    def _to_model(row: sqlite3.Row) -> SkuRollup:
        return SkuRollup(
            snapshot_date=date.fromisoformat(row["snapshot_date"]), model=row["model"],
            variant=row["variant"], condition=Condition(row["condition"]),
            best_listing_id=row["best_listing_id"], duplicate_count=row["duplicate_count"],
        )


class SqliteRunRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def last_successful(self) -> date | None:
        row = self._conn.execute(
            "SELECT MAX(snapshot_date) AS d FROM runs WHERE status = 'ok'"
        ).fetchone()
        return _opt_date(row["d"])

    def start(self, snapshot_date: date, source_kind: str) -> int:
        """Idempotent per UNIQUE snapshot_date: a re-run resets the existing row to 'running'."""
        iso = snapshot_date.isoformat()
        self._conn.execute(
            "INSERT INTO runs (snapshot_date, started_at, source_kind, status) "
            "VALUES (?, ?, ?, 'running') "
            "ON CONFLICT(snapshot_date) DO UPDATE SET "
            "started_at = excluded.started_at, source_kind = excluded.source_kind, "
            "status = 'running', finished_at = NULL, listing_count = NULL",
            (iso, _now(), source_kind),
        )
        return self._conn.execute(
            "SELECT id FROM runs WHERE snapshot_date = ?", (iso,)
        ).fetchone()["id"]

    def finish(self, run_id: int, *, status: str, listing_count: int) -> None:
        self._conn.execute(
            "UPDATE runs SET finished_at = ?, status = ?, listing_count = ? WHERE id = ?",
            (_now(), status, listing_count, run_id),
        )


# ---------------------------------------------------------------------------
# Unit of Work — bundles the repos + owns the transaction boundary (SC6)
# ---------------------------------------------------------------------------
class SqliteUnitOfWork:
    """Runs the connection in autocommit mode; ``transaction()`` gives explicit atomic scopes."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn
        conn.isolation_level = None  # autocommit; explicit BEGIN/COMMIT via transaction()
        self.chipsets = SqliteChipsetRepo(conn)
        self.devices = SqliteDeviceRepo(conn)
        self.aliases = SqliteAliasRepo(conn)
        self.listings = SqliteListingRepo(conn)
        self.scores = SqliteScoreRepo(conn)
        self.sku_rollup = SqliteSkuRollupRepo(conn)
        self.runs = SqliteRunRepo(conn)
        self.settings = SqliteSettingsRepo(conn)

    def close(self) -> None:
        """Close the backing connection. Used by the web app's per-request UoW teardown."""
        self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self._conn.execute("BEGIN")
        try:
            yield
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        else:
            self._conn.execute("COMMIT")

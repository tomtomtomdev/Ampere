"""Repository ports — persistence interfaces (Protocols). Impls: ``ampere.adapters.repos``.

Kept as thin CRUD-ish contracts; the daily use-case (``run_daily``) composes them transactionally
per ``snapshot_date`` for idempotency (SC6).
"""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date
from typing import Protocol, runtime_checkable

from ampere.domain.models import Chipset, Device, Listing, Score, SkuRollup


class ChipsetRepo(Protocol):
    def get(self, chipset_id: str) -> Chipset | None: ...
    def all(self) -> list[Chipset]: ...
    def upsert(self, chipset: Chipset) -> None: ...


class DeviceRepo(Protocol):
    def get(self, device_id: str) -> Device | None: ...
    def all(self) -> list[Device]: ...
    def upsert(self, device: Device) -> None: ...


class AliasRepo(Protocol):
    def lookup(self, raw_pattern: str) -> str | None: ...
    def remember(self, raw_pattern: str, device_id: str) -> None: ...


class ListingRepo(Protocol):
    def for_snapshot(self, snapshot_date: date) -> list[Listing]: ...
    def latest_snapshot_before(self, snapshot_date: date) -> date | None:
        """The most recent snapshot strictly earlier than ``snapshot_date`` (for diffing)."""
        ...

    def replace_snapshot(self, snapshot_date: date, listings: list[Listing]) -> None:
        """Delete + rewrite all listings for the date. Not self-committing — the caller's
        ``UnitOfWork.transaction`` makes this atomic with the other repos' writes (SC6)."""
        ...


class ScoreRepo(Protocol):
    def for_snapshot(self, snapshot_date: date) -> list[Score]: ...
    def replace_snapshot(self, snapshot_date: date, scores: list[Score]) -> None: ...


class SkuRollupRepo(Protocol):
    def for_snapshot(self, snapshot_date: date) -> list[SkuRollup]: ...
    def replace_snapshot(self, snapshot_date: date, rollups: list[SkuRollup]) -> None: ...


class SettingsRepo(Protocol):
    """A tiny key-value store for app settings (e.g. the UI-configurable push channel, §11.2)."""

    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


class RunRepo(Protocol):
    def last_successful(self) -> date | None: ...
    def start(self, snapshot_date: date, source_kind: str) -> int:
        """Record (idempotently, per UNIQUE snapshot_date) a ``running`` row; return its id."""
        ...

    def finish(self, run_id: int, *, status: str, listing_count: int) -> None: ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Bundles the repos over one backing store + owns the transaction boundary (SC6).

    ``devices`` and ``aliases`` also satisfy the resolver's ``DeviceCatalogPort`` /
    ``AliasCatalogPort`` (structural typing), so ``run_daily`` passes them straight to ``resolve``.
    Repos do not self-commit; a data write is made atomic by wrapping it in ``transaction()``.
    """

    chipsets: ChipsetRepo
    devices: DeviceRepo
    aliases: AliasRepo
    listings: ListingRepo
    scores: ScoreRepo
    sku_rollup: SkuRollupRepo
    runs: RunRepo
    settings: SettingsRepo

    def transaction(self) -> AbstractContextManager[None]:
        """A commit-on-success / rollback-on-exception scope around a set of writes."""
        ...

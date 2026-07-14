"""M6 — automatic daily scheduling + launch-time catch-up (SPEC §8a, SC8), test-first.

SC8: the daily fetch runs automatically once per day; a machine asleep at the scheduled time still
gets exactly one run for that date via launch-time catch-up — never zero, never a duplicate
(idempotent per ``snapshot_date``). ``catch_up`` is the guarded entrypoint (skip if today already
succeeded); ``main`` is the headless ``ampere-run-daily`` shell the OS scheduler invokes, wiring
config + adapters + seed around it. Both exercised offline against FixtureSource (invariant #2).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from ampere.adapters.repos import db
from ampere.adapters.repos.sqlite_repos import SqliteUnitOfWork
from ampere.adapters.sources.fixture_source import FixtureSource
from ampere.application.run_daily import RunConfig, catch_up, main, run_daily

_TODAY = date(2026, 7, 14)
_YESTERDAY = _TODAY - timedelta(days=1)


@pytest.fixture
def uow() -> SqliteUnitOfWork:
    conn = db.connect(":memory:")
    db.create_schema(conn)
    return SqliteUnitOfWork(conn)


class TestCatchUp:
    def test_runs_when_no_successful_run_today(self, uow):
        result = catch_up(uow, FixtureSource(), today=_TODAY)
        assert result is not None
        assert result.status == "ok"
        assert uow.runs.last_successful() == _TODAY

    def test_noop_when_today_already_successful(self, uow):
        first = catch_up(uow, FixtureSource(), today=_TODAY)
        assert first is not None
        again = catch_up(uow, FixtureSource(), today=_TODAY)
        assert again is None  # SC8: never a duplicate run
        # exactly one snapshot for today (idempotent), one listing set
        assert len(uow.listings.for_snapshot(_TODAY)) == first.listing_count

    def test_runs_after_a_gap(self, uow):
        run_daily(source=FixtureSource(), uow=uow, snapshot_date=_YESTERDAY)  # yesterday's run
        result = catch_up(uow, FixtureSource(), today=_TODAY)
        assert result is not None and result.snapshot_date == _TODAY

    def test_retries_when_todays_run_failed(self, uow):
        # A failed run for today leaves last_successful < today -> catch_up should retry.
        uow.runs.start(_TODAY, "fixture")
        run_id = uow.runs.start(_TODAY, "fixture")
        uow.runs.finish(run_id, status="failed", listing_count=0)
        assert uow.runs.last_successful() is None

        result = catch_up(uow, FixtureSource(), today=_TODAY)
        assert result is not None and result.status == "ok"


class TestRunConfig:
    def test_from_env_defaults(self):
        cfg = RunConfig.from_env({})
        assert cfg.source_kind == "fixture"  # safe offline default
        assert cfg.price_min == 1_000_000 and cfg.price_max == 2_000_000

    def test_from_env_overrides(self):
        cfg = RunConfig.from_env({
            "AMPERE_SOURCE": "affiliate",
            "AMPERE_KEYWORD": "hp android",
            "AMPERE_PRICE_MIN": "1500000",
            "AMPERE_PRICE_MAX": "2500000",
            "AMPERE_MALL_ONLY": "1",
        })
        assert cfg.source_kind == "affiliate"
        assert cfg.keyword == "hp android"
        assert cfg.price_min == 1_500_000 and cfg.price_max == 2_500_000
        assert cfg.mall_only is True


class TestMainEntrypoint:
    def test_main_seeds_and_runs_once(self, tmp_path, monkeypatch):
        db_file = tmp_path / "ampere.db"
        monkeypatch.setenv("AMPERE_DB", str(db_file))
        monkeypatch.setenv("AMPERE_SOURCE", "fixture")

        rc = main()
        assert rc == 0

        # A successful run exists for today; the real catalog seed was loaded.
        conn = db.connect(str(db_file))
        try:
            u = SqliteUnitOfWork(conn)
            assert u.runs.last_successful() == date.today()
            assert u.devices.all()  # seeded from data/seed on first run
        finally:
            conn.close()

    def test_main_is_idempotent_second_invocation_is_noop(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AMPERE_DB", str(tmp_path / "ampere.db"))
        monkeypatch.setenv("AMPERE_SOURCE", "fixture")
        assert main() == 0
        assert main() == 0  # guarded catch-up: no error, no duplicate

        conn = db.connect(str(tmp_path / "ampere.db"))
        try:
            rows = conn.execute(
                "SELECT COUNT(*) AS n FROM runs WHERE snapshot_date = ?",
                (date.today().isoformat(),),
            ).fetchone()["n"]
            assert rows == 1  # one runs row for today, not two
        finally:
            conn.close()

"""M0 smoke tests — the skeleton is wired and the DoD holds:

  * every layer imports (Clean-Architecture package tree is intact),
  * the SQLite schema creates,
  * FixtureSource returns a canned, in-band, source-agnostic listing set,
  * scoring config is internally consistent.

M1 scoring/frontier lives in ``test_scoring.py`` / ``test_frontier.py`` and M2 entity resolution
in ``test_resolve.py``; this file stays scoped to the M0 skeleton DoD.
"""

from __future__ import annotations

from ampere import config
from ampere.adapters.repos import db
from ampere.adapters.sources.fixture_source import FixtureSource
from ampere.domain.models import RawListing
from ampere.ports.search_source import SearchSource


def test_schema_creates_in_memory():
    conn = db.connect(":memory:")
    try:
        db.create_schema(conn)
        tables = {
            row["name"]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert {"chipsets", "devices", "listings", "scores", "runs", "sku_rollup"} <= tables
        # runs.snapshot_date is UNIQUE -> idempotency backbone (SC6).
        run_cols = conn.execute("PRAGMA table_info(runs)").fetchall()
        assert any(c["name"] == "snapshot_date" for c in run_cols)
    finally:
        conn.close()


def test_fixture_source_is_a_search_source_and_returns_in_band_listings():
    src = FixtureSource()
    assert isinstance(src, SearchSource)  # structural (Protocol) conformance
    assert src.kind == "fixture"

    rows = src.search("android", config.DEFAULT_PRICE_MIN, config.DEFAULT_PRICE_MAX)
    assert rows, "fixture must return a canned set"
    assert all(isinstance(r, RawListing) for r in rows)
    assert all(config.DEFAULT_PRICE_MIN <= r.list_price <= config.DEFAULT_PRICE_MAX for r in rows)
    # includes deliberately-unmatched titles for the needs-mapping queue (SPEC §7).
    assert any(r.brand is None for r in rows)


def test_fixture_source_mall_only_filter():
    src = FixtureSource()
    mall = src.search("android", 0, 10_000_000, mall_only=True)
    assert mall and all(r.is_mall for r in mall)


def test_scoring_config_is_consistent():
    assert abs(sum(config.PERFORMANCE_WEIGHTS.values()) - 1.0) < 1e-9
    assert abs((config.DEFAULT_W_PERF + config.DEFAULT_W_BATT) - 1.0) < 1e-9
    assert config.SCORING_VERSION  # pinned (SC3)
    for bound in config.REFERENCE_BOUNDS.values():
        assert bound.ref_min < bound.ref_max

"""SQLite connection + schema bootstrap. The concrete repos (M3) build on this.

Kept minimal for M0: ``connect()`` returns a configured connection and ``create_schema()`` applies
``schema.sql`` idempotently (CREATE TABLE IF NOT EXISTS) — satisfying the M0 DoD "schema creates".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# Default on-disk location; ``:memory:`` is used by tests. DB is gitignored + reproducible (SC5).
DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "data" / "ampere.db"


def connect(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection with FK enforcement and ``Row`` access."""
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    """Apply the versioned schema. Idempotent — safe to call on every startup."""
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()

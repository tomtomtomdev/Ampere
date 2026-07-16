-- Ampere SQLite schema (PLAN "Data model"). snapshot_date everywhere => reproducible + diffable.
-- Benchmarks live on `chipsets`, not devices (SPEC §5.5, SC7). runs.snapshot_date UNIQUE +
-- transactional replace-per-date give idempotency (SC6).

PRAGMA foreign_keys = ON;

-- Reference DB (slowly-changing; monthly refresh) -----------------------------------------------
CREATE TABLE IF NOT EXISTS chipsets (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    vendor      TEXT,
    gb6_single  REAL,
    gb6_multi   REAL,
    antutu      REAL,          -- v10 total
    wildlife    REAL,          -- Wild Life Extreme (Highest)
    source      TEXT,
    fetched_at  TEXT
);

CREATE TABLE IF NOT EXISTS devices (
    id                    TEXT PRIMARY KEY,
    brand                 TEXT NOT NULL,
    model                 TEXT NOT NULL,
    variant               TEXT NOT NULL,
    chipset_id            TEXT REFERENCES chipsets(id),
    throttle_modifier     REAL NOT NULL DEFAULT 1.0,
    active_use_hours      REAL,
    legacy_endurance      REAL,
    battery_metric_kind   TEXT,     -- 'active_use_v2' | 'endurance'
    os_updates_years      INTEGER,
    security_updates_years INTEGER,
    update_source         TEXT,
    scoring_notes         TEXT,
    created_at            TEXT
);

CREATE TABLE IF NOT EXISTS aliases (
    raw_pattern  TEXT PRIMARY KEY,     -- learned resolution (SPEC §7 step 5)
    device_id    TEXT NOT NULL REFERENCES devices(id)
);

-- App settings (UI-configurable, slowly-changing). Key-value; the push-channel config
-- (notify.kind / notify.telegram_token / notify.telegram_chat_id) lives here so the web UI and the
-- scheduled run_daily job share one source of truth (SPEC §11.2).
CREATE TABLE IF NOT EXISTS settings (
    key    TEXT PRIMARY KEY,
    value  TEXT
);

-- Daily data (fast-moving) ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS listings (
    id                 TEXT NOT NULL,          -- shopee_id
    snapshot_date      TEXT NOT NULL,
    title              TEXT NOT NULL,
    list_price         INTEGER NOT NULL,
    effective_price    INTEGER NOT NULL,
    price_confidence   TEXT,
    shipping_est       INTEGER NOT NULL DEFAULT 0,
    voucher_est        INTEGER NOT NULL DEFAULT 0,
    cashback_est       INTEGER NOT NULL DEFAULT 0,
    condition          TEXT,
    is_mall            INTEGER NOT NULL DEFAULT 0,
    seller_rating      REAL,
    seller_review_count INTEGER,
    is_star_seller     INTEGER NOT NULL DEFAULT 0,
    trust_score        REAL,
    seller_location    TEXT,
    url                TEXT,
    device_id          TEXT REFERENCES devices(id),
    confidence         TEXT,
    PRIMARY KEY (snapshot_date, id)
);

CREATE TABLE IF NOT EXISTS sku_rollup (
    snapshot_date    TEXT NOT NULL,
    model            TEXT NOT NULL,
    variant          TEXT NOT NULL,
    condition        TEXT NOT NULL,
    best_listing_id  TEXT NOT NULL,
    duplicate_count  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (snapshot_date, model, variant, condition)
);

CREATE TABLE IF NOT EXISTS price_history (
    shopee_id        TEXT NOT NULL,
    snapshot_date    TEXT NOT NULL,
    list_price       INTEGER NOT NULL,
    effective_price  INTEGER NOT NULL,
    PRIMARY KEY (shopee_id, snapshot_date)
);

CREATE TABLE IF NOT EXISTS scores (
    listing_id       TEXT NOT NULL,
    snapshot_date    TEXT NOT NULL,
    performance      REAL NOT NULL,
    battery          REAL NOT NULL,
    capability       REAL NOT NULL,
    value            REAL NOT NULL,
    is_frontier      INTEGER NOT NULL DEFAULT 0,
    confidence       TEXT,
    scoring_version  TEXT NOT NULL,
    PRIMARY KEY (snapshot_date, listing_id)
);

-- Observability / idempotency (SC6, SC8) --------------------------------------------------------
CREATE TABLE IF NOT EXISTS runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_date  TEXT NOT NULL UNIQUE,
    started_at     TEXT,
    finished_at    TEXT,
    source_kind    TEXT,
    listing_count  INTEGER,
    status         TEXT           -- 'running' | 'ok' | 'failed'
);

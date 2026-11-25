"""SQLite database schema and connection utilities for retail inventory state.

Historical M5 sales remain in Parquet files (`data/processed/`), while SQLite
strictly manages simulated inventory records, transaction audit logs, product
metadata, and generated demand forecasts (Section 11).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "retail_inventory.db"


def get_db_path(db_path: str | Path | None = None) -> Path:
    """Resolve the SQLite database path from argument, env var, or default."""
    if db_path is not None:
        path = Path(db_path)
    elif env_path := os.getenv("RETAIL_DB_PATH"):
        path = Path(env_path)
    else:
        path = DEFAULT_DB_PATH

    if not path.is_absolute():
        path = REPO_ROOT / path
    return path


def get_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Open a configured SQLite connection with Row factory and FK enforcement."""
    resolved_path = get_db_path(db_path)
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(resolved_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


@contextmanager
def db_session(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Context manager yielding a transactional SQLite connection."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS product_metadata (
    item_id  TEXT NOT NULL,
    store_id TEXT NOT NULL,
    dept_id  TEXT NOT NULL,
    cat_id   TEXT NOT NULL,
    state_id TEXT NOT NULL,
    PRIMARY KEY (item_id, store_id)
);

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id            TEXT NOT NULL,
    store_id           TEXT NOT NULL,
    on_hand            INTEGER NOT NULL DEFAULT 0 CHECK (on_hand >= 0),
    on_order           INTEGER NOT NULL DEFAULT 0 CHECK (on_order >= 0),
    backorders         INTEGER NOT NULL DEFAULT 0 CHECK (backorders >= 0),
    lead_time_days     INTEGER NOT NULL DEFAULT 5 CHECK (lead_time_days >= 1),
    review_period_days INTEGER NOT NULL DEFAULT 7 CHECK (review_period_days >= 1),
    unit_cost          REAL NOT NULL DEFAULT 0.0 CHECK (unit_cost >= 0.0),
    updated_at         TEXT NOT NULL,
    UNIQUE (item_id, store_id),
    FOREIGN KEY (item_id, store_id) REFERENCES product_metadata (item_id, store_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS inventory_transactions (
    transaction_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id          TEXT NOT NULL,
    store_id         TEXT NOT NULL,
    transaction_type TEXT NOT NULL CHECK (
        transaction_type IN (
            'opening_stock',
            'simulated_sale',
            'receipt',
            'manual_adjustment'
        )
    ),
    quantity         INTEGER NOT NULL,
    transaction_date TEXT NOT NULL,
    notes            TEXT,
    FOREIGN KEY (item_id, store_id) REFERENCES product_metadata (item_id, store_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS forecast_results (
    forecast_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id        TEXT NOT NULL,
    store_id       TEXT NOT NULL,
    forecast_date  TEXT NOT NULL,
    prediction     REAL NOT NULL CHECK (prediction >= 0.0),
    prediction_p95 REAL CHECK (prediction_p95 IS NULL OR prediction_p95 >= 0.0),
    horizon        INTEGER NOT NULL CHECK (horizon IN (7, 14, 28)),
    model_version  TEXT NOT NULL,
    created_at     TEXT NOT NULL,
    UNIQUE (item_id, store_id, forecast_date, horizon, model_version),
    FOREIGN KEY (item_id, store_id) REFERENCES product_metadata (item_id, store_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_inventory_store_item
    ON inventory (store_id, item_id);

CREATE INDEX IF NOT EXISTS idx_transactions_item_store_date
    ON inventory_transactions (store_id, item_id, transaction_date);

CREATE INDEX IF NOT EXISTS idx_forecasts_lookup
    ON forecast_results (store_id, item_id, horizon, model_version, forecast_date);
"""


def init_db(db_path: str | Path | None = None) -> Path:
    """Create all SQLite tables and indexes if they do not already exist."""
    resolved_path = get_db_path(db_path)
    with db_session(resolved_path) as conn:
        conn.executescript(SCHEMA_SQL)
    return resolved_path


if __name__ == "__main__":
    created_path = init_db()
    print(f"Initialized SQLite database at: {created_path}")

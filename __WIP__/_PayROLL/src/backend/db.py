from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    default_rate REAL NOT NULL DEFAULT 0,
    address TEXT NOT NULL DEFAULT '',
    phone_number TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pay_periods (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    start_date TEXT NOT NULL,
    hourly_rate REAL NOT NULL DEFAULT 20,
    yto_rate REAL NOT NULL DEFAULT 0,
    snow_day_multiplier REAL NOT NULL DEFAULT 0.8,
    owed_amount REAL NOT NULL DEFAULT 0,
    tax_rate REAL NOT NULL DEFAULT 0.33,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS day_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pay_period_id INTEGER NOT NULL,
    weekday TEXT NOT NULL,
    week_index INTEGER NOT NULL,
    display_order INTEGER NOT NULL,
    client_id INTEGER,
    route_stop INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT '',
    rate_override REAL,
    comments TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(pay_period_id) REFERENCES pay_periods(id) ON DELETE CASCADE,
    FOREIGN KEY(client_id) REFERENCES clients(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS other_task_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pay_period_id INTEGER NOT NULL,
    weekday TEXT NOT NULL,
    week_index INTEGER NOT NULL,
    label TEXT NOT NULL DEFAULT 'Office Work',
    hours REAL NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(pay_period_id) REFERENCES pay_periods(id) ON DELETE CASCADE,
    UNIQUE(pay_period_id, weekday, week_index)
);

CREATE TABLE IF NOT EXISTS mileage_segments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    pay_period_id INTEGER NOT NULL,
    weekday TEXT NOT NULL,
    week_index INTEGER NOT NULL,
    sequence INTEGER NOT NULL,
    segment_type TEXT NOT NULL,
    from_endpoint TEXT NOT NULL DEFAULT '',
    to_endpoint TEXT NOT NULL DEFAULT '',
    odometer_start REAL,
    odometer_end REAL,
    direct_miles REAL,
    notes TEXT NOT NULL DEFAULT '',
    auto_generated INTEGER NOT NULL DEFAULT 1,
    stale INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(pay_period_id) REFERENCES pay_periods(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS app_settings (
    setting_key TEXT PRIMARY KEY,
    setting_value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_day_entries_period_weekday
ON day_entries(pay_period_id, weekday, week_index, display_order);

CREATE INDEX IF NOT EXISTS idx_mileage_segments_period_weekday
ON mileage_segments(pay_period_id, weekday, week_index, sequence);
"""


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")

    def initialize(self) -> None:
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    def execute(self, sql: str, params: tuple | dict = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, params)

    def query_one(self, sql: str, params: tuple | dict = ()) -> sqlite3.Row | None:
        cursor = self.connection.execute(sql, params)
        return cursor.fetchone()

    def query_all(self, sql: str, params: tuple | dict = ()) -> list[sqlite3.Row]:
        cursor = self.connection.execute(sql, params)
        return cursor.fetchall()

    def commit(self) -> None:
        self.connection.commit()

    def rollback(self) -> None:
        self.connection.rollback()

    def close(self) -> None:
        self.connection.close()

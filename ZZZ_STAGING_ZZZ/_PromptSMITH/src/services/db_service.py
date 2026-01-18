# src/services/db_service.py
import sqlite3
import time
from typing import Any, Dict, List, Optional


class DatabaseManager:
    """
    SQLite single source of truth.

    Table:
      items(id, schema_name, display_name, json_data, created_at, updated_at)

    Includes basic retry on SQLITE_BUSY (locked DB).
    """

    def __init__(self, db_path: str = "promptarchitect.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        cur = self._conn.cursor()
        # Helpful for reducing "database is locked" frequency
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=NORMAL;")

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                schema_name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                json_data TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_items_schema ON items(schema_name);")
        self._conn.commit()

    # -------------------------
    # Lock-safe execution
    # -------------------------

    def _execute_with_retry(self, sql: str, params: tuple = (), retries: int = 5, delay: float = 0.15):
        last_exc = None
        for _ in range(retries):
            try:
                cur = self._conn.cursor()
                cur.execute(sql, params)
                return cur
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() or "busy" in str(e).lower():
                    last_exc = e
                    time.sleep(delay)
                    delay *= 1.6
                    continue
                raise
        if last_exc:
            raise last_exc

    # -------------------------
    # CRUD
    # -------------------------

    def list_items(self, schema_name: str) -> List[Dict[str, Any]]:
        cur = self._execute_with_retry(
            "SELECT id, schema_name, display_name FROM items WHERE schema_name=? ORDER BY updated_at DESC",
            (schema_name,),
        )
        return [dict(r) for r in cur.fetchall()]

    def get_item(self, item_id: int) -> Optional[Dict[str, Any]]:
        cur = self._execute_with_retry(
            "SELECT id, schema_name, display_name, json_data FROM items WHERE id=?",
            (item_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def upsert_item(self, item_id: Optional[int], schema_name: str, display_name: str, json_data: str) -> int:
        if item_id is None:
            cur = self._execute_with_retry(
                """
                INSERT INTO items(schema_name, display_name, json_data, created_at, updated_at)
                VALUES(?,?,?,datetime('now'),datetime('now'))
                """,
                (schema_name, display_name, json_data),
            )
            self._conn.commit()
            return int(cur.lastrowid)

        self._execute_with_retry(
            """
            UPDATE items
            SET schema_name=?,
                display_name=?,
                json_data=?,
                updated_at=datetime('now')
            WHERE id=?
            """,
            (schema_name, display_name, json_data, item_id),
        )
        self._conn.commit()
        return item_id

    def delete_item(self, item_id: int) -> None:
        self._execute_with_retry("DELETE FROM items WHERE id=?", (item_id,))
        self._conn.commit()

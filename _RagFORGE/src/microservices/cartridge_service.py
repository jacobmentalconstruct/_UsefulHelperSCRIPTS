import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from .base_service import BaseService

class CartridgeService(BaseService):
    """
    The Source of Truth.
    Manages the Unified Neural Cartridge Format (UNCF v1.0).
    """
    
    SCHEMA_VERSION = "uncf_v1.0"

    def __init__(self, db_path: str):
        super().__init__("CartridgeService")
        self.db_path = Path(db_path)
        self._init_db()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        """Initializes the standard Schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 1. Manifest (The Boot Sector)
        cursor.execute("CREATE TABLE IF NOT EXISTS manifest (key TEXT PRIMARY KEY, value TEXT)")
        
        # 1.5 Directories (The VFS Index)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS directories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vfs_path TEXT UNIQUE NOT NULL,
                parent_path TEXT,
                metadata TEXT DEFAULT '{}'
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_dir_parent ON directories(parent_path)")

        # 2. Files (The Content Store)
        # Supports Text AND Binary (blob_data)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                vfs_path TEXT NOT NULL,       -- Portable path (e.g. "src/main.py")
                origin_path TEXT,             -- Provenance (e.g. "C:/Users/...")
                origin_type TEXT,             -- 'filesystem', 'web', 'github'
                content TEXT,                 -- Text content (UTF-8)
                blob_data BLOB,               -- Binary content (Images, PDFs)
                mime_type TEXT,
                status TEXT DEFAULT 'RAW',    -- RAW, REFINED, ERROR, SKIPPED
                metadata TEXT DEFAULT '{}',   -- JSON tags, summaries
                last_updated TIMESTAMP
            )
        """)
        # Index for fast lookups by VFS path
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_vfs ON files(vfs_path)")

        # 3. Chunks (The Vector Store)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                chunk_index INTEGER,
                content TEXT,
                embedding BLOB,
                name TEXT,
                type TEXT,
                start_line INTEGER,
                end_line INTEGER,
                FOREIGN KEY(file_id) REFERENCES files(id)
            )
        """)

        # 4. Graph Topology (The Neural Wiring)
        cursor.execute("CREATE TABLE IF NOT EXISTS graph_nodes (id TEXT PRIMARY KEY, type TEXT, label TEXT, data_json TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS graph_edges (source TEXT, target TEXT, relation TEXT, weight REAL)")

        # 5. Validation Logs
        cursor.execute("CREATE TABLE IF NOT EXISTS logs (timestamp REAL, level TEXT, message TEXT, context TEXT)")
        
        conn.commit()
        conn.close()

    def store_file(self, vfs_path: str, origin_path: str, content: str = None, blob: bytes = None, mime_type: str = "text/plain", origin_type: str = "filesystem"):
        """
        The Universal Input Method. 
        Stores raw data. If file exists, updates it and resets status to 'RAW' for re-refining.
        """
        conn = self._get_conn()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO files 
                (vfs_path, origin_path, origin_type, content, blob_data, mime_type, status, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, 'RAW', ?)
            """, (vfs_path, origin_path, origin_type, content, blob, mime_type, time.time()))
            conn.commit()
            return True
        except Exception as e:
            self.log_error(f"DB Store Error ({vfs_path}): {e}")
            return False
        finally:
            conn.close()

    def get_pending_files(self, limit: int = 10) -> List[Dict]:
        """Fetches files waiting for the Refinery."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM files WHERE status = 'RAW' LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]

    def update_status(self, file_id: int, status: str, metadata: dict = None):
        conn = self._get_conn()
        if metadata:
            conn.execute("UPDATE files SET status = ?, metadata = ? WHERE id = ?", 
                         (status, json.dumps(metadata), file_id))
        else:
            conn.execute("UPDATE files SET status = ? WHERE id = ?", (status, file_id))
        conn.commit()
        conn.close()

    def ensure_directory(self, vfs_path: str):
        """Idempotent insert for VFS directories."""
        if not vfs_path: return
        parent = os.path.dirname(vfs_path).replace("\\", "/")
        if parent == vfs_path: parent = "" # Root case
        
        conn = self._get_conn()
        try:
            conn.execute("INSERT OR IGNORE INTO directories (vfs_path, parent_path) VALUES (?, ?)", (vfs_path, parent))
            conn.commit()
        except: pass
        finally:
            conn.close()

    # --- Graph Helpers ---
    def add_node(self, node_id: str, node_type: str, label: str, data: dict = None):
        conn = self._get_conn()
        conn.execute("INSERT OR REPLACE INTO graph_nodes (id, type, label, data_json) VALUES (?, ?, ?, ?)",
                     (node_id, node_type, label, json.dumps(data or {})))
        conn.commit()
        conn.close()

    def add_edge(self, source: str, target: str, relation: str = "related", weight: float = 1.0):
        conn = self._get_conn()
        conn.execute("INSERT OR IGNORE INTO graph_edges (source, target, relation, weight) VALUES (?, ?, ?, ?)",
                     (source, target, relation, weight))
        conn.commit()
        conn.close()

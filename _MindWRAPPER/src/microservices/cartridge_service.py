import sqlite3
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, List
from .base_service import BaseService

class CartridgeService(BaseService):
    """
    The Storage Manager (v2 - Graph Ready).
    Manages the SQLite Cartridge format, now including Graph Nodes, Edges, and Validation Logs.
    """
    
    def __init__(self, db_path: str):
        super().__init__("CartridgeService")
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        """Initializes the ELT Schema + Graph Schema."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 1. Manifest & Files (Standard ELT)
        cursor.execute("CREATE TABLE IF NOT EXISTS manifest (key TEXT PRIMARY KEY, value TEXT)")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,
                content TEXT,
                blob_data BLOB,
                status TEXT DEFAULT 'RAW',
                mime_type TEXT,
                metadata TEXT DEFAULT '{}',
                last_updated TIMESTAMP
            )
        """)

        # 2. Chunks (Vectors)
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

        # 3. [NEW] Graph Topology (The Neural Wiring)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_nodes (
                id TEXT PRIMARY KEY, 
                type TEXT, 
                label TEXT, 
                data_json TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS graph_edges (
                source TEXT, 
                target TEXT, 
                weight REAL,
                relation TEXT
            )
        """)

        # 4. [NEW] Validation (The "Integrity Check")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS unresolved_imports (
                source_file TEXT, 
                import_name TEXT,
                timestamp TIMESTAMP
            )
        """)
        
        conn.commit()
        conn.close()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    # --- Existing Methods (store_raw_file, get_pending_files) remain the same ---

    def store_raw_file(self, path: str, content: str = None, blob: bytes = None, mime_type: str = "text/plain"):
        """Stores raw data. Updates timestamp if file exists."""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO files (path, content, blob_data, mime_type, status, last_updated)
                VALUES (?, ?, ?, ?, 'RAW', ?)
            """, (path, content, blob, mime_type, time.time()))
            
            # Also register as a Graph Node immediately
            node_id = path
            cursor.execute("""
                INSERT OR REPLACE INTO graph_nodes (id, type, label, data_json)
                VALUES (?, ?, ?, ?)
            """, (node_id, 'file', path, json.dumps({'mime': mime_type})))
            
            conn.commit()
            return True
        except Exception as e:
            self.log_error(f"Failed to store {path}: {e}")
            return False
        finally:
            conn.close()

    def update_file_status(self, file_id: int, status: str, metadata: Dict = None):
        """Promotes a file's status."""
        conn = self._get_conn()
        cursor = conn.cursor()
        if metadata:
            meta_json = json.dumps(metadata)
            cursor.execute("UPDATE files SET status = ?, metadata = ? WHERE id = ?", (status, meta_json, file_id))
        else:
            cursor.execute("UPDATE files SET status = ? WHERE id = ?", (status, file_id))
        conn.commit()
        conn.close()

    # --- [NEW] Graph Methods ---

    def add_edge(self, source: str, target: str, weight: float = 1.0, relation: str = "dependency"):
        """Wiries two nodes together."""
        conn = self._get_conn()
        try:
            conn.execute("INSERT OR IGNORE INTO graph_edges (source, target, weight, relation) VALUES (?, ?, ?, ?)",
                         (source, target, weight, relation))
            conn.commit()
        except Exception as e:
            self.log_error(f"Edge Error: {e}")
        finally:
            conn.close()

    def log_unresolved_import(self, source_file: str, import_name: str):
        """Logs a broken link for the Validation Report."""
        conn = self._get_conn()
        conn.execute("INSERT INTO unresolved_imports (source_file, import_name, timestamp) VALUES (?, ?, ?)",
                     (source_file, import_name, time.time()))
        conn.commit()
        conn.close()
    
    def get_pending_files(self, limit: int = 100) -> List[Dict]:
        """Fetches files waiting for the Refinery."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT id, path, content, mime_type FROM files WHERE status = 'RAW' LIMIT ?", (limit,)).fetchall()
        conn.close()
        return [dict(row) for row in rows]
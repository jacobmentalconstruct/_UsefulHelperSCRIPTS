import sqlite3
import json
import time
import os
import uuid
import datetime
import struct
from pathlib import Path

# Try to import sqlite-vec (pip install sqlite-vec)
try:
    import sqlite_vec
except ImportError:
    sqlite_vec = None
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
        conn = sqlite3.connect(self.db_path)
        if sqlite_vec:
            try:
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                conn.enable_load_extension(False)
            except Exception as e:
                self.log_error(f"Failed to load sqlite-vec: {e}")
        return conn

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

        # 3.5 Vector Index (sqlite-vec)
        # Defaulting to 1024 dimensions (mxbai-embed-large). 
        # If you use a different model, this needs to match.
        if sqlite_vec:
            try:
                cursor.execute("CREATE VIRTUAL TABLE IF NOT EXISTS vec_items USING vec0(embedding float[1024])")
            except Exception as e:
                self.log_error(f"Vector Table Init Error: {e}")

        # 4. Graph Topology (The Neural Wiring)
        cursor.execute("CREATE TABLE IF NOT EXISTS graph_nodes (id TEXT PRIMARY KEY, type TEXT, label TEXT, data_json TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS graph_edges (source TEXT, target TEXT, relation TEXT, weight REAL)")

        # 5. Validation Logs
        cursor.execute("CREATE TABLE IF NOT EXISTS logs (timestamp REAL, level TEXT, message TEXT, context TEXT)")
        
        conn.commit()
        conn.close()
        
        # Initialize standard keys if new
        self.initialize_manifest()

    def initialize_manifest(self):
        """Populates the boot sector with standard UNCF headers."""
        if not self.get_manifest("cartridge_id"):
            self.set_manifest("schema_version", self.SCHEMA_VERSION)
            self.set_manifest("cartridge_id", str(uuid.uuid4()))
            self.set_manifest("created_at_utc", datetime.datetime.utcnow().isoformat())
            self.set_manifest("ragforge_version", "1.1.0")

    def set_manifest(self, key: str, value: Any):
        """Upsert metadata key."""
        conn = self._get_conn()
        val_str = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        conn.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", (key, val_str))
        conn.commit()
        conn.close()

    def get_manifest(self, key: str) -> Optional[str]:
        """Retrieve metadata key."""
        conn = self._get_conn()
        row = conn.execute("SELECT value FROM manifest WHERE key=?", (key,)).fetchone()
        conn.close()
        return row[0] if row else None

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

    # --- Vector Search ---
    def search_embeddings(self, query_vector: List[float], limit: int = 5) -> List[Dict]:
        """Performs semantic search using sqlite-vec."""
        if not sqlite_vec or not query_vector:
            return []

        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        results = []
        
        try:
            # Pack vector to binary if needed, but sqlite-vec usually handles raw lists in parameterized queries
            # dependent on the binding. We'll pass binary for safety if using standard bindings,
            # but typically raw list works with the extension's adapters. 
            # For now, we assume the extension handles the list->vector conversion.
            
            rows = conn.execute("""
                SELECT
                    rowid,
                    distance
                FROM vec_items
                WHERE embedding MATCH ?
                ORDER BY distance
                LIMIT ?
            """, (json.dumps(query_vector), limit)).fetchall()
            
            # Resolve back to chunks with VFS context
            for r in rows:
                chunk_id = r['rowid']
                # Join with files to get vfs_path
                query = """
                    SELECT c.*, f.vfs_path 
                    FROM chunks c 
                    JOIN files f ON c.file_id = f.id 
                    WHERE c.id=?
                """
                chunk = conn.execute(query, (chunk_id,)).fetchone()
                
                if chunk:
                    res = dict(chunk)
                    res['score'] = r['distance']
                    results.append(res)
                    
        except Exception as e:
            self.log_error(f"Vector Search Error: {e}")
        finally:
            conn.close()
            
        return results

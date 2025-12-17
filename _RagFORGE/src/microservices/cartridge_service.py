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
        # Set generous timeout (60s) for multi-threaded Ingest/Refinery contention
        conn = sqlite3.connect(self.db_path, timeout=60.0)
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
        
        # Enable WAL Mode: Allows concurrent Readers (Refinery) & Writers (Ingest)
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        
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
        """Populates the boot sector with strict RagFORGE Cartridge Schema (UNCF) v1.1."""
        if not self.get_manifest("cartridge_id"):
            now = datetime.datetime.utcnow().isoformat()

            # 1. Identity & Versioning
            self.set_manifest("schema_name", "ragforge_cartridge")
            self.set_manifest("schema_version", "1.1.0")
            self.set_manifest("cartridge_id", str(uuid.uuid4()))
            self.set_manifest("created_at_utc", now)
            self.set_manifest("created_by_app", "RagFORGE")

            # 2. Provenance / Sources
            # Agents can read this to understand where the content came from and what policies were used.
            self.set_manifest("sources", [])
            self.set_manifest("source_policies", {
                "binary_policy": "Extract Text",
                "web_depth": 0
            })

            # 3. Specs (Defaults - updated by RefineryService._stamp_specs)
            self.set_manifest("embedding_spec", {
                "provider": "unknown",
                "model": "pending_init",
                "dim": 0,
                "dtype": "unknown",
                "distance": "unknown"
            })
            self.set_manifest("chunking_spec", {
                "strategy": "semantic_hybrid",
                "python_ast": True,
                "generic_window": 1500
            })

            # 4. VFS + Content Stats (populated/updated over time)
            self.set_manifest("vfs", {
                "root_label": "",
                "directories": {"count": 0},
                "files": {
                    "count": 0,
                    "by_origin_type": {},
                    "by_mime": {}
                },
                "index_built": False
            })
            self.set_manifest("content_stats", {
                "chunks": {"count": 0},
                "vector_index": {
                    "enabled": True,
                    "table": "vec_items",
                    "dims": 0
                },
                "graph": {
                    "nodes": 0,
                    "edges": 0
                }
            })

            # 5. Capabilities Contract (what an agent can assume exists / how to navigate)
            self.set_manifest("capabilities", {
                "tables": {
                    "manifest": True,
                    "directories": True,
                    "files": True,
                    "chunks": True,
                    "vec_items": True,
                    "graph_nodes": True,
                    "graph_edges": True,
                    "logs": True
                },
                "navigation": {
                    "vfs_path": "files.vfs_path",
                    "directory_index": "directories.vfs_path",
                    "list_files_query": "SELECT vfs_path, mime_type, origin_type, status FROM files ORDER BY vfs_path",
                    "list_directories_query": "SELECT vfs_path, parent_path FROM directories ORDER BY vfs_path"
                },
                "retrieval": {
                    "raw_file_content_query": "SELECT content, blob_data, mime_type FROM files WHERE vfs_path=?",
                    "chunks_by_file_query": "SELECT chunk_index, name, type, start_line, end_line, content FROM chunks WHERE file_id=? ORDER BY chunk_index",
                    "vector_search": "sqlite-vec on vec_items if available"
                }
            })

            # 6. Status & Health
            self.set_manifest("cartridge_health", "FRESH")
            self.set_manifest("ingest_complete", False)
            self.set_manifest("refine_complete", False)
            self.set_manifest("last_ingest_at_utc", "")
            self.set_manifest("last_refine_at_utc", "")
            self.set_manifest("last_error", "")
            self.set_manifest("locks", {
                "write_lock_expected": False,
                "notes": "If DB locks occur, consider batching writes and shorter-lived connections."
            })

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

    def validate_cartridge(self) -> Dict[str, Any]:
        """Quality Control: Checks if the cartridge is Agent-Safe."""
        report = {"valid": True, "health": "OK", "errors": []}
        
        # 1. Check Required Keys
        # These are the minimum contract keys an agent needs to understand what it loaded.
        required = [
            "schema_name",
            "schema_version",
            "cartridge_id",
            "created_at_utc",
            "created_by_app",
            "embedding_spec",
            "chunking_spec",
            "capabilities"
        ]
        for key in required:
            if not self.get_manifest(key):
                report["valid"] = False
                report["errors"].append(f"Missing Manifest Key: {key}")
        
        # 2. Check Vector Index Presence
        conn = self._get_conn()
        try:
            # Check if vec_items table exists (sqlite-vec)
            conn.execute("SELECT count(*) FROM vec_items").fetchone()
        except Exception:
             report["errors"].append("Vector Index (vec_items) missing or not loaded.")
             # Not fatal for 'valid' but impacts capability
             report["health"] = "WARN_NO_VECTORS"
        finally:
            conn.close()
            
        return report

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

    # --- Agent-Friendly Helpers (No raw SQL required) ---
    def _coerce_bool(self, v: Any) -> bool:
        """Best-effort conversion for manifest values stored as strings."""
        if v is None:
            return False
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        return s in ("1", "true", "yes", "y", "on")

    def get_status_flags(self) -> Dict[str, Any]:
        """Returns key manifest status flags in a single call."""
        ingest_complete = self._coerce_bool(self.get_manifest("ingest_complete"))
        refine_complete = self._coerce_bool(self.get_manifest("refine_complete"))
        health = self.get_manifest("cartridge_health") or "UNKNOWN"
        return {
            "ingest_complete": ingest_complete,
            "refine_complete": refine_complete,
            "cartridge_health": health,
            "schema_name": self.get_manifest("schema_name") or "",
            "schema_version": self.get_manifest("schema_version") or "",
            "cartridge_id": self.get_manifest("cartridge_id") or ""
        }

    def list_files(self, prefix: str = "", status: Optional[str] = None, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Enumerate files in the cartridge (optionally filtered by VFS prefix and/or status)."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        try:
            sql = "SELECT id, vfs_path, origin_path, origin_type, mime_type, status, last_updated, metadata FROM files"
            clauses = []
            params = []

            if prefix:
                # Prefix match on portable path
                clauses.append("vfs_path LIKE ?")
                params.append(prefix.rstrip("/") + "/%")

            if status:
                clauses.append("status = ?")
                params.append(status)

            if clauses:
                sql += " WHERE " + " AND ".join(clauses)

            sql += " ORDER BY vfs_path"

            if limit is not None:
                sql += " LIMIT ?"
                params.append(int(limit))

            rows = conn.execute(sql, tuple(params)).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                # metadata is stored as JSON string
                try:
                    d["metadata"] = json.loads(d.get("metadata") or "{}")
                except Exception:
                    d["metadata"] = {}
                out.append(d)
            return out
        finally:
            conn.close()

    def get_file_record(self, vfs_path: str) -> Optional[Dict[str, Any]]:
        """Fetch a single file record by VFS path."""
        if not vfs_path:
            return None
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(
                "SELECT id, vfs_path, origin_path, origin_type, content, blob_data, mime_type, status, metadata, last_updated FROM files WHERE vfs_path = ?",
                (vfs_path,)
            ).fetchone()
            if not row:
                return None
            d = dict(row)
            try:
                d["metadata"] = json.loads(d.get("metadata") or "{}")
            except Exception:
                d["metadata"] = {}
            return d
        finally:
            conn.close()

    def list_directories(self, prefix: str = "") -> List[Dict[str, Any]]:
        """Enumerate directories in the cartridge VFS."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        try:
            if prefix:
                rows = conn.execute(
                    "SELECT id, vfs_path, parent_path, metadata FROM directories WHERE vfs_path LIKE ? ORDER BY vfs_path",
                    (prefix.rstrip("/") + "/%",)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, vfs_path, parent_path, metadata FROM directories ORDER BY vfs_path"
                ).fetchall()

            out = []
            for r in rows:
                d = dict(r)
                try:
                    d["metadata"] = json.loads(d.get("metadata") or "{}")
                except Exception:
                    d["metadata"] = {}
                out.append(d)
            return out
        finally:
            conn.close()

    def get_directory_tree(self, root: str = "") -> Dict[str, Any]:
        """Builds a nested directory tree starting at `root` ("" for full tree)."""
        dirs = self.list_directories(prefix=root) if root else self.list_directories()
        files = self.list_files(prefix=root) if root else self.list_files()

        # Tree nodes are dicts: {"_dirs": {name: node}, "_files": [file_records...]}
        def new_node():
            return {"_dirs": {}, "_files": []}

        tree = new_node()

        # Insert directories
        for d in dirs:
            path = (d.get("vfs_path") or "").strip("/")
            if not path:
                continue
            parts = path.split("/")
            cur = tree
            for p in parts:
                cur = cur["_dirs"].setdefault(p, new_node())

        # Insert files
        for f in files:
            path = (f.get("vfs_path") or "").strip("/")
            if not path:
                continue
            parts = path.split("/")
            fname = parts[-1]
            cur = tree
            for p in parts[:-1]:
                cur = cur["_dirs"].setdefault(p, new_node())
            # Store a light file record for tree browsing
            cur["_files"].append({
                "name": fname,
                "vfs_path": f.get("vfs_path"),
                "mime_type": f.get("mime_type"),
                "origin_type": f.get("origin_type"),
                "status": f.get("status")
            })

        return tree

    def get_status_summary(self) -> Dict[str, Any]:
        """Counts files by status and provides a quick cartridge overview."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute("SELECT status, COUNT(*) as n FROM files GROUP BY status").fetchall()
            by_status = {r["status"]: r["n"] for r in rows}

            dcnt = conn.execute("SELECT COUNT(*) FROM directories").fetchone()[0]
            fcnt = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            ccnt = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            ncnt = conn.execute("SELECT COUNT(*) FROM graph_nodes").fetchone()[0]
            ecnt = conn.execute("SELECT COUNT(*) FROM graph_edges").fetchone()[0]

            return {
                "directories": int(dcnt),
                "files": int(fcnt),
                "chunks": int(ccnt),
                "graph_nodes": int(ncnt),
                "graph_edges": int(ecnt),
                "files_by_status": by_status,
                "flags": self.get_status_flags()
            }
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





import os
import sqlite3
import time
import uuid
import difflib
import logging
import json
from pathlib import Path
from typing import List, Dict, Optional, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("Librarian")

class LibrarianMS:
    """
    The Factory Foreman: Manages the creation and 'sealing' of Cortex Cartridges (.db files).
    Ensures that every exported DB contains a 'Manifest' so external Agents know how to read it.
    """
    
    def __init__(self, storage_dir: str = "./cortex_dbs"):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    # --- KB Management ---

    def list_kbs(self) -> List[str]:
        if not self.storage_dir.exists():
            return []
        files = list(self.storage_dir.glob("*.db"))
        files.sort(key=os.path.getmtime, reverse=True)
        return [f.name for f in files]

    def create_kb(self, name: str) -> Dict[str, str]:
        safe_name = self._sanitize_name(name)
        db_path = self.storage_dir / safe_name
        
        if db_path.exists():
            raise FileExistsError(f"Knowledge Base '{safe_name}' already exists.")

        try:
            self._init_schema(db_path)
            return {"status": "success", "path": str(db_path), "name": safe_name}
        except Exception as e:
            if db_path.exists(): os.remove(db_path)
            raise e

    def delete_kb(self, name: str):
        db_path = self.storage_dir / name
        if db_path.exists():
            os.remove(db_path)
            # Clean up potential WAL/SHM files
            for ext in ['-wal', '-shm']:
                aux = self.storage_dir / (name + ext)
                if aux.exists(): os.remove(aux)

    def _init_schema(self, db_path: Path):
        """Initializes the Standard Cortex Schema."""
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        
        # 1. Manifest (The "Label" for the Agent)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS manifest (
                key TEXT PRIMARY KEY, 
                value TEXT
            )
        """)
        
        # 2. Graph (The Neural Structure)
        cursor.execute("CREATE TABLE IF NOT EXISTS graph_nodes (id TEXT PRIMARY KEY, type TEXT, label TEXT, data_json TEXT)")
        cursor.execute("CREATE TABLE IF NOT EXISTS graph_edges (source TEXT, target TEXT, weight REAL)")

        # 3. Files (The Artifacts)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,      -- Internal ID
                content TEXT,                   -- Full text snapshot
                origin_type TEXT DEFAULT 'filesystem', 
                origin_path TEXT,               
                vfs_path TEXT,                  -- Relative export path
                metadata TEXT DEFAULT '{}',     -- Tags/Authors
                last_updated TIMESTAMP,
                status TEXT DEFAULT 'indexed'
            )
        """)

        # 4. Chunks (The Vectors)
        # Note: We store embedding as a BLOB (JSON bytes) for maximum portability.
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER,
            chunk_index INTEGER,
            content TEXT,
            embedding BLOB,     -- JSON UTF-8 Bytes
            name TEXT,          
            type TEXT,          
            start_line INTEGER,
            end_line INTEGER,
            FOREIGN KEY(file_id) REFERENCES files(id)
        )
        """)

        # 5. Diff Log (History)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS diff_log (
                id TEXT PRIMARY KEY,
                file_path TEXT NOT NULL,
                timestamp TIMESTAMP,
                change_type TEXT,
                diff_blob TEXT,
                author TEXT
            )
        """)
        
        # Set Creation Timestamp + Standard Cartridge Manifest Defaults
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("created_at", str(time.time())))
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("schema_version", "1.0"))

        # Core identity + interpretation hints (so external Agents know what this DB *is*)
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("cartridge_id", str(uuid.uuid4())))
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("artifact_type", "unknown"))
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("artifact_profile", "{}"))
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("root_vfs", "/"))

        # Boot-strapping cards for RAG consumers
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("entrypoints", "[]"))
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("ingest_models", "{}"))
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("source_provenance", "{}"))
        
        conn.commit()
        conn.close()

    def update_manifest(self, db_name: str, key: str, value: str):
        """Updates the manifest. Used by IngestEngine to record Model Names."""
        db_path = self.storage_dir / db_name
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()
        conn.close()

    # --- File Versioning ---

    def update_file(self, db_name: str, file_path: str, new_content: str, 
                   author: str = "user", origin_type: str = "filesystem", 
                   origin_path: str = None, metadata: dict = None) -> Dict[str, Any]:
        """Updates a file and logs the diff."""
        db_path = self.storage_dir / db_name
        if not db_path.exists(): raise FileNotFoundError("KB not found")

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        now = time.time()
        meta_json = json.dumps(metadata) if metadata else "{}"

        try:
            cursor.execute("SELECT id, content FROM files WHERE path = ?", (file_path,))
            row = cursor.fetchone()

            if not row:
                # CREATE
                cursor.execute(
                    """INSERT INTO files 
                       (path, content, last_updated, origin_type, origin_path, vfs_path, metadata) 
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (file_path, new_content, now, origin_type, origin_path or file_path, file_path, meta_json)
                )
                self._log_diff(cursor, file_path, "CREATE", "[New File]", author, now)
                conn.commit()
                return {"status": "created", "path": file_path}

            # EDIT
            old_content = row['content'] or ""
            diff_text = self._compute_diff(file_path, old_content, new_content)
            
            if not diff_text:
                return {"status": "unchanged", "path": file_path}

            self._log_diff(cursor, file_path, "EDIT", diff_text, author, now)
            cursor.execute(
                "UPDATE files SET content = ?, last_updated = ?, metadata = ? WHERE path = ?",
                (new_content, now, meta_json, file_path)
            )
            conn.commit()
            return {"status": "updated", "path": file_path, "diff_size": len(diff_text)}

        finally:
            conn.close()

    def get_file_content(self, db_name: str, file_path: str) -> Optional[str]:
        db_path = self.storage_dir / db_name
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT content FROM files WHERE path = ?", (file_path,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else None

    def list_files_in_kb(self, db_name: str) -> List[str]:
        db_path = self.storage_dir / db_name
        if not db_path.exists(): return []
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        rows = cursor.execute("SELECT path FROM files ORDER BY path ASC").fetchall()
        conn.close()
        return [r[0] for r in rows]

    # --- Helpers ---

    def _compute_diff(self, path: str, old: str, new: str) -> str:
        old_lines = old.splitlines(keepends=True)
        new_lines = new.splitlines(keepends=True)
        diff_gen = difflib.unified_diff(
            old_lines, new_lines, 
            fromfile=f"a/{path}", tofile=f"b/{path}",
            lineterm=''
        )
        return "".join(diff_gen)

    def _log_diff(self, cursor, path, change_type, diff_text, author, timestamp):
        diff_id = str(uuid.uuid4())
        cursor.execute(
            "INSERT INTO diff_log (id, file_path, timestamp, change_type, diff_blob, author) VALUES (?, ?, ?, ?, ?, ?)",
            (diff_id, path, timestamp, change_type, diff_text, author)
        )

    def _sanitize_name(self, name: str) -> str:
        # Enforce .db extension strictly to ensure visibility in list_kbs
        if name.endswith('.db'):
            name = name[:-3]
        
        # Sanitize the base name (strip dots/special chars)
        clean_base = "".join(c for c in name if c.isalnum() or c in (' ', '_', '-')).strip()
        clean_base = clean_base.replace(' ', '_')
        
        return f"{clean_base}.db"



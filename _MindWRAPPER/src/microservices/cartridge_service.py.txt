import sqlite3
import json
import time
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from .base_service import BaseService

class CartridgeService(BaseService):
    """
    The Storage Manager.
    Manages the SQLite Cartridge format, including BLOB storage and ELT Status tracking.
    """
    
    def __init__(self, db_path: str):
        super().__init__("CartridgeService")
        self.db_path = Path(db_path)
        self._init_db()

    def _init_db(self):
        """Initializes the ELT Schema (Extract, Load, Transform)."""
        # Ensure parent folder exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # 1. Manifest (Metadata about the Cartridge itself)
        cursor.execute("CREATE TABLE IF NOT EXISTS manifest (key TEXT PRIMARY KEY, value TEXT)")
        
        # 2. Files (The Core Artifacts)
        # Note the 'blob_data' for binaries and 'status' for the workflow
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT UNIQUE NOT NULL,      -- Virtual path (e.g. src/app.py)
                content TEXT,                   -- Text content (if applicable)
                blob_data BLOB,                 -- Binary content (PDFs, Images)
                
                status TEXT DEFAULT 'RAW',      -- RAW, PENDING_TRIAGE, ENRICHED, ERROR
                mime_type TEXT,                 -- text/plain, application/pdf
                
                metadata TEXT DEFAULT '{}',     -- JSON Tags from the Neural Service
                last_updated TIMESTAMP
            )
        """)

        # 3. Chunks (Vectors)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_id INTEGER,
                chunk_index INTEGER,
                content TEXT,
                embedding BLOB,
                FOREIGN KEY(file_id) REFERENCES files(id)
            )
        """)
        
        conn.commit()
        conn.close()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def store_raw_file(self, path: str, content: str = None, blob: bytes = None, mime_type: str = "text/plain"):
        """
        The 'Vacuum' method. Dumps raw data into the DB.
        """
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO files (path, content, blob_data, mime_type, status, last_updated)
                VALUES (?, ?, ?, ?, 'RAW', ?)
            """, (path, content, blob, mime_type, time.time()))
            conn.commit()
            return True
        except Exception as e:
            self.log_error(f"Failed to store {path}: {e}")
            return False
        finally:
            conn.close()

    def get_pending_files(self, limit: int = 100) -> List[Dict]:
        """Fetches files waiting for the Refinery."""
        conn = self._get_conn()
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        rows = cursor.execute(
            "SELECT id, path, content, mime_type FROM files WHERE status = 'RAW' LIMIT ?", 
            (limit,)
        ).fetchall()
        
        conn.close()
        return [dict(row) for row in rows]

    def update_file_status(self, file_id: int, status: str, metadata: Dict = None):
        """Promotes a file's status (e.g., RAW -> ENRICHED)."""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        if metadata:
            meta_json = json.dumps(metadata)
            cursor.execute("UPDATE files SET status = ?, metadata = ? WHERE id = ?", (status, meta_json, file_id))
        else:
            cursor.execute("UPDATE files SET status = ? WHERE id = ?", (status, file_id))
            
        conn.commit()
        conn.close()

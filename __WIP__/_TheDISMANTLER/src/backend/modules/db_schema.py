"""
SQLite schema initialization for the Dismantler's context store.
Provides a lightweight knowledge layer for the sliding-window context system.
"""
import sqlite3
import os

DB_FILENAME = "_dismantler_context.db"


def get_db_path(project_root=None):
    """Resolve the database file path relative to the project root."""
    if project_root is None:
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    return os.path.join(project_root, DB_FILENAME)


def get_connection(db_path=None):
    """Open a connection with WAL mode and row-factory enabled."""
    db_path = db_path or get_db_path()
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path=None):
    """
    Create the schema tables if they don't exist.
    Tables:
        source_files  – tracked files with content hashes
        chunks        – semantic code chunks tied to files
        chunk_meta    – enriched per-chunk metadata (decorators, signatures,
                        call targets, raises, ref counts) for Scout triage
        context_log   – query history for the sliding window
        file_manifest – compact structural manifest per file (Surgeon-Agent)
    """
    conn = get_connection(db_path)
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS source_files (
            file_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            path        TEXT    UNIQUE NOT NULL,
            name        TEXT    NOT NULL,
            language    TEXT,
            content_hash TEXT   NOT NULL,
            line_count  INTEGER DEFAULT 0,
            last_indexed TEXT
        );

        CREATE TABLE IF NOT EXISTS chunks (
            chunk_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id     INTEGER NOT NULL REFERENCES source_files(file_id),
            chunk_type  TEXT    NOT NULL DEFAULT 'code',
            name        TEXT,
            start_line  INTEGER NOT NULL,
            end_line    INTEGER NOT NULL,
            content     TEXT    NOT NULL,
            token_est   INTEGER DEFAULT 0,
            depth       INTEGER DEFAULT 0,
            UNIQUE(file_id, start_line, end_line)
        );

        CREATE TABLE IF NOT EXISTS context_log (
            log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id     INTEGER REFERENCES source_files(file_id),
            cursor_line INTEGER,
            window_start INTEGER,
            window_end  INTEGER,
            timestamp   TEXT    DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS file_manifest (
            manifest_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id      INTEGER NOT NULL REFERENCES source_files(file_id) ON DELETE CASCADE,
            manifest_text TEXT   NOT NULL,
            built_at     TEXT    DEFAULT (datetime('now')),
            UNIQUE(file_id)
        );

        CREATE TABLE IF NOT EXISTS chunk_meta (
            chunk_id    INTEGER PRIMARY KEY REFERENCES chunks(chunk_id) ON DELETE CASCADE,
            decorators  TEXT,
            signature   TEXT,
            return_type TEXT,
            calls       TEXT,
            raises      TEXT,
            ref_count   INTEGER DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_chunks_file ON chunks(file_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_lines ON chunks(file_id, start_line, end_line);
        CREATE INDEX IF NOT EXISTS idx_manifest_file ON file_manifest(file_id);
    """)

    conn.commit()
    conn.close()

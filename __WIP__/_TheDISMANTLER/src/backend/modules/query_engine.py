"""
QueryEngine – Safe SQL query interface for the Dismantler's SQLite store.
Acts as the boundary between the BackendEngine and db_schema.py.
No UI dependencies. All errors returned as structured dicts.
"""
from backend.modules.db_schema import get_connection


class QueryEngine:
    """
    Provides high-level, parameterized query methods over the context database.
    All public methods return plain dicts/lists (never raw cursor objects).
    """

    def __init__(self, db_path=None):
        self.db_path = db_path

    # ── file queries ────────────────────────────────────────

    def list_source_files(self):
        """Return all indexed source files with metadata."""
        conn = get_connection(self.db_path)
        rows = conn.execute(
            """
            SELECT file_id, path, name, language, content_hash, line_count, last_indexed
            FROM source_files
            ORDER BY name
            """
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_file_by_path(self, path):
        """Lookup a single file by path."""
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM source_files WHERE path=?", (path,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_file_by_id(self, file_id):
        """Lookup a single file by ID."""
        conn = get_connection(self.db_path)
        row = conn.execute(
            "SELECT * FROM source_files WHERE file_id=?", (file_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    # ── chunk queries ───────────────────────────────────────

    def get_chunks_for_file(self, file_id):
        """Return all chunks belonging to a file, ordered by line."""
        conn = get_connection(self.db_path)
        rows = conn.execute(
            """
            SELECT chunk_id, chunk_type, name, start_line, end_line, content, token_est, depth
            FROM chunks
            WHERE file_id=?
            ORDER BY start_line
            """,
            (file_id,),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_chunk_detail(self, chunk_id):
        """Return full detail for a single chunk, including its parent file."""
        conn = get_connection(self.db_path)
        row = conn.execute(
            """
            SELECT c.*, sf.path, sf.name AS file_name, sf.language
            FROM chunks c
            JOIN source_files sf ON c.file_id = sf.file_id
            WHERE c.chunk_id=?
            """,
            (chunk_id,),
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_chunk_neighbors(self, chunk_id, radius=2):
        """Return chunks adjacent to the given chunk (same file)."""
        detail = self.get_chunk_detail(chunk_id)
        if not detail:
            return []

        conn = get_connection(self.db_path)
        rows = conn.execute(
            """
            SELECT chunk_id, chunk_type, name, start_line, end_line, token_est
            FROM chunks
            WHERE file_id = (SELECT file_id FROM chunks WHERE chunk_id=?)
              AND chunk_id != ?
            ORDER BY ABS(start_line - ?)
            LIMIT ?
            """,
            (chunk_id, chunk_id, detail["start_line"], radius * 2),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── search queries ──────────────────────────────────────

    def search_content(self, query, limit=20):
        """LIKE-based content search across all chunks."""
        conn = get_connection(self.db_path)
        rows = conn.execute(
            """
            SELECT c.chunk_id, c.name, c.chunk_type, c.start_line, c.end_line,
                   c.content, c.token_est,
                   sf.path, sf.name AS file_name
            FROM chunks c
            JOIN source_files sf ON c.file_id = sf.file_id
            WHERE c.content LIKE ?
            ORDER BY c.token_est ASC
            LIMIT ?
            """,
            (f"%{query}%", limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def search_by_name(self, name, limit=20):
        """Search chunks by their definition name."""
        conn = get_connection(self.db_path)
        rows = conn.execute(
            """
            SELECT c.chunk_id, c.name, c.chunk_type, c.start_line, c.end_line,
                   c.token_est, sf.path, sf.name AS file_name
            FROM chunks c
            JOIN source_files sf ON c.file_id = sf.file_id
            WHERE c.name LIKE ?
            ORDER BY c.name
            LIMIT ?
            """,
            (f"%{name}%", limit),
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    # ── statistics ──────────────────────────────────────────

    def get_stats(self):
        """Return summary statistics about the indexed store."""
        conn = get_connection(self.db_path)
        stats = {
            "files": conn.execute("SELECT COUNT(*) FROM source_files").fetchone()[0],
            "chunks": conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
            "total_tokens": conn.execute(
                "SELECT COALESCE(SUM(token_est), 0) FROM chunks"
            ).fetchone()[0],
            "context_queries": conn.execute(
                "SELECT COUNT(*) FROM context_log"
            ).fetchone()[0],
        }
        conn.close()
        return stats

    # ── reconstruction ──────────────────────────────────────

    def reconstruct_file(self, file_id):
        """
        Reconstruct a file's full content from its chunks.
        Returns the content as a single string ordered by line number.
        """
        chunks = self.get_chunks_for_file(file_id)
        if not chunks:
            return None
        return "\n".join(ch["content"] for ch in chunks)

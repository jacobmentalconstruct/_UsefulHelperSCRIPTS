"""
Sliding-window context module.
Provides the AI with focused code context based on the user's active cursor
position, backed by the SQLite chunk store.
"""
import hashlib
from backend.modules.db_schema import get_connection, init_db


class SlidingWindow:
    """
    Manages a cursor-aware context window over indexed source files.
    The window expands outward from the cursor line, collecting
    neighbouring chunks until a token budget is met.
    """

    DEFAULT_BUDGET = 2048  # max tokens to include in context

    def __init__(self, db_path=None):
        self.db_path = db_path
        init_db(self.db_path)

    # ── indexing ────────────────────────────────────────────

    def index_file(self, path, content, language=None, chunks=None):
        """
        Register or update a source file and its chunks.
        `chunks` is a list of dicts: {name, start_line, end_line, content, chunk_type, depth}
        If chunks is None, the file is stored as a single chunk.
        """
        conn = get_connection(self.db_path)
        cur = conn.cursor()

        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        name = path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        lines = content.count("\n") + 1

        cur.execute(
            """
            INSERT INTO source_files (path, name, language, content_hash, line_count, last_indexed)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(path) DO UPDATE SET
                content_hash=excluded.content_hash,
                line_count=excluded.line_count,
                last_indexed=excluded.last_indexed
            """,
            (path, name, language, content_hash, lines),
        )
        file_id = cur.execute(
            "SELECT file_id FROM source_files WHERE path=?", (path,)
        ).fetchone()["file_id"]

        # Replace existing chunks
        cur.execute("DELETE FROM chunks WHERE file_id=?", (file_id,))

        if chunks:
            for ch in chunks:
                token_est = len(ch["content"].split())
                cur.execute(
                    """
                    INSERT INTO chunks (file_id, chunk_type, name, start_line, end_line, content, token_est, depth)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        file_id,
                        ch.get("chunk_type", "code"),
                        ch.get("name"),
                        ch["start_line"],
                        ch["end_line"],
                        ch["content"],
                        token_est,
                        ch.get("depth", 0),
                    ),
                )
        else:
            # Store the whole file as one chunk
            token_est = len(content.split())
            cur.execute(
                """
                INSERT INTO chunks (file_id, chunk_type, name, start_line, end_line, content, token_est)
                VALUES (?, 'file', ?, 1, ?, ?, ?)
                """,
                (file_id, name, lines, content, token_est),
            )

        conn.commit()
        conn.close()

    # ── context retrieval ───────────────────────────────────

    def get_context(self, file_path, cursor_line, budget=None):
        """
        Build a context window around `cursor_line` for the given file.
        Returns a list of chunk dicts sorted by proximity to the cursor,
        staying within the token budget.
        """
        budget = budget or self.DEFAULT_BUDGET
        conn = get_connection(self.db_path)
        cur = conn.cursor()

        row = cur.execute(
            "SELECT file_id FROM source_files WHERE path=?", (file_path,)
        ).fetchone()
        if not row:
            conn.close()
            return []

        file_id = row["file_id"]

        # Fetch all chunks for this file, sorted by distance from cursor
        chunks = cur.execute(
            """
            SELECT chunk_id, chunk_type, name, start_line, end_line, content, token_est, depth
            FROM chunks
            WHERE file_id=?
            ORDER BY ABS(start_line - ?) + ABS(end_line - ?)
            """,
            (file_id, cursor_line, cursor_line),
        ).fetchall()

        # Log the query
        if chunks:
            first = chunks[0]
            cur.execute(
                """
                INSERT INTO context_log (file_id, cursor_line, window_start, window_end)
                VALUES (?, ?, ?, ?)
                """,
                (file_id, cursor_line, first["start_line"], first["end_line"]),
            )
            conn.commit()

        # Collect chunks within budget
        result = []
        spent = 0
        for ch in chunks:
            if spent + ch["token_est"] > budget:
                continue
            spent += ch["token_est"]
            result.append(dict(ch))

        # Return in file order
        result.sort(key=lambda c: c["start_line"])

        conn.close()
        return result

    def search_chunks(self, query, limit=10):
        """Simple LIKE-based chunk search across all files."""
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT c.*, sf.path, sf.name as file_name
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

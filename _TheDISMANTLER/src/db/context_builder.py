"""
ContextBuilder – Pure data extraction layer for the Warm Constrained Swarm.

Responsibilities:
  1. Generate the Metadata Manifest (structural skeleton map) from the DB
  2. Fetch raw chunks by file path or by specific chunk IDs
  3. Apply Spatial Anchoring: prepend absolute line numbers to every code line
     using enumerate() on chunk content — no new tables, purely on-the-fly

This module has ZERO awareness of LLM clients or orchestration logic.
It only reads the SQLite database and formats data for downstream consumers.

Database tables consumed:
  - source_files  (file_id, path, name, language, line_count)
  - chunks        (chunk_id, file_id, chunk_type, name, start_line, end_line, content, token_est, depth)
  - file_manifest (file_id, manifest_text)
"""

from backend.modules.db_schema import get_connection


class ContextBuilder:
    """
    Stateless context extraction and formatting.
    All methods accept an optional db_path for testability.
    """

    # ── Manifest Retrieval ────────────────────────────────────

    @staticmethod
    def get_manifest(file_path: str, db_path: str = None) -> str:
        """
        Retrieve the pre-built structural manifest for a file.

        Returns the manifest text string, or an empty string if the
        file has not been curated yet. Never returns None — downstream
        consumers can always safely embed the result in a prompt.

        Args:
            file_path: Absolute path to the source file.
            db_path:   Optional override for the SQLite database location.
        """
        conn = get_connection(db_path)
        try:
            row = conn.execute(
                """
                SELECT fm.manifest_text
                FROM file_manifest fm
                JOIN source_files sf ON fm.file_id = sf.file_id
                WHERE sf.path = ?
                """,
                (file_path,),
            ).fetchone()
            return row["manifest_text"] if row else ""
        finally:
            conn.close()

    # ── Manifest Generation (from live DB data) ───────────────

    @staticmethod
    def build_manifest_from_db(file_path: str, db_path: str = None) -> str:
        """
        Dynamically generate a lightweight Skeleton Map (<500 tokens)
        from the chunks table without requiring a prior curate pass.

        This queries the chunks table directly and formats the structural
        overview. Useful when the stored file_manifest is stale or absent.

        Format:
            FILE: filename.py  (python, 340 lines)
            STRUCTURE:
              [class]  ClassName              L18–340
                [def]  method_name            L26–57

        Args:
            file_path: Absolute path to the source file.
            db_path:   Optional database path override.

        Returns:
            Formatted manifest string, or empty string if file not indexed.
        """
        conn = get_connection(db_path)
        try:
            # Fetch file metadata
            file_row = conn.execute(
                "SELECT file_id, name, language, line_count FROM source_files WHERE path = ?",
                (file_path,),
            ).fetchone()
            if not file_row:
                return ""

            file_id = file_row["file_id"]
            file_name = file_row["name"]
            language = file_row["language"] or "unknown"
            line_count = file_row["line_count"] or 0

            # Fetch all chunks ordered by position (file order)
            chunks = conn.execute(
                """
                SELECT name, chunk_type, start_line, end_line, depth
                FROM chunks
                WHERE file_id = ?
                ORDER BY start_line, depth
                """,
                (file_id,),
            ).fetchall()

            # ── Format the skeleton map ──
            parts = [f"FILE: {file_name}  ({language}, {line_count} lines)"]

            if chunks:
                parts.append("STRUCTURE:")
                for ch in chunks:
                    indent = "  " * (ch["depth"] + 1)
                    kind = _kind_label(ch["chunk_type"])
                    name = ch["name"] or "(anonymous)"
                    s = ch["start_line"]
                    e = ch["end_line"]
                    parts.append(f"{indent}[{kind}]  {name:<28s} L{s}\u2013{e}")
            else:
                parts.append("STRUCTURE: (no chunks indexed)")

            return "\n".join(parts)

        finally:
            conn.close()

    # ── Chunk Retrieval ───────────────────────────────────────

    @staticmethod
    def get_all_chunks(file_path: str, db_path: str = None) -> list:
        """
        Fetch every chunk for a file, ordered by position in file.

        Returns a list of dicts:
            [{chunk_id, chunk_type, name, start_line, end_line,
              content, token_est, depth}, ...]

        Args:
            file_path: Absolute path to the source file.
            db_path:   Optional database path override.
        """
        conn = get_connection(db_path)
        try:
            file_row = conn.execute(
                "SELECT file_id FROM source_files WHERE path = ?",
                (file_path,),
            ).fetchone()
            if not file_row:
                return []

            rows = conn.execute(
                """
                SELECT chunk_id, chunk_type, name, start_line, end_line,
                       content, token_est, depth
                FROM chunks
                WHERE file_id = ?
                ORDER BY start_line
                """,
                (file_row["file_id"],),
            ).fetchall()
            return [dict(r) for r in rows]

        finally:
            conn.close()

    @staticmethod
    def get_chunks_by_ids(chunk_ids: list, db_path: str = None) -> list:
        """
        Fetch specific chunks by their chunk_id values.

        Returns chunks in file order (sorted by start_line),
        regardless of the order of input IDs.

        Args:
            chunk_ids: List of integer chunk_id values.
            db_path:   Optional database path override.
        """
        if not chunk_ids:
            return []

        conn = get_connection(db_path)
        try:
            placeholders = ",".join("?" for _ in chunk_ids)
            rows = conn.execute(
                f"""
                SELECT chunk_id, chunk_type, name, start_line, end_line,
                       content, token_est, depth
                FROM chunks
                WHERE chunk_id IN ({placeholders})
                ORDER BY start_line
                """,
                chunk_ids,
            ).fetchall()
            return [dict(r) for r in rows]

        finally:
            conn.close()

    @staticmethod
    def get_chunk_index(file_path: str, db_path: str = None) -> list:
        """
        Lightweight index: returns chunk metadata WITHOUT the content field.
        Designed for the Scout model to decide which chunks to request.

        Returns:
            [{chunk_id, name, chunk_type, start_line, end_line, token_est, depth}, ...]

        Args:
            file_path: Absolute path to the source file.
            db_path:   Optional database path override.
        """
        conn = get_connection(db_path)
        try:
            file_row = conn.execute(
                "SELECT file_id FROM source_files WHERE path = ?",
                (file_path,),
            ).fetchone()
            if not file_row:
                return []

            rows = conn.execute(
                """
                SELECT chunk_id, chunk_type, name, start_line, end_line,
                       token_est, depth
                FROM chunks
                WHERE file_id = ?
                ORDER BY start_line
                """,
                (file_row["file_id"],),
            ).fetchall()
            return [dict(r) for r in rows]

        finally:
            conn.close()

    # ── Spatial Anchoring ─────────────────────────────────────

    @staticmethod
    def anchor_chunks(chunks: list) -> list:
        """
        Apply spatial anchoring: prepend absolute line numbers to every
        code line in each chunk using enumerate().

        Input chunk dict must have 'content' (str) and 'start_line' (int).
        Returns a NEW list of chunk dicts — originals are not mutated.

        Example transform:
            Input content:   "def load_file(self, path):\\n    return"
            start_line:      66
            Output content:  "66: def load_file(self, path):\\n67:     return"

        Args:
            chunks: List of chunk dicts with 'content' and 'start_line' keys.

        Returns:
            New list of chunk dicts with line-numbered content.
        """
        anchored = []
        for ch in chunks:
            lines = ch["content"].splitlines(keepends=False)
            start = ch["start_line"]

            numbered_lines = [
                f"{start + i}: {line}"
                for i, line in enumerate(lines)
            ]

            ch_copy = dict(ch)
            ch_copy["content"] = "\n".join(numbered_lines)
            anchored.append(ch_copy)

        return anchored

    @staticmethod
    def anchor_single(content: str, start_line: int) -> str:
        """
        Convenience: anchor a single block of text from a known start line.
        Returns the line-numbered string directly.

        Args:
            content:    Raw source code string.
            start_line: The 1-based line number of the first line.
        """
        lines = content.splitlines(keepends=False)
        return "\n".join(
            f"{start_line + i}: {line}"
            for i, line in enumerate(lines)
        )

    # ── Prompt Formatting Helpers ─────────────────────────────

    @staticmethod
    def format_context_block(chunks: list, anchored: bool = True) -> str:
        """
        Format a list of chunks into a [CONTEXT] block string ready
        for prompt injection.

        When anchored=True (default), line numbers are prepended
        to every code line before formatting.

        Args:
            chunks:   List of chunk dicts.
            anchored: Whether to apply spatial anchoring. Default True.

        Returns:
            Formatted string: "[CONTEXT]\\n...\\n[/CONTEXT]"
        """
        if not chunks:
            return ""

        if anchored:
            chunks = ContextBuilder.anchor_chunks(chunks)

        sections = []
        for ch in chunks:
            header = f"## {ch.get('name', 'chunk')} (L{ch['start_line']}\u2013{ch['end_line']})"
            sections.append(f"{header}\n{ch['content']}")

        body = "\n---\n".join(sections)
        return f"[CONTEXT]\n{body}\n[/CONTEXT]"

    @staticmethod
    def format_full_prompt(
        query: str,
        manifest: str = "",
        chunks: list = None,
        system_prompt: str = None,
    ) -> str:
        """
        Assemble a complete prompt string with all layers:
        [system] → [FILE MANIFEST] → [CONTEXT with anchoring] → [query]

        This is a pure formatting function with no side effects.

        Args:
            query:         The user's chat message.
            manifest:      Structural manifest string (may be empty).
            chunks:        List of chunk dicts to include as context.
            system_prompt: Optional system-level instruction block.

        Returns:
            Fully formatted prompt string.
        """
        parts = []

        if system_prompt:
            parts.append(system_prompt)

        if manifest:
            parts.append(f"[FILE MANIFEST]\n{manifest}\n[/FILE MANIFEST]")

        if chunks:
            parts.append(ContextBuilder.format_context_block(chunks, anchored=True))

        parts.append(query)
        return "\n\n".join(parts)


# ── Module-level helpers (not exported) ───────────────────────

# Kind label mapping (matches manifest_engine.py conventions)
_KIND_MAP = {
    "class":    "class",
    "function": "def",
    "method":   "def",
    "def":      "def",
    "async":    "async",
    "module":   "module",
    "file":     "file",
    "code":     "code",
}


def _kind_label(chunk_type: str) -> str:
    """Map a chunk_type to its display label."""
    return _KIND_MAP.get(chunk_type, chunk_type or "?")

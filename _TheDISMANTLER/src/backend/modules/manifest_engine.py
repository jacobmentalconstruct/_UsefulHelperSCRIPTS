"""
ManifestEngine – Builds a compact, plain-text structural manifest of a source
file from its pre-computed AST hierarchy.

The manifest is the "Anatomical Map" in the Surgeon-Agent architecture:
a ~300-500 token overview always prepended to AI prompts so the model knows
the full shape of the file before reading any chunk.

No AI calls.  No disk reads.  Pure function over existing data.
"""
import re
import os

# Max characters per gist line (truncated with ellipsis)
_GIST_MAX = 72

# Import-extraction patterns per language (regex on full source)
_IMPORT_PATTERNS = {
    "python":     re.compile(r"^(?:import|from)\s+([\w.]+)", re.MULTILINE),
    "javascript": re.compile(r"""(?:import|require)\s*[\({'"]([\w./]+)""", re.MULTILINE),
    "typescript": re.compile(r"""(?:import|require)\s*[\({'"]([\w./]+)""", re.MULTILINE),
    "java":       re.compile(r"^import\s+([\w.]+);", re.MULTILINE),
    "go":         re.compile(r'"([\w./]+)"', re.MULTILINE),
    "rust":       re.compile(r"^use\s+([\w:]+)", re.MULTILINE),
}

# Human-readable abbreviations for chunk kind labels
_KIND_LABELS = {
    "class":    "class",
    "function": "def",
    "method":   "def",
    "def":      "def",
    "async":    "async",
    "module":   "module",
    "file":     "file",
}


class ManifestEngine:
    """Builds the file manifest from AST hierarchy + raw source."""

    @staticmethod
    def build(file_path: str, language: str, content: str, hierarchy: list) -> str:
        """
        Build a compact structural manifest string.

        Args:
            file_path:  Absolute or relative path to the source file.
            language:   Language string (e.g. "python", "javascript").
            content:    Raw source text.
            hierarchy:  List of AST node dicts produced by get_hierarchy_flat_from_source.
                        Each dict: {name, kind, start_line, end_line, depth}

        Returns:
            A plain-text manifest string suitable for prepending to an AI prompt.
        """
        lines_list = content.splitlines()
        total_lines = len(lines_list)
        file_name = os.path.basename(file_path)

        # ── Header ──────────────────────────────────────────
        parts = [f"FILE: {file_name}  ({language or 'unknown'}, {total_lines} lines)"]

        # ── Imports ─────────────────────────────────────────
        imports = ManifestEngine._extract_imports(content, language)
        if imports:
            # Keep it compact — first 10 unique top-level module names
            parts.append(f"IMPORTS: {', '.join(imports[:10])}")

        # ── Structure ────────────────────────────────────────
        if hierarchy:
            parts.append("STRUCTURE:")
            for node in hierarchy:
                indent   = "  " * (node.get("depth", 0) + 1)
                kind_lbl = _KIND_LABELS.get(node.get("kind", ""), node.get("kind", "?"))
                name     = node.get("name", "?")
                s_line   = node.get("start_line", 0)
                e_line   = node.get("end_line", 0)
                gist     = ManifestEngine._extract_gist(lines_list, s_line, e_line)
                gist_str = f"  \u2014 {gist}" if gist else ""
                parts.append(
                    f"{indent}[{kind_lbl}]  {name:<28s} L{s_line}\u2013{e_line}{gist_str}"
                )
        else:
            parts.append("STRUCTURE: (no AST nodes detected)")

        return "\n".join(parts)

    # ── helpers ─────────────────────────────────────────────

    @staticmethod
    def _extract_imports(content: str, language: str) -> list:
        """Extract a deduplicated list of top-level imported module names."""
        pattern = _IMPORT_PATTERNS.get(language or "")
        if not pattern:
            return []
        names = []
        seen  = set()
        for m in pattern.finditer(content):
            # Take only the first component (e.g. "os.path" → "os")
            top = m.group(1).split(".")[0].split("/")[-1].strip()
            if top and top not in seen:
                seen.add(top)
                names.append(top)
        return names

    @staticmethod
    def _extract_gist(lines_list: list, start_line: int, end_line: int) -> str:
        """
        Extract a one-line description from the node's body:
        1. First triple-quoted docstring line
        2. First single-quoted / hash comment line inside the body
        3. Empty string if nothing found
        """
        # Body starts on the line *after* the def/class signature
        body_start = start_line       # 1-based; index = start_line (0-based body)
        body_end   = min(end_line, start_line + 12)  # scan first 12 lines

        for i in range(body_start, body_end):
            if i >= len(lines_list):
                break
            stripped = lines_list[i].strip()

            # Triple-quote docstring (opening line)
            if stripped.startswith(('"""', "'''")):
                text = stripped.lstrip('"\'').rstrip('"\'').strip()
                if text:
                    return text[:_GIST_MAX] + ("…" if len(text) > _GIST_MAX else "")

            # Single-line hash comment
            if stripped.startswith("#"):
                text = stripped.lstrip("#").strip()
                if text and not text.startswith("!"):  # skip shebangs
                    return text[:_GIST_MAX] + ("…" if len(text) > _GIST_MAX else "")

        return ""

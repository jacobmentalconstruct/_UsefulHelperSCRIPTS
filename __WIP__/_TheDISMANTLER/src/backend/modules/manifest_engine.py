"""
ManifestEngine – Builds a compact, enriched structural manifest of a source
file from its pre-computed AST hierarchy and walker metadata.

The manifest is the "Anatomical Map" in the Surgeon-Agent architecture:
a ~300-700 token overview always prepended to AI prompts so the model knows
the full shape of the file before reading any chunk.

Enriched data (when walker nodes are provided):
  - Function signatures with parameter names and type annotations
  - Decorator annotations (@staticmethod, @property, @dataclass, etc.)
  - Return type annotations
  - CALLS section: which functions call which (wiring diagram)
  - RAISES section: which exceptions each function can raise
  - Reference counts: how many other nodes reference each node

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
    """Builds the file manifest from AST hierarchy + walker metadata."""

    @staticmethod
    def build(
        file_path: str,
        language: str,
        content: str,
        hierarchy: list,
        walker_nodes: list = None,
        edges: list = None,
    ) -> str:
        """
        Build a compact structural manifest string.

        Args:
            file_path:     Absolute or relative path to the source file.
            language:      Language string (e.g. "python", "javascript").
            content:       Raw source text.
            hierarchy:     List of AST node dicts from get_hierarchy_flat_from_source.
                           Each dict: {name, kind, start_line, end_line, depth}
            walker_nodes:  Optional list of ASTNode objects (or dicts via .to_dict())
                           from ASTNodeWalker. When provided, enriches manifest with
                           signatures, decorators, return types, raises.
            edges:         Optional list of edge dicts from ASTNodeWalker:
                           {source, target, kind} where kind = "calls" | "inherits"

        Returns:
            A plain-text manifest string suitable for prepending to an AI prompt.
        """
        lines_list = content.splitlines()
        total_lines = len(lines_list)
        file_name = os.path.basename(file_path)

        # Build a lookup from walker nodes keyed by (name, start_line)
        # so we can pair enriched data with hierarchy entries
        node_lookup = {}
        if walker_nodes:
            node_lookup = ManifestEngine._build_node_lookup(walker_nodes)

        # Compute per-node reference counts from edges
        ref_counts = {}
        if edges:
            ref_counts = ManifestEngine._compute_ref_counts(edges)

        # ── Header ──────────────────────────────────────────
        parts = [f"FILE: {file_name}  ({language or 'unknown'}, {total_lines} lines)"]

        # ── Imports ─────────────────────────────────────────
        imports = ManifestEngine._extract_imports(content, language)
        if imports:
            parts.append(f"IMPORTS: {', '.join(imports[:10])}")

        # ── Structure (enriched) ────────────────────────────
        if hierarchy:
            parts.append("STRUCTURE:")
            for node in hierarchy:
                indent   = "  " * (node.get("depth", 0) + 1)
                kind_lbl = _KIND_LABELS.get(node.get("kind", ""), node.get("kind", "?"))
                name     = node.get("name", "?")
                s_line   = node.get("start_line", 0)
                e_line   = node.get("end_line", 0)

                # Try to get enriched data from walker
                enriched = node_lookup.get((name, s_line), {})

                # Signature: show params if available
                sig = enriched.get("signature", "")
                ret = enriched.get("return_type", "")
                decorators = enriched.get("decorators", [])

                # Build the name display with optional signature
                if sig and kind_lbl in ("def", "async"):
                    # Truncate very long signatures
                    sig_display = sig if len(sig) <= 50 else sig[:47] + "..."
                    name_display = f"{name}({sig_display})"
                else:
                    name_display = name

                # Return type suffix
                ret_str = f" \u2192 {ret}" if ret else ""

                # Decorator prefix (compact)
                dec_str = ""
                if decorators:
                    dec_str = "  " + " ".join(f"@{d}" for d in decorators)

                # Reference count
                rc = ref_counts.get(name, 0)
                rc_str = f"  refs={rc}" if rc > 0 else ""

                # Gist from source
                gist = ManifestEngine._extract_gist(lines_list, s_line, e_line)
                gist_str = f"  \u2014 {gist}" if gist else ""

                parts.append(
                    f"{indent}[{kind_lbl}]  {name_display}{ret_str}"
                    f"  L{s_line}\u2013{e_line}{rc_str}{dec_str}{gist_str}"
                )
        else:
            parts.append("STRUCTURE: (no AST nodes detected)")

        # ── Calls wiring diagram ────────────────────────────
        if edges:
            calls_section = ManifestEngine._build_calls_section(edges)
            if calls_section:
                parts.append(calls_section)

            # Inheritance section
            inherits_section = ManifestEngine._build_inherits_section(edges)
            if inherits_section:
                parts.append(inherits_section)

        # ── Raises section ──────────────────────────────────
        if walker_nodes:
            raises_section = ManifestEngine._build_raises_section(walker_nodes)
            if raises_section:
                parts.append(raises_section)

        return "\n".join(parts)

    # ── enrichment helpers ─────────────────────────────────

    @staticmethod
    def _build_node_lookup(walker_nodes: list) -> dict:
        """
        Build a lookup dict from walker ASTNode objects.
        Keyed by (name, start_line) tuple for reliable matching
        against hierarchy entries.
        """
        lookup = {}
        for n in walker_nodes:
            # Support both ASTNode objects and dicts
            if hasattr(n, "name"):
                key = (n.name, n.start_line)
                lookup[key] = {
                    "signature":   getattr(n, "signature", ""),
                    "return_type": getattr(n, "return_type", ""),
                    "decorators":  getattr(n, "decorators", []),
                    "references":  list(getattr(n, "references", set())),
                    "raises":      getattr(n, "raises", []),
                }
            elif isinstance(n, dict):
                key = (n.get("name"), n.get("start_line"))
                lookup[key] = {
                    "signature":   n.get("signature", ""),
                    "return_type": n.get("return_type", ""),
                    "decorators":  n.get("decorators", []),
                    "references":  n.get("references", []),
                    "raises":      n.get("raises", []),
                }
        return lookup

    @staticmethod
    def _compute_ref_counts(edges: list) -> dict:
        """
        Count incoming references per node name.
        A node with ref_count=7 is a hub; ref_count=0 is a leaf.
        """
        counts = {}
        for edge in edges:
            target = edge.get("target", "")
            if target:
                # Only count the base name (strip module prefix)
                base = target.rsplit(".", 1)[-1]
                counts[base] = counts.get(base, 0) + 1
        return counts

    @staticmethod
    def _build_calls_section(edges: list) -> str:
        """
        Build a compact CALLS section from edge data.
        Groups call targets by source function.

        Format:
            CALLS:
              load_config -> os.path.exists, json.load, validate_schema
              save_config -> tempfile.mkstemp, os.rename
        """
        call_edges = [e for e in edges if e.get("kind") == "calls"]
        if not call_edges:
            return ""

        # Group by source
        groups = {}
        for e in call_edges:
            src = e["source"]
            tgt = e["target"]
            groups.setdefault(src, []).append(tgt)

        lines = ["CALLS:"]
        for src, targets in groups.items():
            # Deduplicate and sort for readability
            unique = sorted(set(targets))
            # Truncate very long target lists
            if len(unique) > 8:
                display = ", ".join(unique[:8]) + f" (+{len(unique)-8} more)"
            else:
                display = ", ".join(unique)
            lines.append(f"  {src} \u2192 {display}")

        return "\n".join(lines)

    @staticmethod
    def _build_inherits_section(edges: list) -> str:
        """
        Build an INHERITS section from edge data.
        Format:
            INHERITS:
              ConfigManager -> BaseConfig
        """
        inherit_edges = [e for e in edges if e.get("kind") == "inherits"]
        if not inherit_edges:
            return ""

        lines = ["INHERITS:"]
        for e in inherit_edges:
            lines.append(f"  {e['source']} \u2192 {e['target']}")
        return "\n".join(lines)

    @staticmethod
    def _build_raises_section(walker_nodes: list) -> str:
        """
        Build a RAISES section listing exception types per function.
        Only includes functions that actually raise exceptions.

        Format:
            RAISES:
              load_config: FileNotFoundError, JSONDecodeError
              fetch_remote: ConnectionError, Timeout
        """
        entries = []
        for n in walker_nodes:
            if hasattr(n, "raises"):
                raises = n.raises
                name = n.name
            elif isinstance(n, dict):
                raises = n.get("raises", [])
                name = n.get("name", "?")
            else:
                continue

            if raises:
                entries.append((name, raises))

        if not entries:
            return ""

        lines = ["RAISES:"]
        for name, exceptions in entries:
            lines.append(f"  {name}: {', '.join(exceptions)}")
        return "\n".join(lines)

    # ── original helpers ───────────────────────────────────

    @staticmethod
    def _extract_imports(content: str, language: str) -> list:
        """Extract a deduplicated list of top-level imported module names."""
        pattern = _IMPORT_PATTERNS.get(language or "")
        if not pattern:
            return []
        names = []
        seen  = set()
        for m in pattern.finditer(content):
            # Take only the first component (e.g. "os.path" -> "os")
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
                    return text[:_GIST_MAX] + ("\u2026" if len(text) > _GIST_MAX else "")

            # Single-line hash comment
            if stripped.startswith("#"):
                text = stripped.lstrip("#").strip()
                if text and not text.startswith("!"):  # skip shebangs
                    return text[:_GIST_MAX] + ("\u2026" if len(text) > _GIST_MAX else "")

        return ""

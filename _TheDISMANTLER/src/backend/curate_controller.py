"""
CurateController – Orchestrates the curation pipeline:
Read File -> Parse AST -> Index Chunks -> Run AI Scout -> Update Graph.
Coordinates between the FileController, SlidingWindow, ASTNodeWalker,
and AIController to produce enriched code metadata.
Zero UI dependencies.
"""
import os
from backend.modules.ast_node_walker import ASTNodeWalker
from backend.modules.ast_lens import get_hierarchy_flat_from_source
from backend.modules.manifest_engine import ManifestEngine

# Directories always skipped during directory curation
_SKIP_DIRS = {"__pycache__", "_backupBIN", "_logs", "_versioning-history",
              ".git", ".venv", "node_modules", ".mypy_cache", ".pytest_cache"}


class CurateController:
    """
    Drives the curation workflow for a single source file.
    Steps:
    1. Read the file from disk or accept buffer content
    2. Parse AST and extract entities/edges (Python only)
    3. Build chunks and index them into the SlidingWindow store
    4. Optionally run an AI scout pass for enrichment
    """

    def __init__(self, project_root, log=None):
        self.project_root = project_root
        self.log = log or (lambda msg: None)
        self.walker = ASTNodeWalker()
        self._backend = None

    def bind_engine(self, backend_engine):
        """Late-bind reference to BackendEngine for cross-controller access."""
        self._backend = backend_engine

    def handle(self, schema):
        """Controller dispatch for BackendEngine."""
        action = schema.get("action")

        if action == "curate_file":
            return self._curate_file(schema)
        elif action == "get_entities":
            return self._get_entities(schema)
        elif action == "get_hierarchy":
            return self._get_hierarchy(schema)
        elif action == "get_hierarchy_flat":
            return self._get_hierarchy_flat(schema)
        elif action == "curate_directory":
            return self._curate_directory(schema)
        return {"status": "error", "message": f"Unknown curate action: {action}"}

    # ── curation pipeline ───────────────────────────────────

    def _curate_file(self, schema):
        """
        Full curation pipeline for a single file.
        Accepts optional 'content' in schema to use buffer instead of disk.
        Returns entities, edges, hierarchy, and chunk count.
        """
        file_path = schema.get("file")
        if not file_path:
            return {"status": "error", "message": "No file specified"}

        # Buffer-first: use provided content, fall back to disk
        content = schema.get("content")
        if content is None:
            if not os.path.isfile(file_path):
                return {"status": "error", "message": f"File not found: {file_path}"}
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError) as e:
                return {"status": "error", "message": f"Read failed: {e}"}

        self.log(f"Curating: {file_path}")

        # Detect language from extension
        ext = os.path.splitext(file_path)[1].lower()
        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".java": "java", ".go": "go", ".rs": "rust", ".rb": "ruby",
            ".c": "c", ".cpp": "cpp", ".cs": "csharp",
        }
        language = lang_map.get(ext, ext.lstrip(".") or None)

        # Step 1: Walk AST for entities/edges (Python only — the walker
        # uses Python's ast module and will fail on other languages)
        entities = []
        edges = []
        if language == "python":
            self.walker.walk_source(content, file_path)
            entities = self.walker.get_entity_list()
            edges = self.walker.get_edge_list()
            self.log(f"  Found {len(entities)} entities, {len(edges)} relationships")
        else:
            self.log(f"  Entity extraction skipped (language: {language})")

        # Step 2: Get hierarchy from source content (no double-read)
        hierarchy = get_hierarchy_flat_from_source(content, ext)

        # Step 3: Build chunks from hierarchy
        lines = content.splitlines()
        chunks = []
        for node in hierarchy:
            start = node["start_line"] - 1
            end = node["end_line"]
            chunk_lines = lines[start:end]
            chunks.append({
                "name": node["name"],
                "start_line": node["start_line"],
                "end_line": node["end_line"],
                "content": "\n".join(chunk_lines),
                "chunk_type": node["kind"],
                "depth": node["depth"],
            })

        self.log(f"  Indexed {len(chunks)} chunks ({language})")

        # Step 4: Push chunks into SlidingWindow DB for search/context
        manifest = ""
        if self._backend:
            sw = self._backend.sliding_window
            try:
                sw.index_file(file_path, content, language, chunks or None)
                self.log(f"  SlidingWindow indexed: {file_path}")
            except Exception as e:
                self.log(f"  SlidingWindow indexing failed: {e}")

            # Step 5: Build and store the enriched structural manifest
            try:
                manifest = ManifestEngine.build(
                    file_path, language, content, hierarchy,
                    walker_nodes=self.walker.nodes if language == "python" else None,
                    edges=edges or None,
                )
                # Retrieve the file_id from the DB to store the manifest
                from backend.modules.db_schema import get_connection
                conn = get_connection(sw.db_path)
                row = conn.execute(
                    "SELECT file_id FROM source_files WHERE path=?", (file_path,)
                ).fetchone()
                conn.close()
                if row:
                    sw.index_manifest(row["file_id"], manifest)
                    self.log(f"  Manifest built: {len(manifest)} chars")
            except Exception as e:
                self.log(f"  Manifest build failed: {e}")

            # Step 6: Persist per-chunk metadata for Scout enrichment
            if language == "python" and self.walker.nodes:
                try:
                    ref_counts = self._compute_ref_counts(edges)
                    meta_list = self._build_chunk_meta(
                        self.walker.nodes, edges, ref_counts
                    )
                    sw.index_chunk_meta(file_path, meta_list)
                    self.log(f"  Chunk metadata stored: {len(meta_list)} entries")
                except Exception as e:
                    self.log(f"  Chunk metadata storage failed: {e}")

        return {
            "status": "ok",
            "file": file_path,
            "language": language,
            "content": content,
            "entities": entities,
            "edges": edges,
            "hierarchy": hierarchy,
            "chunks": chunks,
            "manifest": manifest,
        }

    def _curate_directory(self, schema):
        """Curate all source files in a directory."""
        directory = schema.get("directory")
        extensions = schema.get("extensions", {".py"})
        if isinstance(extensions, list):
            extensions = set(extensions)

        if not directory or not os.path.isdir(directory):
            return {"status": "error", "message": f"Directory not found: {directory}"}

        results = []
        for root, dirs, files in os.walk(directory):
            # Skip hidden dirs (.) and known non-source dirs; allow _ prefixed project dirs
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in extensions:
                    full = os.path.join(root, fname)
                    result = self._curate_file({"file": full})
                    if result.get("status") == "ok":
                        results.append({
                            "file": full,
                            "entities": len(result["entities"]),
                            "chunks": len(result["chunks"]),
                        })

        return {
            "status": "ok",
            "files_curated": len(results),
            "results": results,
        }

    # ── metadata helpers ─────────────────────────────────────

    @staticmethod
    def _compute_ref_counts(edges):
        """Count incoming references per node name from edge list."""
        counts = {}
        for e in edges:
            target = e.get("target", "")
            if target:
                base = target.rsplit(".", 1)[-1]
                counts[base] = counts.get(base, 0) + 1
        return counts

    @staticmethod
    def _build_chunk_meta(walker_nodes, edges, ref_counts):
        """
        Build a list of per-chunk metadata dicts from walker ASTNode objects.
        Each dict has: name, start_line, end_line, decorators, signature,
                       return_type, calls, raises, ref_count
        """
        # Build call targets grouped by source name
        call_map = {}
        for e in edges:
            if e.get("kind") == "calls":
                call_map.setdefault(e["source"], []).append(e["target"])

        meta = []
        for n in walker_nodes:
            calls = sorted(set(call_map.get(n.name, [])))
            meta.append({
                "name":        n.name,
                "start_line":  n.start_line,
                "end_line":    n.end_line,
                "decorators":  n.decorators,
                "signature":   n.signature,
                "return_type": n.return_type,
                "calls":       calls,
                "raises":      n.raises,
                "ref_count":   ref_counts.get(n.name, 0),
            })
        return meta

    # ── entity access ───────────────────────────────────────

    def _get_entities(self, schema):
        """Return entities and edges for a file (Python only)."""
        file_path = schema.get("file")
        content = schema.get("content")

        if content is None:
            if not file_path or not os.path.isfile(file_path):
                return {"status": "error", "message": f"File not found: {file_path}"}
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError) as e:
                return {"status": "error", "message": f"Read failed: {e}"}

        ext = os.path.splitext(file_path or "")[1].lower()
        if ext != ".py":
            return {
                "status": "ok",
                "entities": [],
                "edges": [],
                "entity_types": [],
                "note": "Entity extraction only supported for Python files",
            }

        self.walker.walk_source(content, file_path)

        return {
            "status": "ok",
            "entities": self.walker.get_entity_list(),
            "edges": self.walker.get_edge_list(),
            "entity_types": self.walker.get_entity_types(),
        }

    def _get_hierarchy(self, schema):
        """Return the AST tree as a formatted string."""
        file_path = schema.get("file")
        content = schema.get("content")

        if content is None:
            if not file_path or not os.path.isfile(file_path):
                return {"status": "error", "message": f"File not found: {file_path}"}
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError) as e:
                return {"status": "error", "message": f"Read failed: {e}"}

        ext = os.path.splitext(file_path or "")[1].lower()
        if ext == ".py":
            self.walker.walk_source(content, file_path)
            tree_text = self.walker.format_tree()
        else:
            # Use regex fallback via ast_lens for non-Python
            hierarchy = get_hierarchy_flat_from_source(content, ext)
            tree_lines = []
            for node in hierarchy:
                prefix = "  " * node["depth"]
                icon = "\u25B8" if node["kind"] == "class" else "\u25CB"
                span = f"L{node['start_line']}-{node['end_line']}"
                tree_lines.append(f"{prefix}{icon} {node['kind']} {node['name']}  ({span})")
            tree_text = "\n".join(tree_lines) if tree_lines else "(no structure detected)"

        return {
            "status": "ok",
            "tree": tree_text,
        }

    def _get_hierarchy_flat(self, schema):
        """Return the flattened hierarchy as a list of dicts (for UI Context tab)."""
        file_path = schema.get("file")
        content = schema.get("content")

        if content is None:
            if not file_path or not os.path.isfile(file_path):
                return {"status": "error", "message": f"File not found: {file_path}"}
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except (OSError, UnicodeDecodeError) as e:
                return {"status": "error", "message": f"Read failed: {e}"}

        ext = os.path.splitext(file_path or "")[1].lower()
        hierarchy = get_hierarchy_flat_from_source(content, ext)

        return {
            "status": "ok",
            "hierarchy": hierarchy,
        }

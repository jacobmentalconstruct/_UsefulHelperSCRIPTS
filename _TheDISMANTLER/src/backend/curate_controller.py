"""
CurateController – Orchestrates the curation pipeline:
Read File -> Parse AST -> Index Chunks -> Run AI Scout -> Update Graph.
Coordinates between the FileController, SlidingWindow, ASTNodeWalker,
and AIController to produce enriched code metadata.
Zero UI dependencies.
"""
import os
from backend.modules.ast_node_walker import ASTNodeWalker
from backend.modules.ast_lens import parse_file, get_hierarchy_flat


class CurateController:
    """
    Drives the curation workflow for a single source file.
    Steps:
    1. Read the file from disk (via FileController)
    2. Parse AST and extract entities/edges
    3. Index chunks into the SlidingWindow store
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
        elif action == "curate_directory":
            return self._curate_directory(schema)
        return {"status": "error", "message": f"Unknown curate action: {action}"}

    # ── curation pipeline ───────────────────────────────────

    def _curate_file(self, schema):
        """
        Full curation pipeline for a single file.
        Returns entities, edges, hierarchy, and chunk count.
        """
        file_path = schema.get("file")
        if not file_path or not os.path.isfile(file_path):
            return {"status": "error", "message": f"File not found: {file_path}"}

        self.log(f"Curating: {file_path}")

        # Step 1: Read the file
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            return {"status": "error", "message": f"Read failed: {e}"}

        # Step 2: Walk AST for entities and edges
        nodes = self.walker.walk_source(content, file_path)
        entities = self.walker.get_entity_list()
        edges = self.walker.get_edge_list()

        self.log(f"  Found {len(entities)} entities, {len(edges)} relationships")

        # Step 3: Get hierarchy for chunk indexing
        hierarchy = get_hierarchy_flat(file_path)

        # Step 4: Build chunks from hierarchy
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

        # Step 5: Detect language
        ext = os.path.splitext(file_path)[1].lower()
        lang_map = {
            ".py": "python", ".js": "javascript", ".ts": "typescript",
            ".java": "java", ".go": "go", ".rs": "rust", ".rb": "ruby",
            ".c": "c", ".cpp": "cpp", ".cs": "csharp",
        }
        language = lang_map.get(ext, ext.lstrip(".") or None)

        self.log(f"  Indexed {len(chunks)} chunks ({language})")

        return {
            "status": "ok",
            "file": file_path,
            "language": language,
            "content": content,
            "entities": entities,
            "edges": edges,
            "hierarchy": hierarchy,
            "chunks": chunks,
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
        for root, _dirs, files in os.walk(directory):
            # Skip hidden and internal directories
            if any(part.startswith((".","_")) for part in root.replace("\\","/").split("/")):
                continue
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

    # ── entity access ───────────────────────────────────────

    def _get_entities(self, schema):
        """Return entities and edges from the last curation pass."""
        file_path = schema.get("file")
        if not file_path or not os.path.isfile(file_path):
            return {"status": "error", "message": f"File not found: {file_path}"}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError) as e:
            return {"status": "error", "message": f"Read failed: {e}"}

        self.walker.walk_source(source, file_path)

        return {
            "status": "ok",
            "entities": self.walker.get_entity_list(),
            "edges": self.walker.get_edge_list(),
            "entity_types": self.walker.get_entity_types(),
        }

    def _get_hierarchy(self, schema):
        """Return the AST tree as a formatted string."""
        file_path = schema.get("file")
        if not file_path or not os.path.isfile(file_path):
            return {"status": "error", "message": f"File not found: {file_path}"}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError) as e:
            return {"status": "error", "message": f"Read failed: {e}"}

        self.walker.walk_source(source, file_path)
        tree_text = self.walker.format_tree()

        return {
            "status": "ok",
            "tree": tree_text,
        }

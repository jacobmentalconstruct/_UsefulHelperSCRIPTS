"""
Transformer Controller – Orchestrates the monolith extraction pipeline.
Handles the full workflow: analysis → tagging → extraction → integrity checks.
"""
import os
import ast
import re
from backend.modules.transformer import MonolithTransformer


class TransformerController:
    """
    High-level interface for the Modular Transformation Engine.
    Provides a three-step workflow:
    1. analyze_monolith() – Parse and report structure
    2. tag_for_extraction() – Identify extraction targets
    3. execute_extraction() – Write refactored code
    """

    def __init__(self, project_root, log=None):
        self.project_root = project_root
        self.log = log or (lambda msg: None)
        self.transformer = MonolithTransformer(project_root, log)
        self.analysis_cache = None
        self._backend = None
        self._refinement_engine = None

    def bind_engine(self, backend_engine):
        """Late-bind reference to the parent BackendEngine for cross-controller access."""
        self._backend = backend_engine

    def _get_refinement_engine(self):
        """Lazy-initialize the RefinementEngine with AI and SlidingWindow refs."""
        if self._refinement_engine is None:
            if not self._backend:
                raise RuntimeError("bind_engine() must be called before using refinement")
            from backend.modules.refinement_engine import RefinementEngine
            self._refinement_engine = RefinementEngine(
                self._backend.controllers["ai"],
                self._backend.sliding_window,
                self.log,
            )
        return self._refinement_engine

    # ── step 1: analysis ────────────────────────────────────

    def analyze_monolith(self, file_path: str) -> dict:
        """
        Parse a monolithic file and return a detailed analysis.
        Use this to understand the structure before extraction.
        """
        if not os.path.isfile(file_path):
            return {"error": f"File not found: {file_path}"}

        analysis = self.transformer.parse_file(file_path)
        self.analysis_cache = analysis
        return analysis

    # ── step 2: extraction strategy ─────────────────────────

    def extract_with_tags(self, file_path: str, dry_run=False) -> dict:
        """
        Extract blocks that have explicit # <EXTRACT_TO: ...> tags.
        Manual approach: requires the user to annotate the monolith first.
        """
        blocks = self.transformer.extract_tagged_blocks(file_path)
        if not blocks:
            self.log("No tagged extraction blocks found. Use auto_extract() instead.")
            return {"blocks": 0, "message": "No tagged blocks found"}

        report = self.transformer.generate_report()
        self.log(report)

        result = self.transformer.write_blocks(blocks, dry_run=dry_run)
        return result

    def extract_auto(self, file_path: str, dry_run=False) -> dict:
        """
        Automatically detect extraction candidates based on code patterns.
        Heuristic approach: uses naming conventions, imports, and AST analysis.
        """
        blocks = self.transformer.auto_detect_blocks(file_path)
        if not blocks:
            self.log("No extraction candidates auto-detected.")
            return {"blocks": 0, "message": "No candidates auto-detected"}

        report = self.transformer.generate_report()
        self.log(report)

        result = self.transformer.write_blocks(blocks, dry_run=dry_run)
        return result

    # ── step 3: integrity ──────────────────────────────────

    def verify_integrity(self) -> dict:
        """
        Run integrity checks on extracted blocks:
        - No circular dependencies
        - All imports resolvable
        - No missing functions
        - Stateless UI constraint
        - Headless backend constraint
        """
        checks = {
            "circular_deps": self._check_circular_dependencies(),
            "import_validity": self._check_imports(),
            "ui_database_mixing": self._check_ui_database_isolation(),
            "backend_ui_imports": self._check_backend_purity(),
        }
        return checks

    def _check_circular_dependencies(self) -> dict:
        """Build an import graph from src/ and detect circular references."""
        src_dir = os.path.join(self.project_root, "src")
        if not os.path.isdir(src_dir):
            src_dir = self.project_root

        graph = {}
        py_files = self._collect_py_files(src_dir)

        for fpath in py_files:
            mod_name = self._path_to_module(fpath, src_dir)
            graph[mod_name] = self._extract_imports(fpath)

        cycles = []
        visited = set()
        stack = set()

        def dfs(node, path):
            if node in stack:
                idx = path.index(node)
                cycles.append(path[idx:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            stack.add(node)
            path.append(node)
            for neighbor in graph.get(node, set()):
                if neighbor in graph:
                    dfs(neighbor, path)
            path.pop()
            stack.discard(node)

        for mod in graph:
            if mod not in visited:
                dfs(mod, [])

        status = "ok" if not cycles else "warning"
        return {"status": status, "circular_refs": cycles[:10]}

    def _check_imports(self) -> dict:
        """Verify local imports in src/ resolve to existing files."""
        src_dir = os.path.join(self.project_root, "src")
        if not os.path.isdir(src_dir):
            src_dir = self.project_root

        py_files = self._collect_py_files(src_dir)
        known = set()
        for fpath in py_files:
            known.add(self._path_to_module(fpath, src_dir))

        unresolved = []
        for fpath in py_files:
            mod_name = self._path_to_module(fpath, src_dir)
            for imp in self._extract_imports(fpath):
                if imp.startswith(("backend", "ui", "theme")):
                    if imp not in known:
                        unresolved.append({"module": mod_name, "import": imp})

        status = "ok" if not unresolved else "warning"
        return {"status": status, "unresolved": unresolved[:20]}

    def _check_ui_database_mixing(self) -> dict:
        """Scan UI modules for database logic."""
        src_dir = os.path.join(self.project_root, "src")
        ui_dir = os.path.join(src_dir, "ui")
        if not os.path.isdir(ui_dir):
            return {"status": "ok", "violations": []}

        db_pat = re.compile(
            r"(?:import\s+sqlite3|from\s+.*db_schema|"
            r"\.execute\s*\(|\.cursor\s*\(|get_connection)"
        )

        violations = []
        for fpath in self._collect_py_files(ui_dir):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if db_pat.search(line):
                            rel = os.path.relpath(fpath, src_dir)
                            violations.append({"file": rel, "line": i, "text": line.strip()})
            except (OSError, UnicodeDecodeError):
                continue

        status = "ok" if not violations else "warning"
        return {"status": status, "violations": violations[:20]}

    def _check_backend_purity(self) -> dict:
        """Scan backend modules for tkinter or UI library imports."""
        src_dir = os.path.join(self.project_root, "src")
        be_dir = os.path.join(src_dir, "backend")
        if not os.path.isdir(be_dir):
            return {"status": "ok", "violations": []}

        ui_pat = re.compile(
            r"(?:import\s+tkinter|from\s+tkinter|"
            r"from\s+ui\b|messagebox|filedialog)"
        )

        violations = []
        for fpath in self._collect_py_files(be_dir):
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if ui_pat.search(line):
                            rel = os.path.relpath(fpath, src_dir)
                            violations.append({"file": rel, "line": i, "text": line.strip()})
            except (OSError, UnicodeDecodeError):
                continue

        status = "ok" if not violations else "warning"
        return {"status": status, "violations": violations[:20]}

    # ── integrity helpers ──────────────────────────────────

    @staticmethod
    def _collect_py_files(directory):
        """Collect all .py files under a directory, skipping __pycache__."""
        results = []
        for root, dirs, files in os.walk(directory):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for f in files:
                if f.endswith(".py"):
                    results.append(os.path.join(root, f))
        return results

    @staticmethod
    def _path_to_module(fpath, src_dir):
        """Convert a file path to a dotted module name."""
        rel = os.path.relpath(fpath, src_dir).replace(os.sep, "/")
        if rel.endswith("/__init__.py"):
            return rel[:-12].replace("/", ".")
        return rel[:-3].replace("/", ".")

    @staticmethod
    def _extract_imports(fpath):
        """Extract imported module names from a Python file using AST."""
        try:
            with open(fpath, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=fpath)
        except (SyntaxError, OSError, UnicodeDecodeError):
            return set()

        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    imports.add(node.module)
        return imports

    # ── reporting & summary ────────────────────────────────

    def generate_extraction_guide(self, file_path: str) -> str:
        """
        Generate a guide for manually tagging the monolith.
        Shows structure and recommended extraction targets.
        """
        analysis = self.analyze_monolith(file_path)
        if "error" in analysis:
            return analysis["error"]

        guide_lines = [
            "EXTRACTION GUIDE",
            "=" * 70,
            "",
            f"File: {file_path}",
            f"Classes found: {len(analysis.get('classes', []))}",
            f"Functions found: {len(analysis.get('functions', []))}",
            "",
            "RECOMMENDED TAGS:",
            "",
        ]

        for cls in analysis.get("classes", []):
            suggested_target = self._suggest_target_for_class(cls["name"])
            guide_lines.append(f"# Class: {cls['name']}")
            guide_lines.append(f"# → Suggested: {suggested_target}")
            guide_lines.append(f"# <EXTRACT_TO: {suggested_target}>")
            guide_lines.append(f"# ... class code ...")
            guide_lines.append(f"# </EXTRACT_TO>")
            guide_lines.append("")

        return "\n".join(guide_lines)

    def _suggest_target_for_class(self, class_name: str) -> str:
        """Suggest a target location based on class name."""
        if "Controller" in class_name:
            return f"src/backend/{class_name.replace('Controller', '').lower()}_controller.py"
        if "Panel" in class_name or "Widget" in class_name:
            return f"src/ui/modules/{class_name.lower()}.py"
        return f"src/backend/modules/{class_name.lower()}.py"

    def handle(self, schema: dict) -> dict:
        """Controller dispatch for BackendEngine."""
        action = schema.get("action")

        if action == "analyze":
            return {"status": "ok", "analysis": self.analyze_monolith(schema.get("file"))}
        elif action == "extract_tagged":
            return self.extract_with_tags(schema.get("file"), dry_run=schema.get("dry_run", True))
        elif action == "extract_auto":
            return self.extract_auto(schema.get("file"), dry_run=schema.get("dry_run", True))
        elif action == "verify":
            return {"status": "ok", "checks": self.verify_integrity()}
        elif action == "guide":
            return {"status": "ok", "guide": self.generate_extraction_guide(schema.get("file"))}

        # ── refinement actions ─────────────────────────────
        elif action == "refine_create":
            engine = self._get_refinement_engine()
            sid = engine.create_session(
                file_path=schema.get("file"),
                initial_plan=schema.get("plan", ""),
                model=schema.get("model", ""),
                max_passes=schema.get("max_passes", 5),
            )
            return {"status": "ok", "session_id": sid}

        elif action == "refine_pass":
            engine = self._get_refinement_engine()
            result = engine.execute_pass(
                schema.get("session_id"),
                stream_callback=schema.get("stream_callback"),
            )
            if "error" in result:
                return {"status": "error", "message": result["error"]}
            return {"status": "ok", "pass_result": result}

        elif action == "refine_retry":
            engine = self._get_refinement_engine()
            result = engine.retry_pass(
                schema.get("session_id"),
                stream_callback=schema.get("stream_callback"),
            )
            if "error" in result:
                return {"status": "error", "message": result["error"]}
            return {"status": "ok", "pass_result": result}

        elif action == "refine_status":
            engine = self._get_refinement_engine()
            state = engine.get_session(schema.get("session_id"))
            if state:
                return {"status": "ok", "session": state}
            return {"status": "error", "message": "Session not found"}

        elif action == "refine_cancel":
            engine = self._get_refinement_engine()
            engine.cancel_session(schema.get("session_id"))
            return {"status": "ok", "message": "Session cancelled"}

        return {"status": "error", "message": f"Unknown transformer action: {action}"}

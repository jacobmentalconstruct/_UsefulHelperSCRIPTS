"""
Modular Transformation Engine – Strangler Fig Extraction.
Parses monolithic Python files and redistributes their logic into the
established Dismantler v2.0 federated structure.
"""
import ast
import re
import os
import hashlib
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional


class DependencyAnalyzer(ast.NodeVisitor):
    """
    Walks an AST and extracts:
    - All imports (external and relative)
    - All function/class names referenced
    - UI vs backend patterns (tkinter, database, etc.)
    """

    def __init__(self):
        self.imports = set()
        self.external_imports = set()
        self.names_referenced = set()
        self.names_defined = set()
        self.tkinter_patterns = False
        self.database_patterns = False
        self.controller_patterns = False

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.add(alias.name.split(".")[0])
            if not alias.name.startswith("."):
                self.external_imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module:
            if not node.module.startswith("."):
                self.external_imports.add(node.module)
            self.imports.add(node.module.split(".")[0] if node.module else "")
        self.generic_visit(node)

    def visit_Name(self, node):
        if isinstance(node.ctx, ast.Load):
            self.names_referenced.add(node.id)
        elif isinstance(node.ctx, (ast.Store, ast.Del)):
            self.names_defined.add(node.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.names_defined.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.names_defined.add(node.name)
        self.generic_visit(node)

    def analyze_code(self, code):
        """Check for domain-specific patterns."""
        if "tkinter" in code or "tk." in code or "ttk." in code:
            self.tkinter_patterns = True
        if "sql" in code.lower() or "sqlite" in code.lower() or "cursor.execute" in code:
            self.database_patterns = True
        if "class" in code and "Controller" in code:
            self.controller_patterns = True


class ExtractedBlock:
    """Represents a code block ready for extraction."""

    def __init__(
        self,
        name: str,
        code: str,
        node_type: str,  # 'class', 'function', 'module'
        dependencies: Set[str],
        target: str,
        imports: Set[str],
    ):
        self.name = name
        self.code = code
        self.node_type = node_type
        self.dependencies = dependencies
        self.target = target
        self.imports = imports

    def hash(self) -> str:
        """Return a hash of the code for deduplication."""
        normalized = re.sub(r"\s+", " ", self.code.strip())
        return hashlib.md5(normalized.encode()).hexdigest()


class MonolithTransformer:
    """
    The Parsing Orchestrator.
    Reads a monolithic file, identifies extraction targets, and writes
    refactored code to the Dismantler structure.
    """

    def __init__(self, project_root: str, log=None):
        self.project_root = project_root
        self.log = log or (lambda msg: None)
        self.extracted_blocks: List[ExtractedBlock] = []
        self.deduplication_hashes: Dict[str, str] = {}

    # ── phase 1: semantic analysis ──────────────────────────

    def parse_file(self, file_path: str) -> Dict[str, any]:
        """
        Parse a monolithic file and return a summary of its structure.
        Identifies classes, functions, and global patterns.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError) as e:
            self.log(f"Failed to read {file_path}: {e}")
            return {}

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            self.log(f"Syntax error in {file_path}: {e}")
            return {}

        summary = {
            "file": file_path,
            "classes": [],
            "functions": [],
            "imports": set(),
            "global_vars": [],
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                summary["classes"].append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "methods": [m.name for m in node.body if isinstance(m, ast.FunctionDef)],
                })
            elif isinstance(node, ast.FunctionDef) and not self._is_method(node, tree):
                summary["functions"].append({
                    "name": node.name,
                    "lineno": node.lineno,
                })
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        summary["imports"].add(alias.name)
                else:
                    if node.module:
                        summary["imports"].add(node.module)

        self.log(f"Parsed {file_path}: {len(summary['classes'])} classes, {len(summary['functions'])} functions")
        return summary

    def _is_method(self, func_node, tree) -> bool:
        """Check if a function is actually a method inside a class."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if item is func_node:
                        return True
        return False

    # ── phase 2: extraction ─────────────────────────────────

    def extract_tagged_blocks(self, file_path: str) -> List[ExtractedBlock]:
        """
        Read a file with explicit extraction tags like:
        # <EXTRACT_TO: src/backend/modules/utils.py>
        def my_function():
            pass
        # </EXTRACT_TO>

        Returns a list of ExtractedBlock objects.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError) as e:
            self.log(f"Failed to read {file_path}: {e}")
            return []

        blocks = []
        pattern = r"#\s*<EXTRACT_TO:\s*(.+?)>\s*\n(.*?)\n\s*#\s*</EXTRACT_TO>"
        matches = re.finditer(pattern, source, re.DOTALL)

        for match in matches:
            target = match.group(1).strip()
            code = match.group(2).strip()

            # Analyze dependencies
            analyzer = DependencyAnalyzer()
            analyzer.analyze_code(code)
            try:
                tree = ast.parse(code)
                analyzer.visit(tree)
            except SyntaxError:
                pass

            # Extract the name
            name = self._extract_name_from_code(code)

            block = ExtractedBlock(
                name=name,
                code=code,
                node_type=self._infer_node_type(code),
                dependencies=analyzer.names_referenced - analyzer.names_defined,
                target=target,
                imports=analyzer.external_imports,
            )
            blocks.append(block)

        self.extracted_blocks = blocks
        self.log(f"Tagged {len(blocks)} extraction blocks in {file_path}")
        return blocks

    def auto_detect_blocks(self, file_path: str) -> List[ExtractedBlock]:
        """
        Automatically detect extraction targets based on code patterns.
        Uses heuristics: imports, naming conventions, AST analysis.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source = f.read()
        except (OSError, UnicodeDecodeError):
            return []

        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        blocks = []

        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                code = ast.unparse(node)
                target = self._classify_for_extraction(node.name, code)
                if target:
                    analyzer = DependencyAnalyzer()
                    analyzer.analyze_code(code)
                    analyzer.visit(node)
                    blocks.append(
                        ExtractedBlock(
                            name=node.name,
                            code=code,
                            node_type="class",
                            dependencies=analyzer.names_referenced - analyzer.names_defined,
                            target=target,
                            imports=analyzer.external_imports,
                        )
                    )

            elif isinstance(node, ast.FunctionDef):
                code = ast.unparse(node)
                target = self._classify_for_extraction(node.name, code)
                if target:
                    analyzer = DependencyAnalyzer()
                    analyzer.analyze_code(code)
                    analyzer.visit(node)
                    blocks.append(
                        ExtractedBlock(
                            name=node.name,
                            code=code,
                            node_type="function",
                            dependencies=analyzer.names_referenced - analyzer.names_defined,
                            target=target,
                            imports=analyzer.external_imports,
                        )
                    )

        self.extracted_blocks = blocks
        self.log(f"Auto-detected {len(blocks)} extraction candidates in {file_path}")
        return blocks

    def _classify_for_extraction(self, name: str, code: str) -> Optional[str]:
        """
        Heuristic classifier to determine where a block should go.
        Returns target path or None if should not be extracted.
        """
        # Controller classes → backend/*_controller.py
        if "Controller" in name:
            controller_name = name.replace("Controller", "").lower()
            return f"src/backend/{controller_name}_controller.py"

        # Tkinter widgets → ui/modules/
        if any(pattern in code for pattern in ["tk.Frame", "ttk.Notebook", "tk.Text", "Canvas"]):
            return f"src/ui/modules/{name.lower()}.py"

        # Database-heavy → backend/modules/
        if "query" in name.lower() or "db" in name.lower() or "sql" in code.lower():
            return "src/backend/modules/db_schema.py"

        # Pure algorithms → backend/modules/
        if "def" in code and "self" not in code:
            return f"src/backend/modules/{name.lower()}.py"

        return None

    # ── phase 3: integrity pass ────────────────────────────

    def resolve_imports(self, block: ExtractedBlock) -> List[str]:
        """
        Determine what imports are needed for this block in its new location.
        Checks dependencies and context.
        """
        imports = []

        # Always needed in UI modules
        if "ui/modules" in block.target:
            if "tk." in block.code or "ttk." in block.code:
                imports.append("import tkinter as tk")
                imports.append("from tkinter import ttk")
            if "THEME" in block.code:
                imports.append("from theme import THEME")

        # Always needed in backend modules
        if "backend" in block.target:
            if "sqlite" in block.code.lower():
                imports.append("import sqlite3")
            if "SlidingWindow" in block.code or "get_connection" in block.code:
                imports.append("from backend.modules.db_schema import get_connection, init_db")

        # Custom imports from external packages
        for ext_import in block.imports:
            if ext_import not in ("tkinter", "tkinter.ttk", "sqlite3"):
                imports.append(f"import {ext_import}")

        return imports

    def check_deduplication(self, block: ExtractedBlock) -> Optional[str]:
        """
        Check if similar logic already exists in the target location.
        Returns the existing file path if found, else None.
        """
        block_hash = block.hash()

        # Check if we've already seen this code
        if block_hash in self.deduplication_hashes:
            return self.deduplication_hashes[block_hash]

        # Check if target file already exists and has similar code
        target_path = os.path.join(self.project_root, block.target)
        if os.path.isfile(target_path):
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    existing = f.read()
                    if self._similarity_score(block.code, existing) > 0.8:
                        self.deduplication_hashes[block_hash] = target_path
                        return target_path
            except (OSError, UnicodeDecodeError):
                pass

        self.deduplication_hashes[block_hash] = block.target
        return None

    @staticmethod
    def _similarity_score(code1: str, code2: str) -> float:
        """Simple similarity check using normalized token comparison."""
        norm1 = re.sub(r"\s+", " ", code1.strip())
        norm2 = re.sub(r"\s+", " ", code2.strip())
        if not norm1 or not norm2:
            return 0.0
        matching = sum(1 for a, b in zip(norm1, norm2) if a == b)
        return matching / max(len(norm1), len(norm2))

    # ── writing & synthesis ─────────────────────────────────

    def write_blocks(self, blocks: List[ExtractedBlock], dry_run=False) -> Dict[str, any]:
        """
        Write extracted blocks to their target files.
        Returns a summary of what was written.
        """
        result = {
            "written": [],
            "skipped": [],
            "duplicates": [],
        }

        for block in blocks:
            # Check for duplicates
            duplicate = self.check_deduplication(block)
            if duplicate and duplicate != block.target:
                self.log(f"Skipping {block.name}: duplicate found in {duplicate}")
                result["duplicates"].append({
                    "block": block.name,
                    "existing": duplicate,
                })
                continue

            # Resolve imports
            imports = self.resolve_imports(block)

            # Build the file content
            content = "\n".join(imports)
            if imports:
                content += "\n\n"
            content += block.code

            target_path = os.path.join(self.project_root, block.target)

            if not dry_run:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                try:
                    with open(target_path, "a", encoding="utf-8") as f:
                        f.write("\n\n" + content)
                    self.log(f"Wrote {block.name} to {block.target}")
                    result["written"].append(block.target)
                except (OSError, IOError) as e:
                    self.log(f"Failed to write {block.target}: {e}")
                    result["skipped"].append(block.target)
            else:
                self.log(f"[DRY RUN] Would write {block.name} to {block.target}")
                result["written"].append(f"[DRY RUN] {block.target}")

        return result

    # ── helpers ─────────────────────────────────────────────

    def _extract_name_from_code(self, code: str) -> str:
        """Extract the main definition name (class or function) from code."""
        match = re.search(r"^(?:class|def)\s+(\w+)", code, re.MULTILINE)
        return match.group(1) if match else "unknown"

    def _infer_node_type(self, code: str) -> str:
        """Infer whether code is a class, function, or module."""
        if re.match(r"^\s*class\s+", code):
            return "class"
        elif re.match(r"^\s*def\s+", code):
            return "function"
        return "module"

    # ── reporting ───────────────────────────────────────────

    def generate_report(self) -> str:
        """Generate a human-readable report of extraction candidates."""
        lines = ["Extraction Summary", "=" * 60]
        lines.append(f"Total blocks: {len(self.extracted_blocks)}")
        lines.append("")

        by_target = {}
        for block in self.extracted_blocks:
            if block.target not in by_target:
                by_target[block.target] = []
            by_target[block.target].append(block)

        for target, blocks in sorted(by_target.items()):
            lines.append(f"{target}:")
            for block in blocks:
                lines.append(f"  - {block.name} ({block.node_type})")

        return "\n".join(lines)

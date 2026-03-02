"""
Code Metrics Tool – Analyze Python files for quality metrics.

Provides:
- Line count (total, code, comments, blank)
- Complexity estimation
- Cyclomatic complexity indicators
- Function/class statistics
"""
import ast
import os
from backend.tools.base_tool import BaseTool
from typing import Dict, Any, List


class CodeMetricsTool(BaseTool):
    """Analyzes Python files and generates code quality metrics."""

    name = "Code Metrics"
    version = "1.0.0"
    description = "Analyze Python files for code quality metrics"
    tags = ["analysis", "metrics", "quality", "code"]
    requires = []

    def handle(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle code metrics requests.

        Schema:
        {
            "system": "code_metrics",
            "action": "analyze",
            "file": "/path/to/file.py"
        }
        """
        action = schema.get("action")

        if action == "analyze":
            return self._analyze_file(schema)
        elif action == "analyze_dir":
            return self._analyze_directory(schema)
        elif action == "list_functions":
            return self._list_functions(schema)
        else:
            return self.error(f"Unknown action: {action}")

    # ── Analyzers ──────────────────────────────────────────

    def _analyze_file(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze a single file."""
        file_path = schema.get("file")
        if not file_path or not os.path.isfile(file_path):
            return self.error(f"File not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            return self.error(f"Failed to read file: {e}")

        metrics = self._compute_metrics(content, file_path)
        return self.success(message="Analysis complete", metrics=metrics)

    def _analyze_directory(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """Analyze all Python files in a directory."""
        directory = schema.get("directory")
        if not directory or not os.path.isdir(directory):
            return self.error(f"Directory not found: {directory}")

        all_metrics = {}
        for root, _dirs, files in os.walk(directory):
            for filename in files:
                if filename.endswith(".py"):
                    filepath = os.path.join(root, filename)
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        metrics = self._compute_metrics(content, filepath)
                        all_metrics[filepath] = metrics
                    except (OSError, UnicodeDecodeError):
                        pass

        return self.success(
            message=f"Analyzed {len(all_metrics)} files",
            file_count=len(all_metrics),
            metrics=all_metrics
        )

    def _list_functions(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """List all functions and classes in a file."""
        file_path = schema.get("file")
        if not file_path or not os.path.isfile(file_path):
            return self.error(f"File not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        except (OSError, UnicodeDecodeError) as e:
            return self.error(f"Failed to read file: {e}")

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            return self.error(f"Syntax error: {e}")

        functions = []
        classes = []

        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                functions.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "args": len(node.args.args),
                })
            elif isinstance(node, ast.ClassDef):
                class_funcs = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                classes.append({
                    "name": node.name,
                    "lineno": node.lineno,
                    "methods": class_funcs,
                })

        return self.success(
            message="Extraction complete",
            functions=functions,
            classes=classes
        )

    # ── Metrics Computation ────────────────────────────────

    def _compute_metrics(self, content: str, file_path: str) -> Dict[str, Any]:
        """Compute comprehensive metrics for source code."""
        lines = content.split("\n")

        # Line counts
        total_lines = len(lines)
        blank_lines = sum(1 for line in lines if line.strip() == "")
        comment_lines = sum(1 for line in lines if line.strip().startswith("#"))
        code_lines = total_lines - blank_lines - comment_lines

        # AST analysis
        try:
            tree = ast.parse(content)
            function_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
            class_count = sum(1 for node in ast.walk(tree) if isinstance(node, ast.ClassDef))
            cyclomatic = self._estimate_cyclomatic_complexity(tree)
        except SyntaxError:
            function_count = 0
            class_count = 0
            cyclomatic = 0

        # Average function size
        avg_func_size = code_lines / function_count if function_count > 0 else 0

        # Complexity rating
        complexity_rating = self._rate_complexity(cyclomatic)

        return {
            "file": file_path,
            "total_lines": total_lines,
            "code_lines": code_lines,
            "comment_lines": comment_lines,
            "blank_lines": blank_lines,
            "comment_ratio": round(comment_lines / code_lines if code_lines > 0 else 0, 2),
            "functions": function_count,
            "classes": class_count,
            "avg_function_size": round(avg_func_size, 1),
            "cyclomatic_complexity": cyclomatic,
            "complexity_rating": complexity_rating,
        }

    def _estimate_cyclomatic_complexity(self, tree: ast.AST) -> int:
        """
        Estimate cyclomatic complexity (simplified).
        Counts decision points: if, for, while, except, and, or
        """
        count = 1  # Base complexity

        for node in ast.walk(tree):
            if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler)):
                count += 1
            elif isinstance(node, (ast.BoolOp)):
                # Count 'and'/'or' as decision points
                count += len(node.values) - 1

        return count

    @staticmethod
    def _rate_complexity(cyclomatic: int) -> str:
        """Rate complexity level based on cyclomatic number."""
        if cyclomatic <= 5:
            return "Low"
        elif cyclomatic <= 10:
            return "Moderate"
        elif cyclomatic <= 20:
            return "High"
        else:
            return "Very High"

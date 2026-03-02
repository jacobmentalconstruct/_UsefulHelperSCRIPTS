"""
AST Lens module.
Generates a read-only hierarchical breakdown of source files using
Python's built-in ast module for Python files and a regex fallback
for other languages.
"""
import ast
import os
import re


def parse_file(file_path):
    """
    Parse a source file and return a hierarchy of code constructs.
    Returns a list of node dicts:
        {name, kind, start_line, end_line, depth, children}
    """
    ext = os.path.splitext(file_path)[1].lower()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            source = f.read()
    except (OSError, UnicodeDecodeError):
        return []

    if ext == ".py":
        return _parse_python(source)
    return _parse_generic(source, ext)


def get_hierarchy_flat(file_path):
    """
    Flatten the hierarchy into a sorted list of
    {name, kind, start_line, end_line, depth} dicts.
    """
    nodes = parse_file(file_path)
    flat = []
    _flatten(nodes, flat)
    flat.sort(key=lambda n: n["start_line"])
    return flat


# ── Python AST parsing ──────────────────────────────────────

def _parse_python(source):
    """Use the ast module to extract classes, methods, and functions."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _parse_generic(source, ".py")

    return _walk_ast(tree.body, depth=0)


def _walk_ast(nodes, depth):
    result = []
    for node in nodes:
        entry = None
        if isinstance(node, ast.ClassDef):
            children = _walk_ast(node.body, depth + 1)
            entry = {
                "name": node.name,
                "kind": "class",
                "start_line": node.lineno,
                "end_line": node.end_lineno or node.lineno,
                "depth": depth,
                "children": children,
            }
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            children = _walk_ast(node.body, depth + 1)
            entry = {
                "name": node.name,
                "kind": "function",
                "start_line": node.lineno,
                "end_line": node.end_lineno or node.lineno,
                "depth": depth,
                "children": children,
            }

        if entry:
            result.append(entry)
    return result


# ── Generic regex fallback ──────────────────────────────────

# Patterns for common languages
_PATTERNS = {
    ".js":   r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(|class\s+(\w+))",
    ".ts":   r"(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\(|class\s+(\w+))",
    ".java": r"(?:class\s+(\w+)|(?:public|private|protected|static)\s+\w+\s+(\w+)\s*\()",
    ".c":    r"(?:(?:void|int|char|float|double|long)\s+(\w+)\s*\()",
    ".cpp":  r"(?:class\s+(\w+)|(?:void|int|char|float|double|long|auto)\s+(\w+)\s*\()",
    ".go":   r"(?:func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+))",
    ".rs":   r"(?:fn\s+(\w+)|struct\s+(\w+)|impl\s+(\w+))",
    ".rb":   r"(?:def\s+(\w+)|class\s+(\w+))",
    ".py":   r"(?:def\s+(\w+)|class\s+(\w+))",
}


def _parse_generic(source, ext):
    """Regex-based extraction for non-Python files."""
    pattern = _PATTERNS.get(ext)
    if not pattern:
        return []

    result = []
    for i, line in enumerate(source.splitlines(), start=1):
        m = re.search(pattern, line)
        if m:
            name = next((g for g in m.groups() if g), None)
            if name:
                kind = "class" if "class" in line else "function"
                result.append({
                    "name": name,
                    "kind": kind,
                    "start_line": i,
                    "end_line": i,
                    "depth": 0,
                    "children": [],
                })
    return result


# ── helpers ─────────────────────────────────────────────────

def _flatten(nodes, out, depth=0):
    """Recursively flatten a node tree."""
    for n in nodes:
        out.append({
            "name": n["name"],
            "kind": n["kind"],
            "start_line": n["start_line"],
            "end_line": n["end_line"],
            "depth": depth,
        })
        _flatten(n.get("children", []), out, depth + 1)


def format_tree(file_path):
    """
    Return a human-readable indented tree string for display
    in the AST Lens workspace tab.
    """
    nodes = parse_file(file_path)
    lines = []
    _tree_lines(nodes, lines, indent=0)
    return "\n".join(lines) if lines else "(no structure detected)"


def _tree_lines(nodes, out, indent):
    for n in nodes:
        prefix = "  " * indent
        icon = "\u25B8" if n["kind"] == "class" else "\u25CB"
        span = f"L{n['start_line']}-{n['end_line']}"
        out.append(f"{prefix}{icon} {n['kind']} {n['name']}  ({span})")
        _tree_lines(n.get("children", []), out, indent + 1)

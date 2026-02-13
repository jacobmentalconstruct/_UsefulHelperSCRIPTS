from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple, List


@dataclass
class RuleSet:
    package_dir: str = "src"
    # Modules that should be treated as internal-to-src when imported without prefix.
    internal_top_level: Tuple[str, ...] = (
        "backend",
        "ui",
        "microservices",
    )


def is_under(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def rewrite_imports_in_file(py_path: Path, rules: RuleSet) -> bool:
    """
    Returns True if file changed.
    Only rewrites when file is under src/ and import matches internal_top_level.
    """
    text = py_path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return False

    changed = False
    lines = text.splitlines(keepends=True)

    # Collect node spans to rewrite via naive line slicing (stable enough for ImportFrom).
    # We only rewrite 'from X import Y' style for now.
    edits: List[Tuple[int, int, str]] = []  # (lineno0, endlineno0, replacement)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # Skip already-relative imports
            if node.level and node.level > 0:
                continue

            if not node.module:
                continue

            mod = node.module

            # If it starts with internal module roots, rewrite to relative.
            # Examples:
            #   from backend import X         -> from .backend import X
            #   from ui import build_ui       -> from .ui import build_ui
            #   from microservices.X import Y -> from .microservices.X import Y
            root = mod.split(".")[0]
            if root not in rules.internal_top_level:
                continue

            # Rewrite by adding leading dot
            new_mod = "." + mod

            # Reconstruct the exact import statement (preserve imported names + aliases)
            names = []
            for a in node.names:
                if a.asname:
                    names.append(f"{a.name} as {a.asname}")
                else:
                    names.append(a.name)
            names_str = ", ".join(names)

            # Preserve "from __future__" (should not match our roots anyway)
            replacement = f"from {new_mod} import {names_str}\n"

            # Node lineno/end_lineno are 1-based
            if hasattr(node, "lineno") and hasattr(node, "end_lineno"):
                start = node.lineno - 1
                end = node.end_lineno - 1
                # Only rewrite single-line imports (keeps it safe)
                if start == end:
                    original_line = lines[start]
                    # Keep indentation of original line
                    indent = original_line[: len(original_line) - len(original_line.lstrip(" \t"))]
                    edits.append((start, start, indent + replacement))
                    changed = True

    if not changed:
        return False

    # Apply edits from bottom to top so indices stay valid
    for start, end, repl in sorted(edits, key=lambda e: e[0], reverse=True):
        lines[start : end + 1] = [repl]

    new_text = "".join(lines)
    if new_text != text:
        py_path.write_text(new_text, encoding="utf-8")
        return True
    return False


def main() -> None:
    rules = RuleSet()
    repo_root = Path(__file__).resolve().parent
    src_dir = repo_root / rules.package_dir
    if not src_dir.exists():
        raise SystemExit(f"Cannot find {src_dir}")

    changed_files = 0
    for py_path in src_dir.rglob("*.py"):
        if rewrite_imports_in_file(py_path, rules):
            changed_files += 1
            print(f"rewrote: {py_path}")

    print(f"\nDone. Files changed: {changed_files}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
LineNumberizer — make diffs agent-friendly by annotating files with stable, parseable line numbers.

New in this version
  • AST export (Python): `linenumberizer ast FILE.py --out FILE._ast.json [--mode tree|flat]`
    - Gracefully logs and emits a stub JSON when the input is NOT a Python file.
    - On Python SyntaxError, logs the error with the exact line number and exits non‑zero.

Core features
  • annotate: write a numbered copy with a consistent prefix format.
  • strip: remove previously added numbers safely.
  • map: export a JSON line-map (line → SHA-256 of raw content) for sanity checks.

Format
  Default each line is prefixed as:  "{LN:>W}│ "  (e.g., "   42│ ") where the bar is U+2502.

(c) 2025 — MIT License
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys
import hashlib
import ast
from dataclasses import dataclass
from typing import Iterable, Tuple, Any, Dict

# ----------------------------
# Core formatting primitives
# ----------------------------

@dataclass(frozen=True)
class PrefixStyle:
    name: str
    pattern: re.Pattern
    def make(self, n: int, width: int) -> str:
        raise NotImplementedError

class PipeStyle(PrefixStyle):
    def make(self, n: int, width: int) -> str:
        return f"{n:>{width}}│ "  # U+2502

class ColonStyle(PrefixStyle):
    def make(self, n: int, width: int) -> str:
        return f"{n:>{width}}: "

class BracketStyle(PrefixStyle):
    def make(self, n: int, width: int) -> str:
        return f"[L{n:0{width}d}] "

# Regexes that recognize our own prefixes ONLY (conservative stripping)
PIPE_RE   = re.compile(r"^(?P<prefix>\s*\d+\u2502\s)")
COLON_RE  = re.compile(r"^(?P<prefix>\s*\d+:\s)")
BRACK_RE  = re.compile(r"^(?P<prefix>\s*\[L\d+\]\s)")

STYLES = {
    "pipe": PipeStyle("pipe", PIPE_RE),
    "colon": ColonStyle("colon", COLON_RE),
    "bracket": BracketStyle("bracket", BRACK_RE),
}

# ----------------------------
# I/O helpers
# ----------------------------

def open_text_maybe(path: str) -> io.TextIOBase:
    if path == "-":
        return io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", newline="")
    return open(path, "r", encoding="utf-8", newline="")

def create_text_maybe(path: str) -> io.TextIOBase:
    if path == "-":
        return io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", newline="")
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    return open(path, "w", encoding="utf-8", newline="")

# ----------------------------
# Core operations
# ----------------------------

def detect_total_lines(path: str) -> int:
    total = 0
    with open_text_maybe(path) as fh:
        for _ in fh:
            total += 1
    return total

def annotate_lines(lines: Iterable[str], start: int, width: int, style: PrefixStyle) -> Iterable[str]:
    n = start
    for line in lines:
        yield f"{style.make(n, width)}{line}"
        n += 1

def strip_lines(lines: Iterable[str]) -> Iterable[str]:
    for line in lines:
        m = PIPE_RE.match(line) or COLON_RE.match(line) or BRACK_RE.match(line)
        if m:
            yield line[m.end("prefix"):]
        else:
            yield line

def line_hash(s: str) -> str:
    # Hash raw line content (no newline normalization; keep bytes as is)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def build_map(lines: Iterable[str]) -> Tuple[int, list]:
    total = 0
    entries = []
    for ln, line in enumerate(lines, start=1):
        total += 1
        entries.append({"n": ln, "hash": line_hash(line)})
    return total, entries

# ----------------------------
# Python AST export
# ----------------------------

AST_SAFE_FIELDS = (
    "lineno", "col_offset", "end_lineno", "end_col_offset",
    "name", "id", "arg", "attr",
)

def _node_span(d: Dict[str, Any]) -> Dict[str, Any]:
    # ... (this function remains the same)
    out = {}
    for k in AST_SAFE_FIELDS:
        if k in d:
            out[k] = d[k]
    return out

def _ast_node_to_dict(node: ast.AST) -> Dict[str, Any]:
    # ... (this function remains the same)
    d: Dict[str, Any] = {"type": type(node).__name__}
    for k, v in ast.iter_fields(node):
        if isinstance(v, ast.AST):
            continue
        if isinstance(v, list) and v and all(isinstance(x, ast.AST) for x in v):
            continue
        if isinstance(v, (str, int, float, bool)) and k in AST_SAFE_FIELDS:
            d[k] = v
    d.update(_node_span(getattr(node, "__dict__", {})))

    children = []
    for child in ast.iter_child_nodes(node):
        children.append(_ast_node_to_dict(child))
    if children:
        d["children"] = children
    return d

def build_py_ast(text: str, mode: str = "tree") -> Dict[str, Any]:
    # ... (this function remains the same)
    root = ast.parse(text)
    tree = _ast_node_to_dict(root)
    if mode == "tree":
        return {"language": "python", "mode": "tree", "root": tree}

    # flat mode
    flat, stack = [], [(tree, -1)]
    while stack:
        node, parent = stack.pop()
        idx = len(flat)
        entry = {k: v for k, v in node.items() if k != "children"}
        entry["parent"] = parent
        flat.append(entry)
        for ch in reversed(node.get("children", [])):
            stack.append((ch, idx))
    return {"language": "python", "mode": "flat", "nodes": flat}


# In linenumberizer.py, replace the existing SemanticVisitor class

class SemanticVisitor(ast.NodeVisitor):
    """
    An AST visitor that builds a list of "logical blocks" from the source.
    Implements suggestions from user feedback.
    """
    def __init__(self, depth: str = 'top'):
        self.depth = depth
        self.blocks: list[Dict[str, Any]] = []

    def _get_signature(self, node: ast.FunctionDef) -> Dict[str, Any]:
        # ... (this helper function remains the same as before)
        sig = {"params": [], "returns": None}
        if node.returns:
            sig["returns"] = ast.unparse(node.returns)
        
        defaults = [None] * (len(node.args.args) - len(node.args.defaults)) + [ast.unparse(d) for d in node.args.defaults]
        for arg, default_val in zip(node.args.args, defaults):
            param = {"name": arg.arg}
            if arg.annotation:
                param["annotation"] = ast.unparse(arg.annotation)
            if default_val is not None:
                param["default"] = default_val
            sig["params"].append(param)
        return sig

    def _process_node(self, node: ast.AST, is_top_level: bool = False):
        if not hasattr(node, 'lineno'):
            return

        # Suggestion 1: Use ast.unparse for robust source capture
        source_segment = ast.unparse(node)

        block = {
            "type": type(node).__name__,
            "span": (node.lineno, node.end_lineno),
        }
        
        node_name = getattr(node, 'name', '')
        if node_name:
            block['name'] = node_name

        # Process different node types
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            block["decorators"] = [ast.unparse(d) for d in node.decorator_list]
            if isinstance(node, ast.FunctionDef):
                 block["signature"] = self._get_signature(node)
        elif isinstance(node, ast.Import):
            block["names"] = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            block["module"] = node.module or ""
            block["names"] = [alias.name for alias in node.names]
        
        # Add source and hash after all fields are gathered
        block["source"] = source_segment
        block["hash"] = line_hash(source_segment)

        # Suggestion 4: Add a stable block ID
        hash_short = block['hash'][:8]
        block['id'] = f"{block['type']}:{node_name}:{block['span'][0]}:{block['span'][1]}:{hash_short}"

        # Decide whether to add the block and whether to recurse
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            self.blocks.append(block)
            if self.depth == 'all':
                for child in node.body:
                    self._process_node(child, is_top_level=False)
        
        # Suggestion 3: Capture imports inside functions if depth is 'all'
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            if is_top_level or self.depth == 'all':
                self.blocks.append(block)

        elif is_top_level:
             # Capture other top-level statements like assignments
             self.blocks.append(block)

    def visit_Module(self, node: ast.Module):
        for child in node.body:
            self._process_node(child, is_top_level=True)

# You will also need to update the `build_semantic_model` function slightly
# to remove the 'source_text' argument from the visitor's constructor.

def build_semantic_model(text: str, depth: str) -> Dict[str, Any]:
    """Builds a high-level list of logical blocks (functions, classes, etc.)."""
    root = ast.parse(text)
    visitor = SemanticVisitor(depth) # <-- Correctly calls with only 'depth'
    visitor.visit(root)
    sorted_blocks = sorted(visitor.blocks, key=lambda b: b['span'][0])
    return {"blocks": sorted_blocks}
    
# ----------------------------
# Command handlers
# ----------------------------

def cmd_annotate(args: argparse.Namespace) -> int:
    style = STYLES[args.style]
    total = detect_total_lines(args.file)
    width = max(args.width or 0, len(str(args.start + total - 1)), 3)

    out_path = args.out or suggest_out_path(args.file, suffix=numbered_suffix(args.style))
    with open_text_maybe(args.file) as inp:
        processed = annotate_lines(inp, start=args.start, width=width, style=style)
        if args.dry_run:
            for chunk in processed:
                sys.stdout.write(chunk)
        else:
            if args.inplace:
                tmp_path = out_path + ".tmp"
                with create_text_maybe(tmp_path) as out:
                    for chunk in processed:
                        out.write(chunk)
                os.replace(tmp_path, args.file)
                print(f"Annotated in-place: {args.file} (style={args.style}, width={width})")
            else:
                with create_text_maybe(out_path) as out:
                    for chunk in processed:
                        out.write(chunk)
                print(f"Annotated → {out_path} (style={args.style}, width={width})")

    if args.map:
        with open_text_maybe(out_path if not args.inplace else args.file) as fh:
            total2, entries = build_map(strip_prefix_for_map(fh))
        payload = {
            "source": os.path.abspath(args.file),
            "annotated": os.path.abspath(out_path if not args.inplace else args.file),
            "style": args.style,
            "width": width,
            "start": args.start,
            "total_lines": total2,
            "lines": entries,
        }
        with create_text_maybe(args.map) as m:
            json.dump(payload, m, indent=2)
        print(f"Map written → {args.map}")

    return 0

def strip_prefix_for_map(lines: Iterable[str]) -> Iterable[str]:
    for line in lines:
        m = PIPE_RE.match(line) or COLON_RE.match(line) or BRACK_RE.match(line)
        yield line[m.end("prefix"): ] if m else line


def cmd_strip(args: argparse.Namespace) -> int:
    with open_text_maybe(args.file) as inp:
        processed = strip_lines(inp)
        out_path = args.out or suggest_out_path(args.file, suffix=".stripped")
        if args.dry_run:
            for chunk in processed:
                sys.stdout.write(chunk)
        else:
            if args.inplace:
                tmp = out_path + ".tmp"
                with create_text_maybe(tmp) as out:
                    for chunk in processed:
                        out.write(chunk)
                os.replace(tmp, args.file)
                print(f"Stripped in-place: {args.file}")
            else:
                with create_text_maybe(out_path) as out:
                    for chunk in processed:
                        out.write(chunk)
                print(f"Stripped → {out_path}")
    return 0


def cmd_map(args: argparse.Namespace) -> int:
    with open_text_maybe(args.file) as fh:
        total, entries = build_map(strip_prefix_for_map(fh))
    payload = {
        "source": os.path.abspath(args.file),
        "total_lines": total,
        "lines": entries,
    }
    out_path = args.out or suggest_out_path(args.file, suffix=".linemap.json")
    with create_text_maybe(out_path) as out:
        json.dump(payload, out, indent=2)
    print(f"Map written → {out_path}")
    return 0


def cmd_ast(args: argparse.Namespace) -> int:
    """Export a Python AST as JSON. Gracefully handles non-Python inputs."""
    try:
        with open_text_maybe(args.file) as fh:
            src = fh.read()
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    out_path = args.out or suggest_out_path(args.file, suffix=f"._ast.{args.mode}.json")
    ext = os.path.splitext(args.file)[1].lower()

    if ext not in {".py", ""}:
        # Graceful no-op with stub payload for non-Python files
        stub = {
            "language": "unknown",
            "note": f"AST export currently supports Python (.py). Skipping '{args.file}'.",
            "supported": False,
        }
        with create_text_maybe(out_path) as out:
            json.dump(stub, out, indent=2)
        print(f"note: Non-Python file detected; wrote stub AST → {out_path}")
        return 0

    try:
        if args.mode in ("tree", "flat"):
            payload = build_py_ast(src, mode=args.mode)
        elif args.mode == "semantic":
            # Suggestion 4: Emit file-level metadata
            payload = {
                "language": "python",
                "mode": "semantic",
                "file_metadata": {
                    "path": os.path.abspath(args.file),
                    "total_lines": src.count('\n') + 1,
                    "last_modified": os.path.getmtime(args.file),
                }
            }
            semantic_data = build_semantic_model(src, depth=args.depth)
            payload.update(semantic_data)
        else:
            raise ValueError(f"Unknown AST mode: {args.mode}")

        with create_text_maybe(out_path) as out:
            json.dump(payload, out, indent=2)
        print(f"AST written → {out_path}")
        return 0
    except SyntaxError as e:
        line = getattr(e, 'lineno', '?')
        print(f"error: Python syntax error at line {line}: {e}", file=sys.stderr)
        return 3

# ----------------------------
# Utilities
# ----------------------------

def numbered_suffix(style: str) -> str:
    return f".numbered.{style}"

def suggest_out_path(src: str, suffix: str) -> str:
    base = os.path.abspath(src)
    return base + suffix

# ----------------------------
# CLI
# ----------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="linenumberizer",
        description="Annotate files with parseable line numbers; export maps and Python AST.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    # annotate
    a = sub.add_parser("annotate", help="Write a numbered copy of FILE")
    a.add_argument("file", help="Path to input file or '-' for stdin")
    a.add_argument("--out", "-o", help="Output path (default: FILE.numbered.<style> or stdout if --dry-run)")
    a.add_argument("--style", choices=STYLES.keys(), default="pipe", help="Prefix style")
    a.add_argument("--start", type=int, default=1, help="Starting line number (default: 1)")
    a.add_argument("--width", type=int, default=0, help="Minimum number width (auto if 0)")
    a.add_argument("--map", help="Also write a JSON line map to this path")
    a.add_argument("--dry-run", action="store_true", help="Write to stdout instead of a file")
    a.add_argument("--inplace", action="store_true", help="Replace FILE in-place (writes to temp and moves over)")
    a.set_defaults(func=cmd_annotate)

    # strip
    s = sub.add_parser("strip", help="Remove previously added line number prefixes")
    s.add_argument("file", help="Path to input file or '-' for stdin")
    s.add_argument("--out", "-o", help="Output path (default: FILE.stripped)")
    s.add_argument("--dry-run", action="store_true", help="Write to stdout instead of a file")
    s.add_argument("--inplace", action="store_true", help="Replace FILE in-place (writes to temp and moves over)")
    s.set_defaults(func=cmd_strip)

    # map
    m = sub.add_parser("map", help="Emit a JSON line→hash map for the (raw) content")
    m.add_argument("file", help="Path to input file or '-' for stdin")
    m.add_argument("--out", "-o", help="Output path (default: FILE.linemap.json)")
    m.set_defaults(func=cmd_map)

    # ast (Python)
    astd = sub.add_parser("ast", help="Export a Python AST (JSON)")
    astd.add_argument("file", help="Path to input file (Python .py recommended)")
    astd.add_argument("--out", "-o", help="Output JSON path (default: FILE._ast.json)")
    astd.add_argument("--mode", choices=("tree", "flat", "semantic"), default="tree", help="Tree(nested), flat list, or semantic blocks")
    astd.add_argument("--depth", choices=("top", "all"), default="top", help="For semantic mode: 'top' level blocks only, or 'all' nested blocks.")
    astd.set_defaults(func=cmd_ast)
    

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0
    except FileNotFoundError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

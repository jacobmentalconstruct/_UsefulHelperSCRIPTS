#!/usr/bin/env python3
"""
sync-ms-deps.py

Crawls a microservice directory and keeps two kinds of dependency metadata in each service:

  1) internal_dependencies
     - Local Python modules that must be vendored alongside the service.

  2) external_dependencies
     - Third-party packages that belong in requirements.txt (pip-installable).

The script is AST-only: it does NOT import/execute any microservices.

It can:
- Produce a report (Markdown + optional JSON)
- Optionally rewrite @service_metadata(...) decorators to include/update:
    internal_dependencies=[...]
    external_dependencies=[...]
- Optionally write a requirements.txt derived from external_dependencies

Typical usage:
  python sync-ms-deps.py . --report-only
  python sync-ms-deps.py . --fix
  python sync-ms-deps.py . --fix --write-requirements requirements.txt
"""

from __future__ import annotations

import ast
import argparse
import json
import io
import re
import tokenize
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any

MICROSERVICE_GLOB_DEFAULT = "*MS.py"
PY_GLOB = "*.py"

FALLBACK_STDLIB: Set[str] = {
    "abc", "argparse", "array", "asyncio", "base64", "binascii", "bisect",
    "calendar", "collections", "contextlib", "copy", "csv", "ctypes",
    "dataclasses", "datetime", "decimal", "difflib", "email", "enum", "fnmatch",
    "functools", "gc", "getpass", "glob", "gzip", "hashlib", "heapq", "hmac",
    "html", "http", "importlib", "inspect", "io", "ipaddress", "itertools",
    "json", "logging", "math", "mimetypes", "multiprocessing", "numbers",
    "operator", "os", "pathlib", "pickle", "platform", "plistlib", "pprint",
    "queue", "random", "re", "shlex", "shutil", "signal", "socket", "sqlite3",
    "ssl", "statistics", "string", "struct", "subprocess", "sys", "tempfile",
    "textwrap", "threading", "time", "tkinter", "traceback", "types",
    "typing", "unittest", "urllib", "uuid", "warnings", "weakref", "xml", "zipfile",
}

INHERITANCE_TO_INTERNAL_MODULE: Dict[str, str] = {
    "BaseService": "base_service",
}

META_KEY_INTERNAL = "internal_dependencies"
META_KEY_EXTERNAL = "external_dependencies"


@dataclass
class FileDeps:
    internal: List[str]
    external: List[str]
    declared_internal: List[str]
    errors: List[str]


@dataclass
class FileReport:
    file: str
    ok: bool
    changed: bool
    deps: FileDeps
    notes: List[str]


def get_stdlib_names() -> Set[str]:
    try:
        import sys
        names = set(getattr(sys, "stdlib_module_names", []))
        return names | FALLBACK_STDLIB
    except Exception:
        return set(FALLBACK_STDLIB)


def module_root(mod: str) -> str:
    return mod.split(".")[0].strip()


def normalize_dep_token(token: str) -> str:
    t = token.strip().strip('"').strip("'")
    if not t:
        return ""
    t = t.replace("\\", "/")
    if t.endswith(".py"):
        t = t[:-3]
        t = t.split("/")[-1]
    return t.strip()


def ast_list_of_str(values: List[str]) -> ast.AST:
    return ast.List(elts=[ast.Constant(v) for v in values], ctx=ast.Load())


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8", newline="\n")


def _deps_to_header_value(values: List[str]) -> str:
    return ", ".join(values) if values else "None"


def rewrite_manifest_header_deps(src: str, internal: List[str], external: List[str]) -> Tuple[bool, str]:
    """Rewrite the top manifest docstring to Option A fields.

    If the file begins with a triple-quoted manifest block that contains SERVICE_NAME/ENTRY_POINT,
    we will:
      - remove DEPENDENCIES: ...
      - set/insert INTERNAL_DEPENDENCIES: ...
      - set/insert EXTERNAL_DEPENDENCIES: ...

    We keep all other header keys untouched.
    """
    lines = src.splitlines(keepends=True)
    if not lines:
        return False, src

    i = 0
    prefix: List[str] = []

    # Preserve shebang and encoding cookies if present
    if lines[i].startswith("#!"):
        prefix.append(lines[i]); i += 1
    while i < len(lines) and (re.match(r"^#.*coding[:=]", lines[i]) or "coding" in lines[i] and lines[i].lstrip().startswith("#")):
        # keep common coding cookie comment lines
        prefix.append(lines[i]); i += 1

    # Preserve leading blank/comment lines
    while i < len(lines) and (lines[i].strip() == "" or lines[i].lstrip().startswith("#")):
        prefix.append(lines[i]); i += 1

    if i >= len(lines):
        return False, src

    stripped = lines[i].lstrip()
    if not (stripped.startswith('"""') or stripped.startswith("'''")):
        return False, src

    indent = lines[i][:len(lines[i]) - len(stripped)]
    quote = stripped[:3]

    # Collect docstring block
    doc_lines: List[str] = []
    start_i = i
    doc_lines.append(lines[i]); i += 1

    # If closing delimiter is on the same line (rare), handle it
    if quote in stripped[3:]:
        # one-line docstring; we won't rewrite it
        return False, src

    while i < len(lines):
        doc_lines.append(lines[i])
        if lines[i].strip().endswith(quote):
            i += 1
            break
        i += 1

    if not doc_lines or not doc_lines[-1].strip().endswith(quote):
        return False, src

    # Extract inner body lines (between opening and closing delimiter)
    inner = doc_lines[1:-1]
    inner_text = "".join(inner)

    # Parse key/value lines inside manifest
    kv_lines = inner_text.splitlines()
    parsed: List[Tuple[str, str]] = []
    for ln in kv_lines:
        s = ln.strip()
        if not s:
            continue
        if ":" not in s:
            # keep non-kv lines as a special key
            parsed.append(("__RAW__", ln))
            continue
        k, v = s.split(":", 1)
        parsed.append((k.strip(), v.strip()))

    keys = {k for (k, _) in parsed if k != "__RAW__"}
    if not ("SERVICE_NAME" in keys and "ENTRY_POINT" in keys):
        # Not our manifest format; leave untouched
        return False, src

    new_internal = _deps_to_header_value(internal)
    new_external = _deps_to_header_value(external)

    # Build output lines, preserving order and updating/inserting fields
    out: List[str] = []
    saw_internal = False
    saw_external = False

    def emit_kv(k: str, v: str) -> None:
        out.append(f"{indent}{k}: {v}\n")

    # Preserve RAW lines by re-emitting them exactly
    # Also drop DEPENDENCIES line entirely.
    for k, v in parsed:
        if k == "__RAW__":
            out.append(v if v.endswith("\n") else (v + "\n"))
            continue
        if k == "DEPENDENCIES":
            continue
        if k == "INTERNAL_DEPENDENCIES":
            emit_kv("INTERNAL_DEPENDENCIES", new_internal)
            saw_internal = True
            continue
        if k == "EXTERNAL_DEPENDENCIES":
            emit_kv("EXTERNAL_DEPENDENCIES", new_external)
            saw_external = True
            continue
        emit_kv(k, v)

    # If missing, insert after ENTRY_POINT (or after SERVICE_NAME as fallback)
    if not (saw_internal and saw_external):
        # Reconstruct with controlled insertion point
        rebuilt: List[str] = []
        inserted = False
        for ln in out:
            rebuilt.append(ln)
            if not inserted and ln.strip().startswith("ENTRY_POINT:"):
                if not saw_internal:
                    rebuilt.append(f"{indent}INTERNAL_DEPENDENCIES: {new_internal}\n")
                if not saw_external:
                    rebuilt.append(f"{indent}EXTERNAL_DEPENDENCIES: {new_external}\n")
                inserted = True
        if not inserted:
            # fallback: append at end
            if not saw_internal:
                rebuilt.append(f"{indent}INTERNAL_DEPENDENCIES: {new_internal}\n")
            if not saw_external:
                rebuilt.append(f"{indent}EXTERNAL_DEPENDENCIES: {new_external}\n")
        out = rebuilt

    # Rebuild docstring with same quote + indent
    new_doc = [doc_lines[0]] + out + [doc_lines[-1]]
    new_src = "".join(prefix) + "".join(new_doc) + "".join(lines[i:])
    return (new_src != src), new_src


# NOTE:
# Python emits SyntaxWarning for invalid escapes like "\s" inside normal string literals.
# This is common when someone writes regexes as "\s+" instead of r"\s+".
# We can repair those *in microservice files* before ast.parse(), so scanning stays clean.
_REGEX_ESCAPE_SEQS = ("\\s", "\\S", "\\d", "\\D", "\\w", "\\W")


def _string_token_is_raw(tok_string: str) -> bool:
    """Return True if a STRING token has a raw-string prefix (r/R anywhere in prefix)."""
    # Token looks like: r"...", fr"...", b"...", etc.
    # Prefix is everything before the first quote char.
    i = 0
    while i < len(tok_string) and tok_string[i] not in ("'", '"'):
        i += 1
    prefix = tok_string[:i]
    return ("r" in prefix.lower())


def fix_invalid_escapes_in_source(src: str, sequences: Tuple[str, ...] = _REGEX_ESCAPE_SEQS) -> Tuple[str, int]:
    """Return (new_src, num_fixes) by escaping common regex sequences in non-raw string literals.

    We only touch STRING tokens (via tokenize) to avoid modifying code/comments.
    Example: "\\s+" (invalid escape) -> "\\\\s+" (valid Python string that yields regex \\s+).
    """
    fixes = 0
    out_tokens: List[tokenize.TokenInfo] = []

    try:
        gen = tokenize.generate_tokens(io.StringIO(src).readline)
    except Exception:
        return src, 0

    for tok in gen:
        if tok.type != tokenize.STRING:
            out_tokens.append(tok)
            continue

        s = tok.string
        if _string_token_is_raw(s):
            out_tokens.append(tok)
            continue

        new_s = s
        for seq in sequences:
            # Replace only when the backslash isn't already escaped.
            # Pattern matches: \s but not \\s
            pat = r"(?<!\\)" + re.escape(seq)
            repl = r"\\" + seq[1:]  # '\\' + 's' => '\\s'
            new_s, n = re.subn(pat, repl, new_s)
            fixes += n

        if new_s != s:
            out_tokens.append(tok._replace(string=new_s))
        else:
            out_tokens.append(tok)

    try:
        new_src = tokenize.untokenize(out_tokens)
    except Exception:
        return src, 0

    return new_src, fixes


def repair_invalid_escapes_in_file(path: Path) -> Tuple[bool, int]:
    """Repair invalid escape sequences in a file. Returns (changed, fixes)."""
    src = read_text(path)
    new_src, fixes = fix_invalid_escapes_in_source(src)
    if fixes > 0 and new_src != src:
        write_text(path, new_src)
        return True, fixes
    return False, 0


def extract_string_collection(expr: ast.AST) -> Set[str]:
    out: Set[str] = set()

    def add_str(node: ast.AST) -> None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.strip()
            if s:
                out.add(s)

    if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
        for elt in expr.elts:
            add_str(elt)
        return out

    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id in {"set", "list", "tuple"}:
        if expr.args:
            return extract_string_collection(expr.args[0])
        return out

    if isinstance(expr, ast.Dict):
        for k in expr.keys:
            if k is not None:
                add_str(k)
        return out

    return out


class DepVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imports: Set[str] = set()
        self.from_imports: Set[str] = set()
        self.base_names: Set[str] = set()
        self.declared_dependencies: Set[str] = set()

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name:
                self.imports.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module is not None:
            self.from_imports.add(node.module)
        else:
            self.from_imports.add(".")
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        for base in node.bases:
            name = None
            if isinstance(base, ast.Name):
                name = base.id
            elif isinstance(base, ast.Attribute):
                name = base.attr
            if name:
                self.base_names.add(name)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        for t in node.targets:
            if isinstance(t, ast.Name) and t.id == "DEPENDENCIES":
                extracted = extract_string_collection(node.value)
                if extracted:
                    self.declared_dependencies |= extracted
        self.generic_visit(node)


def parse_service_metadata_dependencies(tree: ast.AST) -> Tuple[Set[str], Set[str]]:
    """Extract dependency hints from @service_metadata(...) decorators.

    We store state on the visitor instance (self.internal/self.external) instead of
    mutating outer-scope variables from inside visit_* methods.

    Reason: augmented assignment like `external |= ...` inside a method creates a
    local binding and can trigger UnboundLocalError.
    """

    class _MetaVisitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.internal: Set[str] = set()
            self.external: Set[str] = set()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            for dec in node.decorator_list:
                if not isinstance(dec, ast.Call):
                    continue

                func = dec.func
                if not (isinstance(func, ast.Name) and func.id == "service_metadata"):
                    continue

                for kw in dec.keywords:
                    if not kw.arg:
                        continue

                    if kw.arg in {"dependencies", META_KEY_EXTERNAL}:
                        self.external |= extract_string_collection(kw.value)
                    elif kw.arg == META_KEY_INTERNAL:
                        self.internal |= extract_string_collection(kw.value)

            self.generic_visit(node)

    v = _MetaVisitor()
    v.visit(tree)
    return v.internal, v.external


class ServiceMetadataRewriter(ast.NodeTransformer):
    def __init__(self, internal: List[str], external: List[str], remove_legacy_dependencies_arg: bool = True) -> None:
        self.internal = internal
        self.external = external
        self.remove_legacy = remove_legacy_dependencies_arg
        self.touched = False

    def visit_ClassDef(self, node: ast.ClassDef) -> ast.AST:
        if not node.decorator_list:
            return node

        new_decorators: List[ast.AST] = []
        for dec in node.decorator_list:
            new_decorators.append(self._rewrite_decorator(dec))
        node.decorator_list = new_decorators
        return node

    def _rewrite_decorator(self, dec: ast.AST) -> ast.AST:
        if not isinstance(dec, ast.Call):
            return dec
        func = dec.func
        if not (isinstance(func, ast.Name) and func.id == "service_metadata"):
            return dec

        kw_map: Dict[str, ast.keyword] = {kw.arg: kw for kw in dec.keywords if kw.arg}

        kw_map[META_KEY_INTERNAL] = ast.keyword(arg=META_KEY_INTERNAL, value=ast_list_of_str(self.internal))
        kw_map[META_KEY_EXTERNAL] = ast.keyword(arg=META_KEY_EXTERNAL, value=ast_list_of_str(self.external))

        if self.remove_legacy and "dependencies" in kw_map:
            del kw_map["dependencies"]

        original_order = [kw.arg for kw in dec.keywords if kw.arg]
        wanted: List[str] = []
        seen: Set[str] = set()
        for k in original_order:
            if k in kw_map and k not in seen:
                wanted.append(k); seen.add(k)
        for k in (META_KEY_INTERNAL, META_KEY_EXTERNAL):
            if k in kw_map and k not in seen:
                wanted.append(k); seen.add(k)
        for k in kw_map.keys():
            if k not in seen:
                wanted.append(k); seen.add(k)

        dec.keywords = [kw_map[k] for k in wanted if k in kw_map]
        self.touched = True
        return dec


def analyze_file(
    path: Path,
    stdlib: Set[str],
    local_modules: Set[str],
    repair_invalid_escapes: bool = False,
) -> Tuple[FileDeps, List[str]]:
    errors: List[str] = []
    notes: List[str] = []
    internal: Set[str] = set()
    external: Set[str] = set()
    declared_internal: Set[str] = set()

    # Optional pre-pass: repair invalid regex escapes like "\s" inside normal strings.
    if repair_invalid_escapes:
        changed, fixes = repair_invalid_escapes_in_file(path)
        if changed:
            notes.append(f"Repaired {fixes} invalid escape sequence(s) in string literals.")

    try:
        src = read_text(path)
        # Pass filename so any warnings/errors point at the real file instead of <unknown>
        tree = ast.parse(src, filename=str(path))
    except SyntaxError as e:
        return FileDeps(internal=[], external=[], declared_internal=[], errors=[f"SyntaxError: {e}"]), ["Could not parse AST"]

    dv = DepVisitor()
    dv.visit(tree)

    import_roots = {module_root(m) for m in dv.imports if m}
    from_roots = {module_root(m) for m in dv.from_imports if m and m != "."}
    relative_present = "." in dv.from_imports

    if relative_present:
        notes.append("Contains relative imports (treated as internal when resolvable).")

    for mod in sorted(import_roots | from_roots):
        if not mod:
            continue
        if mod in stdlib:
            continue
        if mod in local_modules:
            internal.add(mod)
        else:
            external.add(mod)

    for base in dv.base_names:
        if base in INHERITANCE_TO_INTERNAL_MODULE:
            internal.add(INHERITANCE_TO_INTERNAL_MODULE[base])

    for raw in dv.declared_dependencies:
        t = normalize_dep_token(raw)
        if not t:
            continue
        if t in local_modules:
            declared_internal.add(t)
            internal.add(t)
            continue
        if t.endswith("MS"):
            underscored = f"_{t}"
            if underscored in local_modules:
                declared_internal.add(underscored)
                internal.add(underscored)

    meta_internal, meta_external = parse_service_metadata_dependencies(tree)

    for raw in meta_internal:
        t = normalize_dep_token(raw)
        if t in local_modules:
            internal.add(t)

    for raw in meta_external:
        t = normalize_dep_token(raw)
        if t and (t not in stdlib) and (t not in local_modules):
            external.add(t)

    external = {e for e in external if e and e not in stdlib}

    deps = FileDeps(
        internal=sorted(internal),
        external=sorted(external),
        declared_internal=sorted(declared_internal),
        errors=errors,
    )
    return deps, notes


def rewrite_file_decorators(
    path: Path,
    internal: List[str],
    external: List[str],
    remove_legacy: bool = True,
    repair_invalid_escapes: bool = False,
) -> Tuple[bool, str]:
    # Optional pre-pass repair so parsing/unparsing doesn't spam warnings.
    if repair_invalid_escapes:
        repair_invalid_escapes_in_file(path)

    src = read_text(path)
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        return False, src

    rewriter = ServiceMetadataRewriter(internal, external, remove_legacy_dependencies_arg=remove_legacy)
    new_tree = rewriter.visit(tree)
    ast.fix_missing_locations(new_tree)

    if not rewriter.touched:
        return False, src

    try:
        new_src = ast.unparse(new_tree)
    except Exception:
        return False, src

    if not new_src.endswith("\n"):
        new_src += "\n"
    return (new_src != src), new_src


def render_report_md(reports: List[FileReport], root_dir: Path) -> str:
    lines: List[str] = []
    total = len(reports)
    ok = sum(1 for r in reports if r.ok)
    changed = sum(1 for r in reports if r.changed)

    lines.append("# Microservice Dependency Report")
    lines.append("")
    lines.append(f"- Root: `{root_dir}`")
    lines.append(f"- Files scanned: **{total}**")
    lines.append(f"- Parsed OK: **{ok}**")
    lines.append(f"- Rewritten files: **{changed}**")
    lines.append("")
    lines.append("## Per-file summary")
    lines.append("")
    lines.append("| File | Parsed | Changed | Internal deps | External deps | Notes/Errors |")
    lines.append("|---|---:|---:|---|---|---|")

    def fmt_list(xs: List[str]) -> str:
        return ", ".join(xs) if xs else ""

    for r in reports:
        parsed = "✅" if r.ok else "❌"
        ch = "✅" if r.changed else ""
        notes = "; ".join((r.notes + r.deps.errors)[:3])
        if len(r.notes + r.deps.errors) > 3:
            notes += " …"
        lines.append(
            f"| `{r.file}` | {parsed} | {ch} | {fmt_list(r.deps.internal)} | {fmt_list(r.deps.external)} | {notes} |"
        )

    all_external: Set[str] = set()
    for r in reports:
        all_external |= set(r.deps.external)

    lines.append("")
    lines.append("## Aggregate external dependencies (requirements candidates)")
    lines.append("")
    for dep in sorted(all_external):
        lines.append(f"- {dep}")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Sync microservice dependency metadata (internal vs external).")
    ap.add_argument("path", nargs="?", default=".", help="Microservice directory (default: .)")
    ap.add_argument("--ms-glob", default=MICROSERVICE_GLOB_DEFAULT, help=f"Glob for microservice files (default: {MICROSERVICE_GLOB_DEFAULT})")
    ap.add_argument("--fix", action="store_true", help="Rewrite @service_metadata(...) in files.")
    ap.add_argument("--report-only", action="store_true", help="Do not modify files (default behavior).")
    ap.add_argument("--write-report", default="ms_deps_report.md", help="Write markdown report to this path (default: ms_deps_report.md)")
    ap.add_argument("--write-report-json", default=None, help="Optional JSON report path.")
    ap.add_argument("--write-requirements", default=None, help="Write requirements.txt to this path (external deps aggregate).")
    ap.add_argument(
        "--repair-invalid-escapes",
        action="store_true",
        help="Repair invalid regex escapes like \\s in non-raw string literals inside scanned microservices.",
    )
    ap.add_argument(
        "--sync-header-deps",
        action="store_true",
        help="Rewrite the top manifest docstring to use INTERNAL_DEPENDENCIES / EXTERNAL_DEPENDENCIES (Option A).",
    )
    ap.add_argument("--remove-legacy-dependencies-arg", action="store_true", help="Remove legacy 'dependencies=' arg when rewriting.")
    ap.add_argument("--no-remove-legacy-dependencies-arg", dest="remove_legacy_dependencies_arg", action="store_false", help="Keep legacy 'dependencies=' arg when rewriting.")
    ap.set_defaults(remove_legacy_dependencies_arg=True)

    args = ap.parse_args(argv)
    root_dir = Path(args.path).resolve()
    if not root_dir.exists() or not root_dir.is_dir():
        print(f"[ERROR] Not a directory: {root_dir}")
        return 1

    local_modules: Set[str] = set()
    for py in root_dir.glob(PY_GLOB):
        if py.name.startswith(".") or py.name == "__init__.py":
            continue
        local_modules.add(py.stem)

    stdlib = get_stdlib_names()

    ms_files = sorted(root_dir.glob(args.ms_glob))
    if not ms_files:
        md = render_report_md([], root_dir)
        write_text(Path(args.write_report).resolve(), md)
        print(f"[WARN] No files matched '{args.ms_glob}' in {root_dir}. Wrote empty report.")
        return 0

    reports: List[FileReport] = []

    for fp in ms_files:
        deps, notes = analyze_file(
            fp,
            stdlib=stdlib,
            local_modules=local_modules,
            repair_invalid_escapes=args.repair_invalid_escapes,
        )
        ok = not deps.errors
        changed = False

        if ok:
            would_change, new_src = rewrite_file_decorators(
                fp,
                internal=deps.internal,
                external=deps.external,
                remove_legacy=args.remove_legacy_dependencies_arg,
                repair_invalid_escapes=args.repair_invalid_escapes,
            )

            header_would_change = False
            if args.sync_header_deps:
                header_would_change, new_src = rewrite_manifest_header_deps(
                    new_src,
                    internal=deps.internal,
                    external=deps.external,
                )
                if header_would_change:
                    notes.append("Synced manifest header deps (Option A).")

            total_would_change = would_change or header_would_change

            if args.fix:
                changed = total_would_change
                if changed:
                    write_text(fp, new_src)
            else:
                # dry run: mark files that *would* change
                changed = total_would_change

        reports.append(FileReport(
            file=fp.name,
            ok=ok,
            changed=changed,
            deps=deps,
            notes=notes,
        ))

    md = render_report_md(reports, root_dir)
    report_path = Path(args.write_report).resolve()
    write_text(report_path, md)

    if args.write_report_json:
        jp = Path(args.write_report_json).resolve()
        payload = {"root": str(root_dir), "files": [asdict(r) for r in reports]}
        write_text(jp, json.dumps(payload, indent=2, sort_keys=True))

    if args.write_requirements:
        reqs: Set[str] = set()
        for r in reports:
            reqs |= set(r.deps.external)
        req_path = Path(args.write_requirements).resolve()
        write_text(req_path, "\n".join(sorted(reqs)) + ("\n" if reqs else ""))

    print(f"[OK] Scanned {len(ms_files)} microservices in {root_dir}")
    print(f"     Report: {report_path}")
    if args.write_report_json:
        print(f"     JSON:   {Path(args.write_report_json).resolve()}")
    if args.write_requirements:
        print(f"     Reqs:   {Path(args.write_requirements).resolve()}")
    if args.fix:
        print(f"     Rewrote: {sum(1 for r in reports if r.changed)} file(s)")
    else:
        print(f"     (dry run) Would rewrite: {sum(1 for r in reports if r.changed)} file(s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())





"""tk_ui_mapper.py

Tkinter UI Mapper (AST-first, optional Ollama inference, human-in-the-loop decisions)

What it does (MVP):
- Choose a project folder
- Crawl .py files (excluding common junk)
- Find entrypoint candidates ("if __name__ == '__main__':" blocks)
- If multiple entrypoints are found, ask the user to pick one (HITL)
- Parse all project python files with AST to:
  - discover widget creation calls (tk/ttk constructors)
  - discover layout calls (.pack/.grid/.place)
  - discover wiring (command=, .bind, menu add_command)
  - discover handlers (function/method defs) and link when resolvable
- Collect UNKNOWN cases (dynamic parents, loops, getattr handlers, etc.)
- Optional: use Ollama model (default qwen2.5-coder:0.5b) to infer UNKNOWN cases
  - Still HITL: user can approve/skip inference results when ambiguity is high
- Export monolithic report as Markdown + JSON

No external deps: uses stdlib only.

Notes:
- AST does NOT preserve comments; this tool maps structure for reporting.
- Import resolution is deliberately lightweight. The report marks PROVEN vs INFERRED.

Author: Prototype for Raithe's _UsefulHelperSCRIPTS ecosystem
"""

from __future__ import annotations

import ast
import json
import os
import queue
import threading
import time
import traceback
import urllib.request
import urllib.error
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText


# -----------------------------
# Config
# -----------------------------

DEFAULT_MODEL = "qwen2.5-coder:0.5b"
DEFAULT_OLLAMA_URL = "http://localhost:11434"

EXCLUDE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache",
    "dist", "build", ".idea", ".vscode", "node_modules",
}

# ---- .gitignore support (stdlib-only, best-effort) ----
# We intentionally keep this lightweight (no pathspec dep).
# Supported patterns:
#   - blank lines / comments (# ...)
#   - directory patterns: .venv/  build/  dist/
#   - file globs: *.log  *.pyc
#   - simple basename entries: .env  thumbs.db
# Unsupported (will be ignored safely): negation (!pattern) and complex gitignore rules.

def _load_gitignore_patterns(project_root: Path) -> list[str]:
    gi = project_root / ".gitignore"
    if not gi.exists():
        return []
    try:
        raw = gi.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []

    patterns: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        # We intentionally do not implement negation in this MVP
        if s.startswith("!"):
            continue
        patterns.append(s)
    return patterns


def _is_ignored_by_gitignore(rel_posix: str, patterns: list[str]) -> bool:
    """Best-effort matcher for a subset of .gitignore patterns."""
    if not patterns:
        return False

    # normalize
    rel_posix = rel_posix.lstrip("/")
    base = rel_posix.split("/")[-1]

    for pat in patterns:
        p = pat.strip()
        if not p or p.startswith("#") or p.startswith("!"):
            continue

        # directory pattern
        if p.endswith("/"):
            dp = p.rstrip("/").lstrip("/")
            # match any segment == dp
            if f"/{dp}/" in f"/{rel_posix}/" or rel_posix.startswith(dp + "/"):
                return True
            continue

        # anchored path
        if "/" in p:
            ap = p.lstrip("/")
            # prefix match (treat like path glob without wildcards)
            if rel_posix == ap or rel_posix.startswith(ap.rstrip("/") + "/"):
                return True

        # glob (basename)
        if "*" in p or "?" in p:
            import fnmatch
            if fnmatch.fnmatch(base, p):
                return True
            continue

        # simple basename
        if base == p:
            return True

    return False

WIDGET_METHODS_LAYOUT = {"pack", "grid", "place"}
WIRING_METHODS = {"bind", "bind_all", "trace_add", "add_command", "add_checkbutton", "add_radiobutton"}


# -----------------------------
# Logging to Tk (queue-driven)
# -----------------------------

class TkLogger:
    def __init__(self, text: tk.Text):
        self.text = text
        self.q: "queue.Queue[str]" = queue.Queue()
        self.closed = False

    def log(self, msg: str):
        if self.closed:
            return
        ts = time.strftime("%H:%M:%S")
        self.q.put(f"[{ts}] {msg}\n")

    def pump(self):
        if self.closed:
            return
        try:
            while True:
                line = self.q.get_nowait()
                self.text.configure(state="normal")
                self.text.insert("end", line)
                self.text.see("end")
                self.text.configure(state="disabled")
        except queue.Empty:
            return

    def close(self):
        self.closed = True


# -----------------------------
# Data model
# -----------------------------

@dataclass
class EntrypointCandidate:
    file: str
    line: int
    summary: str


@dataclass
class WidgetNode:
    id: str
    file: str
    line: int
    name: str                    # variable or attribute name
    widget_type: str             # e.g., ttk.Button
    parent_expr: str             # textual expression
    kwargs: dict
    confidence: float            # 0..1 (AST confidence)


@dataclass
class LayoutCall:
    file: str
    line: int
    target: str                  # widget expression
    manager: str                 # pack/grid/place
    kwargs: dict


@dataclass
class WiringEdge:
    file: str
    line: int
    source: str                  # widget expression
    kind: str                    # command/bind/menu/trace
    event: Optional[str]         # e.g., "<Button-1>" for bind
    handler: str                 # handler expression
    confidence: float


@dataclass
class HandlerDef:
    file: str
    line: int
    qualname: str                # e.g., Class.method or function


@dataclass
class UnknownCase:
    case_type: str
    file: str
    line: int
    snippet: str
    question: str
    context: str


@dataclass
class InferenceResult:
    case: UnknownCase
    best_guess: str
    confidence: float
    evidence: list[str]
    explanation: str


@dataclass
class UiMap:
    project_root: str
    entrypoint: Optional[EntrypointCandidate]
    widgets: list[WidgetNode]
    layouts: list[LayoutCall]
    wiring: list[WiringEdge]
    handlers: list[HandlerDef]
    unknowns: list[UnknownCase]
    inferred: list[InferenceResult]


# -----------------------------
# Small AST utilities
# -----------------------------

class SourceLines:
    def __init__(self, text: str):
        self.text = text
        self.lines = text.splitlines()

    def snippet_around(self, line_1based: int, radius: int = 6) -> str:
        i = max(0, line_1based - 1 - radius)
        j = min(len(self.lines), line_1based - 1 + radius + 1)
        out = []
        for idx in range(i, j):
            out.append(f"{idx+1:>5}: {self.lines[idx]}")
        return "\n".join(out)

    def context_block(self, start_line_1based: int, end_line_1based: int) -> str:
        i = max(0, start_line_1based - 1)
        j = min(len(self.lines), end_line_1based)
        out = []
        for idx in range(i, j):
            out.append(f"{idx+1:>5}: {self.lines[idx]}")
        return "\n".join(out)


def is_main_guard_test(node: ast.AST) -> bool:
    # if __name__ == "__main__":
    if not isinstance(node, ast.Compare):
        return False
    if not isinstance(node.left, ast.Name) or node.left.id != "__name__":
        return False
    if len(node.ops) != 1 or not isinstance(node.ops[0], ast.Eq):
        return False
    if len(node.comparators) != 1:
        return False
    comp = node.comparators[0]
    return isinstance(comp, ast.Constant) and comp.value == "__main__"


def expr_to_str(node: ast.AST) -> str:
    # best-effort rendering
    try:
        return ast.unparse(node)  # py3.9+
    except Exception:
        return node.__class__.__name__


def literal_kwargs(call: ast.Call) -> dict:
    out: dict[str, Any] = {}
    for kw in call.keywords or []:
        if kw.arg is None:
            out["**kwargs"] = expr_to_str(kw.value)
            continue
        try:
            out[kw.arg] = ast.literal_eval(kw.value)
        except Exception:
            out[kw.arg] = expr_to_str(kw.value)
    return out


def looks_like_tk_constructor(func_expr: ast.AST) -> Optional[str]:
    """Return qualified name string if func looks like tk/ttk constructor, else None."""
    # Matches: tk.Button, ttk.Frame, tkinter.Tk, tkinter.ttk.Button, etc.
    if isinstance(func_expr, ast.Attribute):
        base = expr_to_str(func_expr.value)
        attr = func_expr.attr
        # simple heuristics
        if base in {"tk", "ttk", "tkinter", "tkinter.ttk"}:
            return f"{base}.{attr}"
        # some code uses aliased imports; we can't know. return None.
    return None


# -----------------------------
# Project crawling + entrypoints
# -----------------------------

def iter_py_files(project_root: Path) -> list[Path]:
    files: list[Path] = []

    # Load .gitignore patterns once (best-effort subset)
    gitignore_patterns = _load_gitignore_patterns(project_root)

    for root, dirs, filenames in os.walk(project_root):
        root_p = Path(root)
        rel_root = root_p.relative_to(project_root).as_posix() if root_p != project_root else ""

        # prune dirs by hard excludes + .gitignore
        kept_dirs: list[str] = []
        for d in dirs:
            if d in EXCLUDE_DIRS:
                continue

            rel_dir = f"{rel_root}/{d}" if rel_root else d

            # extra safety: never crawl common venv dirs even if gitignore missing
            if d.lower() in {".venv", "venv", "env"}:
                continue

            if _is_ignored_by_gitignore(rel_dir + "/", gitignore_patterns):
                continue

            kept_dirs.append(d)

        dirs[:] = kept_dirs

        for fn in filenames:
            if not fn.endswith(".py"):
                continue

            rel_file = f"{rel_root}/{fn}" if rel_root else fn
            if _is_ignored_by_gitignore(rel_file, gitignore_patterns):
                continue

            files.append(root_p / fn)

    return sorted(files)


def find_entrypoints(py_files: list[Path], log: TkLogger, cancel: threading.Event) -> list[EntrypointCandidate]:
    cands: list[EntrypointCandidate] = []
    for p in py_files:
        if cancel.is_set():
            return cands
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except Exception:
            continue

        for node in ast.walk(tree):
            if cancel.is_set():
                return cands
            if isinstance(node, ast.If) and is_main_guard_test(node.test):
                # summarize first non-empty line in the body
                body_summary = ""
                for b in node.body:
                    if isinstance(b, ast.Expr) and isinstance(b.value, ast.Constant) and isinstance(b.value.value, str):
                        continue
                    body_summary = expr_to_str(b)
                    break
                line = getattr(node, "lineno", 1)
                cands.append(EntrypointCandidate(file=str(p), line=int(line), summary=body_summary))
    log.log(f"Entrypoint candidates found: {len(cands)}")
    return cands


# -----------------------------
# AST Mapper
# -----------------------------

class TkUiAstMapper(ast.NodeVisitor):
    def __init__(self, file_path: Path, source: str, log: TkLogger):
        self.file_path = file_path
        self.src = source
        self.lines = SourceLines(source)
        self.log = log

        self.widgets: list[WidgetNode] = []
        self.layouts: list[LayoutCall] = []
        self.wiring: list[WiringEdge] = []
        self.handlers: list[HandlerDef] = []
        self.unknowns: list[UnknownCase] = []

        # scope tracking
        self._class_stack: list[str] = []

        # symbol tables: map var/attr name -> widget type
        self._widget_symbols: dict[str, str] = {}

    def current_qualprefix(self) -> str:
        return ".".join(self._class_stack) if self._class_stack else ""

    def visit_ClassDef(self, node: ast.ClassDef):
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef):
        q = self.current_qualprefix()
        qual = f"{q}.{node.name}" if q else node.name
        self.handlers.append(HandlerDef(file=str(self.file_path), line=getattr(node, "lineno", 1), qualname=qual))
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        q = self.current_qualprefix()
        qual = f"{q}.{node.name}" if q else node.name
        self.handlers.append(HandlerDef(file=str(self.file_path), line=getattr(node, "lineno", 1), qualname=qual))
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign):
        # widget creation if RHS is call to tk/ttk constructor
        if isinstance(node.value, ast.Call):
            ctor = looks_like_tk_constructor(node.value.func)
            if ctor:
                # name
                target_name = None
                if node.targets:
                    t0 = node.targets[0]
                    if isinstance(t0, ast.Name):
                        target_name = t0.id
                    elif isinstance(t0, ast.Attribute):
                        target_name = expr_to_str(t0)

                # parent expr = first arg if present
                parent_expr = expr_to_str(node.value.args[0]) if node.value.args else "<unknown>"
                kwargs = literal_kwargs(node.value)

                line = getattr(node, "lineno", 1)
                wid = f"{self.file_path}:{line}:{target_name or 'widget'}"

                confidence = 0.9 if parent_expr != "<unknown>" else 0.6

                self.widgets.append(
                    WidgetNode(
                        id=wid,
                        file=str(self.file_path),
                        line=int(line),
                        name=target_name or "<unnamed>",
                        widget_type=ctor,
                        parent_expr=parent_expr,
                        kwargs=kwargs,
                        confidence=confidence,
                    )
                )

                if target_name:
                    self._widget_symbols[target_name] = ctor

                # wiring: command=...
                if "command" in kwargs:
                    self.wiring.append(
                        WiringEdge(
                            file=str(self.file_path),
                            line=int(line),
                            source=target_name or wid,
                            kind="command",
                            event=None,
                            handler=str(kwargs["command"]),
                            confidence=0.85,
                        )
                    )

                # unknowns: if parent expr is complex
                if parent_expr.startswith("(") or "." in parent_expr and parent_expr.count("("):
                    self.unknowns.append(
                        UnknownCase(
                            case_type="DYNAMIC_PARENT",
                            file=str(self.file_path),
                            line=int(line),
                            snippet=self.lines.snippet_around(int(line), radius=3),
                            question="What is the likely parent container for this widget?",
                            context=self.lines.snippet_around(int(line), radius=12),
                        )
                    )

        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        # layout calls: x.pack/grid/place(...)
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            if attr in WIDGET_METHODS_LAYOUT:
                line = getattr(node, "lineno", 1)
                target = expr_to_str(node.func.value)
                kwargs = literal_kwargs(node)
                self.layouts.append(
                    LayoutCall(
                        file=str(self.file_path),
                        line=int(line),
                        target=target,
                        manager=attr,
                        kwargs=kwargs,
                    )
                )

            # wiring calls
            if attr in WIRING_METHODS:
                line = getattr(node, "lineno", 1)
                source = expr_to_str(node.func.value)
                kind = attr
                event = None
                handler = ""

                if attr in {"bind", "bind_all"}:
                    if node.args:
                        event = expr_to_str(node.args[0])
                    if len(node.args) >= 2:
                        handler = expr_to_str(node.args[1])
                elif attr == "trace_add":
                    # var.trace_add(mode, callback)
                    if node.args:
                        event = expr_to_str(node.args[0])
                    if len(node.args) >= 2:
                        handler = expr_to_str(node.args[1])
                else:
                    # menu.add_command(label=..., command=...)
                    k = literal_kwargs(node)
                    if "command" in k:
                        handler = str(k["command"])

                if handler:
                    self.wiring.append(
                        WiringEdge(
                            file=str(self.file_path),
                            line=int(line),
                            source=source,
                            kind="bind" if attr in {"bind", "bind_all"} else ("trace" if attr == "trace_add" else "menu"),
                            event=event,
                            handler=handler,
                            confidence=0.75,
                        )
                    )

                # unknowns: getattr handler
                if "getattr" in handler:
                    self.unknowns.append(
                        UnknownCase(
                            case_type="DYNAMIC_HANDLER",
                            file=str(self.file_path),
                            line=int(line),
                            snippet=self.lines.snippet_around(int(line), radius=3),
                            question="What handler does this resolve to at runtime?",
                            context=self.lines.snippet_around(int(line), radius=12),
                        )
                    )

        self.generic_visit(node)


def map_project_ast(project_root: Path, py_files: list[Path], log: TkLogger, cancel: threading.Event) -> UiMap:
    widgets: list[WidgetNode] = []
    layouts: list[LayoutCall] = []
    wiring: list[WiringEdge] = []
    handlers: list[HandlerDef] = []
    unknowns: list[UnknownCase] = []

    for p in py_files:
        if cancel.is_set():
            break
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(text)
        except Exception as e:
            log.log(f"SKIP parse error: {p} :: {e}")
            continue

        mapper = TkUiAstMapper(p, text, log)
        try:
            mapper.visit(tree)
        except Exception as e:
            log.log(f"ERROR mapping {p.name}: {e}")
            continue

        widgets.extend(mapper.widgets)
        layouts.extend(mapper.layouts)
        wiring.extend(mapper.wiring)
        handlers.extend(mapper.handlers)
        unknowns.extend(mapper.unknowns)

    return UiMap(
        project_root=str(project_root),
        entrypoint=None,
        widgets=widgets,
        layouts=layouts,
        wiring=wiring,
        handlers=handlers,
        unknowns=unknowns,
        inferred=[],
    )


# -----------------------------
# Ollama client (stdlib urllib)
# -----------------------------

class OllamaClient:
    def __init__(self, base_url: str, log: TkLogger):
        self.base_url = base_url.rstrip("/")
        self.log = log

    def list_models(self, timeout: float = 3.0) -> list[str]:
        url = f"{self.base_url}/api/tags"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            return sorted(models)
        except Exception as e:
            self.log.log(f"Ollama list_models failed: {e}")
            return []

    def generate_json(self, model: str, prompt: str, timeout: float = 30.0) -> dict:
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        j = json.loads(raw)
        # Ollama returns {'response': '...'}
        txt = j.get("response", "")
        # Try parse as JSON
        try:
            return json.loads(txt)
        except Exception:
            return {"raw": txt}


def build_inference_prompt(case: UnknownCase) -> str:
    schema = {
        "best_guess": "string",
        "confidence": "0..1",
        "evidence": ["line refs or short quotes"],
        "explanation": "short"
    }
    return (
        "You are helping map a Tkinter UI using static AST evidence.\n"
        "Only infer what is strongly supported by the provided code context.\n"
        "Return ONLY valid JSON with keys: best_guess, confidence, evidence, explanation.\n\n"
        f"CASE_TYPE: {case.case_type}\n"
        f"QUESTION: {case.question}\n\n"
        "SNIPPET:\n"
        f"{case.snippet}\n\n"
        "CONTEXT:\n"
        f"{case.context}\n\n"
        "JSON_SCHEMA_EXAMPLE:\n"
        f"{json.dumps(schema, indent=2)}\n"
    )


# -----------------------------
# Reporting
# -----------------------------

def write_report_md(ui: UiMap, out_path: Path):
    def fmt_conf(x: float) -> str:
        return f"{x:.2f}"

    lines: list[str] = []
    lines.append(f"# Tkinter UI Map Report\n")
    lines.append(f"**Project Root:** `{ui.project_root}`\n")

    if ui.entrypoint:
        lines.append("## Entrypoint (Selected)\n")
        lines.append(f"- File: `{ui.entrypoint.file}`\n")
        lines.append(f"- Line: {ui.entrypoint.line}\n")
        lines.append(f"- Summary: `{ui.entrypoint.summary}`\n")

    lines.append("## Widgets (PROVEN via AST)\n")
    for w in sorted(ui.widgets, key=lambda x: (x.file, x.line)):
        lines.append(f"- **{w.widget_type}** `{w.name}`  ")
        lines.append(f"  - Location: `{w.file}`:{w.line}  ")
        lines.append(f"  - Parent: `{w.parent_expr}`  ")
        lines.append(f"  - Kwargs: `{json.dumps(w.kwargs, sort_keys=True)}`  ")
        lines.append(f"  - Confidence: {fmt_conf(w.confidence)}\n")

    lines.append("## Layout Calls (PROVEN via AST)\n")
    for lc in sorted(ui.layouts, key=lambda x: (x.file, x.line)):
        lines.append(f"- `{lc.target}`.{lc.manager}({json.dumps(lc.kwargs, sort_keys=True)})  ")
        lines.append(f"  - Location: `{lc.file}`:{lc.line}\n")

    lines.append("## Wiring (PROVEN via AST)\n")
    for e in sorted(ui.wiring, key=lambda x: (x.file, x.line)):
        ev = f" event={e.event}" if e.event else ""
        lines.append(f"- **{e.kind}** source=`{e.source}` handler=`{e.handler}`{ev}  ")
        lines.append(f"  - Location: `{e.file}`:{e.line}  ")
        lines.append(f"  - Confidence: {fmt_conf(e.confidence)}\n")

    lines.append("## Handlers Discovered (PROVEN via AST defs)\n")
    for h in sorted(ui.handlers, key=lambda x: (x.file, x.line, x.qualname)):
        lines.append(f"- `{h.qualname}`  ({h.file}:{h.line})")
    lines.append("\n")

    lines.append("## Unknowns (AST could not resolve)\n")
    for u in sorted(ui.unknowns, key=lambda x: (x.file, x.line)):
        lines.append(f"### {u.case_type} @ `{u.file}`:{u.line}\n")
        lines.append(f"**Question:** {u.question}\n")
        lines.append("```\n" + u.snippet + "\n```\n")

    if ui.inferred:
        lines.append("## Inferred (LLM-assisted)\n")
        for inf in ui.inferred:
            u = inf.case
            lines.append(f"### {u.case_type} @ `{u.file}`:{u.line}\n")
            lines.append(f"- **Best guess:** {inf.best_guess}\n")
            lines.append(f"- **Confidence:** {fmt_conf(inf.confidence)}\n")
            if inf.evidence:
                lines.append("- **Evidence:**\n")
                for ev in inf.evidence:
                    lines.append(f"  - {ev}\n")
            lines.append(f"- **Explanation:** {inf.explanation}\n")

    out_path.write_text("\n".join(lines), encoding="utf-8")


def write_report_json(ui: UiMap, out_path: Path):
    # Convert dataclasses to JSON-serializable
    def ser(o):
        if hasattr(o, "__dataclass_fields__"):
            return asdict(o)
        raise TypeError

    out_path.write_text(json.dumps(ui, default=ser, indent=2), encoding="utf-8")


# -----------------------------
# HITL dialogs
# -----------------------------

class CandidatePicker(tk.Toplevel):
    def __init__(self, master: tk.Tk, cands: list[EntrypointCandidate]):
        super().__init__(master)
        self.title("Select Entrypoint")
        self.geometry("820x380")
        self.resizable(True, True)
        self.choice: Optional[EntrypointCandidate] = None

        ttk.Label(self, text="Multiple entrypoints were found. Select the one that launches the UI.").pack(anchor="w", padx=10, pady=(10, 6))

        cols = ("file", "line", "summary")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=12)
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=220 if c == "file" else 80, stretch=True)
        self.tree.column("summary", width=460)
        self.tree.pack(fill="both", expand=True, padx=10)

        for i, c in enumerate(cands):
            self.tree.insert("", "end", iid=str(i), values=(c.file, c.line, c.summary))

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="Select", command=self._select).pack(side="right")
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side="right", padx=(0, 8))

        self.tree.bind("<Double-1>", lambda e: self._select())

        self.grab_set()
        self.transient(master)

    def _select(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Pick one", "Select an entrypoint candidate.", parent=self)
            return
        idx = int(sel[0])
        vals = self.tree.item(sel[0], "values")
        self.choice = EntrypointCandidate(file=vals[0], line=int(vals[1]), summary=vals[2])
        self.destroy()

    def _cancel(self):
        self.choice = None
        self.destroy()


# -----------------------------
# Main App
# -----------------------------

class TkUiMapperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Tkinter UI Mapper (AST + optional Ollama)")
        self.geometry("980x720")

        self.cancel_flag = threading.Event()
        self.worker: Optional[threading.Thread] = None

        # state
        self.project_dir = tk.StringVar(value=str(Path.cwd()))
        self.ollama_url = tk.StringVar(value=DEFAULT_OLLAMA_URL)
        self.model = tk.StringVar(value=DEFAULT_MODEL)
        self.use_llm = tk.BooleanVar(value=True)

        self.ui_map: Optional[UiMap] = None

        # top controls
        top = ttk.Frame(self)
        top.pack(fill="x", padx=10, pady=10)

        ttk.Label(top, text="Project folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.project_dir).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(top, text="Browse…", command=self.pick_project).grid(row=0, column=2)

        ttk.Label(top, text="Ollama URL:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.ollama_url).grid(row=1, column=1, sticky="ew", padx=6, pady=(8, 0))
        ttk.Button(top, text="Refresh models", command=self.refresh_models).grid(row=1, column=2, pady=(8, 0))

        ttk.Label(top, text="Model:").grid(row=2, column=0, sticky="w", pady=(8, 0))
        self.model_combo = ttk.Combobox(top, textvariable=self.model, values=[DEFAULT_MODEL], state="readonly")
        self.model_combo.grid(row=2, column=1, sticky="w", padx=6, pady=(8, 0))

        ttk.Checkbutton(top, text="Use LLM to infer unknowns (HITL)", variable=self.use_llm).grid(row=2, column=2, sticky="w", pady=(8, 0))

        top.columnconfigure(1, weight=1)

        # buttons
        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10)
        self.run_btn = ttk.Button(btns, text="Run Map", command=self.run_map)
        self.run_btn.pack(side="left")
        self.save_btn = ttk.Button(btns, text="Save Report", command=self.save_report, state="disabled")
        self.save_btn.pack(side="left", padx=(8, 0))
        self.cancel_btn = ttk.Button(btns, text="Cancel", command=self.cancel, state="disabled")
        self.cancel_btn.pack(side="left", padx=(8, 0))

        # log
        self.log_text = ScrolledText(self, height=28)
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)
        self.log_text.configure(state="disabled")
        self.log = TkLogger(self.log_text)

        self.after(80, self._pump)

    def _pump(self):
        self.log.pump()
        self.after(80, self._pump)

    def pick_project(self):
        d = filedialog.askdirectory(title="Select project folder")
        if d:
            self.project_dir.set(d)

    def cancel(self):
        self.log.log("Cancel requested…")
        self.cancel_flag.set()

    def set_busy(self, busy: bool):
        self.run_btn.configure(state="disabled" if busy else "normal")
        self.save_btn.configure(state="disabled" if busy or not self.ui_map else "normal")
        self.cancel_btn.configure(state="normal" if busy else "disabled")

    def refresh_models(self):
        # async refresh
        self.log.log("Refreshing Ollama models…")
        url = self.ollama_url.get().strip()
        client = OllamaClient(url, self.log)

        def _work():
            models = client.list_models()
            def _apply():
                if models:
                    self.model_combo["values"] = models
                    # keep default if present
                    if self.model.get() not in models and DEFAULT_MODEL in models:
                        self.model.set(DEFAULT_MODEL)
                    elif self.model.get() not in models and models:
                        self.model.set(models[0])
                    self.log.log(f"Loaded {len(models)} model(s) from Ollama")
                else:
                    self.log.log("No models returned (is Ollama running?)")
            self.after(0, _apply)

        threading.Thread(target=_work, daemon=True).start()

    def run_map(self):
        root = Path(self.project_dir.get()).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            messagebox.showerror("Invalid folder", "Select a valid project folder.")
            return

        self.cancel_flag.clear()
        self.ui_map = None
        self.set_busy(True)

        def _worker():
            try:
                self.log.log(f"Scanning project: {root}")
                py_files = iter_py_files(root)
                self.log.log(f"Python files found: {len(py_files)}")

                cands = find_entrypoints(py_files, self.log, self.cancel_flag)
                entry = None

                if self.cancel_flag.is_set():
                    raise RuntimeError("Cancelled")

                # HITL: select entrypoint when ambiguous
                if len(cands) == 0:
                    self.log.log("No __main__ entrypoints found. Proceeding with AST mapping anyway.")
                elif len(cands) == 1:
                    entry = cands[0]
                    self.log.log(f"Selected entrypoint: {entry.file}:{entry.line}")
                else:
                    # ask user on UI thread
                    entry = self._ask_pick_entrypoint(cands)
                    if entry is None:
                        raise RuntimeError("User cancelled entrypoint selection")
                    self.log.log(f"User selected entrypoint: {entry.file}:{entry.line}")

                if self.cancel_flag.is_set():
                    raise RuntimeError("Cancelled")

                ui_map = map_project_ast(root, py_files, self.log, self.cancel_flag)
                ui_map.entrypoint = entry

                self.log.log(f"AST map done: widgets={len(ui_map.widgets)} layouts={len(ui_map.layouts)} wiring={len(ui_map.wiring)} unknowns={len(ui_map.unknowns)}")

                if self.use_llm.get() and ui_map.unknowns and not self.cancel_flag.is_set():
                    self.log.log("LLM inference enabled: starting UNKNOWN case inference (HITL)…")
                    inferred = self._infer_unknowns_hitl(ui_map.unknowns)
                    ui_map.inferred = inferred
                    self.log.log(f"LLM inference complete: inferred={len(inferred)}")

                self.ui_map = ui_map

                def _done():
                    self.set_busy(False)
                    self.save_btn.configure(state="normal")
                    self.log.log("Run complete.")

                self.after(0, _done)

            except Exception as e:
                tb = traceback.format_exc()
                self.log.log(f"ERROR: {e}\n{tb}")
                self.after(0, lambda: self.set_busy(False))

        self.worker = threading.Thread(target=_worker, daemon=True)
        self.worker.start()

    def _ask_pick_entrypoint(self, cands: list[EntrypointCandidate]) -> Optional[EntrypointCandidate]:
        # synchronous ask (but must run on main thread)
        result_holder: dict[str, Any] = {"choice": None}
        ev = threading.Event()

        def _show():
            dlg = CandidatePicker(self, cands)
            self.wait_window(dlg)
            result_holder["choice"] = dlg.choice
            ev.set()

        self.after(0, _show)
        ev.wait()
        return result_holder["choice"]

    def _infer_unknowns_hitl(self, unknowns: list[UnknownCase]) -> list[InferenceResult]:
        url = self.ollama_url.get().strip()
        model = self.model.get().strip() or DEFAULT_MODEL
        client = OllamaClient(url, self.log)

        results: list[InferenceResult] = []

        for idx, case in enumerate(unknowns, start=1):
            if self.cancel_flag.is_set():
                self.log.log("Inference cancelled.")
                break

            self.log.log(f"Infer {idx}/{len(unknowns)}: {case.case_type} @ {Path(case.file).name}:{case.line}")
            prompt = build_inference_prompt(case)

            try:
                j = client.generate_json(model=model, prompt=prompt, timeout=45.0)
            except Exception as e:
                self.log.log(f"Ollama inference failed: {e}")
                continue

            # parse
            best_guess = str(j.get("best_guess", j.get("raw", ""))).strip()
            conf = j.get("confidence", 0.4)
            try:
                conf_f = float(conf)
            except Exception:
                conf_f = 0.4
            evidence = j.get("evidence", [])
            if not isinstance(evidence, list):
                evidence = [str(evidence)]
            explanation = str(j.get("explanation", "")).strip()

            inf = InferenceResult(
                case=case,
                best_guess=best_guess,
                confidence=max(0.0, min(1.0, conf_f)),
                evidence=[str(x) for x in evidence][:8],
                explanation=explanation,
            )

            # HITL approval for low confidence
            approved = self._ask_approve_inference(inf)
            if approved:
                results.append(inf)
                self.log.log(f"Approved inference: {inf.best_guess} (conf={inf.confidence:.2f})")
            else:
                self.log.log("Skipped inference (user declined).")

        return results

    def _ask_approve_inference(self, inf: InferenceResult) -> bool:
        # Always HITL prompt; user can skip noisy guesses.
        holder = {"ok": False}
        ev = threading.Event()

        def _show():
            msg = (
                f"UNKNOWN: {inf.case.case_type}\n"
                f"Location: {inf.case.file}:{inf.case.line}\n\n"
                f"Best guess: {inf.best_guess}\n"
                f"Confidence: {inf.confidence:.2f}\n\n"
                f"Explanation: {inf.explanation}\n\n"
                "Approve this inference to include it in the report?"
            )
            holder["ok"] = messagebox.askyesno("Approve inference?", msg, parent=self)
            ev.set()

        self.after(0, _show)
        ev.wait()
        return bool(holder["ok"])

    def save_report(self):
        if not self.ui_map:
            messagebox.showinfo("Nothing to save", "Run the mapper first.")
            return

        out_dir = filedialog.askdirectory(title="Select output folder")
        if not out_dir:
            return

        out = Path(out_dir)
        md_path = out / "ui_map_report.md"
        js_path = out / "ui_map_report.json"

        try:
            write_report_md(self.ui_map, md_path)
            write_report_json(self.ui_map, js_path)
            self.log.log(f"Saved report: {md_path}")
            self.log.log(f"Saved report: {js_path}")
            messagebox.showinfo("Saved", f"Report saved to:\n{md_path}\n{js_path}")
        except Exception as e:
            messagebox.showerror("Save failed", str(e))


if __name__ == "__main__":
    app = TkUiMapperApp()
    app.mainloop()


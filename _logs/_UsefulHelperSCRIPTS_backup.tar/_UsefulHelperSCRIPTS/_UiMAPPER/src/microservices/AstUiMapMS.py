"""
AstUiMapMS
----------
AST-driven UI mapping microservice.

Responsibilities:
- Consume parsed ASTs (from AstParseCacheMS) for a project
- Detect Tkinter UI constructs and extract a "UI Map" model:
    - windows / roots
    - widget constructions
    - geometry/layout calls (pack/grid/place)
    - config/style calls (configure, config, ttk.Style)
    - command/callback bindings (command=..., bind(...))
    - menu structures (Menu/add_command)
- Collect "unknown cases" for optional LLM/HITL inference

Non-goals:
- Project crawling / .gitignore filtering
- Threading / cancellation ownership (accepts a cancel predicate)
- LLM calls (backend orchestrator uses OllamaClientMS)
- UI (Tk) rendering

This is intentionally conservative: when uncertain, it records an UnknownCase.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple


# -------------------------
# Data Model
# -------------------------

@dataclass(frozen=True)
class SourceLoc:
    path: Path
    lineno: Optional[int] = None
    col: Optional[int] = None


@dataclass
class UiWidget:
    widget_id: str
    widget_type: str
    parent_id: Optional[str]
    created_at: SourceLoc
    kwargs: Dict[str, str] = field(default_factory=dict)
    layout_calls: List[str] = field(default_factory=list)
    config_calls: List[str] = field(default_factory=list)
    command_targets: List[str] = field(default_factory=list)
    bind_events: List[str] = field(default_factory=list)


@dataclass
class UiWindow:
    window_id: str
    created_at: SourceLoc
    title_calls: List[str] = field(default_factory=list)
    geometry_calls: List[str] = field(default_factory=list)
    config_calls: List[str] = field(default_factory=list)


@dataclass
class UnknownCase:
    kind: str
    detail: str
    where: SourceLoc
    snippet: Optional[str] = None


@dataclass
class UiMap:
    project_root: Path
    windows: Dict[str, UiWindow] = field(default_factory=dict)
    widgets: Dict[str, UiWidget] = field(default_factory=dict)
    unknowns: List[UnknownCase] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)


# -------------------------
# Config
# -------------------------

@dataclass
class AstUiMapConfig:
    # If True, include non-Tk UI constructs (future); currently unused.
    include_generic_ui: bool = False


# -------------------------
# Service
# -------------------------

class AstUiMapMS:
    def __init__(self, project_root: Path, config: Optional[AstUiMapConfig] = None):
        self.root = Path(project_root).resolve()
        self.config = config or AstUiMapConfig()

    def map_project(
        self,
        ast_by_path: Dict[Path, ast.AST],
        *,
        cancel: Optional[Callable[[], bool]] = None,
        log: Optional[Callable[[str], None]] = None,
    ) -> UiMap:
        """
        Build a UiMap from a dict of {path: ast_tree}.
        """
        cancel = cancel or (lambda: False)
        log = log or (lambda _msg: None)

        ui_map = UiMap(project_root=self.root)

        # Deterministic iteration
        for path in sorted(ast_by_path.keys(), key=lambda p: p.as_posix().lower()):
            if cancel():
                break
            tree = ast_by_path[path]
            try:
                self._map_file(path, tree, ui_map, log=log, cancel=cancel)
            except Exception as e:
                ui_map.unknowns.append(
                    UnknownCase(
                        kind="mapper_exception",
                        detail=str(e),
                        where=SourceLoc(path=path),
                    )
                )

        return ui_map

    # -------------------------
    # File mapping
    # -------------------------

    def _map_file(
        self,
        path: Path,
        tree: ast.AST,
        ui_map: UiMap,
        *,
        log: Callable[[str], None],
        cancel: Callable[[], bool],
    ) -> None:
        visitor = _TkAstVisitor(path=path, ui_map=ui_map, log=log, cancel=cancel)
        visitor.visit(tree)


# -------------------------
# AST Visitor
# -------------------------

class _TkAstVisitor(ast.NodeVisitor):
    """
    Conservative Tkinter/ttk UI mapper.

    It detects:
    - tk.Tk() / tkinter.Tk() root creation
    - ttk/tk widget constructors: Button/Frame/Label/Entry/etc.
    - .pack/.grid/.place calls
    - .configure/.config calls
    - `command=` callback names
    - .bind("...") events
    """

    TK_ROOT_NAMES = {"Tk"}
    LAYOUT_METHODS = {"pack", "grid", "place"}
    CONFIG_METHODS = {"config", "configure"}
    BIND_METHOD = "bind"

    # Common widget ctor names (heuristic)
    WIDGET_NAMES = {
        "Frame", "Label", "Button", "Entry", "Text", "Canvas", "Menu", "Scrollbar",
        "Listbox", "Toplevel", "Checkbutton", "Radiobutton", "Spinbox", "Scale",
        "PanedWindow", "LabelFrame", "Message",
        # ttk
        "Combobox", "Treeview", "Notebook", "Separator", "Progressbar",
    }

    def __init__(
        self,
        *,
        path: Path,
        ui_map: UiMap,
        log: Callable[[str], None],
        cancel: Callable[[], bool],
    ):
        self.path = path
        self.ui_map = ui_map
        self.log = log
        self.cancel = cancel

        # Basic symbol tracking
        self._imports: Dict[str, str] = {}  # alias -> module (e.g., tk -> tkinter)
        self._assigned_ids: Dict[str, str] = {}  # varname -> widget_id/window_id

        self._next_id = 1

    # -------------------------
    # Helpers
    # -------------------------

    def _new_id(self, prefix: str) -> str:
        i = self._next_id
        self._next_id += 1
        return f"{prefix}{i}"

    def _loc(self, node: ast.AST) -> SourceLoc:
        return SourceLoc(
            path=self.path,
            lineno=getattr(node, "lineno", None),
            col=getattr(node, "col_offset", None),
        )

    def _expr_to_str(self, node: ast.AST) -> str:
        """
        Best-effort compact string for an AST expression.
        Conservative: returns placeholders when complex.
        """
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            base = self._expr_to_str(node.value)
            return f"{base}.{node.attr}"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Call):
            fn = self._expr_to_str(node.func)
            return f"{fn}(...)"
        if isinstance(node, ast.Subscript):
            return f"{self._expr_to_str(node.value)}[...]"
        return node.__class__.__name__

    def _call_name(self, call: ast.Call) -> str:
        return self._expr_to_str(call.func)

    def _is_tk_root_call(self, call: ast.Call) -> bool:
        # tk.Tk(), tkinter.Tk(), or bare Tk() if imported
        fn = call.func
        if isinstance(fn, ast.Attribute) and fn.attr in self.TK_ROOT_NAMES:
            return True
        if isinstance(fn, ast.Name) and fn.id in self.TK_ROOT_NAMES:
            return True
        return False

    def _is_widget_ctor_call(self, call: ast.Call) -> Optional[str]:
        """
        Return widget type name if this call looks like a widget constructor.
        """
        fn = call.func
        # ttk.Button / tk.Frame
        if isinstance(fn, ast.Attribute) and fn.attr in self.WIDGET_NAMES:
            return fn.attr
        # bare Button() (from tkinter import Button)
        if isinstance(fn, ast.Name) and fn.id in self.WIDGET_NAMES:
            return fn.id
        return None

    def _extract_parent_id(self, call: ast.Call) -> Optional[str]:
        """
        First positional argument for widget constructors is usually parent.
        If it's a known var, map to widget_id/window_id.
        """
        if not call.args:
            return None
        a0 = call.args[0]
        if isinstance(a0, ast.Name):
            return self._assigned_ids.get(a0.id)
        return None

    def _extract_kwargs(self, call: ast.Call) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for kw in call.keywords:
            if kw.arg is None:
                continue
            out[kw.arg] = self._expr_to_str(kw.value)
        return out

    def _maybe_record_command(self, widget: UiWidget, kwargs: Dict[str, str]) -> None:
        cmd = kwargs.get("command")
        if cmd:
            widget.command_targets.append(cmd)

    # -------------------------
    # Visit nodes
    # -------------------------

    def visit_Import(self, node: ast.Import) -> Any:
        for alias in node.names:
            name = alias.name  # e.g., tkinter
            asname = alias.asname or name
            self._imports[asname] = name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        # from tkinter import ttk as ttk
        mod = node.module or ""
        for alias in node.names:
            asname = alias.asname or alias.name
            self._imports[asname] = f"{mod}.{alias.name}" if mod else alias.name
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> Any:
        # var = Call(...)
        if self.cancel():
            return None

        if isinstance(node.value, ast.Call):
            call = node.value

            # Root window
            if self._is_tk_root_call(call):
                win_id = self._new_id("win")
                w = UiWindow(window_id=win_id, created_at=self._loc(node))
                self.ui_map.windows[win_id] = w

                for t in node.targets:
                    if isinstance(t, ast.Name):
                        self._assigned_ids[t.id] = win_id

                self.generic_visit(node)
                return None

            # Widget ctor
            wtype = self._is_widget_ctor_call(call)
            if wtype:
                wid = self._new_id("w")
                parent_id = self._extract_parent_id(call)
                kwargs = self._extract_kwargs(call)

                w = UiWidget(
                    widget_id=wid,
                    widget_type=wtype,
                    parent_id=parent_id,
                    created_at=self._loc(node),
                    kwargs=kwargs,
                )
                self._maybe_record_command(w, kwargs)
                self.ui_map.widgets[wid] = w

                for t in node.targets:
                    if isinstance(t, ast.Name):
                        self._assigned_ids[t.id] = wid

                self.generic_visit(node)
                return None

        self.generic_visit(node)
        return None

    def visit_Call(self, node: ast.Call) -> Any:
        if self.cancel():
            return None

        # method calls like: widget.pack(...), root.title(...), widget.configure(...)
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            receiver = node.func.value

            recv_id = None
            if isinstance(receiver, ast.Name):
                recv_id = self._assigned_ids.get(receiver.id)

            # Layout calls
            if attr in self.LAYOUT_METHODS and recv_id and recv_id in self.ui_map.widgets:
                w = self.ui_map.widgets[recv_id]
                w.layout_calls.append(f"{attr}({self._args_sig(node)})")
                self.generic_visit(node)
                return None

            # Config calls
            if attr in self.CONFIG_METHODS and recv_id:
                sig = f"{attr}({self._args_sig(node)})"
                if recv_id in self.ui_map.widgets:
                    self.ui_map.widgets[recv_id].config_calls.append(sig)
                elif recv_id in self.ui_map.windows:
                    self.ui_map.windows[recv_id].config_calls.append(sig)
                else:
                    self.ui_map.unknowns.append(
                        UnknownCase(
                            kind="config_on_unknown_receiver",
                            detail=f"{self._expr_to_str(receiver)}.{attr}",
                            where=self._loc(node),
                        )
                    )
                self.generic_visit(node)
                return None

            # Window title / geometry
            if recv_id and recv_id in self.ui_map.windows:
                if attr == "title":
                    self.ui_map.windows[recv_id].title_calls.append(self._call_render(node))
                elif attr == "geometry":
                    self.ui_map.windows[recv_id].geometry_calls.append(self._call_render(node))

            # bind events
            if attr == self.BIND_METHOD and recv_id and recv_id in self.ui_map.widgets:
                w = self.ui_map.widgets[recv_id]
                ev = self._extract_bind_event(node)
                w.bind_events.append(ev)
                self.generic_visit(node)
                return None

        self.generic_visit(node)
        return None

    # -------------------------
    # Call rendering helpers
    # -------------------------

    def _args_sig(self, call: ast.Call) -> str:
        """
        Compact signature string: positional + keyword names.
        """
        parts: List[str] = []
        for a in call.args:
            parts.append(self._expr_to_str(a))
        for kw in call.keywords:
            if kw.arg is None:
                parts.append("**kwargs")
            else:
                parts.append(f"{kw.arg}={self._expr_to_str(kw.value)}")
        return ", ".join(parts)

    def _call_render(self, call: ast.Call) -> str:
        return f"{self._call_name(call)}({self._args_sig(call)})"

    def _extract_bind_event(self, call: ast.Call) -> str:
        """
        bind("<Button-1>", handler) => "<Button-1> -> handler"
        """
        event = "<?>"
        handler = "<?>"
        if call.args:
            event = self._expr_to_str(call.args[0])
        if len(call.args) >= 2:
            handler = self._expr_to_str(call.args[1])
        return f"{event} -> {handler}"


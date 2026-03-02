"""
CallbackGraphBuilderMS
----------------------
Build a callback/call graph focused on UI event wiring.

Goal:
- Given ASTs and UI mapping data, build a directed graph showing:
    - widgets/events -> handler functions
    - handler functions -> other functions they call
- This enables "what triggers what" exploration.

Responsibilities:
- Extract handler targets from:
    - widget ctor kwargs: command=...
    - .bind(event, handler)
    - Menu.add_command(command=...)
- Build function index per module:
    - def name(...)
    - methods: ClassName.method
- Build intra-file call edges using conservative name/attr call extraction
- Provide a simple graph model and unknowns list

Non-goals:
- Perfect static analysis (imports, dynamic dispatch, lambdas)
- Cross-module resolution via import aliasing (future)
- Execution / tracing
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


# -------------------------
# Data Model
# -------------------------

@dataclass(frozen=True)
class GraphNode:
    """
    Node kinds:
    - "event": UI event source (widget_id + event kind)
    - "func": function or method symbol
    """
    kind: str
    key: str  # stable identifier


@dataclass(frozen=True)
class GraphEdge:
    src: GraphNode
    dst: GraphNode
    kind: str  # "event_to_handler" | "calls"


@dataclass
class CallbackGraph:
    nodes: Dict[str, GraphNode] = field(default_factory=dict)
    edges: List[GraphEdge] = field(default_factory=list)
    unknowns: List[str] = field(default_factory=list)


# -------------------------
# Service
# -------------------------

class CallbackGraphBuilderMS:
    """
    Build a callback graph from:
        - ast_by_path: {Path: ast.AST}
        - ui_map-like info:
            - widgets with command_targets and bind_events
            - (optional) mapping var->widget_id already done by AstUiMapMS

    This service does not depend on a specific UiMap class; it uses duck-typing.
    """

    def build(
        self,
        ast_by_path: Dict[Path, ast.AST],
        ui_map: object,
    ) -> CallbackGraph:
        graph = CallbackGraph()

        # 1) Index functions
        func_index = self._index_functions(ast_by_path)

        # 2) Add event->handler edges from ui_map
        self._add_event_edges(ui_map, func_index, graph)

        # 3) Add function call edges by scanning bodies
        self._add_call_edges(ast_by_path, func_index, graph)

        return graph

    # -------------------------
    # Function indexing
    # -------------------------

    def _index_functions(self, ast_by_path: Dict[Path, ast.AST]) -> Dict[str, Tuple[Path, ast.AST]]:
        """
        Returns:
            symbol_key -> (path, node)
        symbol_key formats:
            - modulepath::funcname
            - modulepath::ClassName.method
        """
        idx: Dict[str, Tuple[Path, ast.AST]] = {}

        for path in sorted(ast_by_path.keys(), key=lambda p: p.as_posix().lower()):
            tree = ast_by_path[path]
            modkey = self._module_key(path)
            visitor = _FunctionIndexVisitor(modkey=modkey)
            visitor.visit(tree)
            for k, n in visitor.found.items():
                idx[k] = (path, n)

        return idx

    def _module_key(self, path: Path) -> str:
        return path.as_posix()

    # -------------------------
    # UI event edges
    # -------------------------

    def _add_event_edges(self, ui_map: object, func_index: Dict[str, Tuple[Path, ast.AST]], graph: CallbackGraph) -> None:
        """
        ui_map.widgets is expected to be a dict-like of widget objects:
            widget.widget_id
            widget.command_targets: List[str]
            widget.bind_events: List[str] entries like "<Button-1> -> handler"
        """
        widgets = getattr(ui_map, "widgets", {}) or {}

        for wid, w in widgets.items():
            widget_id = getattr(w, "widget_id", str(wid))

            # command= callbacks
            for target in getattr(w, "command_targets", []) or []:
                self._link_event_to_handler(
                    graph,
                    event_key=f"{widget_id}:command",
                    handler_expr=target,
                    func_index=func_index,
                )

            # bind callbacks: "<Event> -> handler"
            for bind in getattr(w, "bind_events", []) or []:
                # stored as string; parse conservatively
                try:
                    ev, handler = bind.split("->", 1)
                    ev = ev.strip()
                    handler = handler.strip()
                except Exception:
                    graph.unknowns.append(f"unparseable_bind:{widget_id}:{bind}")
                    continue

                self._link_event_to_handler(
                    graph,
                    event_key=f"{widget_id}:bind:{ev}",
                    handler_expr=handler,
                    func_index=func_index,
                )

    def _link_event_to_handler(
        self,
        graph: CallbackGraph,
        *,
        event_key: str,
        handler_expr: str,
        func_index: Dict[str, Tuple[Path, ast.AST]],
    ) -> None:
        ev_node = self._get_node(graph, "event", event_key)

        # handler_expr might be "self.on_click" or "on_click" or "lambda ..."
        handler_symbol = self._resolve_handler_expr(handler_expr, func_index)

        if handler_symbol is None:
            graph.unknowns.append(f"unresolved_handler:{event_key}:{handler_expr}")
            return

        fn_node = self._get_node(graph, "func", handler_symbol)
        graph.edges.append(GraphEdge(src=ev_node, dst=fn_node, kind="event_to_handler"))

    def _resolve_handler_expr(
        self,
        handler_expr: str,
        func_index: Dict[str, Tuple[Path, ast.AST]],
    ) -> Optional[str]:
        s = handler_expr.strip()

        if s.startswith("lambda"):
            return None

        # If already looks like module-qualified symbol key, accept.
        if "::" in s:
            return s if s in func_index else None

        # Normalize "self.foo" -> try any "::Class.method" and "::foo"
        if s.startswith("self."):
            meth = s.split(".", 1)[1]
            # Try any method match ending with ".meth"
            candidates = [k for k in func_index.keys() if k.endswith(f".{meth}")]
            if len(candidates) == 1:
                return candidates[0]
            if len(candidates) > 1:
                return None
            # Try free function name
            candidates = [k for k in func_index.keys() if k.endswith(f"::{meth}")]
            if len(candidates) == 1:
                return candidates[0]
            return None

        # Bare name: find unique match
        candidates = [k for k in func_index.keys() if k.endswith(f"::{s}")]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            return None

        # Attribute form "obj.fn"
        if "." in s:
            tail = s.split(".")[-1]
            candidates = [k for k in func_index.keys() if k.endswith(f"::{tail}") or k.endswith(f".{tail}")]
            if len(candidates) == 1:
                return candidates[0]

        return None

    # -------------------------
    # Call edges
    # -------------------------

    def _add_call_edges(self, ast_by_path: Dict[Path, ast.AST], func_index: Dict[str, Tuple[Path, ast.AST]], graph: CallbackGraph) -> None:
        """
        Build edges between functions based on ast.Call nodes inside each function body.
        """
        for sym, (path, node) in func_index.items():
            fn_calls = _CallCollectorVisitor()
            fn_calls.visit(node)

            src = self._get_node(graph, "func", sym)

            for called in fn_calls.called_names:
                dst_sym = self._resolve_called_name(called, func_index)
                if dst_sym is None:
                    # unknown external call; ignore quietly or record
                    continue
                dst = self._get_node(graph, "func", dst_sym)
                graph.edges.append(GraphEdge(src=src, dst=dst, kind="calls"))

    def _resolve_called_name(self, called: str, func_index: Dict[str, Tuple[Path, ast.AST]]) -> Optional[str]:
        """
        called may be:
            - foo
            - self.foo
            - mod.foo
        Resolve conservatively to a unique symbol in index.
        """
        s = called.strip()

        if s.startswith("self."):
            tail = s.split(".", 1)[1]
            candidates = [k for k in func_index.keys() if k.endswith(f".{tail}")]
            if len(candidates) == 1:
                return candidates[0]
            return None

        # bare function name
        if "." not in s:
            candidates = [k for k in func_index.keys() if k.endswith(f"::{s}")]
            if len(candidates) == 1:
                return candidates[0]
            return None

        # attribute call: mod.foo or obj.foo
        tail = s.split(".")[-1]
        candidates = [k for k in func_index.keys() if k.endswith(f"::{tail}") or k.endswith(f".{tail}")]
        if len(candidates) == 1:
            return candidates[0]

        return None

    # -------------------------
    # Graph helpers
    # -------------------------

    def _get_node(self, graph: CallbackGraph, kind: str, key: str) -> GraphNode:
        nk = f"{kind}:{key}"
        node = graph.nodes.get(nk)
        if node is None:
            node = GraphNode(kind=kind, key=key)
            graph.nodes[nk] = node
        return node


# -------------------------
# Visitors
# -------------------------

class _FunctionIndexVisitor(ast.NodeVisitor):
    def __init__(self, modkey: str):
        self.modkey = modkey
        self.class_stack: List[str] = []
        self.found: Dict[str, ast.AST] = {}

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)
        self.generic_visit(node)
        self.class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        key = self._make_key(node.name)
        self.found[key] = node
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        key = self._make_key(node.name)
        self.found[key] = node
        self.generic_visit(node)

    def _make_key(self, fn_name: str) -> str:
        if self.class_stack:
            cls = self.class_stack[-1]
            return f"{self.modkey}::{cls}.{fn_name}"
        return f"{self.modkey}::{fn_name}"


class _CallCollectorVisitor(ast.NodeVisitor):
    """
    Collect simple call target strings.
    """
    def __init__(self):
        self.called_names: Set[str] = set()

    def visit_Call(self, node: ast.Call) -> None:
        self.called_names.add(self._call_to_str(node.func))
        self.generic_visit(node)

    def _call_to_str(self, node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            # self.foo / mod.foo
            base = self._call_to_str(node.value)
            return f"{base}.{node.attr}"
        return node.__class__.__name__


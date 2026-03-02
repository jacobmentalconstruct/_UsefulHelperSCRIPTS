"""
TkWidgetDetectorMS
------------------
AST utility microservice for detecting Tkinter/ttk widget construction patterns.

Why this exists (separation of concerns):
- AstUiMapMS should orchestrate "mapping" and aggregation.
- TkWidgetDetectorMS should provide tight, testable detection utilities.

Responsibilities:
- Identify whether an ast.Call looks like:
    - root window creation (Tk())
    - widget constructor call (Frame/Button/etc.)
    - Menu construction
    - layout call (pack/grid/place)
    - config call (configure/config)
    - bind call (bind)
- Extract:
    - widget type name
    - parent expression
    - keyword args (best-effort stringification)
    - command callback targets

Non-goals:
- Whole-file traversal
- Project mapping
- LLM inference
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple


# -------------------------
# Data Structures
# -------------------------

@dataclass(frozen=True)
class DetectedWidgetCall:
    widget_type: str
    parent_expr: Optional[str]
    kwargs: Dict[str, str]
    command_target: Optional[str]


@dataclass(frozen=True)
class DetectedMethodCall:
    method: str
    receiver_expr: str
    args_sig: str


# -------------------------
# Service
# -------------------------

class TkWidgetDetectorMS:
    """
    Stateless detection + extraction helpers.
    """

    # Conservative common set; extend later.
    TK_ROOT_NAMES: Set[str] = {"Tk"}
    LAYOUT_METHODS: Set[str] = {"pack", "grid", "place"}
    CONFIG_METHODS: Set[str] = {"config", "configure"}
    BIND_METHOD: str = "bind"
    MENU_METHODS: Set[str] = {"add_command", "add_separator", "add_cascade"}

    WIDGET_NAMES: Set[str] = {
        # tkinter
        "Frame", "Label", "Button", "Entry", "Text", "Canvas", "Menu", "Scrollbar",
        "Listbox", "Toplevel", "Checkbutton", "Radiobutton", "Spinbox", "Scale",
        "PanedWindow", "LabelFrame", "Message",
        # ttk
        "Combobox", "Treeview", "Notebook", "Separator", "Progressbar",
    }

    # -------------------------
    # Primary detectors
    # -------------------------

    def is_tk_root_call(self, call: ast.Call) -> bool:
        """
        tk.Tk(), tkinter.Tk(), or bare Tk()
        """
        fn = call.func
        if isinstance(fn, ast.Attribute) and fn.attr in self.TK_ROOT_NAMES:
            return True
        if isinstance(fn, ast.Name) and fn.id in self.TK_ROOT_NAMES:
            return True
        return False

    def detect_widget_ctor(self, call: ast.Call) -> Optional[DetectedWidgetCall]:
        """
        If call is a widget constructor, return extracted details.
        """
        widget_type = self._widget_type(call)
        if not widget_type:
            return None

        parent_expr = self._extract_parent_expr(call)
        kwargs = self._extract_kwargs(call)
        cmd = kwargs.get("command")

        return DetectedWidgetCall(
            widget_type=widget_type,
            parent_expr=parent_expr,
            kwargs=kwargs,
            command_target=cmd,
        )

    def detect_layout_call(self, call: ast.Call) -> Optional[DetectedMethodCall]:
        """
        widget.pack(...) / widget.grid(...) / widget.place(...)
        """
        return self._detect_attr_call(call, self.LAYOUT_METHODS)

    def detect_config_call(self, call: ast.Call) -> Optional[DetectedMethodCall]:
        """
        widget.configure(...) / widget.config(...)
        """
        return self._detect_attr_call(call, self.CONFIG_METHODS)

    def detect_bind_call(self, call: ast.Call) -> Optional[DetectedMethodCall]:
        """
        widget.bind(event, handler, ...)
        """
        if not isinstance(call.func, ast.Attribute):
            return None
        if call.func.attr != self.BIND_METHOD:
            return None
        recv = self.expr_to_str(call.func.value)
        return DetectedMethodCall(
            method=self.BIND_METHOD,
            receiver_expr=recv,
            args_sig=self.call_args_sig(call),
        )

    def detect_menu_method(self, call: ast.Call) -> Optional[DetectedMethodCall]:
        """
        menu.add_command(...) / add_separator / add_cascade
        """
        return self._detect_attr_call(call, self.MENU_METHODS)

    # -------------------------
    # Extraction utilities
    # -------------------------

    def expr_to_str(self, node: ast.AST) -> str:
        """
        Conservative stringification.
        Designed for diagnostics + mapping, not round-tripping.
        """
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self.expr_to_str(node.value)}.{node.attr}"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Call):
            return f"{self.expr_to_str(node.func)}(...)"
        if isinstance(node, ast.Subscript):
            return f"{self.expr_to_str(node.value)}[...]"
        if isinstance(node, ast.JoinedStr):
            return "f'...'"
        return node.__class__.__name__

    def call_args_sig(self, call: ast.Call) -> str:
        parts: List[str] = []
        for a in call.args:
            parts.append(self.expr_to_str(a))
        for kw in call.keywords:
            if kw.arg is None:
                parts.append("**kwargs")
            else:
                parts.append(f"{kw.arg}={self.expr_to_str(kw.value)}")
        return ", ".join(parts)

    # -------------------------
    # Internal helpers
    # -------------------------

    def _widget_type(self, call: ast.Call) -> Optional[str]:
        fn = call.func
        if isinstance(fn, ast.Attribute) and fn.attr in self.WIDGET_NAMES:
            return fn.attr
        if isinstance(fn, ast.Name) and fn.id in self.WIDGET_NAMES:
            return fn.id
        return None

    def _extract_parent_expr(self, call: ast.Call) -> Optional[str]:
        if not call.args:
            return None
        return self.expr_to_str(call.args[0])

    def _extract_kwargs(self, call: ast.Call) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for kw in call.keywords:
            if kw.arg is None:
                continue
            out[kw.arg] = self.expr_to_str(kw.value)
        return out

    def _detect_attr_call(self, call: ast.Call, allowed: Set[str]) -> Optional[DetectedMethodCall]:
        if not isinstance(call.func, ast.Attribute):
            return None
        if call.func.attr not in allowed:
            return None
        recv = self.expr_to_str(call.func.value)
        return DetectedMethodCall(
            method=call.func.attr,
            receiver_expr=recv,
            args_sig=self.call_args_sig(call),
        )


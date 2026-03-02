"""
ui.py
-----
UI orchestrator for UiMAPPER.

Design goals:
- Own ALL Tkinter concerns: theme/colors, widgets, layout, user interactions.
- Be an orchestrator: no business logic / analysis logic inside.
- Talks to backend orchestrator via a small API:
    - start_run(project_root, settings)
    - cancel_run()
    - get_state_dict()
    - take_latest_decision_plan()
- Subscribes to ProgressEventBusMS and marshals events onto Tk thread.
- Maintains lightweight UI state (selected folder, settings toggles).

This file provides:
- UiOrchestrator class with:
    - build(root) -> Frame (main container)
    - set_backend(backend) (dependency injection)
    - attach_event_bus(bus) (subscribe)
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Callable, List

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# -------------------------
# Backend import
# -------------------------

# Adjust import to match your project.
from .backend import BackendOrchestrator, BackendSettings
from .microservices.OllamaModelSelectorMS import OllamaModelSelectorMS

# -------------------------
# Theme (match your helper scripts)
# -------------------------

@dataclass(frozen=True)
class Theme:
    bg: str = "#0f1117"
    panel: str = "#151a22"
    panel2: str = "#11151c"
    fg: str = "#e6edf3"
    muted: str = "#9aa4b2"
    accent: str = "#6cb6ff"
    warn: str = "#f2cc60"
    err: str = "#ff6b6b"
    ok: str = "#7ee787"
    border: str = "#243042"
    entry_bg: str = "#0b0e14"
    sel_bg: str = "#243b55"
    sel_fg: str = "#e6edf3"


THEME = Theme()


def apply_dark_ttk_style(root: tk.Tk) -> None:
    """
    Minimal ttk dark theme. This should be aligned with your microservice examples.
    """
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass

    style.configure(".", font=("Segoe UI", 10), foreground=THEME.fg)
    style.configure("TFrame", background=THEME.bg)
    style.configure("Panel.TFrame", background=THEME.panel)
    style.configure("TLabel", background=THEME.bg, foreground=THEME.fg)
    style.configure("Muted.TLabel", background=THEME.bg, foreground=THEME.muted)

    style.configure("TButton", background=THEME.panel, foreground=THEME.fg, borderwidth=1)
    style.map(
        "TButton",
        background=[("active", THEME.panel2)],
        foreground=[("disabled", THEME.muted)],
    )

    style.configure("Accent.TButton", background=THEME.accent, foreground="#081018")
    style.map("Accent.TButton", background=[("active", THEME.accent)])

    style.configure("TEntry", fieldbackground=THEME.entry_bg, foreground=THEME.fg)
    style.configure("TCheckbutton", background=THEME.bg, foreground=THEME.fg)
    style.map("TCheckbutton", foreground=[("disabled", THEME.muted)])

    style.configure("TNotebook", background=THEME.bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=THEME.panel, foreground=THEME.fg, padding=(10, 6))
    style.map("TNotebook.Tab", background=[("selected", THEME.panel2)])

    style.configure(
        "Treeview",
        background=THEME.panel,
        fieldbackground=THEME.panel,
        foreground=THEME.fg,
        bordercolor=THEME.border,
        lightcolor=THEME.border,
        darkcolor=THEME.border,
        rowheight=22,
    )
    style.map("Treeview", background=[("selected", THEME.sel_bg)], foreground=[("selected", THEME.sel_fg)])
    style.configure("Treeview.Heading", background=THEME.panel2, foreground=THEME.fg, relief="flat")

    style.configure("TScrollbar", background=THEME.panel, troughcolor=THEME.bg, bordercolor=THEME.bg, arrowcolor=THEME.fg)


# -------------------------
# UI Orchestrator
# -------------------------

class UiOrchestrator:
    def __init__(self, backend: BackendOrchestrator):
        self.backend = backend
        self.bus = backend.bus

        self.root: Optional[tk.Tk] = None
        self.container: Optional[ttk.Frame] = None

        # UI vars
        self.var_project_root = tk.StringVar(value="")
        self.var_enable_inference = tk.BooleanVar(value=False)
        self.var_model = tk.StringVar(value="")
        self.var_include_pyw = tk.BooleanVar(value=True)

        # Widgets we update
        self._status_lbl: Optional[ttk.Label] = None
        self._counts_lbl: Optional[ttk.Label] = None
        self._log_text: Optional[tk.Text] = None
        self._tree: Optional[ttk.Treeview] = None
        self._structure_tree: Optional[ttk.Treeview] = None
        self._model_selector: Optional[tk.Frame] = None

        # Progress event queue (marshalled with after). Guard with a lock because callbacks may fire off-thread.
        self._event_queue: List[Dict[str, Any]] = []
        self._event_queue_limit = 500
        self._event_lock = threading.Lock()

        # Subscribe once
        self.bus.subscribe(self._on_progress_event)

    # -------------------------
    # Public
    # -------------------------

    def build(self, root: tk.Tk) -> ttk.Frame:
        self.root = root
        apply_dark_ttk_style(root)
        root.configure(bg=THEME.bg)

        self.container = ttk.Frame(root, style="TFrame")
        self.container.pack(fill="both", expand=True)

        self._build_header(self.container)
        self._build_body(self.container)
        self._build_footer(self.container)

        # Start periodic UI update loop
        self._tick()

        return self.container

    def destroy(self) -> None:
        # Unsubscribe
        try:
            self.bus.unsubscribe(self._on_progress_event)
        except Exception:
            pass

    # -------------------------
    # Layout
    # -------------------------

    def _build_header(self, parent: ttk.Frame) -> None:
        hdr = ttk.Frame(parent, style="Panel.TFrame")
        hdr.pack(fill="x", padx=10, pady=(10, 6))

        title = ttk.Label(hdr, text="UiMAPPER", font=("Segoe UI", 14, "bold"), background=THEME.panel, foreground=THEME.fg)
        title.grid(row=0, column=0, sticky="w", padx=10, pady=8)

        self._status_lbl = ttk.Label(hdr, text="idle", style="Muted.TLabel", background=THEME.panel)
        self._status_lbl.grid(row=0, column=1, sticky="e", padx=10)

        hdr.columnconfigure(0, weight=1)
        hdr.columnconfigure(1, weight=0)

    def _build_body(self, parent: ttk.Frame) -> None:
        body = ttk.Frame(parent, style="TFrame")
        body.pack(fill="both", expand=True, padx=10, pady=6)

        # Left: controls + log
        left = ttk.Frame(body, style="Panel.TFrame")
        left.pack(side="left", fill="y", padx=(0, 8), pady=0)

        self._build_controls(left)
        self._build_log(left)

        # Right: results
        right = ttk.Frame(body, style="Panel.TFrame")
        right.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=0)

        self._build_results(right)

        left.configure(padding=10)
        right.configure(padding=10)

    def _build_controls(self, parent: ttk.Frame) -> None:
        box = ttk.Frame(parent, style="Panel.TFrame")
        box.pack(fill="x")

        # Project root
        ttk.Label(box, text="Project Root", background=THEME.panel, foreground=THEME.fg).grid(row=0, column=0, sticky="w")
        ent = ttk.Entry(box, textvariable=self.var_project_root, width=42)
        ent.grid(row=1, column=0, sticky="ew", pady=(4, 6))
        btn_browse = ttk.Button(box, text="Browse…", command=self._browse_folder)
        btn_browse.grid(row=1, column=1, sticky="e", padx=(8, 0), pady=(4, 6))

        # Options
        chk_pyw = ttk.Checkbutton(box, text="Include .pyw", variable=self.var_include_pyw)
        chk_pyw.grid(row=2, column=0, sticky="w", pady=(2, 2))

        chk_inf = ttk.Checkbutton(box, text="Enable inference (Ollama)", variable=self.var_enable_inference)
        chk_inf.grid(row=3, column=0, sticky="w", pady=(2, 6))

        ttk.Label(box, text="Ollama Model", style="Muted.TLabel", background=THEME.panel).grid(row=4, column=0, sticky="w")

        selector = OllamaModelSelectorMS(
            {
                "parent": box,
                "on_change": lambda m: self.var_model.set(m),
                "auto_refresh": True,
            },
            theme={"panel_bg": THEME.panel, "foreground": THEME.fg},
            bus=self.bus,
        )
        selector.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(4, 10))
        self._model_selector = selector

        # Actions
        btn_run = ttk.Button(box, text="Run", style="Accent.TButton", command=self._run_clicked)
        btn_run.grid(row=6, column=0, sticky="ew", pady=(0, 6))

        btn_cancel = ttk.Button(box, text="Cancel", command=self._cancel_clicked)
        btn_cancel.grid(row=7, column=0, sticky="ew", pady=(0, 6))

        btn_open_reports = ttk.Button(box, text="Open Report Folder", command=self._open_report_folder)
        btn_open_reports.grid(row=8, column=0, sticky="ew", pady=(0, 0))

        box.columnconfigure(0, weight=1)

        self._counts_lbl = ttk.Label(box, text="", style="Muted.TLabel", background=THEME.panel)
        self._counts_lbl.grid(row=9, column=0, sticky="w", pady=(10, 0))

    def _build_log(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Log", background=THEME.panel, foreground=THEME.fg).pack(anchor="w", pady=(10, 4))

        txt = tk.Text(
            parent,
            height=18,
            bg=THEME.entry_bg,
            fg=THEME.fg,
            insertbackground=THEME.fg,
            relief="flat",
            wrap="word",
        )
        txt.pack(fill="both", expand=False)
        txt.configure(state="disabled")
        self._log_text = txt

    def _build_results(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Results", background=THEME.panel, foreground=THEME.fg).pack(anchor="w", pady=(0, 6))

        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        # --- Summary tab (existing results list)
        tab_summary = ttk.Frame(nb, style="Panel.TFrame")
        nb.add(tab_summary, text="Summary")

        cols = ("kind", "value")
        tree = ttk.Treeview(tab_summary, columns=cols, show="headings", height=18)
        tree.heading("kind", text="Kind")
        tree.heading("value", text="Value")
        tree.column("kind", width=160, anchor="w")
        tree.column("value", width=520, anchor="w")
        tree.pack(fill="both", expand=True)

        self._tree = tree

        # --- Structure tab (hierarchy view)
        tab_struct = ttk.Frame(nb, style="Panel.TFrame")
        nb.add(tab_struct, text="Structure")

        st_cols = ("details",)
        stree = ttk.Treeview(tab_struct, columns=st_cols, show="tree headings", height=18)
        stree.heading("#0", text="Widget")
        stree.heading("details", text="Details")
        stree.column("#0", width=360, anchor="w")
        stree.column("details", width=360, anchor="w")
        stree.pack(fill="both", expand=True)

        self._structure_tree = stree

        btns = ttk.Frame(parent, style="Panel.TFrame")
        btns.pack(fill="x", pady=(10, 0))

        ttk.Button(btns, text="View Decision Plan", command=self._view_decision_plan).pack(side="left")
        ttk.Button(btns, text="Copy UiMap JSON", command=self._copy_uimap_json).pack(side="left", padx=(8, 0))

    def _build_footer(self, parent: ttk.Frame) -> None:
        ftr = ttk.Frame(parent, style="TFrame")
        ftr.pack(fill="x", padx=10, pady=(6, 10))

        ttk.Label(
            ftr,
            text="Tip: inference results are staged as a decision plan. Auto-apply uses high confidence only; approvals are manual.",
            style="Muted.TLabel",
        ).pack(anchor="w")

    # -------------------------
    # Event handling / updates
    # -------------------------

    def _on_progress_event(self, event: Dict[str, Any]) -> None:
        # This may be called from a worker thread.
        with self._event_lock:
            if len(self._event_queue) >= self._event_queue_limit:
                self._event_queue.pop(0)
            self._event_queue.append(event)

    def _tick(self) -> None:
        """
        Periodic UI refresh:
        - consume progress events
        - poll backend state
        """
        if self.root is None:
            return

        self._drain_events()
        self._refresh_state_view()

        # keep ticking
        self.root.after(150, self._tick)

    def _drain_events(self) -> None:
        with self._event_lock:
            if not self._event_queue:
                return

            events = self._event_queue[:]
            self._event_queue.clear()

        for ev in events:
            self._append_log(self._format_event(ev))

    def _refresh_state_view(self) -> None:
        st = self.backend.get_state_dict()
        status = st.get("status", "<?>")
        err = st.get("last_error", None)

        if self._status_lbl is not None:
            txt = status if not err else f"{status}  (error: {err})"
            self._status_lbl.configure(text=txt)

        # counts
        c = (st.get("counters") or {})
        counts_line = (
            f"dirs={c.get('dirs_seen',0)}  files={c.get('files_seen',0)}  py={c.get('py_files',0)}  "
            f"ast_ok={c.get('ast_ok',0)}  ast_err={c.get('ast_err',0)}  "
            f"windows={c.get('windows',0)}  widgets={c.get('widgets',0)}  unknowns={c.get('unknowns',0)}"
        )
        if self._counts_lbl is not None:
            self._counts_lbl.configure(text=counts_line)

        # result tree summary
        if self._tree is not None:
            self._tree.delete(*self._tree.get_children())
            self._tree.insert("", "end", values=("session_id", st.get("session_id", "")))
            self._tree.insert("", "end", values=("project_root", st.get("project_root", "")))
            self._tree.insert("", "end", values=("status", status))
            if st.get("report_md_path"):
                self._tree.insert("", "end", values=("report_md", st.get("report_md_path")))
            if st.get("report_json_path"):
                self._tree.insert("", "end", values=("report_json", st.get("report_json_path")))
            if st.get("report_jsonl_path"):
                self._tree.insert("", "end", values=("report_jsonl", st.get("report_jsonl_path")))

            # entrypoint candidates (top 5)
            eps = st.get("entrypoint_candidates") or []
            for i, ep in enumerate(eps[:5], start=1):
                self._tree.insert("", "end", values=(f"entrypoint_{i}", ep.get("path", "")))

        # structure tree (ui_map widget hierarchy)
        if self._structure_tree is not None:
            self._refresh_structure_tree(st)

    # -------------------------
    # Structure tree
    # -------------------------

    def _refresh_structure_tree(self, st: Dict[str, Any]) -> None:
        """Render ui_map widget hierarchy into the Structure tab."""
        if self._structure_tree is None:
            return

        uimap = st.get("ui_map") or {}
        widgets: Dict[str, Any] = (uimap.get("widgets") or {})

        self._structure_tree.delete(*self._structure_tree.get_children())

        if not widgets:
            self._structure_tree.insert("", "end", text="(no ui_map/widgets yet)", values=("Run the mapper to populate.",))
            return

        # Build parent->children index
        children_by_parent: Dict[Optional[str], List[str]] = {}
        for wid, w in widgets.items():
            pid = w.get("parent_id", None)
            children_by_parent.setdefault(pid, []).append(wid)

        def _created_sort_key(wid: str):
            w = widgets.get(wid) or {}
            ca = w.get("created_at") or {}
            try:
                ln = int(ca.get("lineno", 10**9))
            except Exception:
                ln = 10**9
            path = str(ca.get("path", ""))
            return (path, ln, wid)

        for pid in list(children_by_parent.keys()):
            children_by_parent[pid].sort(key=_created_sort_key)

        def _label_for(wid: str) -> (str, str):
            w = widgets.get(wid) or {}
            wtype = w.get("widget_type", "Widget")
            ca = w.get("created_at") or {}
            path = str(ca.get("path", ""))
            lineno = ca.get("lineno", "")

            layout = w.get("layout_calls") or []
            has_layout = bool(layout)
            cmds = w.get("command_targets") or []
            has_cmd = bool(cmds)

            tag_bits: List[str] = []
            if has_layout:
                tag_bits.append("layout")
            if has_cmd:
                tag_bits.append("cmd")
            tags = ("[" + ", ".join(tag_bits) + "]") if tag_bits else ""

            text = f"{wid}  {wtype} {tags}".rstrip()
            details = f"@ {path}:{lineno}".rstrip(":")
            return text, details

        roots = children_by_parent.get(None, [])
        if not roots:
            # Some generators use "" instead of None.
            roots = children_by_parent.get("", [])

        root_node = self._structure_tree.insert("", "end", text="ROOTS", values=("parent_id is null/empty",))

        visited: set[str] = set()

        def _insert_subtree(parent_item: str, wid: str, depth: int) -> None:
            if depth > 200:
                self._structure_tree.insert(parent_item, "end", text=f"{wid} ...", values=("depth limit",))
                return
            if wid in visited:
                self._structure_tree.insert(parent_item, "end", text=f"{wid} ...", values=("cycle detected",))
                return
            visited.add(wid)

            text, details = _label_for(wid)
            item = self._structure_tree.insert(parent_item, "end", text=text, values=(details,))
            for child_id in children_by_parent.get(wid, []):
                _insert_subtree(item, child_id, depth + 1)

        for wid in roots:
            _insert_subtree(root_node, wid, 0)

        # Expand roots by default
        try:
            self._structure_tree.item(root_node, open=True)
        except Exception:
            pass

    # -------------------------
    # UI actions
    # -------------------------

    def _browse_folder(self) -> None:
        if self.root is None:
            return
        p = filedialog.askdirectory(title="Select project root")
        if p:
            self.var_project_root.set(p)

    def _run_clicked(self) -> None:
        p = self.var_project_root.get().strip()
        if not p:
            messagebox.showwarning("Missing", "Select a project root.")
            return

        settings = BackendSettings(
            include_pyw=bool(self.var_include_pyw.get()),
            enable_inference=bool(self.var_enable_inference.get()),
            ollama_model=self.var_model.get().strip(),
        )
        self.backend.start_run(Path(p), settings=settings)

    def _cancel_clicked(self) -> None:
        self.backend.cancel_run("user")

    def _open_report_folder(self) -> None:
        st = self.backend.get_state_dict()
        md = st.get("report_md_path") or st.get("report_json_path") or st.get("report_jsonl_path")
        if not md:
            messagebox.showinfo("No reports yet", "Run the mapper to generate reports.")
            return

        folder = str(Path(md).resolve().parent)
        try:
            import os, subprocess, sys
            if sys.platform.startswith("win"):
                os.startfile(folder)  # type: ignore
            elif sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception:
            messagebox.showinfo("Folder", folder)

    def _view_decision_plan(self) -> None:
        plan = self.backend.take_latest_decision_plan()
        if not plan:
            messagebox.showinfo("Decision Plan", "No decision plan available (either inference disabled or no items).")
            return

        # Simple viewer dialog
        top = tk.Toplevel(self.root)
        top.title("Decision Plan")
        top.configure(bg=THEME.bg)

        txt = tk.Text(top, bg=THEME.entry_bg, fg=THEME.fg, insertbackground=THEME.fg, relief="flat", wrap="none")
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        txt.insert("1.0", json.dumps(plan, indent=2))
        txt.configure(state="disabled")

        ttk.Button(top, text="Close", command=top.destroy).pack(pady=(0, 10))

        top.geometry("900x600")

    def _copy_uimap_json(self) -> None:
        st = self.backend.get_state_dict()
        uimap = st.get("ui_map")
        if not uimap:
            messagebox.showinfo("UiMap", "No UiMap available yet.")
            return

        s = json.dumps(uimap, indent=2)
        self.root.clipboard_clear()
        self.root.clipboard_append(s)
        messagebox.showinfo("Copied", "UiMap JSON copied to clipboard.")

    # -------------------------
    # Log helpers
    # -------------------------

    def _append_log(self, line: str) -> None:
        if self._log_text is None:
            return
        self._log_text.configure(state="normal")
        self._log_text.insert("end", line + "\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _format_event(self, ev: Dict[str, Any]) -> str:
        t = ev.get("type", "event")
        lvl = ev.get("level", "info")
        msg = ev.get("message", "")
        return f"[{lvl.upper():5}] {t}: {msg}"


# -------------------------
# Convenience builder for app.py
# -------------------------

def build_ui(root: tk.Tk, backend: BackendOrchestrator) -> UiOrchestrator:
    ui = UiOrchestrator(backend=backend)
    ui.build(root)
    return ui





"""
ASTExplorerPanel – Outline view for the left Explorer sidebar.

Displays the AST hierarchy of the open file (classes, functions, methods)
as an indented flat list.  Click any node to scroll the Current editor to
that node's span and highlight it.

Data comes from the backend action:
    {"system": "curate", "action": "get_hierarchy_flat", "file": path}

Each node is: {name, kind, start_line, end_line, depth}
"""
import threading
import tkinter as tk
from theme import THEME


class ASTExplorerPanel(tk.Frame):
    """
    Outline / AST explorer for the left sidebar.
    Requires set_context(backend, file_path) and set_text_widget(tw) to be
    called before the panel is useful.
    """

    # Tag applied to the entire span of a selected node in the editor
    _SPAN_TAG = "ast_span_highlight"

    def __init__(self, parent, text_widget=None, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        self.text_widget = text_widget
        self.backend = None
        self.file_path = None
        self._nodes = []   # list of raw hierarchy dicts

        self._build_ui()

    # ── UI construction ─────────────────────────────────────

    def _build_ui(self):
        # Header row: status label + refresh button
        header = tk.Frame(self, bg=THEME["bg"])
        header.pack(fill="x", padx=6, pady=(6, 2))

        self.status_label = tk.Label(
            header,
            text="No file loaded",
            bg=THEME["bg"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
        )
        self.status_label.pack(side="left", fill="x", expand=True)

        tk.Button(
            header,
            text="↺ Refresh",
            command=self._refresh,
            bg=THEME["bg2"],
            fg=THEME["accent"],
            activebackground=THEME["accent"],
            activeforeground="#ffffff",
            font=THEME["font_interface_small"],
            relief="flat",
            padx=8,
            pady=2,
            cursor="hand2",
        ).pack(side="right")

        # Node listbox + scrollbar
        list_frame = tk.Frame(self, bg=THEME["bg"])
        list_frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        scrollbar = tk.Scrollbar(list_frame, bg=THEME["bg2"])
        scrollbar.pack(side="right", fill="y")

        self.node_list = tk.Listbox(
            list_frame,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code_small"],
            relief="flat",
            selectbackground=THEME["accent"],
            selectforeground="#ffffff",
            activestyle="none",
            yscrollcommand=scrollbar.set,
        )
        self.node_list.pack(fill="both", expand=True)
        scrollbar.config(command=self.node_list.yview)

        self.node_list.bind("<Button-1>", self._on_node_click)

    # ── public API ──────────────────────────────────────────

    def set_context(self, backend, file_path: str):
        """Called by WorkspaceTab when a file is loaded.  Triggers auto-refresh."""
        self.backend = backend
        self.file_path = file_path
        self._refresh()

    def set_text_widget(self, text_widget):
        """Update the editor text widget used for navigation."""
        self.text_widget = text_widget

    def load_hierarchy(self, nodes: list):
        """
        Populate the list from a hierarchy already in memory
        (e.g. delivered by a workflow result).
        """
        self._nodes = nodes
        self.node_list.delete(0, "end")

        for node in nodes:
            depth  = node.get("depth", 0)
            kind   = node.get("kind", "?")
            name   = node.get("name", "?")
            start  = node.get("start_line", "?")
            end    = node.get("end_line", "?")
            indent = "  " * depth
            self.node_list.insert("end", f"{indent}{kind}  {name}    L{start}–{end}")

        n = len(nodes)
        self.status_label.config(
            text=f"{n} node{'s' if n != 1 else ''}"
        )

    # ── internal ────────────────────────────────────────────

    def _refresh(self):
        """Fetch hierarchy from the backend in a daemon thread."""
        if not self.backend or not self.file_path:
            return
        self.status_label.config(text="Loading…")

        def _run():
            result = self.backend.execute_task({
                "system": "curate",
                "action": "get_hierarchy_flat",
                "file": self.file_path,
            })
            if result.get("status") == "ok":
                nodes = result.get("hierarchy", [])
                self.after(0, lambda n=nodes: self.load_hierarchy(n))
            else:
                msg = result.get("message", "Failed")
                self.after(0, lambda m=msg: self.status_label.config(text=m))

        threading.Thread(target=_run, daemon=True).start()

    def _on_node_click(self, event):
        """Scroll to and highlight the clicked node's span in the editor."""
        idx = self.node_list.nearest(event.y)
        if idx < 0 or idx >= len(self._nodes):
            return
        node = self._nodes[idx]
        start = node.get("start_line")
        end   = node.get("end_line")
        if start is not None and self.text_widget:
            self._highlight_span(start, end or start)

    def _highlight_span(self, start_line: int, end_line: int):
        """Apply a muted background over the node's entire line range."""
        tw = self.text_widget
        # Dark amber — distinct from find highlights (dark blue) and diff colours
        tw.tag_configure(self._SPAN_TAG, background="#28231a")
        tw.tag_remove(self._SPAN_TAG, "1.0", "end")
        tw.tag_add(self._SPAN_TAG, f"{start_line}.0", f"{end_line}.end")
        tw.see(f"{start_line}.0")
        tw.mark_set("insert", f"{start_line}.0")
        tw.focus_set()

"""
Search Lens – Content search interface for the SQLite context store.
Provides a search entry, results list, and event bindings for
querying indexed chunks by content or entity name.
Stateless UI: all queries go through BackendEngine.
"""
import tkinter as tk
from tkinter import ttk
from theme import THEME
from ui.modules._buttons import AccentButton


class SearchLens(tk.Frame):
    """
    Search panel for querying the indexed codebase.
    Supports content search (LIKE-based) and name-based search.
    Results require files to be indexed first via curation.
    """

    def __init__(self, parent, on_result_select=None, backend=None, **kwargs):
        super().__init__(parent, bg=THEME["bg2"], **kwargs)
        self._on_result_select = on_result_select
        self.backend = backend
        self._results = []

        # ── header ──────────────────────────────────────────
        tk.Label(
            self,
            text="SEARCH",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
        ).pack(fill="x", padx=6, pady=(6, 2))

        # ── search bar ─────────────────────────────────────
        bar = tk.Frame(self, bg=THEME["bg2"])
        bar.pack(fill="x", padx=6, pady=(0, 4))

        self.search_entry = tk.Entry(
            bar,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            insertbackground=THEME["accent"],
            font=THEME["font_interface"],
            relief="flat",
        )
        self.search_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.search_entry.bind("<Return>", lambda e: self._do_search())

        AccentButton(bar, text="Search", command=self._do_search).pack(side="right")

        # ── search type ────────────────────────────────────
        type_frame = tk.Frame(self, bg=THEME["bg2"])
        type_frame.pack(fill="x", padx=6)

        self.search_type = tk.StringVar(value="content")
        tk.Radiobutton(
            type_frame,
            text="Content",
            variable=self.search_type,
            value="content",
            bg=THEME["bg2"],
            fg=THEME["fg"],
            selectcolor=THEME["accent"],
            font=THEME["font_interface_small"],
            activebackground=THEME["bg2"],
        ).pack(side="left")

        tk.Radiobutton(
            type_frame,
            text="Name",
            variable=self.search_type,
            value="name",
            bg=THEME["bg2"],
            fg=THEME["fg"],
            selectcolor=THEME["accent"],
            font=THEME["font_interface_small"],
            activebackground=THEME["bg2"],
        ).pack(side="left")

        # ── results list ───────────────────────────────────
        self._status = tk.Label(
            self,
            text="Enter a query above",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
        )
        self._status.pack(fill="x", padx=6, pady=(4, 0))

        results_frame = tk.Frame(self, bg=THEME["bg2"])
        results_frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        self.results_list = tk.Listbox(
            results_frame,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code_small"],
            selectbackground=THEME["accent"],
            selectforeground="#ffffff",
            relief="flat",
            activestyle="none",
        )
        scrollbar = tk.Scrollbar(results_frame, command=self.results_list.yview)
        self.results_list.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.results_list.pack(side="left", fill="both", expand=True)

        self.results_list.bind("<<ListboxSelect>>", self._on_result_click)

    # ── public API ──────────────────────────────────────────

    def set_results(self, results):
        """Manually set search results (list of chunk dicts)."""
        self._results = results
        self.results_list.delete(0, "end")
        for r in results:
            file_name = r.get("file_name", r.get("path", "?"))
            name = r.get("name", "")
            line = r.get("start_line", "")
            display = f"{file_name}:{line}  {name}" if name else f"{file_name}:{line}"
            self.results_list.insert("end", display)
        self._status.config(text=f"{len(results)} result(s)")

    # ── internal ────────────────────────────────────────────

    def _do_search(self):
        query = self.search_entry.get().strip()
        if not query:
            return

        if not self.backend:
            self._status.config(text="No backend available")
            return

        self._status.config(text="Searching...")

        search_type = self.search_type.get()

        # Both modes search the SlidingWindow chunk store directly
        sw = self.backend.sliding_window
        if search_type == "content":
            results = sw.search_chunks(query)
        else:
            results = sw.search_chunks(query)

        if not results:
            self._status.config(
                text="No results. Use Tools > Run Default Workflow "
                     "to index open files first."
            )
            self.results_list.delete(0, "end")
            self._results = []
        else:
            self.set_results(results)

    def _on_result_click(self, _event):
        sel = self.results_list.curselection()
        if not sel or not self._results:
            return

        idx = sel[0]
        if idx < len(self._results):
            result = self._results[idx]
            if self._on_result_select:
                self._on_result_select(result)

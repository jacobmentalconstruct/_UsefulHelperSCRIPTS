"""
ExplorerPanel – Tabbed sidebar container for workspace explorers.
Currently contains FindReplacePanel as the first tab.
Designed for future expansion: File Tree, Breakpoints, etc.
"""
import tkinter as tk
from tkinter import ttk
from theme import THEME
from backend.modules.search_engine import SearchEngine
from ui.modules.ast_explorer import ASTExplorerPanel
from ui.modules.chunks_explorer import ChunksExplorerPanel


class FindReplacePanel(tk.Frame):
    """
    Find/Replace panel with whitespace-agnostic search.
    Displays results as clickable list; click to jump+highlight in editor.
    """

    def __init__(self, parent, text_widget=None, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        self.text_widget = text_widget
        self.search_engine = SearchEngine()
        self._current_matches = []

        self._build_ui()

    def _build_ui(self):
        """Build the Find/Replace interface."""

        # --- Find Row ---
        find_frame = tk.Frame(self, bg=THEME["bg"])
        find_frame.pack(fill="x", padx=6, pady=(6, 3))

        tk.Label(find_frame, text="Find:", bg=THEME["bg"], fg=THEME["fg"], font=THEME["font_interface_small"]).pack(side="left", padx=(0, 4))
        self.find_entry = tk.Entry(find_frame, bg=THEME["bg3"], fg=THEME["fg"], font=THEME["font_code"], relief="flat")
        self.find_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        self.find_entry.bind("<KeyRelease>", lambda e: self._on_find_changed())

        tk.Button(
            find_frame,
            text="🎨",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=("Segoe UI Symbol", 10),
            relief="flat",
            padx=2,
            pady=0,
            command=self._show_whitespace_palette
        ).pack(side="left", padx=(0, 4))

        # --- Replace Row ---
        replace_frame = tk.Frame(self, bg=THEME["bg"])
        replace_frame.pack(fill="x", padx=6, pady=3)

        tk.Label(replace_frame, text="Replace:", bg=THEME["bg"], fg=THEME["fg"], font=THEME["font_interface_small"]).pack(side="left", padx=(0, 4))
        self.replace_entry = tk.Entry(replace_frame, bg=THEME["bg3"], fg=THEME["fg"], font=THEME["font_code"], relief="flat")
        self.replace_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))

        tk.Button(
            replace_frame,
            text="🎨",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=("Segoe UI Symbol", 10),
            relief="flat",
            padx=2,
            pady=0,
            command=self._show_whitespace_palette
        ).pack(side="left")

        # --- Options Row ---
        options_frame = tk.Frame(self, bg=THEME["bg"])
        options_frame.pack(fill="x", padx=6, pady=3)

        self.match_case_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            options_frame,
            text="Match Case",
            bg=THEME["bg"],
            fg=THEME["fg"],
            selectcolor=THEME["bg2"],
            variable=self.match_case_var,
            command=self._on_find_changed,
            font=THEME["font_interface_small"]
        ).pack(side="left", padx=(0, 12))

        self.match_ws_exact_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            options_frame,
            text="Match Whitespace Exactly",
            bg=THEME["bg"],
            fg=THEME["fg"],
            selectcolor=THEME["bg2"],
            variable=self.match_ws_exact_var,
            command=self._on_find_changed,
            font=THEME["font_interface_small"]
        ).pack(side="left")

        # --- Action Buttons Row ---
        button_frame = tk.Frame(self, bg=THEME["bg"])
        button_frame.pack(fill="x", padx=6, pady=(3, 6))

        tk.Button(
            button_frame,
            text="Find All",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            activebackground=THEME["accent"],
            activeforeground="#ffffff",
            relief="flat",
            padx=8,
            font=THEME["font_interface_small"],
            command=self._find_all
        ).pack(side="left", padx=(0, 4))

        tk.Button(
            button_frame,
            text="Replace",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            activebackground=THEME["accent"],
            activeforeground="#ffffff",
            relief="flat",
            padx=8,
            font=THEME["font_interface_small"],
            command=self._replace_current
        ).pack(side="left", padx=(0, 4))

        tk.Button(
            button_frame,
            text="Replace All",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            activebackground=THEME["accent"],
            activeforeground="#ffffff",
            relief="flat",
            padx=8,
            font=THEME["font_interface_small"],
            command=self._replace_all
        ).pack(side="left")

        # --- Status Label ---
        self.status_label = tk.Label(
            self,
            text="",
            bg=THEME["bg"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
            padx=6
        )
        self.status_label.pack(fill="x")

        # --- Results Listbox ---
        self.results_list = tk.Listbox(
            self,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code"],
            relief="flat",
            height=8
        )
        self.results_list.pack(fill="both", expand=True, padx=6, pady=(3, 6))
        self.results_list.bind("<Button-1>", self._on_result_click)

    def _on_find_changed(self):
        """Update results when search pattern changes."""
        if self.text_widget:
            self._find_all()

    def _find_all(self):
        """Find all matches and populate results list."""
        if not self.text_widget:
            self.status_label.config(text="No editor connected")
            return

        pattern = self.find_entry.get()
        if not pattern:
            self.results_list.delete(0, "end")
            self.status_label.config(text="")
            return

        source = self.text_widget.get("1.0", "end-1c")
        matches = self.search_engine.find_all(
            source,
            pattern,
            match_case=self.match_case_var.get(),
            match_ws_exactly=self.match_ws_exact_var.get()
        )

        # Two persistent tags:
        #   match_all    — muted background on every hit
        #   match_active — high-contrast background on the selected hit
        # Raise match_active so it always paints on top of match_all.
        self.text_widget.tag_configure("match_all",    background="#1e3050")
        self.text_widget.tag_configure("match_active", background=THEME["accent"], foreground="#ffffff")
        self.text_widget.tag_raise("match_active", "match_all")

        # Clear previous highlights
        self.text_widget.tag_remove("match_all",    "1.0", "end")
        self.text_widget.tag_remove("match_active", "1.0", "end")

        # Rebuild results list
        self.results_list.delete(0, "end")
        self._current_matches = []

        for line_num, col_num, line_text, matched_text in matches:
            context = line_text.strip()[:50] + ("..." if len(line_text.strip()) > 50 else "")
            self.results_list.insert("end", f"Line {line_num}, Col {col_num}: {context}")
            self._current_matches.append((line_num, col_num, matched_text))

            # Muted highlight for every match
            self.text_widget.tag_add(
                "match_all",
                f"{line_num}.{col_num}",
                f"{line_num}.{col_num + len(matched_text)}",
            )

        match_count = len(matches)
        self.status_label.config(text=f"{match_count} match{'es' if match_count != 1 else ''} found")

    def _on_result_click(self, event):
        """Jump to clicked result in editor."""
        if not self.text_widget:
            return

        # Use nearest() to derive the index from the click y-coordinate
        # immediately.  curselection() is NOT used here because <Button-1>
        # fires before the Listbox updates its selection — it would return the
        # previously-selected row, navigating to the wrong location.
        idx = self.results_list.nearest(event.y)
        if idx < 0 or idx >= len(self._current_matches):
            return

        line_num, col_num, matched_text = self._current_matches[idx]

        # Move the high-contrast "active" highlight to this match only;
        # all other matches keep the muted "match_all" highlight.
        self.text_widget.tag_remove("match_active", "1.0", "end")
        self.text_widget.tag_add(
            "match_active",
            f"{line_num}.{col_num}",
            f"{line_num}.{col_num + len(matched_text)}",
        )

        # Scroll to the exact position and move the cursor
        self.text_widget.see(f"{line_num}.{col_num}")
        self.text_widget.mark_set("insert", f"{line_num}.{col_num}")
        self.text_widget.focus_set()

    def _replace_current(self):
        """Replace current selection."""
        if not self.text_widget:
            return

        try:
            start = self.text_widget.index("sel.first")
            end = self.text_widget.index("sel.last")
            self.text_widget.delete(start, end)
            self.text_widget.insert(start, self.replace_entry.get())
            self._on_find_changed()
        except tk.TclError:
            self.status_label.config(text="No selection to replace")

    def _replace_all(self):
        """Replace all matches."""
        if not self.text_widget:
            return

        pattern = self.find_entry.get()
        replacement = self.replace_entry.get()

        if not pattern:
            self.status_label.config(text="No pattern to replace")
            return

        source = self.text_widget.get("1.0", "end-1c")
        new_source, count = self.search_engine.replace_all(
            source,
            pattern,
            replacement,
            match_case=self.match_case_var.get(),
            match_ws_exactly=self.match_ws_exact_var.get()
        )

        if count > 0:
            self.text_widget.delete("1.0", "end")
            self.text_widget.insert("1.0", new_source)
            self.status_label.config(text=f"Replaced {count} occurrence{'s' if count != 1 else ''}")
            self._on_find_changed()
        else:
            self.status_label.config(text="No matches to replace")

    def _show_whitespace_palette(self):
        """Show whitespace symbol palette popup."""
        popup = tk.Toplevel(self)
        popup.title("Whitespace Symbols")
        popup.geometry("250x120")
        popup.configure(bg=THEME["bg"])

        frame = tk.Frame(popup, bg=THEME["bg"])
        frame.pack(fill="both", expand=True, padx=6, pady=6)

        symbols = [
            ("[space]", " "),
            ("[tab]", "\t"),
            ("[newline]", "\n"),
            ("[2-spaces]", "  "),
            ("[4-spaces]", "    "),
        ]

        for label, symbol in symbols:
            tk.Button(
                frame,
                text=label,
                bg=THEME["bg2"],
                fg=THEME["accent"],
                relief="flat",
                padx=6,
                pady=2,
                command=lambda s=symbol: self._insert_symbol(s, popup),
                font=THEME["font_interface_small"]
            ).pack(side="left", padx=2)

    def _insert_symbol(self, symbol, popup):
        """Insert symbol into focused entry field."""
        try:
            focused = self.find_entry.winfo_toplevel().focus_get()
            if focused == self.find_entry:
                self.find_entry.insert("insert", symbol)
            elif focused == self.replace_entry:
                self.replace_entry.insert("insert", symbol)
            popup.destroy()
            self._on_find_changed()
        except Exception:
            popup.destroy()

    def set_text_widget(self, text_widget):
        """Set the text widget to search within."""
        self.text_widget = text_widget


class ExplorerPanel(tk.Frame):
    """
    Tabbed explorer sidebar container.
    Tabs:
      0 – Find/Replace
      1 – Outline  (AST hierarchy)
      2 – Chunks   (AI context units)
    Designed for future expansion via add_explorer_tab().
    """

    def __init__(self, parent, text_widget=None, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        self.text_widget = text_widget
        self.explorer_tabs = {}

        # Tabbed interface
        self.notebook = ttk.Notebook(self, style="Inner.TNotebook")
        self.notebook.pack(fill="both", expand=True)

        # Tab 0: Find/Replace
        self.find_replace_panel = FindReplacePanel(self.notebook, text_widget=text_widget)
        self.notebook.add(self.find_replace_panel, text="  Find/Replace  ")
        self.explorer_tabs["find_replace"] = self.find_replace_panel

        # Tab 1: Outline (AST hierarchy)
        self.ast_panel = ASTExplorerPanel(self.notebook, text_widget=text_widget)
        self.notebook.add(self.ast_panel, text="  Outline  ")
        self.explorer_tabs["outline"] = self.ast_panel

        # Tab 2: Chunks (AI context units)
        self.chunks_panel = ChunksExplorerPanel(self.notebook, text_widget=text_widget)
        self.notebook.add(self.chunks_panel, text="  Chunks  ")
        self.explorer_tabs["chunks"] = self.chunks_panel

    def add_explorer_tab(self, name, panel_widget):
        """Add an additional explorer tab (extensibility hook)."""
        self.notebook.add(panel_widget, text=f"  {name}  ")
        self.explorer_tabs[name.lower()] = panel_widget

    def set_text_widget(self, text_widget):
        """Forward the active editor text widget to all explorer panels."""
        self.text_widget = text_widget
        self.find_replace_panel.set_text_widget(text_widget)
        self.ast_panel.set_text_widget(text_widget)
        self.chunks_panel.set_text_widget(text_widget)

    def set_context(self, backend, file_path: str, get_content=None):
        """
        Called by WorkspaceTab on every file load.
        Forwards context to Outline and Chunks panels so they can (auto-)refresh.
        get_content: callable() → current editor text, passed to ChunksExplorerPanel.
        """
        self.ast_panel.set_context(backend, file_path)
        self.chunks_panel.set_context(backend, file_path, get_content=get_content)

    def load_hierarchy(self, nodes: list):
        """Push AST hierarchy data (from a workflow result) to the Outline panel."""
        self.ast_panel.load_hierarchy(nodes)

    def load_chunks(self, chunks: list):
        """Push chunk data (from a workflow result) to the Chunks panel."""
        self.chunks_panel.load_chunks(chunks)

    def focus_find_replace(self):
        """Focus the Find/Replace tab."""
        self.notebook.select(0)
        self.find_replace_panel.find_entry.focus_set()

    def focus_outline(self):
        """Focus the Outline tab."""
        self.notebook.select(1)

    def focus_chunks(self):
        """Focus the Chunks tab."""
        self.notebook.select(2)

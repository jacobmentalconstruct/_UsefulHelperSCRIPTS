"""
Browser Lens – File browser Treeview for directory navigation.
Handles directory navigation and initial file selection for curation.
Stateless UI: all data operations go through BackendEngine.
"""
import tkinter as tk
from tkinter import ttk
import os
from theme import THEME


class BrowserLens(tk.Frame):
    """
    Treeview-based file browser panel.
    Displays a directory tree and allows the user to select files
    for opening in workspace tabs.
    """

    def __init__(self, parent, on_file_select=None, **kwargs):
        super().__init__(parent, bg=THEME["bg2"], **kwargs)
        self._on_file_select = on_file_select
        self._root_path = None

        # ── header ──────────────────────────────────────────
        header = tk.Frame(self, bg=THEME["bg2"])
        header.pack(fill="x", padx=4, pady=(6, 2))

        tk.Label(
            header,
            text="BROWSE",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
        ).pack(side="left")

        self._path_label = tk.Label(
            header,
            text="",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="e",
        )
        self._path_label.pack(side="right", fill="x", expand=True)

        # ── treeview ────────────────────────────────────────
        tree_frame = tk.Frame(self, bg=THEME["bg2"])
        tree_frame.pack(fill="both", expand=True, padx=4, pady=(0, 4))

        self.tree = ttk.Treeview(
            tree_frame,
            selectmode="browse",
            show="tree headings",
            columns=("type", "lines"),
        )
        self.tree.heading("#0", text="Name", anchor="w")
        self.tree.heading("type", text="Type", anchor="w")
        self.tree.heading("lines", text="Lines", anchor="e")
        self.tree.column("#0", width=200, stretch=True)
        self.tree.column("type", width=60, stretch=False)
        self.tree.column("lines", width=50, stretch=False)

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", self._on_double_click)

    # ── public API ──────────────────────────────────────────

    def load_directory(self, directory_path):
        """Populate the tree with a directory's contents."""
        self._root_path = directory_path
        self._path_label.config(text=os.path.basename(directory_path))

        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        self._populate_tree("", directory_path)

    def load_file_list(self, files):
        """
        Populate the tree from a list of file dicts.
        Each dict should have: {path, name, language, line_count}
        """
        for item in self.tree.get_children():
            self.tree.delete(item)

        for f in files:
            self.tree.insert(
                "",
                "end",
                text=f.get("name", ""),
                values=(
                    f.get("language", ""),
                    f.get("line_count", ""),
                ),
                tags=("file",),
            )
            # Store full path in the item
            item_id = self.tree.get_children()[-1]
            self.tree.set(item_id, "path", f.get("path", ""))

    def get_selected_path(self):
        """Return the full path of the selected item."""
        sel = self.tree.selection()
        if not sel:
            return None
        item = sel[0]
        # Check if we stored a path tag
        tags = self.tree.item(item, "tags")
        if "file" in tags and self._root_path:
            text = self.tree.item(item, "text")
            return os.path.join(self._root_path, text)
        return None

    # ── internal ────────────────────────────────────────────

    def _populate_tree(self, parent_id, path):
        """Recursively populate the tree from a filesystem path."""
        try:
            entries = sorted(os.listdir(path))
        except PermissionError:
            return

        for entry in entries:
            if entry.startswith(".") or entry.startswith("_"):
                continue

            full = os.path.join(path, entry)
            if os.path.isdir(full):
                node = self.tree.insert(
                    parent_id, "end", text=entry,
                    values=("dir", ""), tags=("dir",),
                )
                self._populate_tree(node, full)
            else:
                ext = os.path.splitext(entry)[1]
                try:
                    lines = sum(1 for _ in open(full, "rb"))
                except (OSError, PermissionError):
                    lines = ""
                self.tree.insert(
                    parent_id, "end", text=entry,
                    values=(ext, lines), tags=("file",),
                )

    def _on_select(self, _event):
        """Single-click selection."""
        pass  # Preview could go here

    def _on_double_click(self, _event):
        """Double-click opens the file."""
        sel = self.tree.selection()
        if not sel:
            return

        item = sel[0]
        tags = self.tree.item(item, "tags")

        if "file" in tags and self._on_file_select:
            text = self.tree.item(item, "text")
            if self._root_path:
                # Build full path by walking up the tree
                path_parts = [text]
                parent = self.tree.parent(item)
                while parent:
                    path_parts.insert(0, self.tree.item(parent, "text"))
                    parent = self.tree.parent(parent)
                full_path = os.path.join(self._root_path, *path_parts)
                self._on_file_select(full_path)

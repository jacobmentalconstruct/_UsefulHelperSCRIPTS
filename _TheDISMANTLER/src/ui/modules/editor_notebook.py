"""
EditorNotebook – 3-tab notebook replacing the single TextEditor
in WorkspaceTab.
Tab 1: Original  (read-only baseline as loaded from disk)
Tab 2: Current   (editable scratchpad)
Tab 3: Diff      (read-only colored diff preview)
Stateless UI: all data comes through WorkspaceTab / BackendEngine.
AST Outline and Chunks browsing live in the left ExplorerPanel.
"""
import tkinter as tk
from tkinter import ttk
from theme import THEME
from ui.modules.text_editor import TextEditor


# ── DiffView ───────────────────────────────────────────────


class DiffView(tk.Frame):
    """
    Read-only inline diff viewer with color-tagged lines.
    Green = additions, Red = removals, Cyan = hunk headers.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)

        self.text = tk.Text(
            self,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code"],
            state="disabled",
            relief="flat",
            wrap="none",
            padx=6,
            pady=4,
        )
        self.text.pack(fill="both", expand=True)

        self._status = tk.Label(
            self,
            text="No diff loaded",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
            padx=6,
        )
        self._status.pack(fill="x", side="bottom")

        # Tag config
        self.text.tag_config("add_line", foreground=THEME["success"], background="#1a2e1a")
        self.text.tag_config("del_line", foreground=THEME["error"], background="#2e1a1a")
        self.text.tag_config("hunk", foreground=THEME["accent"])
        self.text.tag_config("context", foreground=THEME["fg_dim"])

    def load_diff(self, diff_text):
        """Load a unified diff string with color tags."""
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        adds = dels = 0
        for line in diff_text.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                self.text.insert("end", line + "\n", "hunk")
            elif line.startswith("@@"):
                self.text.insert("end", line + "\n", "hunk")
            elif line.startswith("+"):
                self.text.insert("end", line + "\n", "add_line")
                adds += 1
            elif line.startswith("-"):
                self.text.insert("end", line + "\n", "del_line")
                dels += 1
            else:
                self.text.insert("end", line + "\n", "context")
        self.text.config(state="disabled")
        self._status.config(text=f"+{adds} / -{dels} lines")

    def load_side_by_side(self, original, patched):
        """Inline comparison of original vs patched content."""
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        orig_lines = original.splitlines()
        patch_lines = patched.splitlines()
        max_len = max(len(orig_lines), len(patch_lines))
        adds = dels = 0
        for i in range(max_len):
            o = orig_lines[i] if i < len(orig_lines) else ""
            p = patch_lines[i] if i < len(patch_lines) else ""
            if o != p:
                if o:
                    self.text.insert("end", f"- {o}\n", "del_line")
                    dels += 1
                if p:
                    self.text.insert("end", f"+ {p}\n", "add_line")
                    adds += 1
            else:
                self.text.insert("end", f"  {o}\n", "context")
        self.text.config(state="disabled")
        self._status.config(text=f"+{adds} / -{dels} lines")

    def clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")
        self._status.config(text="No diff loaded")


# ── EditorNotebook ─────────────────────────────────────────


class EditorNotebook(tk.Frame):
    """
    3-tab notebook container that replaces the single TextEditor.
    Exposes a compatibility API so WorkspaceTab can treat it
    as a drop-in replacement for TextEditor.
    AST Outline and Chunks browsing live in the left ExplorerPanel.
    """

    TAB_ORIGINAL = 0
    TAB_CURRENT = 1
    TAB_DIFF = 2

    # Maps internal tab index → key used by WorkspaceTab / SplitColumnFrame
    _TAB_KEYS = {0: "original", 1: "current", 2: "diff"}

    # Reverse mapping: key → index (for hide/show operations)
    _TAB_INDICES = {"original": 0, "current": 1, "diff": 2}

    def __init__(self, parent, on_split_request=None, **kwargs):
        """
        Args:
            on_split_request: optional callable(tab_key) invoked when the user
                              chooses "Open in Column" from the inner-tab
                              right-click menu.  WorkspaceTab wires this up.
        """
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        self.on_split_request = on_split_request

        self.notebook = ttk.Notebook(self, style="Inner.TNotebook")
        self.notebook.pack(fill="both", expand=True)

        # Tab 1: Original (read-only TextEditor)
        self.original_editor = TextEditor(self.notebook)
        self.original_editor.text.config(state="disabled")
        self.notebook.add(self.original_editor, text="  Original  ")

        # Tab 2: Current (editable TextEditor)
        self.current_editor = TextEditor(self.notebook)
        self.notebook.add(self.current_editor, text="  Current  ")

        # Tab 3: Diff / Preview
        self.diff_view = DiffView(self.notebook)
        self.notebook.add(self.diff_view, text="  Diff  ")

        # Default to Current tab
        self.notebook.select(self.TAB_CURRENT)

        # Right-click on inner tabs → "Open in Column" context menu
        self.notebook.bind("<Button-3>", self._on_inner_tab_right_click)

    # ── compatibility API (delegates to current_editor) ────

    @property
    def file_path(self):
        return self.current_editor.file_path

    @file_path.setter
    def file_path(self, path):
        self.current_editor.file_path = path
        self.original_editor.file_path = path

    @property
    def is_modified(self):
        return self.current_editor.is_modified

    @property
    def text(self):
        """Direct access to the Current tab's Text widget."""
        return self.current_editor.text

    def get_content(self):
        return self.current_editor.get_content()

    def set_content(self, content):
        """Set content in both Original (read-only baseline) and Current (editable)."""
        # Original tab: enable, populate, disable, clear modified
        self.original_editor.text.config(state="normal")
        self.original_editor.set_content(content)
        self.original_editor.text.config(state="disabled")
        self.original_editor._modified = False

        # Current tab: populate as editable working copy
        self.current_editor.set_content(content)

    def get_cursor_line(self):
        return self.current_editor.get_cursor_line()

    def _refresh_status(self):
        self.current_editor._refresh_status()

    # ── tab-specific API ───────────────────────────────────

    def load_diff(self, diff_text):
        """Load unified diff into the Diff tab and switch to it."""
        self.diff_view.load_diff(diff_text)
        self.notebook.select(self.TAB_DIFF)

    def load_diff_side_by_side(self, original, patched):
        """Load inline comparison into the Diff tab and switch to it."""
        self.diff_view.load_side_by_side(original, patched)
        self.notebook.select(self.TAB_DIFF)

    def select_tab(self, index):
        """Programmatically switch to a tab by index."""
        self.notebook.select(index)

    def hide_tab(self, tab_key: str):
        """
        Hide a tab from the inner notebook header (move-to-column semantics).
        If the hidden tab is currently selected, fall back to Current.
        """
        idx = self._TAB_INDICES.get(tab_key)
        if idx is None:
            return
        # Guard: never hide Current — it's the primary editing surface
        if tab_key == "current":
            return
        # If this tab is currently active, switch away first
        try:
            if self.notebook.index("current") == idx:
                self.notebook.select(self.TAB_CURRENT)
        except tk.TclError:
            pass
        self.notebook.tab(idx, state="hidden")

    def show_tab(self, tab_key: str):
        """Restore a previously hidden tab back to the inner notebook header."""
        idx = self._TAB_INDICES.get(tab_key)
        if idx is not None:
            self.notebook.tab(idx, state="normal")

    def _on_inner_tab_right_click(self, event):
        """Show context menu on right-click over an inner tab label."""
        # ttk.Notebook.index("@x,y") gives the tab index under the cursor
        # and raises TclError if the click lands outside any tab label.
        try:
            clicked_idx = self.notebook.index(f"@{event.x},{event.y}")
        except tk.TclError:
            return  # Click was not on any tab label

        tab_key = self._TAB_KEYS.get(clicked_idx)
        if tab_key is None:
            return

        label = self._TAB_KEYS[clicked_idx].title()
        # Check if this tab is already in a column (toggled off label)
        currently_split = self.notebook.tab(clicked_idx, "state") == "hidden"
        action = "Restore" if currently_split else "Move to Column"

        menu = tk.Menu(self, tearoff=0, bg=THEME["bg2"], fg=THEME["fg"])
        menu.add_command(
            label=f"{action}:  {label}",
            command=lambda k=tab_key: self._request_split(k),
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _request_split(self, tab_key: str):
        """Notify WorkspaceTab (via callback) that the user wants a split."""
        if self.on_split_request:
            self.on_split_request(tab_key)

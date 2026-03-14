"""
SplitColumnFrame – A detachable panel that clones one of the EditorNotebook
tabs into its own resizable column in the WorkspaceTab PanedWindow.

Each column has:
  - A compact header bar with the source-tab name and a [×] close button
  - A content area containing a fresh instance of the appropriate view widget
    (DiffView or a read-only TextEditor)

WorkspaceTab is the owner; it creates, updates, and removes SplitColumnFrames.
No business logic lives here — just display.
"""
import tkinter as tk
from theme import THEME
from ui.modules.text_editor import TextEditor
from ui.modules.editor_notebook import DiffView


class SplitColumnFrame(tk.Frame):
    """
    Self-contained split-view column.  Contains one of three possible views
    (original, current, diff) that mirrors the matching inner tab.
    """

    # maps tab_key → human label
    _LABELS = {
        "original": "Original",
        "current":  "Current",
        "diff":     "Diff",
    }

    def __init__(self, parent, tab_key: str, on_close, **kwargs):
        """
        Args:
            parent:   the PanedWindow that owns this frame
            tab_key:  "original" | "current" | "diff"
            on_close: callable that removes this column from the workspace
        """
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        self.tab_key = tab_key
        self._on_close_cb = on_close

        self._build_header()
        self._build_content()

    # ── construction ────────────────────────────────────────

    def _build_header(self):
        header = tk.Frame(self, bg=THEME["bg2"], height=24)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        lbl = self._LABELS.get(self.tab_key, self.tab_key.title())
        tk.Label(
            header,
            text=f"  {lbl}  ",
            bg=THEME["bg2"],
            fg=THEME["fg"],
            font=THEME["font_interface_small"],
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        tk.Button(
            header,
            text="×",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            activebackground=THEME["error"],
            activeforeground="#ffffff",
            font=THEME["font_interface_small"],
            relief="flat",
            padx=6,
            pady=0,
            cursor="hand2",
            command=self._on_close_cb,
        ).pack(side="right")

    def _build_content(self):
        """Create the appropriate view widget for this tab_key."""
        if self.tab_key in ("original", "current"):
            self.view = TextEditor(self)
            self.view.text.config(state="disabled")   # read-only mirror
        elif self.tab_key == "diff":
            self.view = DiffView(self)
        else:
            # Fallback: plain read-only text
            self.view = TextEditor(self)
            self.view.text.config(state="disabled")

        self.view.pack(fill="both", expand=True)

    # ── update API (called by WorkspaceTab) ─────────────────

    def set_text(self, content: str):
        """For original/current columns: push plain text into the mirror."""
        if hasattr(self.view, "set_content"):
            # TextEditor API
            self.view.text.config(state="normal")
            self.view.set_content(content)
            self.view.text.config(state="disabled")

    def set_diff(self, diff_text: str):
        """For diff column: push a unified diff string."""
        if hasattr(self.view, "load_diff"):
            self.view.load_diff(diff_text)

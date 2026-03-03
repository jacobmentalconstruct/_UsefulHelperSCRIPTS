"""
Text editor widget with line-number gutter and live-sync status indicator.
Used as the scratchpad inside each workspace tab.
"""
import tkinter as tk
from theme import THEME


class TextEditor(tk.Frame):
    """
    Code-style text editor with:
    - Line-number gutter (auto-updating)
    - Modified / synced status tracking
    - Cursor position reporting
    """

    def __init__(self, parent, change_callback=None, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)

        self._modified = False
        self._file_path = None
        self.change_callback = change_callback

        # --- status bar ---
        self._status = tk.Label(
            self,
            text="No file",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
            padx=6,
        )
        self._status.pack(fill="x", side="bottom")

        # --- editor area (gutter + text) ---
        editor_frame = tk.Frame(self, bg=THEME["bg"])
        editor_frame.pack(fill="both", expand=True)

        self.gutter = tk.Text(
            editor_frame,
            width=5,
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_code"],
            state="disabled",
            relief="flat",
            padx=4,
            takefocus=0,
            cursor="arrow",
        )
        self.gutter.pack(side="left", fill="y")

        self.text = tk.Text(
            editor_frame,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            insertbackground=THEME["accent"],
            selectbackground=THEME["accent"],
            font=THEME["font_code"],
            relief="flat",
            undo=True,
            wrap="none",
            padx=6,
            pady=4,
        )
        self.text.pack(side="left", fill="both", expand=True)

        scrollbar = tk.Scrollbar(editor_frame, command=self._on_scroll)
        scrollbar.pack(side="right", fill="y")
        self.text.config(yscrollcommand=scrollbar.set)

        # Sync gutter with text scroll
        self.text.bind("<KeyRelease>", self._on_change)
        self.text.bind("<ButtonRelease-1>", self._on_change)
        self.text.bind("<<Modified>>", self._on_modified_flag)

        self._update_gutter()

    # ── public API ──────────────────────────────────────────

    @property
    def file_path(self):
        return self._file_path

    @file_path.setter
    def file_path(self, path):
        self._file_path = path
        self._refresh_status()

    @property
    def is_modified(self):
        return self._modified

    def get_content(self):
        return self.text.get("1.0", "end-1c")

    def set_content(self, content):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.edit_modified(False)
        self._modified = False
        self._update_gutter()
        self._refresh_status()

    def get_cursor_line(self):
        """Return the 1-based line number where the cursor sits."""
        return int(self.text.index("insert").split(".")[0])

    # ── internal ────────────────────────────────────────────

    def _on_scroll(self, *args):
        self.text.yview(*args)
        self.gutter.yview(*args)

    def _on_change(self, _event=None):
        self._update_gutter()
        self._refresh_status()
        if self.change_callback:
            self.change_callback()

    def _on_modified_flag(self, _event=None):
        if self.text.edit_modified():
            self._modified = True
            self._refresh_status()

    def _update_gutter(self):
        line_count = int(self.text.index("end-1c").split(".")[0])
        gutter_text = "\n".join(str(i) for i in range(1, line_count + 1))
        self.gutter.config(state="normal")
        self.gutter.delete("1.0", "end")
        self.gutter.insert("1.0", gutter_text)
        self.gutter.config(state="disabled")

    def _refresh_status(self):
        parts = []
        if self._file_path:
            parts.append(str(self._file_path))
        else:
            parts.append("No file")

        if self._modified:
            parts.append("[modified]")
        else:
            parts.append("[synced]")

        line = self.get_cursor_line()
        col = int(self.text.index("insert").split(".")[1])
        parts.append(f"Ln {line}, Col {col}")

        self._status.config(text="  |  ".join(parts))

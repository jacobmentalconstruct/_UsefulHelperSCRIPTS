"""
Patch Lens – Before/After diff view for AI-suggested changes.
Displays the original code alongside the patched version with
highlighted differences. Integrates with the PatchEngine.
Stateless UI: all patch logic is in backend/modules/patch_engine.py.
"""
import tkinter as tk
from theme import THEME
from ui.modules._buttons import AccentButton, ToolbarButton


class PatchLens(tk.Frame):
    """
    Side-by-side diff viewer for patch previews.
    Left panel:  Original code (read-only)
    Right panel: Patched code (read-only)
    Bottom:      Unified diff output
    """

    def __init__(self, parent, on_apply=None, on_reject=None, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        self._on_apply = on_apply
        self._on_reject = on_reject
        self._original = ""
        self._patched = ""

        # ── header bar ──────────────────────────────────────
        header = tk.Frame(self, bg=THEME["bg2"])
        header.pack(fill="x")

        tk.Label(
            header,
            text="PATCH PREVIEW",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
            padx=6,
        ).pack(side="left", pady=4)

        ToolbarButton(header, text="Reject", command=self._reject).pack(side="right", padx=2, pady=2)
        AccentButton(header, text="Apply", command=self._apply).pack(side="right", padx=2, pady=2)

        # ── side-by-side panels ─────────────────────────────
        paned = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=THEME["bg"],
            sashwidth=4,
            sashrelief="flat",
        )
        paned.pack(fill="both", expand=True, pady=(4, 0))

        # Left: Original
        left_frame = tk.Frame(paned, bg=THEME["bg2"])
        tk.Label(
            left_frame,
            text="ORIGINAL",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
        ).pack(fill="x", padx=4, pady=(4, 0))

        self.original_text = tk.Text(
            left_frame,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code"],
            state="disabled",
            relief="flat",
            wrap="none",
            padx=6,
            pady=4,
        )
        self.original_text.pack(fill="both", expand=True, padx=4, pady=4)
        paned.add(left_frame, stretch="always")

        # Right: Patched
        right_frame = tk.Frame(paned, bg=THEME["bg2"])
        tk.Label(
            right_frame,
            text="PATCHED",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
        ).pack(fill="x", padx=4, pady=(4, 0))

        self.patched_text = tk.Text(
            right_frame,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code"],
            state="disabled",
            relief="flat",
            wrap="none",
            padx=6,
            pady=4,
        )
        self.patched_text.pack(fill="both", expand=True, padx=4, pady=4)
        paned.add(right_frame, stretch="always")

        # ── diff tag config ─────────────────────────────────
        for widget in (self.original_text, self.patched_text):
            widget.tag_config("added", background="#2a4a2a", foreground=THEME["success"])
            widget.tag_config("removed", background="#4a2a2a", foreground=THEME["error"])
            widget.tag_config("changed", background="#3a3a2a", foreground=THEME["warning"])

        # ── unified diff panel ──────────────────────────────
        diff_frame = tk.Frame(self, bg=THEME["bg2"])
        diff_frame.pack(fill="x", pady=(4, 0))

        tk.Label(
            diff_frame,
            text="UNIFIED DIFF",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
        ).pack(fill="x", padx=4, pady=(4, 0))

        self.diff_text = tk.Text(
            diff_frame,
            bg=THEME["bg3"],
            fg=THEME["fg_dim"],
            font=THEME["font_code_small"],
            height=8,
            state="disabled",
            relief="flat",
            wrap="none",
            padx=6,
            pady=4,
        )
        self.diff_text.pack(fill="x", padx=4, pady=4)

        self.diff_text.tag_config("add_line", foreground=THEME["success"])
        self.diff_text.tag_config("del_line", foreground=THEME["error"])
        self.diff_text.tag_config("hunk", foreground=THEME["accent"])

    # ── public API ──────────────────────────────────────────

    def load_diff(self, original, patched, diff_text=""):
        """
        Load a before/after comparison.
        original: original source string
        patched:  patched source string
        diff_text: optional unified diff string
        """
        self._original = original
        self._patched = patched

        # Populate original panel
        self.original_text.config(state="normal")
        self.original_text.delete("1.0", "end")
        self.original_text.insert("1.0", original)
        self.original_text.config(state="disabled")

        # Populate patched panel
        self.patched_text.config(state="normal")
        self.patched_text.delete("1.0", "end")
        self.patched_text.insert("1.0", patched)
        self.patched_text.config(state="disabled")

        # Populate diff
        self.diff_text.config(state="normal")
        self.diff_text.delete("1.0", "end")
        if diff_text:
            for line in diff_text.splitlines():
                if line.startswith("+"):
                    self.diff_text.insert("end", line + "\n", "add_line")
                elif line.startswith("-"):
                    self.diff_text.insert("end", line + "\n", "del_line")
                elif line.startswith("@@"):
                    self.diff_text.insert("end", line + "\n", "hunk")
                else:
                    self.diff_text.insert("end", line + "\n")
        self.diff_text.config(state="disabled")

        # Highlight differences
        self._highlight_differences()

    def clear(self):
        """Clear all panels."""
        for widget in (self.original_text, self.patched_text, self.diff_text):
            widget.config(state="normal")
            widget.delete("1.0", "end")
            widget.config(state="disabled")

    # ── internal ────────────────────────────────────────────

    def _highlight_differences(self):
        """Mark added/removed/changed lines in side-by-side view."""
        orig_lines = self._original.splitlines()
        patch_lines = self._patched.splitlines()

        # Simple line-by-line comparison
        max_lines = max(len(orig_lines), len(patch_lines))
        for i in range(max_lines):
            line_num = i + 1
            orig = orig_lines[i] if i < len(orig_lines) else None
            patched = patch_lines[i] if i < len(patch_lines) else None

            if orig is None:
                # Added in patched
                self.patched_text.tag_add("added", f"{line_num}.0", f"{line_num}.end")
            elif patched is None:
                # Removed from original
                self.original_text.tag_add("removed", f"{line_num}.0", f"{line_num}.end")
            elif orig != patched:
                # Changed
                self.original_text.tag_add("changed", f"{line_num}.0", f"{line_num}.end")
                self.patched_text.tag_add("changed", f"{line_num}.0", f"{line_num}.end")

    def _apply(self):
        if self._on_apply:
            self._on_apply(self._patched)

    def _reject(self):
        if self._on_reject:
            self._on_reject()

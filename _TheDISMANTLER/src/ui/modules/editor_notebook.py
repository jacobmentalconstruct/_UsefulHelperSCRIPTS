"""
EditorNotebook – 4-tab notebook replacing the single TextEditor
in WorkspaceTab.
Tab 1: Original  (read-only baseline as loaded from disk)
Tab 2: Current   (editable scratchpad)
Tab 3: Diff      (read-only colored diff preview)
Tab 4: Context   (diagnostic: AST nodes, chunks, metrics)
Stateless UI: all data comes through WorkspaceTab / BackendEngine.
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


# ── ContextView ────────────────────────────────────────────


class ContextView(tk.Frame):
    """
    Read-only diagnostic panel showing sliding window chunks,
    AST hierarchy, or code metrics.
    """

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)

        # Mode toolbar
        toolbar = tk.Frame(self, bg=THEME["bg2"])
        toolbar.pack(fill="x")

        self._mode_var = tk.StringVar(value="chunks")
        for label, val in [("Chunks", "chunks"), ("AST", "ast"), ("Metrics", "metrics")]:
            tk.Radiobutton(
                toolbar,
                text=label,
                variable=self._mode_var,
                value=val,
                bg=THEME["bg2"],
                fg=THEME["fg"],
                selectcolor=THEME["accent"],
                activebackground=THEME["bg2"],
                font=THEME["font_interface_small"],
                indicatoron=0,
                padx=10,
                pady=2,
            ).pack(side="left", padx=2, pady=2)

        self.text = tk.Text(
            self,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code_small"],
            state="disabled",
            relief="flat",
            wrap="none",
            padx=6,
            pady=4,
        )
        self.text.pack(fill="both", expand=True)

        # Tags
        self.text.tag_config("heading", foreground=THEME["accent"], font=THEME["font_interface_bold"])
        self.text.tag_config("key", foreground=THEME["warning"])
        self.text.tag_config("value", foreground=THEME["fg"])
        self.text.tag_config("dim", foreground=THEME["fg_dim"])

    def load_chunks(self, chunks):
        """Display sliding window chunks."""
        self._mode_var.set("chunks")
        self._clear()
        self.text.config(state="normal")
        self.text.insert("end", f"CHUNKS ({len(chunks)})\n", "heading")
        self.text.insert("end", "=" * 50 + "\n\n", "dim")
        for ch in chunks:
            self.text.insert("end", f"{ch.get('name', '?')}", "key")
            self.text.insert("end", f"  [{ch.get('chunk_type', '?')}]", "dim")
            self.text.insert(
                "end",
                f"  L{ch.get('start_line', '?')}-{ch.get('end_line', '?')}\n",
                "dim",
            )
            preview = ch.get("content", "")[:200]
            self.text.insert("end", f"  {preview}\n\n", "value")
        self.text.config(state="disabled")

    def load_ast(self, hierarchy):
        """Display AST hierarchy nodes."""
        self._mode_var.set("ast")
        self._clear()
        self.text.config(state="normal")
        self.text.insert("end", f"AST HIERARCHY ({len(hierarchy)} nodes)\n", "heading")
        self.text.insert("end", "=" * 50 + "\n\n", "dim")
        for node in hierarchy:
            indent = "  " * node.get("depth", 0)
            self.text.insert("end", f"{indent}{node.get('kind', '?')} ", "dim")
            self.text.insert("end", f"{node.get('name', '?')}", "key")
            self.text.insert(
                "end",
                f"  L{node.get('start_line', '?')}-{node.get('end_line', '?')}\n",
                "dim",
            )
        self.text.config(state="disabled")

    def load_metrics(self, metrics):
        """Display code metrics."""
        self._mode_var.set("metrics")
        self._clear()
        self.text.config(state="normal")
        self.text.insert("end", "CODE METRICS\n", "heading")
        self.text.insert("end", "=" * 50 + "\n\n", "dim")
        for k, v in metrics.items():
            self.text.insert("end", f"  {k}: ", "key")
            self.text.insert("end", f"{v}\n", "value")
        self.text.config(state="disabled")

    def clear(self):
        self._clear()

    def _clear(self):
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.config(state="disabled")


# ── EditorNotebook ─────────────────────────────────────────


class EditorNotebook(tk.Frame):
    """
    4-tab notebook container that replaces the single TextEditor.
    Exposes a compatibility API so WorkspaceTab can treat it
    as a drop-in replacement for TextEditor.
    """

    TAB_ORIGINAL = 0
    TAB_CURRENT = 1
    TAB_DIFF = 2
    TAB_CONTEXT = 3

    def __init__(self, parent, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)

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

        # Tab 4: Context
        self.context_view = ContextView(self.notebook)
        self.notebook.add(self.context_view, text="  Context  ")

        # Default to Current tab
        self.notebook.select(self.TAB_CURRENT)

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

    def load_context_chunks(self, chunks):
        """Load chunk data into the Context tab and switch to it."""
        self.context_view.load_chunks(chunks)
        self.notebook.select(self.TAB_CONTEXT)

    def load_context_ast(self, hierarchy):
        """Load AST hierarchy into the Context tab and switch to it."""
        self.context_view.load_ast(hierarchy)
        self.notebook.select(self.TAB_CONTEXT)

    def load_context_metrics(self, metrics):
        """Load code metrics into the Context tab and switch to it."""
        self.context_view.load_metrics(metrics)
        self.notebook.select(self.TAB_CONTEXT)

    def select_tab(self, index):
        """Programmatically switch to a tab by index."""
        self.notebook.select(index)

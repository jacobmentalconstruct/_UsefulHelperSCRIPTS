"""
ChunksExplorerPanel – AI context-unit browser for the left Explorer sidebar.

Displays the indexed chunks for the open file — the semantic code segments
(class bodies, function bodies) that the SlidingWindow feeds to the AI as
context when you ask it a question.

Clicking a chunk scrolls the Current editor to that chunk's span and
highlights it.  A summary footer shows totals and token budget.

Data comes from the backend action:
    {"system": "curate", "action": "curate_file", "file": path,
     "content": <current editor content>}

Each chunk is: {name, chunk_type, start_line, end_line, content,
                token_est, depth}
"""
import threading
import tkinter as tk
from theme import THEME


_TYPE_ABBREV = {
    "class":    "cls",
    "function": "fn",
    "method":   "mth",
    "file":     "fil",
    "code":     "cod",
}


class ChunksExplorerPanel(tk.Frame):
    """
    AI-context chunk browser for the left sidebar.
    Requires set_context(...) and set_text_widget(tw) before it is useful.
    """

    _SPAN_TAG = "chunk_span_highlight"

    def __init__(self, parent, text_widget=None, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        self.text_widget = text_widget
        self.backend = None
        self.file_path = None
        self._get_content = None   # callable → current editor text
        self._chunks = []

        self._build_ui()

    # ── UI construction ─────────────────────────────────────

    def _build_ui(self):
        # Header row
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
            text="↺ Curate",
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

        # Chunk listbox + scrollbar
        list_frame = tk.Frame(self, bg=THEME["bg"])
        list_frame.pack(fill="both", expand=True, padx=6, pady=(2, 0))

        scrollbar = tk.Scrollbar(list_frame, bg=THEME["bg2"])
        scrollbar.pack(side="right", fill="y")

        self.chunk_list = tk.Listbox(
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
        self.chunk_list.pack(fill="both", expand=True)
        scrollbar.config(command=self.chunk_list.yview)

        self.chunk_list.bind("<Button-1>", self._on_chunk_click)

        # Footer summary bar
        self.summary_label = tk.Label(
            self,
            text="",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
            padx=8,
        )
        self.summary_label.pack(fill="x", side="bottom")

    # ── public API ──────────────────────────────────────────

    def set_context(self, backend, file_path: str, get_content=None):
        """
        Called by WorkspaceTab when a file is loaded.
        get_content: optional callable() → current editor text string,
                     used so Curate always indexes the live buffer.
        """
        self.backend = backend
        self.file_path = file_path
        self._get_content = get_content
        # Don't auto-curate on load — curate is a heavier write operation.
        # The user can press "↺ Curate" or it will populate from a workflow result.
        self.status_label.config(text="Press ↺ Curate to index this file")
        self.chunk_list.delete(0, "end")
        self._chunks = []
        self.summary_label.config(text="")

    def set_text_widget(self, text_widget):
        """Update the editor text widget used for navigation."""
        self.text_widget = text_widget

    def load_chunks(self, chunks: list):
        """
        Populate the list from chunks already in memory
        (e.g. delivered by a workflow result).
        """
        self._chunks = chunks
        self.chunk_list.delete(0, "end")

        total_tokens = 0
        for ch in chunks:
            ctype  = _TYPE_ABBREV.get(ch.get("chunk_type", "?"), ch.get("chunk_type", "?"))
            name   = ch.get("name", "?")
            start  = ch.get("start_line", "?")
            end    = ch.get("end_line", "?")
            tokens = ch.get("token_est", 0)
            total_tokens += tokens
            depth  = ch.get("depth", 0)
            indent = "  " * depth
            self.chunk_list.insert(
                "end",
                f"{indent}[{ctype}]  {name}    L{start}–{end}  ~{tokens}t",
            )

        n = len(chunks)
        self.status_label.config(
            text=f"{n} chunk{'s' if n != 1 else ''}"
        )
        # Count unique kinds for summary
        kinds = {}
        for ch in chunks:
            k = ch.get("chunk_type", "?")
            kinds[k] = kinds.get(k, 0) + 1
        parts = [f"{v} {k}" for k, v in sorted(kinds.items())]
        self.summary_label.config(
            text=f"{',  '.join(parts)}  |  ~{total_tokens} tokens total"
        )

    # ── internal ────────────────────────────────────────────

    def _refresh(self):
        """Run curate_file on the current buffer in a daemon thread."""
        if not self.backend or not self.file_path:
            return
        self.status_label.config(text="Curating…")

        content = self._get_content() if self._get_content else None

        def _run():
            task = {
                "system": "curate",
                "action": "curate_file",
                "file": self.file_path,
            }
            if content is not None:
                task["content"] = content
            result = self.backend.execute_task(task)
            if result.get("status") == "ok":
                chunks = result.get("chunks", [])
                self.after(0, lambda c=chunks: self.load_chunks(c))
            else:
                msg = result.get("message", "Curation failed")
                self.after(0, lambda m=msg: self.status_label.config(text=m))

        threading.Thread(target=_run, daemon=True).start()

    def _on_chunk_click(self, event):
        """Scroll to and highlight the clicked chunk's span in the editor."""
        idx = self.chunk_list.nearest(event.y)
        if idx < 0 or idx >= len(self._chunks):
            return
        ch = self._chunks[idx]
        start = ch.get("start_line")
        end   = ch.get("end_line")
        if start is not None and self.text_widget:
            self._highlight_span(start, end or start)

    def _highlight_span(self, start_line: int, end_line: int):
        """Apply a muted background over the chunk's entire line range."""
        tw = self.text_widget
        # Dark teal — distinct from find highlights (dark blue) and AST highlights (dark amber)
        tw.tag_configure(self._SPAN_TAG, background="#0f2a28")
        tw.tag_remove(self._SPAN_TAG, "1.0", "end")
        tw.tag_add(self._SPAN_TAG, f"{start_line}.0", f"{end_line}.end")
        tw.see(f"{start_line}.0")
        tw.mark_set("insert", f"{start_line}.0")
        tw.focus_set()

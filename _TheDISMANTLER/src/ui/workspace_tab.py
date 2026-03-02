"""
WorkspaceTab – An isolated workspace instance containing a text editor
scratchpad and a chat panel sidebar, arranged in a PanedWindow.
Each tab tracks its own file path and sync state.
"""
import tkinter as tk
from theme import THEME
from ui.modules.text_editor import TextEditor
from ui.modules.chat_panel import ChatPanel


class WorkspaceTab(tk.Frame):
    """
    A single workspace tab for the ttk.Notebook.
    Left side:  TextEditor (scratchpad with line numbers)
    Right side: ChatPanel (message history + model selector)
    """

    def __init__(self, parent, backend=None, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        self.backend = backend
        self._file_path = None

        # Horizontal PanedWindow splits editor and chat
        self.paned = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=THEME["bg"],
            sashwidth=4,
            sashrelief="flat",
        )
        self.paned.pack(fill="both", expand=True)

        # Left: Text editor
        self.editor = TextEditor(self.paned)
        self.paned.add(self.editor, stretch="always")

        # Right: Chat panel
        self.chat = ChatPanel(self.paned, on_send=self._on_chat_send)
        self.paned.add(self.chat, width=340, stretch="never")

    # ── public API ──────────────────────────────────────────

    @property
    def file_path(self):
        return self._file_path

    def load_file(self, path):
        """Load a file into the editor scratchpad."""
        if not self.backend:
            return
        result = self.backend.execute_task({
            "system": "file", "action": "read", "path": path
        })
        if result.get("status") == "ok":
            self._file_path = path
            self.editor.file_path = path
            self.editor.set_content(result["content"])

    def save_file(self):
        """Save the current editor content back to disk (with auto-archive)."""
        if not self.backend or not self._file_path:
            return
        content = self.editor.get_content()
        self.backend.execute_task({
            "system": "file",
            "action": "write",
            "path": self._file_path,
            "content": content,
        })
        self.editor.text.edit_modified(False)
        self.editor._modified = False
        self.editor._refresh_status()

    def get_tab_title(self):
        """Return a short title for the notebook tab."""
        if self._file_path:
            return self._file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return "Untitled"

    # ── internal ────────────────────────────────────────────

    def _on_chat_send(self, message, model):
        """Handle a chat message: gather context, call AI, show response."""
        if not self.backend or not model:
            self.chat.append_message("system", "No model selected.")
            return

        # Gather sliding-window context from the cursor position
        context_chunks = []
        if self._file_path:
            cursor_line = self.editor.get_cursor_line()
            context_chunks = self.backend.get_context_for_cursor(
                self._file_path, cursor_line
            )

        # Format and send to AI
        prompt = self.backend.controllers["ai"].format_prompt(
            message, context_chunks
        )

        self.chat.append_message("system", f"Thinking... ({model})")

        def on_done(response):
            self.after(0, lambda: self.chat.append_message("assistant", response))

        self.backend.controllers["ai"].generate_async(
            model, prompt, on_done=on_done
        )

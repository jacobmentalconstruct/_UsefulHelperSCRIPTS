"""
WorkspaceTab – An isolated workspace instance containing a 4-tab
editor notebook and a chat panel sidebar, arranged in a PanedWindow.
Each tab tracks its own file path and sync state.
"""
import tkinter as tk
import threading
from theme import THEME
from ui.modules.editor_notebook import EditorNotebook
from ui.modules.chat_panel import ChatPanel


class WorkspaceTab(tk.Frame):
    """
    A single workspace tab for the main ttk.Notebook.
    Left side:  EditorNotebook (Original | Current | Diff | Context)
    Right side: ChatPanel (message history + model selector)
    """

    def __init__(self, parent, backend=None, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        self.backend = backend
        self._file_path = None
        self._workflow_running = False

        # Horizontal PanedWindow splits editor notebook and chat
        self.paned = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=THEME["bg"],
            sashwidth=4,
            sashrelief="flat",
        )
        self.paned.pack(fill="both", expand=True)

        # Left: 4-tab editor notebook
        self.editor = EditorNotebook(self.paned)
        self.paned.add(self.editor, stretch="always")

        # Right: Chat panel
        self.chat = ChatPanel(self.paned, on_send=self._on_chat_send)
        self.paned.add(self.chat, width=340, stretch="never")

    # ── public API ──────────────────────────────────────────

    @property
    def file_path(self):
        return self._file_path

    def load_file(self, path):
        """Load a file into both Original (read-only) and Current (editable) tabs."""
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
        """Save the Current tab content back to disk (with auto-archive)."""
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
        self.editor.current_editor._modified = False
        self.editor._refresh_status()

    def get_tab_title(self):
        """Return a short title for the notebook tab."""
        if self._file_path:
            return self._file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return "Untitled"

    # ── workflow execution ─────────────────────────────────

    def run_workflow(self, workflow_schema, model=None):
        """
        Launch a workflow in a background thread.
        workflow_schema: {"name": "...", "steps": [...]}
        """
        if self._workflow_running or not self.backend or not self._file_path:
            return

        self._workflow_running = True
        initial_context = {
            "file": self._file_path,
            "content": self.editor.get_content(),
        }
        if model:
            initial_context["model"] = model

        def status_cb(info):
            self.after(0, lambda i=info: self._on_workflow_status(i))

        def run():
            from backend.modules.workflow_engine import WorkflowEngine
            engine = WorkflowEngine(
                execute_fn=self.backend.execute_task,
                log=self.backend.log,
            )
            result = engine.run(
                workflow_schema, initial_context, status_callback=status_cb,
            )
            self.after(0, lambda: self._on_workflow_complete(result))

        threading.Thread(target=run, daemon=True).start()

    def _on_workflow_status(self, info):
        """Update chat panel with workflow progress."""
        step = info.get("step", 0)
        total = info.get("total", 0)
        status = info.get("status", "")
        self.chat.append_message("system", f"[{step}/{total}] {status}")

    def _on_workflow_complete(self, result):
        """Route workflow results to the appropriate editor tabs."""
        self._workflow_running = False
        ctx = result.get("context", {})

        # Route diff/patch data to Tab 3
        if "diff" in ctx:
            self.editor.load_diff(ctx["diff"])
        elif "previews" in ctx:
            # From export controller preview action
            for p in ctx["previews"]:
                if p.get("diff"):
                    self.editor.load_diff(p["diff"])
                    break

        # Route diagnostic data to Tab 4 (last populated view wins focus)
        if "chunks" in ctx:
            self.editor.load_context_chunks(ctx["chunks"])
        if "hierarchy" in ctx:
            self.editor.load_context_ast(ctx["hierarchy"])
        if "metrics" in ctx:
            self.editor.load_context_metrics(ctx["metrics"])

        self.chat.append_message("system", "Workflow complete.")

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

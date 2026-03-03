"""
WorkspaceTab – An isolated workspace instance containing:
- ExplorerPanel (left sidebar: Find/Replace, Outline, Chunks)
- EditorNotebook (center: 3-tab editor — Original | Current | Diff)
- ChatPanel (right sidebar)
Arranged in a horizontal PanedWindow.
"""
import tkinter as tk
import threading
from theme import THEME
from ui.modules.editor_notebook import EditorNotebook
from ui.modules.chat_panel import ChatPanel
from ui.modules.explorer_panel import ExplorerPanel
from ui.modules.split_column import SplitColumnFrame
from backend.modules.patch_engine import PatchEngine


class WorkspaceTab(tk.Frame):
    """
    A single workspace tab for the main ttk.Notebook.
    Left:   ExplorerPanel (Find/Replace, Outline, Chunks)
    Center: EditorNotebook (Original | Current | Diff)
    Right:  ChatPanel (message history + model selector)
    """

    def __init__(self, parent, backend=None, **kwargs):
        super().__init__(parent, bg=THEME["bg"], **kwargs)
        self.backend = backend
        self._file_path = None
        self._workflow_running = False
        self._original_baseline = None
        self._diff_debounce_timer = None
        self._split_columns: dict = {}   # {tab_key: SplitColumnFrame}

        # Horizontal PanedWindow: Explorer | EditorNotebook | [splits...] | Chat
        self.paned = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=THEME["bg"],
            sashwidth=4,
            sashrelief="flat",
        )
        self.paned.pack(fill="both", expand=True)

        # Left: Explorer Panel (with Find/Replace, File Tree, etc.)
        self.explorer = ExplorerPanel(self.paned, text_widget=None)
        self.paned.add(self.explorer, width=320, stretch="never")

        # Center: 3-tab editor notebook
        self.editor = EditorNotebook(
            self.paned,
            on_split_request=self._on_split_request,
        )
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
            # Always land on Current tab when a file is opened, regardless of
            # which inner tab was active before (e.g. Diff from a prior session)
            self.editor.select_tab(self.editor.TAB_CURRENT)
            # Store the frozen baseline for live diff comparison
            self._original_baseline = result["content"]
            # Clear diff view when new file loaded — call diff_view directly
            # to avoid auto-switching to the Diff tab on file open
            self.editor.diff_view.load_diff("")
            # Bind editor modify event to pause live-sync
            self.editor.text.bind("<<Modified>>", self._on_editor_modified)
            # Wire editor change callback for live diff regeneration
            self.editor.current_editor.change_callback = self._regenerate_diff_live
            # Wire explorer panel to current editor text widget
            self.explorer.set_text_widget(self.editor.current_editor.text)
            # Give explorer panels the backend context for the new file
            self.explorer.set_context(
                self.backend,
                path,
                get_content=self.editor.get_content,
            )
            # Push new file content to any open split columns
            self._update_split_columns("original", content=result["content"])
            self._update_split_columns("current", content=result["content"])
            self._update_split_columns("diff", diff_text="")

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
        # Resume live-sync after save (hash is updated by FileController.write_file)
        fc = self.backend.controllers.get("file")
        if fc and self._file_path:
            fc.resume_sync(self._file_path)

    def _on_editor_modified(self, _event=None):
        """Pause live-sync when user edits the buffer."""
        if self.editor.text.edit_modified() and self._file_path:
            fc = self.backend.controllers.get("file") if self.backend else None
            if fc:
                fc.pause_sync(self._file_path)

    def get_tab_title(self):
        """Return a short title for the notebook tab."""
        if self._file_path:
            return self._file_path.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        return "Untitled"

    # ── split column management ─────────────────────────────

    def _on_split_request(self, tab_key: str):
        """
        Called by EditorNotebook when the user right-clicks an inner tab
        and chooses "Open in Column".  Toggles a split column for that tab:
        - If none exists → create and insert before Chat pane
        - If one already exists → close it (toggle off)
        """
        if tab_key in self._split_columns:
            self._close_split_column(tab_key)
        else:
            self._open_split_column(tab_key)

    def _open_split_column(self, tab_key: str):
        """
        Create a new SplitColumnFrame, place it between the editor and Chat,
        and hide the source tab from the inner notebook (move semantics).
        """
        col = SplitColumnFrame(
            self.paned,
            tab_key=tab_key,
            on_close=lambda k=tab_key: self._close_split_column(k),
        )
        # Evict Chat, append column, re-append Chat so order is:
        # Explorer | Editor | [split columns...] | Chat
        self.paned.forget(self.chat)
        self.paned.add(col, width=420, stretch="never")
        self.paned.add(self.chat, width=340, stretch="never")
        self._split_columns[tab_key] = col

        # Move source tab out of inner notebook header
        self.editor.hide_tab(tab_key)

        # Populate column with current content immediately
        self._push_to_split_column(tab_key, col)

    def _close_split_column(self, tab_key: str):
        """Remove a split column and restore its tab to the inner notebook."""
        col = self._split_columns.pop(tab_key, None)
        if col:
            self.paned.forget(col)
            col.destroy()
            # Restore the tab to the inner notebook header
            self.editor.show_tab(tab_key)

    def _push_to_split_column(self, tab_key: str, col: "SplitColumnFrame"):
        """Push current content to a split column widget."""
        if tab_key == "original":
            content = self.editor.original_editor.get_content()
            col.set_text(content)
        elif tab_key == "current":
            content = self.editor.get_content()
            col.set_text(content)
        elif tab_key == "diff":
            # Regenerate diff to populate the column
            if self._original_baseline and self._file_path:
                try:
                    diff_text = PatchEngine.preview(
                        self._original_baseline, self.editor.get_content()
                    )
                    col.set_diff(diff_text)
                except Exception:
                    pass

    def _update_split_columns(self, tab_key: str, **payload):
        """Relay an update to the named split column if one is open."""
        col = self._split_columns.get(tab_key)
        if not col:
            return
        if tab_key in ("original", "current"):
            col.set_text(payload.get("content", ""))
        elif tab_key == "diff":
            col.set_diff(payload.get("diff_text", ""))

    # ── live diff regeneration ──────────────────────────────

    def _regenerate_diff_live(self):
        """
        Debounced callback: regenerate diff panel when editor content changes.
        Compares Current (editor) against Original (frozen baseline).
        """
        # Cancel pending timer if one exists
        if self._diff_debounce_timer:
            self.after_cancel(self._diff_debounce_timer)
            self._diff_debounce_timer = None

        # Schedule regeneration after 500ms of no changes
        def do_regenerate():
            self._diff_debounce_timer = None
            if not self._original_baseline or not self._file_path:
                return

            current_content = self.editor.get_content()
            try:
                diff_text = PatchEngine.preview(self._original_baseline, current_content)
                # Call diff_view.load_diff() directly — NOT editor.load_diff()
                # EditorNotebook.load_diff() auto-switches to the Diff tab which
                # would yank focus away while the user is typing in Current.
                self.editor.diff_view.load_diff(diff_text)
                # Also push to any open split columns
                self._update_split_columns("diff", diff_text=diff_text)
                self._update_split_columns("current", content=current_content)
            except Exception as e:
                self.backend.log(f"Live diff generation failed: {e}")

        self._diff_debounce_timer = self.after(500, do_regenerate)

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
        """Route workflow results to the appropriate panels."""
        self._workflow_running = False
        ctx = result.get("context", {})

        # Route diff/patch data to the Diff tab
        if "diff" in ctx:
            self.editor.load_diff(ctx["diff"])
        elif "previews" in ctx:
            # From export controller preview action
            for p in ctx["previews"]:
                if p.get("diff"):
                    self.editor.load_diff(p["diff"])
                    break

        # Route AST/chunk diagnostic data to the left explorer sidebar
        if "chunks" in ctx:
            self.explorer.load_chunks(ctx["chunks"])
        if "hierarchy" in ctx:
            self.explorer.load_hierarchy(ctx["hierarchy"])

        self.chat.append_message("system", "Workflow complete.")

    # ── internal ────────────────────────────────────────────

    def _on_chat_send(self, message, model):
        """
        Handle a chat message using the Surgeon-Agent architecture.

        1. Fetch the file manifest (structural map of the whole file).
        2. Select the most relevant chunks via intent-driven scoring.
        3. Detect holistic queries ("explain this", "find all X", …) and pass
           the holistic flag so AIController enters accumulator mode.
        4. Dispatch to the AI controller with manifest + chunks in schema.
        """
        if not self.backend or not model:
            self.chat.append_message("system", "No model selected.")
            return

        # ── Gather context using the Surgeon-Agent flow ─────
        context_chunks = []
        manifest       = None
        if self._file_path:
            cursor_line    = self.editor.get_cursor_line()
            context_chunks = self.backend.get_context_for_query(
                self._file_path, message, cursor_line
            )
            manifest = self.backend.get_manifest(self._file_path)

        from backend.ai_controller import AIController
        holistic = AIController.is_holistic_query(message)
        status_hint = "analysing full file…" if holistic else f"thinking… ({model})"
        self.chat.append_message("system", status_hint)

        def run():
            result = self.backend.execute_task({
                "system":         "ai",
                "action":         "generate",
                "model":          model,
                "prompt":         message,
                "context_chunks": context_chunks,
                "manifest":       manifest,
                "holistic":       holistic,
            })
            response = result.get("response", result.get("message", "No response"))
            self.after(0, lambda: self.chat.append_message("assistant", response))

        threading.Thread(target=run, daemon=True).start()

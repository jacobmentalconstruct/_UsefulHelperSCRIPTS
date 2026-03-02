"""
MainWindow – Orchestrates the tabbed workspace and global menu bar.
Built on ttk.Notebook for multi-file curation.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from theme import THEME
from ui.workspace_tab import WorkspaceTab
from ui.modules.transformer_panel import TransformerPanel


class WelcomePanel(tk.Frame):
    """
    Empty state shown when no files are open.
    Displays a low-contrast icon and explanatory text.
    """

    def __init__(self, parent, on_open_file=None):
        super().__init__(parent, bg=THEME["bg"])
        self.on_open_file = on_open_file

        # Center the content
        center = tk.Frame(self, bg=THEME["bg"])
        center.place(relx=0.5, rely=0.5, anchor="center")

        # Large subtle icon (using Unicode box drawing + circle)
        icon = tk.Label(
            center,
            text="◎",
            bg=THEME["bg"],
            fg=THEME["fg_dim"],
            font=("Consolas", 72),
        )
        icon.pack(pady=(0, 20))

        # Title
        title = tk.Label(
            center,
            text="DISMANTLER",
            bg=THEME["bg"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_bold"],
        )
        title.pack(pady=(0, 8))

        # Subtitle
        subtitle = tk.Label(
            center,
            text="Code Curation with Local AI",
            bg=THEME["bg"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
        )
        subtitle.pack(pady=(0, 20))

        # Hint text
        hint = tk.Label(
            center,
            text="⌘O  Open a file  |  ⌘N  New Tab",
            bg=THEME["bg"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
        )
        hint.pack(pady=(0, 12))

        # Or click button
        btn = tk.Button(
            center,
            text="Open File",
            command=on_open_file,
            bg=THEME["bg2"],
            fg=THEME["accent"],
            activebackground=THEME["accent"],
            activeforeground="#ffffff",
            font=THEME["font_interface"],
            relief="flat",
            padx=16,
            pady=6,
            cursor="hand2",
        )
        btn.pack()


class MainWindow(tk.Toplevel):
    """
    The primary application window.
    - ttk.Notebook with workspace tabs
    - Welcome panel shown when no files are open
    - Global menu bar: File, Edit, Chat, Tools, Settings
    - Status bar at the bottom
    """

    def __init__(self, backend, master=None):
        super().__init__(master)
        self.backend = backend
        self.title("The DISMANTLER")
        self.geometry("1280x800")
        self.configure(bg=THEME["bg"])
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self._apply_ttk_theme()
        self._build_menu()
        self._build_notebook()
        self._build_statusbar()

        # Show welcome panel initially (no default untitled tab)
        self._show_welcome()

    # ── ttk theme ───────────────────────────────────────────

    def _apply_ttk_theme(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TNotebook", background=THEME["bg"], borderwidth=0)
        style.configure(
            "TNotebook.Tab",
            background=THEME["bg2"],
            foreground=THEME["fg"],
            padding=[10, 4],
            font=THEME["font_interface"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", THEME["bg"])],
            foreground=[("selected", THEME["accent"])],
        )

        # Inner notebook style (EditorNotebook's 4 tabs inside each workspace)
        style.configure("Inner.TNotebook", background=THEME["bg"], borderwidth=0)
        style.configure(
            "Inner.TNotebook.Tab",
            background=THEME["bg3"],
            foreground=THEME["fg_dim"],
            padding=[8, 2],
            font=THEME["font_interface_small"],
        )
        style.map(
            "Inner.TNotebook.Tab",
            background=[("selected", THEME["bg2"])],
            foreground=[("selected", THEME["fg"])],
        )

    # ── menu bar ────────────────────────────────────────────

    def _build_menu(self):
        menubar = tk.Menu(
            self,
            bg=THEME["bg2"],
            fg=THEME["fg"],
            activebackground=THEME["accent"],
            activeforeground="#ffffff",
        )

        # File
        file_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg2"], fg=THEME["fg"])
        file_menu.add_command(label="New Tab", command=self.add_workspace_tab, accelerator="Ctrl+N")
        file_menu.add_command(label="Open File...", command=self._open_file, accelerator="Ctrl+O")
        file_menu.add_command(label="Save", command=self._save_file, accelerator="Ctrl+S")
        file_menu.add_separator()
        file_menu.add_command(label="Close File", command=self._close_current_tab, accelerator="Ctrl+W")
        menubar.add_cascade(label="File", menu=file_menu)

        # Edit
        edit_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg2"], fg=THEME["fg"])
        edit_menu.add_command(label="Undo", accelerator="Ctrl+Z")
        edit_menu.add_command(label="Redo", accelerator="Ctrl+Y")
        edit_menu.add_separator()
        edit_menu.add_command(label="Find...", accelerator="Ctrl+F")
        menubar.add_cascade(label="Edit", menu=edit_menu)

        # Chat
        chat_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg2"], fg=THEME["fg"])
        chat_menu.add_command(label="Clear Chat History", command=self._clear_chat)
        menubar.add_cascade(label="Chat", menu=chat_menu)

        # Tools
        tools_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg2"], fg=THEME["fg"])
        tools_menu.add_command(label="AST Lens", command=self._open_ast_lens)
        tools_menu.add_command(label="Transformer Engine", command=self._open_transformer)
        tools_menu.add_command(label="AI Plan Refinement", command=self._open_refinement)
        tools_menu.add_command(label="Run Default Workflow", command=self._run_default_workflow)
        tools_menu.add_separator()
        tools_menu.add_command(label="Refresh Models", command=self._refresh_models)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        # Settings
        settings_menu = tk.Menu(menubar, tearoff=0, bg=THEME["bg2"], fg=THEME["fg"])
        settings_menu.add_command(label="Preferences")
        menubar.add_cascade(label="Settings", menu=settings_menu)

        self.config(menu=menubar)

        # Keyboard shortcuts
        self.bind_all("<Control-n>", lambda e: self.add_workspace_tab())
        self.bind_all("<Control-o>", lambda e: self._open_file())
        self.bind_all("<Control-s>", lambda e: self._save_file())
        self.bind_all("<Control-w>", lambda e: self._close_current_tab())

    # ── notebook ────────────────────────────────────────────

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        self.welcome_tab_id = None

    def _show_welcome(self):
        """Display the welcome panel when no workspace tabs are open."""
        welcome = WelcomePanel(self.notebook, on_open_file=self._open_file)
        self.welcome_tab_id = self.notebook.add(welcome, text="  Welcome  ")
        self.notebook.select(self.welcome_tab_id)

    def _hide_welcome(self):
        """Remove the welcome panel when the first workspace tab is opened."""
        if self.welcome_tab_id:
            self.notebook.forget(self.welcome_tab_id)
            self.welcome_tab_id = None

    def add_workspace_tab(self, file_path=None):
        """Create a new workspace tab, optionally loading a file."""
        # Hide welcome panel if this is the first tab
        if self.welcome_tab_id:
            self._hide_welcome()

        tab = WorkspaceTab(self.notebook, backend=self.backend)
        if file_path:
            tab.load_file(file_path)

        title = tab.get_tab_title()
        tab_id = self.notebook.add(tab, text=f"  {title}  ")
        self.notebook.select(tab_id)
        return tab

    def _get_current_tab(self):
        sel = self.notebook.select()
        if sel:
            return self.notebook.nametowidget(sel)
        return None

    # ── status bar ──────────────────────────────────────────

    def _build_statusbar(self):
        self.statusbar = tk.Label(
            self,
            text="Ready",
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=THEME["font_interface_small"],
            anchor="w",
            padx=8,
        )
        self.statusbar.pack(fill="x", side="bottom")

    def set_status(self, text):
        self.statusbar.config(text=text)

    # ── menu actions ────────────────────────────────────────

    def _open_file(self):
        path = filedialog.askopenfilename(
            filetypes=[
                ("All Source", "*.py *.js *.ts *.java *.c *.cpp *.go *.rs *.rb"),
                ("Python", "*.py"),
                ("All Files", "*.*"),
            ]
        )
        if path:
            self.add_workspace_tab(file_path=path)

    def _save_file(self):
        tab = self._get_current_tab()
        if tab and isinstance(tab, WorkspaceTab):
            if tab.file_path:
                tab.save_file()
                self.set_status(f"Saved: {tab.file_path}")
            else:
                self._save_file_as(tab)

    def _save_file_as(self, tab):
        path = filedialog.asksaveasfilename(
            defaultextension=".py",
            filetypes=[("Python", "*.py"), ("All Files", "*.*")],
        )
        if path:
            tab._file_path = path
            tab.editor.file_path = path
            tab.save_file()
            idx = self.notebook.index(tab)
            self.notebook.tab(idx, text=f"  {tab.get_tab_title()}  ")
            self.set_status(f"Saved: {path}")

    def _close_current_tab(self):
        """Close the currently active tab with a save/discard/cancel dialog."""
        tab = self._get_current_tab()
        if tab:
            self._close_tab(tab)

    def _close_tab(self, tab):
        """
        Close a specific tab.
        Shows a save/discard/cancel dialog if the tab has unsaved changes.
        """
        if isinstance(tab, WorkspaceTab):
            if tab.editor.is_modified:
                # Multi-choice dialog: Save / Discard / Cancel
                file_desc = tab.file_path or "Untitled"
                dialog = messagebox.askyesnocancel(
                    "Unsaved Changes",
                    f"Save changes to {file_desc}?",
                    icon=messagebox.WARNING,
                )
                if dialog is None:  # Cancel
                    return
                elif dialog:  # Yes (Save)
                    if tab.file_path:
                        tab.save_file()
                    else:
                        self._save_file_as(tab)
                        if not tab.file_path:  # Save As was cancelled
                            return
                # else: dialog is False (Discard) - proceed to close

            # Actually close the tab
            self.notebook.forget(tab)
            tab.destroy()

            # If no more workspace tabs, show welcome panel
            workspace_tabs = [
                self.notebook.nametowidget(tid)
                for tid in self.notebook.tabs()
                if isinstance(self.notebook.nametowidget(tid), WorkspaceTab)
            ]
            if not workspace_tabs:
                self._show_welcome()

    def _clear_chat(self):
        tab = self._get_current_tab()
        if tab and isinstance(tab, WorkspaceTab):
            tab.chat.clear_history()

    def _open_ast_lens(self):
        """Show AST hierarchy in the Context tab of the current workspace."""
        tab = self._get_current_tab()
        if not tab or not isinstance(tab, WorkspaceTab) or not tab.file_path:
            self.set_status("AST Lens requires an open file.")
            return

        from backend.modules.ast_lens import get_hierarchy_flat
        hierarchy = get_hierarchy_flat(tab.file_path)
        tab.editor.load_context_ast(hierarchy)
        self.set_status(f"AST: {len(hierarchy)} nodes")

    def _open_transformer(self):
        """Open the Modular Transformation Engine UI."""
        TransformerPanel(self, backend=self.backend)

    def _open_refinement(self):
        """Open the AI Plan Refinement panel for the current file."""
        tab = self._get_current_tab()
        if not tab or not isinstance(tab, WorkspaceTab) or not tab.file_path:
            self.set_status("AI Plan Refinement requires an open file.")
            return

        # Generate extraction guide for the current file first
        result = self.backend.execute_task({
            "system": "transformer",
            "action": "guide",
            "file": tab.file_path,
        })

        if result.get("status") == "ok":
            from ui.modules.refinement_panel import RefinementPanel
            RefinementPanel(
                self,
                backend=self.backend,
                file_path=tab.file_path,
                initial_plan=result["guide"],
            )
        else:
            self.set_status(
                f"Failed to generate extraction guide: {result.get('message', 'Unknown error')}"
            )

    def _run_default_workflow(self):
        """Run the default curation workflow on the current file."""
        tab = self._get_current_tab()
        if not tab or not isinstance(tab, WorkspaceTab) or not tab.file_path:
            self.set_status("Workflow requires an open file.")
            return
        model = tab.chat.get_selected_model()
        tab.run_workflow(
            {"name": "Default Curation", "steps": ["curate", "code_metrics"]},
            model=model,
        )
        self.set_status("Workflow started...")

    def _refresh_models(self):
        """Tell all workspace tabs to refresh their model selectors."""
        for tab_id in self.notebook.tabs():
            tab = self.notebook.nametowidget(tab_id)
            if isinstance(tab, WorkspaceTab):
                tab.chat.model_selector.refresh()
        self.set_status("Model list refreshed.")

    # ── lifecycle ───────────────────────────────────────────

    def _on_close(self):
        """Check for unsaved work before closing."""
        for tab_id in self.notebook.tabs():
            tab = self.notebook.nametowidget(tab_id)
            if isinstance(tab, WorkspaceTab) and tab.editor.is_modified:
                if not messagebox.askyesno("Unsaved Changes",
                        "You have unsaved changes. Quit anyway?"):
                    return
                break
        self.destroy()

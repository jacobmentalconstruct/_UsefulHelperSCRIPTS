import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sqlite3

class CellViewerModal(tk.Toplevel):
    """Reusable DB browser for instruction repositories."""
    def __init__(self, parent, colors, table_name, backend, on_select_callback):
        super().__init__(parent)
        self.title(f"Browse: {table_name.replace('_', ' ').title()}")
        self.geometry("600x400")
        self.configure(bg=colors.get('background'))
        self.backend = backend
        self.table_name = table_name
        self.callback = on_select_callback

        # Treeview for Tabular Data
        style = ttk.Style()
        style.configure(
            "Treeview",
            background=colors.get('entry_bg', colors.get('panel_bg')),
            foreground=colors.get('entry_fg', colors.get('foreground')),
            fieldbackground=colors.get('entry_bg', colors.get('panel_bg')),
            borderwidth=0
        )
        style.configure(
            "Treeview.Heading",
            background=colors.get('heading_bg', colors.get('panel_bg')),
            foreground=colors.get('heading_fg', colors.get('foreground'))
        )
        style.map(
            "Treeview",
            background=[('selected', colors.get('select_bg', colors.get('accent')))],
            foreground=[('selected', colors.get('select_fg', colors.get('entry_fg', colors.get('foreground'))))]
        )
        self.tree = ttk.Treeview(self, columns=("ID", "Name", "Preview", "Default"), show='headings')
        
        for col in ("ID", "Name", "Preview", "Default"): 
            self.tree.heading(col, text=col)
            self.tree.column(col, width=50 if col in ('ID', 'Default') else 150 if col == 'Name' else 250)
        
        self.tree.pack(fill='both', expand=True, padx=10, pady=10)
        self._refresh_data()

        # Subscribe to theme updates
        if hasattr(self.backend, 'bus'):
            self.backend.bus.subscribe("theme_updated", self.refresh_theme)

        self.btn_frame = tk.Frame(self, bg=colors.get('background'))
        self.btn_frame.pack(fill='x', padx=10, pady=5)
        
        btn_opts = {
            "bg": colors.get('panel_bg', colors.get('background')),
            "fg": colors.get('button_fg', colors.get('foreground')),
            "relief": "flat"
        }
        tk.Button(self.btn_frame, text="Load Selection", command=self._on_load, **btn_opts).pack(side='left', padx=5)
        tk.Button(self.btn_frame, text="Set as Default", command=self._on_default, **btn_opts).pack(side='left', padx=5)
        tk.Button(
            self.btn_frame,
            text="Delete",
            bg=colors.get('error', colors.get('accent')),
            fg=colors.get('button_fg', colors.get('foreground')),
            relief="flat",
            command=self._on_delete
        ).pack(side='right', padx=5)

    def _refresh_data(self):
        self.tree.delete(*self.tree.get_children())
        for item in self.backend.get_repository_items(self.table_name):
            # item = (id, name, content, is_default)
            self.tree.insert("", "end", values=(item[0], item[1], item[2][:100].replace('\n', ' '), "★" if item[3] else ""))

    def _on_load(self):
        selected = self.tree.selection()
        if selected:
            item_values = self.tree.item(selected[0], 'values')
            with sqlite3.connect(self.backend.db_path) as conn:
                if self.table_name == 'personas':
                    # Bonded Template: Returns a tuple for the callback to handle
                    res = conn.execute("SELECT role_text, sys_prompt_text, task_prompt_text FROM personas WHERE id=?", (item_values[0],)).fetchone()
                    if res: self.callback(res) 
                else:
                    # Atomic Fragment
                    res = conn.execute(f"SELECT content FROM {self.table_name} WHERE id=?", (item_values[0],)).fetchone()
                    if res: self.callback(res[0])
            self.destroy()

    def _on_default(self):
        selected = self.tree.selection()
        if selected:
            item_id = self.tree.item(selected[0], 'values')[0]
            self.backend.set_as_default(self.table_name, item_id)
            self._refresh_data()

    def _on_delete(self):
        selected = self.tree.selection()
        if selected:
            item_id = self.tree.item(selected[0], 'values')[0]
            self.backend.delete_repository_item(self.table_name, item_id)
            self._refresh_data()

    def refresh_theme(self, new_colors):
        self.configure(bg=new_colors.get('background'))
        self.btn_frame.configure(bg=new_colors.get('background'))
        style = ttk.Style()
        style.configure(
            "Treeview",
            background=new_colors.get('entry_bg', new_colors.get('panel_bg')),
            foreground=new_colors.get('entry_fg', new_colors.get('foreground')),
            fieldbackground=new_colors.get('entry_bg', new_colors.get('panel_bg'))
        )
        style.configure(
            "Treeview.Heading",
            background=new_colors.get('heading_bg', new_colors.get('panel_bg')),
            foreground=new_colors.get('heading_fg', new_colors.get('foreground'))
        )

class CELL_UI:
    def __init__(self, shell, backend):
        self.shell = shell
        self.backend = backend
        self.container = shell.get_main_container()
        self.colors = shell.colors

        # Track singleton modals / key widgets
        self._settings_window = None
        self.model_lbl = None
        self.btn_save_template = None
        self.btn_load_template = None
        self.btn_submit = None

        # Panels (Step 2 stubs)
        self.panel_prompt = None
        self.panel_inference = None
        self.panel_result = None
        self.panel_export = None

        # Two-column layout containers (Step 1 layout)
        self.main_row = None
        self.left_col = None
        self.right_col = None

        # Action bar ref (so it can be themed)
        self.action_frame = None

        # Panel widgets (stubs)
        self.infer_log = None
        self.result_text = None
        self.btn_accept = None
        self.btn_reject = None
        self.btn_exit = None

        # Export Router (inline) widgets
        self.export_router_frame = None
        self.export_dest_var = None
        self.export_dest_cb = None
        self.export_options_frame = None
        self.export_execute_btn = None
        self._export_selected = None
        
        # Restore window state from DB
        saved_geo = self.backend.get_setting('window_geometry')
        if saved_geo: self.shell.root.geometry(saved_geo)
        
        self._setup_main_window()
        self._build_context_menu()
        self._restore_component_state()
        self._register_signals()

    def _register_signals(self):
        """Connects UI to the nervous system."""
        if hasattr(self.backend, 'bus'):
            self.backend.bus.subscribe("log_append", self._on_log_append)
            self.backend.bus.subscribe("process_complete", self._on_process_complete)
            # Pass the new palette through so ttk/tk widgets can rebind safely.
            self.backend.bus.subscribe("theme_updated", self.refresh_theme)

    def _on_log_append(self, content):
        """Marshals background thread signal to main UI thread."""
        self.shell.root.after(0, lambda: self.append_log(content))

    def _on_process_complete(self, artifact):
        """Marshals completion signal to main UI thread."""
        text = artifact.get('response', '')
        self.shell.root.after(0, lambda: self.display_result(text))

    def _setup_main_window(self):
        # PANEL 1 (Prompt Setup): left column
        # Panels 2-4 (Inference / HITL / Export): right column
        self.main_row = tk.Frame(self.container, bg=self.colors.get('background'))
        self.main_row.pack(fill='both', expand=True)

        self.left_col = tk.Frame(self.main_row, bg=self.colors.get('background'))
        self.left_col.pack(side='left', fill='both', expand=True)

        self.right_col = tk.Frame(self.main_row, bg=self.colors.get('background'))
        self.right_col.pack(side='right', fill='y', padx=(8, 0))

        # PANEL 1 (Prompt Setup)
        self.panel_prompt = tk.Frame(self.container, bg=self.colors.get('background'))
        self.panel_prompt.pack(in_=self.left_col, fill='both', expand=True)

        # --- Top Label ---
        self.top_label = tk.Label(self.panel_prompt, text="Type in your idea HERE.", 
                 fg=self.colors.get('foreground'), bg=self.colors.get('background'),
                 font=("Segoe UI", 12, "bold"))
        self.top_label.pack(pady=(10, 5))

        # --- Formatting Toolbar ---
        self.toolbar = tk.Frame(self.panel_prompt, bg=self.colors.get('panel_bg'))
        self.toolbar.pack(fill='x', padx=10)
        
        btn_opts = {"bg": self.colors.get('panel_bg'), "fg": self.colors.get('foreground', 'white'), "relief": "flat", "padx": 5}
        self.btn_bold = tk.Button(self.toolbar, text="B", font=("TkDefaultFont", 9, "bold"), **btn_opts, command=self._bold_text)
        self.btn_bold.pack(side='left')
        self.btn_italic = tk.Button(self.toolbar, text="I", font=("TkDefaultFont", 9, "italic"), **btn_opts, command=self._italic_text)
        self.btn_italic.pack(side='left')
        self.btn_list = tk.Button(self.toolbar, text="• List", **btn_opts, command=self._bullet_list)
        self.btn_list.pack(side='left')
        
        self.btn_settings = tk.Button(self.toolbar, text="⚙", **btn_opts, command=self._open_settings)
        self.btn_settings.pack(side='right')

        # --- Inference Config Section ---
        self.config_frame = tk.LabelFrame(self.panel_prompt, text=" Inference Parameters ", 
                                     fg=self.colors.get('foreground'), bg=self.colors.get('background'),
                                     relief='solid', bd=1, font=("Segoe UI", 9, "bold"))
        self.config_frame.pack(fill='x', padx=10, pady=10)

        # Model Selection
        self.model_lbl = tk.Label(self.config_frame, text="Model:", bg=self.colors.get('background'), fg=self.colors.get('foreground', 'white'))
        self.model_lbl.grid(row=0, column=0, sticky='w', padx=5)
        self.model_var = tk.StringVar()
        self.model_dropdown = ttk.Combobox(self.config_frame, textvariable=self.model_var)
        self.model_dropdown['values'] = self.backend.get_models()
        self.model_dropdown.grid(row=0, column=1, sticky='ew', padx=5, pady=2)
        
        # Direct Role Input
        self.role_lbl = tk.Label(self.config_frame, text="System Role:", bg=self.colors.get('background'), fg=self.colors.get('foreground', 'white'))
        self.role_lbl.grid(row=1, column=0, sticky='w', padx=5)
        self.role_inner = tk.Frame(self.config_frame, bg=self.colors.get('background'))
        self.role_inner.grid(row=1, column=1, sticky='ew')
        
        self.role_entry = tk.Entry(
            self.role_inner,
            bg=self.colors.get('entry_bg', self.colors.get('panel_bg')),
            fg=self.colors.get('entry_fg', self.colors.get('foreground')),
            insertbackground=self.colors.get('entry_fg', self.colors.get('foreground'))
        )
        self.role_entry.insert(0, self.backend.system_role)
        self.role_entry.pack(side='left', fill='x', expand=True, padx=(5, 2), pady=2)
        
        self.btn_role_save = tk.Button(self.role_inner, text="💾", bg=self.colors.get('panel_bg'), fg=self.colors.get('button_fg', self.colors.get('foreground', 'white')), relief="flat", 
                  command=lambda: self._save_repo_dialog('saved_roles', self.role_entry.get()))
        self.btn_role_save.pack(side='left', padx=2)
        self.btn_role_open = tk.Button(self.role_inner, text="📂", bg=self.colors.get('panel_bg'), fg=self.colors.get('button_fg', self.colors.get('foreground', 'white')), relief="flat", 
                  command=lambda: self._open_viewer('saved_roles', lambda c: self._update_widget(self.role_entry, c)))
        self.btn_role_open.pack(side='left', padx=2)

        # Direct Prompt Input
        self.prompt_lbl = tk.Label(self.config_frame, text="System Prompt:", bg=self.colors.get('background'), fg=self.colors.get('foreground', 'white'))
        self.prompt_lbl.grid(row=2, column=0, sticky='nw', padx=5)
        self.prompt_inner = tk.Frame(self.config_frame, bg=self.colors.get('background'))
        self.prompt_inner.grid(row=2, column=1, sticky='ew')
        
        self.prompt_text = tk.Text(
            self.prompt_inner,
            height=3,
            bg=self.colors.get('entry_bg', self.colors.get('panel_bg')),
            fg=self.colors.get('entry_fg', self.colors.get('foreground')),
            insertbackground=self.colors.get('entry_fg', self.colors.get('foreground')),
            font=("Segoe UI", 9)
        )
        self.prompt_text.pack(side='left', fill='x', expand=True, padx=(5, 2), pady=2)
        
        self.prompt_btns_frame = tk.Frame(self.prompt_inner, bg=self.colors.get('background'))
        self.prompt_btns_frame.pack(side='left', fill='y')
        self.btn_prompt_save = tk.Button(self.prompt_btns_frame, text="💾", bg=self.colors.get('panel_bg'), fg=self.colors.get('button_fg', self.colors.get('foreground', 'white')), relief="flat", 
                  command=lambda: self._save_repo_dialog('saved_sys_prompts', self.prompt_text.get('1.0', 'end-1c')))
        self.btn_prompt_save.pack(pady=2)
        self.btn_prompt_open = tk.Button(self.prompt_btns_frame, text="📂", bg=self.colors.get('panel_bg'), fg=self.colors.get('button_fg', self.colors.get('foreground', 'white')), relief="flat", 
                  command=lambda: self._open_viewer('saved_sys_prompts', lambda c: self._update_widget(self.prompt_text, c)))
        self.btn_prompt_open.pack(pady=2)

        self.config_frame.columnconfigure(1, weight=1)

        # --- Main Input Box ---
        self.input_box = tk.Text(
            self.panel_prompt,
            undo=True,
            wrap="word",
            bg=self.colors.get('entry_bg', self.colors.get('panel_bg')),
            fg=self.colors.get('entry_fg', self.colors.get('foreground')),
            insertbackground=self.colors.get('entry_fg', self.colors.get('foreground')),
            selectbackground=self.colors.get('select_bg', self.colors.get('accent')),
            font=("Consolas", 11)
        )
        self.input_box.pack(fill='both', expand=True, padx=10, pady=5)
        self.input_box.focus_set()

        # --- Action Bar ---
        self.action_frame = tk.Frame(self.panel_prompt, bg=self.colors.get('background'))
        self.action_frame.pack(fill='x', padx=10, pady=(0, 10))

        self.btn_save_template = tk.Button(
            self.action_frame,
            text="SAVE AS TEMPLATE",
            bg=self.colors.get('panel_bg'),
            fg=self.colors.get('button_fg', self.colors.get('foreground', 'white')),
            font=("Segoe UI", 9),
            command=self._save_full_template
        )
        self.btn_save_template.pack(side='left', fill='x', expand=True, padx=(0, 2))

        self.btn_load_template = tk.Button(
            self.action_frame,
            text="LOAD TEMPLATE",
            bg=self.colors.get('panel_bg'),
            fg=self.colors.get('button_fg', self.colors.get('foreground', 'white')),
            font=("Segoe UI", 9),
            command=lambda: self._open_viewer('personas', None)
        )
        self.btn_load_template.pack(side='left', fill='x', expand=True, padx=(2, 5))

        self.btn_submit = tk.Button(
            self.action_frame,
            text="RUN CELL",
            bg=self.colors.get('accent'),
            fg=self.colors.get('button_fg', self.colors.get('foreground')),
            font=("Segoe UI", 10, "bold"),
            command=self._submit
        )
        self.btn_submit.pack(side='left', fill='x', expand=True)

        # ------------------------------------------------------------------
        # PANEL 2 — Inference Console
        # ------------------------------------------------------------------
        self.panel_inference = tk.LabelFrame(
            self.container,
            text=" Inference Console ",
            fg=self.colors.get('foreground'),
            bg=self.colors.get('background'),
            relief='solid', bd=1, font=("Segoe UI", 9, "bold")
        )
        self.panel_inference.pack(in_=self.right_col, fill='x', padx=10, pady=(0, 10))

        self.infer_log = tk.Text(
            self.panel_inference,
            height=6,
            wrap="word",
            bg=self.colors.get('entry_bg', self.colors.get('panel_bg')),
            fg=self.colors.get('entry_fg', self.colors.get('foreground')),
            insertbackground=self.colors.get('entry_fg', self.colors.get('foreground')),
            font=("Consolas", 10)
        )
        self.infer_log.insert('1.0', "[Stub] Inference logs will stream here during the run.\n")
        self.infer_log.configure(state='disabled')
        self.infer_log.pack(fill='x', expand=False, padx=10, pady=8)

        # ------------------------------------------------------------------
        # PANEL 3 — Result + HITL
        # ------------------------------------------------------------------
        self.panel_result = tk.LabelFrame(
            self.container,
            text=" Result + HITL ",
            fg=self.colors.get('foreground'),
            bg=self.colors.get('background'),
            relief='solid', bd=1, font=("Segoe UI", 9, "bold")
        )
        self.panel_result.pack(in_=self.right_col, fill='both', expand=True, padx=10, pady=(0, 10))

        self.result_text = tk.Text(
            self.panel_result,
            height=8,
            wrap="word",
            bg=self.colors.get('entry_bg', self.colors.get('panel_bg')),
            fg=self.colors.get('entry_fg', self.colors.get('foreground')),
            insertbackground=self.colors.get('entry_fg', self.colors.get('foreground')),
            font=("Consolas", 11)
        )
        self.result_text.insert('1.0', "[Stub] Model response will appear here.\n")
        self.result_text.configure(state='disabled')
        self.result_text.pack(fill='both', expand=True, padx=10, pady=(8, 6))

        hitl_bar = tk.Frame(self.panel_result, bg=self.colors.get('background'))
        hitl_bar.pack(fill='x', padx=10, pady=(0, 10))

        self.btn_accept = tk.Button(
            hitl_bar,
            text="ACCEPT",
            bg=self.colors.get('accent'),
            fg=self.colors.get('button_fg', 'white'),
            relief="flat",
            state='disabled',
            command=self._on_accept
        )
        self.btn_accept.pack(side='left', padx=(0, 6))

        self.btn_reject = tk.Button(
            hitl_bar,
            text="REJECT & EDIT",
            bg=self.colors.get('button_bg', self.colors.get('panel_bg')),
            fg=self.colors.get('button_fg', self.colors.get('foreground')),
            relief="flat",
            state='disabled',
            command=self._on_reject
        )
        self.btn_reject.pack(side='left', padx=(0, 6))

        self.btn_exit = tk.Button(
            hitl_bar,
            text="EXIT CELL",
            bg=self.colors.get('button_bg', self.colors.get('panel_bg')),
            fg=self.colors.get('button_fg', self.colors.get('foreground')),
            relief="flat",
            command=self.shell.root.destroy
        )
        self.btn_exit.pack(side='right')

        # PANEL 4 — Export / Spawn (inline router)
        self.panel_export = tk.LabelFrame(
            self.container,
            text=" Export / Spawn ",
            fg=self.colors.get('foreground'),
            bg=self.colors.get('background'),
            relief='solid', bd=1, font=("Segoe UI", 9, "bold")
        )
        self.panel_export.pack(in_=self.right_col, fill='x', padx=10, pady=(0, 12))

        self.export_router_frame = tk.Frame(self.panel_export, bg=self.colors.get('background'))
        self.export_router_frame.pack(fill='x', padx=10, pady=10)

        top_row = tk.Frame(self.export_router_frame, bg=self.colors.get('background'))
        top_row.pack(fill='x')

        tk.Label(top_row, text="Destination:", bg=self.colors.get('background'), fg=self.colors.get('foreground', 'white')).pack(side='left')

        self.export_dest_var = tk.StringVar(value="Spawn")
        self.export_dest_cb = ttk.Combobox(
            top_row, 
            textvariable=self.export_dest_var, 
            state='readonly', 
            values=["Spawn", "File", "Database", "Vector", "Code", "Patch", "Logs"]
        )
        self.export_dest_cb.pack(side='left', padx=8, fill='x', expand=True)

        self.export_execute_btn = tk.Button(
            top_row, text="EXECUTE", 
            bg=self.colors.get('accent'),
            fg=self.colors.get('button_fg', 'white'),
            relief="flat", state='disabled', command=self._handle_export
        )
        self.export_execute_btn.pack(side='right')

        self.export_options_frame = tk.Frame(self.export_router_frame, bg=self.colors.get('background'))
        self.export_options_frame.pack(fill='x', pady=(8, 0))

    def _build_export_options(dest: str):
        for w in self.export_options_frame.winfo_children(): w.destroy()
        if dest == "Spawn":
            tk.Button(self.export_options_frame, text="Spawn Child Cell", bg=self.colors.get('panel_bg'), fg=self.colors.get('button_fg', self.colors.get('foreground')), relief='flat', state='disabled').pack(fill='x', pady=2)
        elif dest == "File":
            for fmt in ("JSON", "Markdown", "Text"):
                tk.Button(self.export_options_frame, text=f"Save {fmt}", bg=self.colors.get('panel_bg'), fg=self.colors.get('button_fg', self.colors.get('foreground')), relief='flat', state='disabled').pack(fill='x', pady=2)

        self.export_dest_cb.bind('<<ComboboxSelected>>', lambda _e: _build_export_options(self.export_dest_var.get()))
        _build_export_options("Spawn")

    def _get_current_artifact(self):
        """Helper to package UI state into a standard artifact."""
        return {
            "payload": self.result_text.get("1.0", "end-1c"),
            "instructions": {
                "system_role": self.role_entry.get(),
                "system_prompt": self.prompt_text.get("1.0", "end-1c")
            },
            "metadata": {"model": self.model_var.get(), "source": "ui_action"}
        }

    def _handle_export(self):
        """Routes the execution command based on the selected destination."""
        dest = self.export_dest_var.get()
        artifact = self._get_current_artifact()

        if dest == "Spawn":
            self.backend.spawn_child(artifact)
        elif dest == "File":
            path = filedialog.asksaveasfilename(defaultextension=".txt", parent=self.shell.root)
            if path:
                self.backend.export_artifact(artifact, "File", path)
        elif dest == "Vector":
            # Save to default long-term memory bank
            self.backend.export_artifact(artifact, "Vector")
            messagebox.showinfo("Memory", "Artifact embedded into Vector Store.", parent=self.shell.root)
        else:
            messagebox.showinfo("Not Implemented", f"Export to {dest} is coming soon!", parent=self.shell.root)

    def _on_accept(self):
        """HITL: User approves the result."""
        artifact = self._get_current_artifact()
        self.backend.record_feedback(artifact, is_accepted=True)
        self.btn_accept.configure(state='disabled', text="ACCEPTED")
        self.btn_reject.configure(state='disabled')

    def _on_reject(self):
        """HITL: User rejects. Unlock input for editing."""
        artifact = self._get_current_artifact()
        self.backend.record_feedback(artifact, is_accepted=False)
        
        # Move result back to input box for refinement
        rejected_content = self.result_text.get("1.0", "end-1c")
        self.input_box.delete("1.0", "end")
        self.input_box.insert("1.0", rejected_content)
        
        # Reset UI state
        self.result_text.configure(state='normal')
        self.result_text.delete("1.0", "end")
        self.result_text.insert("1.0", "[Drafting refinement...]")
        self.result_text.configure(state='disabled')
        
        self.btn_accept.configure(state='disabled')
        self.btn_reject.configure(state='disabled')
        self.input_box.focus_set()

    def _apply_markdown_style(self, prefix, suffix=""):
        """Wraps selected text in Markdown markers for AI readability."""
        try:
            start = self.input_box.index("sel.first")
            end = self.input_box.index("sel.second")
            selected_text = self.input_box.get(start, end)
            self.input_box.delete(start, end)
            self.input_box.insert(start, f"{prefix}{selected_text}{suffix or prefix}")
        except tk.TclError:
            pass

    def _bold_text(self):
        self._apply_markdown_style("**")

    def _italic_text(self):
        self._apply_markdown_style("_")

    def _bullet_list(self):
        """Converts selected lines into a Markdown bulleted list."""
        try:
            start = self.input_box.index("sel.first linestart")
            end = self.input_box.index("sel.second lineend")
            lines = self.input_box.get(start, end).splitlines()
            bulleted_lines = [f"* {line.lstrip('* ')}" for line in lines]
            self.input_box.delete(start, end)
            self.input_box.insert(start, "\n".join(bulleted_lines))
        except tk.TclError:
            self.input_box.insert("insert", "* ")

    def _update_widget(self, widget, content):
        if isinstance(widget, tk.Entry):
            widget.delete(0, 'end')
            widget.insert(0, content)
        elif isinstance(widget, tk.Text):
            # Ensure widget is editable before update
            original_state = widget.cget('state')
            widget.configure(state='normal')
            widget.delete('1.0', 'end')
            widget.insert('1.0', content)
            # Only lock it back if it was originally disabled (e.g. logs), otherwise leave editable
            if original_state == 'disabled':
                widget.configure(state='disabled')

    def append_log(self, message: str):
        """Appends text to the inference console (Thread-Safe via _on_log_append)."""
        if self.infer_log is None: return
        self.infer_log.configure(state='normal')
        self.infer_log.insert('end', message) # Streamed tokens don't force newlines
        self.infer_log.see('end')
        self.infer_log.configure(state='disabled')

    def display_result(self, text: str):
        """Displays the final artifact and enables HITL buttons."""
        self.result_text.configure(state='normal')
        self.result_text.delete('1.0', 'end')
        self.result_text.insert('1.0', text)
        self.result_text.configure(state='disabled')
        
        if self.btn_accept:
            self.btn_accept.configure(state='normal')
        if self.btn_reject:
            self.btn_reject.configure(state='normal')
        if self.export_execute_btn:
            self.export_execute_btn.configure(state='normal')

    def _save_repo_dialog(self, table, content):
        """Modular save dialog for individual repositories."""
        dialog = tk.Toplevel(self.shell.root)
        dialog.title(f"Save to {table.split('_')[-1].title()}")
        dialog.geometry("300x150")
        dialog.configure(bg=self.colors.get('background'))

        dialog.transient(self.shell.root)
        dialog.grab_set()

        tk.Label(dialog, text="Name Selection:", bg=self.colors.get('background'), fg=self.colors.get('foreground', 'white')).pack(pady=5)
        name_entry = tk.Entry(dialog)
        name_entry.pack(padx=10, fill='x')
        name_entry.focus_set()

        default_var = tk.BooleanVar()
        tk.Checkbutton(
            dialog,
            text="Set as Default",
            variable=default_var,
            bg=self.colors.get('background'),
            fg=self.colors.get('foreground', 'white'),
            selectcolor=self.colors.get('panel_bg', '#444')
        ).pack()

        def confirm():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("Missing name", "Please enter a name.", parent=dialog)
                return

            try:
                if table == 'personas':
                    success = self.backend.save_persona(name, content[0], content[1], content[2], default_var.get())
                else:
                    success = self.backend.save_repository_item(table, name, content, default_var.get())
            except Exception as e:
                messagebox.showerror("Save failed", f"Unexpected error: {e}", parent=dialog)
                return

            if success:
                messagebox.showinfo("Success", "Saved successfully!", parent=dialog)
                dialog.destroy()
            else:
                messagebox.showerror("Save failed", "Could not save. Check the app log for the SQLite error.", parent=dialog)

        btn_frame = tk.Frame(dialog, bg=self.colors.get('background'))
        btn_frame.pack(pady=10)

        tk.Button(btn_frame, text="Save", width=10, command=confirm).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Cancel", width=10, command=dialog.destroy).pack(side='left', padx=5)

        dialog.bind("<Return>", lambda _e: confirm())
        dialog.bind("<Escape>", lambda _e: dialog.destroy())

    def _open_viewer(self, table, callback):
        """Opens the Universal Cell Viewer Modal with context-aware callbacks."""
        if table == 'personas':
            def persona_callback(data):
                self._update_widget(self.role_entry, data[0])
                self._update_widget(self.prompt_text, data[1])
                self._update_widget(self.input_box, data[2])
            callback = persona_callback
            
        CellViewerModal(self.shell.root, self.colors, table, self.backend, callback)

    def _open_settings(self):
        # Enforce singleton Settings modal
        if self._settings_window is not None:
            try:
                if self._settings_window.winfo_exists():
                    self._settings_window.deiconify()
                    self._settings_window.lift()
                    self._settings_window.focus_force()
                    return
            except Exception:
                self._settings_window = None

        settings = tk.Toplevel(self.shell.root)
        self._settings_window = settings
        settings.title("Settings")
        settings.geometry("350x250")
        settings.configure(bg=self.colors.get('background'))

        def _close_settings():
            self._settings_window = None
            try:
                settings.destroy()
            except Exception:
                pass

        settings.protocol("WM_DELETE_WINDOW", _close_settings)

        # Load persisted theme (default Dark)
        current_theme = (self.backend.get_setting('theme_preference') or 'Dark').strip().title()
        if current_theme not in ('Dark', 'Light'):
            current_theme = 'Dark'

        # Theme Section
        lbl_theme = tk.Label(settings, text="Theme:", bg=self.colors.get('background'), fg=self.colors.get('foreground', 'white'))
        lbl_theme.pack(pady=(15, 2))
        
        theme_var = tk.StringVar(value=current_theme)
        theme_cb = ttk.Combobox(settings, textvariable=theme_var, values=["Dark", "Light"], state='readonly')
        theme_cb.pack(pady=2)

        # Geometry Section
        lbl_size = tk.Label(settings, text="Window Size (WxH):", bg=self.colors.get('background'), fg=self.colors.get('foreground', 'white'))
        lbl_size.pack(pady=(15, 2))
        
        size_entry = tk.Entry(
            settings,
            bg=self.colors.get('entry_bg', self.colors.get('panel_bg')),
            fg=self.colors.get('entry_fg', self.colors.get('foreground')),
            insertbackground=self.colors.get('entry_fg', self.colors.get('foreground')),
            relief="flat"
        )
        current_geo = self.shell.root.geometry().split('+')[0]
        size_entry.insert(0, current_geo)
        size_entry.pack(pady=2)

        btn_frame = tk.Frame(settings, bg=self.colors.get('background'))
        btn_frame.pack(side='bottom', fill='x', pady=20)

        def apply_changes():
            # 1. Apply Geometry
            new_geo = size_entry.get().strip()
            if new_geo:
                try:
                    self.shell.root.geometry(new_geo)
                    self.backend.save_setting('window_geometry', new_geo)
                except Exception:
                    pass # Ignore invalid geometry strings

            # 2. Apply Theme
            selected_theme = (theme_var.get() or 'Dark').strip().title()
            if selected_theme not in ('Dark', 'Light'):
                selected_theme = 'Dark'

            self.backend.save_setting('theme_preference', selected_theme)
            if hasattr(self.shell, 'set_theme'):
                self.shell.set_theme(selected_theme)
                self.colors = self.shell.colors
                self.refresh_theme()
                
                # Refresh settings window colors immediately (including entry/button surfaces)
                settings.configure(bg=self.colors.get('background'))
                lbl_theme.configure(bg=self.colors.get('background'), fg=self.colors.get('foreground'))
                lbl_size.configure(bg=self.colors.get('background'), fg=self.colors.get('foreground'))
                btn_frame.configure(bg=self.colors.get('background'))

                try:
                    size_entry.configure(
                        bg=self.colors.get('entry_bg', self.colors.get('panel_bg')),
                        fg=self.colors.get('entry_fg', self.colors.get('foreground')),
                        insertbackground=self.colors.get('entry_fg', self.colors.get('foreground'))
                    )
                except Exception:
                    pass

                # Theme all buttons we created in this window
                try:
                    for w in container.winfo_children():
                        if isinstance(w, tk.Button):
                            w.configure(
                                bg=self.colors.get('panel_bg'),
                                fg=self.colors.get('button_fg', self.colors.get('foreground')),
                                activebackground=self.colors.get('panel_bg'),
                                activeforeground=self.colors.get('button_fg', self.colors.get('foreground'))
                            )
                except Exception:
                    pass

                # Recursive cleanup pass: remove any lingering OS-default surfaces
                try:
                    def _walk(w):
                        for child in w.winfo_children():
                            try:
                                if isinstance(child, (tk.Frame, tk.LabelFrame, tk.Toplevel)):
                                    child.configure(bg=self.colors.get('background'))
                                elif isinstance(child, tk.Label):
                                    child.configure(bg=self.colors.get('background'), fg=self.colors.get('foreground'))
                                elif isinstance(child, tk.Entry):
                                    child.configure(
                                        bg=self.colors.get('entry_bg', self.colors.get('panel_bg')),
                                        fg=self.colors.get('entry_fg', self.colors.get('foreground')),
                                        insertbackground=self.colors.get('entry_fg', self.colors.get('foreground'))
                                    )
                                elif isinstance(child, tk.Button):
                                    child.configure(
                                        bg=self.colors.get('panel_bg'),
                                        fg=self.colors.get('button_fg', self.colors.get('foreground')),
                                        activebackground=self.colors.get('panel_bg'),
                                        activeforeground=self.colors.get('button_fg', self.colors.get('foreground'))
                                    )
                            except Exception:
                                pass
                            _walk(child)
                    _walk(settings)
                except Exception:
                    pass

        def on_ok():
            apply_changes()
            _close_settings()

        # Buttons: Apply | OK | Cancel
        # We use pack with side to center them or space them out
        container = tk.Frame(btn_frame, bg=self.colors.get('background'))
        container.pack(anchor='center')

        btn_opts = {
            "bg": self.colors.get('panel_bg'), 
            "fg": self.colors.get('button_fg', self.colors.get('foreground')),
            "relief": "flat",
            "width": 8
        }

        tk.Button(container, text="Apply", command=apply_changes, **btn_opts).pack(side='left', padx=5)
        tk.Button(container, text="OK", command=on_ok, **btn_opts).pack(side='left', padx=5)
        tk.Button(container, text="Cancel", command=_close_settings, **btn_opts).pack(side='left', padx=5)

    def _build_context_menu(self):
        self.menu = tk.Menu(self.input_box, tearoff=0)
        self.menu.add_command(label="Cut", command=lambda: self.input_box.event_generate("<<Cut>>"))
        self.menu.add_command(label="Copy", command=lambda: self.input_box.event_generate("<<Copy>>"))
        self.menu.add_command(label="Paste", command=lambda: self.input_box.event_generate("<<Paste>>"))
        self.input_box.bind("<Button-3>", lambda e: self.menu.post(e.x_root, e.y_root))

    def _save_full_template(self):
        """Captures the entire state of the config bar as a bonded Persona."""
        role = self.role_entry.get()
        sys_p = self.prompt_text.get("1.0", "end-1c")
        task_p = self.input_box.get("1.0", "end-1c")
        self._save_repo_dialog('personas', (role, sys_p, task_p))

    def _restore_component_state(self):
        """Restores components using Defaults first, then Session state."""
        default_role = self.backend.get_default_item('saved_roles')
        last_role = self.backend.get_setting('last_system_role')
        self._update_widget(self.role_entry, default_role or last_role or "")

        default_sys = self.backend.get_default_item('saved_sys_prompts')
        last_sys = self.backend.get_setting('last_system_prompt')
        self._update_widget(self.prompt_text, default_sys or last_sys or "")

        last_model = self.backend.get_setting('last_model')
        if last_model in self.model_dropdown['values']:
            self.model_var.set(last_model)

    def _submit(self):
        """Process submission, persist parameters, and update UI consoles."""
        content = self.input_box.get("1.0", "end-1c")
        model = self.model_var.get()
        role = self.role_entry.get()
        prompt = self.prompt_text.get("1.0", "end-1c")
        
        # Persist settings via backend
        self.backend.save_setting('last_model', model)
        self.backend.save_setting('last_system_role', role)
        self.backend.save_setting('last_system_prompt', prompt)

        # Prepare Inference Log
        self.infer_log.configure(state='normal')
        self.infer_log.delete('1.0', 'end')
        self.infer_log.insert('1.0', f"[System] Initiating run with {model}...\n")
        self.infer_log.configure(state='disabled')

        # Prepare Result Box
        self.result_text.configure(state='normal')
        self.result_text.delete('1.0', 'end')
        self.result_text.insert('1.0', "Waiting for model response...\n")
        self.result_text.configure(state='disabled')
        
        # Trigger backend processing
        self.backend.process_submission(content, model, role, prompt)

    def refresh_theme(self, new_colors=None):
        """Re-applies the current theme to all primary UI widgets."""
        # Pull the newest palette. (If the shell swaps dict objects, this keeps us aligned.)
        self.colors = new_colors or self.shell.colors

        # Update Containers
        self.container.configure(bg=self.colors.get('background'))

        if self.main_row is not None:
            self.main_row.configure(bg=self.colors.get('background'))
        if self.left_col is not None:
            self.left_col.configure(bg=self.colors.get('background'))
        if self.right_col is not None:
            self.right_col.configure(bg=self.colors.get('background'))

        if self.panel_prompt is not None:
            self.panel_prompt.configure(bg=self.colors.get('background'))

        if self.action_frame is not None:
            self.action_frame.configure(bg=self.colors.get('background'))
        self.toolbar.configure(bg=self.colors.get('panel_bg'))
        self.config_frame.configure(fg=self.colors.get('foreground'), bg=self.colors.get('background'))
        self.role_inner.configure(bg=self.colors.get('background'))
        self.prompt_inner.configure(bg=self.colors.get('background'))
        self.prompt_btns_frame.configure(bg=self.colors.get('background'))

        if self.action_frame is not None:
            self.action_frame.configure(bg=self.colors.get('background'))

        # Right-column panels
        panel_list = [self.panel_inference, self.panel_result, self.panel_export]
        for panel in panel_list:
            if panel is not None:
                try:
                    panel.configure(
                        bg=self.colors.get('background'),
                        fg=self.colors.get('foreground'),
                        highlightbackground=self.colors.get('border')
                    )
                except Exception:
                    # Some Tk/ttk widgets may not accept fg/highlightbackground
                    try:
                        panel.configure(bg=self.colors.get('background'))
                    except Exception:
                        pass

        if self.export_router_frame is not None:
            self.export_router_frame.configure(bg=self.colors.get('background'))
            for child in self.export_router_frame.winfo_children():
                try:
                    child.configure(bg=self.colors.get('background'), fg=self.colors.get('foreground'))
                except Exception:
                    try:
                        child.configure(bg=self.colors.get('background'))
                    except Exception:
                        pass

        if self.export_options_frame is not None:
            self.export_options_frame.configure(bg=self.colors.get('background'))

        # Update Labels
        self.top_label.configure(fg=self.colors.get('foreground'), bg=self.colors.get('background'))
        if self.model_lbl is not None:
            self.model_lbl.configure(bg=self.colors.get('background'), fg=self.colors.get('foreground'))
        self.role_lbl.configure(bg=self.colors.get('background'), fg=self.colors.get('foreground'))
        self.prompt_lbl.configure(bg=self.colors.get('background'), fg=self.colors.get('foreground'))

        # Update Entries and Text widgets
        self.role_entry.configure(bg=self.colors.get('entry_bg'), fg=self.colors.get('entry_fg'), insertbackground=self.colors.get('entry_fg'))
        self.prompt_text.configure(bg=self.colors.get('entry_bg'), fg=self.colors.get('entry_fg'), insertbackground=self.colors.get('entry_fg'))
        self.input_box.configure(bg=self.colors.get('entry_bg'), fg=self.colors.get('entry_fg'), insertbackground=self.colors.get('entry_fg'), selectbackground=self.colors.get('select_bg'))

        # TTK STYLES: ttk widgets (Combobox/Treeview/etc.) won't pick up tk bg/fg changes.
        # If we don't restyle them, they can keep OS-default (often white) surfaces after a swap.
        try:
            style = ttk.Style()
            style.configure(
                "TCombobox",
                fieldbackground=self.colors.get('entry_bg', self.colors.get('panel_bg')),
                background=self.colors.get('panel_bg', self.colors.get('background')),
                foreground=self.colors.get('entry_fg', self.colors.get('foreground')),
                arrowcolor=self.colors.get('foreground')
            )
            style.map(
                "TCombobox",
                fieldbackground=[('readonly', self.colors.get('entry_bg', self.colors.get('panel_bg')))],
                foreground=[('readonly', self.colors.get('entry_fg', self.colors.get('foreground')))]
            )
        except Exception:
            pass

        # Panel 2/3 stubs
        if self.infer_log is not None:
            self.infer_log.configure(bg=self.colors.get('entry_bg'), fg=self.colors.get('entry_fg'), insertbackground=self.colors.get('entry_fg'))
        if self.result_text is not None:
            self.result_text.configure(bg=self.colors.get('entry_bg'), fg=self.colors.get('entry_fg'), insertbackground=self.colors.get('entry_fg'), selectbackground=self.colors.get('select_bg'))

        # Update Buttons (toolbar + small repo buttons)
        btn_list = [self.btn_bold, self.btn_italic, self.btn_list, self.btn_settings, self.btn_role_save, self.btn_role_open, self.btn_prompt_save, self.btn_prompt_open]
        for btn in btn_list:
            btn.configure(bg=self.colors.get('panel_bg'), fg=self.colors.get('foreground'))

        # Update Action Bar buttons
        if self.btn_save_template is not None:
            self.btn_save_template.configure(
                bg=self.colors.get('panel_bg'),
                fg=self.colors.get('button_fg', self.colors.get('foreground'))
            )
        if self.btn_load_template is not None:
            self.btn_load_template.configure(
                bg=self.colors.get('panel_bg'),
                fg=self.colors.get('button_fg', self.colors.get('foreground'))
            )
        if self.btn_submit is not None:
            self.btn_submit.configure(
                bg=self.colors.get('accent'),
                fg=self.colors.get('button_fg', self.colors.get('foreground'))
            )

        # HITL buttons
        if self.btn_accept is not None:
            self.btn_accept.configure(bg=self.colors.get('accent'), fg=self.colors.get('button_fg', 'white'))
        if self.btn_reject is not None:
            self.btn_reject.configure(bg=self.colors.get('button_bg', self.colors.get('panel_bg')), fg=self.colors.get('button_fg', self.colors.get('foreground')))
        if self.btn_exit is not None:
            self.btn_exit.configure(bg=self.colors.get('button_bg', self.colors.get('panel_bg')), fg=self.colors.get('button_fg', self.colors.get('foreground')))

        # Export buttons
        if self.export_execute_btn is not None:
            self.export_execute_btn.configure(bg=self.colors.get('accent'), fg=self.colors.get('button_fg', 'white'))





















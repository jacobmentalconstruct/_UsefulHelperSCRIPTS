import tkinter as tk
from tkinter import ttk, messagebox
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
            foreground=[('selected', colors.get('select_fg', '#ffffff'))]
        )
        self.tree = ttk.Treeview(self, columns=("ID", "Name", "Preview", "Default"), show='headings')
        
        for col in ("ID", "Name", "Preview", "Default"): 
            self.tree.heading(col, text=col)
            self.tree.column(col, width=50 if col in ('ID', 'Default') else 150 if col == 'Name' else 250)
        
        self.tree.pack(fill='both', expand=True, padx=10, pady=10)
        self._refresh_data()

        btn_frame = tk.Frame(self, bg=colors.get('background'))
        btn_frame.pack(fill='x', padx=10, pady=5)
        
        tk.Button(btn_frame, text="Load Selection", command=self._on_load).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Set as Default", command=self._on_default).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Delete", bg=colors.get('error', '#f44747'), fg="white", command=self._on_delete).pack(side='right', padx=5)

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
        
        # Restore window state from DB
        saved_geo = self.backend.get_setting('window_geometry')
        if saved_geo: self.shell.root.geometry(saved_geo)
        
        self._setup_main_window()
        self._build_context_menu()
        self._restore_component_state()

    def _setup_main_window(self):
        # --- Top Label ---
        self.top_label = tk.Label(self.container, text="Type in your idea HERE.", 
                 fg=self.colors.get('foreground'), bg=self.colors.get('background'),
                 font=("Segoe UI", 12, "bold"))
        self.top_label.pack(pady=(10, 5))

        # --- Formatting Toolbar ---
        self.toolbar = tk.Frame(self.container, bg=self.colors.get('panel_bg'))
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
        self.config_frame = tk.LabelFrame(self.container, text=" Inference Parameters ", 
                                     fg=self.colors.get('foreground'), bg=self.colors.get('background'))
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
            bg=self.colors.get('entry_bg', '#3c3c3c'),
            fg=self.colors.get('entry_fg', 'white'),
            insertbackground=self.colors.get('entry_fg', 'white')
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
            bg=self.colors.get('entry_bg', '#3c3c3c'),
            fg=self.colors.get('entry_fg', 'white'),
            insertbackground=self.colors.get('entry_fg', 'white'),
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
            self.container,
            undo=True,
            wrap="word",
            bg=self.colors.get('entry_bg', '#252526'),
            fg=self.colors.get('entry_fg', '#d4d4d4'),
            insertbackground=self.colors.get('entry_fg', 'white'),
            selectbackground=self.colors.get('select_bg', '#264f78'),
            font=("Consolas", 11)
        )
        self.input_box.pack(fill='both', expand=True, padx=10, pady=5)
        self.input_box.focus_set()

        # --- Action Bar ---
        action_frame = tk.Frame(self.container, bg=self.colors.get('background'))
        action_frame.pack(fill='x', padx=10, pady=(0, 10))

        self.btn_save_template = tk.Button(
            action_frame,
            text="SAVE AS TEMPLATE",
            bg=self.colors.get('panel_bg'),
            fg=self.colors.get('button_fg', self.colors.get('foreground', 'white')),
            font=("Segoe UI", 9),
            command=self._save_full_template
        )
        self.btn_save_template.pack(side='left', fill='x', expand=True, padx=(0, 2))

        self.btn_load_template = tk.Button(
            action_frame,
            text="LOAD TEMPLATE",
            bg=self.colors.get('panel_bg'),
            fg=self.colors.get('button_fg', self.colors.get('foreground', 'white')),
            font=("Segoe UI", 9),
            command=lambda: self._open_viewer('personas', None)
        )
        self.btn_load_template.pack(side='left', fill='x', expand=True, padx=(2, 5))

        self.btn_submit = tk.Button(
            action_frame,
            text="SUBMIT",
            bg=self.colors.get('accent', '#007acc'),
            fg="white",
            font=("Segoe UI", 10, "bold"),
            command=self._submit
        )
        self.btn_submit.pack(side='left', fill='x', expand=True)

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
            widget.delete('1.0', 'end')
            widget.insert('1.0', content)

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

        tk.Button(dialog, text="Save", command=confirm).pack(pady=10)
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

        tk.Label(settings, text="Theme:", bg=self.colors.get('background'), fg=self.colors.get('foreground', 'white')).pack(pady=(10,0))
        theme_var = tk.StringVar(value=current_theme)
        theme_cb = ttk.Combobox(settings, textvariable=theme_var, values=["Dark", "Light"], state='readonly')
        theme_cb.pack()

        tk.Label(settings, text="Window Size (WxH):", bg=self.colors.get('background'), fg=self.colors.get('foreground', 'white')).pack(pady=(10,0))
        size_entry = tk.Entry(settings)
        size_entry.insert(0, self.shell.root.geometry().split('+')[0])
        size_entry.pack()

        btn_frame = tk.Frame(settings, bg=self.colors.get('background'))
        btn_frame.pack(pady=20)

        def save():
            new_geo = size_entry.get()
            self.shell.root.geometry(new_geo)
            self.backend.save_setting('window_geometry', new_geo)

            selected_theme = (theme_var.get() or 'Dark').strip().title()
            if selected_theme not in ('Dark', 'Light'):
                selected_theme = 'Dark'

            # Persist + apply via shell microservice
            self.backend.save_setting('theme_preference', selected_theme)
            if hasattr(self.shell, 'set_theme'):
                self.shell.set_theme(selected_theme)
                # UI reads from shell.colors
                self.colors = self.shell.colors
                self.refresh_theme()

            _close_settings()

        tk.Button(btn_frame, text="Accept", command=save, width=10).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Cancel", command=_close_settings, width=10).pack(side='left', padx=5)

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
        """Process submission and persist current parameters."""
        content = self.input_box.get("1.0", "end-1c")
        model = self.model_var.get()
        role = self.role_entry.get()
        prompt = self.prompt_text.get("1.0", "end-1c")
        
        self.backend.save_setting('last_model', model)
        self.backend.save_setting('last_system_role', role)
        self.backend.save_setting('last_system_prompt', prompt)
        
        self.backend.process_submission(content, model, role, prompt)

    def refresh_theme(self):
        """Re-applies the current shell colors to all primary UI widgets."""
        self.colors = self.shell.colors

        # Update Containers
        self.container.configure(bg=self.colors.get('background'))
        self.toolbar.configure(bg=self.colors.get('panel_bg'))
        self.config_frame.configure(fg=self.colors.get('foreground'), bg=self.colors.get('background'))
        self.role_inner.configure(bg=self.colors.get('background'))
        self.prompt_inner.configure(bg=self.colors.get('background'))
        self.prompt_btns_frame.configure(bg=self.colors.get('background'))

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
                bg=self.colors.get('accent', '#007acc'),
                fg='white'
            )




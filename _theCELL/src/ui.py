import tkinter as tk
from tkinter import ttk, messagebox

class CELL_UI:
    def __init__(self, shell, backend):
        self.shell = shell
        self.backend = backend
        self.container = shell.get_main_container() # [cite: 104]
        self.colors = shell.colors # [cite: 102]
        
        self._setup_main_window()
        self._build_context_menu()

    def _setup_main_window(self):
        # --- Top Label ---
        tk.Label(self.container, text="Type in your idea HERE.", 
                 fg=self.colors.get('foreground'), bg=self.colors.get('background'),
                 font=("Segoe UI", 12, "bold")).pack(pady=(10, 5))

        # --- Formatting Toolbar ---
        toolbar = tk.Frame(self.container, bg=self.colors.get('panel_bg'))
        toolbar.pack(fill='x', padx=10)
        
        btn_opts = {"bg": self.colors.get('panel_bg'), "fg": "white", "relief": "flat", "padx": 5}
        tk.Button(toolbar, text="B", font=("TkDefaultFont", 9, "bold"), **btn_opts, command=self._bold_text).pack(side='left')
        tk.Button(toolbar, text="I", font=("TkDefaultFont", 9, "italic"), **btn_opts, command=self._italic_text).pack(side='left')
        tk.Button(toolbar, text="• List", **btn_opts, command=self._bullet_list).pack(side='left')
        
        tk.Button(toolbar, text="⚙", **btn_opts, command=self._open_settings).pack(side='right')

        # --- Inference Config Section ---
        config_frame = tk.LabelFrame(self.container, text=" Inference Parameters ", 
                                     fg=self.colors.get('foreground'), bg=self.colors.get('background'))
        config_frame.pack(fill='x', padx=10, pady=10)

        # Model Selection
        tk.Label(config_frame, text="Model:", bg=self.colors.get('background'), fg="white").grid(row=0, column=0, sticky='w', padx=5)
        self.model_var = tk.StringVar()
        self.model_dropdown = ttk.Combobox(config_frame, textvariable=self.model_var)
        self.model_dropdown['values'] = self.backend.get_models()
        self.model_dropdown.grid(row=0, column=1, sticky='ew', padx=5, pady=2)

        # Direct Role Input
        tk.Label(config_frame, text="System Role:", bg=self.colors.get('background'), fg="white").grid(row=1, column=0, sticky='w', padx=5)
        self.role_entry = tk.Entry(config_frame, bg="#3c3c3c", fg="white", insertbackground="white")
        self.role_entry.insert(0, self.backend.system_role)
        self.role_entry.grid(row=1, column=1, sticky='ew', padx=5, pady=2)

        # Direct Prompt Input
        tk.Label(config_frame, text="System Prompt:", bg=self.colors.get('background'), fg="white").grid(row=2, column=0, sticky='nw', padx=5)
        self.prompt_text = tk.Text(config_frame, height=3, bg="#3c3c3c", fg="white", insertbackground="white", font=("Segoe UI", 9))
        self.prompt_text.grid(row=2, column=1, sticky='ew', padx=5, pady=2)

        config_frame.columnconfigure(1, weight=1)

        # --- Main Input Box ---
        self.input_box = tk.Text(self.container, undo=True, wrap="word",
                                 bg="#252526", fg="#d4d4d4", 
                                 insertbackground="white",
                                 selectbackground="#264f78",
                                 font=("Consolas", 11))
        self.input_box.pack(fill='both', expand=True, padx=10, pady=5)
        self.input_box.focus_set()

        # --- Submit Button ---
        tk.Button(self.container, text="SUBMIT", bg="#007acc", fg="white", 
                  font=("Segoe UI", 10, "bold"), command=self._submit).pack(fill='x', padx=10, pady=(0, 10))

            # --- UI Logic Stubs ---
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

    def _open_settings(self):
        settings = tk.Toplevel(self.shell.root)
        settings.title("Settings")
        settings.geometry("350x250")
        settings.configure(bg=self.colors.get('background'))

        tk.Label(settings, text="Theme:", bg=self.colors.get('background'), fg="white").pack(pady=(10,0))
        theme_var = tk.StringVar(value="Dark")
        theme_cb = ttk.Combobox(settings, textvariable=theme_var, values=["Dark", "Light"])
        theme_cb.pack()

        tk.Label(settings, text="Window Size (WxH):", bg=self.colors.get('background'), fg="white").pack(pady=(10,0))
        size_entry = tk.Entry(settings)
        size_entry.insert(0, self.shell.root.geometry().split('+')[0])
        size_entry.pack()

        btn_frame = tk.Frame(settings, bg=self.colors.get('background'))
        btn_frame.pack(pady=20)

        def save():
            # Apply logic for theme and geometry here
            self.shell.root.geometry(size_entry.get())
            settings.destroy()

        tk.Button(btn_frame, text="Accept", command=save, width=10).pack(side='left', padx=5)
        tk.Button(btn_frame, text="Cancel", command=settings.destroy, width=10).pack(side='left', padx=5)


    def _build_context_menu(self):
        self.menu = tk.Menu(self.input_box, tearoff=0)
        self.menu.add_command(label="Cut", command=lambda: self.input_box.event_generate("<<Cut>>"))
        self.menu.add_command(label="Copy", command=lambda: self.input_box.event_generate("<<Copy>>"))
        self.menu.add_command(label="Paste", command=lambda: self.input_box.event_generate("<<Paste>>"))
        self.input_box.bind("<Button-3>", lambda e: self.menu.post(e.x_root, e.y_root))

    def _submit(self):
        content = self.input_box.get("1.0", "end-1c")
        model = self.model_var.get()
        role = self.role_entry.get()
        prompt = self.prompt_text.get("1.0", "end-1c")
        self.backend.process_submission(content, model, role, prompt)




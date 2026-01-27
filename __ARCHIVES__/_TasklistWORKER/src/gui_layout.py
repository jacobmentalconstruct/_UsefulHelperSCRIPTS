import tkinter as tk
from tkinter import ttk, scrolledtext

class WorkbenchUI:
    def __init__(self, root):
        self.root = root
        self.root.title("_CognitiveWORKBENCH v5.1 [Scaffolded]")
        self.root.geometry("1900x1000")
        self.root.configure(bg="#0f172a")
        
        self.widgets = {}
        self._setup_styles()
        self._build_layout()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#0f172a")
        style.configure("TLabel", background="#1e293b", foreground="#e2e8f0")
        style.configure("TButton", background="#334155", foreground="white", borderwidth=0)
        style.map("TButton", background=[('active', '#475569')])
        style.configure("Card.TFrame", background="#1e293b", relief="flat")
        
        # Log Panel
        style.configure("Log.TFrame", background="#020617", borderwidth=2, relief="sunken")
        
        # Notebook (Tabs)
        style.configure("TNotebook", background="#0f172a", borderwidth=0)
        style.configure("TNotebook.Tab", background="#334155", foreground="white", padding=[10, 5], font=("Segoe UI", 9))
        style.map("TNotebook.Tab", background=[("selected", "#1e293b")], foreground=[("selected", "#60a5fa")])

    def _build_layout(self):
        # Master Vertical Paned Window
        self.main_split = tk.PanedWindow(self.root, orient=tk.VERTICAL, bg="#0f172a", sashwidth=6)
        self.main_split.pack(fill="both", expand=True)

        # --- UPPER SECTION: 3-COLUMNS ---
        self.paned_cols = tk.PanedWindow(self.main_split, orient=tk.HORIZONTAL, bg="#0f172a", sashwidth=6)
        self.main_split.add(self.paned_cols, stretch="always", minsize=600)

        # === COL 1: SUBCONSCIOUS (Left) ===
        self.f_left = tk.Frame(self.paned_cols, bg="#020617")
        self.paned_cols.add(self.f_left, minsize=350, stretch="always")
        
        h_left = tk.Frame(self.f_left, bg="#020617", pady=5)
        h_left.pack(fill="x")
        tk.Label(h_left, text="⚡ SUBCONSCIOUS", bg="#020617", fg="#64748b", font=("Segoe UI", 9, "bold")).pack(side="left", padx=5)
        
        self.cb_helper = ttk.Combobox(h_left, state="readonly", width=25)
        self.cb_helper.pack(side="right", padx=5)
        self.widgets["cb_helper"] = self.cb_helper
        
        self.txt_thoughts = scrolledtext.ScrolledText(self.f_left, bg="#020617", fg="#94a3b8", borderwidth=0, font=("Consolas", 9))
        self.txt_thoughts.pack(fill="both", expand=True, padx=5)
        self.widgets["thoughts"] = self.txt_thoughts

        f_left_foot = tk.Frame(self.f_left, bg="#1e293b", height=40)
        f_left_foot.pack(side="bottom", fill="x")
        self.btn_settings = tk.Button(f_left_foot, text="⚙ Settings / Embedder", bg="#1e293b", fg="#94a3b8", relief="flat")
        self.btn_settings.pack(side="left", padx=10, pady=5)
        self.widgets["btn_settings"] = self.btn_settings

        # === COL 2: SESSION LTM (Center) ===
        self.f_center = tk.Frame(self.paned_cols, bg="#0f172a")
        self.paned_cols.add(self.f_center, minsize=600, stretch="always")

        h_center = tk.Frame(self.f_center, bg="#1e293b", height=50)
        h_center.pack(fill="x")
        tk.Label(h_center, text="SESSION", bg="#1e293b", fg="white", font=("Segoe UI", 11, "bold")).pack(side="left", padx=10)
        
        tk.Label(h_center, text="Chat Model:", bg="#1e293b", fg="#94a3b8").pack(side="left", padx=(15, 5))
        self.cb_chat_model = ttk.Combobox(h_center, state="readonly", width=30)
        self.cb_chat_model.pack(side="left")
        self.widgets["cb_chat_model"] = self.cb_chat_model

        # Session Role Controls
        f_role_sess = tk.Frame(h_center, bg="#1e293b")
        f_role_sess.pack(side="left", padx=15)
        tk.Label(f_role_sess, text="Role:", bg="#1e293b", fg="#94a3b8").pack(side="left")
        self.cb_chat_role = ttk.Combobox(f_role_sess, state="readonly", width=20)
        self.cb_chat_role.pack(side="left", padx=2)
        self.widgets["cb_chat_role"] = self.cb_chat_role
        
        self.btn_add_role_chat = tk.Button(f_role_sess, text="+", bg="#334155", fg="white", width=3)
        self.btn_add_role_chat.pack(side="left")
        self.widgets["btn_add_role_chat"] = self.btn_add_role_chat

        self.btn_onboard = tk.Button(h_center, text="Catch Me Up", bg="#2563eb", fg="white", font=("Segoe UI", 9))
        self.btn_onboard.pack(side="right", padx=10)
        self.widgets["btn_onboard"] = self.btn_onboard

        self.txt_session = scrolledtext.ScrolledText(self.f_center, bg="#0f172a", fg="#e2e8f0", borderwidth=0, font=("Segoe UI", 10), insertbackground="white")
        self.txt_session.pack(fill="both", expand=True, padx=10, pady=(10, 0))
        self.widgets["session_log"] = self.txt_session

        f_chat_input = tk.Frame(self.f_center, bg="#1e293b", pady=5, padx=5)
        f_chat_input.pack(fill="x", padx=10, pady=10)
        
        self.txt_chat_input = tk.Text(f_chat_input, height=4, bg="#0f172a", fg="white", borderwidth=0, font=("Segoe UI", 10), insertbackground="white")
        self.txt_chat_input.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.widgets["chat_input"] = self.txt_chat_input
        
        self.btn_send_chat = tk.Button(f_chat_input, text="SEND ➤", bg="#16a34a", fg="white", font=("Segoe UI", 10, "bold"), width=10)
        self.btn_send_chat.pack(side="right", fill="y")
        self.widgets["btn_send_chat"] = self.btn_send_chat

        # === COL 3: WORKFLOW (Right) - NOW TABBED ===
        self.f_right_container = tk.Frame(self.paned_cols, bg="#1e293b")
        self.paned_cols.add(self.f_right_container, minsize=550, stretch="always")

        # The Notebook
        self.notebook = ttk.Notebook(self.f_right_container)
        self.notebook.pack(fill="both", expand=True, padx=5, pady=5)

        # -- TAB 1: EXECUTION (The Active Workbench) --
        self.tab_exec = tk.Frame(self.notebook, bg="#1e293b")
        self.notebook.add(self.tab_exec, text=" ▶ Execution ")
        self._build_execution_tab(self.tab_exec)

        # -- TAB 2: TASKLISTS (Manager) --
        self.tab_tasks = tk.Frame(self.notebook, bg="#0f172a")
        self.notebook.add(self.tab_tasks, text=" Tasklists ")
        tk.Label(self.tab_tasks, text="Tasklist Manager / Engineering (Coming Soon)", bg="#0f172a", fg="#475569").pack(expand=True)

        # -- TAB 3: PROMPTS (Manager) --
        self.tab_prompts = tk.Frame(self.notebook, bg="#0f172a")
        self.notebook.add(self.tab_prompts, text=" Prompts ")
        tk.Label(self.tab_prompts, text="Prompt Engineering Library (Coming Soon)", bg="#0f172a", fg="#475569").pack(expand=True)

        # -- TAB 4: CARTRIDGES (Manager) --
        self.tab_carts = tk.Frame(self.notebook, bg="#0f172a")
        self.notebook.add(self.tab_carts, text=" Cartridges ")
        tk.Label(self.tab_carts, text="RAG Cartridge Manager (Coming Soon)", bg="#0f172a", fg="#475569").pack(expand=True)

        # --- LOWER SECTION: SYSTEM LOG ---
        self.f_log = ttk.Frame(self.main_split, style="Log.TFrame")
        self.main_split.add(self.f_log, minsize=150, stretch="never")
        
        # Log Content (Top)
        self.txt_log = scrolledtext.ScrolledText(self.f_log, height=8, bg="#020617", fg="#475569", font=("Consolas", 9), borderwidth=0)
        self.txt_log.pack(fill="both", expand=True, side="top")
        self.widgets["log_console"] = self.txt_log

        # Log Toolbar (Bottom)
        f_log_ctrl = tk.Frame(self.f_log, bg="#0f172a", height=25)
        f_log_ctrl.pack(side="bottom", fill="x")
        
        tk.Label(f_log_ctrl, text="SYSTEM LOG", bg="#0f172a", fg="#64748b", font=("Segoe UI", 8, "bold")).pack(side="left", padx=5)
        
        self.btn_log_save = tk.Button(f_log_ctrl, text="💾 Save Log", bg="#334155", fg="white", font=("Segoe UI", 8))
        self.btn_log_save.pack(side="right", padx=2, pady=2)
        self.widgets["btn_log_save"] = self.btn_log_save
        
        self.btn_log_config = tk.Button(f_log_ctrl, text="⚙ Config", bg="#334155", fg="white", font=("Segoe UI", 8))
        self.btn_log_config.pack(side="right", padx=2, pady=2)
        self.widgets["btn_log_config"] = self.btn_log_config

    def _build_execution_tab(self, parent):
        # Header
        h_right = tk.Frame(parent, bg="#334155", height=45)
        h_right.pack(fill="x")
        tk.Label(h_right, text="WORKBENCH", bg="#334155", fg="white", font=("Segoe UI", 10, "bold")).pack(side="left", padx=10)
        
        tk.Label(h_right, text="Task Model:", bg="#334155", fg="#cbd5e1").pack(side="left", padx=(15, 5))
        self.cb_task_model = ttk.Combobox(h_right, state="readonly", width=30)
        self.cb_task_model.pack(side="left")
        self.widgets["cb_task_model"] = self.cb_task_model

        self.btn_cartridge = tk.Button(h_right, text="📦 Make Cartridge", bg="#475569", fg="white")
        self.btn_cartridge.pack(side="right", padx=5)
        self.widgets["btn_cartridge"] = self.btn_cartridge

        # Task Steps Editor
        self.canvas_tasks = tk.Canvas(parent, bg="#1e293b", highlightthickness=0)
        self.scroll_tasks = ttk.Scrollbar(parent, orient="vertical", command=self.canvas_tasks.yview)
        self.frame_tasks_inner = tk.Frame(self.canvas_tasks, bg="#1e293b")
        
        self.canvas_tasks.create_window((0, 0), window=self.frame_tasks_inner, anchor="nw")
        self.canvas_tasks.configure(yscrollcommand=self.scroll_tasks.set)
        
        self.canvas_tasks.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        self.scroll_tasks.pack(side="right", fill="y", in_=parent)
        self.frame_tasks_inner.bind("<Configure>", lambda e: self.canvas_tasks.configure(scrollregion=self.canvas_tasks.bbox("all")))
        self.widgets["task_container"] = self.frame_tasks_inner

        # Action Area
        f_action = tk.Frame(parent, bg="#0f172a", pady=10, padx=10)
        f_action.pack(side="bottom", fill="x")

        tk.Label(f_action, text="STAGING (Output Buffer)", bg="#0f172a", fg="#facc15", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.txt_staging = tk.Text(f_action, height=10, bg="#1e293b", fg="white", borderwidth=1, relief="solid", insertbackground="white")
        self.txt_staging.pack(fill="x", pady=(5, 5))
        self.widgets["staging"] = self.txt_staging

        f_btns = tk.Frame(f_action, bg="#0f172a")
        f_btns.pack(fill="x")
        
        self.btn_add_step = tk.Button(f_btns, text="+ Step", bg="#334155", fg="white")
        self.btn_add_step.pack(side="left", padx=(0, 5))
        self.widgets["btn_add_step"] = self.btn_add_step

        self.btn_inject = tk.Button(f_btns, text="↙ Inject to Chat", bg="#0f766e", fg="white", state="disabled")
        self.btn_inject.pack(side="left", padx=5)
        self.widgets["btn_inject"] = self.btn_inject
        
        tk.Frame(f_btns, bg="#0f172a").pack(side="left", expand=True)

        self.btn_run = tk.Button(f_btns, text="RUN STEP ➡", bg="#2563eb", fg="white", font=("Segoe UI", 10, "bold"), width=15)
        self.btn_run.pack(side="right")
        self.widgets["btn_run"] = self.btn_run

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import json
import os
import sys
import datetime
import requests

# --- CRITICAL PATH RESOLUTION ---
# Since we run via 'python -m src.app', we must find the repo root for microservices/
_current_dir = os.path.dirname(os.path.abspath(__file__))
_root_dir = os.path.abspath(os.path.join(_current_dir, ".."))
if _root_dir not in sys.path:
    sys.path.insert(0, _root_dir)
# --------------------------------

# --- INTEGRATED MICROSERVICES ---
# sys.path injection above guarantees root-relative imports
from microservices._ToolsMS import MicroserviceTools

# =========================================================
# 1. CORE CLIENTS
# =========================================================

class OllamaClient:
    """Manages local inference via Ollama."""
    def list_models(self):
        try:
            res = requests.get("http://localhost:11434/api/tags", timeout=2)
            if res.status_code == 200:
                return [m["name"] for m in res.json().get("models", [])]
        except Exception:
            pass
        return ["qwen2.5:7b-instruct", "qwen2.5:7b-coder", "qwen2.5:1.5b"]

    def generate(self, model, system, prompt):
        url = "http://localhost:11434/api/chat"
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.2}
        }
        res = requests.post(url, json=payload, timeout=60)
        res.raise_for_status()
        return res.json()['message']['content']

class RoleManager:
    """Defines personas for the AI or signals for mechanical tools."""
    def __init__(self):
        self.roles = {
            "Helpful Assistant": "You are a helpful AI assistant.",
            "Python Expert": "You are a senior Python developer. Output code only.",
            "Strict Analyst": "You are a logic-first analyst. Output raw JSON only.",
            "Mechanical Tool": "EXECUTE_TOOL" # Special signal for _ToolsMS
        }
    def get_names(self): return list(self.roles.keys())
    def get_prompt(self, name): return self.roles.get(name, "")

# =========================================================
# 2. UI COMPONENTS
# =========================================================

class TaskStepController(tk.Frame):
    """A single row in the iterative task list."""
    def __init__(self, parent, index, app_ref, role_mgr):
        super().__init__(parent, bg="#1e293b", bd=1, relief="flat", pady=2)
        self.app = app_ref
        self.index = index
        self.role_mgr = role_mgr
        self.data = {"role": "Helpful Assistant", "prompt": ""}
        self._build_ui()

    def _build_ui(self):
        self.lbl_idx = tk.Label(self, text=f"#{self.index+1}", bg="#1e293b", fg="#94a3b8", width=3)
        self.lbl_idx.pack(side="left")

        self.cb_role = ttk.Combobox(self, values=self.role_mgr.get_names(), state="readonly", width=18)
        self.cb_role.pack(side="left", padx=5)
        self.cb_role.set(self.data["role"])
        self.cb_role.bind("<<ComboboxSelected>>", self._sync)

        self.txt_prompt = tk.Entry(self, bg="#0f172a", fg="white", insertbackground="white", borderwidth=0)
        self.txt_prompt.pack(side="left", fill="x", expand=True, padx=5)
        self.txt_prompt.bind("<FocusOut>", self._sync)
        self.txt_prompt.bind("<Return>", self._run_step_from_enter)
        self.txt_prompt.bind("<KP_Enter>", self._run_step_from_enter)

        tk.Button(self, text="▶", command=lambda: self.app.run_step(self.index), 
                  bg="#3b82f6", fg="white", font=("Arial", 9, "bold")).pack(side="right", padx=5)

    def _sync(self, e=None):
        self.data["role"] = self.cb_role.get()
        self.data["prompt"] = self.txt_prompt.get()

    def _run_step_from_enter(self, e=None):
        """Enter key runs this step."""
        self._sync()
        self.app.run_step(self.index)
        return "break"

# =========================================================
# 3. MAIN WORKBENCH APPLICATION
# =========================================================

class WorkbenchApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Systems Thinker: Microservice Transformer")
        self.geometry("1200x800")
        self.configure(bg="#0f172a")

        self.client = OllamaClient()
        self.roles = RoleManager()
        self.steps = []
        self.state = {"last_response": "", "current_file": ""}

        # RUN-ALL state
        self._run_all_active = False
        self._run_all_index = 0

        # Initialize ToolsMS pointing to the repo root so it can find std_lib and base_service
        self.tools_engine = MicroserviceTools(_root_dir)
        self.recipe_path = tk.StringVar()

        self._build_ui()
        self.log("Workbench Ready. Tooling Cartridge initialized.")

    def _build_ui(self):
        # Top Config
        top = tk.Frame(self, bg="#1e293b", pady=10)
        top.pack(fill="x")
        
        tk.Label(top, text="TARGET DIR:", bg="#1e293b", fg="white").pack(side="left", padx=(10, 5))
        self.ent_dir = tk.Entry(top, width=50, bg="#0f172a", fg="white")
        self.ent_dir.insert(0, os.getcwd())
        self.ent_dir.pack(side="left", padx=5)
        tk.Button(top, text="Browse", command=self._browse).pack(side="left")

        tk.Label(top, text="FILE:", bg="#1e293b", fg="#fbbf24").pack(side="left", padx=(15, 5))
        self.ent_file = tk.Entry(top, width=20, bg="#0f172a", fg="white")
        self.ent_file.insert(0, "dirty_service.py")
        self.ent_file.pack(side="left", padx=5)

        self.var_test_mode = tk.BooleanVar(value=True)
        tk.Checkbutton(top, text="TEST MODE (SANDBOX)", variable=self.var_test_mode, 
                       bg="#1e293b", fg="#f87171", selectcolor="#0f172a").pack(side="left", padx=10)

        self.cb_model = ttk.Combobox(top, values=self.client.list_models(), width=25)
        self.cb_model.pack(side="right", padx=10)
        if self.cb_model['values']: self.cb_model.set(self.cb_model['values'][0])
        tk.Label(top, text="MODEL:", bg="#1e293b", fg="white").pack(side="right")

        # Layout
        main_panes = tk.PanedWindow(self, orient="horizontal", bg="#0f172a", sashwidth=4)
        main_panes.pack(fill="both", expand=True)

        # Left: Task Recipe
        left_frame = tk.Frame(main_panes, bg="#0f172a")
        main_panes.add(left_frame, width=500)
        
        tk.Label(left_frame, text="ITERATIVE TASK LIST", bg="#0f172a", fg="#3b82f6", font=("Arial", 10, "bold")).pack(pady=5)
        self.step_container = tk.Frame(left_frame, bg="#0f172a")
        self.step_container.pack(fill="both", expand=True, padx=5)
        
        f_recipe_actions = tk.Frame(left_frame, bg="#0f172a")
        f_recipe_actions.pack(fill="x", side="bottom", pady=5, padx=5)
        
        tk.Button(f_recipe_actions, text="LOAD RECIPE", command=self.load_tasklist, bg="#1e293b", fg="#3b82f6").pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(f_recipe_actions, text="SAVE RECIPE", command=self.save_tasklist, bg="#1e293b", fg="#10b981").pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(f_recipe_actions, text="RUN ALL", command=self.run_all_steps, bg="#1e293b", fg="#fbbf24").pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(left_frame, text="+ ADD STEP", command=self.add_step, bg="#334155", fg="white").pack(fill="x", pady=(5, 0), padx=5)

        # Right: Response & Log
        right_panes = tk.PanedWindow(main_panes, orient="vertical", bg="#0f172a")
        main_panes.add(right_panes)

        self.txt_response = scrolledtext.ScrolledText(right_panes, bg="#1e1e1e", fg="white", font=("Consolas", 10))
        right_panes.add(self.txt_response, height=450)

        self.txt_log = scrolledtext.ScrolledText(right_panes, bg="#000000", fg="#00ff00", font=("Consolas", 9))
        right_panes.add(self.txt_log)

        # Initial Default Steps
        self.add_step("Mechanical Tool", "scan_file_structure")
        self.add_step("Strict Analyst", "Analyze the AST and plan migration.")

    def log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")

        def _do_log():
            self.txt_log.insert("end", f"[{ts}] {msg}\n")
            self.txt_log.see("end")

        # Tkinter widgets must only be touched from the main/UI thread
        if threading.current_thread() is threading.main_thread():
            _do_log()
        else:
            self.after(0, _do_log)

    def _browse(self):
        d = filedialog.askdirectory()
        if d:
            self.ent_dir.delete(0, "end")
            self.ent_dir.insert(0, d)
            # Keep ToolsMS anchored to repo root (not the selected working dir)
            self.tools_engine = MicroserviceTools(_root_dir)

    def add_step(self, role=None, prompt=None):
        s = TaskStepController(self.step_container, len(self.steps), self, self.roles)
        if role: s.cb_role.set(role)
        if prompt: s.txt_prompt.insert(0, prompt)
        s.pack(fill="x", pady=1)
        self.steps.append(s)

    def save_tasklist(self):
        """Export current steps to JSON recipe."""
        recipe = []
        for s in self.steps:
            s._sync()
            recipe.append(s.data)
        
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON Recipe", "*.json")])
        if path:
            with open(path, "w") as f:
                json.dump(recipe, f, indent=2)
            self.log(f"Recipe saved to {os.path.basename(path)}")

    def load_tasklist(self):
        """Import steps from JSON recipe."""
        path = filedialog.askopenfilename(filetypes=[("JSON Recipe", "*.json")])
        if path:
            with open(path, "r") as f:
                recipe = json.load(f)
            
            # Clear existing steps
            for s in self.steps: s.destroy()
            self.steps = []
            
            for item in recipe:
                self.add_step(item.get("role"), item.get("prompt"))
            self.log(f"Loaded {len(recipe)} steps from {os.path.basename(path)}")

    def run_step(self, idx):
        step = self.steps[idx]
        step._sync()
        role = step.data["role"]
        prompt = step.data["prompt"]
        
        self.log(f"Initiating Step #{idx+1} ({role})")
        
        if role == "Mechanical Tool":
            threading.Thread(target=self._tool_worker, args=(prompt,), daemon=True).start()
        else:
            model = self.cb_model.get()
            sys_p = self.roles.get_prompt(role)
            # Inject history context
            full_p = f"{prompt}\n\n[LAST_OUTPUT]:\n{self.state['last_response']}"
            threading.Thread(target=self._ai_worker, args=(model, sys_p, full_p), daemon=True).start()

    def run_all_steps(self):
        """Run steps sequentially. Stops on detected failure."""
        if self._run_all_active:
            self.log("RUN ALL already active.")
            return

        if not self.steps:
            self.log("No steps to run.")
            return

        self._run_all_active = True
        self._run_all_index = 0
        self.log("RUN ALL started.")
        self.run_step(self._run_all_index)

    def _is_failure_output(self, content: str) -> bool:
        """Best-effort failure detection across tool + AI outputs."""
        if not content:
            return False

        # Common explicit signals
        lowered = content.lower()
        if "tool error" in lowered or "ai error" in lowered:
            return True

        # JSON outputs from tools often include success/error
        try:
            obj = json.loads(content)
            if isinstance(obj, dict):
                if obj.get("success") is False:
                    return True
                if "error" in obj and obj.get("error"):
                    return True
                if obj.get("message") and isinstance(obj.get("message"), str) and "error" in obj.get("message").lower():
                    return True
        except Exception:
            pass

        # Plain-text errors
        if lowered.strip().startswith("error:"):
            return True

        return False

    def _run_all_advance(self):
        """Called after a step finishes (from _update_output)."""
        if not self._run_all_active:
            return

        # Stop if last output looks like a failure
        if self._is_failure_output(self.state.get("last_response", "")):
            self.log(f"RUN ALL stopped on failure at step #{self._run_all_index + 1}.")
            self._run_all_active = False
            return

        # Next step
        self._run_all_index += 1
        if self._run_all_index >= len(self.steps):
            self.log("RUN ALL complete.")
            self._run_all_active = False
            return

        self.run_step(self._run_all_index)

    def _tool_worker(self, cmd):
        target_dir = self.ent_dir.get()
        original_file = self.ent_file.get()

        # SANDBOX LOGIC: If test mode is on, we work on a copy
        if self.var_test_mode.get():
            sandbox_file = f"TEST_{original_file}"
            source_path = os.path.join(target_dir, original_file)
            dest_path = os.path.join(target_dir, sandbox_file)

            # Create sandbox copy if it doesn't exist yet
            if not os.path.exists(dest_path) and os.path.exists(source_path):
                import shutil
                shutil.copy2(source_path, dest_path)
                self.log(f"[SANDBOX] Created test file: {sandbox_file}")
            target_file = sandbox_file
        else:
            target_file = original_file

        try:
            # 1. DIRECTORY BACKUP
            if cmd == "create_backup":
                import shutil
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                backup_path = os.path.join(os.path.dirname(target_dir), f"BACKUP_{ts}")
                shutil.copytree(target_dir, backup_path)
                res = {"success": True, "message": f"Backup created: {backup_path}"}

            # 2. READ TEMPLATE (Boilerplate)
            elif cmd == "read_template":
                # Use repository root (where microservices/ actually resides)
                template_path = os.path.join(_root_dir, "microservices", "microservice_template.py")
                if os.path.exists(template_path):
                    with open(template_path, "r", encoding="utf-8") as f:
                        res = f.read()
                else:
                    res = {"success": False, "message": f"Error: Template not found at {template_path}"}

            # 3. MECHANICAL ANALYSIS (AST)
            elif cmd == "scan_file_structure":
                res = self.tools_engine.scan_file_structure(target_file)

            # 4. PATCHING (Surgeon)
            elif cmd == "apply_safe_patch":
                res = self.tools_engine.apply_patch(target_file, self.state["last_response"], dry_run=False)

            # 5. CLEANUP PATCH GENERATOR
            elif cmd == "get_cleanup_patch":
                res = self.tools_engine.generate_cleanup_patch()

            else:
                res = {"success": False, "message": f"Error: Tool '{cmd}' not recognized."}

        except Exception as e:
            self.log(f"TOOL ERROR: {e}")
            res = {"success": False, "message": f"TOOL ERROR: {e}"}

        output = json.dumps(res, indent=2) if isinstance(res, (dict, list)) else str(res)
        self._update_output(output, f"Tool '{cmd}' completed.")

    def _ai_worker(self, model, sys, prompt):
        try:
            # Standardized context injection for the iteration swarm
            augmented_prompt = f"### PREVIOUS STEP RESULT ###\n{self.state['last_response']}\n\n### CURRENT TASK ###\n{prompt}"
            res = self.client.generate(model, sys, augmented_prompt)
            self._update_output(res, "AI Generation complete.")
        except Exception as e:
            self.log(f"AI ERROR: {e}")

    def _update_output(self, content, log_msg):
        def _do_update():
            self.state["last_response"] = content
            self.txt_response.delete("1.0", "end")
            self.txt_response.insert("1.0", content)
            self.log(log_msg)

            # If RUN ALL is active, advance after this step completes
            if getattr(self, "_run_all_active", False):
                # Always advance via after() to keep sequencing stable
                self.after(0, self._run_all_advance)

        # Tkinter widgets must only be touched from the main/UI thread
        if threading.current_thread() is threading.main_thread():
            _do_update()
        else:
            self.after(0, _do_update)

if __name__ == "__main__":
    import sys
    # Phase 2 CLI Hook: If arguments are passed, we could bypass the UI
    if len(sys.argv) > 1 and "--cli" in sys.argv:
        print("[SYSTEM] CLI Mode detected. Bulk iteration would start here in Phase 2.")
        # In Phase 2, we would initialize RefactorEngine and run without mainloop
    else:
        app = WorkbenchApp()
        app.mainloop()





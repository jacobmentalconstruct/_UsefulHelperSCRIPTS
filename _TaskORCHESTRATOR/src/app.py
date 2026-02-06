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
# Using internal package imports
from src._microservices._ToolsMS import MicroserviceTools

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
    def __init__(self, app_ref=None):
        self.app = app_ref
        # Resolve path relative to this file's directory
        _base = os.path.dirname(os.path.abspath(__file__))
        _roles_path = os.path.join(_base, "_roles", "default_roles.json")
        
        if os.path.exists(_roles_path):
            try:
                with open(_roles_path, "r", encoding="utf-8") as f:
                    self.roles = json.load(f)
            except Exception:
                self.roles = {"Helpful Assistant": "Fallback: Load Error"}
        else:
            self.roles = {"Helpful Assistant": "Fallback: roles.json not found"}
    def get_names(self): return list(self.roles.keys())

    def get_prompt(self, name):
        """Extract the base_prompt from the structured role object."""
        role_data = self.roles.get(name, "")
        if isinstance(role_data, dict):
            return role_data.get("base_prompt", "")
        return role_data

    def get_system_prompt_by_id(self, prompt_id):
        """Lookup a specific instruction set from the system_prompts library."""
        if not self.app or not hasattr(self.app, 'system_prompts'):
            return ""
        
        # Search through all loaded system prompt files
        for filename, library in self.app.system_prompts.items():
            if prompt_id in library:
                return library[prompt_id].get('content', "")
        return ""

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
        self.expanded = False # Track UI state 
        # model: "(default)" means use the global model dropdown
        self.data = {"role": "Helpful Assistant", "prompt": "", "model": "(default)"}
        self._build_ui()

    def _build_ui(self):
        # Main Horizontal Control Row
        self.row_controls = tk.Frame(self, bg="#1e293b")
        self.row_controls.pack(fill="x")

        self.lbl_idx = tk.Label(self.row_controls, text=f"#{self.index+1}", bg="#1e293b", fg="#94a3b8", width=3)
        self.lbl_idx.pack(side="left")

        self.cb_role = ttk.Combobox(self.row_controls, values=self.role_mgr.get_names(), state="readonly", width=18)
        self.cb_role.pack(side="left", padx=5)
        self.cb_role.set(self.data["role"])
        self.cb_role.bind("<<ComboboxSelected>>", self._sync)

        # Per-step model override
        model_values = ["(default)"] + list(self.app.client.list_models())
        self.cb_model = ttk.Combobox(self.row_controls, values=model_values, state="readonly", width=18)
        self.cb_model.pack(side="left", padx=5)
        self.cb_model.set(self.data.get("model") or "(default)")
        self.cb_model.bind("<<ComboboxSelected>>", self._sync)

        # Collapsed Label (shows preview when closed)
        self.lbl_preview = tk.Label(self.row_controls, text="", bg="#1e293b", fg="#64748b", anchor="w")
        self.lbl_preview.pack(side="left", fill="x", expand=True, padx=5)

        tk.Button(self.row_controls, text="▶", command=lambda: self.app.run_step(self.index), 
                  bg="#3b82f6", fg="white", font=("Arial", 9, "bold")).pack(side="right", padx=5)

        # Dedicated Expand/Collapse Button
        self.btn_toggle = tk.Button(self.row_controls, text="▼", command=self.toggle_expand, 
                                    bg="#1e293b", fg="#94a3b8", relief="flat", font=("Arial", 10))
        self.btn_toggle.pack(side="right", padx=2)

        # The Expanded Prompt Area
        self.f_expanded = tk.Frame(self, bg="#0f172a", pady=5)
        # Not packed yet; wait for expansion toggle

        tk.Label(self.f_expanded, text="PROMPT:", bg="#0f172a", fg="#3b82f6", font=("Arial", 8, "bold")).pack(anchor="w", padx=5)
        self.txt_prompt = tk.Text(self.f_expanded, bg="#0f172a", fg="white", insertbackground="white", 
                                  borderwidth=0, height=5, font=("Consolas", 10), undo=True)
        self.txt_prompt.pack(fill="x", expand=True, padx=5)
        self.txt_prompt.bind("<FocusOut>", self._sync)

        def _on_text_focus(e):
            self.txt_prompt.config(state="normal")
            self.txt_prompt.focus_set()
            return "break"

        # Standardize focus and allow selection
        self.txt_prompt.bind("<Button-1>", _on_text_focus)

        # Clicking the index now only recalls output without toggling expansion
        self.lbl_idx.bind("<Button-1>", lambda e: self.app.show_step_output(self.index))

        # Initial enable/disable based on role
        self._update_model_state()

    def _sync(self, e=None):
        self.data["role"] = self.cb_role.get()
        # Text widgets require start and end indices for get()
        self.data["prompt"] = self.txt_prompt.get("1.0", "end-1c")
        self.data["model"] = self.cb_model.get() if hasattr(self, "cb_model") else "(default)"
        self._update_model_state()

    def _update_model_state(self):
        try:
            if self.cb_role.get() == "Mechanical Tool":
                self.cb_model.configure(state="disabled")
            else:
                self.cb_model.configure(state="readonly")
        except Exception:
            pass

    def _on_click(self, e=None):
        # Recall output for this step if available
        try:
            self.app.show_step_output(self.index)
        except Exception:
            pass
        self.toggle_expand()

    def toggle_expand(self):
        """Switches between collapsed and expanded view."""
        if self.expanded:
            self.f_expanded.pack_forget()
            self.lbl_preview.configure(text=self.txt_prompt.get("1.0", "end-1c")[:50] + "...")
            self.lbl_preview.pack(side="left", fill="x", expand=True, padx=5)
            self.btn_toggle.configure(text="▼")
            self.expanded = False
        else:
            self.lbl_preview.pack_forget()
            self.f_expanded.pack(fill="x", expand=True)
            self.btn_toggle.configure(text="▲")
            self.expanded = True

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
        # Link roles to self so it can access self.system_prompts later
        self.roles = RoleManager(self)
        self.steps = []

        # Tool Palette: The 'Swiss Army' manual for the AI
        self.tool_palette = {
            "create_backup": "Creates a timestamped backup of the target directory.",
            "read_template": "Loads the standard microservice boilerplate text.",
            "scan_file_structure": "Extracts imports, classes, and functions from a file via AST.",
            "apply_safe_patch": "Applies a TokenizingPatcher JSON hunk to the target file.",
            "get_cleanup_patch": "Generates a patch to fix common whitespace/formatting issues."
        }
        self.state = {"last_response": "", "current_file": ""}

        # Per-step output history
        # step_outputs[idx] = {"content": str, "success": bool|None, "ts": str, "log_msg": str}
        self.step_outputs = {}
        self._selected_step_index = None

        # RUN-ALL state
        self._run_all_active = False
        self._run_all_index = 0
        self._run_all_last_stop_reason = ""

        # Initialize ToolsMS pointing to the repo root so it can find std_lib and base_service
        self.tools_engine = MicroserviceTools(_root_dir)
        self.recipe_path = tk.StringVar()

        # Build UI first so widgets like txt_log exist before any logging occurs
        self._build_ui()

        # Initialize storage for new domains
        self.system_prompts = self._load_json_dir("_system_prompts")
        self.workflows = self._load_json_dir("_workflows")
        self._workflow_active = False
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
        tk.Button(f_recipe_actions, text="🚀 WORKFLOW", command=lambda: self.run_workflow("default_workflow"), bg="#4f46e5", fg="white").pack(side="left", expand=True, fill="x", padx=2)
        tk.Button(left_frame, text="+ ADD STEP", command=self.add_step, bg="#334155", fg="white").pack(fill="x", pady=(5, 0), padx=5)

        # Right: Response & Log
        right_panes = tk.PanedWindow(main_panes, orient="vertical", bg="#0f172a")
        main_panes.add(right_panes)

        self.txt_response = scrolledtext.ScrolledText(right_panes, bg="#1e1e1e", fg="white", font=("Consolas", 10))
        right_panes.add(self.txt_response, height=450)

        self.txt_summary = scrolledtext.ScrolledText(right_panes, bg="#0b1220", fg="#e2e8f0", font=("Consolas", 9))
        right_panes.add(self.txt_summary, height=140)

        self.txt_log = scrolledtext.ScrolledText(right_panes, bg="#000000", fg="#00ff00", font=("Consolas", 9))
        right_panes.add(self.txt_log)

        # Initial Default Steps
        self.add_step("Mechanical Tool", "scan_file_structure")
        self.add_step("Strict Analyst", "Analyze the AST and plan migration.")

    def _request_missing_template(self, name):
        """Opens a popup window to allow the user to paste a new boilerplate."""
        result = {"text": None}
        dialog = tk.Toplevel(self)
        dialog.title(f"Missing Boilerplate: {name}")
        dialog.geometry("600x500")
        
        tk.Label(dialog, text=f"Paste the boilerplate/template for '{name}' below:", pady=10).pack()
        txt = scrolledtext.ScrolledText(dialog, bg="#1e1e1e", fg="white", font=("Consolas", 10))
        txt.pack(fill="both", expand=True, padx=10, pady=10)

        def _save():
            result["text"] = txt.get("1.0", "end-1c")
            dialog.destroy()

        tk.Button(dialog, text="SAVE & RESUME", command=_save, bg="#10b981", fg="white", pady=5).pack(pady=10)
        self.wait_window(dialog)
        return result["text"]

    def _load_json_dir(self, folder_name):
        """Utility to scan src/_folder/ for all JSON configuration objects."""
        data = {}
        _base = os.path.dirname(os.path.abspath(__file__))
        target_path = os.path.join(_base, folder_name)
        if os.path.exists(target_path):
            for f_name in os.listdir(target_path):
                if f_name.endswith(".json"):
                    try:
                        with open(os.path.join(target_path, f_name), "r", encoding="utf-8") as f:
                            data[f_name] = json.load(f)
                    except Exception as e:
                        self.log(f"Error loading {f_name}: {e}")
        return data

    def log(self, msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")

        def _do_log():
            # Safety check: skip logging if UI isn't ready yet
            if not hasattr(self, 'txt_log'):
                print(f"[{ts}] {msg}")
                return
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
        if prompt: s.txt_prompt.insert("1.0", prompt)
        s.pack(fill="x", pady=1)
        self.steps.append(s)

    def spawn_children(self, parent_idx, items):
        """Decomposes a list into individual child steps inheriting parent context."""
        parent_step = self.steps[parent_idx]
        role = parent_step.cb_role.get()
        
        self.log(f"Spawning {len(items)} children from Step #{parent_idx+1}")
        for item in items:
            if item.strip():
                self.add_step(role=role, prompt=item.strip())
        
        # If we were in RUN ALL mode, we stop to let user review the new generation
        if self._run_all_active:
            self._run_all_active = False
            self.log("RUN ALL paused for child review.")

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
                # Apply optional per-step model override
                try:
                    if self.steps and item.get("model"):
                        self.steps[-1].data["model"] = item.get("model")
                        if hasattr(self.steps[-1], "cb_model"):
                            self.steps[-1].cb_model.set(item.get("model"))
                        self.steps[-1]._sync()
                except Exception:
                    pass
            self.log(f"Loaded {len(recipe)} steps from {os.path.basename(path)}")

    def show_step_output(self, idx: int):
        """Show the most recent output for a step (if it has run)."""
        self._selected_step_index = idx
        record = self.step_outputs.get(idx)
        if not record:
            return

        content = record.get("content", "")
        # Avoid triggering RUN ALL advance; this is a manual view action
        def _do_show():
            self.txt_response.delete("1.0", "end")
            self.txt_response.insert("1.0", content)
        if threading.current_thread() is threading.main_thread():
            _do_show()
        else:
            self.after(0, _do_show)

    def run_step(self, idx):
        step = self.steps[idx]
        step._sync()
        role = step.data["role"]
        prompt = step.data["prompt"]
        
        self.log(f"Initiating Step #{idx+1} ({role})")
        
        if role == "Mechanical Tool":
            threading.Thread(target=self._tool_worker, args=(prompt, idx), daemon=True).start()
        else:
            # Per-step model override ("(default)" falls back to global)
            step_model = step.data.get("model")
            model = self.cb_model.get() if not step_model or step_model == "(default)" else step_model
            sys_p = self.roles.get_prompt(role)
            # Inject history context
            full_p = f"{prompt}\n\n[LAST_OUTPUT]:\n{self.state['last_response']}"
            threading.Thread(target=self._ai_worker, args=(model, sys_p, full_p, idx), daemon=True).start()

    def run_workflow(self, workflow_name):
        """Executes a workflow by iterating a tasklist over files."""
        wf = self.workflows.get(workflow_name) if isinstance(self.workflows.get(workflow_name), dict) else {}
        if not wf and workflow_name.endswith(".json"):
             wf = self.workflows.get(workflow_name, {})
            
        if not wf:
            self.log(f"Workflow '{workflow_name}' not found.")
            return

        target_dir = wf.get("target_dir", self.ent_dir.get())
        extension = wf.get("extension", ".py")
        
        # Find files matching criteria
        files = [f for f in os.listdir(target_dir) if f.endswith(extension) and not f.startswith("TEST_")]

        def _workflow_loop():
            self._workflow_active = True
            for f_name in files:
                self.log(f"[WORKFLOW] Processing: {f_name}")
                self.after(0, lambda f=f_name: self.ent_file.delete(0, "end"))
                self.after(0, lambda f=f_name: self.ent_file.insert(0, f))
                
                # Start the tasklist
                self.after(0, self.run_all_steps)
                
                # Wait for the tasklist to complete before moving to next file
                import time
                while self._run_all_active:
                    time.sleep(1)
            
            self.log("[WORKFLOW] All files processed.")
            self._workflow_active = False

        threading.Thread(target=_workflow_loop, daemon=True).start()

    def run_all_steps(self):
        if self._run_all_active:
            self.log("RUN ALL already active.")
            return

        if not self.steps:
            self.log("No steps to run.")
            return

        self._run_all_active = True
        self._run_all_index = 0
        self._run_all_last_stop_reason = ""
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
            self._run_all_last_stop_reason = f"Failure at step #{self._run_all_index + 1}"
            self.log(f"RUN ALL stopped on failure at step #{self._run_all_index + 1}.")
            self._run_all_active = False
            try:
                self._update_run_summary()
            except Exception:
                pass
            return

        # Next step
        self._run_all_index += 1
        if self._run_all_index >= len(self.steps):
            self._run_all_last_stop_reason = "Complete"
            self.log("RUN ALL complete.")
            self._run_all_active = False
            try:
                self._update_run_summary()
            except Exception:
                pass
            return

        self.run_step(self._run_all_index)

    def _tool_worker(self, cmd, step_idx=None):
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
                # Look for a template matching the current target file's extension or name
                ext = os.path.splitext(target_file)[1].replace('.', '') or "txt"
                template_name = f"{ext}_template.py" if ext == "py" else f"{ext}_template.txt"
                template_path = os.path.join(_root_dir, "src", "_microservices", template_name)
                
                if os.path.exists(template_path):
                    with open(template_path, "r", encoding="utf-8") as f:
                        res = f.read()
                else:
                    # GUARDRAIL: Prompt user to provide a boilerplate on the fly
                    self.log(f"[GUARDRAIL] Template missing: {template_name}. Requesting user input.")
                    user_input = self._request_missing_template(template_name)
                    if user_input:
                        with open(template_path, "w", encoding="utf-8") as f:
                            f.write(user_input)
                        res = user_input
                        self.log(f"[SUCCESS] Saved new template: {template_name}")
                    else:
                        res = {"success": False, "message": f"Aborted: No template provided for {template_name}"}

            # 3. MECHANICAL ANALYSIS (AST)
            elif cmd == "scan_file_structure":
                target_path = os.path.join(target_dir, target_file)
                res = self.tools_engine.scan_file_structure(target_path)

            # 4. PATCHING (Surgeon)
            elif cmd == "apply_safe_patch":
                target_path = os.path.join(target_dir, target_file)
                res = self.tools_engine.apply_patch(target_path, self.state["last_response"], dry_run=False)

            # 5. CLEANUP PATCH GENERATOR
            elif cmd == "get_cleanup_patch":
                res = self.tools_engine.generate_cleanup_patch()

            else:
                res = {"success": False, "message": f"Error: Tool '{cmd}' not recognized."}

        except Exception as e:
            self.log(f"TOOL ERROR: {e}")
            res = {"success": False, "message": f"TOOL ERROR: {e}"}

        output = json.dumps(res, indent=2) if isinstance(res, (dict, list)) else str(res)
        success = None
        if isinstance(res, dict):
            if res.get("success") is True:
                success = True
            elif res.get("success") is False or res.get("error"):
                success = False

        status = "succeeded" if success is True else ("failed" if success is False else "completed")
        self._update_output(output, f"Tool '{cmd}' {status}.", step_idx=step_idx, success=success)

    def _ai_worker(self, model, sys, prompt, step_idx=None):
        try:
            # Inject Tool Palette as a reference guide for the AI
            tools_ref = "\n### AVAILABLE MECHANICAL TOOLS ###\n" + json.dumps(self.tool_palette, indent=2)
            
            # Standardized context injection for the iteration swarm
            augmented_prompt = f"### PREVIOUS STEP RESULT ###\n{self.state['last_response']}{tools_ref}\n\n### CURRENT TASK ###\n{prompt}"
            res = self.client.generate(model, sys, augmented_prompt)
            self._update_output(res, "AI Generation complete.", step_idx=step_idx, success=True)
        except Exception as e:
            self.log(f"AI ERROR: {e}")
            self._update_output(f"AI ERROR: {e}", "AI Generation failed.", step_idx=step_idx, success=False)

    def _update_run_summary(self):
        """Render a compact wrap-up of the current run state."""
        lines = []
        lines.append("=== RUN SUMMARY ===")
        if self._run_all_active:
            lines.append(f"Status: RUNNING (step {self._run_all_index + 1} / {len(self.steps)})")
        else:
            if self._run_all_last_stop_reason:
                lines.append(f"Status: STOPPED - {self._run_all_last_stop_reason}")
            else:
                lines.append("Status: IDLE")

        lines.append("")
        for i, s in enumerate(self.steps):
            rec = self.step_outputs.get(i)
            if not rec:
                status = "(not run)"
            else:
                succ = rec.get("success")
                if succ is True:
                    status = "OK"
                elif succ is False:
                    status = "FAIL"
                else:
                    status = "DONE"
            role = s.data.get("role")
            model = s.data.get("model") if role != "Mechanical Tool" else "-"
            lines.append(f"#{i+1:02d} [{status}] {role} | model={model}")

        lines.append("")
        lines.append("Final output shown in main output pane.")

        text = "\n".join(lines)
        self.txt_summary.delete("1.0", "end")
        self.txt_summary.insert("1.0", text)

    def _update_output(self, content, log_msg, step_idx=None, success=None):
        def _do_update():
            self.state["last_response"] = content
            self.txt_response.delete("1.0", "end")
            self.txt_response.insert("1.0", content)
            self.log(log_msg)

            # Persist output per-step for later recall
            if step_idx is not None:
                ts = datetime.datetime.now().strftime("%H:%M:%S")
                self.step_outputs[step_idx] = {
                    "content": content,
                    "success": success,
                    "ts": ts,
                    "log_msg": log_msg,
                }

            # Update summary panel
            try:
                self._update_run_summary()
            except Exception:
                pass

            # Detect and execute Spawn Intent
            if content.startswith("[LIST]"):
                raw_list = content.replace("[LIST]", "").strip()
                # Support both newline and comma separation
                items = [i.strip() for i in raw_list.split('\n') if i.strip()]
                if len(items) == 1 and ',' in items[0]:
                    items = [i.strip() for i in items[0].split(',')]
                
                if items:
                    self.spawn_children(step_idx, items)
                    return # Stop advancement; children are now the focus

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
    else:
        app = WorkbenchApp()
        app.mainloop()

# --- FUNCTIONAL PATCH ENGINE ---
# These must be at the top-level (global scope) to be importable via 'from src.app import ...'

class PatchError(Exception): 
    """Exception raised for errors in the patching process."""
    pass

def apply_patch_text(original_text, patch_obj, global_force_indent=False):
    """
    Applies multiple JSON hunks to a target text. 
    Each hunk must match the search_block exactly.
    """
    new_text = original_text
    hunks = patch_obj.get("hunks", [])

    for i, hunk in enumerate(hunks):
        description = hunk.get("description", f"Hunk #{i}")
        search = hunk.get("search_block", "")
        replace = hunk.get("replace_block", "")

        if not search:
            continue

        if search in new_text:
            # Basic replacement
            new_text = new_text.replace(search, replace)
        else:
            raise PatchError(f"Failed to apply '{description}': Search block not found.")

    return new_text














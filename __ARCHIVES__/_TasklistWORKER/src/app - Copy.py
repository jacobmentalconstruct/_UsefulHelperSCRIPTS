import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import threading
import json
import os
import datetime

# --- MICROSERVICES CHECK ---
try:
    from src._microservices.ollama_client import OllamaClient
    from src._microservices.template_engine import resolve_template
except ImportError:
    try:
        from _microservices.ollama_client import OllamaClient
        from _microservices.template_engine import resolve_template
    except ImportError:
        raise ImportError("Microservices missing. Ensure src/_microservices exists.")

# ==============================================================================
# CUSTOM WIDGET: Smart Task Step (Expander)
# ==============================================================================
class TaskStepWidget(tk.Frame):
    def __init__(self, parent, index, app_ref, initial_data=None):
        super().__init__(parent, bg="#334155", bd=1, relief="flat")
        self.app = app_ref
        self.index = index
        self.expanded = False
        
        # Data Model
        self.data = initial_data or {
            "system": "You are a helpful AI assistant.",
            "prompt": "",
            "use_context": True
        }

        self._build_ui()
        self._refresh_summary()

    def _build_ui(self):
        # --- HEADER (Always Visible) ---
        self.header = tk.Frame(self, bg="#334155", height=30)
        self.header.pack(fill="x", padx=2, pady=2)
        
        # Click header to toggle
        self.header.bind("<Button-1>", self.toggle)
        
        # Step Number / Status Indicator
        self.lbl_idx = tk.Label(self.header, text=f"#{self.index+1}", bg="#334155", fg="#94a3b8", font=("Segoe UI", 10, "bold"), width=4)
        self.lbl_idx.pack(side="left")
        self.lbl_idx.bind("<Button-1>", self.toggle)

        # Summary Text (Read-only representation)
        self.lbl_summary = tk.Label(self.header, text="(New Step)", bg="#334155", fg="white", anchor="w", font=("Segoe UI", 10))
        self.lbl_summary.pack(side="left", fill="x", expand=True, padx=5)
        self.lbl_summary.bind("<Button-1>", self.toggle)

        # Delete Button (Small 'x')
        lbl_del = tk.Label(self.header, text="×", bg="#334155", fg="#ef4444", font=("Arial", 12, "bold"), cursor="hand2")
        lbl_del.pack(side="right", padx=5)
        lbl_del.bind("<Button-1>", lambda e: self.app.delete_step(self.index))

        # --- BODY (Hidden by default) ---
        self.body = tk.Frame(self, bg="#1e293b", padx=5, pady=5)
        
        # 1. System Prompt
        tk.Label(self.body, text="System Prompt:", bg="#1e293b", fg="#64748b", font=("Segoe UI", 8)).pack(anchor="w")
        self.ent_sys = tk.Entry(self.body, bg="#0f172a", fg="#94a3b8", borderwidth=0, insertbackground="white")
        self.ent_sys.pack(fill="x", pady=(0, 5))
        self.ent_sys.insert(0, self.data["system"])

        # 2. User Prompt (Auto-growing Text)
        tk.Label(self.body, text="User Prompt:", bg="#1e293b", fg="#cbd5e1", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.txt_prompt = tk.Text(self.body, height=4, bg="#0f172a", fg="white", borderwidth=0, insertbackground="white", font=("Segoe UI", 10), wrap="word")
        self.txt_prompt.pack(fill="x", pady=(0, 5))
        self.txt_prompt.insert("1.0", self.data["prompt"])
        
        # Bindings for "Save on Type" / "Auto-size"
        self.txt_prompt.bind("<KeyRelease>", self._on_text_change)
        self.txt_prompt.bind("<FocusOut>", self._sync_data)

        # 3. Context Toggle
        self.var_ctx = tk.BooleanVar(value=self.data["use_context"])
        chk = tk.Checkbutton(self.body, text="Include Previous Response", variable=self.var_ctx, bg="#1e293b", fg="#94a3b8", selectcolor="#0f172a", activebackground="#1e293b", activeforeground="white")
        chk.pack(anchor="w")

    def toggle(self, event=None):
        if self.expanded:
            self.collapse()
        else:
            self.expand()

    def expand(self):
        self.app.collapse_all_steps() # Singleton expansion (optional, feels cleaner)
        self.body.pack(fill="x", expand=True)
        self.header.config(bg="#475569")
        self.lbl_idx.config(bg="#475569", fg="white")
        self.lbl_summary.config(bg="#475569")
        self.expanded = True
        self.txt_prompt.focus_set()

    def collapse(self):
        self._sync_data()
        self.body.pack_forget()
        self.header.config(bg="#334155")
        self.lbl_idx.config(bg="#334155", fg="#94a3b8")
        self.lbl_summary.config(bg="#334155")
        self.expanded = False
        self._refresh_summary()

    def _sync_data(self, event=None):
        """Update internal data dict from widgets."""
        self.data["system"] = self.ent_sys.get()
        self.data["prompt"] = self.txt_prompt.get("1.0", "end-1c")
        self.data["use_context"] = self.var_ctx.get()

    def _on_text_change(self, event=None):
        # Auto-grow logic
        lines = int(self.txt_prompt.index('end-1c').split('.')[0])
        new_height = min(max(4, lines + 1), 15)
        if int(self.txt_prompt.cget("height")) != new_height:
            self.txt_prompt.config(height=new_height)

    def _refresh_summary(self):
        """Update the collapsed header text."""
        raw = self.data["prompt"].replace("\n", " ").strip()
        if not raw: raw = "(Empty Step)"
        if len(raw) > 50: raw = raw[:47] + "..."
        self.lbl_summary.config(text=raw)

    def set_active(self, active: bool):
        color = "#2563eb" if active else ("#475569" if self.expanded else "#334155")
        self.config(bg=color)
        if not self.expanded:
            self.header.config(bg=color)
            self.lbl_idx.config(bg=color)
            self.lbl_summary.config(bg=color)

# ==============================================================================
# MAIN APPLICATION
# ==============================================================================
class PromptChainerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("_PromptCHAINER v3.1 [IDE Mode]")
        self.root.geometry("1600x900")
        self.root.configure(bg="#0f172a")

        self.client = OllamaClient()
        
        # State
        self.state = {
            "chat": {"history": [], "last_response": ""},
            "working": {"step_outputs": {}, "thoughts": []},
            "outputs": {}
        }
        self.steps = [] # List of TaskStepWidget
        self.current_step_idx = 0
        self.is_running = False
        
        # UI Vars
        self.selected_model = tk.StringVar()
        self.helper_model = tk.StringVar()
        self.auto_run = tk.BooleanVar(value=False)

        self._build_layout()
        self._refresh_models()
        self.log_system("System Initialized.")

    def _build_layout(self):
        # Main container (3 Columns)
        self.paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#0f172a", sashwidth=4, sashrelief="flat")
        self.paned.pack(fill="both", expand=True, pady=(0, 30)) # Leave room for bottom log

        # --- COL 1: HISTORY (Left) ---
        f_left = tk.Frame(self.paned, bg="#0f172a")
        self.paned.add(f_left, minsize=350, stretch="always")
        
        tk.Label(f_left, text="Conversation History", bg="#0f172a", fg="#64748b", font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=5, pady=5)
        self.txt_chat = scrolledtext.ScrolledText(f_left, bg="#020617", fg="#94a3b8", borderwidth=0, font=("Consolas", 10))
        self.txt_chat.pack(fill="both", expand=True, padx=5)

        # --- COL 2: CHAIN EDITOR (Center) ---
        f_center = tk.Frame(self.paned, bg="#1e293b")
        self.paned.add(f_center, minsize=450, stretch="always")

        # 1. Header (Top)
        c_head = tk.Frame(f_center, bg="#1e293b", pady=10, padx=10)
        c_head.pack(side="top", fill="x")
        tk.Label(c_head, text="Task Chain", font=("Segoe UI", 14, "bold"), bg="#1e293b", fg="white").pack(side="left")
        
        tk.Label(c_head, text="Model:", bg="#1e293b", fg="#94a3b8").pack(side="left", padx=(20, 5))
        self.cb_model = ttk.Combobox(c_head, textvariable=self.selected_model, state="readonly", width=18)
        self.cb_model.pack(side="left")
        
        tk.Button(c_head, text="📂", command=self.load_chain, bg="#334155", fg="white", width=3, relief="flat").pack(side="right")
        tk.Button(c_head, text="💾", command=self.save_chain, bg="#334155", fg="white", width=3, relief="flat").pack(side="right", padx=5)

        # 2. Footer Buttons (Bottom - PACK FIRST TO ENSURE VISIBILITY)
        f_ctrl = tk.Frame(f_center, bg="#1e293b", pady=10, padx=10)
        f_ctrl.pack(side="bottom", fill="x")
        
        # "+ Add Step"
        tk.Button(f_ctrl, text="+ Add Step", command=self.add_step, bg="#334155", fg="white", relief="flat", font=("Segoe UI", 10)).pack(fill="x")

        # 3. Scrollable Task Area (Fills remaining space)
        self.canvas = tk.Canvas(f_center, bg="#1e293b", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(f_center, orient="vertical", command=self.canvas.yview)
        self.frame_tasks = tk.Frame(self.canvas, bg="#1e293b")
        
        self.canvas.create_window((0, 0), window=self.frame_tasks, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="top", fill="both", expand=True, padx=5)
        self.scrollbar.pack(side="right", fill="y")
        self.frame_tasks.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))


        # --- COL 3: ANALYSIS & OUTPUT (Right) ---
        f_right = tk.Frame(self.paned, bg="#0f172a")
        self.paned.add(f_right, minsize=400, stretch="always")

        # Split Right Col into Thoughts (Top) and Staging (Bottom)
        paned_right = tk.PanedWindow(f_right, orient=tk.VERTICAL, bg="#0f172a", sashwidth=4)
        paned_right.pack(fill="both", expand=True)

        # Thoughts Pane
        f_thoughts = tk.Frame(paned_right, bg="#0f172a")
        h_thoughts = tk.Frame(f_thoughts, bg="#0f172a")
        h_thoughts.pack(fill="x", pady=5)
        tk.Label(h_thoughts, text="Thought Stream", bg="#0f172a", fg="#a78bfa", font=("Segoe UI", 10, "bold")).pack(side="left", padx=5)
        
        # Helper Model Select
        self.cb_helper = ttk.Combobox(h_thoughts, textvariable=self.helper_model, state="readonly", width=15)
        self.cb_helper.pack(side="right", padx=5)
        tk.Label(h_thoughts, text="Helper:", bg="#0f172a", fg="#64748b", font=("Segoe UI", 8)).pack(side="right")

        self.txt_thoughts = scrolledtext.ScrolledText(f_thoughts, bg="#1e1e1e", fg="#a78bfa", borderwidth=0, font=("Segoe UI", 9))
        self.txt_thoughts.pack(fill="both", expand=True, padx=5)
        paned_right.add(f_thoughts, minsize=200, stretch="always")

        # Staging Pane (Bottom Right)
        f_stage = tk.Frame(paned_right, bg="#0f172a")
        
        tk.Label(f_stage, text="FINAL OUTPUT / STAGING (Edit before continuing)", bg="#0f172a", fg="#facc15", font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=5, pady=(10, 5))
        
        self.txt_staging = scrolledtext.ScrolledText(f_stage, bg="#1e293b", fg="#e2e8f0", borderwidth=0, font=("Consolas", 11), insertbackground="white")
        self.txt_staging.pack(fill="both", expand=True, padx=5)
        
        # ACTION BAR (The Green Arrow)
        f_action = tk.Frame(f_stage, bg="#0f172a", pady=10)
        f_action.pack(fill="x", padx=5)
        
        # This is the Master Action Button
        self.btn_action = tk.Button(f_action, text="START CHAIN ➡", command=self.on_action_click, bg="#2563eb", fg="white", font=("Segoe UI", 12, "bold"), relief="flat", height=2)
        self.btn_action.pack(fill="x")
        
        tk.Checkbutton(f_action, text="Auto-Commit (No Pause)", variable=self.auto_run, bg="#0f172a", fg="#94a3b8", selectcolor="#0f172a", activebackground="#0f172a").pack(anchor="e")

        paned_right.add(f_stage, minsize=300, stretch="always")

        # --- BOTTOM: SYSTEM LOG ---
        self.txt_log = tk.Text(self.root, height=8, bg="#020617", fg="#475569", font=("Consolas", 9), borderwidth=0, state="disabled")
        self.txt_log.place(relx=0, rely=1, anchor="sw", relwidth=1.0, height=150) # Use place to anchor firmly to bottom
        self.txt_log.pack(side="bottom", fill="x")

    # --- LOGIC ---

    def log_system(self, msg):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_log.config(state="normal")
        self.txt_log.insert("end", f"[{timestamp}] {msg}\n")
        self.txt_log.see("end")
        self.txt_log.config(state="disabled")

    def _refresh_models(self):
        def worker():
            try:
                models = self.client.list_models()
                self.root.after(0, lambda: self._update_combos(models))
            except Exception as e:
                self.log_system(f"Error listing models: {e}")
        threading.Thread(target=worker, daemon=True).start()

    def _update_combos(self, models):
        self.cb_model.config(values=models)
        self.cb_helper.config(values=models)
        if models:
            self.cb_model.set(models[0])
            helpers = [m for m in models if "mini" in m or "7b" in m]
            self.cb_helper.set(helpers[0] if helpers else models[0])
        self.log_system(f"Found {len(models)} models.")

    def collapse_all_steps(self):
        for s in self.steps:
            if s.expanded: s.collapse()

    def add_step(self, data=None):
        idx = len(self.steps)
        # Create widget
        w = TaskStepWidget(self.frame_tasks, idx, self, initial_data=data)
        w.pack(fill="x", pady=2)
        self.steps.append(w)
        
        # If adding manually (no data), expand it for editing
        if not data:
            w.expand()

    def delete_step(self, index):
        if not (0 <= index < len(self.steps)): return
        
        # Remove widget
        self.steps[index].destroy()
        self.steps.pop(index)
        
        # Re-index remaining
        for i, s in enumerate(self.steps):
            s.index = i
            s.lbl_idx.config(text=f"#{i+1}")
        
        self.log_system(f"Deleted step #{index+1}")

    def on_action_click(self):
        # Determine context: Are we starting? confirming? finishing?
        
        # Case 1: Not running -> Start
        if not self.is_running:
            self.start_chain()
            return

        # Case 2: Running -> Commit Staging & Move Next
        self.commit_staging()

    def start_chain(self):
        if not self.steps:
            messagebox.showwarning("Empty", "Add some steps first.")
            return

        self.is_running = True
        self.current_step_idx = 0
        
        # Clear logs
        self.txt_chat.delete("1.0", "end")
        self.txt_thoughts.delete("1.0", "end")
        self.state["chat"]["history"] = []
        self.state["chat"]["last_response"] = ""
        
        self.log_system("--- STARTED NEW CHAIN ---")
        self.run_step(0)

    def run_step(self, idx):
        if idx >= len(self.steps):
            self.finish_chain()
            return

        self.current_step_idx = idx
        step_widget = self.steps[idx]
        step_widget._sync_data() # Ensure we have latest text
        data = step_widget.data

        # UI Update
        for s in self.steps: s.set_active(False)
        step_widget.set_active(True)
        
        self.btn_action.config(text="Running...", bg="#475569", state="disabled")
        self.log_system(f"Executing Step #{idx+1}")

        # Construct Prompt
        # 1. Template Resolution
        raw_prompt = data["prompt"]
        final_prompt = resolve_template(raw_prompt, self.state)
        
        # 2. Context Injection
        if data["use_context"] and idx > 0:
            final_prompt += f"\n\n[CONTEXT FROM PREVIOUS STEP]:\n{self.state['chat']['last_response']}"

        self.txt_chat.insert("end", f"\n[USER - Step {idx+1}]\n{final_prompt}\n" + "-"*30 + "\n")
        self.txt_chat.see("end")

        # Threaded Inference
        threading.Thread(target=self._inference_worker, args=(data["system"], final_prompt), daemon=True).start()

    def _inference_worker(self, sys_prompt, user_prompt):
        try:
            main_model = self.selected_model.get()
            resp = self.client.generate(main_model, sys_prompt, user_prompt)

            helper_model = self.helper_model.get()
            thought = "..."
            if helper_model:
                thought = self.client.generate(helper_model, "Summarize this interaction and suggest the next logical thought.", f"Q: {user_prompt}\nA: {resp}")

            self.root.after(0, lambda: self._on_step_complete(resp, thought))
        except Exception as e:
            self.root.after(0, lambda: self.log_system(f"Inference Error: {e}"))
            self.root.after(0, lambda: self.btn_action.config(state="normal", text="Retry"))

    def _on_step_complete(self, response, thought):
        # 1. Populate Staging
        self.txt_staging.delete("1.0", "end")
        self.txt_staging.insert("1.0", response)
        
        # 2. Populate Thoughts
        self.txt_thoughts.insert("end", f"Step {self.current_step_idx+1}: {thought.strip()}\n\n")
        self.txt_thoughts.see("end")

        # 3. Enable 'Next' Button
        is_last = (self.current_step_idx == len(self.steps) - 1)
        btn_text = "Finish & Save 🏁" if is_last else "Confirm & Next ➡"
        btn_color = "#16a34a" if is_last else "#2563eb"
        
        self.btn_action.config(state="normal", text=btn_text, bg=btn_color)
        self.log_system(f"Step #{self.current_step_idx+1} complete. Waiting for confirmation.")

        if self.auto_run.get():
            self.commit_staging()

    def commit_staging(self):
        # User may have edited text in staging
        final_text = self.txt_staging.get("1.0", "end-1c")
        
        self.state["chat"]["last_response"] = final_text
        self.txt_chat.insert("end", f"\n[ASSISTANT]\n{final_text}\n" + "="*40 + "\n")
        self.txt_chat.see("end")
        
        self.run_step(self.current_step_idx + 1)

    def finish_chain(self):
        self.is_running = False
        self.btn_action.config(text="START CHAIN ➡", bg="#2563eb")
        self.log_system("Chain Completed.")
        
        # Save Log
        if not os.path.exists("_logs"): os.makedirs("_logs")
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        fn = f"_logs/run_{ts}.json"
        
        log_data = {
            "chat": self.txt_chat.get("1.0", "end-1c"),
            "thoughts": self.txt_thoughts.get("1.0", "end-1c"),
            "final_output": self.state["chat"]["last_response"]
        }
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)
        
        messagebox.showinfo("Success", f"Run saved to {fn}")

    # --- SAVE / LOAD ---
    def save_chain(self):
        # Force sync of all widgets
        for s in self.steps: s._sync_data()
        
        data = [s.data for s in self.steps]
        f = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if f:
            with open(f, 'w') as file:
                json.dump(data, file, indent=2)
            self.log_system(f"Saved chain to {os.path.basename(f)}")

    def load_chain(self):
        f = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if f:
            with open(f, 'r') as file:
                data = json.load(file)
            
            # Clear UI
            for s in self.steps: s.destroy()
            self.steps = []
            
            # Rebuild
            for step_data in data:
                self.add_step(step_data)
            self.log_system(f"Loaded chain from {os.path.basename(f)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = PromptChainerApp(root)
    root.mainloop()
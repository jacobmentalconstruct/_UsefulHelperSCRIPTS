import tkinter as tk
from tkinter import messagebox, ttk, simpledialog, filedialog
import threading
import json
import os
import datetime

from src.gui_layout import WorkbenchUI

try:
    from src._microservices.ollama_client import OllamaClient
    from src._microservices.template_engine import resolve_template
except ImportError:
    from _microservices.ollama_client import OllamaClient
    from _microservices.template_engine import resolve_template

# ==============================================================================
# DATA MANAGER: Roles
# ==============================================================================
class RoleManager:
    def __init__(self):
        # Default Roles
        self.roles = {
            "Helpful Assistant": "You are a helpful AI assistant.",
            "Python Expert": "You are a senior Python developer. Be concise and precise.",
            "Creative Writer": "You are a creative writer. Use vivid imagery.",
            "Strict Analyst": "You are a logic-first analyst. No fluff."
        }
    
    def get_names(self):
        return list(self.roles.keys())
    
    def get_prompt(self, name):
        return self.roles.get(name, "")
    
    def add_role(self, name, prompt):
        self.roles[name] = prompt

# ==============================================================================
# DIALOGS
# ==============================================================================
class AddRoleDialog(simpledialog.Dialog):
    def body(self, master):
        tk.Label(master, text="Role Name:").grid(row=0)
        tk.Label(master, text="System Prompt:").grid(row=1)
        self.e1 = tk.Entry(master)
        self.e2 = tk.Entry(master)
        self.e1.grid(row=0, column=1)
        self.e2.grid(row=1, column=1)
        return self.e1
    def apply(self):
        self.result = (self.e1.get(), self.e2.get())

class LogConfigDialog(simpledialog.Dialog):
    def __init__(self, parent, current_config):
        self.config = current_config
        super().__init__(parent, title="Log Configuration")

    def body(self, master):
        tk.Label(master, text="Log Subdirectory:").grid(row=0, sticky="w")
        self.e_dir = tk.Entry(master)
        self.e_dir.insert(0, self.config["dir"])
        self.e_dir.grid(row=0, column=1)

        self.var_ts = tk.BooleanVar(value=self.config["timestamp"])
        tk.Checkbutton(master, text="Include Timestamp in Filename", variable=self.var_ts).grid(row=1, columnspan=2, sticky="w")
        
        return self.e_dir

    def apply(self):
        self.result = {
            "dir": self.e_dir.get(),
            "timestamp": self.var_ts.get()
        }

# ==============================================================================
# CONTROLLER: Task Step Row
# ==============================================================================
class TaskStepController(tk.Frame):
    def __init__(self, parent, index, app_ref, role_mgr, initial_data=None):
        super().__init__(parent, bg="#334155", bd=1, relief="flat")
        self.app = app_ref
        self.index = index
        self.role_mgr = role_mgr
        self.expanded = False
        
        self.data = initial_data or {
            "role": "Helpful Assistant",
            "prompt": "",
            "isolated": False,
            "skip": False
        }
        
        self._build_row_ui()
        self._refresh_summary()

    def _build_row_ui(self):
        # Header
        self.header = tk.Frame(self, bg="#334155", height=30)
        self.header.pack(fill="x", padx=2, pady=2)
        self.header.bind("<Button-1>", self.toggle)

        # Controls Left
        self.lbl_idx = tk.Label(self.header, text=f"#{self.index+1}", bg="#334155", fg="#94a3b8", font=("Segoe UI", 10, "bold"), width=3)
        self.lbl_idx.pack(side="left")

        # Run Single Step Button
        self.btn_run_single = tk.Label(self.header, text="▶", bg="#334155", fg="#4ade80", cursor="hand2", font=("Arial", 10))
        self.btn_run_single.pack(side="left", padx=5)
        self.btn_run_single.bind("<Button-1>", self.run_this_step_only)
        
        # Summary
        self.lbl_summary = tk.Label(self.header, text="(New Step)", bg="#334155", fg="white", anchor="w")
        self.lbl_summary.pack(side="left", fill="x", expand=True, padx=5)
        self.lbl_summary.bind("<Button-1>", self.toggle)
        
        # Status Icons
        self.lbl_skip = tk.Label(self.header, text="⛔", bg="#334155", fg="#ef4444", font=("Segoe UI", 8)) # Hidden default
        self.lbl_iso = tk.Label(self.header, text="🔒", bg="#334155", fg="#facc15", font=("Segoe UI", 8)) # Hidden default

        # Delete
        lbl_del = tk.Label(self.header, text="×", bg="#334155", fg="#ef4444", cursor="hand2", font=("Arial", 12, "bold"))
        lbl_del.pack(side="right", padx=5)
        lbl_del.bind("<Button-1>", lambda e: self.app.delete_step(self.index))

        # Body
        self.body = tk.Frame(self, bg="#1e293b", padx=5, pady=5)
        
        # Role Row
        f_role = tk.Frame(self.body, bg="#1e293b")
        f_role.pack(fill="x", pady=(0, 5))
        tk.Label(f_role, text="Role:", bg="#1e293b", fg="#64748b").pack(side="left")
        
        self.cb_role = ttk.Combobox(f_role, values=self.role_mgr.get_names(), state="readonly")
        self.cb_role.pack(side="left", fill="x", expand=True, padx=5)
        self.cb_role.set(self.data["role"])
        self.cb_role.bind("<<ComboboxSelected>>", self._sync_data)

        tk.Button(f_role, text="+", command=self._add_role_local, bg="#334155", fg="white", width=2).pack(side="right")

        # Prompt
        tk.Label(self.body, text="Prompt:", bg="#1e293b", fg="#cbd5e1", font=("Segoe UI", 8, "bold")).pack(anchor="w")
        self.txt_prompt = tk.Text(self.body, height=5, bg="#0f172a", fg="white", borderwidth=0, font=("Segoe UI", 9), wrap="word")
        self.txt_prompt.pack(fill="x", pady=(0, 5))
        self.txt_prompt.insert("1.0", self.data["prompt"])
        self.txt_prompt.bind("<FocusOut>", self._sync_data)

        # Settings Row
        f_set = tk.Frame(self.body, bg="#1e293b")
        f_set.pack(fill="x")
        
        self.var_iso = tk.BooleanVar(value=self.data["isolated"])
        tk.Checkbutton(f_set, text="Run in Isolation", variable=self.var_iso, bg="#1e293b", fg="#facc15", selectcolor="#0f172a", activebackground="#1e293b", command=self._sync_data).pack(side="left")
        
        self.var_skip = tk.BooleanVar(value=self.data["skip"])
        tk.Checkbutton(f_set, text="Skip Step", variable=self.var_skip, bg="#1e293b", fg="#ef4444", selectcolor="#0f172a", activebackground="#1e293b", command=self._sync_data).pack(side="right")

    def toggle(self, event=None):
        if self.expanded: self.collapse()
        else: self.expand()

    def expand(self):
        self.app.collapse_all_steps()
        self.body.pack(fill="x", expand=True)
        self.expanded = True
    
    def collapse(self):
        self._sync_data()
        self.body.pack_forget()
        self.expanded = False
        self._refresh_summary()

    def _sync_data(self, event=None):
        self.data["role"] = self.cb_role.get()
        self.data["prompt"] = self.txt_prompt.get("1.0", "end-1c")
        self.data["isolated"] = self.var_iso.get()
        self.data["skip"] = self.var_skip.get()
        self._refresh_summary()

    def _refresh_summary(self):
        raw = self.data["prompt"].replace("\n", " ").strip()
        if not raw: raw = "(Empty Step)"
        if len(raw) > 35: raw = raw[:32] + "..."
        
        summary = f"[{self.data['role']}] {raw}"
        self.lbl_summary.config(text=summary)
        
        # Toggle Icons
        if self.data["isolated"]: self.lbl_iso.pack(side="right", padx=2)
        else: self.lbl_iso.pack_forget()
        
        if self.data["skip"]: 
            self.lbl_skip.pack(side="right", padx=2)
            self.lbl_summary.config(fg="#64748b") # Grey out text
        else: 
            self.lbl_skip.pack_forget()
            self.lbl_summary.config(fg="white")

    def _add_role_local(self):
        self.app.add_new_role()
        # Refresh combo
        self.cb_role.config(values=self.app.roles.get_names())

    def run_this_step_only(self, event=None):
        # Stop propagation so we don't toggle expand
        # Run this step via app controller
        self.app.run_manual_step(self.index)
        return "break"

    def set_active(self, state):
        # state: "active", "pending", "none"
        if state == "active":
            bg = "#2563eb"
        elif state == "pending":
            bg = "#475569" # Grey to show it needs rerunning
        else:
            bg = "#334155"
        
        self.header.config(bg=bg)
        self.lbl_idx.config(bg=bg)
        self.btn_run_single.config(bg=bg)
        self.lbl_summary.config(bg=bg)

# ==============================================================================
# MAIN CONTROLLER
# ==============================================================================
class WorkbenchApp:
    def __init__(self, root):
        self.ui = WorkbenchUI(root)
        self.client = OllamaClient()
        self.roles = RoleManager()
        
        # App Config
        self.log_config = {"dir": "_logs", "timestamp": True}
        
        # State
        self.state = {
            "chat": {"last_response": ""},
            "history": [] 
        }
        self.steps = []
        self.current_step_idx = 0
        self.is_running = False
        
        # Bindings
        self.ui.widgets["btn_add_step"].config(command=self.add_step)
        self.ui.widgets["btn_run"].config(command=self.on_run_click)
        self.ui.widgets["btn_inject"].config(command=self.inject_to_chat)
        self.ui.widgets["btn_send_chat"].config(command=self.send_chat_message)
        
        self.ui.widgets["btn_add_role_chat"].config(command=self.add_new_role)
        self.ui.widgets["cb_chat_role"].bind("<<ComboboxSelected>>", lambda e: None) # Just holds value
        
        # Log Bindings
        self.ui.widgets["btn_log_save"].config(command=self.save_log_file)
        self.ui.widgets["btn_log_config"].config(command=self.open_log_config)

        # Init Data
        self._refresh_roles()
        self.add_step()
        threading.Thread(target=self._fetch_models, daemon=True).start()
        self.log("Workbench initialized.")

    def log(self, msg):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        self.ui.widgets["log_console"].config(state="normal")
        self.ui.widgets["log_console"].insert("end", f"[{timestamp}] {msg}\n")
        self.ui.widgets["log_console"].see("end")
        self.ui.widgets["log_console"].config(state="disabled")

    def _fetch_models(self):
        try:
            models = self.client.list_models()
            self.ui.root.after(0, lambda: self._update_dropdowns(models))
        except Exception as e:
            self.ui.root.after(0, lambda: self.log(f"Model Error: {e}"))

    def _update_dropdowns(self, models):
        for w in ["cb_helper", "cb_chat_model", "cb_task_model"]:
            self.ui.widgets[w].config(values=models)
            if models: self.ui.widgets[w].set(models[0])

    def _refresh_roles(self):
        names = self.roles.get_names()
        self.ui.widgets["cb_chat_role"].config(values=names)
        self.ui.widgets["cb_chat_role"].set("Helpful Assistant")
        # Update steps if needed? No, they pull dynamically.

    def add_new_role(self):
        d = AddRoleDialog(self.ui.root)
        if d.result:
            name, prompt = d.result
            if name and prompt:
                self.roles.add_role(name, prompt)
                self._refresh_roles()
                self.log(f"Added role: {name}")

    # --- CHAT LOGIC ---
    def send_chat_message(self):
        # 1. Get Text
        txt = self.ui.widgets["chat_input"].get("1.0", "end-1c").strip()
        if not txt: return
        
        # 2. Clear Input
        self.ui.widgets["chat_input"].delete("1.0", "end")
        
        # 3. Log User
        self._append_session("USER", txt)
        
        # 4. Get Config
        model = self.ui.widgets["cb_chat_model"].get()
        role_name = self.ui.widgets["cb_chat_role"].get()
        sys_prompt = self.roles.get_prompt(role_name)
        
        self.log(f"Chatting with {model} as {role_name}...")
        
        # 5. Thread
        threading.Thread(target=self._chat_worker, args=(model, sys_prompt, txt), daemon=True).start()

    def _chat_worker(self, model, sys, prompt):
        try:
            # We don't maintain full history buffer in state yet for simplicity, 
            # we just send prompt. Ideally we'd send history.
            # V5 Update: Let's simple-chain.
            context = ""
            if self.state["chat"]["last_response"]:
                context = f"Previous Context: {self.state['chat']['last_response']}\n\n"
            
            resp = self.client.generate(model, sys, context + prompt)
            self.ui.root.after(0, lambda: self._on_chat_complete(resp))
        except Exception as e:
            self.ui.root.after(0, lambda: self.log(f"Chat Error: {e}"))

    def _on_chat_complete(self, resp):
        self._append_session("ASSISTANT", resp)
        self.state["chat"]["last_response"] = resp

    # --- TASK LOGIC ---
    def collapse_all_steps(self):
        for s in self.steps: 
            if s.expanded: s.collapse()

    def add_step(self, data=None):
        container = self.ui.widgets["task_container"]
        idx = len(self.steps)
        step = TaskStepController(container, idx, self, self.roles, initial_data=data)
        step.pack(fill="x", pady=2)
        self.steps.append(step)
        if not data: step.expand()

    def delete_step(self, idx):
        if 0 <= idx < len(self.steps):
            self.steps[idx].destroy()
            self.steps.pop(idx)
            for i, s in enumerate(self.steps):
                s.index = i
                s.lbl_idx.config(text=f"#{i+1}")

    def run_manual_step(self, idx):
        # Visual Reset logic
        # If we run step 2, steps 3, 4, 5 become "Pending" (dirty)
        for i in range(idx + 1, len(self.steps)):
            self.steps[i].set_active("pending")
        
        # Hijack the standard runner
        self.run_step(idx)

    def on_run_click(self):
        # Continue chain logic
        self.run_step(self.current_step_idx)

    def run_step(self, idx):
        if idx >= len(self.steps): return
        
        self.current_step_idx = idx
        step = self.steps[idx]
        step._sync_data()

        if step.data["skip"]:
            self.log(f"Skipping Step #{idx+1}...")
            # Auto-advance if running chain, but wait if manual?
            # For now, just stop and let user click next.
            self.current_step_idx += 1
            if self.current_step_idx < len(self.steps):
                self.run_step(self.current_step_idx) # Auto skip
            return

        # UI Update
        for s in self.steps: 
            if s != step and s.header.cget("bg") == "#2563eb": 
                s.set_active("none")
        step.set_active("active")

        self.ui.widgets["btn_run"].config(text="Running...", state="disabled", bg="#475569")
        self.ui.widgets["btn_inject"].config(state="disabled")

        # Build Prompt
        raw_p = step.data["prompt"]
        final_p = resolve_template(raw_p, self.state)
        
        if not step.data["isolated"] and idx > 0 and self.state["chat"]["last_response"]:
             final_p += f"\n\n[CONTEXT]:\n{self.state['chat']['last_response']}"
        
        model = self.ui.widgets["cb_task_model"].get() or "qwen2.5:7b-instruct"
        role_name = step.data["role"]
        sys_p = self.roles.get_prompt(role_name)

        self.log(f"Running Step #{idx+1} on {model}...")
        threading.Thread(target=self._task_worker, args=(model, sys_p, final_p), daemon=True).start()

    def _task_worker(self, model, sys, prompt):
        try:
            resp = self.client.generate(model, sys, prompt)
            
            helper = self.ui.widgets["cb_helper"].get()
            thought = self.client.generate(helper, "Analyze.", f"TASK: {prompt[:100]}\nRESULT: {resp[:100]}")
            
            self.ui.root.after(0, lambda: self._on_task_complete(resp, thought))
        except Exception as e:
            self.ui.root.after(0, lambda: self.log(f"Task Error: {e}"))

    def _on_task_complete(self, resp, thought):
        self.ui.widgets["staging"].delete("1.0", "end")
        self.ui.widgets["staging"].insert("1.0", resp)
        self.ui.widgets["thoughts"].insert("end", f"Step {self.current_step_idx+1}: {thought}\n\n")
        
        btn = self.ui.widgets["btn_run"]
        is_last = self.current_step_idx == len(self.steps) - 1
        btn.config(text="Finish 🏁" if is_last else "Confirm & Next ➡", state="normal", bg="#16a34a" if is_last else "#2563eb")
        self.ui.widgets["btn_inject"].config(state="normal")

    def inject_to_chat(self):
        content = self.ui.widgets["staging"].get("1.0", "end-1c")
        self._append_session("INJECTED", content)
        self.state["chat"]["last_response"] = content
        
        if self.current_step_idx < len(self.steps) - 1:
            self.current_step_idx += 1
            self.steps[self.current_step_idx].set_active("active")

    def _append_session(self, role, text):
        w = self.ui.widgets["session_log"]
        w.insert("end", f"\n[{role}]\n{text}\n" + "-"*40 + "\n")
        w.see("end")

    # --- LOGGING UTILS ---
    def open_log_config(self):
        d = LogConfigDialog(self.ui.root, self.log_config)
        if d.result:
            self.log_config = d.result
            self.log(f"Log config updated: {self.log_config}")

    def save_log_file(self):
        d = self.log_config["dir"]
        if not os.path.exists(d): os.makedirs(d)
        
        name = "system_log"
        if self.log_config["timestamp"]:
            name += f"_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        name += ".txt"
        
        path = os.path.join(d, name)
        content = self.ui.widgets["log_console"].get("1.0", "end-1c")
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        
        messagebox.showinfo("Saved", f"Log saved to {path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = WorkbenchApp(root)
    root.mainloop()

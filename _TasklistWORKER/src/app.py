import tkinter as tk
from tkinter import ttk, scrolledtext, filedialog, messagebox
import threading
import json
import os

# --- MICROSERVICES INTEGRATION ---
# Ensure we can import from the subfolder
try:
    from src._microservices.ollama_client import OllamaClient
    from src._microservices.template_engine import resolve_template
except ImportError:
    # Fallback for flat structure testing
    try:
        from _microservices.ollama_client import OllamaClient
        from _microservices.template_engine import resolve_template
    except ImportError:
        print("CRITICAL: Microservices not found. Ensure src/_microservices exists.")
        raise

class PromptChainerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("_PromptCHAINER v2 [Staging Mode]")
        self.root.geometry("1400x900")
        self.root.configure(bg="#0f172a")

        # --- CLIENTS ---
        self.client = OllamaClient()

        # --- STATE ---
        self.state = {
            "chat": {"history": [], "last_response": ""},
            "working": {"step_outputs": {}, "thoughts": []},
            "outputs": {}
        }
        self.task_steps = []  # List of dicts: {id, text_widget, ...}
        self.current_step_index = 0
        self.is_running = False
        
        # UI Variables
        self.selected_model = tk.StringVar()
        self.helper_model = tk.StringVar()
        self.auto_run = tk.BooleanVar(value=False)
        self.status_msg = tk.StringVar(value="Ready")

        self._setup_ui()
        self._refresh_models()

    def _setup_ui(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TFrame", background="#0f172a")
        style.configure("TLabel", background="#0f172a", foreground="white")
        style.configure("TButton", background="#334155", foreground="white", borderwidth=0)
        style.map("TButton", background=[('active', '#475569')])

        # === MAIN LAYOUT (3 PANELS) ===
        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg="#0f172a", sashwidth=4, sashrelief="raised")
        main_pane.pack(fill="both", expand=True, padx=5, pady=5)

        # --- PANEL 1: CONTEXT & STAGING (Left) ---
        p1 = tk.Frame(main_pane, bg="#0f172a")
        main_pane.add(p1, minsize=400, stretch="always")

        # Header P1
        f_head1 = tk.Frame(p1, bg="#1e293b", padx=10, pady=5)
        f_head1.pack(fill="x")
        tk.Label(f_head1, text="Main Model:", bg="#1e293b", fg="#94a3b8").pack(side="left")
        self.cb_model = ttk.Combobox(f_head1, textvariable=self.selected_model, state="readonly", width=25)
        self.cb_model.pack(side="left", padx=5)
        tk.Button(f_head1, text="↻", command=self._refresh_models, bg="#334155", fg="white", width=3).pack(side="left")

        # Staging Area
        tk.Label(p1, text="STAGING AREA (Edit AI Output Here)", bg="#0f172a", fg="#facc15", font=("Segoe UI", 10, "bold"), pady=5).pack(anchor="w")
        self.txt_staging = scrolledtext.ScrolledText(p1, bg="#1e293b", fg="#e2e8f0", insertbackground="white", font=("Consolas", 10), height=15)
        self.txt_staging.pack(fill="x", padx=5)

        # Commit Controls
        f_commit = tk.Frame(p1, bg="#0f172a", pady=5)
        f_commit.pack(fill="x", padx=5)
        self.btn_commit = tk.Button(f_commit, text="✅ Confirm & Next Step", command=self.commit_and_continue, bg="#059669", fg="white", font=("Segoe UI", 10, "bold"), state="disabled")
        self.btn_commit.pack(fill="x")

        # Chat History
        tk.Label(p1, text="Conversation Log", bg="#0f172a", fg="#94a3b8", pady=5).pack(anchor="w")
        self.txt_chat = scrolledtext.ScrolledText(p1, bg="#020617", fg="#94a3b8", insertbackground="white", font=("Consolas", 9))
        self.txt_chat.pack(fill="both", expand=True, padx=5, pady=(0, 5))


        # --- PANEL 2: TASK CHAIN (Center) ---
        p2 = tk.Frame(main_pane, bg="#1e293b")
        main_pane.add(p2, minsize=350, stretch="always")

        # Header P2
        f_head2 = tk.Frame(p2, bg="#334155", padx=10, pady=5)
        f_head2.pack(fill="x")
        tk.Label(f_head2, text="Recipe Chain", font=("Segoe UI", 11, "bold"), bg="#334155", fg="white").pack(side="left")
        tk.Button(f_head2, text="💾", command=self.save_chain, bg="#475569", fg="white", width=3).pack(side="right", padx=2)
        tk.Button(f_head2, text="📂", command=self.load_chain, bg="#475569", fg="white", width=3).pack(side="right")

        # Task List Container
        self.canvas_tasks = tk.Canvas(p2, bg="#1e293b", highlightthickness=0)
        self.scrollbar_tasks = ttk.Scrollbar(p2, orient="vertical", command=self.canvas_tasks.yview)
        self.frame_tasks = tk.Frame(self.canvas_tasks, bg="#1e293b")

        self.canvas_tasks.create_window((0, 0), window=self.frame_tasks, anchor="nw")
        self.canvas_tasks.configure(yscrollcommand=self.scrollbar_tasks.set)

        self.canvas_tasks.pack(side="top", fill="both", expand=True, padx=5, pady=5)
        self.scrollbar_tasks.pack(side="right", fill="y")
        self.frame_tasks.bind("<Configure>", lambda e: self.canvas_tasks.configure(scrollregion=self.canvas_tasks.bbox("all")))

        # Controls
        f_ctrl = tk.Frame(p2, bg="#1e293b", pady=10)
        f_ctrl.pack(fill="x", padx=10)
        tk.Button(f_ctrl, text="+ Add Step", command=self.add_task_step, bg="#334155", fg="white").pack(fill="x")
        
        self.btn_run = tk.Button(f_ctrl, text="▶ START CHAIN", command=self.start_chain, bg="#2563eb", fg="white", font=("Segoe UI", 12, "bold"), pady=5)
        self.btn_run.pack(fill="x", pady=10)
        
        tk.Checkbutton(f_ctrl, text="Auto-Commit (No Pause)", variable=self.auto_run, bg="#1e293b", fg="white", selectcolor="#0f172a").pack(anchor="c")


        # --- PANEL 3: THOUGHTS & HELPERS (Right) ---
        p3 = tk.Frame(main_pane, bg="#0f172a")
        main_pane.add(p3, minsize=300, stretch="always")

        # Header P3
        f_head3 = tk.Frame(p3, bg="#1e293b", padx=10, pady=5)
        f_head3.pack(fill="x")
        tk.Label(f_head3, text="Helper Model:", bg="#1e293b", fg="#94a3b8").pack(side="left")
        self.cb_helper = ttk.Combobox(f_head3, textvariable=self.helper_model, state="readonly", width=20)
        self.cb_helper.pack(side="left", padx=5)

        tk.Label(p3, text="💭 Thought Stream", bg="#0f172a", fg="#a78bfa", font=("Segoe UI", 10, "bold"), pady=5).pack(anchor="w", padx=5)
        
        self.txt_thoughts = scrolledtext.ScrolledText(p3, bg="#1e1e1e", fg="#a78bfa", insertbackground="white", font=("Segoe UI", 9))
        self.txt_thoughts.pack(fill="both", expand=True, padx=5, pady=(0, 5))

        # Status Bar
        self.lbl_status = tk.Label(self.root, textvariable=self.status_msg, bg="#2563eb", fg="white", anchor="w", padx=10)
        self.lbl_status.pack(fill="x", side="bottom")

        # Init
        self.add_task_step()

    # --- LOGIC ---

    def _refresh_models(self):
        def worker():
            try:
                models = self.client.list_models()
                self.root.after(0, lambda: self._update_combos(models))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Ollama Error", f"Could not list models: {e}"))

        threading.Thread(target=worker, daemon=True).start()

    def _update_combos(self, models):
        self.cb_model.config(values=models)
        self.cb_helper.config(values=models)
        if models:
            self.cb_model.set(models[0])
            # Try to find a smaller model for helper, else default
            helpers = [m for m in models if "mini" in m or "7b" in m or "qwen" in m]
            self.cb_helper.set(helpers[0] if helpers else models[0])

    def add_task_step(self, content=""):
        idx = len(self.task_steps)
        
        f = tk.Frame(self.frame_tasks, bg="#334155", pady=2, padx=2)
        f.pack(fill="x", pady=2)
        
        lbl = tk.Label(f, text=f"{idx+1}", bg="#334155", fg="#94a3b8", width=3, font=("Segoe UI", 12, "bold"))
        lbl.pack(side="left", anchor="n")

        txt = tk.Text(f, height=3, bg="#1e293b", fg="white", insertbackground="white", borderwidth=0, font=("Segoe UI", 10))
        txt.pack(side="left", fill="x", expand=True, padx=2)
        txt.insert("1.0", content)

        self.task_steps.append({"frame": f, "text": txt, "index": idx})

    def start_chain(self):
        self.current_step_index = 0
        self.state["chat"]["history"] = []
        self.txt_chat.delete("1.0", "end")
        self.txt_thoughts.delete("1.0", "end")
        
        self.run_current_step()

    def run_current_step(self):
        if self.current_step_index >= len(self.task_steps):
            self.status_msg.set("Chain Complete.")
            messagebox.showinfo("Done", "Recipe completed successfully.")
            return

        # UI Updates
        for step in self.task_steps:
            bg = "#2563eb" if step["index"] == self.current_step_index else "#334155"
            step["frame"].config(bg=bg)

        self.status_msg.set(f"Running Step {self.current_step_index + 1}...")
        self.btn_run.config(state="disabled")
        self.btn_commit.config(state="disabled")

        # Get Prompt
        raw_prompt = self.task_steps[self.current_step_index]["text"].get("1.0", "end-1c")
        
        # Resolve Template (The Microservice Logic!)
        final_prompt = resolve_template(raw_prompt, self.state)
        
        # Append "Last Response" context manually if not in template
        # (Simple chaining strategy for prototype)
        if self.current_step_index > 0 and "{{state" not in raw_prompt:
            final_prompt += f"\n\nContext from previous step:\n{self.state['chat']['last_response']}"

        self._log_chat("USER", final_prompt)
        
        # Run Inference Thread
        threading.Thread(target=self._inference_worker, args=(final_prompt,), daemon=True).start()

    def _inference_worker(self, prompt):
        try:
            # 1. Main Inference
            model = self.selected_model.get()
            response = self.client.generate(model, "You are a helpful assistant.", prompt)
            
            # 2. Helper Inference (Thought Bubble)
            helper_model = self.helper_model.get()
            summary = "..."
            if helper_model:
                summary = self.client.generate(
                    helper_model, 
                    "Summarize the AI's response in 1 sentence. Be meta.",
                    f"PROMPT: {prompt}\nRESPONSE: {response}"
                )

            # Update UI
            self.root.after(0, lambda: self._on_step_success(response, summary))

        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
            self.root.after(0, lambda: self.btn_run.config(state="normal"))

    def _on_step_success(self, response, summary):
        # Show result in Staging Area
        self.txt_staging.delete("1.0", "end")
        self.txt_staging.insert("1.0", response)
        
        # Log thoughts
        self.txt_thoughts.insert("end", f"Step {self.current_step_index + 1}: {summary.strip()}\n\n")
        self.txt_thoughts.see("end")

        # Check for final step
        is_last = (self.current_step_index >= len(self.task_steps) - 1)

        if is_last:
            self.status_msg.set("Chain Finished. Edit Final Output if needed, then Commit.")
            self.btn_commit.config(state="normal", bg="#16a34a", text="🏁 Finish & Save Log", command=self.finish_chain)
        else:
            self.status_msg.set("Review Output. Edit if needed, then Confirm.")
            self.btn_commit.config(state="normal", bg="#059669", text="✅ Confirm & Next Step", command=self.commit_and_continue)

        # Auto-run check
        if self.auto_run.get():
            if is_last:
                self.finish_chain()
            else:
                self.commit_and_continue()

    def commit_and_continue(self):
        # 1. Grab content from Staging (User might have edited it!)
        final_output = self.txt_staging.get("1.0", "end-1c")
        
        # 2. Update State
        self.state["chat"]["last_response"] = final_output
        self._log_chat("ASSISTANT", final_output)
        
        # 3. Move index
        self.current_step_index += 1
        self.btn_commit.config(state="disabled", bg="#334155")
        
        # 4. Run next
        self.run_current_step()

    def finish_chain(self):
        # 1. Grab Final content
        final_output = self.txt_staging.get("1.0", "end-1c")
        
        # 2. Update State
        self.state["chat"]["last_response"] = final_output
        self.state["outputs"]["final"] = final_output
        self._log_chat("ASSISTANT (FINAL)", final_output)
        
        # 3. Save Session Log
        self._save_session_log()

        # 4. UI Feedback
        self.status_msg.set("Chain Completed and Saved.")
        self.btn_commit.config(state="disabled", text="Chain Complete", bg="#334155")
        self.btn_run.config(state="normal")
        messagebox.showinfo("Success", "Chain finished. Session log saved to _logs/")

    def _save_session_log(self):
        if not os.path.exists("_logs"):
            os.makedirs("_logs")
        
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"_logs/chain_run_{timestamp}.json"
        
        log_data = {
            "state": self.state,
            "chat_history": self.txt_chat.get("1.0", "end-1c"),
            "thoughts": self.txt_thoughts.get("1.0", "end-1c")
        }
        
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(log_data, f, indent=2)
            print(f"Log saved to {filename}")

    def _log_chat(self, role, text):
        self.txt_chat.insert("end", f"\n[{role}]\n{text}\n" + "-"*30 + "\n")
        self.txt_chat.see("end")

    def save_chain(self):
        data = [s["text"].get("1.0", "end-1c") for s in self.task_steps]
        f = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if f:
            with open(f, 'w') as file:
                json.dump(data, file)

    def load_chain(self):
        f = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if f:
            with open(f, 'r') as file:
                data = json.load(file)
            
            for s in self.task_steps: s["frame"].destroy()
            self.task_steps = []
            for text in data: self.add_task_step(text)

if __name__ == "__main__":
    root = tk.Tk()
    app = PromptChainerApp(root)
    root.mainloop()

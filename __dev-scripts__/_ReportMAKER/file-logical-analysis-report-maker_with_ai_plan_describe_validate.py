import os
import ast
import json
import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext

class AIPreservationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Constrained AI Preservation Builder (With Live Logs)")
        self.root.geometry("1100x700") # Expanded to fit side-by-side logs
        
        # --- UI Elements: Top Control Panel ---
        self.control_frame = tk.Frame(root)
        self.control_frame.pack(fill=tk.X, padx=10, pady=5)
        
        tk.Label(self.control_frame, text="System Preservation Exporter", font=("Arial", 14, "bold")).pack(pady=5)
        
        # Controls Grouping
        control_subframe = tk.Frame(self.control_frame)
        control_subframe.pack(pady=5)

        tk.Button(control_subframe, text="1. Select Project Root", command=self.select_folder, width=25).grid(row=0, column=0, padx=5)
        self.folder_label = tk.Label(control_subframe, text="No folder selected", fg="grey")
        self.folder_label.grid(row=0, column=1, padx=5, sticky="w")

        tk.Label(control_subframe, text="2. Select Local AI (Ollama):").grid(row=1, column=0, pady=10, padx=5, sticky="e")
        self.model_var = tk.StringVar(value="None (Fast AST only)")
        self.models = [
            "None (Fast AST only)", 
            "qwen2.5-coder:0.5b", 
            "qwen2.5-coder:1.5b",
            "qwen2.5:0.5b",
            "qwen2.5:1.5b"
        ]
        dropdown = ttk.Combobox(control_subframe, textvariable=self.model_var, values=self.models, state="readonly", width=25)
        dropdown.grid(row=1, column=1, pady=10, padx=5, sticky="w")

        self.gen_btn = tk.Button(control_subframe, text="3. Generate Multi-Pass AI Report", command=self.start_export, width=30, bg="#2E86C1", fg="white")
        self.gen_btn.grid(row=2, column=0, columnspan=2, pady=10)
        
        self.status_label = tk.Label(self.control_frame, text="Waiting to start...", fg="blue")
        self.status_label.pack()

        # --- UI Elements: Side-by-Side Log Panes ---
        self.paned_window = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left Pane: Code View
        self.code_frame = tk.LabelFrame(self.paned_window, text="Current File Code", font=("Arial", 10, "bold"))
        self.code_text = scrolledtext.ScrolledText(self.code_frame, wrap=tk.WORD, font=("Consolas", 9), bg="#f4f4f4")
        self.code_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.paned_window.add(self.code_frame, weight=1)

        # Right Pane: AI Inference Log View
        self.log_frame = tk.LabelFrame(self.paned_window, text="AI Inference Log (Multi-Pass)", font=("Arial", 10, "bold"))
        self.log_text = scrolledtext.ScrolledText(self.log_frame, wrap=tk.WORD, font=("Consolas", 9), bg="#1e1e1e", fg="#00ff00")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.paned_window.add(self.log_frame, weight=1)

        self.source_dir = None

    def select_folder(self):
        self.source_dir = filedialog.askdirectory(title="Select Project Root Folder")
        if self.source_dir:
            self.folder_label.config(text=os.path.basename(self.source_dir), fg="black")

    def update_status(self, text):
        """Helper to update UI safely during synchronous loops."""
        self.status_label.config(text=text)
        self.root.update()

    def set_code_view(self, filename, code_content):
        """Displays the code currently being analyzed."""
        self.code_frame.config(text=f"Current File: {filename}")
        self.code_text.delete(1.0, tk.END)
        self.code_text.insert(tk.END, code_content)
        self.root.update()

    def append_log(self, phase_name, content, clear=False):
        """Appends output to the AI log terminal."""
        if clear:
            self.log_text.delete(1.0, tk.END)
        
        separator = "=" * 50
        header = f"\n{separator}\n>>> {phase_name.upper()}\n{separator}\n\n"
        
        self.log_text.insert(tk.END, header)
        self.log_text.insert(tk.END, content + "\n")
        self.log_text.see(tk.END) # Auto-scroll to bottom
        self.root.update()

    def query_ollama(self, model, prompt):
        """Base function to send a prompt to Ollama."""
        try:
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=120 
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except requests.exceptions.RequestException as e:
            return f"*Failed to reach Ollama ({model}): {str(e)}*"

    def execute_multipass(self, model, code_content, rel_path):
        """Executes the Plan -> Describe -> Validate -> Align inference loop with UI logging."""
        
        self.set_code_view(rel_path, code_content)
        self.append_log("STARTING ANALYSIS", f"Target: {rel_path}\nModel: {model}", clear=True)

        # --- PASS 1: PLAN (The Strategist) ---
        self.update_status(f"[{rel_path}] Pass 1: Planning extraction...")
        prompt_1 = f"""You are a code analysis planner. Review this Python module.
Your job is NOT to describe the file, but to write a 3-4 point checklist of the MOST critical architectural questions that need answering to preserve it. Look for UI loops, background threads, external dependencies, and global state.

FILE CODE:
```python
{code_content}
```

Provide ONLY the short question checklist:"""
        plan = self.query_ollama(model, prompt_1)
        self.append_log("Pass 1: Extraction Plan", plan)
        if plan.startswith("*Failed"): return plan

        # --- PASS 2: DESCRIBE (The Executor) ---
        self.update_status(f"[{rel_path}] Pass 2: Describing against plan...")
        prompt_2 = f"""You are a technical code describer. Read the code and answer the questions in the provided checklist.
Be highly specific to the code provided. Do not invent details.

FILE CODE:
```python
{code_content}
```

CHECKLIST TO ANSWER:
{plan}

Provide your answers clearly:"""
        draft_description = self.query_ollama(model, prompt_2)
        self.append_log("Pass 2: Draft Description", draft_description)
        if draft_description.startswith("*Failed"): return draft_description

        # --- PASS 3: VALIDATE (The Critic) ---
        self.update_status(f"[{rel_path}] Pass 3: Validating draft...")
        prompt_3 = f"""You are a strict senior software architect validating a junior's draft description.

FILE CODE:
```python
{code_content}
```

JUNIOR'S DRAFT:
{draft_description}

Review the code and point out what the draft MISSED or HALLUCINATED regarding:
1. Threading constraints (Did they miss a blocking call or thread handoff?)
2. State ownership (Did they misidentify who owns the data?)
3. Hidden invariants (Are there architectural rules broken?)

If the draft is perfect, reply "No corrections needed." Otherwise, provide bulleted corrections:"""
        critique = self.query_ollama(model, prompt_3)
        self.append_log("Pass 3: Critic's Corrections", critique)
        if critique.startswith("*Failed"): return critique

        # --- PASS 4: ALIGN (The Synthesizer) ---
        self.update_status(f"[{rel_path}] Pass 4: Aligning final blueprint...")
        prompt_4 = f"""You are a software preservation architect finalizing a blueprint.

DRAFT DESCRIPTION:
{draft_description}

CRITIC'S CORRECTIONS:
{critique}

Based ONLY on the draft and the corrections, output ONLY the following Markdown template completed for this file. Keep descriptions brief and highly technical.

- **Ownership Boundaries:**
  - **Owns:** [What state/logic this module strictly controls]
  - **Does NOT Own:** [What it relies on others for]
- **State & Lifecycle:** [Persistent, Ephemeral, or Stateless?]
- **Threading Constraints:** [UI Thread, Background Worker, Async, or None]
- **Invariants:** [Architectural promises that must not be broken]
- **Maturity:** [Stable | Evolving | Experimental]
"""
        final_synthesis = self.query_ollama(model, prompt_4)
        self.append_log("Pass 4: Final Synthesis", final_synthesis)
        return final_synthesis

    def analyze_file(self, file_path, rel_path, selected_model):
        """Extracts structural inventory (AST) AND runs multi-pass AI inference."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_code = f.read()
            
            node = ast.parse(raw_code)
            imports, classes, functions = [], [], []
            module_doc = ast.get_docstring(node) or "No module docstring provided."

            # 1. AST Structural Mapping
            for item in node.body:
                if isinstance(item, ast.Import):
                    for alias in item.names: imports.append(alias.name)
                elif isinstance(item, ast.ImportFrom):
                    imports.append(f"{item.module} (specifics imported)")
                elif isinstance(item, ast.ClassDef):
                    classes.append((item.name, ast.get_docstring(item) or "No description.", [sub.name for sub in item.body if isinstance(sub, ast.FunctionDef)]))
                elif isinstance(item, ast.FunctionDef):
                    functions.append((item.name, ast.get_docstring(item) or "No description."))
            
            report = f"## Module: `{rel_path}`\n\n### 1. Structural Inventory\n**Purpose:** {module_doc.splitlines()[0]}\n\n"
            
            if classes:
                report += "**Classes Extracted:**\n"
                for c_name, c_doc, methods in classes:
                    report += f"- `class {c_name}`: *{c_doc}*\n"
            if functions:
                report += "**Loose Functions:**\n"
                for f_name, f_doc in functions:
                    report += f"- `def {f_name}()`\n"

            report += "\n### 2. Dependency Direction\n**Upstream Dependencies:**\n"
            for imp in imports: report += f"- `{imp}`\n"
            if not imports: report += "*None (Leaf Node)*\n"

            # 2. Multi-Pass AI Execution
            report += "\n### 3. Preservation & Architectural Rules\n"
            if selected_model != "None (Fast AST only)":
                report += f"> *AI Inferred Metadata (Model: {selected_model} | Method: Plan-Describe-Validate-Align)*\n\n"
                ai_response = self.execute_multipass(selected_model, raw_code, os.path.basename(rel_path))
                report += ai_response + "\n"
            else:
                self.set_code_view(rel_path, raw_code)
                self.append_log("AST MODE ONLY", "Skipping AI Inference...", clear=True)
                
                report += "> *Manual Entry Required (No AI selected)*\n"
                report += "- **Ownership Boundaries:**\n  - **Owns:** [TODO]\n  - **Does NOT Own:** [TODO]\n"
                report += "- **State & Lifecycle:** [TODO]\n- **Threading Constraints:** [TODO]\n"
                report += "- **Invariants:** [TODO]\n"

            return report
        except Exception as e:
            return f"Error parsing {rel_path}: {str(e)}"

    def start_export(self):
        if not self.source_dir:
            messagebox.showwarning("Warning", "Please select a folder first!")
            return

        export_path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[('Markdown File', '*.md')])
        if not export_path: return

        selected_model = self.model_var.get()
        self.gen_btn.config(state="disabled")
        self.update_status("Scanning directory tree...")

        subsystems = {}
        total_files = 0

        for root, dirs, files in os.walk(self.source_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', 'env', '__pycache__')]
            for file in files:
                if file.endswith(".py"):
                    rel_path = os.path.relpath(os.path.join(root, file), self.source_dir)
                    subsystem_name = os.path.dirname(rel_path) or "Root Subsystem"
                    if subsystem_name not in subsystems: subsystems[subsystem_name] = []
                    subsystems[subsystem_name].append(os.path.join(root, file))
                    total_files += 1

        processed = 0
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(f"# AI System Preservation Blueprint\n> *Generated with AST mapping & Multi-Pass AI Architectural Inference.*\n\n")
            
            for subsystem, file_paths in subsystems.items():
                f.write(f"\n# ==========================================\n")
                f.write(f"# SUBSYSTEM: {subsystem.upper()}\n")
                f.write(f"# ==========================================\n\n")
                
                for file_path in file_paths:
                    processed += 1
                    rel_path = os.path.relpath(file_path, self.source_dir)
                    
                    self.update_status(f"Processing {processed}/{total_files}: {os.path.basename(file_path)}")
                        
                    f.write(self.analyze_file(file_path, rel_path, selected_model))
                    f.write("\n---\n\n")
                    
        self.update_status("Done!")
        self.append_log("COMPLETE", f"Finished processing {total_files} files.", clear=False)
        self.gen_btn.config(state="normal")
        messagebox.showinfo("Success", f"Preservation Blueprint exported to:\n{export_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = AIPreservationApp(root)
    root.mainloop()
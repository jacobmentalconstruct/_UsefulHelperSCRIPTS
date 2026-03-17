import os
import ast
import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import ollama

# ==========================================
# CLASS 1: OLLAMA GOVERNOR
# ==========================================
class OllamaGovernor:
    # Pre-defined safety tiers
    TIERS = {
        "VRAM Only (Fastest)": {"ctx": 8192, "predict": 512, "color": "#2ecc71"},
        "Balanced (MoE)":      {"ctx": 16384, "predict": 1024, "color": "#f1c40f"},
        "Deep Logic (Slow)":   {"ctx": 32768, "predict": 2048, "color": "#e67e22"},
        "Extreme (Risk)":      {"ctx": 65536, "predict": 4096, "color": "#e74c3c"}
    }

    def __init__(self):
        self.client = ollama

    def get_models(self, search_term=None):
        """Fetches models from Ollama, optionally filtered by name."""
        try:
            response = self.client.list()
            models = [m.get('name', m) for m in response.get('models', [])]
            if search_term:
                return [m for m in models if search_term.lower() in m.lower()]
            return models
        except Exception as e:
            print(f"Error connecting to Ollama: {e}")
            return []

    def run_inference(self, model, prompt, tier_name, custom_limit=None):
        """Executes chat with enforced token governors to protect VRAM/RAM."""
        tier = self.TIERS.get(tier_name, self.TIERS["VRAM Only (Fastest)"])
        ctx_limit = int(custom_limit) if custom_limit else tier["ctx"]

        options = {
            "num_ctx": ctx_limit,
            "num_predict": tier["predict"],
            "temperature": 0.7
        }

        return self.client.chat(
            model=model,
            messages=[{'role': 'user', 'content': prompt}],
            options=options
        )

    def get_ui_widget(self, parent, search=""):
        """Returns a modular Tkinter Frame for injection into larger apps."""
        frame = ttk.LabelFrame(parent, text="2. Local AI Governor (Ollama)", padding=10)
        frame.columnconfigure(1, weight=1)

        # Model Selection
        ttk.Label(frame, text="Model:").grid(row=0, column=0, sticky="w", padx=5)
        model_list = ["None (Fast AST only)"] + self.get_models(search)
        model_var = tk.StringVar(value=model_list[0] if model_list else "None (Fast AST only)")
        model_drop = ttk.Combobox(frame, textvariable=model_var, values=model_list, state="readonly", width=35)
        model_drop.grid(row=0, column=1, pady=5, sticky="ew")

        # Tier Selection
        ttk.Label(frame, text="Safety Tier:").grid(row=1, column=0, sticky="w", padx=5)
        tier_var = tk.StringVar(value="VRAM Only (Fastest)")
        tier_drop = ttk.Combobox(frame, textvariable=tier_var, values=list(self.TIERS.keys()), state="readonly")
        tier_drop.grid(row=1, column=1, pady=5, sticky="ew")

        # Enforced Max Token Input
        ttk.Label(frame, text="Enforced Max:").grid(row=2, column=0, sticky="w", padx=5)
        token_var = tk.StringVar(value=str(self.TIERS["VRAM Only (Fastest)"]["ctx"]))
        token_entry = ttk.Entry(frame, textvariable=token_var)
        token_entry.grid(row=2, column=1, pady=5, sticky="ew")

        # Logic to update Entry when Tier changes
        def update_limit(*args):
            new_val = self.TIERS[tier_var.get()]["ctx"]
            token_var.set(str(new_val))

        tier_var.trace_add("write", update_limit)

        return frame, {"model": model_var, "tier": tier_var, "tokens": token_var}


# ==========================================
# CLASS 2: MAIN APPLICATION
# ==========================================
class AIPreservationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Constrained AI Preservation Builder (With Governor)")
        self.root.geometry("1100x750")

        self.governor = OllamaGovernor()
        self.source_dir = None

        # --- UI Elements: Top Control Panel ---
        self.control_frame = tk.Frame(root)
        self.control_frame.pack(fill=tk.X, padx=10, pady=5)

        tk.Label(self.control_frame, text="System Preservation Exporter", font=("Arial", 14, "bold")).pack(pady=5)

        control_subframe = tk.Frame(self.control_frame)
        control_subframe.pack(pady=5)

        # Step 1: Folder Select
        folder_frame = tk.Frame(control_subframe)
        folder_frame.grid(row=0, column=0, pady=5, sticky="ew")
        tk.Button(folder_frame, text="1. Select Project Root", command=self.select_folder, width=25).pack(side=tk.LEFT, padx=5)
        self.folder_label = tk.Label(folder_frame, text="No folder selected", fg="grey")
        self.folder_label.pack(side=tk.LEFT, padx=5)

        # Step 2: Inject the Governor UI
        self.gov_frame, self.gov_vars = self.governor.get_ui_widget(control_subframe)
        self.gov_frame.grid(row=1, column=0, pady=10, sticky="ew")

        # Step 3: Generation Button
        self.gen_btn = tk.Button(
            control_subframe,
            text="3. Generate Multi-Pass AI Report",
            command=self.start_export,
            width=30,
            bg="#2E86C1",
            fg="white"
        )
        self.gen_btn.grid(row=2, column=0, pady=10)

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

    def select_folder(self):
        self.source_dir = filedialog.askdirectory(title="Select Project Root Folder")
        if self.source_dir:
            self.folder_label.config(text=os.path.basename(self.source_dir), fg="black")

    def update_status(self, text):
        self.status_label.config(text=text)
        self.root.update()

    def set_code_view(self, filename, code_content):
        self.code_frame.config(text=f"Current File: {filename}")
        self.code_text.delete(1.0, tk.END)
        self.code_text.insert(tk.END, code_content)
        self.root.update()

    def append_log(self, phase_name, content, clear=False):
        if clear:
            self.log_text.delete(1.0, tk.END)
        separator = "=" * 50
        header = f"\n{separator}\n>>> {phase_name.upper()}\n{separator}\n\n"
        self.log_text.insert(tk.END, header)
        self.log_text.insert(tk.END, content + "\n")
        self.log_text.see(tk.END)
        self.root.update()

    def query_ollama(self, model, prompt):
        """Uses the connected Governor to handle the Ollama request securely."""
        try:
            tier_name = self.gov_vars["tier"].get()
            custom_limit = self.gov_vars["tokens"].get()
            response = self.governor.run_inference(model, prompt, tier_name, custom_limit)
            return response['message']['content'].strip()
        except Exception as e:
            return f"*Failed to reach Ollama ({model}): {str(e)}*"

    def execute_multipass(self, model, code_content, rel_path):
        self.set_code_view(rel_path, code_content)
        self.append_log("STARTING ANALYSIS", f"Target: {rel_path}\nModel: {model}", clear=True)

        # PASS 1: PLAN
        self.update_status(f"[{rel_path}] Pass 1: Planning extraction...")
        prompt_1 = f"""You are a code analysis planner. Review this Python module.
Write a 3-4 point checklist of the MOST critical architectural questions that need answering to preserve it. Look for UI loops, background threads, external dependencies, and global state.

FILE CODE:
```python
{code_content}
```
Provide ONLY the short question checklist:"""
        plan = self.query_ollama(model, prompt_1)
        self.append_log("Pass 1: Extraction Plan", plan)
        if plan.startswith("*Failed"):
            return plan

        # PASS 2: DESCRIBE
        self.update_status(f"[{rel_path}] Pass 2: Describing against plan...")
        prompt_2 = f"""You are a technical code describer. Read the code and answer the questions in the provided checklist based ONLY on the code.

FILE CODE:
```python
{code_content}
```

CHECKLIST TO ANSWER:
{plan}

Provide your answers clearly:"""
        draft_description = self.query_ollama(model, prompt_2)
        self.append_log("Pass 2: Draft Description", draft_description)
        if draft_description.startswith("*Failed"):
            return draft_description

        # PASS 3: VALIDATE
        self.update_status(f"[{rel_path}] Pass 3: Validating draft...")
        prompt_3 = f"""You are a strict senior software architect validating a junior's draft description.

FILE CODE:
```python
{code_content}
```

JUNIOR'S DRAFT:
{draft_description}

Review the code and point out what the draft MISSED or HALLUCINATED regarding threading constraints, state ownership, or hidden invariants. If perfect, reply 'No corrections needed.' Otherwise, provide bulleted corrections:"""
        critique = self.query_ollama(model, prompt_3)
        self.append_log("Pass 3: Critic's Corrections", critique)
        if critique.startswith("*Failed"):
            return critique

        # PASS 4: ALIGN
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
- **Maturity:** [Stable | Evolving | Experimental]"""
        final_synthesis = self.query_ollama(model, prompt_4)
        self.append_log("Pass 4: Final Synthesis", final_synthesis)
        return final_synthesis

    def analyze_file(self, file_path, rel_path, selected_model):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_code = f.read()

            node = ast.parse(raw_code)
            imports, classes, functions = [], [], []
            module_doc = ast.get_docstring(node) or "No module docstring provided."

            for item in node.body:
                if isinstance(item, ast.Import):
                    for alias in item.names:
                        imports.append(alias.name)
                elif isinstance(item, ast.ImportFrom):
                    imports.append(f"{item.module} (specifics imported)")
                elif isinstance(item, ast.ClassDef):
                    classes.append((
                        item.name,
                        ast.get_docstring(item) or "No description.",
                        [sub.name for sub in item.body if isinstance(sub, ast.FunctionDef)]
                    ))
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
            for imp in imports:
                report += f"- `{imp}`\n"
            if not imports:
                report += "*None (Leaf Node)*\n"

            report += "\n### 3. Preservation & Architectural Rules\n"
            if "None" not in selected_model:
                report += f"> *AI Inferred Metadata (Model: {selected_model} | Method: Plan-Describe-Validate-Align)*\n\n"
                ai_response = self.execute_multipass(selected_model, raw_code, os.path.basename(rel_path))
                report += ai_response + "\n"
            else:
                self.set_code_view(rel_path, raw_code)
                self.append_log("AST MODE ONLY", "Skipping AI Inference...", clear=True)
                report += "> *Manual Entry Required (No AI selected)*\n"
                report += "- **Ownership Boundaries:**\n  - **Owns:** [TODO]\n  - **Does NOT Own:** [TODO]\n"
                report += "- **State & Lifecycle:** [TODO]\n"
                report += "- **Threading Constraints:** [TODO]\n"
                report += "- **Invariants:** [TODO]\n"

            return report
        except Exception as e:
            return f"Error parsing {rel_path}: {str(e)}"

    def start_export(self):
        if not self.source_dir:
            messagebox.showwarning("Warning", "Please select a folder first!")
            return

        export_path = filedialog.asksaveasfilename(
            defaultextension=".md",
            filetypes=[('Markdown File', '*.md')]
        )
        if not export_path:
            return

        selected_model = self.gov_vars["model"].get()
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
                    if subsystem_name not in subsystems:
                        subsystems[subsystem_name] = []
                    subsystems[subsystem_name].append(os.path.join(root, file))
                    total_files += 1

        processed = 0
        with open(export_path, "w", encoding="utf-8") as f:
            f.write("# AI System Preservation Blueprint\n")
            f.write("> *Generated with AST mapping & Multi-Pass AI Architectural Inference.*\n\n")

            for subsystem, file_paths in subsystems.items():
                f.write("\n# ==========================================\n")
                f.write(f"# SUBSYSTEM: {subsystem.upper()}\n")
                f.write("# ==========================================\n\n")

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

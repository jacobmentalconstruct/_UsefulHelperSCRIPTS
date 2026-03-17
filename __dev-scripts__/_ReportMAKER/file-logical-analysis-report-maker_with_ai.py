import os
import ast
import json
import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

class AIPreservationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI-Assisted Preservation Builder")
        self.root.geometry("500x320")
        
        # --- UI Elements ---
        tk.Label(root, text="System Preservation Exporter", font=("Arial", 14, "bold")).pack(pady=10)
        
        # Folder Selection
        tk.Button(root, text="1. Select Project Root", command=self.select_folder, width=30).pack(pady=5)
        self.folder_label = tk.Label(root, text="No folder selected", fg="grey")
        self.folder_label.pack()

        # Model Selection
        tk.Label(root, text="2. Select Local AI (Ollama):").pack(pady=(10, 0))
        self.model_var = tk.StringVar(value="None (Fast AST only)")
        self.models = [
            "None (Fast AST only)", 
            "qwen2.5-coder:0.5b", 
            "qwen2.5-coder:1.5b",
            "qwen2.5:0.5b",
            "qwen2.5:1.5b"
        ]
        dropdown = ttk.Combobox(root, textvariable=self.model_var, values=self.models, state="readonly", width=27)
        dropdown.pack()

        # Generate Button
        self.gen_btn = tk.Button(root, text="3. Generate AI Preservation Report", command=self.start_export, width=30, bg="#2E86C1", fg="white")
        self.gen_btn.pack(pady=20)
        
        self.status_label = tk.Label(root, text="", fg="blue")
        self.status_label.pack()

        self.source_dir = None

    def select_folder(self):
        self.source_dir = filedialog.askdirectory(title="Select Project Root Folder")
        if self.source_dir:
            self.folder_label.config(text=os.path.basename(self.source_dir), fg="black")

    def ask_ollama(self, model, code_content):
        """Sends the code to local Ollama to infer architecture rules."""
        prompt = f"""You are an expert software preservation architect.
Review the following Python module and determine its architectural boundaries.

FILE CODE:
```python
{code_content}
```

Respond ONLY with the following Markdown template completed based on your analysis of the code. Be brief and highly technical.

- **Ownership Boundaries:**
  - **Owns:** [What state/logic this module strictly controls]
  - **Does NOT Own:** [What it relies on others for]
- **State & Lifecycle:** [Persistent, Ephemeral, or Stateless?]
- **Threading Constraints:** [UI Thread, Background Worker, Async, or None]
- **Invariants:** [Architectural promises that must not be broken]
- **Maturity:** [Stable | Evolving | Experimental]
"""
        try:
            # Assumes Ollama is running on the default local port
            response = requests.post(
                "http://localhost:11434/api/generate",
                json={"model": model, "prompt": prompt, "stream": False},
                timeout=60 # small models should be fast, but we give it a minute just in case
            )
            response.raise_for_status()
            return response.json().get("response", "").strip()
        except requests.exceptions.RequestException as e:
            return f"*Failed to reach Ollama ({model}): {str(e)}*"

    def analyze_file(self, file_path, rel_path, selected_model):
        """Extracts structural inventory (AST) AND asks AI for Preservation metadata."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                raw_code = f.read()
            
            # Parse the Abstract Syntax Tree (AST) to extract exact structure
            node = ast.parse(raw_code)
            
            imports, classes, functions = [], [], []
            module_doc = ast.get_docstring(node) or "No module docstring provided."

            # 1. AST: Map Dependencies & Structure
            for item in node.body:
                if isinstance(item, ast.Import):
                    for alias in item.names: imports.append(alias.name)
                elif isinstance(item, ast.ImportFrom):
                    imports.append(f"{item.module} (specifics imported)")
                elif isinstance(item, ast.ClassDef):
                    classes.append((item.name, ast.get_docstring(item) or "No description.", [sub.name for sub in item.body if isinstance(sub, ast.FunctionDef)]))
                elif isinstance(item, ast.FunctionDef):
                    functions.append((item.name, ast.get_docstring(item) or "No description."))
            
            # 2. Build Structural Output (Guaranteed 100% accurate via AST)
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

            # 3. AI Preservation Extraction (Filling the semantic gap)
            report += "\n### 3. Preservation & Architectural Rules\n"
            if selected_model != "None (Fast AST only)":
                report += "> *AI Inferred Metadata (Model: " + selected_model + ")*\n\n"
                ai_response = self.ask_ollama(selected_model, raw_code)
                report += ai_response + "\n"
            else:
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
        self.status_label.config(text="Scanning files & talking to Ollama... Please wait.")
        self.root.update()

        subsystems = {}
        total_files = 0

        # Gather files, ignoring hidden directories, virtual environments, and caches
        for root, dirs, files in os.walk(self.source_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', 'env', '__pycache__')]
            for file in files:
                if file.endswith(".py"):
                    rel_path = os.path.relpath(os.path.join(root, file), self.source_dir)
                    subsystem_name = os.path.dirname(rel_path) or "Root Subsystem"
                    if subsystem_name not in subsystems: subsystems[subsystem_name] = []
                    subsystems[subsystem_name].append(os.path.join(root, file))
                    total_files += 1

        # Process and write the report
        processed = 0
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(f"# AI System Preservation Blueprint\n> *Generated with AST mapping & AI architectural inference.*\n\n")
            
            for subsystem, file_paths in subsystems.items():
                f.write(f"\n# ==========================================\n")
                f.write(f"# SUBSYSTEM: {subsystem.upper()}\n")
                f.write(f"# ==========================================\n\n")
                
                for file_path in file_paths:
                    processed += 1
                    self.status_label.config(text=f"Processing {processed}/{total_files}: {os.path.basename(file_path)}")
                    self.root.update() # Keeps UI from freezing entirely
                    
                    rel_path = os.path.relpath(file_path, self.source_dir)
                    f.write(self.analyze_file(file_path, rel_path, selected_model))
                    f.write("\n---\n\n")
                    
        self.status_label.config(text="Done!")
        self.gen_btn.config(state="normal")
        messagebox.showinfo("Success", f"Preservation Blueprint exported to:\n{export_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = AIPreservationApp(root)
    root.mainloop()
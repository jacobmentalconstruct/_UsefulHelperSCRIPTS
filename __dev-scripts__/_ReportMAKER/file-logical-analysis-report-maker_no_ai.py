import os
import ast
import tkinter as tk
from tkinter import filedialog, messagebox

class PreservationBlueprintApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CodeMONKEY Preservation Builder")
        self.root.geometry("450x200")
        
        tk.Label(root, text="System Preservation Exporter", font=("Arial", 14, "bold")).pack(pady=10)
        
        tk.Button(root, text="1. Select Project Root", command=self.select_folder, width=30).pack(pady=5)
        self.folder_label = tk.Label(root, text="No folder selected", fg="grey")
        self.folder_label.pack()

        tk.Button(root, text="2. Generate Preservation Report", command=self.export_blueprint, width=30, bg="#2E86C1", fg="white").pack(pady=20)
        
        self.source_dir = None

    def select_folder(self):
        self.source_dir = filedialog.askdirectory(title="Select Project Root Folder")
        if self.source_dir:
            self.folder_label.config(text=os.path.basename(self.source_dir), fg="black")

    def analyze_file(self, file_path, rel_path):
        """Extracts structural inventory AND dependency direction."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                node = ast.parse(f.read())
            
            imports = []
            classes = []
            functions = []
            
            module_doc = ast.get_docstring(node) or "No module docstring provided."

            for item in node.body:
                # 1. Map Dependencies (Directionality)
                if isinstance(item, ast.Import):
                    for alias in item.names:
                        imports.append(alias.name)
                elif isinstance(item, ast.ImportFrom):
                    imports.append(f"{item.module} (specifics imported)")
                
                # 2. Map Structural Inventory
                elif isinstance(item, ast.ClassDef):
                    class_doc = ast.get_docstring(item) or "No description."
                    methods = [sub.name for sub in item.body if isinstance(sub, ast.FunctionDef)]
                    classes.append((item.name, class_doc.splitlines()[0], methods))
                    
                elif isinstance(item, ast.FunctionDef):
                    func_doc = ast.get_docstring(item) or "No description."
                    functions.append((item.name, func_doc.splitlines()[0]))
            
            return self.format_module_report(rel_path, module_doc, imports, classes, functions)
        except Exception as e:
            return f"Error parsing {rel_path}: {str(e)}"

    def format_module_report(self, filename, module_doc, imports, classes, functions):
        """Scaffolds the exact Preservation Metadata the agent requested."""
        
        report = f"## Module: `{filename}`\n\n"
        
        # --- PASS 1: Structural Inventory ---
        report += "### 1. Structural Inventory\n"
        report += f"**Purpose:** {module_doc.splitlines()[0]}\n\n"
        
        if classes:
            report += "**Classes Extracted:**\n"
            for c_name, c_doc, methods in classes:
                report += f"- `class {c_name}`: *{c_doc}*\n"
                for m in methods:
                    report += f"  - `def {m}()`\n"
        if functions:
            report += "**Loose Functions:**\n"
            for f_name, f_doc in functions:
                report += f"- `def {f_name}()`: *{f_doc}*\n"
                
        # --- PASS 2: Dependency Direction ---
        
        report += "\n### 2. Dependency Direction\n"
        if imports:
            report += "**Upstream Dependencies (This module relies on):**\n"
            for imp in imports:
                report += f"- `{imp}`\n"
        else:
            report += "*No internal/external imports detected (Leaf Node).* \n"
        report += "**Downstream Consumers:** `[PENDING: Cross-reference analysis]`\n"

        # --- PASS 3: Preservation Metadata (Template) ---
        report += "\n### 3. Preservation & Architectural Rules\n"
        report += "> *Note: The following fields require architectural definition to prevent drift.*\n\n"
        report += "- **Ownership Boundaries:**\n"
        report += "  - **Owns:** `[TODO: State what this module strictly controls]`\n"
        report += "  - **Does NOT Own:** `[TODO: What is this module forbidden from doing?]`\n"
        report += "- **State & Lifecycle:**\n"
        report += "  - **Authoritative State:** `[TODO: Persistent, Ephemeral, or Stateless?]`\n"
        report += "- **Threading / Event-Loop Constraints:** `[TODO: UI Thread, Background Worker, or Async?]`\n"
        report += "- **Invariants:** `[TODO: Architectural promises that must not be broken]`\n"
        report += "- **Reconstruction Path:** `[TODO: How to rebuild if lost]`\n"
        report += "- **Maturity:** `[Stable | Evolving | Experimental | Legacy]`\n"
        
        return report

    def export_blueprint(self):
        if not self.source_dir:
            messagebox.showwarning("Warning", "Please select a folder first!")
            return

        export_path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[('Markdown File', '*.md')])
        if not export_path: return

        # Group by Subsystem (Folder)
        subsystems = {}
        
        for root, dirs, files in os.walk(self.source_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', '__pycache__')]
            for file in files:
                if file.endswith(".py"):
                    rel_path = os.path.relpath(os.path.join(root, file), self.source_dir)
                    subsystem_name = os.path.dirname(rel_path) or "Root Subsystem"
                    
                    if subsystem_name not in subsystems:
                        subsystems[subsystem_name] = []
                    subsystems[subsystem_name].append(os.path.join(root, file))

        # Write Report
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(f"# System Preservation Blueprint: {os.path.basename(self.source_dir)}\n")
            f.write("> *Generated to capture structural inventory, dependency direction, and preservation metadata.*\n\n")
            
            for subsystem, file_paths in subsystems.items():
                f.write(f"\n# ==========================================\n")
                f.write(f"# SUBSYSTEM: {subsystem.upper()}\n")
                f.write(f"# ==========================================\n\n")
                
                for file_path in file_paths:
                    rel_path = os.path.relpath(file_path, self.source_dir)
                    f.write(self.analyze_file(file_path, rel_path))
                    f.write("\n---\n\n")
                    
        messagebox.showinfo("Success", f"Preservation Blueprint exported to:\n{export_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = PreservationBlueprintApp(root)
    root.mainloop()
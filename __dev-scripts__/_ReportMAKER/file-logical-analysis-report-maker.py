import os
import re
import ast
import tkinter as tk
from tkinter import filedialog, messagebox

class BlueprintApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CodeMONKEY Blueprint Export")
        self.root.geometry("400x200")
        
        # UI Elements
        tk.Label(root, text="App Blueprint Generator", font=("Arial", 14, "bold")).pack(pady=10)
        
        tk.Button(root, text="1. Select Project Folder", command=self.select_folder, width=25).pack(pady=5)
        self.folder_label = tk.Label(root, text="No folder selected", fg="grey")
        self.folder_label.pack()

        tk.Button(root, text="2. Generate & Export", command=self.export_blueprint, width=25, bg="#4CAF50", fg="white").pack(pady=20)
        
        self.source_dir = None

    def select_folder(self):
        self.source_dir = filedialog.askdirectory(title="Select Project Root Folder")
        if self.source_dir:
            self.folder_label.config(text=os.path.basename(self.source_dir), fg="black")

    def parse_python_file(self, file_path):
        """Extracts NL descriptions of logic using Python's Abstract Syntax Tree."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                node = ast.parse(f.read())
            
            logic = []
            module_doc = ast.get_docstring(node)
            if module_doc:
                logic.append(f"**Module Purpose:** {module_doc.splitlines()[0]}")

            for item in node.body:
                if isinstance(item, ast.ClassDef):
                    logic.append(f"\n- **Class `{item.name}`**")
                    class_doc = ast.get_docstring(item)
                    if class_doc: logic.append(f"  *Intent: {class_doc.splitlines()[0]}*")
                    
                    for sub in item.body:
                        if isinstance(sub, ast.FunctionDef):
                            doc = ast.get_docstring(sub) or "Processes logic."
                            logic.append(f"  - `method {sub.name}()`: {doc.splitlines()[0]}")
                            
                elif isinstance(item, ast.FunctionDef):
                    doc = ast.get_docstring(item) or "Performs an action."
                    logic.append(f"- `function {item.name}()`: {doc.splitlines()[0]}")
            
            return "\n".join(logic)
        except Exception as e:
            return f"Error parsing: {str(e)}"

    def export_blueprint(self):
        if not self.source_dir:
            messagebox.showwarning("Warning", "Please select a folder first!")
            return

        # Pick save location
        file_types = [('Markdown File', '*.md'), ('Text File', '*.txt'), ('HTML Webpage', '*.html')]
        export_path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=file_types)
        
        if not export_path:
            return

        blueprint_data = f"# Blueprint: {os.path.basename(self.source_dir)}\n\n"
        
        # Walk through files
        for root, dirs, files in os.walk(self.source_dir):
            # Skip hidden/venv folders
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('venv', '__pycache__')]
            
            for file in files:
                if file.endswith(".py"):
                    rel_path = os.path.relpath(os.path.join(root, file), self.source_dir)
                    blueprint_data += f"## File: `{rel_path}`\n"
                    blueprint_data += self.parse_python_file(os.path.join(root, file))
                    blueprint_data += "\n\n---\n\n"

        # Final write
        with open(export_path, "w", encoding="utf-8") as f:
            f.write(blueprint_data)
            
        messagebox.showinfo("Success", f"Blueprint exported to {os.path.basename(export_path)}")

if __name__ == "__main__":
    root = tk.Tk()
    app = BlueprintApp(root)
    root.mainloop()
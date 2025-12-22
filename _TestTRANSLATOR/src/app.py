import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import json
import urllib.request
import urllib.error
import os
import threading
import re
import ast

class LogicInjector:
    def __init__(self, root):
        self.root = root
        self.root.title("_LogicINJECTOR (Mad Libs Architecture)")
        self.root.geometry("750x700")
        
        # Variables
        self.origin_path = tk.StringVar()
        self.boiler_path = tk.StringVar()
        self.output_folder = tk.StringVar()
        self.output_name = tk.StringVar()
        self.selected_model = tk.StringVar()

        # Check/Create External Prompt
        self.prompt_file = "injector_prompt.txt"
        self.ensure_prompt_file()

        # UI Layout
        self.create_widgets()
        
        # Load models in background
        threading.Thread(target=self.fetch_models, daemon=True).start()

    def clean_logic_with_ast(self, dirty_code):
            """
            Uses Python's AST to find the 'execute' function inside the AI's output
            and extract ONLY its body lines, preserving comments.
            """
            try:
                # 1. Parse the dirty code into a Tree
                tree = ast.parse(dirty_code)
                
                target_node = None
                # 2. Walk the tree to find the 'execute' function definition
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name == 'execute':
                        target_node = node
                        break
                
                # 3. If found, slice the original string using line numbers
                if target_node and target_node.body:
                    # Get start and end lines of the BODY (skipping the 'def execute' line)
                    start_line = target_node.body[0].lineno - 1
                    end_line = target_node.body[-1].end_lineno
                    
                    lines = dirty_code.splitlines()
                    # Extract the block
                    body_lines = lines[start_line:end_line]
                    
                    # 4. Auto-Dedent the block
                    # (Find the indentation of the first line and remove it from all lines)
                    if body_lines:
                        first_line = body_lines[0]
                        indent_len = len(first_line) - len(first_line.lstrip())
                        cleaned_lines = [line[indent_len:] if len(line) >= indent_len else line for line in body_lines]
                        return "\n".join(cleaned_lines)
                
                # If no 'execute' function found, maybe the AI respected us? Return as is.
                return dirty_code

            except Exception as e:
                self.log(f"AST Warning: Could not parse AI output ({e}). Using raw.")
                return dirty_code

    def ensure_prompt_file(self):
        """Creates the Extraction Prompt (Mad Libs Style)."""
        # Note: We overwrite the old prompt because the strategy has changed.
        prompt_content = (
            "You are a Code Extraction Engine.\n"
            "OBJECTIVE: Analyze the ORIGIN python file and extract 3 specific components.\n"
            "OUTPUT FORMAT: Wrap content in XML tags. Do not output the whole file.\n\n"
            "<IMPORTS>\n(Paste all import statements here. Include 'import multiprocessing as mp' if present.)\n</IMPORTS>\n\n"
            "<HELPERS>\n(Paste any global helper functions starting with '_' here, e.g., 'def _isolated_worker...'. Copy them EXACTLY.)\n</HELPERS>\n\n"
            "<LOGIC>\n(Refactor the main execution logic to fit inside a class method. Indent it by 8 spaces. Use 'self.config' if needed.)\n</LOGIC>\n\n"
            "SYSTEM NOTE: Do not chat. Only output these three tagged blocks."
        )
        with open(self.prompt_file, "w", encoding="utf-8") as f:
            f.write(prompt_content)

    def create_widgets(self):
        # ... (Standard UI boilerplate) ...
        paddings = {'padx': 10, 'pady': (5, 0)}
        
        tk.Label(self.root, text="1. Origin Logic File:").pack(anchor="w", **paddings)
        frame1 = tk.Frame(self.root); frame1.pack(fill="x", padx=10)
        tk.Entry(frame1, textvariable=self.origin_path).pack(side="left", fill="x", expand=True)
        tk.Button(frame1, text="Browse", command=lambda: self.pick_file(self.origin_path)).pack(side="right")

        tk.Label(self.root, text="2. Boilerplate File (Must have '# [INJECT LOGIC HERE]'):").pack(anchor="w", **paddings)
        frame2 = tk.Frame(self.root); frame2.pack(fill="x", padx=10)
        tk.Entry(frame2, textvariable=self.boiler_path).pack(side="left", fill="x", expand=True)
        tk.Button(frame2, text="Browse", command=lambda: self.pick_file(self.boiler_path)).pack(side="right")

        tk.Label(self.root, text="3. Ollama Model:").pack(anchor="w", **paddings)
        self.model_combo = ttk.Combobox(self.root, textvariable=self.selected_model, state="readonly")
        self.model_combo.pack(fill="x", padx=10)

        tk.Label(self.root, text="4. Output Folder:").pack(anchor="w", **paddings)
        frame4 = tk.Frame(self.root); frame4.pack(fill="x", padx=10)
        tk.Entry(frame4, textvariable=self.output_folder).pack(side="left", fill="x", expand=True)
        tk.Button(frame4, text="Browse", command=lambda: self.pick_folder(self.output_folder)).pack(side="right")

        tk.Label(self.root, text="5. Output Filename:").pack(anchor="w", **paddings)
        tk.Entry(self.root, textvariable=self.output_name).pack(fill="x", padx=10)

        # START BUTTON
        self.btn_run = tk.Button(self.root, text="EXTRACT & ASSEMBLE", command=self.start_thread, bg="#dddddd", height=2)
        self.btn_run.pack(fill="x", padx=10, pady=15)

        # LOGGING WINDOW
        tk.Label(self.root, text="Process Log:").pack(anchor="w", padx=10)
        self.log_window = scrolledtext.ScrolledText(self.root, height=15, state='disabled', font=("Consolas", 9))
        self.log_window.pack(fill="both", expand=True, padx=10, pady=5)

    def log(self, message):
        def _append():
            self.log_window.config(state='normal')
            self.log_window.insert(tk.END, message + "\n")
            self.log_window.see(tk.END)
            self.log_window.config(state='disabled')
        self.root.after(0, _append)

    def pick_file(self, var):
        f = filedialog.askopenfilename()
        if f: var.set(f)
    
    def pick_folder(self, var):
        f = filedialog.askdirectory()
        if f: var.set(f)

    def fetch_models(self):
        try:
            with urllib.request.urlopen("http://localhost:11434/api/tags") as r:
                data = json.loads(r.read().decode())
                models = [m['name'] for m in data['models']]
                self.root.after(0, lambda: self.model_combo.config(values=models))
                if models: self.root.after(0, lambda: self.model_combo.current(0))
        except:
            self.log("Error: Could not fetch models.")

    def start_thread(self):
        if not all([self.origin_path.get(), self.boiler_path.get(), self.output_folder.get(), self.output_name.get()]):
            messagebox.showerror("Error", "All fields required.")
            return
        
        self.btn_run.config(state="disabled", text="Working...")
        self.log_window.config(state='normal'); self.log_window.delete(1.0, tk.END); self.log_window.config(state='disabled')
        threading.Thread(target=self.run_injection, daemon=True).start()

    def run_injection(self):
        try:
            self.log("--- Starting Mad Libs Assembly ---")
            
            # 1. READ FILES (With strict error handling for encoding)
            self.log("Reading files...")
            with open(self.origin_path.get(), 'r', encoding='utf-8', errors='ignore') as f: 
                origin_content = f.read()
            with open(self.boiler_path.get(), 'r', encoding='utf-8', errors='ignore') as f: 
                boiler_content = f.read()
            with open(self.prompt_file, 'r', encoding='utf-8') as f:
                system_prompt = f.read()

            # 2. ASK OLLAMA TO FILL THE TAGS
            user_prompt = f"==== ORIGIN CODE ====\n{origin_content}"
            
            payload = {
                "model": self.selected_model.get(),
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_ctx": 8192} 
            }

            self.log(f"Requesting Extraction from {self.selected_model.get()}...")
            
            req = urllib.request.Request("http://localhost:11434/api/chat", 
                                         data=json.dumps(payload).encode('utf-8'), 
                                         headers={'Content-Type': 'application/json'})
            
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode('utf-8'))
                ai_output = result['message']['content']
                self.log("Received AI response. Parsing tags...")

            # 3. PARSE TAGS (REGEX)
                        imports = re.search(r"<IMPORTS>(.*?)</IMPORTS>", ai_output, re.DOTALL)
                        helpers = re.search(r"<HELPERS>(.*?)</HELPERS>", ai_output, re.DOTALL)
                        logic   = re.search(r"<LOGIC>(.*?)</LOGIC>", ai_output, re.DOTALL)

                        imports_code = imports.group(1).strip() if imports else ""
                        helpers_code = helpers.group(1).strip() if helpers else ""
                        
                        # --- AST CLEANER ---
                        if logic:
                            raw_logic = logic.group(1)
                            
                            # 1. Run the AST surgery (Stripping wrappers + auto-dedenting)
                            cleaned_logic = self.clean_logic_with_ast(raw_logic)
                            
                            # 2. Force 8-space indentation for the final Boilerplate insertion
                            logic_lines = cleaned_logic.splitlines()
                            indented_lines = ["        " + line for line in logic_lines]
                            logic_code = "\n".join(indented_lines)
                        else:
                            logic_code = "        # NO LOGIC DETECTED"

                        self.log(f"Extracted:\n- Imports: {len(imports_code)} chars\n- Helpers: {len(helpers_code)} chars\n- Logic: {len(logic_code)} chars")

            # 4. ASSEMBLE THE MAD LIB
            # A. Inject Imports at the very top
            final_code = f"{imports_code}\n\n{boiler_content}"

            # B. Inject Logic (Find the placeholder)
            if "# [INJECT LOGIC HERE]" in final_code:
                final_code = final_code.replace("# [INJECT LOGIC HERE]", logic_code)
            else:
                self.log("WARNING: Placeholder '# [INJECT LOGIC HERE]' not found. Appending logic to end (unsafe).")
                final_code += f"\n\n# ORPHANED LOGIC:\n{logic_code}"

            # C. Inject Helpers (Before the class definition is usually best, but top level works too)
            # We will insert them right after the imports/metadata block
            # A simple trick: Insert them before "class "
            if "class " in final_code:
                parts = final_code.split("class ", 1)
                final_code = f"{parts[0]}\n\n# --- HELPERS ---\n{helpers_code}\n\nclass {parts[1]}"
            else:
                final_code += f"\n\n{helpers_code}"

            # 5. SAVE
            final_path = os.path.join(self.output_folder.get(), self.output_name.get())
            with open(final_path, 'w', encoding='utf-8') as f:
                f.write(final_code)
            
            self.log(f"SUCCESS: Assembled file saved to {final_path}")
            self.root.after(0, lambda: messagebox.showinfo("Success", "Mad Libs Assembly Complete!"))

        except Exception as e:
            self.log(f"CRITICAL ERROR: {str(e)}")
            print(e)
        finally:
            self.root.after(0, lambda: self.btn_run.config(state="normal", text="EXTRACT & ASSEMBLE"))

if __name__ == "__main__":
    root = tk.Tk()
    app = LogicInjector(root)
    root.mainloop()
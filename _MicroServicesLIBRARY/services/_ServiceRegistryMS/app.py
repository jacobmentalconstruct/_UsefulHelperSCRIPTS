import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import json
import threading
import requests
import os
import sys
import re

# ==============================================================================
# IMPORT CORE LOGIC
# ==============================================================================
# We need the 'apply_patch_text' function to validate our work.
try:
    from app import apply_patch_text, PatchError
except ImportError:
    try:
        from src.app import apply_patch_text, PatchError
    except ImportError:
        print("WARNING: Could not import 'app.py'. Validation disabled.")
        apply_patch_text = None
        PatchError = Exception

# ==============================================================================
# 🧠 CHAIN OF THOUGHT ENGINE
# ==============================================================================

class ChainOfThoughtClient:
    """
    Manages the multi-step inference process with Ollama.
    """
    def __init__(self, model="qwen2.5-coder:7b", host="http://localhost:11434"):
        self.host = host
        self.model = model
        self.log_callback = None
        self.stop_event = threading.Event()

    def log(self, step_num, message, status="INFO"):
        """Sends log updates to the GUI."""
        if self.log_callback:
            self.log_callback(step_num, message, status)

    def _call_ollama(self, prompt, context_window=8192):
        """Helper to send raw requests to Ollama."""
        try:
            payload = {
                "model": self.model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.1,  # Strict adherence
                    "num_ctx": context_window
                }
            }
            response = requests.post(f"{self.host}/api/generate", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except requests.exceptions.ConnectionError:
            raise Exception("Ollama is not running. Run 'ollama serve'.")
        except Exception as e:
            raise Exception(f"API Error: {e}")

    def execute_chain(self, target_code, messy_instruction, done_callback):
        """
        The Master Tasklist Execution Loop.
        """
        def _run():
            try:
                self.stop_event.clear()

                # --- STEP 1: SCOUTING (Locate the Search Block) ---
                self.log(1, "🔍 ANALYZING INTENT & LOCATING CONTEXT...", "WORK")
                
                # UPDATED PROMPT: Explicitly handles "New Code" vs "Old Code"
                scout_prompt = f"""
TASK: Localize the code to be replaced.
CONTEXT: The "USER INSTRUCTION" likely contains the NEW version of a code block (Desired State).
GOAL: Find the *ORIGINAL, EXISTING* code block in the "TARGET FILE" that corresponds to this change (Current State).

RULES:
1. Return the code EXACTLY as it appears in the TARGET FILE right now.
2. Do NOT return the "New Version" from the instructions.
3. Do NOT include placeholder comments (like # ...) unless they literally exist in the TARGET FILE.

TARGET FILE:
```python
{target_code}
```

USER INSTRUCTION (New Version):
{messy_instruction}

RESPONSE (The EXACT lines from the TARGET FILE that will be replaced):
"""
                found_block = self._call_ollama(scout_prompt)
                
                # Cleanup: Remove markdown if the model added it
                clean_block = found_block.replace("```python", "").replace("```", "").strip()
                
                # Validation: Does this block actually exist in the file?
                if clean_block not in target_code:
                    # Retry logic or Fail
                    self.log(1, "❌ FAILED: AI returned code not found in file.", "ERR")
                    # Provide a helpful hint in the error
                    hint = "Hint: The AI likely tried to return the NEW code instead of the OLD code."
                    done_callback(False, f"Could not locate the exact code block.\n{hint}\n\nAI Output:\n{clean_block[:100]}...")
                    return
                
                found_block = clean_block
                self.log(1, f"✅ CONTEXT LOCKED: Found {len(found_block.splitlines())} lines.", "OK")

                # --- STEP 2: ARCHITECTING (Draft the Replacement) ---
                self.log(2, "🔨 DRAFTING NEW CODE (Filling Placeholders)...", "WORK")
                
                architect_prompt = f"""
TASK: Rewrite the "SOURCE BLOCK" applying the "USER CHANGES".
CRITICAL RULE: The user might use placeholders like "# ... existing code ...". You MUST replace those placeholders with the ACTUAL lines from the "SOURCE BLOCK".

SOURCE BLOCK (Original from File):
```python
{found_block}
```

USER CHANGES (New/Messy Instructions):
{messy_instruction}

RESPONSE (The fully complete, valid Python code block):
"""
                draft_block = self._call_ollama(architect_prompt)
                # Cleanup markdown
                draft_block = draft_block.replace("```python", "").replace("```", "").strip()
                self.log(2, "✅ DRAFT COMPLETE.", "OK")

                # --- STEP 3: ENGINEERING (Format to JSON) ---
                self.log(3, "📦 PACKAGING INTO JSON PATCH...", "WORK")
                
                final_prompt = f"""
TASK: Create a JSON patch.
SEARCH_BLOCK: {found_block}
REPLACE_BLOCK: {draft_block}

SCHEMA:
{{
  "hunks": [
    {{
      "description": "Auto-generated patch",
      "search_block": "PASTE SEARCH_BLOCK HERE",
      "replace_block": "PASTE REPLACE_BLOCK HERE",
      "use_patch_indent": false
    }}
  ]
}}

OUTPUT (JSON ONLY):
"""
                json_str = self._call_ollama(final_prompt)
                
                # JSON Extraction logic
                start = json_str.find("{")
                end = json_str.rfind("}")
                if start != -1 and end != -1:
                    json_str = json_str[start:end+1]

                self.log(3, "✅ JSON GENERATED.", "OK")
                done_callback(True, json_str)

            except Exception as e:
                self.log(4, f"🔥 SYSTEM ERROR: {e}", "ERR")
                done_callback(False, str(e))

        threading.Thread(target=_run, daemon=True).start()


# ==============================================================================
# 🖥️ GUI
# ==============================================================================

class CoTPatchApp:
    def __init__(self, root):
        self.root = root
        self.root.title("System 2 Patcher (Chain-of-Thought)")
        self.root.geometry("1200x850")
        self.root.configure(bg="#0f172a")

        self.client = ChainOfThoughtClient()
        self.client.log_callback = self.update_task_list

        self._setup_ui()

    def _setup_ui(self):
        # Styles
        style = ttk.Style()
        style.theme_use("clam")
        self.colors = {
            "bg": "#0f172a", "panel": "#1e293b", "input": "#020617",
            "text": "#e2e8f0", "green": "#22c55e", "red": "#ef4444", 
            "yellow": "#facc15", "purple": "#7C3AED"
        }
        
        # --- Top Bar ---
        top = tk.Frame(self.root, bg=self.colors["panel"], pady=5)
        top.pack(fill="x")
        
        tk.Button(top, text="📂 Load Target File", command=self.load_file, 
                  bg="#334155", fg="white", relief="flat", padx=10).pack(side="left", padx=10)
        
        self.lbl_file = tk.Label(top, text="No file loaded", bg=self.colors["panel"], fg="#94a3b8")
        self.lbl_file.pack(side="left", padx=5)

        tk.Label(top, text="Model:", bg=self.colors["panel"], fg="white").pack(side="right", padx=5)
        self.model_var = tk.StringVar(value="qwen2.5-coder:7b")
        models = ["qwen2.5-coder:7b", "qwen2.5-coder:1.5b", "starcoder2:7b", "mistral:latest"]
        ttk.Combobox(top, textvariable=self.model_var, values=models, width=20).pack(side="right", padx=10)

        # --- Main Split ---
        paned = tk.PanedWindow(self.root, orient="horizontal", bg="#0f172a", sashwidth=4, sashrelief="flat")
        paned.pack(fill="both", expand=True, padx=10, pady=10)

        # LEFT COLUMN: Inputs
        left_frame = tk.Frame(paned, bg=self.colors["panel"])
        
        # 1. Target Code View
        tk.Label(left_frame, text="1. TARGET CODE (Context)", bg="#334155", fg="white", anchor="w").pack(fill="x")
        self.txt_target = scrolledtext.ScrolledText(left_frame, height=15, bg=self.colors["input"], fg="#94a3b8", bd=0)
        self.txt_target.pack(fill="both", expand=True, pady=(0, 10))
        
        # 2. User Instructions
        tk.Label(left_frame, text="2. MESSY INSTRUCTION (Prompt)", bg="#334155", fg="white", anchor="w").pack(fill="x")
        self.txt_instruct = scrolledtext.ScrolledText(left_frame, height=10, bg=self.colors["input"], fg="#e2e8f0", bd=0, insertbackground="white")
        self.txt_instruct.pack(fill="both", expand=True)
        self.txt_instruct.insert("1.0", "# Paste your sloppy code or request here...\n# e.g. \"Update the scan function to look 3 folders up. Use placeholders.\"")
        
        paned.add(left_frame, minsize=400)

        # RIGHT COLUMN: Process & Output
        right_frame = tk.Frame(paned, bg=self.colors["panel"])
        
        # 3. Task List (The Brain)
        tk.Label(right_frame, text="🧠 THOUGHT PROCESS (Tasklist)", bg="#475569", fg="white", anchor="w").pack(fill="x")
        self.list_tasks = tk.Listbox(right_frame, height=8, bg=self.colors["input"], fg=self.colors["green"], 
                                     font=("Consolas", 10), bd=0, selectbackground="#334155")
        self.list_tasks.pack(fill="x", padx=5, pady=5)
        
        # Action Button
        self.btn_run = tk.Button(right_frame, text="🚀 EXECUTE TASK CHAIN", command=self.run_chain, 
                                 bg=self.colors["purple"], fg="white", font=("Segoe UI", 11, "bold"), relief="flat")
        self.btn_run.pack(fill="x", padx=5, pady=5)

        # 4. JSON Output
        tk.Label(right_frame, text="3. FINAL JSON PATCH", bg="#334155", fg="white", anchor="w").pack(fill="x")
        self.txt_json = scrolledtext.ScrolledText(right_frame, bg=self.colors["input"], fg="#fbbf24", font=("Consolas", 10), bd=0)
        self.txt_json.pack(fill="both", expand=True, padx=5, pady=5)

        # Bottom Buttons
        btn_frame = tk.Frame(right_frame, bg=self.colors["panel"])
        btn_frame.pack(fill="x", pady=5)
        
        tk.Button(btn_frame, text="✅ VALIDATE PATCH", command=self.validate, bg="#059669", fg="white", relief="flat").pack(side="left", fill="x", expand=True, padx=5)
        tk.Button(btn_frame, text="💾 SAVE JSON", command=self.save_json, bg="#334155", fg="white", relief="flat").pack(side="left", fill="x", expand=True, padx=5)

        paned.add(right_frame, minsize=400)

    # --- Logic ---

    def load_file(self):
        path = filedialog.askopenfilename()
        if path:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.txt_target.delete("1.0", tk.END)
                self.txt_target.insert("1.0", content)
                self.lbl_file.config(text=os.path.basename(path))
            except Exception as e:
                messagebox.showerror("Error", f"Failed to load file: {e}")

    def update_task_list(self, step, msg, status="INFO"):
        # Map status to color
        colors = {"WORK": self.colors["yellow"], "OK": self.colors["green"], "ERR": self.colors["red"], "INFO": self.colors["text"]}
        fg = colors.get(status, self.colors["text"])
        
        def _update():
            self.list_tasks.insert(tk.END, f"[{step}] {msg}")
            self.list_tasks.itemconfig(tk.END, {'fg': fg})
            self.list_tasks.see(tk.END)
        
        self.root.after(0, _update)

    def run_chain(self):
        target = self.txt_target.get("1.0", tk.END).strip()
        instruct = self.txt_instruct.get("1.0", tk.END).strip()
        
        if not target or not instruct:
            messagebox.showwarning("Missing Input", "Please provide both the Target Code and Instructions.")
            return

        # UI Reset
        self.list_tasks.delete(0, tk.END)
        self.txt_json.delete("1.0", tk.END)
        self.btn_run.config(state="disabled", text="THINKING...", bg="#4b5563")
        
        # Update Model
        self.client.model = self.model_var.get()
        
        # Run
        self.client.execute_chain(target, instruct, self.on_complete)

    def on_complete(self, success, result):
        self.root.after(0, lambda: self._finish_ui(success, result))

    def _finish_ui(self, success, result):
        self.btn_run.config(state="normal", text="🚀 EXECUTE TASK CHAIN", bg=self.colors["purple"])
        
        if success:
            self.txt_json.insert("1.0", result)
            # Auto-validate if core logic is available
            if apply_patch_text:
                self.validate()
        else:
            self.update_task_list(4, f"FATAL ERROR: {result}", "ERR")
            messagebox.showerror("Chain Failed", result)

    def validate(self):
        if not apply_patch_text:
            messagebox.showerror("Error", "Core patch logic not found. Cannot validate.")
            return

        try:
            target = self.txt_target.get("1.0", tk.END)
            patch_str = self.txt_json.get("1.0", tk.END).strip()
            
            if not patch_str:
                return

            patch_obj = json.loads(patch_str)
            
            # Dry run
            apply_patch_text(target, patch_obj)
            
            self.update_task_list(5, "✅ VALIDATION SUCCESSFUL. Patch is clean.", "OK")
            messagebox.showinfo("Success", "Patch is valid and applies cleanly!")
            
        except Exception as e:
            self.update_task_list(5, f"❌ VALIDATION FAILED: {e}", "ERR")
            messagebox.showerror("Validation Failed", str(e))

    def save_json(self):
        content = self.txt_json.get("1.0", tk.END).strip()
        if not content: return
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)

if __name__ == "__main__":
    root = tk.Tk()
    app = CoTPatchApp(root)
    root.mainloop()
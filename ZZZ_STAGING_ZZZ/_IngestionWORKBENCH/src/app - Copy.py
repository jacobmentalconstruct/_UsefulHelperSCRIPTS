import sys
import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
from pathlib import Path
import json
import threading
import requests
import time

# --- 1. ROBUST PATH SETUP ---
current_dir = Path(__file__).resolve().parent
ms_dir = current_dir / "microservices"
config_dir = current_dir / "config" # New Config Directory

if str(ms_dir) not in sys.path:
    sys.path.insert(0, str(ms_dir))
if str(current_dir) not in sys.path: 
    sys.path.insert(0, str(current_dir))

# --- 2. IMPORTS ---
try:
    from _TkinterAppShellMS import TkinterAppShellMS
    from _TkinterThemeManagerMS import TkinterThemeManagerMS
    from _ServiceRegistryMS import ServiceRegistryMS
except ImportError as e:
    print(f"\n[CRITICAL ERROR] Import Failed.\nError Details: {e}")
    sys.exit(1)

# --- 3. CONFIGURATION ---
try:
    PROJECT_ROOT = current_dir.parent.parent
    DETECTED_LIB_PATH = PROJECT_ROOT / "_MicroserviceLIBRARY"
except Exception:
    DETECTED_LIB_PATH = Path(r"C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_MicroserviceLIBRARY")
    
DEFAULT_LIBRARY_PATH = DETECTED_LIB_PATH if DETECTED_LIB_PATH.exists() else Path(".")
OLLAMA_BASE_URL = "http://localhost:11434"
PROMPTS_FILE = config_dir / "cortex_prompts.json"

# --- 4. THEME ---
COLORS = {
    "bg_dark": "#1b1b1b", "bg_panel": "#252526", "fg_text": "#e0c097",
    "fg_dim": "#858585", "accent": "#cd7f32", "accent_hover": "#ffd700",
    "select_bg": "#442d15", "success": "#50fa7b", "warning": "#ffb86c",
    "chat_user": "#2d2d2d", "chat_ai": "#252526"
}

class SteampunkStyler:
    @staticmethod
    def apply(root):
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure(".", background=COLORS["bg_dark"], foreground=COLORS["fg_text"], font=("Consolas", 10))
        style.configure("Treeview", background=COLORS["bg_panel"], foreground=COLORS["fg_text"], 
                        fieldbackground=COLORS["bg_panel"], borderwidth=0, font=("Consolas", 11))
        style.map("Treeview", background=[("selected", COLORS["select_bg"])], foreground=[("selected", COLORS["accent_hover"])])
        style.configure("TNotebook", background=COLORS["bg_dark"], borderwidth=0)
        style.configure("TNotebook.Tab", background=COLORS["bg_panel"], foreground=COLORS["fg_dim"], padding=[10, 5])
        style.map("TNotebook.Tab", background=[("selected", COLORS["accent"])], foreground=[("selected", COLORS["bg_dark"])])
        style.configure("TButton", background=COLORS["bg_panel"], foreground=COLORS["accent"], borderwidth=1, focusthickness=3)
        style.map("TButton", background=[("active", COLORS["select_bg"]), ("pressed", COLORS["accent"])], 
                  foreground=[("active", COLORS["accent_hover"]), ("pressed", COLORS["bg_dark"])])
        style.configure("Header.TLabel", foreground=COLORS["accent"], font=("Consolas", 12, "bold"))
        style.configure("Section.TLabel", foreground=COLORS["fg_dim"], font=("Consolas", 10, "italic"))

class ConfigLoader:
    """Handles externalized prompts and settings."""
    @staticmethod
    def load_prompts():
        defaults = {
            "system_prompts": {
                "registry_lookup": "You are the Library Registry Manager. Answer purely based on the provided list.",
                "deep_analysis": "You are a Senior Python Architect. Answer technical questions based on the provided code."
            },
            "context_templates": {
                "registry_header": "AVAILABLE SERVICES LIST:\n",
                "code_header": "SOURCE CODE CONTEXT:\n",
                "file_block": "\n=== BEGIN FILE: {filename} ===\n{content}\n=== END FILE ===\n"
            },
            "ui_messages": {
                "ollama_check": "Checking Ollama connection...",
                "ollama_connected": "Ollama connected. Found {count} models.",
                "analyzing_files": "Analyzing {count} selected source files..."
            },
             "inference_options": {
                "temperature": 0.1,
                "timeout_seconds": 120
            }
        }
        
        if PROMPTS_FILE.exists():
            try:
                with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Merge deep keys if necessary, or just top level
                    return data
            except Exception as e:
                print(f"[WARN] Failed to load prompts.json: {e}")
                return defaults
        return defaults

class ReferenceGenerator:
    @staticmethod
    def build_markdown_manual(services: list) -> str:
        lines = [f"# MICROSERVICE LIBRARY REFERENCE", f"**Generated:** {time.strftime('%Y-%m-%d %H:%M')}", "---"]
        for s in services:
            lines.append(f"- [{s['name']}](#{s['name'].lower()})")
        lines.append("\n---")
        for s in services:
            lines.append(f"\n## {s['name']}")
            lines.append(f"**ID:** `{s.get('token_id', 'N/A')}` | **Path:** `{s['path']}`")
            lines.append(f"\n> {s['description'].replace(chr(10), ' ')}")
            lines.append("\n### Capabilities")
            for m_name, m_data in s.get('methods', {}).items():
                args = ", ".join(m_data.get('args', []))
                lines.append(f"- **`{m_name}({args})`**")
        return "\n".join(lines)

# --- AI CHAT WIDGET ---
class AIChatPane(ttk.Frame):
    def __init__(self, parent, context_getter):
        super().__init__(parent)
        self.context_getter = context_getter
        self.config = ConfigLoader.load_prompts() # Initial load
        self.build_ui()
        threading.Thread(target=self.fetch_models, daemon=True).start()
        
    def build_ui(self):
        top_bar = ttk.Frame(self, padding=5)
        top_bar.pack(fill="x")
        ttk.Label(top_bar, text="MODEL:", style="Section.TLabel").pack(side="left")
        self.cbo_model = ttk.Combobox(top_bar, state="readonly", width=35)
        self.cbo_model.pack(side="left", padx=5)
        self.cbo_model.set("Detecting models...")
        ttk.Button(top_bar, text="↻", width=3, command=lambda: threading.Thread(target=self.fetch_models, daemon=True).start()).pack(side="left", padx=2)

        self.chat_display = scrolledtext.ScrolledText(self, state='disabled', bg=COLORS["bg_panel"], 
                                                    fg=COLORS["fg_text"], font=("Consolas", 11), wrap="word", borderwidth=0)
        self.chat_display.tag_config("user", foreground="#50fa7b", justify="right")
        self.chat_display.tag_config("ai", foreground="#8be9fd")
        self.chat_display.tag_config("system", foreground=COLORS["fg_dim"], font=("Consolas", 9, "italic"))
        self.chat_display.pack(fill="both", expand=True, padx=5, pady=5)
        
        input_frame = ttk.Frame(self)
        input_frame.pack(fill="x", padx=5, pady=5)
        self.txt_input = tk.Text(input_frame, height=3, bg="#000", fg="#fff", font=("Consolas", 11), insertbackground="#fff")
        self.txt_input.pack(side="left", fill="x", expand=True)
        self.txt_input.bind("<Return>", self.on_enter)
        self.txt_input.bind("<Shift-Return>", lambda e: None)
        ttk.Button(input_frame, text="SEND", command=self.send_message).pack(side="right", fill="y", padx=(5, 0))

        self.append_system(self.config["ui_messages"]["ollama_check"])

    def fetch_models(self):
        try:
            url = f"{OLLAMA_BASE_URL}/api/tags"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                all_models = [m['name'] for m in data.get('models', [])]
                defaults = [m for m in all_models if "code" in m or "qwen" in m]
                default = defaults[0] if defaults else (all_models[0] if all_models else "No Models Found")
                
                self.after(0, lambda: self.update_combo(all_models, default))
                msg = self.config["ui_messages"]["ollama_connected"].format(count=len(all_models))
                self.after(0, lambda: self.append_system(msg))
            else:
                msg = self.config["ui_messages"]["ollama_error"].format(status=resp.status_code)
                self.after(0, lambda: self.append_system(msg))
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda: self.append_system(f"Ollama Unreachable: {err_msg}"))

    def update_combo(self, values, default_val):
        self.cbo_model['values'] = values
        self.cbo_model.set(default_val)

    def append_system(self, text):
        self.chat_display.configure(state='normal')
        self.chat_display.insert("end", f"[SYSTEM] {text}\n", "system")
        self.chat_display.configure(state='disabled')
        self.chat_display.see("end")

    def append_message(self, role, text):
        self.chat_display.configure(state='normal')
        tag = "user" if role == "user" else "ai"
        header = "YOU" if role == "user" else "CORTEX"
        self.chat_display.insert("end", f"\n{header}:\n{text}\n", tag)
        self.chat_display.configure(state='disabled')
        self.chat_display.see("end")

    def on_enter(self, event):
        if not event.state & 0x0001: 
            self.send_message()
            return "break"

    def send_message(self):
        msg = self.txt_input.get("1.0", "end").strip()
        if not msg: return
        
        selected_model = self.cbo_model.get()
        if not selected_model or "..." in selected_model:
            self.append_system("Error: Select a model first.")
            return

        self.txt_input.delete("1.0", "end")
        self.append_message("user", msg)
        
        # RELOAD CONFIG ON EVERY MESSAGE (Hot-Swap)
        self.config = ConfigLoader.load_prompts()
        
        threading.Thread(target=self.run_inference, args=(msg, selected_model), daemon=True).start()

    def run_inference(self, user_query, model_name):
        registry, selected_files = self.context_getter()
        prompts = self.config["system_prompts"]
        templates = self.config["context_templates"]
        ui_msgs = self.config["ui_messages"]
        opts = self.config["inference_options"]
        
        if selected_files:
            # --- MODE 1: DEEP CODE ANALYSIS ---
            msg = ui_msgs.get("analyzing_files", "Analyzing...").format(count=len(selected_files))
            self.after(0, lambda: self.append_system(msg))
            
            context_str = templates.get("code_header", "CONTEXT:\n")
            for fname, content in selected_files.items():
                block = templates.get("file_block", "\nFILE: {filename}\n{content}\n")
                context_str += block.format(filename=fname, content=content)
            
            system_prompt = prompts["deep_analysis"]
            
        else:
            # --- MODE 2: REGISTRY LOOKUP ---
            lines = []
            for s in registry:
                desc_snippet = s['description'].replace('\n', ' ')[:120] 
                lines.append(f"- {s['name']} : {desc_snippet}")
            
            context_str = templates.get("registry_header", "LIST:\n") + "\n".join(lines)
            system_prompt = prompts["registry_lookup"]

        try:
            url = f"{OLLAMA_BASE_URL}/api/chat"
            payload = {
                "model": model_name,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"{context_str}\n\nUSER QUESTION: {user_query}"}
                ],
                "stream": False,
                "options": {
                    "temperature": opts.get("temperature", 0.1)
                }
            }
            
            response = requests.post(url, json=payload, timeout=opts.get("timeout_seconds", 120))
            
            if response.status_code == 200:
                answer = response.json().get("message", {}).get("content", "No content returned.")
                self.after(0, lambda: self.append_message("ai", answer))
            else:
                self.after(0, lambda: self.append_system(f"Ollama Error: {response.status_code} - {response.text}"))
        except Exception as e:
            err_msg = str(e)
            self.after(0, lambda: self.append_system(f"Connection Failed: {err_msg}"))

# --- MAIN APP ---
class MicroserviceBrowserApp:
    def __init__(self):
        self.theme_mgr = TkinterThemeManagerMS()
        self.registry_svc = ServiceRegistryMS()
        
        self.library_root = DEFAULT_LIBRARY_PATH
        self.services_map = {} 
        self.checked_items = set() 
        self.current_registry_data = [] 
        
        self.app = TkinterAppShellMS({
            "theme_manager": self.theme_mgr,
            "title": "CORTEX COMPOSER [v2.7: Configurable]",
            "geometry": "1400x900"
        })
        SteampunkStyler.apply(self.app.root)
        self.app.root.configure(bg=COLORS["bg_dark"])

        self.show_line_numbers = tk.BooleanVar(value=True)
        self.build_ui()
        
        if self.library_root.exists(): 
            self.refresh_library()
        else:
            self.app.root.after(100, self.change_library)

    def build_ui(self):
        container = self.app.get_main_container()
        container.configure(bg=COLORS["bg_dark"])
        
        deck = ttk.Frame(container, padding=10)
        deck.pack(fill="x")
        ttk.Label(deck, text="LIBRARY:", style="Header.TLabel").pack(side="left")
        self.lbl_path = ttk.Label(deck, text=str(self.library_root), foreground=COLORS["fg_dim"])
        self.lbl_path.pack(side="left", padx=10)
        
        btn_frame = ttk.Frame(deck)
        btn_frame.pack(side="right")
        ttk.Button(btn_frame, text="[CHANGE PATH]", command=self.change_library).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="[RE-SCAN]", command=self.refresh_library).pack(side="left", padx=2)

        paned = tk.PanedWindow(container, orient="horizontal", bg=COLORS["accent"], sashwidth=2, sashrelief="flat")
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        left = ttk.Frame(paned)
        paned.add(left, width=400)
        
        sel_row = ttk.Frame(left)
        sel_row.pack(fill="x", pady=5)
        ttk.Button(sel_row, text="ALL", width=5, command=self.select_all).pack(side="left", padx=1)
        ttk.Button(sel_row, text="NONE", width=5, command=self.select_none).pack(side="left", padx=1)
        ttk.Button(sel_row, text="INV", width=5, command=self.select_inverse).pack(side="left", padx=1)
        
        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill="both", expand=True, pady=2)
        self.tree = ttk.Treeview(tree_frame, columns=("status"), show="tree", selectmode="browse")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_service_click)
        self.tree.bind("<Double-1>", self.on_service_toggle)

        ops = ttk.LabelFrame(left, text="OPERATIONS DECK", padding=5)
        ops.pack(fill="x", pady=10)
        ttk.Label(ops, text="PHYSICAL DEPLOYMENT", style="Section.TLabel").pack(anchor="w")
        ttk.Button(ops, text="DEPLOY TO FOLDER...", command=self.deploy_files).pack(fill="x", pady=2)
        ttk.Label(ops, text="INTELLIGENT REPORTING", style="Section.TLabel").pack(anchor="w", pady=(10,0))
        ttk.Button(ops, text="EXPORT REFERENCE MANUAL (MD)", command=self.export_manual).pack(fill="x", pady=2)
        
        self.right_tabs = ttk.Notebook(paned)
        paned.add(self.right_tabs, width=800)
        
        self.tab_source = ttk.Frame(self.right_tabs)
        self.right_tabs.add(self.tab_source, text=" SOURCE INSPECTOR ")
        
        view_head = ttk.Frame(self.tab_source)
        view_head.pack(fill="x", pady=5)
        ttk.Checkbutton(view_head, text="Line Numbers", variable=self.show_line_numbers, command=self.refresh_code_view).pack(side="right")

        self.txt_code = tk.Text(self.tab_source, font=("Consolas", 11), bg=COLORS["bg_panel"], fg=COLORS["fg_text"], 
            insertbackground=COLORS["accent"], selectbackground=COLORS["select_bg"], wrap="none", undo=False, borderwidth=0)
        self.txt_code.pack(fill="both", expand=True)

        self.chat_pane = AIChatPane(self.right_tabs, self.get_context_for_ai)
        self.right_tabs.add(self.chat_pane, text=" CORTEX CHAT ")

    # --- CORE LOGIC ---
    def refresh_library(self):
        self.registry_svc.root = self.library_root
        self.tree.delete(*self.tree.get_children())
        self.services_map.clear()
        
        if not self.library_root.exists():
            messagebox.showerror("Error", f"Path not found: {self.library_root}")
            return
            
        self.current_registry_data = self.registry_svc.scan(save_to=None)
        
        for item in self.current_registry_data:
            name = item['name']
            iid = f"{name}_{item['path']}" if name in self.services_map else name
            self.services_map[iid] = item
            self.tree.insert("", "end", iid=iid, text=f"☐ {name}", tags=("unchecked",))
            
    def get_context_for_ai(self):
        registry = self.current_registry_data
        selected_files = {}
        for iid in self.checked_items:
            data = self.services_map.get(iid)
            if data:
                path = self.library_root / data['path']
                if path.exists():
                    try:
                        selected_files[data['name']] = path.read_text(encoding="utf-8")
                    except Exception as e:
                        selected_files[data['name']] = f"Error reading file: {e}"
        return registry, selected_files

    def _get_selected_data(self):
        return [self.services_map[iid] for iid in self.checked_items]

    # --- SELECTION HANDLING ---
    def on_service_toggle(self, event):
        item_id = self.tree.focus()
        if not item_id: return
        
        orig_name = self.services_map[item_id]['name']
        if item_id in self.checked_items:
            self.checked_items.remove(item_id)
            self.tree.item(item_id, text=f"☐ {orig_name}", tags=("unchecked",))
        else:
            self.checked_items.add(item_id)
            self.tree.item(item_id, text=f"☑ {orig_name}", tags=("checked",))

    def on_service_click(self, event):
        item_id = self.tree.focus()
        if not item_id: return
        data = self.services_map.get(item_id)
        if not data: return
        
        path = self.library_root / data['path']
        if path.exists():
            self.current_code_content = path.read_text(encoding="utf-8")
            self.refresh_code_view()

    def refresh_code_view(self):
        if not hasattr(self, 'current_code_content'): return
        content = self.current_code_content
        self.txt_code.delete("1.0", "end")
        if self.show_line_numbers.get():
            lines = [f"{i+1:03d} | {line}" for i, line in enumerate(content.splitlines())]
            self.txt_code.insert("1.0", "\n".join(lines))
        else:
            self.txt_code.insert("1.0", content)

    # --- BULK ACTIONS ---
    def select_all(self):
        for iid in self.services_map:
            if iid not in self.checked_items:
                self.checked_items.add(iid)
            self.tree.item(iid, text=f"☑ {self.services_map[iid]['name']}")

    def select_none(self):
        self.checked_items.clear()
        for iid in self.services_map:
            self.tree.item(iid, text=f"☐ {self.services_map[iid]['name']}")

    def select_inverse(self):
        new_set = set()
        for iid in self.services_map:
            if iid not in self.checked_items:
                new_set.add(iid)
                self.tree.item(iid, text=f"☑ {self.services_map[iid]['name']}")
            else:
                self.tree.item(iid, text=f"☐ {self.services_map[iid]['name']}")
        self.checked_items = new_set

    # --- OPERATIONS ---
    def deploy_files(self):
        selection = self._get_selected_data()
        if not selection: return messagebox.showwarning("Empty", "Select services to deploy.")
        
        target_dir = filedialog.askdirectory(title="Select Target 'src/microservices' Folder")
        if not target_dir: return

        count = 0
        try:
            dest = Path(target_dir)
            std_lib_name = "microservice_std_lib.py"
            std_lib_src = self.library_root / std_lib_name
            std_lib_dest = dest / std_lib_name
            
            if std_lib_src.exists() and not std_lib_dest.exists():
                shutil.copy2(std_lib_src, std_lib_dest)

            for s in selection:
                src = self.library_root / s['path']
                if src.exists():
                    shutil.copy2(src, dest / src.name)
                    count += 1
            messagebox.showinfo("Deployed", f"Successfully deployed {count} microservices to:\n{dest}")
        except Exception as e:
            messagebox.showerror("Deployment Error", str(e))

    def export_manual(self):
        selection = self._get_selected_data()
        if not selection: 
            if messagebox.askyesno("No Selection", "Export entire library?"):
                selection = list(self.services_map.values())
            else:
                return

        file_path = filedialog.asksaveasfilename(defaultextension=".md", filetypes=[("Markdown", "*.md")], initialfile="Cortex_Reference_Manual.md")
        if not file_path: return
        
        try:
            report = ReferenceGenerator.build_markdown_manual(selection)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(report)
            messagebox.showinfo("Success", f"Manual exported to:\n{file_path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def change_library(self):
        path = filedialog.askdirectory(initialdir=self.library_root)
        if path:
            self.library_root = Path(path)
            self.lbl_path.config(text=str(self.library_root))
            self.refresh_library()

    def run(self):
        self.app.launch()

if __name__ == "__main__":
    browser = MicroserviceBrowserApp()
    browser.run()
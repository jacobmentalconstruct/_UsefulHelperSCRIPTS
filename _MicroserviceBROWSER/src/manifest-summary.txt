import sys
import os
import shutil
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import json

# --- 1. PATH SETUP ---
current_dir = Path(__file__).resolve().parent
if str(current_dir) not in sys.path: sys.path.append(str(current_dir))
ms_dir = current_dir / "microservices"
if str(ms_dir) not in sys.path: sys.path.append(str(ms_dir))

# --- 2. IMPORTS ---
try:
    from microservices._TkinterAppShellMS import TkinterAppShellMS
    from microservices._TkinterThemeManagerMS import TkinterThemeManagerMS
    from microservices._ServiceRegistryMS import ServiceRegistryMS
    from microservices._ContextPackerMS import ContextPackerMS
except ImportError as e:
    # Graceful exit if dependencies are missing
    print(f"CRITICAL: Missing Core Microservices.\nError: {e}")
    sys.exit(1)

# --- 3. CONFIGURATION ---
try:
    # Try to find the library relative to this script
    PROJECT_ROOT = current_dir.parent.parent
    DETECTED_LIB_PATH = PROJECT_ROOT / "_MicroserviceLIBRARY"
except Exception:
    DETECTED_LIB_PATH = Path(r"C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_MicroserviceLIBRARY")
    
# Default to current dir if detection fails
DEFAULT_LIBRARY_PATH = DETECTED_LIB_PATH if DETECTED_LIB_PATH.exists() else Path(".")

# --- 4. THEME (Dark Steampunk) ---
COLORS = {
    "bg_dark": "#1b1b1b", "bg_panel": "#252526", "fg_text": "#e0c097",
    "fg_dim": "#858585", "accent": "#cd7f32", "accent_hover": "#ffd700",
    "select_bg": "#442d15", "success": "#50fa7b", "warning": "#ffb86c"
}

class SteampunkStyler:
    @staticmethod
    def apply(root):
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure(".", background=COLORS["bg_dark"], foreground=COLORS["fg_text"], font=("Consolas", 10))
        
        # Treeview (The List)
        style.configure("Treeview", background=COLORS["bg_panel"], foreground=COLORS["fg_text"], 
                        fieldbackground=COLORS["bg_panel"], borderwidth=0, font=("Consolas", 11))
        style.map("Treeview", background=[("selected", COLORS["select_bg"])], foreground=[("selected", COLORS["accent_hover"])])
        style.configure("Treeview.Heading", background=COLORS["bg_dark"], foreground=COLORS["accent"], font=("Consolas", 10, "bold"))
        
        # Buttons
        style.configure("TButton", background=COLORS["bg_panel"], foreground=COLORS["accent"], borderwidth=1, focusthickness=3)
        style.map("TButton", background=[("active", COLORS["select_bg"]), ("pressed", COLORS["accent"])], 
                  foreground=[("active", COLORS["accent_hover"]), ("pressed", COLORS["bg_dark"])])
        
        # Labels
        style.configure("Header.TLabel", foreground=COLORS["accent"], font=("Consolas", 12, "bold"))
        style.configure("Section.TLabel", foreground=COLORS["fg_dim"], font=("Consolas", 10, "italic"))

# --- 5. REPORT GENERATOR ---
class ReportGenerator:
    @staticmethod
    def agent_spec(services: list) -> str:
        """Generates a token-efficient Tool Definition list for LLMs."""
        lines = ["# TOOL DEFINITIONS (STRICT INTERFACE)", ""]
        for s in services:
            lines.append(f"## Tool: {s['name']}")
            # Grab only the first line of the docstring for brevity
            desc = s['description'].split(chr(10))[0] if s['description'] else "No description."
            lines.append(f"Description: {desc}")
            lines.append("Functions:")
            for m_name, m_data in s.get('methods', {}).items():
                args = ", ".join(m_data.get('args', []))
                lines.append(f"  - {m_name}({args})")
                if m_data.get('doc'):
                    doc_summary = m_data['doc'].split('.')[0].strip()
                    lines.append(f"    # {doc_summary}")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def manifest(services: list) -> str:
        """Generates a high-level inventory list."""
        lines = ["# DEPLOYMENT MANIFEST", f"Total Services: {len(services)}", "-"*40]
        for s in services:
            desc = s['description'][:60] if s['description'] else "No description"
            lines.append(f"- [x] {s['name']} :: {desc}...")
        return "\n".join(lines)

# --- 6. MAIN APP ---
class MicroserviceBrowserApp:
    def __init__(self):
        self.theme_mgr = TkinterThemeManagerMS()
        self.registry_svc = ServiceRegistryMS()
        self.packer_svc = ContextPackerMS()
        
        self.library_root = DEFAULT_LIBRARY_PATH
        self.services_map = {} 
        self.checked_items = set() 
        
        self.app = TkinterAppShellMS({
            "theme_manager": self.theme_mgr,
            "title": "CORTEX COMPOSER [v2.2: Golden Master]",
            "geometry": "1400x900"
        })
        SteampunkStyler.apply(self.app.root)
        self.app.root.configure(bg=COLORS["bg_dark"])

        self.show_line_numbers = tk.BooleanVar(value=True)
        self.build_ui()
        
        # Auto-scan if valid, otherwise prompt user
        if self.library_root.exists(): 
            self.refresh_library()
        else:
            self.app.root.after(100, self.change_library)

    def build_ui(self):
        container = self.app.get_main_container()
        container.configure(bg=COLORS["bg_dark"])
        
        # --- HEADER ---
        deck = ttk.Frame(container, padding=10)
        deck.pack(fill="x")
        ttk.Label(deck, text="LIBRARY SOURCE:", style="Header.TLabel").pack(side="left")
        self.lbl_path = ttk.Label(deck, text=str(self.library_root), foreground=COLORS["fg_dim"])
        self.lbl_path.pack(side="left", padx=10)
        btn_frame = ttk.Frame(deck)
        btn_frame.pack(side="right")
        ttk.Button(btn_frame, text="[CHANGE PATH]", command=self.change_library).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="[RE-SCAN]", command=self.refresh_library).pack(side="left", padx=2)

        paned = tk.PanedWindow(container, orient="horizontal", bg=COLORS["accent"], sashwidth=2, sashrelief="flat")
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        # --- LEFT PANEL (Selection) ---
        left = ttk.Frame(paned)
        paned.add(left, width=400)
        
        # Selection Tools
        sel_row = ttk.Frame(left)
        sel_row.pack(fill="x", pady=5)
        ttk.Button(sel_row, text="ALL", width=5, command=self.select_all).pack(side="left", padx=1)
        ttk.Button(sel_row, text="NONE", width=5, command=self.select_none).pack(side="left", padx=1)
        ttk.Button(sel_row, text="INV", width=5, command=self.select_inverse).pack(side="left", padx=1)
        
        # Tree
        tree_frame = ttk.Frame(left)
        tree_frame.pack(fill="both", expand=True, pady=2)
        self.tree = ttk.Treeview(tree_frame, columns=("status"), show="tree", selectmode="browse")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self.on_service_click)
        self.tree.bind("<Double-1>", self.on_service_toggle)

        # --- OPERATIONS DECK ---
        ops = ttk.LabelFrame(left, text="OPERATIONS DECK", padding=5)
        ops.pack(fill="x", pady=10)
        
        # 1. Deployment
        ttk.Label(ops, text="PHYSICAL DEPLOYMENT", style="Section.TLabel").pack(anchor="w")
        ttk.Button(ops, text="DEPLOY TO FOLDER...", command=self.deploy_files).pack(fill="x", pady=2)
        
        # 2. Reporting
        ttk.Label(ops, text="INTELLIGENT REPORTING", style="Section.TLabel").pack(anchor="w", pady=(10,0))
        ttk.Button(ops, text="COPY 'AGENT SPEC' (For LLMs)", command=self.copy_agent_spec).pack(fill="x", pady=2)
        ttk.Button(ops, text="COPY 'MANIFEST' (Summary)", command=self.copy_manifest).pack(fill="x", pady=2)
        ttk.Button(ops, text="COPY FULL CODE (Raw Dump)", command=self.copy_full_code).pack(fill="x", pady=2)

        # --- RIGHT PANEL (Viewer) ---
        right = ttk.Frame(paned)
        paned.add(right, width=800)
        
        view_head = ttk.Frame(right)
        view_head.pack(fill="x", pady=5)
        ttk.Label(view_head, text="SOURCE INSPECTOR", style="Header.TLabel").pack(side="left")
        ttk.Checkbutton(view_head, text="Line Numbers", variable=self.show_line_numbers, command=self.refresh_code_view).pack(side="right")

        self.txt_code = tk.Text(right, font=("Consolas", 11), bg=COLORS["bg_panel"], fg=COLORS["fg_text"], 
            insertbackground=COLORS["accent"], selectbackground=COLORS["select_bg"], wrap="none", undo=False, borderwidth=0)
        self.txt_code.pack(fill="both", expand=True)

    # --- CORE LOGIC ---

    def refresh_library(self):
        self.registry_svc.root = self.library_root
        self.tree.delete(*self.tree.get_children())
        self.services_map.clear()
        
        if not self.library_root.exists():
            messagebox.showerror("Error", f"Path not found: {self.library_root}")
            return

        registry_data = self.registry_svc.scan(save_to=None)
        
        for item in registry_data:
            name = item['name']
            iid = f"{name}_{item['path']}" if name in self.services_map else name
            self.services_map[iid] = item
            self.tree.insert("", "end", iid=iid, text=f"☐ {name}", tags=("unchecked",))
            
    def _get_selected_data(self):
        """Returns list of dicts for checked items."""
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

    # --- OPERATIONS DECK ---

    def deploy_files(self):
        """Copies actual .py files to a selected directory with dependency safety."""
        selection = self._get_selected_data()
        if not selection: return messagebox.showwarning("Empty", "Select services to deploy.")
        
        target_dir = filedialog.askdirectory(title="Select Target 'src/microservices' Folder")
        if not target_dir: return

        count = 0
        try:
            dest = Path(target_dir)
            
            # --- SAFETY INTERLOCK: Ensure Std Lib is present ---
            std_lib_name = "microservice_std_lib.py"
            std_lib_src = self.library_root / std_lib_name
            std_lib_dest = dest / std_lib_name
            
            if std_lib_src.exists() and not std_lib_dest.exists():
                shutil.copy2(std_lib_src, std_lib_dest)
                print(f"[Auto-Deploy] Copied dependency: {std_lib_name}")
            # ----------------------------------------------------

            for s in selection:
                src = self.library_root / s['path']
                if src.exists():
                    shutil.copy2(src, dest / src.name)
                    count += 1
            messagebox.showinfo("Deployed", f"Successfully deployed {count} microservices to:\n{dest}")
        except Exception as e:
            messagebox.showerror("Deployment Error", str(e))

    def copy_agent_spec(self):
        """Copies the lightweight API definition."""
        selection = self._get_selected_data()
        if not selection: return messagebox.showwarning("Empty", "Select services first.")
        
        report = ReportGenerator.agent_spec(selection)
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(report)
        messagebox.showinfo("Copied", f"Agent Spec ({len(selection)} tools) copied to clipboard.")

    def copy_manifest(self):
        """Copies a high-level list."""
        selection = self._get_selected_data()
        if not selection: return messagebox.showwarning("Empty", "Select services first.")
        
        report = ReportGenerator.manifest(selection)
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(report)
        messagebox.showinfo("Copied", "Manifest copied to clipboard.")

    def copy_full_code(self):
        """The old massive dump."""
        selection = self._get_selected_data()
        if not selection: return messagebox.showwarning("Empty", "Select services first.")
        
        output = ["# CONTEXT DUMP", "="*40]
        for s in selection:
            path = self.library_root / s['path']
            if path.exists():
                output.append(f"\n# FILE: {s['path']}\n" + "-"*40)
                output.append(path.read_text(encoding="utf-8"))
        
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append("\n".join(output))
        messagebox.showinfo("Copied", f"Full Source Code ({len(selection)} files) copied.")

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
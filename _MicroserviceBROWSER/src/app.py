import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path
import json

# --- 1. PATH SETUP ---
current_dir = Path(__file__).resolve().parent

# A. Add 'src/' to path
if str(current_dir) not in sys.path:
    sys.path.append(str(current_dir))

# B. Add 'src/microservices/' to path
ms_dir = current_dir / "microservices"
if str(ms_dir) not in sys.path:
    sys.path.append(str(ms_dir))

# --- 2. MICROSERVICE IMPORTS ---
try:
    from microservices._TkinterAppShellMS import TkinterAppShellMS
    from microservices._TkinterThemeManagerMS import TkinterThemeManagerMS
    from microservices._ServiceRegistryMS import ServiceRegistryMS
    from microservices._ContextPackerMS import ContextPackerMS
except ImportError as e:
    print(f"CRITICAL IMPORT ERROR: {e}")
    sys.exit(1)

# --- 3. CONFIGURATION ---
try:
    PROJECT_ROOT = current_dir.parent.parent
    DETECTED_LIB_PATH = PROJECT_ROOT / "_MicroserviceLIBRARY"
except Exception:
    DETECTED_LIB_PATH = Path(r"C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_MicroserviceLIBRARY")

DEFAULT_LIBRARY_PATH = DETECTED_LIB_PATH if DETECTED_LIB_PATH.exists() else Path(".")

# --- 4. THEME DEFINITION ---
COLORS = {
    "bg_dark": "#1b1b1b",       # Deep Soot
    "bg_panel": "#252526",      # Lighter Soot
    "fg_text": "#e0c097",       # Parchment
    "fg_dim": "#858585",        # Dust
    "accent": "#cd7f32",        # Brass / Bronze
    "accent_hover": "#ffd700",  # Gold
    "select_bg": "#442d15",     # Leather
    "error": "#ff5555"          # Red alert
}

class SteampunkStyler:
    @staticmethod
    def apply(root):
        style = ttk.Style(root)
        style.theme_use('clam') # 'clam' allows for better color customization than 'vista'

        # Global Defaults
        style.configure(".", 
            background=COLORS["bg_dark"], 
            foreground=COLORS["fg_text"], 
            font=("Consolas", 10)
        )

        # Treeview (The List)
        style.configure("Treeview",
            background=COLORS["bg_panel"],
            foreground=COLORS["fg_text"],
            fieldbackground=COLORS["bg_panel"],
            borderwidth=0,
            font=("Consolas", 11)
        )
        style.map("Treeview",
            background=[("selected", COLORS["select_bg"])],
            foreground=[("selected", COLORS["accent_hover"])]
        )
        style.configure("Treeview.Heading",
            background=COLORS["bg_dark"],
            foreground=COLORS["accent"],
            font=("Consolas", 10, "bold")
        )

        # Buttons (Brass Plates)
        style.configure("TButton",
            background=COLORS["bg_panel"],
            foreground=COLORS["accent"],
            borderwidth=1,
            focusthickness=3,
            focuscolor=COLORS["accent"],
            font=("Consolas", 10, "bold")
        )
        style.map("TButton",
            background=[("active", COLORS["select_bg"]), ("pressed", COLORS["accent"])],
            foreground=[("active", COLORS["accent_hover"]), ("pressed", COLORS["bg_dark"])]
        )

        # Frames & Labels
        style.configure("TFrame", background=COLORS["bg_dark"])
        style.configure("TLabel", background=COLORS["bg_dark"], foreground=COLORS["fg_text"])
        style.configure("Header.TLabel", foreground=COLORS["accent"], font=("Consolas", 12, "bold"))
        
        # Scrollbars (Industrial)
        style.configure("Vertical.TScrollbar",
            gripcount=0,
            background=COLORS["bg_panel"],
            darkcolor=COLORS["bg_dark"],
            lightcolor=COLORS["bg_panel"],
            troughcolor=COLORS["bg_dark"],
            bordercolor=COLORS["bg_dark"],
            arrowcolor=COLORS["accent"]
        )

# --- 5. MAIN APP ---
class MicroserviceBrowserApp:
    def __init__(self):
        # Logic
        self.theme_mgr = TkinterThemeManagerMS()
        self.registry_svc = ServiceRegistryMS()
        self.packer_svc = ContextPackerMS()
        
        # State
        self.library_root = DEFAULT_LIBRARY_PATH
        self.services_map = {} 
        self.checked_items = set() # Set of names that are checked "☑"
        
        # Shell
        self.app = TkinterAppShellMS({
            "theme_manager": self.theme_mgr,
            "title": "CORTEX COMPOSER [v2.0]",
            "geometry": "1400x900"
        })
        
        # Apply Theme
        SteampunkStyler.apply(self.app.root)
        self.app.root.configure(bg=COLORS["bg_dark"])

        # Defer UI build to safe time
        self.show_line_numbers = tk.BooleanVar(value=True)
        self.build_ui()
        
        if self.library_root.exists():
            self.refresh_library()

    def build_ui(self):
        container = self.app.get_main_container()
        container.configure(bg=COLORS["bg_dark"])
        
        # --- TOP: Control Deck ---
        deck = ttk.Frame(container, padding=10)
        deck.pack(fill="x")
        
        ttk.Label(deck, text="LIBRARY SOURCE:", style="Header.TLabel").pack(side="left")
        self.lbl_path = ttk.Label(deck, text=str(self.library_root), foreground=COLORS["fg_dim"])
        self.lbl_path.pack(side="left", padx=10)
        
        btn_frame = ttk.Frame(deck)
        btn_frame.pack(side="right")
        ttk.Button(btn_frame, text="[CHANGE]", command=self.change_library).pack(side="left", padx=2)
        ttk.Button(btn_frame, text="[REFRESH]", command=self.refresh_library).pack(side="left", padx=2)

        # --- BODY: Split Pane ---
        # Custom separator style is hard in ttk, so we use bg colors to fake it
        paned = tk.PanedWindow(container, orient="horizontal", bg=COLORS["accent"], sashwidth=2, sashrelief="flat")
        paned.pack(fill="both", expand=True, padx=5, pady=5)
        
        # --- LEFT: Service Picker ---
        left_panel = ttk.Frame(paned)
        paned.add(left_panel, width=350)
        
        # Picker Header
        picker_head = ttk.Frame(left_panel)
        picker_head.pack(fill="x", pady=5)
        ttk.Label(picker_head, text="AVAILABLE MODULES", style="Header.TLabel").pack(side="left")
        
        # Select Tools
        tool_row = ttk.Frame(left_panel)
        tool_row.pack(fill="x", pady=2)
        ttk.Button(tool_row, text="[ALL]", width=6, command=self.select_all).pack(side="left", padx=1)
        ttk.Button(tool_row, text="[NONE]", width=6, command=self.select_none).pack(side="left", padx=1)
        ttk.Button(tool_row, text="[INV]", width=6, command=self.select_inverse).pack(side="left", padx=1)

        # The Tree
        tree_frame = ttk.Frame(left_panel)
        tree_frame.pack(fill="both", expand=True, pady=5)
        
        self.tree = ttk.Treeview(tree_frame, columns=("status"), show="tree", selectmode="browse")
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        
        # Bindings
        self.tree.bind("<<TreeviewSelect>>", self.on_service_click) # Single click = View
        self.tree.bind("<Double-1>", self.on_service_toggle)        # Double click = Toggle Check

        # Export Button (Big)
        self.btn_export = ttk.Button(left_panel, text="EXPORT SELECTION (0)", command=self.export_clipboard)
        self.btn_export.pack(fill="x", pady=10)


        # --- RIGHT: Code Viewer ---
        right_panel = ttk.Frame(paned)
        paned.add(right_panel, width=800)
        
        # Viewer Header
        view_head = ttk.Frame(right_panel)
        view_head.pack(fill="x", pady=5)
        ttk.Label(view_head, text="SOURCE INSPECTOR", style="Header.TLabel").pack(side="left")
        
        # View Controls
        view_ctrl = ttk.Frame(right_panel)
        view_ctrl.pack(fill="x")
        ttk.Checkbutton(view_ctrl, text="Line Numbers", variable=self.show_line_numbers, command=self.refresh_code_view).pack(side="left")
        ttk.Button(view_ctrl, text="[COPY RAW]", command=self.copy_current_code).pack(side="right")

        # Text Area
        self.txt_code = tk.Text(right_panel, 
            font=("Consolas", 11), 
            bg=COLORS["bg_panel"], 
            fg=COLORS["fg_text"], 
            insertbackground=COLORS["accent"], # Cursor color
            selectbackground=COLORS["select_bg"],
            wrap="none", 
            undo=False,
            borderwidth=0
        )
        self.txt_code.pack(fill="both", expand=True, pady=5)

    # --- LOGIC: Tree & Selection ---

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
            # Handle duplicates
            if name in self.services_map:
                iid = f"{name}_{item['path']}"
            else:
                iid = name
                
            self.services_map[iid] = item
            
            # Initial State: Unchecked
            display_text = f"☐ {name}"
            self.tree.insert("", "end", iid=iid, text=display_text, tags=("unchecked",))

    def _update_row_display(self, iid):
        """Updates the visual checkmark based on checked_items set."""
        original_name = self.services_map[iid]['name']
        if iid in self.checked_items:
            self.tree.item(iid, text=f"☑ {original_name}", tags=("checked",))
        else:
            self.tree.item(iid, text=f"☐ {original_name}", tags=("unchecked",))
        self._update_export_btn()

    def on_service_toggle(self, event):
        """Double click toggles selection."""
        item_id = self.tree.focus()
        if not item_id: return
        
        if item_id in self.checked_items:
            self.checked_items.remove(item_id)
        else:
            self.checked_items.add(item_id)
            
        self._update_row_display(item_id)

    def on_service_click(self, event):
        """Single click loads code preview."""
        item_id = self.tree.focus()
        if not item_id: return
        
        data = self.services_map.get(item_id)
        if not data: return
        
        # Load File
        file_path = self.library_root / data['path']
        if file_path.exists():
            try:
                content = file_path.read_text(encoding="utf-8")
                self.current_code_content = content
                self.refresh_code_view()
            except Exception as e:
                self.set_code_text(f"Error reading file: {e}")
        else:
            self.set_code_text(f"File not found: {file_path}")

    # --- LOGIC: Bulk Selection ---

    def select_all(self):
        for iid in self.services_map:
            self.checked_items.add(iid)
            self._update_row_display(iid)

    def select_none(self):
        self.checked_items.clear()
        for iid in self.services_map:
            self._update_row_display(iid)

    def select_inverse(self):
        new_set = set()
        for iid in self.services_map:
            if iid not in self.checked_items:
                new_set.add(iid)
        self.checked_items = new_set
        for iid in self.services_map:
            self._update_row_display(iid)

    def _update_export_btn(self):
        count = len(self.checked_items)
        self.btn_export.config(text=f"EXPORT SELECTION ({count})")

    # --- LOGIC: View & Export ---

    def refresh_code_view(self):
        if not hasattr(self, 'current_code_content'): return
        content = self.current_code_content
        
        if self.show_line_numbers.get():
            lines = content.splitlines()
            numbered = [f"{i+1:03d} | {line}" for i, line in enumerate(lines)]
            self.set_code_text("\n".join(numbered))
        else:
            self.set_code_text(content)

    def set_code_text(self, text):
        self.txt_code.delete("1.0", "end")
        self.txt_code.insert("1.0", text)

    def copy_current_code(self):
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(self.txt_code.get("1.0", "end"))
        messagebox.showinfo("Copied", "Content copied to clipboard.")

    def change_library(self):
        path = filedialog.askdirectory(initialdir=self.library_root)
        if path:
            self.library_root = Path(path)
            self.lbl_path.config(text=str(self.library_root))
            self.refresh_library()

    def export_clipboard(self):
        if not self.checked_items:
            messagebox.showwarning("Empty", "Check some boxes first!")
            return
        
        output = []
        output.append("CONTEXT PACKET: MICROSERVICES")
        output.append("="*60 + "\n")
        
        # Sort by name for consistency
        sorted_ids = sorted(list(self.checked_items), key=lambda x: self.services_map[x]['name'])
        
        for iid in sorted_ids:
            data = self.services_map[iid]
            path = self.library_root / data['path']
            if path.exists():
                output.append(f"START FILE: {data['path']}")
                output.append("-" * 60)
                output.append(path.read_text(encoding="utf-8"))
                output.append("-" * 60)
                output.append(f"END FILE: {data['path']}\n\n")

        full_text = "\n".join(output)
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(full_text)
        messagebox.showinfo("Export", f"Packaged {len(sorted_ids)} services to clipboard.")

    def run(self):
        self.app.launch()

if __name__ == "__main__":
    browser = MicroserviceBrowserApp()
    browser.run()
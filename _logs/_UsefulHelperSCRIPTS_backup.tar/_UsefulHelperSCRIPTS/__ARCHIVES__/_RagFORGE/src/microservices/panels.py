import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import os
import time
import sqlite3
import threading
import time

# --- UI CONSTANTS ---
BG_COLOR = "#1e1e2f"
SIDEBAR_COLOR = "#171725"
ACCENT_COLOR = "#007ACC"
TEXT_COLOR = "#e0e0e0"
SUCCESS_COLOR = "#388E3C"

class SystemLog(tk.Frame):
    """A read-only scrolling log for system events."""
    def __init__(self, parent):
        super().__init__(parent, bg=BG_COLOR)
        tk.Label(self, text="SYSTEM LOG", bg=BG_COLOR, fg="#666", font=("Consolas", 9, "bold")).pack(anchor="w", padx=5, pady=(5,0))
        self.text = scrolledtext.ScrolledText(self, bg="#151515", fg="#00FF00", font=("Consolas", 9), height=8, bd=0)
        self.text.pack(fill="both", expand=True, padx=5, pady=5)
        self.text.config(state="disabled")

    def log(self, msg):
        self.text.config(state="normal")
        ts = time.strftime("%H:%M:%S")
        self.text.insert("end", f"[{ts}] {msg}\n")
        self.text.see("end")
        self.text.config(state="disabled")

class IngestToolbar(tk.Frame):
    """Top bar for selecting source and triggering actions."""
    def __init__(self, parent, on_scan, on_ingest):
        super().__init__(parent, bg=BG_COLOR, pady=5)
        self.on_scan = on_scan
        self.on_ingest = on_ingest
        self.path_var = tk.StringVar()

        # Label
        tk.Label(self, text="SOURCE:", bg=BG_COLOR, fg="#888", font=("Arial", 9, "bold")).pack(side="left", padx=(10, 5))
        
        # Entry
        self.entry = tk.Entry(self, textvariable=self.path_var, bg="#252526", fg="white", 
                              insertbackground="white", relief="flat", font=("Consolas", 10))
        self.entry.pack(side="left", fill="x", expand=True, padx=5, ipady=4)

        # Options
        tk.Label(self, text="Depth:", bg=BG_COLOR, fg="#666", font=("Arial", 8)).pack(side="left")
        self.spin_depth = tk.Spinbox(self, from_=0, to=5, width=3, bg="#333", fg="white", relief="flat")
        self.spin_depth.pack(side="left", padx=2)
        
        self.combo_policy = ttk.Combobox(self, values=["Extract Text", "Store Blob", "Skip Binary"], width=12, state="readonly")
        self.combo_policy.set("Extract Text")
        self.combo_policy.pack(side="left", padx=5)

        # Buttons
        btn_cfg = {"bg": "#444", "fg": "white", "relief": "flat", "padx": 10, "font": ("Arial", 9)}
        
        tk.Button(self, text="📄 File", command=self._browse_file, **btn_cfg).pack(side="left", padx=2)
        tk.Button(self, text="📂 Folder", command=self._browse_folder, **btn_cfg).pack(side="left", padx=2)
        
        # Separator
        tk.Frame(self, width=1, bg="#555").pack(side="left", fill="y", padx=10, pady=5)

        tk.Button(self, text="🔍 SCAN", command=self._trigger_scan, **btn_cfg).pack(side="left", padx=2)
        
        # Ingest (Green)
        ing_cfg = btn_cfg.copy()
        ing_cfg["bg"] = SUCCESS_COLOR
        ing_cfg["font"] = ("Arial", 9, "bold")
        tk.Button(self, text="▶ INGEST", command=self._trigger_ingest, **ing_cfg).pack(side="left", padx=(10, 10))

    def _browse_folder(self):
        d = filedialog.askdirectory()
        if d:
            self.path_var.set(d)
            self._trigger_scan()

    def _browse_file(self):
        f = filedialog.askopenfilename()
        if f:
            self.path_var.set(f)
            self._trigger_scan()

    def _trigger_scan(self):
        path = self.path_var.get().strip()
        try:
            depth = int(self.spin_depth.get())
        except: depth = 0
        
        policy = self.combo_policy.get()
        if path: self.on_scan(path, web_depth=depth, binary_policy=policy)

    def _trigger_ingest(self):
        self.on_ingest()


class FileTreePanel(tk.Frame):
    """Hierarchy Explorer with Checkboxes."""
    def __init__(self, parent, intake_service):
        super().__init__(parent, bg=BG_COLOR)
        self.intake = intake_service
        self.root_path = None
        self.node_map = {}
        
        # --- UI ASSETS: Programmatic Icons ---
        # Create 16x16 checkboxes using empty PhotoImages and coloring pixels (or simple rectangles)
        # 1. Unchecked (Gray outline)
        self.img_off = tk.PhotoImage(width=16, height=16)
        self.img_off.put(("#666",), to=(2, 2, 14, 14))   # Border
        self.img_off.put(("#1e1e2f",), to=(4, 4, 12, 12)) # Center (BG Color)
        
        # 2. Checked (Green Fill)
        self.img_on = tk.PhotoImage(width=16, height=16)
        self.img_on.put(("#388E3C",), to=(2, 2, 14, 14)) # Green Box
        self.img_on.put(("#ffffff",), to=(5, 7, 7, 12))  # Checkmark (simple L shape)
        self.img_on.put(("#ffffff",), to=(7, 10, 11, 7)) 

        # Header
        tk.Label(self, text="HIERARCHY EXPLORER", bg=BG_COLOR, fg="#666", 
                 font=("Consolas", 9, "bold")).pack(anchor="w", padx=5, pady=(5,0))

        # Tree (Inherits 'Treeview' style from app.py)
        self.tree = ttk.Treeview(self, show="tree", selectmode="none")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.tree.bind("<Button-1>", self._on_tree_click)
        
        sb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        sb.place(relx=1, rely=0, relheight=1, anchor="ne")
        self.tree.configure(yscrollcommand=sb.set)

    def load_tree(self, path, web_depth=0):
        self.root_path = path
        self.tree.delete(*self.tree.get_children())
        self.node_map = {}
        # Pass web_depth to scanner
        tree_data = self.intake.scan_path(path, web_depth=web_depth)
        if tree_data:
            self._insert_node("", tree_data)

    def _insert_node(self, parent_id, node):
        # Use the image property for the checkbox, keep text clean for the name
        img = self.img_on if node['checked'] else self.img_off
        
        item_id = self.tree.insert(parent_id, "end", text=f" {node['name']}", image=img, open=(parent_id==""))
        self.node_map[item_id] = node
        
        # Safely handle children
        children = node.get('children', [])
        for child in children:
            self._insert_node(item_id, child)

    def _on_tree_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: return
        
        # Identify what part of the item was clicked
        element = self.tree.identify_element(event.x, event.y)
        
        # Case 1: Clicked the Checkbox (Image) -> Toggle Selection
        if element == "image":
            self._toggle_check(item_id)
            return "break"
            
        # Case 2: Clicked the Row/Text -> Toggle Expand (if folder)
        else:
            # If it has children, toggle the open state
            if self.tree.get_children(item_id) or self.node_map[item_id]['type'] in ['dir', 'folder']:
                current_state = self.tree.item(item_id, "open")
                self.tree.item(item_id, open=not current_state)
                return "break"
            # If file, do nothing (or select row standard behavior)
            return

    def _toggle_check(self, item_id):
        node = self.node_map[item_id]
        new_state = not node['checked']
        self._set_node_state(item_id, new_state)
        self._save_config()

    def _set_node_state(self, item_id, state):
        node = self.node_map[item_id]
        node['checked'] = state
        
        # Update image only
        img = self.img_on if state else self.img_off
        self.tree.item(item_id, image=img)
        
        for child_id in self.tree.get_children(item_id):
            self._set_node_state(child_id, state)

    def _save_config(self):
        if not self.root_path or os.path.isfile(self.root_path): return
        flat_config = {n['rel_path']: n['checked'] for n in self.node_map.values()}
        self.intake.save_persistence(self.root_path, flat_config)

    def get_selected_files(self):
        selected = []
        for node in self.node_map.values():
            if node['checked'] and (node['type'] == 'file' or node['type'] == 'web'):
                selected.append(node['path'])
        return selected

class Sidebar(tk.Frame):
    """
    Manages the list of available Cartridges (.db files).
    """
    def __init__(self, parent, storage_dir, on_select_callback):
        super().__init__(parent, bg=SIDEBAR_COLOR, width=220)
        self.storage_dir = storage_dir
        self.on_select = on_select_callback
        self.pack_propagate(False)

        # Header
        tk.Label(self, text="_RagFORGE", bg=SIDEBAR_COLOR, fg=ACCENT_COLOR, 
                 font=("Consolas", 14, "bold"), pady=15).pack(fill="x")
        
        # List
        tk.Label(self, text="CARTRIDGES", bg=SIDEBAR_COLOR, fg="#666", 
                 font=("Arial", 8, "bold"), anchor="w", padx=10).pack(fill="x")
        
        self.listbox = tk.Listbox(self, bg=SIDEBAR_COLOR, fg=TEXT_COLOR, bd=0, 
                                  highlightthickness=0, selectbackground=ACCENT_COLOR)
        self.listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.listbox.bind("<<ListboxSelect>>", self._on_click)

        # Footer Actions
        btn_frame = tk.Frame(self, bg=SIDEBAR_COLOR, pady=10)
        btn_frame.pack(fill="x", side="bottom")
        
        row1 = tk.Frame(btn_frame, bg=SIDEBAR_COLOR)
        row1.pack(fill="x", pady=2)
        tk.Button(row1, text="📂 ROOT", bg="#2d2d44", fg="#aaa", relief="flat", font=("Arial", 8), 
                  command=self._change_root).pack(side="left", padx=10, fill="x", expand=True)
        
        row2 = tk.Frame(btn_frame, bg=SIDEBAR_COLOR)
        row2.pack(fill="x", pady=2)
        tk.Button(row2, text="REFRESH", bg="#2d2d44", fg="white", relief="flat", 
                  command=self.refresh).pack(side="left", padx=10, fill="x", expand=True)
        tk.Button(row2, text="+ NEW", bg="#2d2d44", fg="white", relief="flat", 
                  command=self._create_new).pack(side="right", padx=10, fill="x", expand=True)

        self.refresh()

    def _change_root(self):
        d = filedialog.askdirectory(title="Select Cartridge Library")
        if d:
            self.storage_dir = d
            self.refresh()

    def refresh(self):
        self.listbox.delete(0, tk.END)
        if not os.path.exists(self.storage_dir):
            os.makedirs(self.storage_dir)
        
        dbs = [f for f in os.listdir(self.storage_dir) if f.endswith(".db")]
        for db in dbs:
            self.listbox.insert(tk.END, db)

    def _on_click(self, event):
        sel = self.listbox.curselection()
        if sel:
            db_name = self.listbox.get(sel[0])
            self.on_select(os.path.join(self.storage_dir, db_name))

    def _create_new(self):
        name = simpledialog.askstring("New Cartridge", "Enter name (e.g. 'project_alpha'):")
        if name:
            if not name.endswith(".db"): name += ".db"
            path = os.path.join(self.storage_dir, name)
            # Just touching the file is enough, CartridgeService will init schema on load
            sqlite3.connect(path).close()
            self.refresh()

class EditorPanel(tk.Frame):
    """
    Views the 'files' table content.
    """
    def __init__(self, parent):
        super().__init__(parent, bg=BG_COLOR)
        self.active_db = None
        
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        
        # Left: File Tree
        self.tree = ttk.Treeview(paned, show="tree", selectmode="browse")
        self.tree.heading("#0", text="VFS Path", anchor="w")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        paned.add(self.tree, weight=1)
        
        # Right: Content
        self.editor = scrolledtext.ScrolledText(paned, bg="#252526", fg=TEXT_COLOR, 
                                                font=("Consolas", 10), insertbackground="white")
        paned.add(self.editor, weight=3)

    def load_db(self, db_path):
        self.active_db = db_path
        self.refresh_list()

    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        self.editor.delete("1.0", tk.END)
        
        if not self.active_db or not os.path.exists(self.active_db): return
        
        try:
            conn = sqlite3.connect(self.active_db)
            rows = conn.execute("SELECT id, vfs_path, status FROM files ORDER BY vfs_path").fetchall()
            conn.close()
            
            for rid, path, status in rows:
                display = f"[{status}] {path}"
                self.tree.insert("", "end", iid=rid, text=display, values=(path,))
        except Exception as e:
            print(f"Tree load error: {e}")

    def _on_select(self, event):
        sel = self.tree.selection()
        if not sel: return
        file_id = sel[0]
        
        try:
            conn = sqlite3.connect(self.active_db)
            row = conn.execute("SELECT content FROM files WHERE id=?", (file_id,)).fetchone()
            conn.close()
            
            self.editor.delete("1.0", tk.END)
            if row and row[0]:
                self.editor.insert("1.0", row[0])
            else:
                self.editor.insert("1.0", "(Binary content or empty)")
        except: pass







#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
== _MindWRAPPER Core ==
The Central Nervous System.
Mounts the Microservices (Intake, Refinery, Neural, Cartridge) and 
exposes them via both a GUI (Workbench) and a CLI (Headless).
"""

import sys
import argparse
import sqlite3
import time
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
from pathlib import Path
import threading

# --- MICROSERVICE IMPORTS ---
sys.path.append(str(Path(__file__).parent))

from microservices.base_service import BaseService
from microservices.neural_service import NeuralService
from microservices.cartridge_service import CartridgeService
from microservices.intake_service import IntakeService
from microservices.refinery_service import RefineryService
from microservices.librarian_service import LibrarianService

# --- CONFIGURATION ---
DEFAULT_DB_PATH = "./cortex_dbs/mindwrapper.db"

# ==============================================================================
#  THE ENGINE ROOM (Controller)
# ==============================================================================
class MindWrapperController(BaseService):
    """
    The 'Backend' Controller. 
    It owns the services so the GUI doesn't have to manage them directly.
    """
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        super().__init__("MindController")
        
        self.log_info(f"Mounting Services at {db_path}...")
        
        # 1. Mount Services
        self.neural = NeuralService(max_workers=8) 
        self.cartridge = CartridgeService(db_path)
        self.intake = IntakeService(self.cartridge)
        self.refinery = RefineryService(self.cartridge, self.neural)
        
        self.neural_online = self.neural.check_connection()
        if not self.neural_online:
            self.log_error("Ollama is OFFLINE. AI features disabled.")

class DatabaseView(tk.Frame):
    """
    The Inspector.
    Provides a raw SQL view of the Cartridge internals.
    """
    def __init__(self, parent, controller):
        super().__init__(parent, bg="#1e1e2f")
        self.ctrl = controller
        
        # --- Toolbar ---
        toolbar = tk.Frame(self, bg="#171725", pady=5, padx=5)
        toolbar.pack(fill="x")
        
        tk.Label(toolbar, text="TABLE:", bg="#171725", fg="gray", font=("Arial", 8, "bold")).pack(side="left")
        self.table_var = tk.StringVar()
        self.table_combo = ttk.Combobox(toolbar, textvariable=self.table_var, width=20, state="readonly")
        self.table_combo.pack(side="left", padx=5)
        self.table_combo.bind("<<ComboboxSelected>>", self.refresh_data)

        tk.Label(toolbar, text="FILTER:", bg="#171725", fg="gray", font=("Arial", 8, "bold")).pack(side="left", padx=(15, 5))
        self.search_entry = tk.Entry(toolbar, bg="#2d2d44", fg="white", insertbackground="white")
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Return>", self.refresh_data)
        
        tk.Button(toolbar, text="↻ REFRESH", bg="#444", fg="white", relief="flat", command=self.refresh_tables).pack(side="right", padx=5)

        # --- Data Grid ---
        self.tree_frame = tk.Frame(self, bg="#1e1e2f")
        self.tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.tree = ttk.Treeview(self.tree_frame, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(column=0, row=0, sticky='nsew')
        vsb.grid(column=1, row=0, sticky='ns')
        hsb.grid(column=0, row=1, sticky='ew')
        
        self.tree_frame.grid_columnconfigure(0, weight=1)
        self.tree_frame.grid_rowconfigure(0, weight=1)
        
        self.tree.bind("<Double-1>", self.on_double_click)
        
        # Initial Load
        self.refresh_tables()

    def refresh_tables(self):
        """Auto-discover tables in the DB."""
        try:
            conn = self.ctrl.cartridge._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [r[0] for r in cursor.fetchall() if not r[0].startswith('sqlite_')]
            conn.close()
            
            self.table_combo['values'] = tables
            if tables:
                if not self.table_var.get() or self.table_var.get() not in tables:
                    self.table_combo.set("files") # Default
                self.refresh_data()
        except Exception as e:
            print(f"DB Error: {e}")

    def refresh_data(self, event=None):
        table = self.table_var.get()
        if not table: return
        
        query_filter = self.search_entry.get().strip()
        self.tree.delete(*self.tree.get_children())
        
        try:
            conn = self.ctrl.cartridge._get_conn()
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. Get Columns
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [r[1] for r in cursor.fetchall()]
            
            # 2. Build Query
            sql = f"SELECT * FROM {table}"
            params = []
            
            if query_filter:
                # Smart Filter: Search in all text-like columns
                text_cols = [c for c in columns if 'id' in c or 'path' in c or 'content' in c or 'metadata' in c]
                if text_cols:
                    conditions = " OR ".join([f"{col} LIKE ?" for col in text_cols])
                    sql += f" WHERE {conditions}"
                    params = [f"%{query_filter}%" for _ in text_cols]
            
            sql += " LIMIT 100"
            
            # 3. Populate Tree
            self.tree['columns'] = columns
            for col in columns:
                self.tree.heading(col, text=col)
                self.tree.column(col, width=120)
                
            cursor.execute(sql, params)
            for row in cursor.fetchall():
                # Truncate long values for display
                values = []
                for val in row:
                    s = str(val)
                    if len(s) > 50: s = s[:50] + "..."
                    values.append(s)
                self.tree.insert("", "end", values=values, tags=(str(row[0]) if 'id' in row.keys() else '',))
                
            conn.close()
        except Exception as e:
            print(f"Data Fetch Error: {e}")

    def on_double_click(self, event):
        """Pop up a viewer for full cell content."""
        item = self.tree.identify_row(event.y)
        if not item: return
        
        # We need to fetch the REAL data, not the truncated view
        values = self.tree.item(item, 'values')
        
        top = tk.Toplevel(self)
        top.title("Cell Inspector")
        top.geometry("600x400")
        top.configure(bg="#252526")
        
        txt = scrolledtext.ScrolledText(top, bg="#1e1e2f", fg="#e0e0e0", font=("Consolas", 10))
        txt.pack(fill="both", expand=True)
        
        # Pretty print the row
        display_text = ""
        headers = self.tree['columns']
        for i, val in enumerate(values):
            header = headers[i] if i < len(headers) else f"Col {i}"
            display_text += f"[{header}]:\n{val}\n\n{'-'*40}\n\n"
            
        txt.insert("1.0", display_text)

# ==============================================================================
#  THE WORKBENCH (GUI)
# ==============================================================================
class SettingsModal(tk.Toplevel):
    """The Model Selector from NeoCORTEX, reborn."""
    def __init__(self, parent, neural_service):
        super().__init__(parent)
        self.neural = neural_service
        self.title("Neural Configuration")
        self.geometry("400x300")
        
        models = self.neural.get_available_models()
        
        tk.Label(self, text="Fast Model (Summary/Meta):").pack(pady=5)
        self.fast_var = tk.StringVar(value=self.neural.config["fast"])
        ttk.Combobox(self, textvariable=self.fast_var, values=models).pack(fill="x", padx=20)

        tk.Label(self, text="Smart Model (Complex Analysis):").pack(pady=5)
        self.smart_var = tk.StringVar(value=self.neural.config["smart"])
        ttk.Combobox(self, textvariable=self.smart_var, values=models).pack(fill="x", padx=20)
        
        tk.Button(self, text="Save", command=self.save).pack(pady=20)

    def save(self):
        self.neural.update_models(self.fast_var.get(), self.smart_var.get(), self.neural.config["embed"])
        self.destroy()

class MindWrapperApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("_MindWRAPPER Control Center")
        self.geometry("1100x700")
        
        # 1. Init Services
        self.librarian = LibrarianService()
        self.neural = NeuralService()
        self.controller = None # Will init when DB is loaded
        
        # 2. Setup Layout
        self._setup_sidebar()
        self._setup_main_area()

    def _setup_sidebar(self):
        sidebar = tk.Frame(self, bg="#171725", width=250)
        sidebar.pack(side="left", fill="y")
        
        # DB List
        tk.Label(sidebar, text="KNOWLEDGE BASES", bg="#171725", fg="#007ACC", font=("Arial", 10, "bold")).pack(pady=10)
        self.db_list = tk.Listbox(sidebar, bg="#1e1e2f", fg="white", bd=0)
        self.db_list.pack(fill="both", expand=True, padx=5)
        self.db_list.bind("<<ListboxSelect>>", self.load_db)
        
        # Controls
        btn_frame = tk.Frame(sidebar, bg="#171725")
        btn_frame.pack(fill="x", pady=10)
        tk.Button(btn_frame, text="+ NEW DB", command=self.create_db).pack(side="left", padx=5)
        tk.Button(btn_frame, text="⚙ SETTINGS", command=self.open_settings).pack(side="right", padx=5)
        
        self.refresh_db_list()

    def _setup_main_area(self):
        self.main_frame = tk.Frame(self, bg="#1e1e2f")
        self.main_frame.pack(side="right", fill="both", expand=True)
        
        # Intake Controls (Replaces the text entry)
        ctrl_frame = tk.Frame(self.main_frame, bg="#252526", pady=10)
        ctrl_frame.pack(fill="x")
        
        self.path_var = tk.StringVar()
        tk.Entry(ctrl_frame, textvariable=self.path_var, width=50).pack(side="left", padx=10)
        tk.Button(ctrl_frame, text="📂 Browse", command=self.browse_folder).pack(side="left")
        
        # Project Type Selector (New!)
        tk.Label(ctrl_frame, text="Type:", bg="#252526", fg="white").pack(side="left", padx=10)
        self.type_var = tk.StringVar(value="CODE")
        ttk.Combobox(ctrl_frame, textvariable=self.type_var, values=["CODE", "DOCS", "MIXED"], width=10).pack(side="left")
        
        tk.Button(ctrl_frame, text="RUN INGEST", bg="#007ACC", fg="white", command=self.run_ingest).pack(side="left", padx=20)

    def refresh_db_list(self):
        self.db_list.delete(0, tk.END)
        for db in self.librarian.list_cartridges():
            self.db_list.insert(tk.END, db)

    def create_db(self):
        # (Add simple popup to ask for name, then refresh list)
        pass

    def load_db(self, event):
        selection = self.db_list.curselection()
        if selection:
            db_name = self.db_list.get(selection[0])
            db_path = self.librarian.set_active(db_name)
            
            # NOW we initialize the heavy Controller/Cartridge services
            self.controller = MindWrapperController(db_path)
            self.controller.neural = self.neural # Share the configured neural service
            messagebox.showinfo("Loaded", f"Connected to {db_name}")

    def open_settings(self):
        SettingsModal(self, self.neural)

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path: self.path_var.set(path)

    def run_ingest(self):
        if not self.controller:
            messagebox.showerror("Error", "Load a Database first!")
            return
        # Call the controller.intake service...

# ==============================================================================
#  ENTRY POINT
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="_MindWRAPPER")
    parser.add_argument("--headless", action="store_true", help="Run in CLI mode")
    parser.add_argument("command", nargs="?", help="ingest/refine (only for headless)")
    parser.add_argument("path", nargs="?", help="Path for ingest")
    args = parser.parse_args()

    # Initialize Backend
    controller = MindWrapperController(DEFAULT_DB_PATH)

    if args.headless:
        # --- CLI MODE ---
        print("running in HEADLESS mode...")
        if args.command == "ingest" and args.path:
            controller.intake.scan_directory(args.path)
        elif args.command == "refine":
            # Simple loop
            while controller.refinery.process_pending_files(10) > 0:
                print("Processing batch...")
        else:
            print("Invalid Headless Arguments. Use: --headless ingest <path> OR --headless refine")
    else:
        # --- GUI MODE ---
        app = MindWrapperApp()
        app.mainloop()

if __name__ == "__main__":
    main()


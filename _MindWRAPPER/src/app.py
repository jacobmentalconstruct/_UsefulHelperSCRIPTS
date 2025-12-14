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
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path
import threading

# --- MICROSERVICE IMPORTS ---
sys.path.append(str(Path(__file__).parent))

from microservices.base_service import BaseService
from microservices.neural_service import NeuralService
from microservices.cartridge_service import CartridgeService
from microservices.intake_service import IntakeService
from microservices.refinery_service import RefineryService

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
class WorkbenchApp(tk.Tk):
    def __init__(self, controller: MindWrapperController):
        super().__init__()
        self.ctrl = controller
        self.title("_MindWRAPPER Workbench v2.0")
        self.geometry("1000x700")
        self.configure(bg="#1e1e2f")
        
        self._setup_ui()
        
    def _setup_ui(self):
        # --- HEADER ---
        header = tk.Frame(self, bg="#101018", pady=10)
        header.pack(fill="x")
        
        status_color = "#4caf50" if self.ctrl.neural_online else "#f44336"
        tk.Label(header, text="MindWRAPPER", bg="#101018", fg="white", font=("Consolas", 16, "bold")).pack(side="left", padx=20)
        tk.Label(header, text=f"Neural Link: {'ONLINE' if self.ctrl.neural_online else 'OFFLINE'}", bg="#101018", fg=status_color).pack(side="right", padx=20)

        # --- TABS ---
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook", background="#1e1e2f", borderwidth=0)
        style.configure("TNotebook.Tab", background="#2d2d44", foreground="white", padding=[15, 5])
        style.map("TNotebook.Tab", background=[("selected", "#007ACC")])

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)
        
        self._init_intake_tab()
        self._init_refinery_tab()
        self._init_inspector_tab()

    def _init_intake_tab(self):
        tab = tk.Frame(self.notebook, bg="#1e1e2f")
        self.notebook.add(tab, text="  INTAKE (Vacuum)  ")
        
        # Path Entry
        row1 = tk.Frame(tab, bg="#1e1e2f", pady=20)
        row1.pack(fill="x")
        tk.Label(row1, text="TARGET PATH:", bg="#1e1e2f", fg="gray").pack(side="left", padx=10)
        self.ent_path = tk.Entry(row1, bg="#2d2d44", fg="white", width=50)
        self.ent_path.insert(0, "./src") # Default
        self.ent_path.pack(side="left", fill="x", expand=True, padx=10)
        
        # Buttons
        btn_scan = tk.Button(row1, text="RUN VACUUM", bg="#007ACC", fg="white", relief="flat", padx=15, command=self._run_vacuum)
        btn_scan.pack(side="left", padx=10)
        
        # Log Output
        self.log_intake = scrolledtext.ScrolledText(tab, bg="#101018", fg="#00ff00", font=("Consolas", 9))
        self.log_intake.pack(fill="both", expand=True, padx=10, pady=10)

    def _init_refinery_tab(self):
        tab = tk.Frame(self.notebook, bg="#1e1e2f")
        self.notebook.add(tab, text="  REFINERY (Enrich)  ")
        
        ctrl_panel = tk.Frame(tab, bg="#1e1e2f", pady=20)
        ctrl_panel.pack(fill="x")
        
        self.lbl_pending = tk.Label(ctrl_panel, text="Pending Files: ?", bg="#1e1e2f", fg="yellow", font=("Arial", 12))
        self.lbl_pending.pack(side="left", padx=20)
        
        btn_refresh = tk.Button(ctrl_panel, text="↻ Refresh", bg="#444", fg="white", relief="flat", command=self._refresh_stats)
        btn_refresh.pack(side="left", padx=5)
        
        btn_process = tk.Button(ctrl_panel, text="RUN NIGHT SHIFT", bg="#E02080", fg="white", relief="flat", padx=15, command=self._run_refinery)
        btn_process.pack(side="right", padx=20)
        
        self.log_refinery = scrolledtext.ScrolledText(tab, bg="#101018", fg="#00ccff", font=("Consolas", 9))
        self.log_refinery.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Initial Load
        self.after(500, self._refresh_stats)

    def _init_inspector_tab(self):
        tab = tk.Frame(self.notebook, bg="#1e1e2f")
        self.notebook.add(tab, text="  CARTRIDGE INSPECTOR  ")
        
        # Initialize the DatabaseView
        # We pass self.ctrl so it can access the CartridgeService
        inspector = DatabaseView(tab, self.ctrl)
        inspector.pack(fill="both", expand=True)

    # --- ACTIONS ---

    def _log(self, widget, msg):
        widget.insert(tk.END, msg + "\n")
        widget.see(tk.END)

    def _run_vacuum(self):
        path = self.ent_path.get()
        self._log(self.log_intake, f"--- Starting Scan: {path} ---")
        
        def worker():
            stats = self.ctrl.intake.scan_directory(path)
            self._log(self.log_intake, f"Scan Complete.\n{stats}")
            self.after(0, self._refresh_stats) # Refresh stats on main thread
            
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_stats(self):
        try:
            pending = self.ctrl.cartridge.get_pending_files(limit=9999)
            count = len(pending)
            self.lbl_pending.config(text=f"Pending Files: {count}")
        except:
            self.lbl_pending.config(text="Pending Files: Error")

    def _run_refinery(self):
        self._log(self.log_refinery, "--- Starting Refinery ---")
        
        def worker():
            total = 0
            while True:
                # Process in small batches to keep UI updating
                count = self.ctrl.refinery.process_pending_files(batch_size=5)
                if count == 0:
                    break
                total += count
                self._log(self.log_refinery, f"Enriched {count} files...")
                self.after(0, self._refresh_stats)
            
            self._log(self.log_refinery, f"--- Refinery Finished. Total: {total} ---")

        threading.Thread(target=worker, daemon=True).start()

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
        app = WorkbenchApp(controller)
        app.mainloop()

if __name__ == "__main__":
    main()

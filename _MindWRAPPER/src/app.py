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
        tk.Label(tab, text="[Placeholder for Database Viewer]", bg="#1e1e2f", fg="gray").pack(pady=50)

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
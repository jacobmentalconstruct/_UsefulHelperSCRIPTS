#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
== _RagFORGE: Neural Cartridge Factory ==
"""

# 1. IMPORTS
import sys
import os

# --- PATH PATCH START ---
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)
# --- PATH PATCH END ---

import argparse
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# Microservices
from microservices.base_service import BaseService
from microservices.cartridge_service import CartridgeService
from microservices.neural_service import NeuralService
from microservices.intake_service import IntakeService
from microservices.refinery_service import RefineryService
from microservices.telemetry_service import TelemetryService

# UI Components
from microservices.panels import (
    Sidebar,
    IngestToolbar,
    FileTreePanel,
    EditorPanel,
    SystemLog,
)
from microservices.graph_view import GraphView
from microservices.thought_stream import ThoughtStream

# 2. CONSTANTS
APP_TITLE = "_RagFORGE v1.0"
STORAGE_DIR = "./cartridges"
BG_COLOR = "#1e1e2f"


# 3. CORE FUNCTIONALITY (Headless Logic)

def headless_forge(source_path: str, db_name: str, verbose: bool = False):
    """CLI Entry point for automated cartridge creation."""
    if not db_name.endswith(".db"):
        db_name += ".db"

    db_path = os.path.join(STORAGE_DIR, db_name)

    print(f"[FORGE] Target Cartridge: {db_path}")
    print(f"[FORGE] Source Material: {source_path}")

    cartridge = CartridgeService(db_path)
    neural = NeuralService()
    intake = IntakeService(cartridge)
    refinery = RefineryService(cartridge, neural)

    print(">>> Phase 1: Intake (Vacuuming files...)")
    stats = intake.ingest_source(source_path)
    print(f"    Intake Result: {stats}")
    
    # Verify Manifest
    cid = cartridge.get_manifest("cartridge_id")
    print(f"    [Manifest] Cartridge ID: {cid}")

    print(">>> Phase 2: Refinery (Chunking & Weaving...)")
    while True:
        processed = refinery.process_pending(batch_size=10)
        if processed == 0:
            break
        if verbose:
            print(f"    Refined batch of {processed}...")

    print(f"[SUCCESS] Cartridge forged at {db_path}")
    return db_path


# 4. GUI LOGIC (The Workstation)

class RagForgeApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1200x800")
        self.configure(bg=BG_COLOR)

        self.neural = NeuralService()
        self.active_cartridge = None
        self.active_db_path = None
        self.refining = False

        self._apply_cyberpunk_theme()
        self._setup_ui()

    def _apply_cyberpunk_theme(self):
        """Injects the Dark/Cyberpunk visual style globally."""
        style = ttk.Style(self)

        try:
            style.theme_use("clam")
        except Exception:
            pass

        dark_bg = "#1e1e2f"
        darker_bg = "#151515"
        text_fg = "#e0e0e0"
        accent = "#007ACC"
        border = "#333344"

        # Treeviews
        style.configure(
            "Treeview",
            background=darker_bg,
            fieldbackground=darker_bg,
            foreground=text_fg,
            borderwidth=0,
            rowheight=26,
            font=("Segoe UI", 10),
        )
        style.map(
            "Treeview",
            background=[("selected", accent)],
            foreground=[("selected", "white")],
        )

        style.configure(
            "Treeview.Heading",
            background=dark_bg,
            foreground="#888",
            relief="flat",
            font=("Segoe UI", 9, "bold"),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", "#2d2d44")],
        )

        # Scrollbars
        style.configure(
            "Vertical.TScrollbar",
            gripcount=0,
            background="#2d2d44",
            darkcolor=dark_bg,
            lightcolor=dark_bg,
            troughcolor=dark_bg,
            bordercolor=dark_bg,
            arrowcolor="#888",
        )
        style.map(
            "Vertical.TScrollbar",
            background=[("active", "#444"), ("disabled", dark_bg)],
        )

        # Tabs
        style.configure(
            "TNotebook",
            background=dark_bg,
            borderwidth=0,
        )
        style.configure(
            "TNotebook.Tab",
            background="#252526",
            foreground="#888",
            padding=[15, 8],
            font=("Segoe UI", 10),
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", accent)],
            foreground=[("selected", "white")],
        )

        # Panes
        style.configure("TPanedwindow", background=dark_bg)
        style.configure("Sash", background=border, handlecv_bg=border)

    def _setup_ui(self):
        self.sidebar = Sidebar(self, STORAGE_DIR, self.load_cartridge)
        self.sidebar.pack(side="left", fill="y")

        self.main_area = tk.Frame(self, bg=BG_COLOR)
        self.main_area.pack(side="right", fill="both", expand=True)

        self.notebook = ttk.Notebook(self.main_area)
        self.notebook.pack(fill="both", expand=True)

        self.tab_forge = tk.Frame(self.notebook, bg=BG_COLOR)
        self.notebook.add(self.tab_forge, text="  DATA INGESTION  ")

        self.ingest_toolbar = IngestToolbar(
            self.tab_forge,
            on_scan=self.run_scan_request,
            on_ingest=self.run_ingest_request,
        )
        self.ingest_toolbar.pack(fill="x", side="top")

        forge_panes = ttk.PanedWindow(self.tab_forge, orient="horizontal")
        forge_panes.pack(fill="both", expand=True, padx=5, pady=5)

        self.file_tree = FileTreePanel(forge_panes, None)
        forge_panes.add(self.file_tree, weight=1)

        right_col = ttk.PanedWindow(forge_panes, orient="vertical")
        forge_panes.add(right_col, weight=3)

        self.stream = ThoughtStream(right_col)
        right_col.add(self.stream, weight=3)

        self.sys_log = SystemLog(right_col)
        right_col.add(self.sys_log, weight=1)

        # Initialize the Nervous System (Telemetry)
        self.telemetry = TelemetryService(self, self.sys_log)
        self.telemetry.start()

        self.editor_panel = EditorPanel(self.notebook)
        self.notebook.add(self.editor_panel, text="  KNOWLEDGE INSPECTOR  ")

        self.graph_view = GraphView(self.notebook)
        self.notebook.add(self.graph_view, text="  NEURAL TOPOLOGY  ")

        status_frame = tk.Frame(
            self.main_area,
            bg="#101018",
            height=25,
            highlightbackground="#333",
            highlightthickness=1,
        )
        status_frame.pack(fill="x", side="bottom")
        status_frame.pack_propagate(False)

        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(
            status_frame,
            textvariable=self.status_var,
            bg="#101018",
            fg="#888",
            font=("Arial", 9),
        ).pack(side="left", padx=10)

    # Remaining methods unchanged …


    def load_cartridge(self, path):
        """Called when user clicks a DB in sidebar."""
        self.active_db_path = path
        self.status_var.set(f"Loaded: {os.path.basename(path)}")
        self.title(f"{APP_TITLE} - [{os.path.basename(path)}]")
        
        # 1. Init Backend for this specific cartridge
        self.active_cartridge = CartridgeService(path)
        
        # 2. Wire up panels
        new_intake = IntakeService(self.active_cartridge)
        self.file_tree.intake = new_intake
        self.editor_panel.load_db(path)
        self.sys_log.log(f"Cartridge loaded: {os.path.basename(path)}")
        
        # 3. Load Graph (Non-blocking)
        self.graph_view.bind_services(self.active_cartridge, self.neural)
        self.graph_view.load_from_db(path)
        
        # 4. Start Background Poller (The Refinery Daemon)
        if not self.refining:
            self.refining = True
            self.after(1000, self._refinery_loop)

    def run_scan_request(self, path, web_depth=0, binary_policy="Extract Text"):
        if not self.active_cartridge:
            messagebox.showwarning("No Cartridge", "Select a cartridge first.")
            return
        
        # Update Manifest with policy preference
        self.active_cartridge.set_manifest("binary_policy", binary_policy)
        self.active_cartridge.set_manifest("web_depth", web_depth)

        self.status_var.set(f"Scanning {path} (Depth: {web_depth})...")
        self.file_tree.load_tree(path, web_depth=web_depth)
        self.sys_log.log(f"Scanned source: {path}")
        self.status_var.set("Scan complete. Select files to ingest.")

    def run_ingest_request(self):
        if not self.active_cartridge:
            return
        
        files = self.file_tree.get_selected_files()
        root = self.file_tree.root_path
        
        if not files:
            messagebox.showwarning("No Files", "No files selected for ingestion.")
            return

        def worker():
            count = len(files)
            msg = f"Ingesting {count} items..."
            self.status_var.set(msg)
            self.sys_log.log(msg)
            try:
                # Access intake via file_tree which now holds the reference
                stats = self.file_tree.intake.ingest_selected(files, root)
                done_msg = f"Ingest Result: {stats}"
                self.status_var.set(done_msg)
                self.sys_log.log(done_msg)
            except Exception as e:
                err = f"Ingest Failed: {e}"
                self.sys_log.log(err)
            
            # Refresh UI elements on main thread
            def _refresh():
                self.editor_panel.refresh_list()
                self.graph_view.load_from_db(self.active_db_path)
                
            self.after(0, _refresh)

        threading.Thread(target=worker, daemon=True).start()

    def _refinery_loop(self):
        """
        The Heartbeat. Checks for RAW files and processes them in small batches.
        Keeps the UI responsive while chewing through data.
        """
        if self.active_cartridge:
            # We create a transient refinery instance to process the batch
            # Ideally, this should be persistent, but for now this works.
            refinery = RefineryService(self.active_cartridge, self.neural)
            
            try:
                # Process a small batch
                processed = refinery.process_pending(batch_size=1)
                
                if processed > 0:
                    self.status_var.set("Refining Knowledge... (Embedding & Weaving)")
                    # Update visuals occasionally
                    if processed % 5 == 0:
                        self.graph_view.load_from_db(self.active_db_path)
                        self.editor_panel.refresh_list()
                else:
                    current_status = self.status_var.get()
                    if "Refining" in current_status:
                        self.status_var.set("Refinery Idle. Cartridge up to date.")
                        self.graph_view.load_from_db(self.active_db_path)
                        self.editor_panel.refresh_list()
            except Exception as e:
                print(f"Refinery Loop Error: {e}")

        # Loop
        self.after(2000, self._refinery_loop)


# 5. CLI ENTRY POINT

def main():
    parser = argparse.ArgumentParser(description="_RagFORGE: Neural Cartridge Factory")
    
    # CLI Args for Headless Mode
    parser.add_argument("--input", "-i", type=str, help="Input source path (folder or URL)")
    parser.add_argument("--output", "-o", type=str, help="Output .db filename (e.g. 'my_brain.db')")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logs")
    
    args = parser.parse_args()

    if args.input and args.output:
        # HEADLESS MODE
        try:
            headless_forge(args.input, args.output, args.verbose)
        except Exception as e:
            print(f"[FATAL] {e}")
            sys.exit(1)
    else:
        # GUI MODE
        app = RagForgeApp()
        app.mainloop()

if __name__ == "__main__":
    main()







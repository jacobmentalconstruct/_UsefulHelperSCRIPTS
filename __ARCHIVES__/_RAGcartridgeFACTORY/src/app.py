import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import logging
import os
import sys

# --- PATH SETUP ---
# Get the absolute path to the 'src' folder
current_dir = os.path.dirname(os.path.abspath(__file__))
microservices_dir = os.path.join(current_dir, "microservices")

# Add both to sys.path so Python can "see" files in both locations
sys.path.append(current_dir)
sys.path.append(microservices_dir) 

# --- Imports ---
from microservices._TkinterAppShellMS import TkinterAppShellMS
from microservices._WorkbenchLayoutMS import WorkbenchLayoutMS
from microservices._TkinterSmartExplorerMS import TkinterSmartExplorerMS
from microservices._TkinterThemeManagerMS import TkinterThemeManagerMS
from microservices._LogViewMS import LogViewMS
from microservices._ThoughtStreamMS import ThoughtStreamMS
from microservices._NeuralGraphViewerMS import NeuralGraphViewerMS
from microservices._TelemetryServiceMS import TelemetryServiceMS
from microservices._ScoutMS import ScoutMS
from orchestrator import ForgeOrchestrator, ForgeState

class RAGFactoryApp:
    def __init__(self):
        # 1. Boot Shell
        self.theme_mgr = TkinterThemeManagerMS() # Initialize first
        self.shell = TkinterAppShellMS({
            "title": "RAGcartridge FACTORY", 
            "geometry": "1400x900",
            "theme_manager": self.theme_mgr
        })
        self.root = self.shell.root
        
        # [NEW] APPLY THE DARK THEME NOW
        self.theme_mgr.apply_theme(self.root) 
                
        # 2. Boot Services
        self.telemetry = TelemetryServiceMS({"root": self.root})
        self.orchestrator = ForgeOrchestrator(self.telemetry)
        
        # 3. Define The Layout Manifest (Declarative!)
        layout_config = {
            "type": "col", 
            "children": [
                {"type": "panel", "id": "pnl_left", "weight": 1},   # Source/Explorer
                {"type": "panel", "id": "pnl_center", "weight": 3}, # Workflow/Graph
                {"type": "panel", "id": "pnl_right", "weight": 1}   # Logs
            ]
        }
        
        # 4. Build Layout
        self.layout_engine = WorkbenchLayoutMS({"parent": self.shell.get_main_container()})
        self.layout_engine.pack(fill="both", expand=True)
        self.layout_engine.build_from_manifest(layout_config)
        
        # 5. Inject Content into Panels
        self._setup_left_panel(self.layout_engine.get_panel("pnl_left"))
        self._setup_center_panel(self.layout_engine.get_panel("pnl_center"))
        self._setup_right_panel(self.layout_engine.get_panel("pnl_right"))

        # 6. Start
        self.telemetry.start()
        self._update_loop()

    def _setup_left_panel(self, parent):
        ttk.Label(parent, text="SOURCE", font="bold").pack(fill="x")
        ttk.Button(parent, text="📂 Load Cartridge", command=self.action_load_cartridge).pack(fill="x")
        ttk.Button(parent, text="🔍 Select Source", command=self.action_select_source).pack(fill="x", pady=5)
        
        ttk.Separator(parent, orient="horizontal").pack(fill="x", pady=10)
        
        self.explorer = TkinterSmartExplorerMS({"parent": parent})
        self.explorer.pack(fill="both", expand=True)

    def _setup_center_panel(self, parent):
        self.lbl_status = ttk.Label(parent, text="STATUS: IDLE", background="#333", foreground="#0f0", anchor="center")
        self.lbl_status.pack(fill="x", ipady=5)
        
        # Workflow Bar
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=5)
        self.btn_scan = ttk.Button(bar, text="SCAN", command=self.action_scan, state="disabled")
        self.btn_scan.pack(side="left", fill="x", expand=True)
        self.btn_ingest = ttk.Button(bar, text="INGEST", command=self.action_ingest, state="disabled")
        self.btn_ingest.pack(side="left", fill="x", expand=True)
        self.btn_refine = ttk.Button(bar, text="REFINE", command=self.action_refine, state="disabled")
        self.btn_refine.pack(side="left", fill="x", expand=True)
        self.btn_stop = ttk.Button(bar, text="STOP", command=self.action_stop, state="disabled")
        self.btn_stop.pack(side="left")

        self.graph_viewer = NeuralGraphViewerMS(parent) # Auto-packs itself
        
    def _setup_right_panel(self, parent):
        self.thought_stream = ThoughtStreamMS({"parent": parent})
        # [FIXED] Removed invalid 'height=200', replaced with 'ipady=10'
        self.thought_stream.pack(fill="x", pady=(0, 10), ipady=10)
        
        self.log_view = LogViewMS({"parent": parent, "log_queue": self.telemetry.log_queue})
        self.log_view.pack(fill="both", expand=True)

    # --- Actions ---
    def action_load_cartridge(self): 
        path = filedialog.asksaveasfilename(title="Create/Open Cartridge", defaultextension=".sqlite")
        if path: self.orchestrator.select_cartridge(path)

    def action_select_source(self): 
        self.source_path = filedialog.askdirectory()
        if self.source_path: self.btn_scan.config(state="normal")

    def action_scan(self): 
        self.orchestrator.scan(self.source_path)

    def action_ingest(self): 
        # Use ScannerMS/ScoutMS logic to flatten tree
        scout = ScoutMS()
        file_list = scout.flatten_tree(self.orchestrator.get_last_scan_tree())
        self.orchestrator.ingest(file_list, self.source_path)

    def action_refine(self): 
        self.orchestrator.refine_until_idle()

    def action_stop(self): 
        self.orchestrator.cancel()

    # --- Loop ---
    def _update_loop(self):
        current_state = self.orchestrator.get_state()
        
        if current_state != self.orchestrator.get_state():
             self.lbl_status.config(text=f"STATUS: {current_state}")

        # Update Explorer if Scanned
        if current_state == ForgeState.SCANNED.value and not self.explorer.tree_data:
             self.explorer.load_data(self.orchestrator.get_last_scan_tree())
        
        # Bind Graph if ready
        if current_state in [ForgeState.CARTRIDGE_SELECTED.value, ForgeState.READY.value] and not getattr(self, 'graph_bound', False):
             if self.orchestrator.cartridge and self.orchestrator.neural:
                 self.graph_viewer.bind_services(self.orchestrator.cartridge, self.orchestrator.neural)
                 self.graph_viewer.load_from_db(self.orchestrator.cartridge.db_path)
                 self.graph_bound = True

        self.root.after(100, self._update_loop)

    def launch(self):
        self.shell.launch()

if __name__ == "__main__":
    app = RAGFactoryApp()
    app.launch()
"""
SERVICE_NAME: _TkinterAppShellMS
ENTRY_POINT: _TkinterAppShellMS.py
DEPENDENCIES: None
"""
import tkinter as tk
from tkinter import ttk
import logging
import json
import os
from typing import Dict, Any, Optional

from microservice_std_lib import service_metadata, service_endpoint

# Updated Import
try:
    from _TkinterThemeManagerMS import TkinterThemeManagerMS
except ImportError:
    TkinterThemeManagerMS = None

logger = logging.getLogger("AppShell")

@service_metadata(
    name="TkinterAppShell",
    version="2.1.0",
    description="The Application Container. Manages root window, layout persistence, and lifecycle.",
    tags=["ui", "core", "lifecycle"],
    capabilities=["ui:root", "ui:gui"]
)
class TkinterAppShellMS:
    """
    The Mother Ship.
    Owns the Tkinter Root and remembers where you parked it.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.root = tk.Tk()
        self.root.withdraw() # Hide during setup
        
        # State File (Saved next to the App/EXE)
        self.layout_file = "window_layout.json"
        
        # Load Theme
        self.theme_svc = self.config.get("theme_manager")
        if not self.theme_svc and TkinterThemeManagerMS:
            self.theme_svc = TkinterThemeManagerMS()
            
        self.colors = self.theme_svc.get_theme() if self.theme_svc else {}
        self._configure_root()
        
        # Bind the "X" button to our smart shutdown
        self.root.protocol("WM_DELETE_WINDOW", self.shutdown)
        
    def _configure_root(self):
        self.root.title(self.config.get("title", "Microservice OS"))
        
        # Apply Base Theme
        bg = self.colors.get('background', '#1e1e1e')
        self.root.configure(bg=bg)
        
        # Configure TTK Styles
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background=bg)
        style.configure('TLabel', background=bg, foreground=self.colors.get('foreground', '#ccc'))
        style.configure('TButton', background=self.colors.get('panel_bg', '#333'), foreground='white')
        
        # --- SMART GEOMETRY RESTORE ---
        restored = False
        if os.path.exists(self.layout_file):
            try:
                with open(self.layout_file, 'r') as f:
                    data = json.load(f)
                    # Apply geometry (Size + Position)
                    if "geometry" in data:
                        self.root.geometry(data["geometry"])
                    # Apply Maximized State
                    if data.get("zoomed", False):
                        self.root.state('zoomed')
                    restored = True
            except Exception as e:
                logger.error(f"Failed to load layout: {e}")

        # Fallback if no save file exists
        if not restored:
            self.root.geometry("1024x768") # Safe default
        
        # Main Container
        self.main_container = tk.Frame(self.root, bg=bg)
        self.main_container.pack(fill="both", expand=True, padx=5, pady=5)

    @service_endpoint(
        inputs={},
        outputs={},
        description="Starts the GUI Main Loop.",
        tags=["lifecycle", "start"],
        mode="sync",
        side_effects=["ui:block"]
    )
    def launch(self):
        """Ignition sequence start."""
        self.root.deiconify()
        logger.info("AppShell Launched.")
        self.root.mainloop()

    @service_endpoint(
        inputs={},
        outputs={"container": "tk.Frame"},
        description="Returns the main content area for other services to dock into.",
        tags=["ui", "layout"]
    )
    def get_main_container(self):
        return self.main_container

    @service_endpoint(
        inputs={},
        outputs={},
        description="Saves layout and shuts down.",
        tags=["lifecycle", "stop"],
        side_effects=["ui:close", "disk:write"]
    )
    def shutdown(self):
        """Saves current window state before exiting."""
        try:
            # Capture state
            is_zoomed = (self.root.state() == 'zoomed')
            geo = self.root.geometry()
            
            with open(self.layout_file, 'w') as f:
                json.dump({
                    "geometry": geo,
                    "zoomed": is_zoomed
                }, f)
        except Exception as e:
            logger.error(f"Could not save layout: {e}")
            
        self.root.quit()

if __name__ == "__main__":
    shell = TkinterAppShellMS({"title": "Test Shell"})
    shell.launch()
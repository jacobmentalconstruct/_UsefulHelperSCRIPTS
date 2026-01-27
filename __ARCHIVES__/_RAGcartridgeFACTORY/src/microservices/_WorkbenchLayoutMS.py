"""
SERVICE_NAME: _WorkbenchLayoutMS
ENTRY_POINT: _WorkbenchLayoutMS.py
DEPENDENCIES: tkinter
"""
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, Optional, Callable

from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
    name="WorkbenchLayout",
    version="1.0.0",
    description="A declarative layout engine that builds resizable, nested Workbenches (Rows/Cols) from a config dictionary.",
    tags=["ui", "layout", "framework"],
    capabilities=["ui:construct"]
)
class WorkbenchLayoutMS(tk.Frame):
    """
    The Architect.
    Recursively builds a UI based on a 'Layout Manifest'.
    Uses ttk.PanedWindow to allow user resizing of areas.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        parent = config.get("parent")
        super().__init__(parent)
        self.config = config or {}
        
        # Registry to hold references to created panels so app.py can find them
        self.panel_registry: Dict[str, tk.Widget] = {}

    @service_endpoint(
        inputs={"manifest": "Dict"},
        outputs={},
        description="Builds the UI structure based on the provided dictionary layout.",
        tags=["ui", "build"]
    )
    def build_from_manifest(self, manifest: Dict[str, Any]):
        """
        Manifest Schema:
        {
            "type": "row" | "col",
            "weight": int,  # 1 = expands, 0 = fixed
            "children": [
                { "type": "panel", "id": "my_panel_id", "weight": 1 },
                { "type": "row", "weight": 2, "children": [...] }
            ]
        }
        """
        # Clear previous
        for widget in self.winfo_children():
            widget.destroy()
        
        # Build Root
        self._build_recursive(self, manifest)
        
    def get_panel(self, panel_id: str) -> Optional[tk.Widget]:
        """Retrieve a specific container by ID to pack widgets into."""
        return self.panel_registry.get(panel_id)

    def _build_recursive(self, parent_widget, node: Dict[str, Any]):
        node_type = node.get("type", "panel")
        weight = node.get("weight", 1)
        
        # A. Container Nodes (Row/Col) -> PanedWindow
        if node_type in ["row", "col"]:
            orient = tk.HORIZONTAL if node_type == "col" else tk.VERTICAL
            
            # Create the splitter
            container = ttk.PanedWindow(parent_widget, orient=orient)
            
            # Pack/Add to parent
            # If parent is a PanedWindow, we use .add(), else .pack()
            if isinstance(parent_widget, ttk.PanedWindow):
                parent_widget.add(container, weight=weight)
            else:
                container.pack(fill="both", expand=True)

            # Recurse for children
            for child in node.get("children", []):
                self._build_recursive(container, child)

        # B. Leaf Nodes (Panel) -> Frame
        elif node_type == "panel":
            p_id = node.get("id", "unknown")
            
            # Create the content frame
            frame = ttk.Frame(parent_widget, padding=2)
            # Register it so we can put stuff in it later
            self.panel_registry[p_id] = frame
            
            if isinstance(parent_widget, ttk.PanedWindow):
                parent_widget.add(frame, weight=weight)
            else:
                frame.pack(fill="both", expand=True)
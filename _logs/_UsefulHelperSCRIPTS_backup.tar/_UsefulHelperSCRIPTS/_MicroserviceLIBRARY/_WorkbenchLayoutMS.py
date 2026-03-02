"""
SERVICE_NAME: _WorkbenchLayoutMS
ENTRY_POINT: _WorkbenchLayoutMS.py
INTERNAL_DEPENDENCIES: microservice_std_lib
EXTERNAL_DEPENDENCIES: None
"""
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, Optional, Callable
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(name='WorkbenchLayout', version='1.0.0', description='A declarative layout engine that builds resizable, nested Workbenches (Rows/Cols) from a config dictionary.', tags=['ui', 'layout', 'framework'], capabilities=['ui:construct'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class WorkbenchLayoutMS(tk.Frame):
    """
    The Architect.
    Recursively builds a UI based on a 'Layout Manifest'.
    Uses ttk.PanedWindow to allow user resizing of areas.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        parent = config.get('parent')
        super().__init__(parent)
        self.config = config or {}
        self.panel_registry: Dict[str, tk.Widget] = {}

    @service_endpoint(inputs={'manifest': 'Dict'}, outputs={}, description='Builds the UI structure based on the provided dictionary layout.', tags=['ui', 'build'])
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
        for widget in self.winfo_children():
            widget.destroy()
        self._build_recursive(self, manifest)

    def get_panel(self, panel_id: str) -> Optional[tk.Widget]:
        """Retrieve a specific container by ID to pack widgets into."""
        return self.panel_registry.get(panel_id)

    def _build_recursive(self, parent_widget, node: Dict[str, Any]):
        node_type = node.get('type', 'panel')
        weight = node.get('weight', 1)
        if node_type in ['row', 'col']:
            orient = tk.HORIZONTAL if node_type == 'col' else tk.VERTICAL
            container = ttk.PanedWindow(parent_widget, orient=orient)
            if isinstance(parent_widget, ttk.PanedWindow):
                parent_widget.add(container, weight=weight)
            else:
                container.pack(fill='both', expand=True)
            for child in node.get('children', []):
                self._build_recursive(container, child)
        elif node_type == 'panel':
            p_id = node.get('id', 'unknown')
            frame = ttk.Frame(parent_widget, padding=2)
            self.panel_registry[p_id] = frame
            if isinstance(parent_widget, ttk.PanedWindow):
                parent_widget.add(frame, weight=weight)
            else:
                frame.pack(fill='both', expand=True)

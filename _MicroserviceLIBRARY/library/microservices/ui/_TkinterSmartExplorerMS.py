"""
SERVICE_NAME: _TkinterSmartExplorerMS
ENTRY_POINT: _TkinterSmartExplorerMS.py
INTERNAL_DEPENDENCIES: microservice_std_lib
EXTERNAL_DEPENDENCIES: None
"""
import tkinter as tk
from tkinter import ttk
from typing import Dict, Any, Optional, List
from microservice_std_lib import service_metadata, service_endpoint
import time

@service_metadata(name='TkinterSmartExplorer', version='1.0.0', description='A hierarchical tree viewer capable of displaying file systems or JSON data structures.', tags=['ui', 'widget', 'explorer'], capabilities=['ui:gui'], internal_dependencies=['microservice_std_lib'], external_dependencies=[], side_effects=['ui:update'])
class TkinterSmartExplorerMS(tk.Frame):
    """
    The Navigator.
    A TreeView widget that expects standard 'Node' dictionaries (name, type, children).
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        parent = self.config.get('parent')
        theme = self.config.get('theme', {})
        super().__init__(parent, bg=theme.get('panel_bg', '#252526'))
        self.tree = ttk.Treeview(self, show='tree headings', selectmode='browse')
        self.tree.heading('#0', text='Explorer', anchor='w')
        vsb = ttk.Scrollbar(self, orient='vertical', command=self.tree.yview)
        hsb = ttk.Scrollbar(self, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        vsb.pack(side='right', fill='y')
        default_icons = {'folder': '📁', 'file': '📄', 'web': '🌐', 'unknown': '❓'}
        self.theme_manager = self.config.get('theme_manager')
        if self.theme_manager and hasattr(self.theme_manager, 'get_node_icons'):
            try:
                icon_map = self.theme_manager.get_node_icons()
                default_icons.update(icon_map)
            except Exception:
                pass
        self.icons = default_icons

    @service_endpoint(inputs={'data': 'Dict'}, outputs={}, description="Populates the tree view with a nested dictionary structure (Standard 'Node' format).", tags=['ui', 'update'], side_effects=['ui:update'])
    def load_data(self, data: Dict[str, Any]):
        """
        Ingests a dictionary tree (like from _ScoutMS or _TreeMapperMS).
        """
        for item in self.tree.get_children():
            self.tree.delete(item)
        self._build_node('', data)

    @service_endpoint(inputs={}, outputs={'schema': 'Dict'}, description='Returns a headless UI schema for this explorer widget.', tags=['ui', 'schema'])
    def get_ui_schema(self) -> Dict[str, Any]:
        return {'widget': 'TreeView', 'columns': ['#0'], 'selectmode': 'browse', 'icons': self.icons}

    def _build_node(self, parent_id, node_data):
        ntype = node_data.get('type', 'unknown')
        icon = self.icons.get(ntype, self.icons['unknown'])
        text = f"{icon} {node_data.get('name', '???')}"
        item_id = self.tree.insert(parent_id, 'end', text=text, open=True)
        for child in node_data.get('children', []):
            self._build_node(item_id, child)
    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        """Returns the operational status of the service."""
        start = getattr(self, 'start_time', None)
        if start is None:
            start = time.time()
            self.start_time = start
        return {'status': 'online', 'uptime': time.time() - start}

if __name__ == '__main__':
    root = tk.Tk()
    explorer = TkinterSmartExplorerMS({'parent': root})
    explorer.pack(fill='both', expand=True)
    dummy_data = {'name': 'Project Root', 'type': 'folder', 'children': [{'name': 'src', 'type': 'folder', 'children': []}, {'name': 'README.md', 'type': 'file'}]}
    explorer.load_data(dummy_data)
    root.mainloop()

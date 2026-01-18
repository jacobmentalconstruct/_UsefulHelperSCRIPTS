"""
SERVICE_NAME: _TkinterButtonMS
ENTRY_POINT: _TkinterButtonMS.py
DEPENDENCIES: tkinter
"""
import tkinter as tk
from typing import Callable, Optional, Dict, Any
from microservice_std_lib import service_metadata

@service_metadata(
    name="StandardButton",
    version="1.0.0",
    description="Standard styled button for toolbars.",
    tags=["ui", "widget"],
    capabilities=["ui:click"]
)
class TkinterButtonMS(tk.Button):
    def __init__(self, parent, text: str, command: Callable, icon: str = None, theme: Dict = None):
        self.theme = theme or {}
        
        # Style Configuration
        bg = self.theme.get('panel_bg', '#333')
        fg = self.theme.get('foreground', '#fff')
        active_bg = self.theme.get('accent', '#007acc')
        
        super().__init__(
            parent,
            text=f" {text} ", # Padding
            command=command,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground="#fff",
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 9)
        )
"""
SERVICE_NAME: _TkinterButtonMS
ENTRY_POINT: _TkinterButtonMS.py
DEPENDENCIES: tkinter, Pillow
"""
import tkinter as tk
from PIL import Image, ImageTk
from typing import Callable, Optional, Dict, Any
from microservice_std_lib import service_metadata

@service_metadata(
    name="StandardButton",
    version="1.1.0",
    description="Standard styled button for toolbars with Icon support.",
    tags=["ui", "widget"],
    capabilities=["ui:click"]
)
class TkinterButtonMS(tk.Button):
    def __init__(self, parent, text: str, command: Callable, icon_path: str = None, theme: Dict = None):
        self.theme = theme or {}
        
        # Style
        bg = self.theme.get('panel_bg', '#333')
        fg = self.theme.get('foreground', '#fff')
        active_bg = self.theme.get('accent', '#007acc')
        
        # Icon Processing
        self.img = None
        if icon_path:
            try:
                pil_img = Image.open(icon_path).resize((16, 16), Image.Resampling.LANCZOS)
                self.img = ImageTk.PhotoImage(pil_img)
            except Exception:
                print(f"Warning: Could not load icon {icon_path}")

        super().__init__(
            parent,
            text=f"  {text}  ", 
            image=self.img if self.img else None,
            compound="left", # Icon left of text
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
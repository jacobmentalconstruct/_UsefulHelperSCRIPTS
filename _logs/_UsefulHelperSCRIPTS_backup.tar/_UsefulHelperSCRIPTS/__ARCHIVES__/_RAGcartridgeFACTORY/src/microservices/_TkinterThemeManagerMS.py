"""
SERVICE_NAME: _TkinterThemeManagerMS
ENTRY_POINT: _TkinterThemeManagerMS.py
DEPENDENCIES: tkinter, ctypes
"""

import tkinter as tk
from tkinter import ttk
import ctypes
import platform
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
    name="TkinterThemeManagerMS",
    version="1.1.0",
    description="Applies a forced Dark Theme to Tkinter widgets and the Windows Title Bar.",
    tags=["ui", "theme", "style"],
    capabilities=["theme:dark"],
    side_effects=["ui:update"]
)
class TkinterThemeManagerMS:
    def __init__(self):
        # VS Code-like Palette
        self.colors = {
            "bg_dark": "#1e1e1e",      # Main Background
            "bg_lighter": "#252526",   # Panels / Trees
            "fg": "#cccccc",           # Text
            "accent": "#007acc",       # Focus / Selection
            "select_bg": "#094771",    # Selected Tree Item
            "select_fg": "#ffffff",
            "border": "#3e3e42",
            
            # [FIX] Added keys expected by AppShell
            "panel_bg": "#252526",
            "foreground": "#cccccc"
        }

    # [FIX] This is the missing method that caused the crash
    @service_endpoint(
        inputs={},
        outputs={"theme": "Dict"},
        description="Returns the current color palette.",
        tags=["ui", "config"]
    )
    def get_theme(self):
        return self.colors

    @service_endpoint(
        inputs={"root": "tk.Tk"},
        outputs={},
        description="Applies the dark theme styles to the provided root window.",
        tags=["ui", "config"]
    )
    def apply_theme(self, root):
        style = ttk.Style(root)
        
        # 1. Force Windows Title Bar to Dark Mode (The "Magic" Hack)
        self._set_windows_titlebar_dark(root)

        # 2. Configure Root Background
        root.configure(bg=self.colors["bg_dark"])
        
        # 3. Switch to 'clam' engine (It listens to color configs better than 'vista')
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass # Fallback if clam isn't available

        # 4. Define Global Defaults
        style.configure(".", 
            background=self.colors["bg_dark"], 
            foreground=self.colors["fg"],
            fieldbackground=self.colors["bg_lighter"],
            troughcolor=self.colors["bg_dark"],
            borderwidth=0,
            darkcolor=self.colors["bg_dark"], 
            lightcolor=self.colors["bg_dark"]
        )
        
        # 5. Widget Specifics
        
        # Frames & Labels
        style.configure("TFrame", background=self.colors["bg_dark"])
        style.configure("TLabel", background=self.colors["bg_dark"], foreground=self.colors["fg"])
        style.configure("TLabelframe", background=self.colors["bg_dark"], bordercolor=self.colors["border"])
        style.configure("TLabelframe.Label", background=self.colors["bg_dark"], foreground=self.colors["fg"])

        # Buttons (Flat & Dark)
        style.configure("TButton", 
            background=self.colors["bg_lighter"], 
            foreground=self.colors["fg"],
            borderwidth=1,
            bordercolor=self.colors["border"],
            focusthickness=3,
            focuscolor=self.colors["accent"]
        )
        style.map("TButton",
            background=[("active", self.colors["accent"]), ("pressed", self.colors["select_bg"])],
            foreground=[("active", "white")]
        )

        # Treeview (Explorer & Logs) - NO WHITE BACKGROUNDS
        style.configure("Treeview", 
            background=self.colors["bg_lighter"],
            fieldbackground=self.colors["bg_lighter"],
            foreground=self.colors["fg"],
            borderwidth=0
        )
        style.map("Treeview", 
            background=[("selected", self.colors["select_bg"])],
            foreground=[("selected", self.colors["select_fg"])]
        )
        
        # Tree Headers
        style.configure("Treeview.Heading",
            background=self.colors["bg_dark"],
            foreground=self.colors["fg"],
            relief="flat",
            borderwidth=0
        )
        
        # Scrollbars (The hardest part to darken)
        style.configure("Vertical.TScrollbar",
            gripcount=0,
            background=self.colors["bg_lighter"],
            darkcolor=self.colors["bg_dark"],
            lightcolor=self.colors["bg_dark"],
            troughcolor=self.colors["bg_dark"],
            bordercolor=self.colors["bg_dark"],
            arrowcolor=self.colors["fg"]
        )
        style.map("Vertical.TScrollbar",
            background=[("active", self.colors["accent"])]
        )

    def _set_windows_titlebar_dark(self, root):
        """
        Uses ctypes to flip the undocumented Windows DWM flag for Dark Mode.
        """
        try:
            if platform.system() == "Windows":
                root.update() # Ensure handle exists
                hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
                # DWMWA_USE_IMMERSIVE_DARK_MODE = 20
                value = ctypes.c_int(2) 
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(value), 4)
        except Exception:
            pass # Fail silently on Linux/Mac or older Windows
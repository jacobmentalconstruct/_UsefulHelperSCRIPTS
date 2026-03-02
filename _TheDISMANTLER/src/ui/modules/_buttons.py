"""
Reusable button widgets for the Dismantler UI.
Stateless components that apply the Deep Space theme automatically.
"""
import tkinter as tk
from theme import THEME


class AccentButton(tk.Button):
    """Primary action button with accent-colored background."""

    def __init__(self, parent, text="", command=None, **kwargs):
        defaults = {
            "bg": THEME["accent"],
            "fg": "#ffffff",
            "activebackground": "#6a58e0",
            "activeforeground": "#ffffff",
            "font": THEME["font_interface_bold"],
            "relief": "flat",
            "cursor": "hand2",
            "padx": 12,
            "pady": 4,
        }
        defaults.update(kwargs)
        super().__init__(parent, text=text, command=command, **defaults)


class ToolbarButton(tk.Button):
    """Flat button for toolbar strips and control bars."""

    def __init__(self, parent, text="", command=None, **kwargs):
        defaults = {
            "bg": THEME["bg2"],
            "fg": THEME["fg"],
            "activebackground": THEME["accent"],
            "activeforeground": "#ffffff",
            "font": THEME["font_interface_small"],
            "relief": "flat",
            "cursor": "hand2",
            "padx": 8,
            "pady": 2,
        }
        defaults.update(kwargs)
        super().__init__(parent, text=text, command=command, **defaults)


class IconButton(tk.Button):
    """Minimal square button for icon-style actions (close, minimize, etc.)."""

    def __init__(self, parent, text="X", command=None, **kwargs):
        defaults = {
            "bg": THEME["bg"],
            "fg": THEME["fg_dim"],
            "activebackground": THEME["error"],
            "activeforeground": "#ffffff",
            "font": ("Consolas", 9),
            "relief": "flat",
            "width": 2,
            "cursor": "hand2",
            "bd": 0,
        }
        defaults.update(kwargs)
        super().__init__(parent, text=text, command=command, **defaults)

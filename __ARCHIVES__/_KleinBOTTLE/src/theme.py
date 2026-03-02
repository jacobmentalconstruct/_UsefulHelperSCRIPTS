"""Theme system for KleinBOTTLE world-builder.

Provides the VSCode-dark-inspired color palette and ttk style configuration.
"""

from __future__ import annotations
from typing import Optional
from tkinter import ttk

DEFAULT_THEME = {
    "background": "#1e1e1e",
    "foreground": "#d4d4d4",
    "panel_bg": "#252526",
    "border": "#3c3c3c",
    "accent": "#007acc",
    "error": "#f48771",
    "success": "#89d185",
    "font_main": ("Segoe UI", 10),
    "font_main_bold": ("Segoe UI", 10, "bold"),
    "font_title": ("Segoe UI", 16, "bold"),
    "font_huge": ("Segoe UI", 26, "bold"),
    "font_mono": ("Consolas", 10),
    "font_mono_small": ("Consolas", 9),
}


class Theme:
    """Small inline theme manager compatible with the microservice palette."""

    def __init__(self, overrides: Optional[dict] = None):
        self.t = dict(DEFAULT_THEME)
        if overrides:
            self.t.update(overrides)

    def __getitem__(self, k: str):
        return self.t[k]

    def get(self, k: str, default=None):
        return self.t.get(k, default)


def apply_ttk_styles(style: ttk.Style, theme: Theme):
    """Configure all ttk widget styles from a Theme instance."""
    try:
        style.theme_use("clam")
    except Exception:
        pass

    bg = theme["background"]
    fg = theme["foreground"]
    panel = theme["panel_bg"]
    border = theme["border"]
    accent = theme["accent"]

    style.configure("TFrame", background=bg)
    style.configure("Panel.TFrame", background=panel)
    style.configure("TLabel", background=bg, foreground=fg, font=theme["font_main"])
    style.configure("Title.TLabel", background=bg, foreground=fg, font=theme["font_title"])
    style.configure("Huge.TLabel", background=bg, foreground=accent, font=theme["font_huge"])
    style.configure("Mono.TLabel", background=bg, foreground=fg, font=theme["font_mono"])
    style.configure("Small.Mono.TLabel", background=bg, foreground=fg, font=theme["font_mono_small"])

    style.configure("TButton", background=panel, foreground=fg, bordercolor=border,
                     focusthickness=2, focuscolor=accent, padding=(10, 6))
    style.map("TButton", background=[("active", "#2d2d2d")], foreground=[("disabled", "#777")])

    style.configure("Accent.TButton", background=accent, foreground="white", padding=(10, 6))
    style.map("Accent.TButton", background=[("active", "#1290df")])

    style.configure("Danger.TButton", background=theme["error"], foreground="black")

    style.configure("TEntry", fieldbackground="#111", foreground=fg, insertcolor=fg, bordercolor=border)
    style.configure("TCombobox", fieldbackground="#111", foreground=fg, arrowcolor=fg, bordercolor=border)

    style.configure("TLabelframe", background=panel, foreground=fg,
                     bordercolor=border, lightcolor=border, darkcolor=border)
    style.configure("TLabelframe.Label", background=panel, foreground=fg, font=theme["font_main_bold"])

    style.configure("Treeview", background="#111", fieldbackground="#111",
                     foreground=fg, bordercolor=border, rowheight=22)
    style.map("Treeview", background=[("selected", accent)], foreground=[("selected", "white")])

    # Notebook tab styles
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=panel, foreground=fg, padding=[10, 4])
    style.map("TNotebook.Tab", background=[("selected", accent)], foreground=[("selected", "white")])

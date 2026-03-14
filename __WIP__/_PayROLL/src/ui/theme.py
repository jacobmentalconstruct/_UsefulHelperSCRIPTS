from __future__ import annotations

import tkinter as tk
from tkinter import ttk


THEME = {
    "bg": "#15191f",
    "panel": "#1d242d",
    "surface": "#232d38",
    "surface_alt": "#2a3642",
    "border": "#354453",
    "text": "#e6edf3",
    "text_dim": "#9ca8b5",
    "accent": "#5ec4a8",
    "accent_alt": "#d68f4d",
    "danger": "#c65a5a",
    "entry": "#0f141a",
}


def apply_dark_theme(root: tk.Tk) -> dict[str, str]:
    style = ttk.Style(root)
    style.theme_use("clam")
    root.configure(bg=THEME["bg"])
    style.configure("App.TFrame", background=THEME["bg"])
    style.configure("Panel.TFrame", background=THEME["panel"])
    style.configure("Surface.TFrame", background=THEME["surface"])
    style.configure("Card.TLabelframe", background=THEME["surface"], foreground=THEME["text"])
    style.configure("Card.TLabelframe.Label", background=THEME["surface"], foreground=THEME["text"])
    style.configure("App.TLabel", background=THEME["bg"], foreground=THEME["text"])
    style.configure("Panel.TLabel", background=THEME["panel"], foreground=THEME["text"])
    style.configure("Surface.TLabel", background=THEME["surface"], foreground=THEME["text"])
    style.configure("Muted.TLabel", background=THEME["bg"], foreground=THEME["text_dim"])
    style.configure("Accent.TLabel", background=THEME["bg"], foreground=THEME["accent"])
    style.configure("App.TButton", background=THEME["surface_alt"], foreground=THEME["text"], bordercolor=THEME["border"])
    style.map("App.TButton", background=[("active", THEME["accent"])], foreground=[("active", THEME["bg"])])
    style.configure("Nav.TButton", background=THEME["panel"], foreground=THEME["text"], anchor="w", padding=8)
    style.map("Nav.TButton", background=[("active", THEME["surface_alt"])])
    style.configure("Primary.TButton", background=THEME["accent"], foreground=THEME["bg"], padding=8, bordercolor=THEME["accent"])
    style.map("Primary.TButton", background=[("active", "#7ad8bc")])
    style.configure("Danger.TButton", background=THEME["danger"], foreground=THEME["text"])
    style.configure(
        "App.Treeview",
        background=THEME["entry"],
        fieldbackground=THEME["entry"],
        foreground=THEME["text"],
        bordercolor=THEME["border"],
    )
    style.configure(
        "App.Treeview.Heading",
        background=THEME["surface_alt"],
        foreground=THEME["text"],
        bordercolor=THEME["border"],
    )
    style.map("App.Treeview", background=[("selected", THEME["accent"])], foreground=[("selected", THEME["bg"])])
    style.configure("TEntry", fieldbackground=THEME["entry"], foreground=THEME["text"], insertcolor=THEME["text"])
    style.configure("TCombobox", fieldbackground=THEME["entry"], foreground=THEME["text"])
    style.configure("TCheckbutton", background=THEME["surface"], foreground=THEME["text"])
    root.option_add("*TCombobox*Listbox*Background", THEME["entry"])
    root.option_add("*TCombobox*Listbox*Foreground", THEME["text"])
    return dict(THEME)

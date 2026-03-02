"""KleinBOTTLE World-Builder - Application Launcher

Dumb entry point: wires up backend + UI and runs the main loop.
"""

from __future__ import annotations

import os
import sys
import tkinter as tk
from tkinter import ttk

# Ensure src/ is on the path so modules resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from theme import Theme, apply_ttk_styles
from backend import Backend
from ui import WorldBuilderUI


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))

    root = tk.Tk()
    root.title("KleinBOTTLE World-Builder")
    root.geometry("1400x900")

    theme = Theme()
    root.configure(bg=theme["background"])
    apply_ttk_styles(ttk.Style(root), theme)

    backend = Backend(root, base_dir)
    ui = WorldBuilderUI(root, backend, theme)

    root.mainloop()


if __name__ == "__main__":
    main()

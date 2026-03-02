"""
Reusable panel container for the Dismantler UI.
A simple themed Frame with optional label header.
"""
import tkinter as tk
from theme import THEME


class Panel(tk.Frame):
    """
    Themed container frame.
    Optionally renders a header label at the top.
    """

    def __init__(self, parent, title=None, bg=None, **kwargs):
        bg = bg or THEME["bg2"]
        super().__init__(parent, bg=bg, **kwargs)

        self.inner = self  # alias for direct child packing

        if title:
            header = tk.Label(
                self,
                text=title,
                bg=bg,
                fg=THEME["accent"],
                font=THEME["font_interface_bold"],
                anchor="w",
            )
            header.pack(fill="x", padx=6, pady=(6, 2))

            self.inner = tk.Frame(self, bg=bg)
            self.inner.pack(fill="both", expand=True, padx=4, pady=(0, 4))

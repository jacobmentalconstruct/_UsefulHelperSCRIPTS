# src/ui/scrollable.py
import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    """
    A classic scrollable Canvas+Frame combo.

    - The Canvas scrolls vertically.
    - 'content' is the inner frame where we grid dynamic form rows.
    """

    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.canvas = tk.Canvas(self, highlightthickness=0)
        self.v_scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)

        self.canvas.configure(yscrollcommand=self.v_scroll.set)

        self.v_scroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.content = ttk.Frame(self.canvas)
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")

        # Keep scroll region correct
        self.content.bind("<Configure>", self._on_content_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse wheel support (Windows/macOS/Linux variants)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")       # Windows/macOS
        self.canvas.bind_all("<Button-4>", self._on_mousewheel_linux, add="+")   # Linux up
        self.canvas.bind_all("<Button-5>", self._on_mousewheel_linux, add="+")   # Linux down

    def _on_content_configure(self, _event):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        # Resize the inner frame width to match canvas width
        self.canvas.itemconfigure(self.window_id, width=event.width)

    def _on_mousewheel(self, event):
        # event.delta is usually 120 increments on Windows
        if event.delta:
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(3, "units")

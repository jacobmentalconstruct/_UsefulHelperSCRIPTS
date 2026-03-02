"""
Reusable dropdown / combobox widget for the Dismantler UI.
Wraps ttk.Combobox with consistent Deep Space styling.
"""
import tkinter as tk
from tkinter import ttk
from theme import THEME


class StyledDropdown(ttk.Combobox):
    """
    A themed read-only dropdown.
    Applies Deep Space palette via a local ttk.Style so it doesn't
    bleed into other comboboxes.
    """

    def __init__(self, parent, values=None, on_change=None, width=20, **kwargs):
        self._on_change = on_change

        super().__init__(
            parent,
            values=values or [],
            state="readonly",
            width=width,
            font=THEME["font_interface"],
            **kwargs,
        )

        if values:
            self.current(0)

        self.bind("<<ComboboxSelected>>", self._selection_changed)

    def _selection_changed(self, _event):
        if self._on_change:
            self._on_change(self.get())

    def set_values(self, values):
        """Replace the option list and select the first item."""
        self["values"] = values
        if values:
            self.current(0)

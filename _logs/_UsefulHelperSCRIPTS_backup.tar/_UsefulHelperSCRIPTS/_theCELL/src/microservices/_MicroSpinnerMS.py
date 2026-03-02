import tkinter as tk
import math
import threading

class MicroSpinner:
    """
    A standalone ASCII spinner for Tkinter Text widgets.
    """
    def __init__(self, text_widget, center_row=5, center_col=20, radius=3, speed=0.2):
        self.txt = text_widget
        self.center_row = center_row
        self.center_col = center_col
        self.radius = radius
        self.speed = speed
        
        self.angle = 0.0
        self.is_running = False
        self.trail = []  # Stores (index, symbol)
        self.symbols = ["@", "#", "*", "+", ".", " "] # Fade sequence
        
        # Initialize a small blank area in the text box if empty
        if self.txt.get("1.0", tk.END).strip() == "":
            blank_block = (" " * 80 + "\n") * 20
            self.txt.insert("1.0", blank_block)

    def _get_pos(self, angle_offset=0):
        """Calculates a specific coordinate based on angle."""
        # 2.2 factor compensates for rectangular font pixels
        x = int(self.center_col + (self.radius * 2.2) * math.cos(self.angle - angle_offset))
        y = int(self.center_row + self.radius * math.sin(self.angle - angle_offset))
        return f"{y}.{x}"

    def update(self):
        if not self.is_running:
            # Clean up the trail when stopping
            for pos in self.trail:
                self._write_at(pos, " ")
            self.trail = []
            return

        # 1. Calculate current head position
        head_pos = self._get_pos(0)
        
        # 2. Add new head to trail, remove oldest if too long
        self.trail.insert(0, head_pos)
        if len(self.trail) > len(self.symbols):
            old_pos = self.trail.pop()
            self._write_at(old_pos, " ")

        # 3. Draw the trail with fading symbols
        for i, pos in enumerate(self.trail):
            symbol = self.symbols[i] if i < len(self.symbols) else " "
            self._write_at(pos, symbol)

        self.angle += self.speed
        self.txt.after(50, self.update)

    def _write_at(self, index, char):
        """Surgically replaces a single character at a Tkinter index."""
        try:
            self.txt.delete(index)
            self.txt.insert(index, char)
        except tk.TclError:
            pass # Handle case where text widget might be cleared externally

    def start(self):
        if not self.is_running:
            self.is_running = True
            self.update()

    def stop(self):
        self.is_running = False
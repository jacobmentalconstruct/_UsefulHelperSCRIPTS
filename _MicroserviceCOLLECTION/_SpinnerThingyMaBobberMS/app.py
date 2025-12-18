import tkinter as tk
import math
import colorsys
import time
from typing import Optional, Dict, Any
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
name="SpinnerTHINGYMABOBBER",
version="1.0.0",
description="Interactive visual spinner widget for OBS/UI overlays.",
tags=["ui", "widget", "visuals"],
capabilities=["ui:gui"]
)
class SpinnerTHINGYMABOBBERMS:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
self.config = config or {}
self.root = tk.Tk()
self.root.title("OBS Interactive Spinner")
        self.root.configure(bg="black")
        
        # Default size
        self.root.geometry("600x600")
        
        # Canvas for drawing
        self.canvas = tk.Canvas(
            self.root, 
            bg="black", 
            highlightthickness=0
        )
        self.canvas.pack(fill="both", expand=True)

        # --- STATE VARIABLES ---
        self.angle_1 = 0
        self.angle_2 = 0
        self.angle_3 = 0
        self.hue = 0
        
        # Text Input State
        self.user_text = "PROCESSING"
        self.cursor_visible = True
        self.last_cursor_toggle = time.time()
        
        # Bind keyboard events to the window
        self.root.bind("<Key>", self.handle_keypress)
        
        # Start animation
        self.animate()

        @service_endpoint(
@service_endpoint(
    inputs={},
    outputs={},
    description="Launches the GUI main loop.",
    tags=["ui", "execution"],
    mode="sync",
    side_effects=["ui:block"]
)
def launch(self):
    self.root.mainloop()

def handle_keypress(self, event):
    # Handle Backspace
    if event.keysym == "BackSpace":
        self.user_text = self.user_text[:-1]
    # Handle Escape (Reset to default)
    elif event.keysym == "Escape":
        self.user_text = "PROCESSING"
    # Ignore special keys (Shift, Ctrl, Alt, F-keys, etc.)
    elif len(event.char) == 1 and ord(event.char) >= 32:
        # Limit length to prevent chaos (optional, but 20 is a safe max)
        if len(self.user_text) < 25: 
            self.user_text += event.char.upper()

def get_neon_color(self, offset=0):
    h = (self.hue + offset) % 1.0
    r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
    return f'#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}'

def draw_arc(self, cx, cy, radius, width, start, extent, color):
    x0 = cx - radius
    y0 = cy - radius
    x1 = cx + radius
    y1 = cy + radius
    
    self.canvas.create_arc(
        x0, y0, x1, y1,
        start=start, extent=extent,
        outline=color, width=width, style="arc"
    )
def animate(self):
    self.canvas.delete("all")
    
    # Window Dimensions
    w = self.canvas.winfo_width()
    h = self.canvas.winfo_height()
    
    if w < 10 or h < 10:
        self.root.after(50, self.animate)
        return

    cx, cy = w / 2, h / 2
    base_size = min(w, h) / 2
    
    # Update Hue
    self.hue += 0.005
    if self.hue > 1: self.hue = 0
    c1 = self.get_neon_color(0.0)
    c2 = self.get_neon_color(0.3)
    c3 = self.get_neon_color(0.6)

    # --- RINGS ---
        
    # Ring 1
    r1 = base_size * 0.85
    self.angle_1 -= 3
    for i in range(3):
        self.draw_arc(cx, cy, r1, base_size*0.08, self.angle_1 + (i*120), 80, c1)

    # Ring 2
    r2 = base_size * 0.65
    self.angle_2 += 5
    self.draw_arc(cx, cy, r2, base_size*0.05, self.angle_2, 160, c2)
    self.draw_arc(cx, cy, r2, base_size*0.05, self.angle_2 + 180, 160, c2)

    # Ring 3
    r3 = base_size * 0.45
    self.angle_3 -= 8
    self.draw_arc(cx, cy, r3, base_size*0.04, self.angle_3, 300, c3)
        # --- TEXT LOGIC ---
        
        # Toggle cursor every 0.5 seconds
        if time.time() - self.last_cursor_toggle > 0.5:
            self.cursor_visible = not self.cursor_visible
            self.last_cursor_toggle = time.time()
            
        display_text = self.user_text + ("_" if self.cursor_visible else " ")

        # Dynamic Font Scaling
        # We start with a base size (0.15 of window).
        # If text is long (> 8 chars), we shrink it proportionally so it fits.
        text_len = max(len(self.user_text), 1)
        scaling_factor = 1.0
        if text_len > 8:
            scaling_factor = 8 / text_len
            
        font_size = int(base_size * 0.15 * scaling_factor)
        # Ensure font doesn't vanish
        font_size = max(font_size, 10) 

        self.canvas.create_text(
            cx, cy, 
            text=display_text, 
            fill="white", 
            font=("Courier", font_size, "bold")
        )

        self.root.after(30, self.animate)

if __name__ == "__main__":
svc = SpinnerTHINGYMABOBBERMS()
svc.launch()

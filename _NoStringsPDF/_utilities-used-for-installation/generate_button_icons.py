"""
SCRIPT: generate_assets.py
DESCRIPTION: Procedurally generates a UI icon pack for NoStringsPDF.
"""
import os
from PIL import Image, ImageDraw

# [FIX] Force script to run from Project Root
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def draw_icon(name, draw_func):
    size = (48, 48) # Generates @2x for crispness, Button class will resize
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    # Style: White lines, 3px thick
    fg = "#ffffff"
    w = 4
    
    draw_func(draw, size, fg, w)
    
    # Save
    if not os.path.exists("assets"):
        os.makedirs("assets")
    img.save(f"assets/{name}.png", "PNG")
    print(f"Generated assets/{name}.png")

# --- DRAWING FUNCTIONS ---

def icon_open(d, s, c, w):
    # Folder shape
    d.polygon([(4, 12), (16, 12), (20, 16), (44, 16), (44, 40), (4, 40)], outline=c, width=w)
    d.line([(4, 20), (44, 20)], fill=c, width=w)

def icon_insert(d, s, c, w):
    # Doc with Plus
    d.rectangle([10, 6, 38, 42], outline=c, width=w)
    d.line([(24, 18), (24, 30)], fill=c, width=w) # Vertical
    d.line([(18, 24), (30, 24)], fill=c, width=w) # Horizontal

def icon_interleave(d, s, c, w):
    # Two stacks merging like a zipper
    d.rectangle([8, 10, 20, 22], outline=c, width=3) # Top Left
    d.rectangle([28, 26, 40, 38], outline=c, width=3) # Bot Right
    # Arrows
    d.line([(22, 16), (26, 32)], fill=c, width=2)

def icon_extract(d, s, c, w):
    # Doc with arrow coming out
    d.rectangle([8, 8, 32, 40], outline=c, width=3)
    d.line([(32, 24), (44, 24)], fill=c, width=3) # Arrow shaft
    d.polygon([(40, 20), (44, 24), (40, 28)], fill=c) # Arrow head

def icon_split(d, s, c, w):
    # Scissors / Cut line
    d.line([(24, 4), (24, 44)], fill=c, width=3) # Vertical dash
    # Arrows parting
    d.polygon([(10, 20), (4, 24), (10, 28)], fill=c) # Left arrow
    d.polygon([(38, 20), (44, 24), (38, 28)], fill=c) # Right arrow

def icon_save(d, s, c, w):
    # Floppy disk (Classic)
    d.rectangle([8, 8, 40, 40], outline=c, width=w) # Main body
    d.rectangle([14, 8, 34, 18], fill=c) # Metal shutter (Top)
    # FIX: Coordinates were flipped [12, 40, 36, 28] -> [12, 28, 36, 40]
    # This draws the label area at the bottom properly.
    d.rectangle([12, 28, 36, 40], outline=c, width=2) 

def icon_rot_l(d, s, c, w):
    # Counter-Clockwise Arrow
    d.arc([8, 8, 40, 40], 135, 405, fill=c, width=w)
    d.polygon([(8, 24), (2, 20), (14, 20)], fill=c) # Arrowhead left

def icon_rot_r(d, s, c, w):
    # Clockwise Arrow
    d.arc([8, 8, 40, 40], 135, 405, fill=c, width=w)
    d.polygon([(40, 24), (46, 20), (34, 20)], fill=c) # Arrowhead right

def icon_zoom_in(d, s, c, w):
    d.ellipse([8, 8, 32, 32], outline=c, width=w)
    d.line([(28, 28), (40, 40)], fill=c, width=w) # Handle
    d.line([(20, 14), (20, 26)], fill=c, width=3) # V
    d.line([(14, 20), (26, 20)], fill=c, width=3) # H

def icon_zoom_out(d, s, c, w):
    d.ellipse([8, 8, 32, 32], outline=c, width=w)
    d.line([(28, 28), (40, 40)], fill=c, width=w) # Handle
    d.line([(14, 20), (26, 20)], fill=c, width=3) # H

def icon_prev(d, s, c, w):
    d.polygon([(30, 10), (14, 24), (30, 38)], fill=c)

def icon_next(d, s, c, w):
    d.polygon([(18, 10), (34, 24), (18, 38)], fill=c)

# --- RUN ---
if __name__ == "__main__":
    mapping = {
        "open": icon_open,
        "insert": icon_insert,
        "interleave": icon_interleave,
        "extract": icon_extract,
        "split": icon_split,
        "save": icon_save,
        "rot_l": icon_rot_l,
        "rot_r": icon_rot_r,
        "zoom_in": icon_zoom_in,
        "zoom_out": icon_zoom_out,
        "prev": icon_prev,
        "next": icon_next
    }
    
    for name, func in mapping.items():
        try:
            draw_icon(name, func)
        except Exception as e:
            print(f"Error generating {name}: {e}")
        
    print("[SUCCESS] Icon pack generated in /assets")
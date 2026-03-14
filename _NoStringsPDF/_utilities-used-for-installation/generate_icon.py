"""
SCRIPT: generate_icon.py
DESCRIPTION: Procedurally generates a modern 'NoStringsPDF' app icon.
"""
from PIL import Image, ImageDraw, ImageFont
import os

# [FIX] Force script to run from Project Root
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def create_icon():
    size = (256, 256)
    # Transparent background
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Colors
    dark_bg = "#252526"
    accent = "#007acc"  # VS Code Blue/Cyan
    paper = "#e0e0e0"
    
    # 1. Draw Background (Rounded Square)
    # We fake rounded corners by drawing circles + rectangles
    r = 40 # Radius
    margin = 10
    box = [margin, margin, size[0]-margin, size[1]-margin]
    
    # Main Body
    draw.rounded_rectangle(box, radius=r, fill=dark_bg, outline="#333", width=4)

    # 2. Draw "Document" Shape in Center
    doc_w, doc_h = 120, 160
    doc_x = (size[0] - doc_w) // 2
    doc_y = (size[1] - doc_h) // 2
    
    # Paper Body
    draw.rectangle([doc_x, doc_y, doc_x + doc_w, doc_y + doc_h], fill=paper)
    
    # 3. Draw "Redacted/Text" Lines (Industrial feel)
    line_h = 12
    gap = 20
    start_y = doc_y + 30
    for i in range(4):
        y = start_y + (i * gap)
        # Random-ish widths
        w = doc_w - 40 if i % 2 == 0 else doc_w - 60
        draw.rectangle([doc_x + 20, y, doc_x + 20 + w, y + line_h], fill="#555")

    # 4. Draw "No Strings" Accent (Cyan Slash/Corner)
    # A triangular fold or slash at the bottom right of the document
    draw.polygon([
        (doc_x + doc_w, doc_y + doc_h - 40), # Top of slash
        (doc_x + doc_w, doc_y + doc_h),      # Corner
        (doc_x + doc_w - 40, doc_y + doc_h)  # Left of slash
    ], fill=accent)

    # 5. Save as ICO
    # Windows icons usually contain multiple sizes
    img.save("app.ico", format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    print("[SUCCESS] Generated app.ico in Project Root")

if __name__ == "__main__":
    create_icon()
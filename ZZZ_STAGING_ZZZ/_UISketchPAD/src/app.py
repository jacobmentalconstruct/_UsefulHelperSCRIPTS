import tkinter as tk
from tkinter import simpledialog, filedialog
from PIL import Image, ImageDraw, ImageTk
import io
import sys
import ctypes

class UISketchPad:
    def __init__(self, root):
        self.root = root
        self.root.title("_UISketchPAD")
        self.root.geometry("800x650")
        
        # --- State ---
        self.current_tool = "pen"  # pen, rect, text, eraser
        self.brush_size = 2
        self.start_x = None
        self.start_y = None
        self.current_shape = None
        self.last_x = 0
        self.last_y = 0

        # --- Colors ---
        self.bg_color = "#FFFFFF"
        self.draw_color = "#000000"
        self.ui_bg = "#E0E0E0"

        # --- Canvas Setup ---
        # 1. The Tkinter Canvas (what you see)
        self.canvas = tk.Canvas(root, bg=self.bg_color, cursor="cross")
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # 2. The Pillow Image (what gets copied/saved)
        self.width = 1200 # Fixed workspace size
        self.height = 1200 
        self.image = Image.new("RGB", (self.width, self.height), self.bg_color)
        self.draw = ImageDraw.Draw(self.image)

        # --- Toolbar ---
        self.toolbar = tk.Frame(root, bg=self.ui_bg, bd=2, relief=tk.RAISED)
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)

        self.btn_pen = self.create_tool_btn("Pen", "pen")
        self.btn_rect = self.create_tool_btn("Box (UI Element)", "rect")
        self.btn_text = self.create_tool_btn("Text", "text")
        self.btn_eraser = self.create_tool_btn("Eraser", "eraser")
        
        tk.Frame(self.toolbar, width=20, bg=self.ui_bg).pack(side=tk.LEFT) # Spacer

        self.btn_clear = tk.Button(self.toolbar, text="Clear All", command=self.clear_canvas, bg="#FFCCCC")
        self.btn_clear.pack(side=tk.LEFT, padx=5, pady=5)

        tk.Frame(self.toolbar, width=20, bg=self.ui_bg).pack(side=tk.LEFT) # Spacer

        self.btn_copy = tk.Button(self.toolbar, text="COPY TO CLIPBOARD", command=self.copy_to_clipboard, bg="#CCFFCC", font=("Arial", 10, "bold"))
        self.btn_copy.pack(side=tk.RIGHT, padx=20, pady=5)

        # --- Bindings ---
        self.canvas.bind("<Button-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)

        self.update_tool_buttons()

    def create_tool_btn(self, text, mode):
        btn = tk.Button(self.toolbar, text=text, command=lambda: self.set_tool(mode))
        btn.pack(side=tk.LEFT, padx=2, pady=5)
        return btn

    def set_tool(self, mode):
        self.current_tool = mode
        self.update_tool_buttons()

    def update_tool_buttons(self):
        btns = {"pen": self.btn_pen, "rect": self.btn_rect, "text": self.btn_text, "eraser": self.btn_eraser}
        for mode, btn in btns.items():
            if mode == self.current_tool:
                btn.config(relief=tk.SUNKEN, bg="#DDDDDD")
            else:
                btn.config(relief=tk.RAISED, bg="#F0F0F0")

    # --- Drawing Logic ---

    def on_click(self, event):
        self.start_x = event.x
        self.start_y = event.y
        self.last_x = event.x
        self.last_y = event.y

        if self.current_tool == "text":
            text_content = simpledialog.askstring("Input", "Enter UI Label:")
            if text_content:
                # Draw on Canvas
                self.canvas.create_text(event.x, event.y, text=text_content, fill="black", anchor=tk.NW, font=("Arial", 12))
                # Draw on Pillow
                self.draw.text((event.x, event.y), text_content, fill="black")

    def on_drag(self, event):
        if self.current_tool == "pen":
            # Draw line on Canvas
            self.canvas.create_line(self.last_x, self.last_y, event.x, event.y, fill="black", width=2, capstyle=tk.ROUND, smooth=True)
            # Draw line on Pillow
            self.draw.line([self.last_x, self.last_y, event.x, event.y], fill="black", width=2)
            self.last_x = event.x
            self.last_y = event.y

        elif self.current_tool == "eraser":
            r = 10
            self.canvas.create_oval(event.x-r, event.y-r, event.x+r, event.y+r, fill="white", outline="white")
            self.draw.ellipse([event.x-r, event.y-r, event.x+r, event.y+r], fill="white", outline="white")

        elif self.current_tool == "rect":
            # Preview the rectangle on canvas only (delete old one, draw new one)
            if self.current_shape:
                self.canvas.delete(self.current_shape)
            self.current_shape = self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y, outline="black", width=2)

    def on_release(self, event):
        if self.current_tool == "rect":
            if self.current_shape:
                self.canvas.delete(self.current_shape)
                self.current_shape = None
            
            # Finalize on Canvas
            self.canvas.create_rectangle(self.start_x, self.start_y, event.x, event.y, outline="black", width=2)
            # Finalize on Pillow
            self.draw.rectangle([self.start_x, self.start_y, event.x, event.y], outline="black", width=2)

    def clear_canvas(self):
        self.canvas.delete("all")
        self.image.paste(self.bg_color, [0, 0, self.width, self.height])

    # --- Clipboard Magic ---
    
    def copy_to_clipboard(self):
        """
        Saves the current drawing state to an in-memory BMP and pushes it 
        to the Windows Clipboard via ctypes.
        """
        # Crop image to relevant area (optional, here we take visible canvas size)
        # Or just take the whole backing store. Let's take the window size.
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        crop_img = self.image.crop((0, 0, w, h))

        output = io.BytesIO()
        crop_img.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:] # Strip BMP header for clipboard format
        output.close()

        self.send_to_clipboard(data)
        
        # Flash visual feedback
        original_bg = self.btn_copy.cget("bg")
        self.btn_copy.config(text="COPIED!", bg="gold")
        self.root.after(1000, lambda: self.btn_copy.config(text="COPY TO CLIPBOARD", bg=original_bg))

    def send_to_clipboard(self, data):
        # Windows-specific clipboard handling using ctypes
        # This avoids needing pywin32
        if sys.platform.startswith('win'):
            import ctypes
            from ctypes import wintypes
            
            CF_DIB = 8
            
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            
            user32.OpenClipboard(0)
            user32.EmptyClipboard()
            
            # Allocate global memory
            hcd = kernel32.GlobalAlloc(0x0002, len(data)) # GMEM_MOVEABLE
            
            # Lock memory and copy data
            ptr = kernel32.GlobalLock(hcd)
            ctypes.memmove(ptr, data, len(data))
            kernel32.GlobalUnlock(hcd)
            
            # Set clipboard data
            user32.SetClipboardData(CF_DIB, hcd)
            user32.CloseClipboard()
        else:
            # Fallback for Linux/Mac: Save to file
            print("Non-Windows OS detected. Saving to 'sketch_clipboard.png' instead.")
            self.image.save("sketch_clipboard.png")
            self.btn_copy.config(text="SAVED TO DISK")


if __name__ == "__main__":
    root = tk.Tk()
    app = UISketchPad(root)
    root.mainloop()
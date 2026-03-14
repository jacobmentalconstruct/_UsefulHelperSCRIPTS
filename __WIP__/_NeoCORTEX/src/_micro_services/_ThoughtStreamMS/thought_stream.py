import tkinter as tk
from tkinter import ttk
import datetime

class ThoughtStream(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.header = ttk.Label(self, text="NEURAL INSPECTOR", font=("Consolas", 10, "bold"))
        self.header.pack(fill="x", padx=5, pady=5)
        
        self.canvas = tk.Canvas(self, bg="#13131f", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#13131f")
        
        self.scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=340)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def add_thought_bubble(self, filename, chunk_id, content, vector_preview, color):
        bubble = tk.Frame(self.scrollable_frame, bg="#1a1a25", highlightbackground="#444", highlightthickness=1)
        bubble.pack(fill="x", padx=5, pady=5)
        
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        tk.Label(bubble, text=f"{filename} #{chunk_id} [{ts}]", fg="#007ACC", bg="#1a1a25", font=("Consolas", 8)).pack(anchor="w", padx=5, pady=2)
        
        snippet = content[:400] + "..." if len(content) > 400 else content
        tk.Label(bubble, text=snippet, fg="#ccc", bg="#10101a", font=("Consolas", 8), justify="left", wraplength=300).pack(fill="x", padx=5, pady=2)
        
        self._draw_sparkline(bubble, vector_preview, color)

    def _draw_sparkline(self, parent, vector, color):
        if not vector: return
        h = 30
        w = 300
        cv = tk.Canvas(parent, height=h, width=w, bg="#1a1a25", highlightthickness=0)
        cv.pack(padx=5, pady=2)
        bar_w = w / len(vector)
        for i, val in enumerate(vector):
            mag = abs(val) 
            bar_h = mag * h
            x0 = i * bar_w
            y0 = h - bar_h
            x1 = x0 + bar_w
            y1 = h
            cv.create_rectangle(x0, y0, x1, y1, fill=color, outline="")
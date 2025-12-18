import tkinter as tk
from tkinter import ttk
import datetime
from typing import Any, Dict, Optional
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
name="ThoughtStream",
version="1.0.0",
description="A UI widget for displaying a stream of AI thoughts/logs.",
tags=["ui", "stream", "logs", "widget"],
capabilities=["ui:gui"]
)
class ThoughtStreamMS(ttk.Frame):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
self.config = config or {}
parent = self.config.get("parent")
super().__init__(parent)
        
        # Header
        self.header = ttk.Label(self, text="NEURAL INSPECTOR", font=("Consolas", 10, "bold"))
        self.header.pack(fill="x", padx=5, pady=5)
        
        # The Stream Area (Canvas allows for custom drawing like sparklines)
        self.canvas = tk.Canvas(self, bg="#13131f", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = tk.Frame(self.canvas, bg="#13131f")
        
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )
        
        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw", width=340) # Fixed width like React
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    @service_endpoint(
    inputs={"filename": "str", "chunk_id": "int", "content": "str", "vector_preview": "List[float]", "color": "str"},
    outputs={},
    description="Adds a new thought bubble to the visual stream.",
    tags=["ui", "update"],
    side_effects=["ui:update"]
    )
    def add_thought_bubble(self, filename, chunk_id, content, vector_preview, color):
    """
    Mimics the 'InspectorFrame' from your React code.
    """
# Bubble Container
        bubble = tk.Frame(self.scrollable_frame, bg="#1a1a25", highlightbackground="#444", highlightthickness=1)
        bubble.pack(fill="x", padx=5, pady=5)
        
        # Header: File + Timestamp
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        header_lbl = tk.Label(bubble, text=f"{filename} #{chunk_id} [{ts}]", 
                              fg="#007ACC", bg="#1a1a25", font=("Consolas", 8))
        header_lbl.pack(anchor="w", padx=5, pady=2)
        
        # Content Snippet
        snippet = content[:400] + "..." if len(content) > 400 else content
        content_lbl = tk.Label(bubble, text=snippet, fg="#ccc", bg="#10101a", 
                               font=("Consolas", 8), justify="left", wraplength=300)
        content_lbl.pack(fill="x", padx=5, pady=2)
        
        # Vector Sparkline (The Custom Draw)
        self._draw_sparkline(bubble, vector_preview, color)

    def _draw_sparkline(self, parent, vector, color):
        """
        Recreates the 'vector_preview' visual from React using a micro-canvas.
        """
        h = 30
        w = 300
        cv = tk.Canvas(parent, height=h, width=w, bg="#1a1a25", highlightthickness=0)
        cv.pack(padx=5, pady=2)
        
        bar_w = w / len(vector) if len(vector) > 0 else 0
        
        for i, val in enumerate(vector):
            # Normalize -1..1 to 0..1 for height
            mag = abs(val) 
            bar_h = mag * h
            x0 = i * bar_w
            y0 = h - bar_h
            x1 = x0 + bar_w
            y1 = h
            
            # Draw bar
            cv.create_rectangle(x0, y0, x1, y1, fill=color, outline="")

# --- Usage Example ---
if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("400x600")
    
    stream = ThoughtStreamMS({"parent": root})
    print("Service ready:", stream)
    stream.pack(fill="both", expand=True)
    
    # Simulate an incoming "Microservice" event
    import random
    fake_vector = [random.uniform(-1, 1) for _ in range(20)]
    stream.add_thought_bubble("ExplorerView.tsx", 1, "import React from 'react'...", fake_vector, "#FF00FF")
    
    root.mainloop()

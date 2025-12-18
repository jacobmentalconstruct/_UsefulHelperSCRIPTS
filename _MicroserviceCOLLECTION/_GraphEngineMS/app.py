import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import sqlite3
import os
from typing import Any, Dict, Optional
from microservice_std_lib import service_metadata, service_endpoint

# Use relative import for sibling module
from .graph_engine import GraphRenderer
@service_metadata(
name="GraphEngine",
version="1.0.0",
description="Interactive 2D Force-Directed Graph Visualizer (Pygame + Tkinter).",
tags=["graph", "visualization", "physics", "ui"],
capabilities=["ui:gui", "compute", "db:sqlite"]
)
class GraphEngineMS(ttk.Frame):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        parent = self.config.get("parent")
        super().__init__(parent)
        self.pack(fill="both", expand=True)

        # Widget logic
        self.canvas_lbl = tk.Label(self, bg="#101018", cursor="crosshair")
        self.canvas_lbl.pack(fill="both", expand=True)

        # Engine Init
        self.engine = GraphRenderer(800, 600)
        self.photo = None  # Keep reference to avoid GC

        # Bindings
        self.canvas_lbl.bind('<Button-1>', self.on_click)
        self.canvas_lbl.bind('<ButtonRelease-1>', self.on_release)
        self.canvas_lbl.bind('<B1-Motion>', self.on_drag)
        self.canvas_lbl.bind('<Motion>', self.on_hover)

        # Zoom bindings
        self.canvas_lbl.bind('<Button-4>', lambda e: self.on_zoom(1.1))  # Linux Scroll Up
        self.canvas_lbl.bind('<Button-5>', lambda e: self.on_zoom(0.9))  # Linux Scroll Down
        self.canvas_lbl.bind('<MouseWheel>', self.on_windows_scroll)    # Windows Scroll
        self.canvas_lbl.bind('<Configure>', self.on_resize)

        # Logic State
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self.is_dragging_node = False

        # Start Loop
        self.animate()

    @service_endpoint(
    inputs={"db_path": "str"},
    outputs={},
    description="Loads graph data from SQLite and initializes the physics engine.",
    tags=["graph", "load", "db"],
    side_effects=["db:read", "ui:update"]
    )
    def load_from_db(self, db_path):
    """
    Fetches Nodes and Edges from the SQLite DB and formats them 
    for the Pygame Physics Engine.
    """
        if not os.path.exists(db_path):
            print(f"GraphView Error: DB not found at {db_path}")
            return

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # 1. Fetch Nodes
        # Schema: id, type, label, data_json
        try:
            db_nodes = cursor.execute("SELECT id, type, label FROM graph_nodes").fetchall()
            db_edges = cursor.execute("SELECT source, target FROM graph_edges").fetchall()
        except sqlite3.OperationalError:
            print("Graph tables missing. Run Ingest first.")
            conn.close()
            return

        conn.close()

        # 2. Map String IDs -> Integer Indices
        # The physics engine uses list indices (0, 1, 2) for speed.
        id_to_index = {}
        formatted_nodes = []
        
        for idx, row in enumerate(db_nodes):
            node_id, n_type, label = row
            id_to_index[node_id] = idx
            formatted_nodes.append({
                'id': node_id,
                'type': n_type,
                'label': label
            })

        # 3. Translate Edges
        formatted_links = []
        for src, tgt in db_edges:
            if src in id_to_index and tgt in id_to_index:
                u = id_to_index[src]
                v = id_to_index[tgt]
                formatted_links.append((u, v))

        # 4. Push to Engine
        print(f"Graph Loaded: {len(formatted_nodes)} Nodes, {len(formatted_links)} Edges")
        self.engine.set_data(formatted_nodes, formatted_links)

    # --- EVENT HANDLERS ---
    
    def on_resize(self, event):
        if event.width > 1 and event.height > 1:
            self.engine.resize(event.width, event.height)

    def on_click(self, event):
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y
        # Check if we clicked a node
        hit = self.engine.handle_mouse_down(event.x, event.y)
        self.is_dragging_node = hit

    def on_release(self, event):
        self.engine.handle_mouse_up()
        self.is_dragging_node = False

    def on_drag(self, event):
        if self.is_dragging_node:
            self.engine.handle_mouse_move(event.x, event.y, True)
        else:
            # Pan Camera
            dx = event.x - self.last_mouse_x
            dy = event.y - self.last_mouse_y
            self.engine.pan(dx, dy)
            
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

    def on_hover(self, event):
        # Just update hover state for aesthetics
        if not self.is_dragging_node:
            self.engine.handle_mouse_move(event.x, event.y, False)

    def on_zoom(self, amount):
        self.engine.zoom_camera(amount, 0, 0)

    def on_windows_scroll(self, event):
        # Windows typically gives 120 or -120
        if event.delta > 0:
            self.on_zoom(1.1)
        else:
            self.on_zoom(0.9)

    # --- RENDER LOOP ---

    def animate(self):
    # 1. Step Physics
    self.engine.step_physics()
        
    # 2. Render to Pygame Surface & Convert to Tkinter
    # (We assume 800x600 or current engine size)
    w, h = self.engine.width, self.engine.height
    raw_data = self.engine.get_image_bytes()
        
    image = Image.frombytes('RGB', (w, h), raw_data)
    self.photo = ImageTk.PhotoImage(image=image)
    self.canvas_lbl.configure(image=self.photo)
        
    # 3. Loop (approx 60 FPS)
    self.after(16, self.animate)


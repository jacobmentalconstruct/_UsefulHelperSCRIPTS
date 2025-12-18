"""
SERVICE_NAME: _NeuralGraphViewerMS
ENTRY_POINT: __NeuralGraphViewerMS.py
DEPENDENCIES: None
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import sqlite3
import json
import os
from __NeuralGraphEngineMS import GraphRenderer
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
    name="NeuralGraphViewerMS",
    version="1.0.0",
    description="The Lens: A Tkinter-based UI component that hosts the neural graph engine and provides search/highlighting overlays.",
    tags=["ui", "visualization", "tkinter"],
    capabilities=["graph-rendering", "search-highlighting"]
)
class NeuralGraphViewerMS(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.pack(fill="both", expand=True)
        
        # Search Overlay
        self.controls = tk.Frame(self, bg="#101018")
        self.controls.pack(fill="x", side="top", padx=5, pady=5)
        
        self.entry_search = tk.Entry(self.controls, bg="#252526", fg="white", insertbackground="white", font=("Consolas", 10))
        self.entry_search.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.entry_search.bind("<Return>", self.run_search)
        
        btn = tk.Button(self.controls, text="NEURAL TEST", command=self.run_search, bg="#007ACC", fg="white", relief="flat")
        btn.pack(side="right")

        # UI Container
        self.canvas_lbl = tk.Label(self, bg="#101018", cursor="crosshair")
        self.canvas_lbl.pack(fill="both", expand=True)
        
        # Services
        self.cartridge = None
        self.neural = None
        
        # Engine Init
        self.engine = GraphRenderer(800, 600)
        self.photo = None 
        
        # Input State
        self.last_mouse_x = 0
        self.last_mouse_y = 0
        self.is_dragging_node = False
        self.is_panning = False

        # Bindings
        self.canvas_lbl.bind('<Button-1>', self.on_click)
        self.canvas_lbl.bind('<Double-Button-1>', self.on_double_click)
        self.canvas_lbl.bind('<ButtonRelease-1>', self.on_release)
        self.canvas_lbl.bind('<B1-Motion>', self.on_drag)
        self.canvas_lbl.bind('<Motion>', self.on_hover)
        self.canvas_lbl.bind('<Button-4>', lambda e: self.on_zoom(1.1)) # Linux Scroll Up
        self.canvas_lbl.bind('<Button-5>', lambda e: self.on_zoom(0.9)) # Linux Scroll Down
        self.canvas_lbl.bind('<MouseWheel>', self.on_windows_scroll)    # Windows Scroll
        self.canvas_lbl.bind('<Configure>', self.on_resize)
        
        # Start the Heartbeat
        self.animate()

    def bind_services(self, cartridge, neural):
        self.cartridge = cartridge
        self.neural = neural

    @service_endpoint(
        inputs={"event": "any"},
        outputs={},
        description="Triggers a neural search based on the entry field and highlights resulting nodes in the viewer.",
        tags=["ui-action", "search"]
    )
    def run_search(self, event=None):
        if not self.cartridge or not self.neural:
            return
            
        query = self.entry_search.get().strip()
        if not query: return
        
        # 1. Embed
        vec = self.neural.get_embedding(query)
        if not vec: return
        
        # 2. Search
        results = self.cartridge.search_embeddings(vec, limit=5)
        
        # 3. Resolve IDs for Graph
        # Graph Node ID format: "{vfs_path}::{chunk_name}"
        ids = set()
        for r in results:
            if 'vfs_path' in r and 'name' in r:
                ids.add(f"{r['vfs_path']}::{r['name']}")
                
        # 4. Highlight
        self.engine.highlight_nodes(ids)

    @service_endpoint(
        inputs={"db_path": "str"},
        outputs={},
        description="Loads graph nodes and edges from a Cartridge database and triggers the physics engine.",
        tags=["data-load", "sqlite"],
        side_effects=["filesystem:read"]
    )
    def load_from_db(self, db_path):
        """
        Loads graph data from SQLite.
        Does NOT block the UI. The physics engine will settle the nodes frame-by-frame.
        """
        if not os.path.exists(db_path): return
        
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # [cite_start]Fetch Nodes [cite: 198]
            db_nodes = cursor.execute("SELECT id, type, label, data_json FROM graph_nodes").fetchall()
            
            # [cite_start]Fetch Edges [cite: 198]
            db_edges = cursor.execute("SELECT source, target FROM graph_edges").fetchall()
            
            conn.close()
        except Exception as e:
            print(f"Graph Load Error: {e}")
            return

        # Format for Engine
        id_to_index = {}
        formatted_nodes = []
        
        for idx, row in enumerate(db_nodes):
            node_id, n_type, label, raw_json = row
            meta = {}
            try:
                if raw_json: meta = json.loads(raw_json)
            except: pass
            
            id_to_index[node_id] = idx
            formatted_nodes.append({'id': node_id, 'type': n_type, 'label': label, 'meta': meta})

        formatted_links = []
        for src, tgt in db_edges:
            if src in id_to_index and tgt in id_to_index:
                formatted_links.append((id_to_index[src], id_to_index[tgt]))

        # Inject Data - The Physics Engine handles the "Explosion" logic internally
        self.engine.set_data(formatted_nodes, formatted_links)

    def on_resize(self, event):
        if event.width > 1 and event.height > 1:
            self.engine.resize(event.width, event.height)

    def on_double_click(self, event):
        # Zoom in on the node we clicked
        hit_node = self.engine.get_node_at(event.x, event.y)
        if hit_node:
            # Center camera on node and zoom in
            self.engine.cam_x = hit_node['x']
            self.engine.cam_y = hit_node['y']
            self.engine.zoom = 2.0
            self.engine.settled = False

    def on_click(self, event):
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y
        
        # Check if we clicked a node
        hit = self.engine.handle_mouse_down(event.x, event.y)
        if hit:
            self.is_dragging_node = True
        else:
            self.is_panning = True

    def on_release(self, event):
        self.engine.handle_mouse_up()
        self.is_dragging_node = False
        self.is_panning = False

    def on_drag(self, event):
        if self.is_dragging_node:
            self.engine.handle_mouse_move(event.x, event.y, True)
        elif self.is_panning:
            # Camera Pan
            dx = event.x - self.last_mouse_x
            dy = event.y - self.last_mouse_y
            self.engine.pan(dx, dy)
            
        self.last_mouse_x = event.x
        self.last_mouse_y = event.y

    def on_hover(self, event):
        if not self.is_dragging_node:
            self.engine.handle_mouse_move(event.x, event.y, False)

    def on_zoom(self, amount):
        self.engine.zoom_camera(amount, 0, 0)
        self.engine.settled = False # Wake up physics on zoom

    def on_windows_scroll(self, event):
        if event.delta > 0: self.on_zoom(1.1)
        else: self.on_zoom(0.9)

    @service_endpoint(
        inputs={},
        outputs={},
        description="The primary heartbeat loop that orchestrates frame-by-frame physics steps and UI blitting.",
        tags=["lifecycle", "rendering"],
        mode="async"
    )
    def animate(self):
        """
        The Heartbeat Loop.
        Runs at ~30 FPS. Handles Physics + Rendering.
        """
        # 1. Step Physics (Micro-calculations)
        self.engine.step_physics()
        
        # 2. Render to Buffer
        raw_data = self.engine.get_image_bytes()
        
        # 3. Blit to Screen
        if raw_data:
            img = Image.frombytes('RGB', (self.engine.width, self.engine.height), raw_data)
            self.photo = ImageTk.PhotoImage(img)
            self.canvas_lbl.configure(image=self.photo)
        
        # 4. Loop
        self.after(30, self.animate)

        if __name__ == "__main__":
            root = tk.Tk()
            root.title("NeuralGraphViewerMS Test")
            view = NeuralGraphViewerMS(root)
            print("Service ready:", view._service_info['name'])
            # Note: Requires a valid DB and Pygame environment to fully render
            root.mainloop()


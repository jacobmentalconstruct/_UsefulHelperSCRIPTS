"""
SERVICE_NAME: _NeuralGraphEngineMS
ENTRY_POINT: _NeuralGraphEngineMS.py
DEPENDENCIES: None
"""

import pygame
import math
import random
import time

# Initialize font module globally once
pygame.font.init()

from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
    name="NeuralGraphEngineMS",
    version="1.1.0",
    description="The Cartographer: A physics-driven rendering engine for visualizing complex neural relationships in a 2D force-directed graph.",
    tags=["visualization", "graph", "pygame"],
    capabilities=["force-directed-layout", "real-time-rendering"],
    dependencies=["pygame", "math", "random"],
    side_effects=["ui:update", "render:write"]
)
class NeuralGraphEngineMS(BaseService):
    def __init__(self, width, height, bg_color=(16, 16, 24)):
        super().__init__("NeuralGraphEngineMS")
        self.width = width
        self.start_time = time.time()
        self.height = height
        self.bg_color = bg_color
        
        self.surface = pygame.Surface((width, height))
        
        # Camera
        self.cam_x = 0
        self.cam_y = 0
        self.zoom = 1.0
        
        # Assets
        self.font = pygame.font.SysFont("Consolas", 12)
        
        # Data
        self.nodes = [] 
        self.links = []
        
        # Interaction
        self.dragged_node_idx = None
        self.hovered_node_idx = None
        
        # Physics State
        self.settled = False

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float", "nodes": "int", "settled": "bool"},
        description="Standardized health check to verify the operational state of the graph renderer.",
        tags=["diagnostic", "health"]
    )
    def get_health(self) -> Dict[str, Any]:
        """Returns the operational status of the NeuralGraphEngineMS."""
        return {
            "status": "online",
            "uptime": time.time() - self.start_time,
            "nodes": len(self.nodes),
            "settled": self.settled
        }

    def resize(self, width, height):
        self.width = width
        self.height = height
        self.surface = pygame.Surface((width, height))

    @service_endpoint(
        inputs={"nodes": "list", "links": "list"},
        outputs={},
        description="Injects new node and edge data into the engine and wakes up the physics simulation.",
        tags=["data", "update"],
        side_effects=["graph:write"]
    )
    def set_data(self, nodes, links):
        self.nodes = nodes
        self.links = links
        self.settled = False # Wake up physics on new data
        
        # 1. Build an ID map so we can find parents
        node_map = {node['id']: node for node in self.nodes}

        for n in self.nodes:
            # GNN Injection: Use pre-calculated layout if available
            if 'gnn_x' in n and 'gnn_y' in n:
                n['x'] = n['gnn_x'] * self.width
                n['y'] = n['gnn_y'] * self.height

            elif 'x' not in n:
                # SMART SPAWN: If I am a satellite, spawn near my planet
                parent_id = n.get('meta', {}).get('parent')
                if parent_id and parent_id in node_map and 'x' in node_map[parent_id]:
                    p = node_map[parent_id]
                    angle = random.random() * 6.28
                    dist = 30
                    n['x'] = p['x'] + math.cos(angle) * dist
                    n['y'] = p['y'] + math.sin(angle) * dist
                else:
                    # Random spawn for Files
                    n['x'] = random.randint(int(self.width*0.2), int(self.width*0.8))
                    n['y'] = random.randint(int(self.height*0.2), int(self.height*0.8))
            if 'vx' not in n: n['vx'] = 0
            if 'vy' not in n: n['vy'] = 0
            
            # Semantic Coloring
            if n.get('type') == 'file':
                n['_color'] = (0, 122, 204) # Blue
                n['_radius'] = 6
            elif n.get('type') == 'web':
                n['_color'] = (204, 0, 122) # Purple/Pink
                n['_radius'] = 7
            elif n.get('type') == 'chunk':
                n['_color'] = (100, 200, 100) # Satellite Green
                n['_radius'] = 3
            else:
                n['_color'] = (160, 32, 240) # Default
                n['_radius'] = 6

    # --- INPUT HANDLING ---
    
    def screen_to_world(self, sx, sy):
        cx, cy = self.width / 2, self.height / 2
        wx = (sx - cx) / self.zoom + cx - self.cam_x
        wy = (sy - cy) / self.zoom + cy - self.cam_y
        return wx, wy

    def get_node_at(self, sx, sy):
        wx, wy = self.screen_to_world(sx, sy)
        for n in self.nodes:
            dist = math.hypot(n['x'] - wx, n['y'] - wy)
            if dist < n['_radius'] * 2:
                return n
        return None

    def handle_mouse_down(self, x, y):
        wx, wy = self.screen_to_world(x, y)
        for i, n in enumerate(self.nodes):
            dist = math.hypot(n['x'] - wx, n['y'] - wy)
            if dist < n['_radius'] * 2:
                self.dragged_node_idx = i
                self.settled = False # Wake up physics
                return True
        return False

    def handle_mouse_move(self, x, y, is_dragging):
        wx, wy = self.screen_to_world(x, y)
        
        if is_dragging and self.dragged_node_idx is not None:
            node = self.nodes[self.dragged_node_idx]
            node['x'] = wx
            node['y'] = wy
            node['vx'] = 0
            node['vy'] = 0
            self.settled = False
        else:
            prev_hover = self.hovered_node_idx
            self.hovered_node_idx = None
            for i, n in enumerate(self.nodes):
                dist = math.hypot(n['x'] - wx, n['y'] - wy)
                if dist < n['_radius'] * 2:
                    self.hovered_node_idx = i
                    break
            return prev_hover != self.hovered_node_idx

    def handle_mouse_up(self):
        self.dragged_node_idx = None

    def pan(self, dx, dy):
        self.cam_x += dx / self.zoom
        self.cam_y += dy / self.zoom

    def zoom_camera(self, amount, mouse_x, mouse_y):
        self.zoom *= amount
        self.zoom = max(0.1, min(self.zoom, 5.0))

    def highlight_nodes(self, node_ids):
        """Highlights specific nodes by ID."""
        for n in self.nodes:
            # 1. Reset to defaults
            if n.get('type') == 'file': 
                n['_color'] = (0, 122, 204)
                n['_radius'] = 6
            elif n.get('type') == 'web': 
                n['_color'] = (204, 0, 122)
                n['_radius'] = 7
            elif n.get('type') == 'chunk': 
                n['_color'] = (100, 200, 100)
                n['_radius'] = 3
            else: 
                n['_color'] = (160, 32, 240)
                n['_radius'] = 6
                
            # 2. Apply Highlight
            if n['id'] in node_ids:
                n['_color'] = (255, 255, 0) # Bright Yellow
                n['_radius'] = 12
                
        self.settled = False # Wake up physics

    # --- PHYSICS (Damped) ---

    @service_endpoint(
        inputs={},
        outputs={"settled": "bool"},
        description="Performs one iteration of the force-directed physics calculation.",
        tags=["physics", "lifecycle"],
        mode="async",
        side_effects=["graph:update"]
    )
    def step_physics(self):
        if not self.nodes or self.settled: return

        REPULSION = 1000
        ATTRACTION = 0.01
        CENTER_GRAVITY = 0.01
        DAMPING = 0.85 # Increased damping to settle faster
        
        cx, cy = self.width / 2, self.height / 2
        total_kinetic_energy = 0

        for i, a in enumerate(self.nodes):
            if i == self.dragged_node_idx: continue

            # LOD: Freeze satellites if zoomed out
            if self.zoom < 1.2 and a.get('type') == 'chunk':
                a['vx'] = 0
                a['vy'] = 0
                continue
            
            fx, fy = 0, 0
            
            # 1. Gravity (Center pull)
            fx += (cx - a['x']) * CENTER_GRAVITY
            fy += (cy - a['y']) * CENTER_GRAVITY

            # 2. Repulsion
            for j, b in enumerate(self.nodes):
                if i == j: continue
                dx = a['x'] - b['x']
                dy = a['y'] - b['y']
                dist_sq = dx*dx + dy*dy
                if dist_sq < 0.1: dist_sq = 0.1
                
                # Performance opt: Ignore far away nodes
                if dist_sq > 25000: continue 

                f = REPULSION / dist_sq
                dist = math.sqrt(dist_sq)
                fx += (dx / dist) * f
                fy += (dy / dist) * f

            a['vx'] = (a['vx'] + fx) * DAMPING
            a['vy'] = (a['vy'] + fy) * DAMPING

        # 3. Attraction (Links)
        for u, v in self.links:
            a = self.nodes[u]
            b = self.nodes[v]
            dx = b['x'] - a['x']
            dy = b['y'] - a['y']
            fx = dx * ATTRACTION
            fy = dy * ATTRACTION
            
            if u != self.dragged_node_idx:
                a['vx'] += fx
                a['vy'] += fy
            if v != self.dragged_node_idx:
                b['vx'] -= fx
                b['vy'] -= fy

        # 4. Apply & Measure Energy
        for i, n in enumerate(self.nodes):
            if i == self.dragged_node_idx: continue
            n['x'] += n['vx']
            n['y'] += n['vy']
            total_kinetic_energy += (abs(n['vx']) + abs(n['vy']))

        # 5. Sleep Threshold
        if total_kinetic_energy < 0.5:
            self.settled = True

    # --- RENDERING ---

    @service_endpoint(
        inputs={},
        outputs={"raw_data": "bytes"},
        description="Renders the current frame to a byte buffer for display in UI components.",
        tags=["render", "output"],
        side_effects=["ui:update", "render:write"]
    )
    def get_image_bytes(self):
        self.surface.fill(self.bg_color)
        
        cx, cy = self.width / 2, self.height / 2
        def to_screen(x, y):
            sx = (x - cx + self.cam_x) * self.zoom + cx
            sy = (y - cy + self.cam_y) * self.zoom + cy
            return int(sx), int(sy)

        # Links
        for u, v in self.links:
            if self.zoom < 1.2:
                if self.nodes[u].get('type') == 'chunk' or self.nodes[v].get('type') == 'chunk':
                    continue

            start = to_screen(self.nodes[u]['x'], self.nodes[u]['y'])
            end = to_screen(self.nodes[v]['x'], self.nodes[v]['y'])
            pygame.draw.line(self.surface, (60, 60, 80), start, end, 1)

        # Nodes
        for i, n in enumerate(self.nodes):
            # LOD: Hide chunks if zoomed out
            if self.zoom < 1.2 and n.get('type') == 'chunk':
                continue

            sx, sy = to_screen(n['x'], n['y'])
            if sx < -20 or sx > self.width + 20 or sy < -20 or sy > self.height + 20: continue
                
            rad = int(n['_radius'] * self.zoom)
            col = n['_color']
            
            if i == self.hovered_node_idx or i == self.dragged_node_idx:
                pygame.draw.circle(self.surface, (255, 255, 255), (sx, sy), rad + 2)
            
            pygame.draw.circle(self.surface, col, (sx, sy), rad)
            
            if self.zoom > 0.8 or i == self.hovered_node_idx:
                text = self.font.render(n['label'], True, (200, 200, 200))
                self.surface.blit(text, (sx + rad + 4, sy - 6))

        return pygame.image.tostring(self.surface, 'RGB')

        if __name__ == "__main__":
            # Manual test setup
            engine = NeuralGraphEngineMS(400, 300)
            print("Service ready:", engine._service_info['name'])
            test_nodes = [{'id': 'A', 'type': 'file', 'label': 'Node A'}, {'id': 'B', 'type': 'chunk', 'label': 'Node B'}]
            test_links = [(0, 1)]
            engine.set_data(test_nodes, test_links)
            engine.step_physics()
            print("Physics step completed.")






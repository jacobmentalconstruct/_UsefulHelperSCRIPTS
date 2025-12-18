import pygame
import math
import random

# Initialize font module globally once
pygame.font.init()

class GraphRenderer:
    def __init__(self, width, height, bg_color=(16, 16, 24)):
        self.width = width
        self.height = height
        self.bg_color = bg_color
        
        # Surface for drawing
        self.surface = pygame.Surface((width, height))
        
             # Camera State
        self.cam_x = 0
        self.cam_y = 0
        self.zoom = 1.0
        
        # Assets
        self.font = pygame.font.SysFont("Consolas", 12)
        
        # Data
        self.nodes = [] 
        self.links = []
        
        # Interaction State
        self.dragged_node_idx = None
        self.hovered_node_idx = None

    def resize(self, width, height):
        """Re-initialize surface on window resize"""
        self.width = width
        self.height = height
        self.surface = pygame.Surface((width, height))

    def set_data(self, nodes, links):
        """
        Expects nodes to have: id, type ('file'|'concept'), label
        Expects links to be tuples of indices: (source_idx, target_idx)
        """
        self.nodes = nodes
        self.links = links
        
        # Initialize physics state for new nodes
        for n in self.nodes:
            if 'x' not in n:
                n['x'] = random.randint(int(self.width*0.2), int(self.width*0.8))
n['y'] = random.randint(int(self.height*0.2), int(self.height*0.8))
            if 'vx' not in n: n['vx'] = 0
            if 'vy' not in n: n['vy'] = 0
            
            # Cache visual properties based on type
            if n.get('type') == 'file':
                n['_color'] = (0, 122, 204) # #007ACC (Blue)
                n['_radius'] = 6
            else:
                n['_color'] = (160, 32, 240) # #A020F0 (Purple)
                n['_radius'] = 8

    # --- INPUT HANDLING (Coordinate Transforms) ---
    
    def screen_to_world(self, sx, sy):
        """Convert Tkinter screen coordinates to Physics world coordinates"""
        # (Screen - Center) / Zoom + Center - Camera
        cx, cy = self.width / 2, self.height / 2
        wx = (sx - cx) / self.zoom + cx - self.cam_x
        wy = (sy - cy) / self.zoom + cy - self.cam_y
        return wx, wy

    def handle_mouse_down(self, x, y):
        wx, wy = self.screen_to_world(x, y)
        # Find clicked node
        for i, n in enumerate(self.nodes):
            dist = math.hypot(n['x'] - wx, n['y'] - wy)
            if dist < n['_radius'] * 2: # Generous hit box
                self.dragged_node_idx = i
                return True
        return False

    def handle_mouse_move(self, x, y, is_dragging):
        wx, wy = self.screen_to_world(x, y)
        
        if is_dragging and self.dragged_node_idx is not None:
            # Move the node directly
            node = self.nodes[self.dragged_node_idx]
            node['x'] = wx
            node['y'] = wy
            node['vx'] = 0
            node['vy'] = 0
        else:
            # Hover check
            prev_hover = self.hovered_node_idx
            self.hovered_node_idx = None
            for i, n in enumerate(self.nodes):
                dist = math.hypot(n['x'] - wx, n['y'] - wy)
                if dist < n['_radius'] * 2:
                    self.hovered_node_idx = i
                    break
            
            return prev_hover != self.hovered_node_idx # Return True if redraw needed

    def handle_mouse_up(self):
        self.dragged_node_idx = None

    def pan(self, dx, dy):
        self.cam_x += dx / self.zoom
        self.cam_y += dy / self.zoom

    def zoom_camera(self, amount, mouse_x, mouse_y):
        # Zoom towards mouse pointer logic could go here
        # For now, simple center zoom
        old_zoom = self.zoom
        self.zoom *= amount
        self.zoom = max(0.1, min(self.zoom, 5.0))

    # --- PHYSICS ---

    def step_physics(self):
        if not self.nodes: return

        # Constants matching D3 feel
        REPULSION = 1000
        ATTRACTION = 0.01
        CENTER_GRAVITY = 0.01
        DAMPING = 0.9
        
        cx, cy = self.width / 2, self.height / 2
# 1. Repulsion (Nodes push apart)
        for i, a in enumerate(self.nodes):
            if i == self.dragged_node_idx: continue # Don't move dragged node
            
            fx, fy = 0, 0
            
            # Center Gravity (Pull lightly to middle so they don't drift away)
            fx += (cx - a['x']) * CENTER_GRAVITY
            fy += (cy - a['y']) * CENTER_GRAVITY

            # Node-Node Repulsion
            for j, b in enumerate(self.nodes):
                if i == j: continue
                dx = a['x'] - b['x']
                dy = a['y'] - b['y']
                dist_sq = dx*dx + dy*dy
                if dist_sq < 0.1: dist_sq = 0.1
                
                # Force = k / dist^2
                f = REPULSION / dist_sq
                dist = math.sqrt(dist_sq)
                fx += (dx / dist) * f
                fy += (dy / dist) * f

            a['vx'] = (a['vx'] + fx) * DAMPING
            a['vy'] = (a['vy'] + fy) * DAMPING

        # 2. Attraction (Links pull together)
        for u, v in self.links:
            a = self.nodes[u]
            b = self.nodes[v]
            
            dx = b['x'] - a['x']
            dy = b['y'] - a['y']
            
            # Spring force
            fx = dx * ATTRACTION
            fy = dy * ATTRACTION
            if u != self.dragged_node_idx:
                a['vx'] += fx
                a['vy'] += fy
            if v != self.dragged_node_idx:
                b['vx'] -= fx
                b['vy'] -= fy

        # 3. Apply Velocity
        for i, n in enumerate(self.nodes):
            if i == self.dragged_node_idx: continue
            n['x'] += n['vx']
            n['y'] += n['vy']

    # --- RENDERING ---

    def get_image_bytes(self):
        """ Renders the scene and returns raw RGB bytes + size """
        self.surface.fill(self.bg_color)
        
        # Pre-calculate center offset
        cx, cy = self.width / 2, self.height / 2
        
        # Helper for transforms
        def to_screen(x, y):
            sx = (x - cx + self.cam_x) * self.zoom + cx
            sy = (y - cy + self.cam_y) * self.zoom + cy
            return int(sx), int(sy)

        # 1. Draw Links
        for u, v in self.links:
            start = to_screen(self.nodes[u]['x'], self.nodes[u]['y'])
            end = to_screen(self.nodes[v]['x'], self.nodes[v]['y'])
            pygame.draw.line(self.surface, (60, 60, 80), start, end, 1)

        # 2. Draw Nodes
        for i, n in enumerate(self.nodes):
            sx, sy = to_screen(n['x'], n['y'])
            
            # Culling: Don't draw if off screen
            if sx < -20 or sx > self.width + 20 or sy < -20 or sy > self.height + 20:
if sx < -20 or sx > self.width + 20 or sy < -20 or sy > self.height + 20:
                continue

            rad = int(n['_radius'] * self.zoom)
            col = n['_color']

            # Highlight hovered
            if i == self.hovered_node_idx or i == self.dragged_node_idx:
                pygame.draw.circle(self.surface, (255, 255, 255), (sx, sy), rad + 2)

            pygame.draw.circle(self.surface, col, (sx, sy), rad)

            # Draw Labels (only if zoomed in enough or hovered)
            if self.zoom > 0.8 or i == self.hovered_node_idx:
                text = self.font.render(n['label'], True, (200, 200, 200))
                self.surface.blit(text, (sx + rad + 4, sy - 6))

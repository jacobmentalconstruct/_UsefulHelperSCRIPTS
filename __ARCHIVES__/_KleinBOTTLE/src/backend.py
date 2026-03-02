"""Backend orchestrator for KleinBOTTLE world-builder.

Owns world state, coordinates services, dispatches AI/SD tasks.
All UI callbacks are scheduled via root.after() for thread safety.
"""

from __future__ import annotations

import json
import os
import time
import threading
from copy import deepcopy
from typing import Callable, Dict, List, Optional

from models import Room, Exit, World, _safe_int
from services import OllamaService, StableDiffusionService


class Backend:
    """Central orchestrator: state + service dispatch."""

    def __init__(self, root, base_dir: str):
        self.root = root
        self.base_dir = base_dir

        # Services
        self.ollama = OllamaService()
        self.sd = StableDiffusionService()

        # World state
        self.world: Optional[World] = None
        self.current_world_path: Optional[str] = None
        self.is_dirty = False
        self.is_scribing = False
        self.is_painting = False
        self.history: List[dict] = []

        # Load default world
        self._load_default_world()

    def _load_default_world(self):
        default_map = os.path.join(self.base_dir, "map", "default_map.json")
        try:
            if os.path.exists(default_map):
                self.world = World.from_file(default_map)
                self.current_world_path = default_map
            else:
                self.world = World._default_manor()
        except Exception:
            self.world = World._default_manor()
            self.current_world_path = None

    # ----- State helpers -----

    def mark_dirty(self):
        self.is_dirty = True

    def history_log(self, action: str):
        self.history.insert(0, {
            "id": str(time.time()),
            "action": action,
            "timestamp": time.strftime("%H:%M:%S"),
        })

    # ----- Navigation -----

    def travel_by_direction(self, direction: str) -> Optional[str]:
        """Returns error message or None on success."""
        r = self.world.current_room
        ex = next((e for e in r.exits if e.direction.lower() == direction.lower()), None)
        if not ex:
            return f"You can't go that way ({direction})."
        return self.travel_to(ex.target_id)

    def travel_to(self, target_id: str) -> Optional[str]:
        """Returns error message or None on success."""
        if self.world.travel(target_id):
            dest = self.world.current_room
            self.history_log(f"Travelled to {dest.title}")
            return None
        return "That destination does not exist."

    def handle_command(self, cmd: str) -> List[str]:
        """Parse an adventure command. Returns list of log lines."""
        lines = [f"> {cmd}"]
        low = cmd.lower()

        if low.startswith("go "):
            dir_ = low.split(" ", 1)[1].strip()
            lookup = {"n": "North", "s": "South", "e": "East", "w": "West", "u": "Up", "d": "Down"}
            dir_name = lookup.get(dir_, dir_.capitalize())
            err = self.travel_by_direction(dir_name)
            if err:
                lines.append(err)
            else:
                dest = self.world.current_room
                lines.append(f"You arrive at the {dest.title}.")
            return lines

        lines.append(f'The command "{cmd}" echoes through the manor, but nothing happens.')
        return lines

    # ----- Room editing -----

    def commit_room_edits(self, title: str, atmosphere: str):
        r = self.world.current_room
        if title and title != r.title:
            r.title = title
        if atmosphere and atmosphere != r.atmosphere:
            r.atmosphere = atmosphere
        self.mark_dirty()

    def commit_hidden_notes(self, text: str):
        self.world.current_room.hidden_notes = text
        self.mark_dirty()

    def add_content(self, item: str):
        self.world.current_room.contents.append(item)
        self.mark_dirty()

    # ----- File I/O -----

    def open_world(self, path: str):
        """Load a world from file. Raises on failure."""
        w = World.from_file(path)
        if not w.current_room_id or w.current_room_id not in w.rooms:
            raise ValueError("World has no valid start/current room.")
        self.world = w
        self.current_world_path = path
        self.is_dirty = False
        self.history_log(f"Opened World: {os.path.basename(path)}")

    def save_world(self, path: Optional[str] = None) -> str:
        """Save world to path. Returns the path saved to."""
        path = path or self.current_world_path
        if not path:
            raise ValueError("No save path specified.")

        data = self.world.to_dict()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        self.world.source_path = path
        if self.world.format == "molt":
            self.world._raw_world = deepcopy(data)

        self.current_world_path = path
        self.is_dirty = False
        self.history_log(f"Saved World: {os.path.basename(path)}")
        return path

    # ----- Ollama -----

    def refresh_ollama_models(self) -> List[str]:
        return self.ollama.list_models()

    def check_ollama_status(self) -> bool:
        return self.ollama.is_online()

    def generate_text(self, model: str, prompt: str,
                      on_success: Callable[[str], None],
                      on_error: Callable[[str], None]):
        """Generate text via Ollama in background thread."""
        self.is_scribing = True
        self.ollama.generate_async(
            model, prompt,
            on_success=on_success,
            on_error=on_error,
            scheduler=self.root.after,
        )

    # ----- Stable Diffusion -----

    def generate_room_image(self, on_success: Callable[[bytes], None],
                            on_error: Callable[[str], None]):
        """Generate a room image via SD in background thread."""
        r = self.world.current_room
        self.is_painting = True

        prompt = (f"90s sierra vga game style, {r.atmosphere} {r.title}, "
                  f"{r.focal_point}, pixel art, dithered, 256 colors, scanlines")
        neg = "photorealistic, modern, high resolution, 3d, gradient, smooth"

        self.sd.txt2img_async(
            prompt,
            on_success=on_success,
            on_error=on_error,
            scheduler=self.root.after,
            negative_prompt=neg,
            width=640, height=400, steps=25, cfg_scale=7.5,
        )

    def save_room_image(self, img_bytes: bytes) -> str:
        """Save image bytes to assets/rooms/{room_id}.png. Returns path."""
        room_id = self.world.current_room.id
        rooms_dir = os.path.join(self.base_dir, "assets", "rooms")
        os.makedirs(rooms_dir, exist_ok=True)
        asset_path = os.path.join(rooms_dir, f"{room_id}.png")
        with open(asset_path, "wb") as f:
            f.write(img_bytes)
        self.world.current_room.image_url = asset_path
        self.mark_dirty()
        return asset_path

    # ----- Service polling -----

    def start_polling(self, on_status: Callable[[bool, str], None], interval_ms: int = 5000):
        """Start a background polling loop for service status."""
        def check():
            online = self.check_ollama_status()
            status = f"Online: {self.ollama.list_models()[0]}" if online and self.ollama.list_models() else "Ollama Offline"
            self.root.after(0, lambda: on_status(online, status))
            self.root.after(interval_ms, check)

        self.root.after(interval_ms, check)

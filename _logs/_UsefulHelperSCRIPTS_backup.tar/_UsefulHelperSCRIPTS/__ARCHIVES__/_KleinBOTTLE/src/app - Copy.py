"""IsolateIRL - Tkinter UI Stub (Monolithic)

Goal
----
Mimic the UI structure seen in the _IsolateIRL file dump (the React "Atelier World-Builder" layout)
using the same Tkinter theme logic/colors as the provided microservice examples.

Notes
-----
- All actions are stubbed (no external services).
- Images are placeholders rendered via Canvas.
- The UI is intentionally modular *inside this single file* so we can later split into services.

Run
---
python app.py

"""

from __future__ import annotations

import json
import time
import threading
import requests
import ollama
import io
import base64
import shutil
import os
from PIL import Image, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional


# -----------------------------------------------------------------------------
# Theme (mirrors _TkinterThemeManagerMS defaults)
# -----------------------------------------------------------------------------

DEFAULT_THEME = {
    "background": "#1e1e1e",
    "foreground": "#d4d4d4",
    "panel_bg": "#252526",
    "border": "#3c3c3c",
    "accent": "#007acc",
    "error": "#f48771",
    "success": "#89d185",
    "font_main": ("Segoe UI", 10),
    "font_main_bold": ("Segoe UI", 10, "bold"),
    "font_title": ("Segoe UI", 16, "bold"),
    "font_huge": ("Segoe UI", 26, "bold"),
    "font_mono": ("Consolas", 10),
    "font_mono_small": ("Consolas", 9),
}


class Theme:
    """Small inline theme manager compatible with the microservice palette."""

    def __init__(self, overrides: Optional[dict] = None):
        self.t = dict(DEFAULT_THEME)
        if overrides:
            self.t.update(overrides)

    def __getitem__(self, k: str):
        return self.t[k]

    def get(self, k: str, default=None):
        return self.t.get(k, default)


def _safe_int(s: str, default: int) -> int:
    try:
        return int(s)
    except Exception:
        return default


# -----------------------------------------------------------------------------
# Data model (lightweight port of the TS types)
# -----------------------------------------------------------------------------


@dataclass
class Exit:
    direction: str
    target_id: str


@dataclass
class Room:
    id: str
    title: str
    short_description: str
    description: str
    focal_point: str
    atmosphere: str
    image_url: str
    x: int
    y: int
    z: int
    contents: List[str]
    hidden_notes: str
    exits: List[Exit]


class World:
    """A small world container that can be loaded/saved.

    Supports two formats:
      - "isolateirl" (internal): rooms are Room dataclasses with explicit x/y/z and exits list.
      - "molt" (your default_map.json): rooms are keyed by room_id with a 'connections' dict.

    In viewer/manual mode we NEVER auto-mutate topology; we only load, render, move, and allow
    explicit user edits. SD image generation is user-triggered and writes only image_url.
    """

    def __init__(self, name: str, rooms: Dict[str, Room], current_room_id: str, fmt: str = "isolateirl"):
        self.name = name
        self.rooms = rooms
        self.current_room_id = current_room_id
        self.format = fmt
        self.source_path: Optional[str] = None

    @staticmethod
    def _default_manor() -> "World":
        # Original stub world retained as a fallback.
        rooms: Dict[str, Room] = {
            "living-room": Room(
                id="living-room",
                title="The Gilded Living Room",
                short_description="A warm, central hub with plush rugs and a crackling hearth.",
                description=(
                    "The center of the home. Sunlight filters through lace curtains, illuminating heavy oak furniture. "
                    "The scent of woodsmoke and cedar lingers in the air."
                ),
                focal_point="a grand stone fireplace",
                atmosphere="Sunlit",
                image_url="placeholder://living",
                x=0,
                y=0,
                z=0,
                contents=["Plush Sofa", "Brass Fire-poker"],
                hidden_notes="A loose brick in the fireplace hides a key.",
                exits=[
                    Exit("North", "kitchen"),
                    Exit("South", "bathroom"),
                    Exit("East", "home-office"),
                    Exit("West", "bedroom"),
                    Exit("Up", "attic"),
                    Exit("Down", "basement"),
                ],
            ),
            "kitchen": Room(
                id="kitchen",
                title="The Scullery Kitchen",
                short_description="Cluttered with copper pots and the smell of rosemary.",
                description="The kitchen is a flurry of organized chaos. Braids of garlic hang from the ceiling joists.",
                focal_point="a cast iron stove",
                atmosphere="Sunlit",
                image_url="placeholder://kitchen",
                x=0,
                y=1,
                z=0,
                contents=["Copper kettle", "Sourdough starter"],
                hidden_notes="The spice rack is fake.",
                exits=[Exit("South", "living-room")],
            ),
            "bathroom": Room(
                id="bathroom",
                title="The Porcelain Lavatory",
                short_description="Cool tile and the scent of jasmine.",
                description="A quiet retreat with a clawfoot tub sitting atop black and white checkered tiles.",
                focal_point="a clawfoot tub",
                atmosphere="Misty",
                image_url="placeholder://bath",
                x=0,
                y=-1,
                z=0,
                contents=["Silk towel", "Glass bottle"],
                hidden_notes="",
                exits=[Exit("North", "living-room")],
            ),
            "home-office": Room(
                id="home-office",
                title="The Master's Study",
                short_description="Stacked with ledgers and ink-stained quills.",
                description="The walls are lined with leather-bound volumes. A massive mahogany desk sits in the corner.",
                focal_point="a mahogany desk",
                atmosphere="Dusty",
                image_url="placeholder://study",
                x=1,
                y=0,
                z=0,
                contents=["Silver quill", "Unfinished letter"],
                hidden_notes="A map is hidden in the desk drawer.",
                exits=[Exit("West", "living-room")],
            ),
            "bedroom": Room(
                id="bedroom",
                title="The Velvet Chamber",
                short_description="Soft shadows and heavy drapes.",
                description="The bed is a mountain of velvet and down. The windows are shuttered against the world.",
                focal_point="a four-poster bed",
                atmosphere="Misty",
                image_url="placeholder://bed",
                x=-1,
                y=0,
                z=0,
                contents=["Music box", "Slipper"],
                hidden_notes="",
                exits=[Exit("East", "living-room"), Exit("North", "closet")],
            ),
            "closet": Room(
                id="closet",
                title="The Small Closet",
                short_description="Cramped and smelling of cedar.",
                description="A tiny space filled with hanging furs and sturdy boots.",
                focal_point="a cedar chest",
                atmosphere="Dusty",
                image_url="placeholder://closet",
                x=-1,
                y=1,
                z=0,
                contents=["Wool cloak"],
                hidden_notes="The floorboards here are hollow.",
                exits=[Exit("South", "bedroom")],
            ),
            "attic": Room(
                id="attic",
                title="The Dust-Choked Observatory",
                short_description="Vast glass domes and brass instruments.",
                description=(
                    "High above the manor, where the air is thin. Massive brass telescopes point through the glass skylights "
                    "at the velvet sky."
                ),
                focal_point="a giant telescope",
                atmosphere="Astronomical",
                image_url="placeholder://stars",
                x=0,
                y=0,
                z=1,
                contents=["Star chart", "Brass sextant"],
                hidden_notes="Aligning the telescope to Orion opens the floor safe.",
                exits=[Exit("Down", "living-room")],
            ),
            "basement": Room(
                id="basement",
                title="The Stone-Walled Scullery",
                short_description="Damp stone and earth.",
                description=(
                    "Beneath the manor, where the roots grow deep. Cool stone walls sweat with condensation. "
                    "It smells of damp earth and fermentation."
                ),
                focal_point="a row of wine casks",
                atmosphere="Cold",
                image_url="placeholder://cave",
                x=0,
                y=0,
                z=-1,
                contents=["Vintage Merlot", "Rat trap"],
                hidden_notes="The wall behind the second cask is bricked over but sounds hollow.",
                exits=[Exit("Up", "living-room")],
            ),
        }
        return World(name="The Gilded Manor", rooms=rooms, current_room_id="living-room", fmt="isolateirl")

    @staticmethod
    def _derive_short(desc: str) -> str:
        if not desc:
            return ""
        s = desc.strip().split("\n", 1)[0].strip()
        # First sentence-ish
        if "." in s:
            s = s.split(".", 1)[0].strip() + "."
        return s

    @staticmethod
    def _layout_from_connections(start_id: str, connections_by_room: Dict[str, Dict[str, str]]) -> Dict[str, tuple[int, int, int]]:
        """Simple BFS layout to assign x/y based on cardinal directions.

        This is deterministic and does NOT write back unless you save.
        """
        deltas = {
            "north": (0, 1, 0),
            "south": (0, -1, 0),
            "east": (1, 0, 0),
            "west": (-1, 0, 0),
            "up": (0, 0, 1),
            "down": (0, 0, -1),
        }
        coords: Dict[str, tuple[int, int, int]] = {start_id: (0, 0, 0)}
        q = [start_id]
        while q:
            rid = q.pop(0)
            rx, ry, rz = coords[rid]
            for d, tid in (connections_by_room.get(rid) or {}).items():
                dl = deltas.get(d.lower())
                if not dl:
                    continue
                nx, ny, nz = rx + dl[0], ry + dl[1], rz + dl[2]
                if tid not in coords:
                    coords[tid] = (nx, ny, nz)
                    q.append(tid)
        return coords

    @classmethod
    def from_file(cls, path: str) -> "World":
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Molt format: rooms with 'connections' dict
        if isinstance(data, dict) and "rooms" in data and any(
            isinstance(v, dict) and "connections" in v for v in (data.get("rooms") or {}).values()
        ):
            rooms_raw: Dict[str, dict] = data.get("rooms") or {}
            start_id = data.get("start_room_id") or next(iter(rooms_raw.keys()), "")

            connections_by_room: Dict[str, Dict[str, str]] = {}
            for rid, rr in rooms_raw.items():
                connections_by_room[rid] = dict(rr.get("connections") or {})

            coords = cls._layout_from_connections(start_id, connections_by_room) if start_id else {}

            rooms: Dict[str, Room] = {}
            for rid, rr in rooms_raw.items():
                name = rr.get("name") or rid
                desc = rr.get("description") or ""

                # Display contents: furniture + fixtures + object names
                furniture = rr.get("furniture") or []
                fixtures = rr.get("fixtures") or []
                objs = rr.get("objects") or []
                obj_names = []
                for o in objs:
                    if isinstance(o, dict) and o.get("name"):
                        obj_names.append(o.get("name"))
                contents = [*furniture, *fixtures, *obj_names]

                cx, cy, cz = coords.get(rid, (0, 0, 0))
                exits = [Exit(direction=k.capitalize(), target_id=v) for k, v in (rr.get("connections") or {}).items()]

                rooms[rid] = Room(
                    id=rid,
                    title=name,
                    short_description=rr.get("short_description") or cls._derive_short(desc),
                    description=desc,
                    focal_point=rr.get("focal_point") or "",
                    atmosphere=rr.get("atmosphere") or "",
                    image_url=rr.get("image_url") or "",
                    x=int(cx),
                    y=int(cy),
                    z=int(cz),
                    contents=contents,
                    hidden_notes=rr.get("hidden_notes") or "",
                    exits=exits,
                )

            w = World(name=data.get("world_id") or data.get("notes") or "Molt Habitat", rooms=rooms, current_room_id=start_id or next(iter(rooms.keys()), ""), fmt="molt")
            w.source_path = path
            return w

        # Internal format (optional): treat as isolateirl if it resembles our schema payload
        if isinstance(data, dict) and "rooms" in data and isinstance(data.get("rooms"), dict):
            rooms: Dict[str, Room] = {}
            for rid, rr in (data.get("rooms") or {}).items():
                exits = [Exit(e.get("direction", ""), e.get("targetId", "")) for e in (rr.get("exits") or []) if isinstance(e, dict)]
                rooms[rid] = Room(
                    id=rid,
                    title=rr.get("title") or rid,
                    short_description=rr.get("shortDescription") or "",
                    description=rr.get("description") or "",
                    focal_point=rr.get("focalPoint") or "",
                    atmosphere=rr.get("atmosphere") or "",
                    image_url=rr.get("imageUrl") or "",
                    x=int((rr.get("coordinates") or {}).get("x", 0)),
                    y=int((rr.get("coordinates") or {}).get("y", 0)),
                    z=int((rr.get("coordinates") or {}).get("z", 0)),
                    contents=list(rr.get("contents") or []),
                    hidden_notes=rr.get("hiddenNotes") or "",
                    exits=exits,
                )
            cur = data.get("current_room_id") or data.get("start_room_id") or next(iter(rooms.keys()), "")
            w = World(name=data.get("name") or "World", rooms=rooms, current_room_id=cur, fmt="isolateirl")
            w.source_path = path
            return w

        # Fallback
        w = cls._default_manor()
        w.source_path = path
        return w

    def to_dict(self) -> dict:
        if self.format == "molt":
            # Write back preserving the molt structure; we only update safe content keys.
            rooms_out: Dict[str, dict] = {}
            for rid, r in self.rooms.items():
                # Preserve existing keys best-effort by rebuilding minimal room dict.
                # We intentionally keep topology in the connections dict derived from exits.
                connections = {e.direction.lower(): e.target_id for e in r.exits}
                rooms_out[rid] = {
                    "name": r.title,
                    "type": "interior" if rid.startswith("house.") else "exterior",
                    "zone": "house" if rid.startswith("house.") else "yard",
                    "description": r.description,
                    "short_description": r.short_description,
                    "focal_point": r.focal_point,
                    "atmosphere": r.atmosphere,
                    "image_url": r.image_url,
                    "hidden_notes": r.hidden_notes,
                    "connections": connections,
                    # Keep the UI-friendly flattened contents as a separate key so we don't destroy furniture/fixtures/objects.
                    "contents_flat": list(r.contents),
                }
            return {
                "world_id": self.name,
                "schema_version": "0.1",
                "start_room_id": self.current_room_id,
                "rooms": rooms_out,
            }

        # isolateirl format
        rooms_out: Dict[str, dict] = {}
        for rid, r in self.rooms.items():
            rooms_out[rid] = {
                "title": r.title,
                "shortDescription": r.short_description,
                "description": r.description,
                "focalPoint": r.focal_point,
                "atmosphere": r.atmosphere,
                "imageUrl": r.image_url,
                "coordinates": {"x": r.x, "y": r.y, "z": r.z},
                "contents": list(r.contents),
                "hiddenNotes": r.hidden_notes,
                "exits": [{"direction": e.direction, "targetId": e.target_id} for e in r.exits],
            }
        return {
            "name": self.name,
            "schema_version": "isolateirl_world_0.1",
            "current_room_id": self.current_room_id,
            "rooms": rooms_out,
        }

    @property
    def current_room(self) -> Room:
        return self.rooms[self.current_room_id]

    def travel(self, target_id: str) -> bool:
        if target_id in self.rooms:
            self.current_room_id = target_id
            return True
        return False


# -----------------------------------------------------------------------------
# Tk helpers
# -----------------------------------------------------------------------------


class ScrollableFrame(ttk.Frame):
    """A ttk frame with a canvas+scrollbar interior (vertical)."""

    def __init__(self, parent, theme: Theme, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)

        self.theme = theme
        self.canvas = tk.Canvas(
            self,
            bg=theme["background"],
            highlightthickness=0,
            bd=0,
        )
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.inner = ttk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Mouse wheel (Windows)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_inner_configure(self, _evt):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, evt):
        self.canvas.itemconfigure(self.inner_id, width=evt.width)

    def _on_mousewheel(self, evt):
        # Only scroll if the pointer is over this canvas
        x, y = self.winfo_pointerxy()
        w = self.winfo_containing(x, y)
        if w is None:
            return
        # If mouse is over inner/canvas descendants, scroll
        if str(w).startswith(str(self.canvas)) or str(w).startswith(str(self.inner)):
            self.canvas.yview_scroll(int(-1 * (evt.delta / 120)), "units")


# -----------------------------------------------------------------------------
# Main App
# -----------------------------------------------------------------------------


class IsolateIRLApp:
    def __init__(self):
        self.theme = Theme()

        # Prefer loading the project map if present
        self.current_world_path: Optional[str] = None
        base_dir = os.path.dirname(os.path.abspath(__file__))
        default_map_path = os.path.join(base_dir, "map", "default_map.json")
        try:
            if os.path.exists(default_map_path):
                self.world = World.from_file(default_map_path)
                self.current_world_path = default_map_path
            else:
                self.world = World._default_manor()
        except Exception as e:
            # Always fail safe into the stub world.
            self.world = World._default_manor()
            self.current_world_path = None


        self.root = tk.Tk()
        self.root.title("IsolateIRL - UI Stub")
        self.root.geometry("1400x900")
        self.root.configure(bg=self.theme["background"])

        self._configure_style()

        self.is_dirty = False
        self.is_scribing = False
        self.is_painting = False
        self.map_zoom = 1.5
        self.img_refs = {}

        self.history: List[dict] = []

        self._build_root_layout()
        # UI is now fully built; safely populate data and start services
        self._render_room()
        self._wire_initial_state()

    # -------------------------------------------------------------------------
    # Styling
    # -------------------------------------------------------------------------

    def _configure_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        bg = self.theme["background"]
        fg = self.theme["foreground"]
        panel = self.theme["panel_bg"]
        border = self.theme["border"]
        accent = self.theme["accent"]

        style.configure("TFrame", background=bg)
        style.configure("Panel.TFrame", background=panel)
        style.configure("TLabel", background=bg, foreground=fg, font=self.theme["font_main"])
        style.configure("Title.TLabel", background=bg, foreground=fg, font=self.theme["font_title"])
        style.configure("Huge.TLabel", background=bg, foreground=accent, font=self.theme["font_huge"])
        style.configure("Mono.TLabel", background=bg, foreground=fg, font=self.theme["font_mono"])
        style.configure("Small.Mono.TLabel", background=bg, foreground=fg, font=self.theme["font_mono_small"])

        style.configure(
            "TButton",
            background=panel,
            foreground=fg,
            bordercolor=border,
            focusthickness=2,
            focuscolor=accent,
            padding=(10, 6),
        )
        style.map(
            "TButton",
            background=[("active", "#2d2d2d")],
            foreground=[("disabled", "#777")],
        )

        style.configure(
            "Accent.TButton",
            background=accent,
            foreground="white",
            padding=(10, 6),
        )
        style.map("Accent.TButton", background=[("active", "#1290df")])

        style.configure(
            "Danger.TButton",
            background=self.theme["error"],
            foreground="black",
        )

        style.configure(
            "TEntry",
            fieldbackground="#111",
            foreground=fg,
            insertcolor=fg,
            bordercolor=border,
        )

        style.configure(
            "TCombobox",
            fieldbackground="#111",
            foreground=fg,
            arrowcolor=fg,
            bordercolor=border,
        )

        style.configure(
            "TLabelframe",
            background=panel,
            foreground=fg,
            bordercolor=border,
            lightcolor=border,
            darkcolor=border,
        )
        style.configure("TLabelframe.Label", background=panel, foreground=fg, font=self.theme["font_main_bold"])

        style.configure(
            "Treeview",
            background="#111",
            fieldbackground="#111",
            foreground=fg,
            bordercolor=border,
            rowheight=22,
        )
        style.map(
            "Treeview",
            background=[("selected", accent)],
            foreground=[("selected", "white")],
        )

    # -------------------------------------------------------------------------
    # Layout
    # -------------------------------------------------------------------------

    def _build_root_layout(self):
        # Header
        self.header = ttk.Frame(self.root, style="Panel.TFrame")
        self.header.pack(side="top", fill="x")

        self.header_left = ttk.Frame(self.header, style="Panel.TFrame")
        self.header_left.pack(side="left", fill="x", expand=True, padx=10, pady=8)

        ttk.Label(
            self.header_left,
            text="Atelier World-Builder (Tk Stub)",
            style="Title.TLabel",
        ).pack(side="left")

        self.header_nav = ttk.Frame(self.header, style="Panel.TFrame")
        self.header_nav.pack(side="left", padx=18)

        ttk.Button(self.header_nav, text="New", command=self._stub_new).pack(side="left", padx=4)
        ttk.Button(self.header_nav, text="Open", command=self._stub_open).pack(side="left", padx=4)
        self.btn_save_world = ttk.Button(self.header_nav, text="Save World", command=self._stub_save_world)
        self.btn_save_world.pack(side="left", padx=4)
        ttk.Button(self.header_nav, text="Export", command=self._stub_export).pack(side="left", padx=4)

        self.header_right = ttk.Frame(self.header, style="Panel.TFrame")
        self.header_right.pack(side="right", padx=10)
        ttk.Button(self.header_right, text="Settings", command=self._open_settings).pack(side="right")

        # Main body as a 3-pane horizontal paned window for resizability
        self.body = ttk.Panedwindow(self.root, orient="horizontal")
        self.body.pack(side="top", fill="both", expand=True)

        self.left_col = ttk.Frame(self.body)
        self.center_col = ttk.Frame(self.body)
        self.right_col = ttk.Frame(self.body)

        # Add panes with approximate ratios (22.5 / 55 / 22.5)
        self.body.add(self.left_col, weight=2)
        self.body.add(self.center_col, weight=5)
        self.body.add(self.right_col, weight=2)

        self._build_left_col()
        self._build_center_col()
        self._build_right_col()

        # Status bar
        self.status = ttk.Frame(self.root, style="Panel.TFrame")
        self.status.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self.status, textvariable=self.status_var, style="Small.Mono.TLabel").pack(side="left", padx=10, pady=4)

    def _build_left_col(self):
        # Top preview
        self.left_preview = ttk.Frame(self.left_col, style="Panel.TFrame")
        self.left_preview.pack(side="top", fill="x")

        self.preview_canvas = tk.Canvas(
            self.left_preview,
            height=140,
            bg="#111",
            highlightthickness=1,
            highlightbackground=self.theme["border"],
        )
        self.preview_canvas.pack(side="top", fill="x", padx=10, pady=10)

        self.preview_title_row = ttk.Frame(self.left_preview, style="Panel.TFrame")
        self.preview_title_row.pack(side="top", fill="x", padx=10, pady=(0, 10))

        self.lbl_room_title_small = ttk.Label(self.preview_title_row, text="", style="Mono.TLabel")
        self.lbl_room_title_small.pack(side="left", fill="x", expand=True)

        ttk.Button(self.preview_title_row, text="-", width=3, command=self._zoom_out).pack(side="right", padx=(4, 0))
        ttk.Button(self.preview_title_row, text="+", width=3, command=self._zoom_in).pack(side="right")

        # Map area with scrollbars
        self.left_map_frame = ttk.Frame(self.left_col)
        self.left_map_frame.pack(side="top", fill="both", expand=True)

        self.map_canvas = tk.Canvas(
            self.left_map_frame,
            bg=self.theme["background"],
            highlightthickness=0,
        )
        self.map_vsb = ttk.Scrollbar(self.left_map_frame, orient="vertical", command=self.map_canvas.yview)
        self.map_hsb = ttk.Scrollbar(self.left_map_frame, orient="horizontal", command=self.map_canvas.xview)
        self.map_canvas.configure(yscrollcommand=self.map_vsb.set, xscrollcommand=self.map_hsb.set)

        self.map_canvas.grid(row=0, column=0, sticky="nsew")
        self.map_vsb.grid(row=0, column=1, sticky="ns")
        self.map_hsb.grid(row=1, column=0, sticky="ew")

        self.left_map_frame.rowconfigure(0, weight=1)
        self.left_map_frame.columnconfigure(0, weight=1)

        # Navigation controls
        self.left_nav = ttk.Frame(self.left_col, style="Panel.TFrame")
        self.left_nav.pack(side="bottom", fill="x")

        nav_grid = ttk.Frame(self.left_nav, style="Panel.TFrame")
        nav_grid.pack(side="top", pady=10)

        # 3x3 direction pad
        for r in range(3):
            nav_grid.rowconfigure(r, weight=1)
        for c in range(3):
            nav_grid.columnconfigure(c, weight=1)

        self.btn_n = ttk.Button(nav_grid, text="N", width=4, command=lambda: self._travel_by_direction("North"))
        self.btn_s = ttk.Button(nav_grid, text="S", width=4, command=lambda: self._travel_by_direction("South"))
        self.btn_e = ttk.Button(nav_grid, text="E", width=4, command=lambda: self._travel_by_direction("East"))
        self.btn_w = ttk.Button(nav_grid, text="W", width=4, command=lambda: self._travel_by_direction("West"))
        self.btn_u = ttk.Button(nav_grid, text="U", width=4, command=lambda: self._travel_by_direction("Up"))
        self.btn_d = ttk.Button(nav_grid, text="D", width=4, command=lambda: self._travel_by_direction("Down"))

        ttk.Label(nav_grid, text=" ", style="Mono.TLabel").grid(row=0, column=0)
        self.btn_n.grid(row=0, column=1, padx=4, pady=4)
        self.btn_u.grid(row=0, column=2, padx=4, pady=4)

        self.btn_w.grid(row=1, column=0, padx=4, pady=4)
        ttk.Label(nav_grid, text="⎈", style="Huge.TLabel").grid(row=1, column=1, padx=6)
        self.btn_e.grid(row=1, column=2, padx=4, pady=4)

        self.btn_d.grid(row=2, column=0, padx=4, pady=4)
        self.btn_s.grid(row=2, column=1, padx=4, pady=4)
        ttk.Label(nav_grid, text=" ", style="Mono.TLabel").grid(row=2, column=2)

        self.lbl_grid_anchor = ttk.Label(self.left_nav, text="Grid Anchor: 0, 0", style="Small.Mono.TLabel")
        self.lbl_grid_anchor.pack(side="bottom", pady=(0, 10))

    def _build_center_col(self):
        # Make center scrollable (like the React main)
        self.center_scroll = ScrollableFrame(self.center_col, self.theme)
        self.center_scroll.pack(fill="both", expand=True)

        inner = self.center_scroll.inner

        # Room title
        title_block = ttk.Frame(inner)
        title_block.pack(fill="x", padx=18, pady=(18, 8))

        self.lbl_room_title_huge = ttk.Label(title_block, text="", style="Huge.TLabel")
        self.lbl_room_title_huge.pack(side="top", anchor="center")

        self.lbl_room_sub = ttk.Label(title_block, text="Scribed Node Location", style="Small.Mono.TLabel")
        self.lbl_room_sub.pack(side="top", pady=(6, 0))

        # VGA Visual container placeholder
        vga = ttk.Frame(inner, style="Panel.TFrame")
        vga.pack(fill="x", padx=18, pady=10)

        self.vga_canvas = tk.Canvas(
            vga,
            height=240,
            bg="#000",
            highlightthickness=2,
            highlightbackground=self.theme["border"],
        )
        self.vga_canvas.pack(fill="x", padx=12, pady=12)

        # Narrative
        narrative = ttk.Frame(inner)
        narrative.pack(fill="x", padx=18, pady=(8, 10))

        self.lbl_short_desc = ttk.Label(narrative, text="", style="Title.TLabel")
        self.lbl_short_desc.pack(anchor="w", pady=(0, 6))

        self.txt_desc = tk.Text(
            narrative,
            height=7,
            wrap="word",
            bg="#111",
            fg=self.theme["foreground"],
            insertbackground=self.theme["foreground"],
            font=self.theme["font_mono"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["border"],
        )
        self.txt_desc.pack(fill="x")

        # Exits banner
        exits_bar = ttk.Frame(inner, style="Panel.TFrame")
        exits_bar.pack(fill="x", padx=18, pady=10)

        ttk.Label(exits_bar, text="Passages Known", style="Small.Mono.TLabel").pack(side="top", pady=(8, 2))
        self.lbl_exits = ttk.Label(exits_bar, text="— —", style="Title.TLabel")
        self.lbl_exits.pack(side="top", pady=(0, 8))

        # Forge/tools
        forge = ttk.Frame(inner)
        forge.pack(fill="x", padx=18, pady=(10, 18))

        # Two-column grid, like React
        forge_left = ttk.Frame(forge)
        forge_right = ttk.Frame(forge)
        forge_left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        forge_right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        forge.columnconfigure(0, weight=1)
        forge.columnconfigure(1, weight=1)

        # Left: contents + hidden notes
        lf_contents = ttk.Labelframe(forge_left, text="Material Contents")
        lf_contents.pack(fill="x", pady=(0, 10))

        self.contents_frame = ttk.Frame(lf_contents, style="Panel.TFrame")
        self.contents_frame.pack(fill="x", padx=8, pady=8)

        lf_hidden = ttk.Labelframe(forge_left, text="DM Private Scripts")
        lf_hidden.pack(fill="both", expand=True)

        self.txt_hidden = tk.Text(
            lf_hidden,
            height=6,
            wrap="word",
            bg="#111",
            fg=self.theme["foreground"],
            insertbackground=self.theme["foreground"],
            font=self.theme["font_mono"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["border"],
        )
        self.txt_hidden.pack(fill="both", expand=True, padx=8, pady=8)

        # Right: Room forge + adventure sandbox
        lf_forge = ttk.Labelframe(forge_right, text="Room Forge")
        lf_forge.pack(fill="x", pady=(0, 10))

        row1 = ttk.Frame(lf_forge, style="Panel.TFrame")
        row1.pack(fill="x", padx=8, pady=(8, 4))

        self.var_title_edit = tk.StringVar()
        self.ent_title = ttk.Entry(row1, textvariable=self.var_title_edit)
        self.ent_title.pack(side="left", fill="x", expand=True)

        ttk.Button(row1, text="AI", style="Accent.TButton", width=4, command=self._stub_ai_generate).pack(side="left", padx=(6, 0))

        row2 = ttk.Frame(lf_forge, style="Panel.TFrame")
        row2.pack(fill="x", padx=8, pady=(4, 8))

        self.var_atmosphere = tk.StringVar()
        self.cmb_atmos = ttk.Combobox(
            row2,
            textvariable=self.var_atmosphere,
            values=["Dusty", "Sunlit", "Overgrown", "Misty", "Astronomical", "Cold"],
            state="readonly",
        )
        self.cmb_atmos.pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Scribe Node", style="Accent.TButton", command=self._stub_scribe_node).pack(
            side="left", padx=(6, 0)
        )

        lf_adv = ttk.Labelframe(forge_right, text="Adventure Sandbox")
        lf_adv.pack(fill="both", expand=True)

        self.txt_adv = tk.Text(
            lf_adv,
            height=8,
            wrap="word",
            bg="#000",
            fg="#00FF41",
            insertbackground="#00FF41",
            font=self.theme["font_mono_small"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["border"],
        )
        self.txt_adv.pack(fill="both", expand=True, padx=8, pady=(8, 6))

        cmd_row = ttk.Frame(lf_adv, style="Panel.TFrame")
        cmd_row.pack(fill="x", padx=8, pady=(0, 8))

        self.var_cmd = tk.StringVar()
        self.ent_cmd = ttk.Entry(cmd_row, textvariable=self.var_cmd)
        self.ent_cmd.pack(side="left", fill="x", expand=True)
        ttk.Button(cmd_row, text="Send", style="Accent.TButton", command=self._handle_command).pack(side="left", padx=(6, 0))

        # Spacer footer
        ttk.Frame(inner).pack(fill="x", pady=20)

    def _build_right_col(self):
        # (Update top bar for Status Light and Picker)
        self.right_top = ttk.Frame(self.right_col, style="Panel.TFrame")
        self.right_top.pack(side="top", fill="x")

        # The Status Light (Canvas Circle)
        self.status_canvas = tk.Canvas(self.right_top, width=20, height=20, 
                                     bg=self.theme["panel_bg"], highlightthickness=0)
        self.status_canvas.pack(side="left", padx=10)
        self.light_id = self.status_canvas.create_oval(4, 4, 16, 16, fill="red")

        # Ollama Model Picker
        self.var_model = tk.StringVar()
        self.cmb_model = ttk.Combobox(self.right_top, textvariable=self.var_model, state="readonly")
        self.cmb_model.pack(side="left", fill="x", expand=True, padx=8, pady=10)
        self._refresh_ollama_models()

        # Split right into chat (top half) and schema (bottom)
        self.right_split = ttk.Panedwindow(self.right_col, orient="vertical")
        self.right_split.pack(side="top", fill="both", expand=True)

        self.chat_panel = ttk.Frame(self.right_split)
        self.schema_panel = ttk.Frame(self.right_split)

        self.right_split.add(self.chat_panel, weight=1)
        self.right_split.add(self.schema_panel, weight=1)

        # Chat panel
        chat_header = ttk.Frame(self.chat_panel, style="Panel.TFrame")
        chat_header.pack(side="top", fill="x")
        ttk.Label(chat_header, text="Architect's Voice", style="Small.Mono.TLabel").pack(side="left", padx=10, pady=8)

        self.txt_chat = tk.Text(
            self.chat_panel,
            height=10,
            wrap="word",
            bg="#111",
            fg=self.theme["foreground"],
            insertbackground=self.theme["foreground"],
            font=self.theme["font_mono_small"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["border"],
        )
        self.txt_chat.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 6))

        chat_input = ttk.Frame(self.chat_panel, style="Panel.TFrame")
        chat_input.pack(side="bottom", fill="x")

        self.var_directive = tk.StringVar()
        self.ent_directive = ttk.Entry(chat_input, textvariable=self.var_directive)
        self.ent_directive.pack(side="left", fill="x", expand=True, padx=10, pady=10)
        ttk.Button(chat_input, text="Send", style="Accent.TButton", command=self._stub_send_directive).pack(
            side="left", padx=(0, 10), pady=10
        )

        # Schema panel
        schema_header = ttk.Frame(self.schema_panel, style="Panel.TFrame")
        schema_header.pack(side="top", fill="x")
        ttk.Label(schema_header, text="JSON Node Schema", style="Small.Mono.TLabel").pack(side="left", padx=10, pady=8)
        ttk.Button(schema_header, text="Copy Raw", command=self._copy_schema).pack(side="right", padx=10)

        self.txt_schema = tk.Text(
            self.schema_panel,
            height=10,
            wrap="none",
            bg="#1a1a1a",
            fg="#CEB9A5",
            insertbackground="#CEB9A5",
            font=self.theme["font_mono_small"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=self.theme["border"],
        )
        self.txt_schema.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 10))

    def _refresh_ollama_models(self):
        try:
            models = [m['name'] for m in ollama.list()['models']]
            self.cmb_model['values'] = models
            if models: self.var_model.set(models[0])
        except:
            self.cmb_model['values'] = ["Ollama Offline"]

    def _check_services_loop(self):
        """Poller to update the status light: Red (Offline), Yellow (Idle), Green (Ready)"""
        def check():
            try:
                # Check Ollama status
                ollama.list()
                color = self.theme["success"] # Green
                status_text = f"Online: {self.var_model.get()}"
            except:
                color = self.theme["error"] # Red
                status_text = "Ollama Offline"
            
            self.root.after(0, lambda: self.status_canvas.itemconfig(self.light_id, fill=color))
            self.root.after(0, lambda: self.status_var.set(status_text))
            self.root.after(5000, self._check_services_loop) # Poll every 5s

        threading.Thread(target=check, daemon=True).start()

    # -------------------------------------------------------------------------
    # State + Rendering
    # -------------------------------------------------------------------------

    def _wire_initial_state(self):
        # Seed logs
        self._adv_log("# Welcome to the Gilded Manor.")
        self._chat_log("Architect: The Gilded Manor awaits further expansion. Shall we add a solar or perhaps a dungeon beneath the foundations?")
        self._chat_log("System: UI stub online. All actions are placeholders.")
        self._check_services_loop() # Start the status polling

        # Bind edits to mark dirty
        self.var_title_edit.trace_add("write", lambda *_: self._mark_dirty())
        self.var_atmosphere.trace_add("write", lambda *_: self._mark_dirty())

        # Commit title edit on focus out / enter
        self.ent_title.bind("<Return>", lambda _e: self._commit_room_edits())
        self.ent_title.bind("<FocusOut>", lambda _e: self._commit_room_edits())

        self.cmb_atmos.bind("<<ComboboxSelected>>", lambda _e: self._commit_room_edits())

        # Hidden notes save
        self.txt_hidden.bind("<KeyRelease>", lambda _e: self._commit_hidden_notes())

        # Map click
        self.map_canvas.bind("<Button-1>", self._on_map_click)

    def _render_room(self):
        r = self.world.current_room

        # Header save indicator
        self.btn_save_world.configure(text="Save World" + (" *" if self.is_dirty else ""))

        # Left preview
        self.lbl_room_title_small.configure(text=r.title)
        self.preview_canvas.delete("all")
        # Check for data URL or existing local file in assets
        if r.image_url.startswith("data:image") or os.path.exists(r.image_url):
            self._display_vga_image(self.preview_canvas, r.image_url, "preview")
        else:
            self._draw_image_placeholder(self.preview_canvas, label="ROOM VIEW", subtitle=r.atmosphere)

        # Left map
        self._render_map()

        # Anchor label
        self.lbl_grid_anchor.configure(text=f"Grid Anchor: {r.x}, {r.y}")

        # Center title + image + text
        self.lbl_room_title_huge.configure(text=r.title)
        self.lbl_short_desc.configure(text=r.short_description)

        # Description text
        self._set_text(self.txt_desc, r.description)

        # Exits
        exits_text = " | ".join([e.direction for e in r.exits]) if r.exits else "(none)"
        self.lbl_exits.configure(text=f"— {exits_text} —")

        # VGA Render
        self.vga_canvas.delete("all")
        if r.image_url.startswith("data:image") or os.path.exists(r.image_url):
            self._display_vga_image(self.vga_canvas, r.image_url, "main")
        else:
            self._draw_image_placeholder(self.vga_canvas, label="ATMOSPHERIC RENDER", subtitle=f"{r.title} / {r.focal_point}")
        
        if self.is_scribing:
            self._draw_overlay(self.vga_canvas, "WEAVING ARCHITECTURAL LORE...")
        if self.is_painting:
            self._draw_overlay(self.vga_canvas, "PAINTING VGA CANVAS...")

        # Forge fields
        self.var_title_edit.set(r.title)
        self.var_atmosphere.set(r.atmosphere)

        # Contents chips
        for child in list(self.contents_frame.winfo_children()):
            child.destroy()

        for i, item in enumerate(r.contents):
            b = ttk.Button(self.contents_frame, text=item, command=lambda it=item: self._stub_chip(it))
            b.grid(row=i // 2, column=i % 2, sticky="ew", padx=4, pady=4)

        add_btn = ttk.Button(self.contents_frame, text="+", width=3, command=self._stub_add_content)
        add_btn.grid(row=(len(r.contents) // 2) + 1, column=0, sticky="w", padx=4, pady=4)

        self.contents_frame.columnconfigure(0, weight=1)
        self.contents_frame.columnconfigure(1, weight=1)

        # Hidden notes
        self._set_text(self.txt_hidden, r.hidden_notes)

        # Schema
        self._render_schema()

    def _render_schema(self):
        r = self.world.current_room
        payload = {
            "id": r.id,
            "title": r.title,
            "shortDescription": r.short_description,
            "description": r.description,
            "focalPoint": r.focal_point,
            "atmosphere": r.atmosphere,
            "imageUrl": r.image_url,
            "coordinates": {"x": r.x, "y": r.y, "z": r.z},
            "contents": r.contents,
            "hiddenNotes": r.hidden_notes,
            "exits": [{"direction": e.direction, "targetId": e.target_id} for e in r.exits],
        }
        self._set_text(self.txt_schema, json.dumps(payload, indent=2))

    def _render_map(self):
        # Simple 2D map (x,y) with zoom & scroll region
        c = self.map_canvas
        c.delete("all")

        bg = self.theme["background"]
        border = self.theme["border"]
        accent = self.theme["accent"]
        fg = self.theme["foreground"]

        # Map world coordinates to canvas
        # We draw a grid centered around (0,0)
        cell = int(70 * self.map_zoom)
        pad = int(80 * self.map_zoom)

        # Determine extents from rooms
        xs = [r.x for r in self.world.rooms.values()]
        ys = [r.y for r in self.world.rooms.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        width = (max_x - min_x + 1) * cell + pad * 2
        height = (max_y - min_y + 1) * cell + pad * 2

        # helper
        def to_canvas(rx: int, ry: int):
            # y inverted like the SVG in the React
            cx = pad + (rx - min_x) * cell
            cy = pad + (max_y - ry) * cell
            return cx, cy

        # Background dotted feel
        for gx in range(0, width, max(18, int(22 * self.map_zoom))):
            for gy in range(0, height, max(18, int(22 * self.map_zoom))):
                c.create_oval(gx, gy, gx + 2, gy + 2, fill=border, outline=border, stipple="gray50")

        # Connections
        for room in self.world.rooms.values():
            x1, y1 = to_canvas(room.x, room.y)
            for ex in room.exits:
                target = self.world.rooms.get(ex.target_id)
                if not target:
                    continue
                x2, y2 = to_canvas(target.x, target.y)
                c.create_line(x1, y1, x2, y2, fill=accent, width=max(2, int(2 * self.map_zoom)), stipple="gray50")

        # Nodes
        for room in self.world.rooms.values():
            cx, cy = to_canvas(room.x, room.y)
            is_active = room.id == self.world.current_room_id
            r = max(10, int(12 * self.map_zoom))

            fill = accent if is_active else bg
            outline = accent
            c.create_oval(cx - r, cy - r, cx + r, cy + r, fill=fill, outline=outline, width=3, tags=("node", room.id))

            # Label: first word
            label = room.title.split(" ")[0]
            c.create_text(cx, cy + (r + 12), text=label, fill=fg, font=self.theme["font_mono_small"], tags=("node", room.id))

        c.configure(scrollregion=(0, 0, width, height))

        # Nudge view to keep active room roughly in view
        ar = self.world.current_room
        ax, ay = to_canvas(ar.x, ar.y)
        # Center the active room
        if width > 0 and height > 0:
            c.xview_moveto(max(0.0, (ax - c.winfo_width() / 2) / width))
            c.yview_moveto(max(0.0, (ay - c.winfo_height() / 2) / height))

    # -------------------------------------------------------------------------
    # Drawing primitives
    # -------------------------------------------------------------------------

    def _draw_image_placeholder(self, canvas: tk.Canvas, label: str, subtitle: str = ""):
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        canvas.create_rectangle(0, 0, w, h, fill="#0b0b0b", outline=self.theme["border"], width=1)

        # Simple faux-scanline effect
        step = 6
        for y in range(0, h, step):
            canvas.create_line(0, y, w, y, fill="#111", width=1)

        canvas.create_text(w // 2, h // 2 - 10, text=label, fill=self.theme["foreground"], font=self.theme["font_mono"])
        if subtitle:
            canvas.create_text(w // 2, h // 2 + 18, text=subtitle, fill=self.theme["accent"], font=self.theme["font_mono_small"])

    def _draw_overlay(self, canvas: tk.Canvas, text: str):
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        canvas.create_rectangle(8, 8, w - 8, h - 8, fill="#000", outline=self.theme["accent"], width=2, stipple="gray50")
        canvas.create_text(w // 2, h // 2, text=text, fill="white", font=self.theme["font_mono"])

    def _display_vga_image(self, canvas: tk.Canvas, image_source: str, ref_key: str):
        """Decodes base64 data or loads a local file and renders it to the specified canvas."""
        try:
            if image_source.startswith("data:image"):
                b64_str = image_source.split(",")[1]
                img_data = base64.b64decode(b64_str)
                img = Image.open(io.BytesIO(img_data))
            else:
                # Load directly from the local assets folder
                img = Image.open(image_source)
            
            cw = canvas.winfo_width()
            ch = canvas.winfo_height()
            if cw > 1 and ch > 1:
                img = img.resize((cw, ch), Image.NEAREST)
            
            photo = ImageTk.PhotoImage(img)
            self.img_refs[ref_key] = photo # Maintain reference
            canvas.create_image(0, 0, anchor="nw", image=photo)
        except Exception as e:
            self._draw_image_placeholder(canvas, "IMAGE ERROR", str(e))

    def _set_text(self, widget: tk.Text, value: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)
        widget.configure(state="normal")  # keep editable unless we lock it

    # -------------------------------------------------------------------------
    # Actions (stubbed)
    # -------------------------------------------------------------------------

    def _mark_dirty(self):
        self.is_dirty = True
        self.btn_save_world.configure(text="Save World *")

    def _commit_room_edits(self):
        r = self.world.current_room
        title = self.var_title_edit.get().strip() or r.title
        atmos = self.var_atmosphere.get().strip() or r.atmosphere
        if title != r.title:
            r.title = title
        if atmos != r.atmosphere:
            r.atmosphere = atmos
        self._mark_dirty()
        self._render_room()

    def _commit_hidden_notes(self):
        r = self.world.current_room
        r.hidden_notes = self.txt_hidden.get("1.0", "end").rstrip("\n")
        self._mark_dirty()
        self._render_schema()

    def _travel_by_direction(self, direction: str):
        r = self.world.current_room
        ex = next((e for e in r.exits if e.direction.lower() == direction.lower()), None)
        if not ex:
            self._adv_log(f"You can't go that way ({direction}).")
            return
        self._travel_to(ex.target_id)

    def _travel_to(self, target_id: str):
        if self.world.travel(target_id):
            dest = self.world.current_room
            self._history_log(f"Travelled to {dest.title}")
            self._adv_log(f"> go {target_id}")
            self._adv_log(f"You arrive at the {dest.title}.")
            self.status_var.set(f"Travelled to {dest.title}.")
            self._render_room()
        else:
            self._adv_log("That destination does not exist.")

    def _on_map_click(self, evt):
        # Determine if a node tag was clicked
        items = self.map_canvas.find_overlapping(evt.x, evt.y, evt.x, evt.y)
        for it in items:
            tags = self.map_canvas.gettags(it)
            for t in tags:
                if t in self.world.rooms:
                    self._travel_to(t)
                    return

    def _handle_command(self):
        cmd = self.var_cmd.get().strip()
        if not cmd:
            return
        self.var_cmd.set("")

        low = cmd.lower()
        self._adv_log(f"> {cmd}")

        if low.startswith("go "):
            dir_ = low.split(" ", 1)[1].strip()
            # Accept N/S/E/W/U/D and full names
            lookup = {
                "n": "North",
                "s": "South",
                "e": "East",
                "w": "West",
                "u": "Up",
                "d": "Down",
            }
            dir_name = lookup.get(dir_, dir_.capitalize())
            self._travel_by_direction(dir_name)
            return

        self._adv_log(f"The command \"{cmd}\" echoes through the manor, but nothing happens.")

    def _zoom_in(self):
        self.map_zoom = min(5.0, self.map_zoom + 0.25)
        self._render_map()
        self.status_var.set(f"Map zoom: {self.map_zoom:.2f}")

    def _zoom_out(self):
        self.map_zoom = max(0.5, self.map_zoom - 0.25)
        self._render_map()
        self.status_var.set(f"Map zoom: {self.map_zoom:.2f}")

    def _stub_new(self):
        self.status_var.set("[stub] New world")
        self._chat_log("System: [stub] New world requested.")

    def _stub_open(self):
        path = filedialog.askopenfilename(
            title="Open World JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=os.path.dirname(self.current_world_path) if self.current_world_path else os.getcwd(),
        )
        if not path:
            return
        try:
            w = World.from_file(path)
            if not w.current_room_id or w.current_room_id not in w.rooms:
                raise ValueError("World has no valid start/current room.")
            self.world = w
            self.current_world_path = path
            self.is_dirty = False
            self._history_log(f"Opened World: {os.path.basename(path)}")
            self._chat_log(f"System: Loaded world from {path}")
            self.status_var.set(f"Loaded: {os.path.basename(path)}")
            self._render_room()
        except Exception as e:
            messagebox.showerror("Open failed", f"Could not open world:\n\n{e}")
            self._chat_log(f"System: Open failed: {e}")

    def _stub_save_world(self):
        # Save to current file if known; otherwise prompt.
        path = self.current_world_path
        if not path:
            path = filedialog.asksaveasfilename(
                title="Save World JSON As",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=os.getcwd(),
                initialfile="world.json",
            )
            if not path:
                return
            self.current_world_path = path

        try:
            data = self.world.to_dict()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            self.is_dirty = False
            self.btn_save_world.configure(text="Save World")
            self._history_log(f"Saved World: {os.path.basename(path)}")
            self._chat_log(f"System: World saved to {path}")
            self.status_var.set(f"World saved: {os.path.basename(path)}")
        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save world:\n\n{e}")
            self._chat_log(f"System: Save failed: {e}")

    def _stub_export(self):
        self._chat_log("System: [stub] Export requested.")
        self.status_var.set("Export (stub).")

    def _stub_ai_generate(self):
        """Real Text Generation via Ollama"""
        if not self.var_model.get(): return
        
        self.is_scribing = True
        self._render_room()
        
        def scribe_thread():
            r = self.world.current_room
            prompt = f"Describe a {r.atmosphere} MUD room called {r.title}. Focal point: {r.focal_point}."
            try:
                response = ollama.generate(model=self.var_model.get(), prompt=prompt)
                new_desc = response['response']
                self.root.after(0, lambda: self._finalize_generation(new_desc))
            except Exception as e:
                self.root.after(0, lambda: self._chat_log(f"Architect Error: {str(e)}"))
                self.root.after(0, lambda: setattr(self, 'is_scribing', False))

        threading.Thread(target=scribe_thread, daemon=True).start()

    def _finalize_generation(self, new_text):
        self.world.current_room.description = new_text
        self.is_scribing = False
        self._mark_dirty()
        self._render_room()
        self._chat_log("Architect: The room has been scribed.")

    def _stub_scribe_node(self):
        """Real Image Generation via Stable Diffusion API"""
        r = self.world.current_room
        self.is_painting = True
        self._render_room()
        self.status_var.set("Painting VGA Canvas...")

        def paint_thread():
            url = "http://127.0.0.1:7860/sdapi/v1/txt2img"
            # OG prompt for Sierra style
            prompt = f"90s sierra vga game style, {r.atmosphere} {r.title}, {r.focal_point}, pixel art, dithered, 256 colors, scanlines"
            payload = {
                "prompt": prompt,
                "negative_prompt": "photorealistic, modern, high resolution, 3d, gradient, smooth",
                "steps": 25,
                "width": 640,
                "height": 400,
                "cfg_scale": 7.5
            }
            try:
                response = requests.post(url, json=payload, timeout=60)
                if response.status_code == 200:
                    img_data = response.json()['images'][0]
                    self.root.after(0, lambda: self._finalize_painting(img_data))
                else:
                    raise Exception(f"SD API Status: {response.status_code}")
            except Exception as e:
                self.root.after(0, lambda: self._chat_log(f"Artisan Error: {str(e)}"))
                self.root.after(0, lambda: setattr(self, 'is_painting', False))
                self.root.after(0, self._render_room)

        threading.Thread(target=paint_thread, daemon=True).start()

    def _finalize_painting(self, b64_data):
        # Save a physical copy to a stable per-room cache
        room_id = self.world.current_room.id
        base_dir = os.path.dirname(os.path.abspath(__file__))
        rooms_dir = os.path.join(base_dir, "assets", "rooms")
        os.makedirs(rooms_dir, exist_ok=True)
        asset_path = os.path.join(rooms_dir, f"{room_id}.png")

        with open(asset_path, "wb") as f:
            f.write(base64.b64decode(b64_data))

        self.world.current_room.image_url = asset_path
        self.is_painting = False
        self._mark_dirty()
        self._render_room()
        self._chat_log(f"Artisan: Canvas finalized and locked to {asset_path}.")

    def _stub_send_directive(self):
        text = self.var_directive.get().strip()
        if not text:
            return
        self.var_directive.set("")
        self._chat_log(f"You: {text}")
        self._chat_log("Architect: [stub] Acknowledged. (No model connected.)")
        self.status_var.set("Directive sent (stub).")

    def _stub_chip(self, item: str):
        self.status_var.set(f"[stub] Clicked content: {item}")

    def _stub_add_content(self):
        r = self.world.current_room
        r.contents.append(f"New Item {_safe_int(str(time.time()).split('.')[0][-2:], 0)}")
        self._mark_dirty()
        self._render_room()

    def _history_log(self, action: str):
        self.history.insert(0, {"id": str(time.time()), "action": action, "timestamp": time.strftime("%H:%M:%S")})

    def _adv_log(self, line: str):
        self.txt_adv.insert("end", line + "\n")
        self.txt_adv.see("end")

    def _chat_log(self, line: str):
        self.txt_chat.insert("end", line + "\n\n")
        self.txt_chat.see("end")

    def _copy_schema(self):
        data = self.txt_schema.get("1.0", "end").rstrip("\n")
        self.root.clipboard_clear()
        self.root.clipboard_append(data)
        self.status_var.set("Schema copied to clipboard.")

    def _open_settings(self):
        # Minimal modal stub
        win = tk.Toplevel(self.root)
        win.title("Settings (Stub)")
        win.configure(bg=self.theme["background"])
        win.geometry("420x280")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="Atelier Styles (Stub)", style="Title.TLabel").pack(padx=14, pady=(14, 6), anchor="w")
        ttk.Label(
            win,
            text="This is a stub modal. Later we can wire actual theme overrides.\n\n"
            "For now: uses the Tkinter microservice palette (dark).",
            style="Mono.TLabel",
        ).pack(padx=14, pady=6, anchor="w")

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=14, pady=12)
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")

    # -------------------------------------------------------------------------
    # App loop
    # -------------------------------------------------------------------------

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    IsolateIRLApp().run()






"""Tkinter UI for KleinBOTTLE world-builder.

Handles layout, rendering, event binding, and dialogs.
Delegates all business logic to Backend.
"""

from __future__ import annotations

import io
import json
import os
import base64
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from typing import Optional

from PIL import Image, ImageTk

from theme import Theme
from models import _safe_int


class ScrollableFrame(ttk.Frame):
    """A ttk frame with a canvas+scrollbar interior (vertical)."""

    def __init__(self, parent, theme: Theme, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.theme = theme
        self.canvas = tk.Canvas(self, bg=theme["background"], highlightthickness=0, bd=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.vsb.set)

        self.inner = ttk.Frame(self.canvas)
        self.inner_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")

        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_inner_configure(self, _evt):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, evt):
        self.canvas.itemconfigure(self.inner_id, width=evt.width)

    def _on_mousewheel(self, evt):
        x, y = self.winfo_pointerxy()
        w = self.winfo_containing(x, y)
        if w and (str(w).startswith(str(self.canvas)) or str(w).startswith(str(self.inner))):
            self.canvas.yview_scroll(int(-1 * (evt.delta / 120)), "units")


class WorldBuilderUI:
    """Tkinter-based world-builder UI."""

    def __init__(self, root: tk.Tk, backend, theme: Theme):
        self.root = root
        self.backend = backend
        self.theme = theme
        self.map_zoom = 1.5
        self.img_refs: dict = {}

        self._build_root_layout()
        self.render_room()
        self._wire_initial_state()

    # ----- Status helper -----

    def _status(self, msg: str):
        self.status_var.set(msg)

    # ----- Layout -----

    def _build_root_layout(self):
        # Header
        header = ttk.Frame(self.root, style="Panel.TFrame")
        header.pack(side="top", fill="x")

        header_left = ttk.Frame(header, style="Panel.TFrame")
        header_left.pack(side="left", fill="x", expand=True, padx=10, pady=8)
        ttk.Label(header_left, text="KleinBOTTLE World-Builder", style="Title.TLabel").pack(side="left")

        header_nav = ttk.Frame(header, style="Panel.TFrame")
        header_nav.pack(side="left", padx=18)
        ttk.Button(header_nav, text="New", command=self._on_new).pack(side="left", padx=4)
        ttk.Button(header_nav, text="Open", command=self._on_open).pack(side="left", padx=4)
        self.btn_save = ttk.Button(header_nav, text="Save World", command=self._on_save)
        self.btn_save.pack(side="left", padx=4)
        ttk.Button(header_nav, text="Export", command=self._on_export).pack(side="left", padx=4)

        header_right = ttk.Frame(header, style="Panel.TFrame")
        header_right.pack(side="right", padx=10)
        ttk.Button(header_right, text="Settings", command=self._open_settings).pack(side="right")

        # 3-pane body
        self.body = ttk.Panedwindow(self.root, orient="horizontal")
        self.body.pack(side="top", fill="both", expand=True)

        self.left_col = ttk.Frame(self.body)
        self.center_col = ttk.Frame(self.body)
        self.right_col = ttk.Frame(self.body)

        self.body.add(self.left_col, weight=2)
        self.body.add(self.center_col, weight=5)
        self.body.add(self.right_col, weight=2)

        self._build_left_col()
        self._build_center_col()
        self._build_right_col()

        # Status bar
        status_frame = ttk.Frame(self.root, style="Panel.TFrame")
        status_frame.pack(side="bottom", fill="x")
        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(status_frame, textvariable=self.status_var, style="Small.Mono.TLabel").pack(side="left", padx=10, pady=4)

    def _build_left_col(self):
        # Preview / banner canvas
        preview = ttk.Frame(self.left_col, style="Panel.TFrame")
        preview.pack(side="top", fill="x")

        self.preview_canvas = tk.Canvas(preview, height=140, bg="#111",
                                         highlightthickness=1, highlightbackground=self.theme["border"])
        self.preview_canvas.pack(side="top", fill="x", padx=10, pady=10)

        title_row = ttk.Frame(preview, style="Panel.TFrame")
        title_row.pack(side="top", fill="x", padx=10, pady=(0, 10))

        self.lbl_room_title_small = ttk.Label(title_row, text="", style="Mono.TLabel")
        self.lbl_room_title_small.pack(side="left", fill="x", expand=True)
        ttk.Button(title_row, text="-", width=3, command=self._zoom_out).pack(side="right", padx=(4, 0))
        ttk.Button(title_row, text="+", width=3, command=self._zoom_in).pack(side="right")

        # Map
        map_frame = ttk.Frame(self.left_col)
        map_frame.pack(side="top", fill="both", expand=True)

        self.map_canvas = tk.Canvas(map_frame, bg=self.theme["background"], highlightthickness=0)
        map_vsb = ttk.Scrollbar(map_frame, orient="vertical", command=self.map_canvas.yview)
        map_hsb = ttk.Scrollbar(map_frame, orient="horizontal", command=self.map_canvas.xview)
        self.map_canvas.configure(yscrollcommand=map_vsb.set, xscrollcommand=map_hsb.set)

        self.map_canvas.grid(row=0, column=0, sticky="nsew")
        map_vsb.grid(row=0, column=1, sticky="ns")
        map_hsb.grid(row=1, column=0, sticky="ew")
        map_frame.rowconfigure(0, weight=1)
        map_frame.columnconfigure(0, weight=1)

        # Navigation pad
        nav = ttk.Frame(self.left_col, style="Panel.TFrame")
        nav.pack(side="bottom", fill="x")
        nav_grid = ttk.Frame(nav, style="Panel.TFrame")
        nav_grid.pack(side="top", pady=10)

        dirs = [
            (0, 1, "N", "North"), (2, 1, "S", "South"),
            (1, 2, "E", "East"), (1, 0, "W", "West"),
            (0, 2, "U", "Up"), (2, 0, "D", "Down"),
        ]
        for r, c, label, direction in dirs:
            ttk.Button(nav_grid, text=label, width=4,
                       command=lambda d=direction: self._on_travel(d)).grid(row=r, column=c, padx=4, pady=4)

        ttk.Label(nav_grid, text="", style="Mono.TLabel").grid(row=0, column=0)
        ttk.Label(nav_grid, text="\u2388", style="Huge.TLabel").grid(row=1, column=1, padx=6)
        ttk.Label(nav_grid, text="", style="Mono.TLabel").grid(row=2, column=2)

        self.lbl_grid_anchor = ttk.Label(nav, text="Grid Anchor: 0, 0", style="Small.Mono.TLabel")
        self.lbl_grid_anchor.pack(side="bottom", pady=(0, 10))

    def _build_center_col(self):
        self.center_scroll = ScrollableFrame(self.center_col, self.theme)
        self.center_scroll.pack(fill="both", expand=True)
        inner = self.center_scroll.inner

        # Title block
        title_block = ttk.Frame(inner)
        title_block.pack(fill="x", padx=18, pady=(18, 8))
        self.lbl_room_title_huge = ttk.Label(title_block, text="", style="Huge.TLabel")
        self.lbl_room_title_huge.pack(side="top", anchor="center")
        self.lbl_room_sub = ttk.Label(title_block, text="Scribed Node Location", style="Small.Mono.TLabel")
        self.lbl_room_sub.pack(side="top", pady=(6, 0))

        # VGA canvas
        vga = ttk.Frame(inner, style="Panel.TFrame")
        vga.pack(fill="x", padx=18, pady=10)
        self.vga_canvas = tk.Canvas(vga, height=240, bg="#000",
                                     highlightthickness=2, highlightbackground=self.theme["border"])
        self.vga_canvas.pack(fill="x", padx=12, pady=12)

        # Narrative
        narrative = ttk.Frame(inner)
        narrative.pack(fill="x", padx=18, pady=(8, 10))
        self.lbl_short_desc = ttk.Label(narrative, text="", style="Title.TLabel")
        self.lbl_short_desc.pack(anchor="w", pady=(0, 6))

        self.txt_desc = tk.Text(narrative, height=7, wrap="word", bg="#111",
                                 fg=self.theme["foreground"], insertbackground=self.theme["foreground"],
                                 font=self.theme["font_mono"], relief="flat",
                                 highlightthickness=1, highlightbackground=self.theme["border"])
        self.txt_desc.pack(fill="x")

        # Exits banner
        exits_bar = ttk.Frame(inner, style="Panel.TFrame")
        exits_bar.pack(fill="x", padx=18, pady=10)
        ttk.Label(exits_bar, text="Passages Known", style="Small.Mono.TLabel").pack(side="top", pady=(8, 2))
        self.lbl_exits = ttk.Label(exits_bar, text="\u2014 \u2014", style="Title.TLabel")
        self.lbl_exits.pack(side="top", pady=(0, 8))

        # Forge
        forge = ttk.Frame(inner)
        forge.pack(fill="x", padx=18, pady=(10, 18))
        forge_left = ttk.Frame(forge)
        forge_right = ttk.Frame(forge)
        forge_left.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        forge_right.grid(row=0, column=1, sticky="nsew", padx=(10, 0))
        forge.columnconfigure(0, weight=1)
        forge.columnconfigure(1, weight=1)

        # Contents
        lf_contents = ttk.Labelframe(forge_left, text="Material Contents")
        lf_contents.pack(fill="x", pady=(0, 10))
        self.contents_frame = ttk.Frame(lf_contents, style="Panel.TFrame")
        self.contents_frame.pack(fill="x", padx=8, pady=8)

        # Hidden notes
        lf_hidden = ttk.Labelframe(forge_left, text="DM Private Scripts")
        lf_hidden.pack(fill="both", expand=True)
        self.txt_hidden = tk.Text(lf_hidden, height=6, wrap="word", bg="#111",
                                   fg=self.theme["foreground"], insertbackground=self.theme["foreground"],
                                   font=self.theme["font_mono"], relief="flat",
                                   highlightthickness=1, highlightbackground=self.theme["border"])
        self.txt_hidden.pack(fill="both", expand=True, padx=8, pady=8)

        # Room forge
        lf_forge = ttk.Labelframe(forge_right, text="Room Forge")
        lf_forge.pack(fill="x", pady=(0, 10))

        row1 = ttk.Frame(lf_forge, style="Panel.TFrame")
        row1.pack(fill="x", padx=8, pady=(8, 4))
        self.var_title_edit = tk.StringVar()
        self.ent_title = ttk.Entry(row1, textvariable=self.var_title_edit)
        self.ent_title.pack(side="left", fill="x", expand=True)
        ttk.Button(row1, text="AI", style="Accent.TButton", width=4, command=self._on_ai_generate).pack(side="left", padx=(6, 0))

        row2 = ttk.Frame(lf_forge, style="Panel.TFrame")
        row2.pack(fill="x", padx=8, pady=(4, 8))
        self.var_atmosphere = tk.StringVar()
        self.cmb_atmos = ttk.Combobox(row2, textvariable=self.var_atmosphere,
                                       values=["Dusty", "Sunlit", "Overgrown", "Misty", "Astronomical", "Cold"],
                                       state="readonly")
        self.cmb_atmos.pack(side="left", fill="x", expand=True)
        ttk.Button(row2, text="Scribe Node", style="Accent.TButton", command=self._on_scribe_node).pack(side="left", padx=(6, 0))

        # Adventure sandbox
        lf_adv = ttk.Labelframe(forge_right, text="Adventure Sandbox")
        lf_adv.pack(fill="both", expand=True)
        self.txt_adv = tk.Text(lf_adv, height=8, wrap="word", bg="#000", fg="#00FF41",
                                insertbackground="#00FF41", font=self.theme["font_mono_small"],
                                relief="flat", highlightthickness=1, highlightbackground=self.theme["border"])
        self.txt_adv.pack(fill="both", expand=True, padx=8, pady=(8, 6))

        cmd_row = ttk.Frame(lf_adv, style="Panel.TFrame")
        cmd_row.pack(fill="x", padx=8, pady=(0, 8))
        self.var_cmd = tk.StringVar()
        ttk.Entry(cmd_row, textvariable=self.var_cmd).pack(side="left", fill="x", expand=True)
        ttk.Button(cmd_row, text="Send", style="Accent.TButton", command=self._on_command).pack(side="left", padx=(6, 0))

        ttk.Frame(inner).pack(fill="x", pady=20)

    def _build_right_col(self):
        # Status light + model picker
        top = ttk.Frame(self.right_col, style="Panel.TFrame")
        top.pack(side="top", fill="x")

        self.status_canvas = tk.Canvas(top, width=20, height=20, bg=self.theme["panel_bg"], highlightthickness=0)
        self.status_canvas.pack(side="left", padx=10)
        self.light_id = self.status_canvas.create_oval(4, 4, 16, 16, fill="red")

        self.var_model = tk.StringVar()
        self.cmb_model = ttk.Combobox(top, textvariable=self.var_model, state="readonly")
        self.cmb_model.pack(side="left", fill="x", expand=True, padx=8, pady=10)
        self._refresh_models()

        # Right split: chat + schema (will become Notebook in Phase 2)
        right_split = ttk.Panedwindow(self.right_col, orient="vertical")
        right_split.pack(side="top", fill="both", expand=True)

        chat_panel = ttk.Frame(right_split)
        schema_panel = ttk.Frame(right_split)
        right_split.add(chat_panel, weight=1)
        right_split.add(schema_panel, weight=1)

        # Chat
        chat_header = ttk.Frame(chat_panel, style="Panel.TFrame")
        chat_header.pack(side="top", fill="x")
        ttk.Label(chat_header, text="Architect's Voice", style="Small.Mono.TLabel").pack(side="left", padx=10, pady=8)

        self.txt_chat = tk.Text(chat_panel, height=10, wrap="word", bg="#111",
                                 fg=self.theme["foreground"], insertbackground=self.theme["foreground"],
                                 font=self.theme["font_mono_small"], relief="flat",
                                 highlightthickness=1, highlightbackground=self.theme["border"])
        self.txt_chat.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 6))

        chat_input = ttk.Frame(chat_panel, style="Panel.TFrame")
        chat_input.pack(side="bottom", fill="x")
        self.var_directive = tk.StringVar()
        ttk.Entry(chat_input, textvariable=self.var_directive).pack(side="left", fill="x", expand=True, padx=10, pady=10)
        ttk.Button(chat_input, text="Send", style="Accent.TButton", command=self._on_directive).pack(side="left", padx=(0, 10), pady=10)

        # Schema
        schema_header = ttk.Frame(schema_panel, style="Panel.TFrame")
        schema_header.pack(side="top", fill="x")
        ttk.Label(schema_header, text="JSON Node Schema", style="Small.Mono.TLabel").pack(side="left", padx=10, pady=8)
        ttk.Button(schema_header, text="Copy Raw", command=self._copy_schema).pack(side="right", padx=10)

        self.txt_schema = tk.Text(schema_panel, height=10, wrap="none", bg="#1a1a1a", fg="#CEB9A5",
                                   insertbackground="#CEB9A5", font=self.theme["font_mono_small"],
                                   relief="flat", highlightthickness=1, highlightbackground=self.theme["border"])
        self.txt_schema.pack(side="top", fill="both", expand=True, padx=10, pady=(0, 10))

    # ----- Initial state -----

    def _wire_initial_state(self):
        self._adv_log("# Welcome to the world-builder.")
        self._chat_log("System: KleinBOTTLE online. Use the Architect's Voice to direct world creation.")

        self.var_title_edit.trace_add("write", lambda *_: self.backend.mark_dirty())
        self.var_atmosphere.trace_add("write", lambda *_: self.backend.mark_dirty())
        self.ent_title.bind("<Return>", lambda _: self._commit_edits())
        self.ent_title.bind("<FocusOut>", lambda _: self._commit_edits())
        self.cmb_atmos.bind("<<ComboboxSelected>>", lambda _: self._commit_edits())
        self.txt_hidden.bind("<KeyRelease>", lambda _: self._commit_hidden())
        self.map_canvas.bind("<Button-1>", self._on_map_click)

        # Start service polling
        self.backend.start_polling(self._on_service_status)

    # ----- Rendering -----

    def render_room(self):
        b = self.backend
        r = b.world.current_room

        self.btn_save.configure(text="Save World" + (" *" if b.is_dirty else ""))
        self.lbl_room_title_small.configure(text=r.title)

        # Preview canvas
        self._render_image_on_canvas(self.preview_canvas, r.image_url, "preview",
                                      placeholder_label="ROOM VIEW", placeholder_sub=r.atmosphere)

        self._render_map()
        self.lbl_grid_anchor.configure(text=f"Grid Anchor: {r.x}, {r.y}")

        # Center
        self.lbl_room_title_huge.configure(text=r.title)
        self.lbl_short_desc.configure(text=r.short_description)
        self._set_text(self.txt_desc, r.description)

        exits_text = " | ".join([e.direction for e in r.exits]) if r.exits else "(none)"
        self.lbl_exits.configure(text=f"\u2014 {exits_text} \u2014")

        # VGA render
        self._render_image_on_canvas(self.vga_canvas, r.image_url, "main",
                                      placeholder_label="ATMOSPHERIC RENDER",
                                      placeholder_sub=f"{r.title} / {r.focal_point}")
        if b.is_scribing:
            self._draw_overlay(self.vga_canvas, "WEAVING ARCHITECTURAL LORE...")
        if b.is_painting:
            self._draw_overlay(self.vga_canvas, "PAINTING VGA CANVAS...")

        # Forge
        self.var_title_edit.set(r.title)
        self.var_atmosphere.set(r.atmosphere)

        # Contents chips
        for child in list(self.contents_frame.winfo_children()):
            child.destroy()
        for i, item in enumerate(r.contents):
            ttk.Button(self.contents_frame, text=item,
                       command=lambda it=item: self._status(f"Content: {it}")).grid(
                row=i // 2, column=i % 2, sticky="ew", padx=4, pady=4)
        ttk.Button(self.contents_frame, text="+", width=3, command=self._on_add_content).grid(
            row=(len(r.contents) // 2) + 1, column=0, sticky="w", padx=4, pady=4)
        self.contents_frame.columnconfigure(0, weight=1)
        self.contents_frame.columnconfigure(1, weight=1)

        self._set_text(self.txt_hidden, r.hidden_notes)
        self._render_schema()

    def _render_schema(self):
        r = self.backend.world.current_room
        payload = {
            "id": r.id, "title": r.title, "shortDescription": r.short_description,
            "description": r.description, "focalPoint": r.focal_point,
            "atmosphere": r.atmosphere, "imageUrl": r.image_url,
            "coordinates": {"x": r.x, "y": r.y, "z": r.z},
            "contents": r.contents, "hiddenNotes": r.hidden_notes,
            "exits": [{"direction": e.direction, "targetId": e.target_id} for e in r.exits],
        }
        self._set_text(self.txt_schema, json.dumps(payload, indent=2))

    def _render_map(self):
        c = self.map_canvas
        c.delete("all")
        world = self.backend.world

        accent = self.theme["accent"]
        bg = self.theme["background"]
        border = self.theme["border"]
        fg = self.theme["foreground"]

        cell = int(70 * self.map_zoom)
        pad = int(80 * self.map_zoom)

        xs = [r.x for r in world.rooms.values()]
        ys = [r.y for r in world.rooms.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)

        width = (max_x - min_x + 1) * cell + pad * 2
        height = (max_y - min_y + 1) * cell + pad * 2

        def to_canvas(rx, ry):
            return pad + (rx - min_x) * cell, pad + (max_y - ry) * cell

        # Dotted grid
        step = max(18, int(22 * self.map_zoom))
        for gx in range(0, width, step):
            for gy in range(0, height, step):
                c.create_oval(gx, gy, gx + 2, gy + 2, fill=border, outline=border, stipple="gray50")

        # Connections
        for room in world.rooms.values():
            x1, y1 = to_canvas(room.x, room.y)
            for ex in room.exits:
                target = world.rooms.get(ex.target_id)
                if target:
                    x2, y2 = to_canvas(target.x, target.y)
                    c.create_line(x1, y1, x2, y2, fill=accent,
                                  width=max(2, int(2 * self.map_zoom)), stipple="gray50")

        # Nodes
        for room in world.rooms.values():
            cx, cy = to_canvas(room.x, room.y)
            is_active = room.id == world.current_room_id
            r = max(10, int(12 * self.map_zoom))
            c.create_oval(cx - r, cy - r, cx + r, cy + r,
                          fill=accent if is_active else bg, outline=accent, width=3,
                          tags=("node", room.id))
            c.create_text(cx, cy + r + 12, text=room.title.split(" ")[0],
                          fill=fg, font=self.theme["font_mono_small"], tags=("node", room.id))

        c.configure(scrollregion=(0, 0, width, height))

        # Center on active room
        ar = world.current_room
        ax, ay = to_canvas(ar.x, ar.y)
        if width > 0 and height > 0:
            c.xview_moveto(max(0.0, (ax - c.winfo_width() / 2) / width))
            c.yview_moveto(max(0.0, (ay - c.winfo_height() / 2) / height))

    # ----- Drawing helpers -----

    def _render_image_on_canvas(self, canvas: tk.Canvas, image_url: str, ref_key: str,
                                 placeholder_label: str = "IMAGE", placeholder_sub: str = ""):
        """Render an image or placeholder on a canvas. De-duplicated from monolith."""
        canvas.delete("all")
        if self._is_displayable(image_url):
            self._display_vga_image(canvas, image_url, ref_key)
        else:
            self._draw_placeholder(canvas, placeholder_label, placeholder_sub)

    @staticmethod
    def _is_displayable(url: str) -> bool:
        return bool(url) and (url.startswith("data:image") or os.path.exists(url))

    def _draw_placeholder(self, canvas: tk.Canvas, label: str, subtitle: str = ""):
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        canvas.create_rectangle(0, 0, w, h, fill="#0b0b0b", outline=self.theme["border"], width=1)
        for y in range(0, h, 6):
            canvas.create_line(0, y, w, y, fill="#111", width=1)
        canvas.create_text(w // 2, h // 2 - 10, text=label, fill=self.theme["foreground"], font=self.theme["font_mono"])
        if subtitle:
            canvas.create_text(w // 2, h // 2 + 18, text=subtitle, fill=self.theme["accent"], font=self.theme["font_mono_small"])

    def _draw_overlay(self, canvas: tk.Canvas, text: str):
        w = max(1, canvas.winfo_width())
        h = max(1, canvas.winfo_height())
        canvas.create_rectangle(8, 8, w - 8, h - 8, fill="#000", outline=self.theme["accent"], width=2, stipple="gray50")
        canvas.create_text(w // 2, h // 2, text=text, fill="white", font=self.theme["font_mono"])

    def _display_vga_image(self, canvas: tk.Canvas, source: str, ref_key: str):
        try:
            if source.startswith("data:image"):
                img = Image.open(io.BytesIO(base64.b64decode(source.split(",")[1])))
            else:
                img = Image.open(source)
            cw, ch = canvas.winfo_width(), canvas.winfo_height()
            if cw > 1 and ch > 1:
                img = img.resize((cw, ch), Image.NEAREST)
            photo = ImageTk.PhotoImage(img)
            self.img_refs[ref_key] = photo
            canvas.create_image(0, 0, anchor="nw", image=photo)
        except Exception as e:
            self._draw_placeholder(canvas, "IMAGE ERROR", str(e))

    def _set_text(self, widget: tk.Text, value: str):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", value)

    # ----- Logging -----

    def _adv_log(self, line: str):
        self.txt_adv.insert("end", line + "\n")
        self.txt_adv.see("end")

    def _chat_log(self, line: str):
        self.txt_chat.insert("end", line + "\n\n")
        self.txt_chat.see("end")

    # ----- Event handlers -----

    def _refresh_models(self):
        models = self.backend.refresh_ollama_models()
        self.cmb_model["values"] = models or ["Ollama Offline"]
        if models:
            self.var_model.set(models[0])

    def _on_service_status(self, online: bool, status_text: str):
        color = self.theme["success"] if online else self.theme["error"]
        self.status_canvas.itemconfig(self.light_id, fill=color)
        self._status(status_text)

    def _commit_edits(self):
        self.backend.commit_room_edits(self.var_title_edit.get().strip(), self.var_atmosphere.get().strip())
        self.render_room()

    def _commit_hidden(self):
        self.backend.commit_hidden_notes(self.txt_hidden.get("1.0", "end").rstrip("\n"))
        self._render_schema()

    def _on_travel(self, direction: str):
        err = self.backend.travel_by_direction(direction)
        if err:
            self._adv_log(err)
        else:
            dest = self.backend.world.current_room
            self._adv_log(f"> go {direction.lower()}")
            self._adv_log(f"You arrive at the {dest.title}.")
            self._status(f"Travelled to {dest.title}.")
            self.render_room()

    def _on_map_click(self, evt):
        items = self.map_canvas.find_overlapping(evt.x, evt.y, evt.x, evt.y)
        for it in items:
            for t in self.map_canvas.gettags(it):
                if t in self.backend.world.rooms:
                    err = self.backend.travel_to(t)
                    if not err:
                        dest = self.backend.world.current_room
                        self._adv_log(f"> go {t}")
                        self._adv_log(f"You arrive at the {dest.title}.")
                        self._status(f"Travelled to {dest.title}.")
                        self.render_room()
                    return

    def _on_command(self):
        cmd = self.var_cmd.get().strip()
        if not cmd:
            return
        self.var_cmd.set("")
        lines = self.backend.handle_command(cmd)
        for line in lines:
            self._adv_log(line)
        # Re-render if travel happened
        if any("arrive" in l.lower() for l in lines):
            self.render_room()

    def _zoom_in(self):
        self.map_zoom = min(5.0, self.map_zoom + 0.25)
        self._render_map()
        self._status(f"Map zoom: {self.map_zoom:.2f}")

    def _zoom_out(self):
        self.map_zoom = max(0.5, self.map_zoom - 0.25)
        self._render_map()
        self._status(f"Map zoom: {self.map_zoom:.2f}")

    def _on_add_content(self):
        self.backend.add_content(f"New Item {_safe_int(str(time.time()).split('.')[0][-2:], 0)}")
        self.render_room()

    # ----- File ops -----

    def _on_new(self):
        self._status("[stub] New world")
        self._chat_log("System: [stub] New world requested.")

    def _on_open(self):
        path = filedialog.askopenfilename(
            title="Open World JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialdir=os.path.dirname(self.backend.current_world_path) if self.backend.current_world_path else os.getcwd(),
        )
        if not path:
            return
        try:
            self.backend.open_world(path)
            self._chat_log(f"System: Loaded world from {path}")
            self._status(f"Loaded: {os.path.basename(path)}")
            self.render_room()
        except Exception as e:
            messagebox.showerror("Open failed", f"Could not open world:\n\n{e}")
            self._chat_log(f"System: Open failed: {e}")

    def _on_save(self):
        path = self.backend.current_world_path
        if not path:
            path = filedialog.asksaveasfilename(
                title="Save World JSON As", defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
                initialdir=os.getcwd(), initialfile="world.json",
            )
            if not path:
                return
        try:
            saved = self.backend.save_world(path)
            self.btn_save.configure(text="Save World")
            self._chat_log(f"System: World saved to {saved}")
            self._status(f"World saved: {os.path.basename(saved)}")
        except Exception as e:
            messagebox.showerror("Save failed", f"Could not save world:\n\n{e}")
            self._chat_log(f"System: Save failed: {e}")

    def _on_export(self):
        self._chat_log("System: [stub] Export requested.")
        self._status("Export (stub).")

    # ----- AI -----

    def _on_ai_generate(self):
        model = self.var_model.get()
        if not model or model == "Ollama Offline":
            return
        r = self.backend.world.current_room
        prompt = f"Describe a {r.atmosphere} MUD room called {r.title}. Focal point: {r.focal_point}."

        self.backend.generate_text(
            model, prompt,
            on_success=self._on_generation_done,
            on_error=lambda e: self._chat_log(f"Architect Error: {e}"),
        )
        self.render_room()

    def _on_generation_done(self, new_text: str):
        self.backend.world.current_room.description = new_text
        self.backend.is_scribing = False
        self.backend.mark_dirty()
        self.render_room()
        self._chat_log("Architect: The room has been scribed.")

    def _on_scribe_node(self):
        def on_img_success(img_bytes: bytes):
            path = self.backend.save_room_image(img_bytes)
            self.backend.is_painting = False
            self.render_room()
            self._chat_log(f"Artisan: Canvas finalized and locked to {path}.")

        def on_img_error(err: str):
            self._chat_log(f"Artisan Error: {err}")
            self.backend.is_painting = False
            self.render_room()

        self.backend.generate_room_image(on_success=on_img_success, on_error=on_img_error)
        self._status("Painting VGA Canvas...")
        self.render_room()

    # ----- Directive (stub for now, wired in Phase 3) -----

    def _on_directive(self):
        text = self.var_directive.get().strip()
        if not text:
            return
        self.var_directive.set("")
        self._chat_log(f"You: {text}")
        self._chat_log("Architect: [stub] Acknowledged. (No model connected.)")
        self._status("Directive sent (stub).")

    # ----- Schema -----

    def _copy_schema(self):
        data = self.txt_schema.get("1.0", "end").rstrip("\n")
        self.root.clipboard_clear()
        self.root.clipboard_append(data)
        self._status("Schema copied to clipboard.")

    # ----- Settings -----

    def _open_settings(self):
        win = tk.Toplevel(self.root)
        win.title("Settings (Stub)")
        win.configure(bg=self.theme["background"])
        win.geometry("420x280")
        win.transient(self.root)
        win.grab_set()

        ttk.Label(win, text="KleinBOTTLE Settings (Stub)", style="Title.TLabel").pack(padx=14, pady=(14, 6), anchor="w")
        ttk.Label(win, text="Settings will be expanded in Phase 1.\nUsing dark microservice palette.",
                  style="Mono.TLabel").pack(padx=14, pady=6, anchor="w")

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=14, pady=12)
        ttk.Button(btns, text="Close", command=win.destroy).pack(side="right")

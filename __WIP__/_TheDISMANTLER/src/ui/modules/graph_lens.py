"""
Graph Lens – Entity relationship view.
Visualizes relationships between code objects (classes, methods, variables).
Stateless UI: all data comes through BackendEngine.
"""
import tkinter as tk
from tkinter import ttk
from theme import THEME


class GraphLens(tk.Frame):
    """
    Entity browser panel.
    Displays a filterable list of code entities (classes, functions,
    methods, variables) and their relationships.
    """

    def __init__(self, parent, on_entity_select=None, **kwargs):
        super().__init__(parent, bg=THEME["bg2"], **kwargs)
        self._on_entity_select = on_entity_select
        self._entities = []
        self._edges = []

        # ── header ──────────────────────────────────────────
        tk.Label(
            self,
            text="GRAPH",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
        ).pack(fill="x", padx=6, pady=(6, 2))

        # ── filter ──────────────────────────────────────────
        filter_frame = tk.Frame(self, bg=THEME["bg2"])
        filter_frame.pack(fill="x", padx=6, pady=(0, 4))

        tk.Label(
            filter_frame,
            text="Filter:",
            bg=THEME["bg2"],
            fg=THEME["fg"],
            font=THEME["font_interface_small"],
        ).pack(side="left")

        self.type_filter = ttk.Combobox(
            filter_frame,
            values=["All", "class", "function", "method", "variable"],
            state="readonly",
            width=12,
            font=THEME["font_interface_small"],
        )
        self.type_filter.set("All")
        self.type_filter.pack(side="left", padx=4)
        self.type_filter.bind("<<ComboboxSelected>>", lambda e: self._apply_filter())

        # ── entity list ─────────────────────────────────────
        list_frame = tk.Frame(self, bg=THEME["bg2"])
        list_frame.pack(fill="both", expand=True, padx=6, pady=(0, 2))

        self.entity_list = tk.Listbox(
            list_frame,
            bg=THEME["bg3"],
            fg=THEME["fg"],
            font=THEME["font_code_small"],
            selectbackground=THEME["accent"],
            selectforeground="#ffffff",
            relief="flat",
            activestyle="none",
        )
        scrollbar = tk.Scrollbar(list_frame, command=self.entity_list.yview)
        self.entity_list.config(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.entity_list.pack(side="left", fill="both", expand=True)

        self.entity_list.bind("<<ListboxSelect>>", self._on_entity_click)

        # ── relationship display ────────────────────────────
        tk.Label(
            self,
            text="RELATIONSHIPS",
            bg=THEME["bg2"],
            fg=THEME["accent"],
            font=THEME["font_interface_bold"],
        ).pack(fill="x", padx=6, pady=(4, 2))

        self.rel_list = tk.Listbox(
            self,
            bg=THEME["bg3"],
            fg=THEME["fg_dim"],
            font=THEME["font_code_small"],
            height=6,
            relief="flat",
            activestyle="none",
        )
        self.rel_list.pack(fill="x", padx=6, pady=(0, 6))

    # ── public API ──────────────────────────────────────────

    def load_entities(self, entities, edges=None):
        """
        Populate the graph from entity and edge lists.
        entities: [{name, kind, line, parent}, ...]
        edges:    [{source, target, kind}, ...]
        """
        self._entities = entities or []
        self._edges = edges or []

        # Update filter options
        types = sorted(set(e["kind"] for e in self._entities))
        self.type_filter["values"] = ["All"] + types

        self._apply_filter()

    def clear(self):
        """Clear all entities and edges."""
        self._entities = []
        self._edges = []
        self.entity_list.delete(0, "end")
        self.rel_list.delete(0, "end")

    # ── internal ────────────────────────────────────────────

    def _apply_filter(self):
        """Refilter the entity list based on the current filter."""
        self.entity_list.delete(0, "end")
        selected_type = self.type_filter.get()

        for entity in self._entities:
            if selected_type != "All" and entity["kind"] != selected_type:
                continue

            parent = f"  ({entity['parent']})" if entity.get("parent") else ""
            display = f"[{entity['kind'][:3].upper()}]  {entity['name']}{parent}  L{entity.get('line', '?')}"
            self.entity_list.insert("end", display)

    def _on_entity_click(self, _event):
        """Show relationships for the selected entity."""
        sel = self.entity_list.curselection()
        if not sel:
            return

        # Find the entity by index in the filtered list
        idx = sel[0]
        selected_type = self.type_filter.get()
        filtered = [
            e for e in self._entities
            if selected_type == "All" or e["kind"] == selected_type
        ]

        if idx >= len(filtered):
            return

        entity = filtered[idx]

        # Show relationships
        self.rel_list.delete(0, "end")
        for edge in self._edges:
            if edge["source"] == entity["name"]:
                self.rel_list.insert("end", f"  -> {edge['kind']} -> {edge['target']}")
            elif edge["target"] == entity["name"]:
                self.rel_list.insert("end", f"  <- {edge['kind']} <- {edge['source']}")

        if not self.rel_list.size():
            self.rel_list.insert("end", "  (no relationships)")

        if self._on_entity_select:
            self._on_entity_select(entity)

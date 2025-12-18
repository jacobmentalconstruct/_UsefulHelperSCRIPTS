import os
import queue
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import tkinter as tk
from tkinter import ttk

from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# USER CONFIGURATION: DEFAULTS
# ==============================================================================
DEFAULT_EXCLUDED_FOLDERS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    ".mypy_cache",
    "_logs",
    "dist",
    "build",
    ".vscode",
    ".idea",
    "target",
    "out",
    "bin",
    "obj",
    "Debug",
    "Release",
    "logs",
}
# ==============================================================================


@service_metadata(
    name="ExplorerWidget",
    version="1.0.0",
    description="A standalone file system tree viewer widget.",
    tags=["ui", "filesystem", "widget"],
    capabilities=["ui:gui", "filesystem:read"],
)
class ExplorerWidgetMS(ttk.Frame):
    """
    A standalone file system tree viewer.
    """

    GLYPH_CHECKED = "[X]"
    GLYPH_UNCHECKED = "[ ]"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config_data: Dict[str, Any] = config or {}
        parent = self.config_data.get("parent")
        super().__init__(parent)

        self.root_path: Path = Path(
            self.config_data.get("root_path", ".")
        ).resolve()
        self.use_defaults: bool = self.config_data.get(
            "use_default_exclusions", True
        )

        # GUI coordination
        self.gui_queue: queue.Queue = queue.Queue()
        self.folder_item_states: Dict[str, str] = {}
        self.state_lock = threading.RLock()

        self._setup_styles()
        self._build_ui()
        self.process_gui_queue()
        self.refresh_tree()

    # ------------------------------------------------------------------ UI SETUP

    def _setup_styles(self) -> None:
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(
            "Explorer.Treeview",
            background="#252526",
            foreground="lightgray",
            fieldbackground="#252526",
            borderwidth=0,
            font=("Consolas", 10),
        )
        style.map(
            "Explorer.Treeview",
            background=[("selected", "#007ACC")],
            foreground=[("selected", "white")],
        )

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(
            self,
            show="tree",
            columns=("size",),
            selectmode="none",
            style="Explorer.Treeview",
        )
        self.tree.column("size", width=80, anchor="e")

        ysb = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        xsb = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)

        self.tree.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        ysb.grid(row=0, column=1, sticky="ns")
        xsb.grid(row=1, column=0, sticky="ew")

        self.tree.bind("<ButtonRelease-1>", self._on_click)

    # ----------------------------------------------------------------- SERVICE API

    @service_endpoint(
        inputs={},
        outputs={},
        description="Rescans the directory and refreshes the tree view.",
        tags=["ui", "refresh"],
        side_effects=["filesystem:read", "ui:update"],
    )
    def refresh_tree(self) -> None:
        # Clear the tree view
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Reset state
        with self.state_lock:
            self.folder_item_states.clear()
            self.folder_item_states[str(self.root_path)] = "checked"

        # Build a flat list of tree items for insertion
        root_id = str(self.root_path)
        tree_data: List[Dict[str, Any]] = [
            {
                "parent": "",
                "iid": root_id,
                "text": f" {self.root_path.name} (Root)",
                "open": True,
            }
        ]

        self._scan_recursive(self.root_path, root_id, tree_data)

        # Insert into Treeview
        for item in tree_data:
            self.tree.insert(
                item["parent"],
                "end",
                iid=item["iid"],
                text=item["text"],
                open=item.get("open", False),
            )
            self.tree.set(item["iid"], "size", "...")

        # Update glyphs
        self._refresh_visuals(root_id)

        # Kick off background size calculation (currently stubbed)
        threading.Thread(
            target=self._calc_sizes_thread,
            args=(root_id,),
            daemon=True,
        ).start()

    # ----------------------------------------------------------------- INTERNALS

    def _scan_recursive(
        self, current_path: Path, parent_id: str, data_list: List[Dict[str, Any]]
    ) -> None:
        try:
            items = sorted(
                current_path.iterdir(),
                key=lambda x: (not x.is_dir(), x.name.lower()),
            )
            for item in items:
                if not item.is_dir():
                    continue

                path_str = str(item.resolve())

                state = "checked"
                if self.use_defaults and item.name in DEFAULT_EXCLUDED_FOLDERS:
                    state = "unchecked"

                with self.state_lock:
                    self.folder_item_states[path_str] = state

                data_list.append(
                    {"parent": parent_id, "iid": path_str, "text": f" {item.name}"}
                )
                self._scan_recursive(item, path_str, data_list)
        except (PermissionError, OSError):
            # Skip directories we can't read
            pass

    def _on_click(self, event: tk.Event) -> None:
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return

        with self.state_lock:
            curr = self.folder_item_states.get(item_id, "unchecked")
            self.folder_item_states[item_id] = (
                "checked" if curr == "unchecked" else "unchecked"
            )

        self._refresh_visuals(str(self.root_path))

    def _refresh_visuals(self, start_node: str) -> None:
        def _update(node_id: str) -> None:
            if not self.tree.exists(node_id):
                return

            with self.state_lock:
                state = self.folder_item_states.get(node_id, "unchecked")

            glyph = (
                self.GLYPH_CHECKED if state == "checked" else self.GLYPH_UNCHECKED
            )

            name = Path(node_id).name
            if node_id == str(self.root_path):
                name += " (Root)"

            self.tree.item(node_id, text=f"{glyph} {name}")

            for child in self.tree.get_children(node_id):
                _update(child)

        _update(start_node)

    def _calc_sizes_thread(self, root_id: str) -> None:
        """
        Background worker for calculating folder sizes.

        Currently a stub so that the thread exits cleanly without errors.
        You can later extend this to walk the filesystem and push
        size updates via self.gui_queue.
        """
        return

    # ----------------------------------------------------------------- SERVICE API

    @service_endpoint(
        inputs={},
        outputs={"selected_paths": "List[str]"},
        description="Returns a list of currently checked folder paths.",
        tags=["ui", "read"],
        side_effects=["ui:read"],
    )
    def get_selected_paths(self) -> List[str]:
        selected: List[str] = []
        with self.state_lock:
            for path, state in self.folder_item_states.items():
                if state == "checked":
                    selected.append(path)
        return selected

    # ------------------------------------------------------------------ GUI QUEUE

    def process_gui_queue(self) -> None:
        while not self.gui_queue.empty():
            try:
                callback = self.gui_queue.get_nowait()
            except queue.Empty:
                break
            else:
                try:
                    callback()
                except Exception:
                    # In production you might want logging here.
                    pass

        # Schedule next pump
        self.after(100, self.process_gui_queue)


if __name__ == "__main__":
    # Simple harness for manual testing.
    root = tk.Tk()
    root.title("ExplorerWidgetMS Test Harness")

    widget = ExplorerWidgetMS({"parent": root, "root_path": os.getcwd()})
    widget.pack(fill="both", expand=True)

    root.mainloop()

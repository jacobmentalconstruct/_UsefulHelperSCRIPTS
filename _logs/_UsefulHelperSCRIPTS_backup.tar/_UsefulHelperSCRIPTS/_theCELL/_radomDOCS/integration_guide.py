"""
Integration Guide: Enhanced Cell Identity System
================================================

This guide shows how to integrate the enhanced cell identity system
into your existing _theCELL project with minimal disruption.

STEP-BY-STEP INTEGRATION
"""

# =============================================================================
# STEP 1: Modify src/backend.py
# =============================================================================

"""
1. Import the new identity system at the top of backend.py:
"""

# Add to imports in src/backend.py
from enhanced_cell_identity import CellIdentity, CellRegistry

"""
2. Modify the Backend.__init__ method:
"""

class Backend:
    def __init__(self, 
                 registry: CellRegistry,  # NEW: Pass in global registry
                 memory_path: str = None, 
                 db_path: str = None, 
                 db_dir: str = "_db",
                 cell_id: str = None,      # MODIFIED: Now optional
                 parent_id: str = None,
                 cell_name: str = None):   # MODIFIED: Now optional
        
        # NEW: Create identity with auto-generation if not provided
        self.identity = CellIdentity(cell_id, cell_name, parent_id)
        
        # MODIFIED: Use identity properties
        self.cell_id = self.identity.cell_id
        self.cell_name = self.identity.cell_name
        self.parent_id = self.identity.parent_id
        
        # NEW: Store registry reference
        self.registry = registry
        
        # BACKWARD COMPATIBLE: Keep children_ids for now
        # But it will be managed through identity/registry
        self.children_ids = list(self.identity.children.keys())
        
        # Register this cell globally
        self.registry.register_cell(self.identity)
        
        # ... rest of existing __init__ code unchanged ...
        
        if db_path is None:
            db_path = os.path.join(db_dir, "app_internal.db")
        
        self.db_path = db_path
        # ... etc ...


# =============================================================================
# STEP 2: Add Cell Rename Method to Backend
# =============================================================================

"""
Add these methods to the Backend class:
"""

class Backend:
    # ... existing methods ...
    
    def rename_cell(self, new_name: str):
        """
        User-facing method to rename this cell.
        Propagates change through registry to all references.
        """
        old_name = self.cell_name
        self.registry.rename_cell(self.cell_id, new_name)
        
        # Update local reference
        self.cell_name = self.identity.cell_name
        
        # Emit signal for UI update
        self.bus.emit("cell_renamed", {
            "cell_id": self.cell_id,
            "old_name": old_name,
            "new_name": new_name
        })
        
        # Update window title if needed
        self.bus.emit("update_window_title", f"_theCELL [{self.cell_name}]")
    
    def get_family_tree(self) -> dict:
        """Returns detailed family relationship data."""
        return {
            "identity": self.identity.to_dict(),
            "lineage": self.registry.get_lineage(self.cell_id),
            "children": self.registry.get_children(self.cell_id),
            "descendants": list(self.registry.get_descendants(self.cell_id))
        }
    
    def close_cell(self):
        """Clean up when cell window is closed."""
        self.registry.unregister_cell(self.cell_id)
        # Any other cleanup...


# =============================================================================
# STEP 3: Modify src/app.py
# =============================================================================

"""
Update the main() function to create and pass the global registry:
"""

def main():
    from enhanced_cell_identity import CellRegistry
    
    # NEW: Create global cell registry (singleton for the application)
    global_registry = CellRegistry()
    
    # Initialize the logic hub with registry
    backend = Backend(registry=global_registry)  # NEW: Pass registry
    
    # Load persisted theme preference (default Dark)
    theme = (backend.get_setting('theme_preference') or 'Dark').strip().title()
    if theme not in ('Dark', 'Light'):
        theme = 'Dark'
    
    # Initialize the Mother Ship (Shell)
    shell = TkinterAppShellMS({
        "title": f"_theCELL [{backend.cell_name}]",  # MODIFIED: Show name in title
        "geometry": "1000x800",
        "theme": theme
    })
    
    # Dock the UI into the shell
    app_ui = CELL_UI(shell, backend)

    # --- Global Orchestration State ---
    # MODIFIED: Use registry instead of manual dict
    
    def broadcast_registry_update():
        """Informs all cells of the current list of available targets."""
        active_cells = global_registry.get_all_cells()
        active_data = {
            cid: {"id": cid, "name": identity.cell_name}
            for cid, identity in active_cells.items()
        }
        
        for cid, identity in active_cells.items():
            cell_backend = _get_backend_for_cell(cid)  # Helper method
            if cell_backend:
                cell_backend.bus.emit("update_registry", active_data)

    def register_cell_orchestration(target_backend):
        """Wires a backend into the global recursive and nexus pipelines."""
        
        # 1. Handle Recursive Spawning
        def on_spawn_request(data):
            print(f"[System] Spawning child from: {data.get('spawn_timestamp')}")
            
            # MODIFIED: Use identity system
            parent_identity = target_backend.identity
            
            # Create child window
            child_win = shell.spawn_window(
                title=f"_theCELL [Child of {parent_identity.cell_name}]",
                geometry="900x700"
            )
            
            # MODIFIED: Let identity system generate unique ID and name
            unique_session_id = None  # Will be auto-generated
            child_backend = Backend(
                registry=global_registry,  # NEW: Pass same registry
                memory_path=f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jsonl",
                cell_id=None,  # Auto-generate
                parent_id=parent_identity.cell_id,
                cell_name=None  # Will default to "Child of ParentName"
            )
            
            # Parent-child relationship is auto-managed by registry
            
            # Shell Proxy for Child Window
            # ... rest of existing code ...


# =============================================================================
# STEP 4: Add Rename UI to src/ui.py
# =============================================================================

"""
Add a rename dialog to the CELL_UI class:
"""

class CELL_UI:
    # ... existing code ...
    
    def _open_rename_dialog(self):
        """Opens a dialog to rename the current cell."""
        from tkinter import simpledialog
        
        new_name = simpledialog.askstring(
            "Rename Cell",
            f"Enter new name for '{self.backend.cell_name}':",
            initialvalue=self.backend.cell_name,
            parent=self.shell.root
        )
        
        if new_name and new_name.strip():
            self.backend.rename_cell(new_name.strip())
    
    def _register_signals(self):
        """Connects UI to the nervous system."""
        if hasattr(self.backend, 'bus'):
            self.backend.bus.subscribe("log_append", self._on_log_append)
            self.backend.bus.subscribe("process_complete", self._on_process_complete)
            self.backend.bus.subscribe("update_registry", self._update_nexus_list)
            self.backend.bus.subscribe("push_to_nexus", self._handle_incoming_push)
            self.backend.bus.subscribe("theme_updated", self.refresh_theme)
            
            # NEW: Handle cell rename events
            self.backend.bus.subscribe("cell_renamed", self._on_cell_renamed)
            self.backend.bus.subscribe("update_window_title", self._update_window_title)
    
    def _on_cell_renamed(self, data):
        """Handles cell rename events."""
        # Update any UI elements that display the cell name
        if hasattr(self, 'cell_name_label'):
            self.cell_name_label.config(text=data['new_name'])
    
    def _update_window_title(self, new_title):
        """Updates the window title."""
        self.shell.root.title(new_title)
    
    def _build_context_menu(self):
        """Build right-click context menu."""
        self.context_menu = tk.Menu(self.shell.root, tearoff=0)
        
        # ... existing menu items ...
        
        # NEW: Add rename option
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Rename Cell", command=self._open_rename_dialog)
        self.context_menu.add_command(label="View Family Tree", command=self._show_family_tree)
    
    def _show_family_tree(self):
        """Shows a dialog with the cell's family relationships."""
        import json
        from tkinter import messagebox
        
        tree_data = self.backend.get_family_tree()
        formatted = json.dumps(tree_data, indent=2)
        
        messagebox.showinfo(
            "Cell Family Tree",
            formatted,
            parent=self.shell.root
        )


# =============================================================================
# STEP 5: Add Menu Bar Rename Option
# =============================================================================

"""
In your existing menu creation code, add a rename option:
"""

def _build_menu_bar(self):
    """Creates the application menu bar."""
    menubar = tk.Menu(self.shell.root)
    self.shell.root.config(menu=menubar)
    
    # Cell menu
    cell_menu = tk.Menu(menubar, tearoff=0)
    menubar.add_cascade(label="Cell", menu=cell_menu)
    
    cell_menu.add_command(label="Rename Cell...", command=self._open_rename_dialog)
    cell_menu.add_command(label="View Family Tree...", command=self._show_family_tree)
    cell_menu.add_separator()
    cell_menu.add_command(label="Close Cell", command=self.shell.root.destroy)
    
    # ... rest of menu ...


# =============================================================================
# STEP 6: Update Nexus Dropdown to Show Names
# =============================================================================

"""
Modify the nexus update handler to display cell names instead of IDs:
"""

def _update_nexus_list(self, active_cells_data):
    """
    Updates the Nexus dropdown with currently active cells.
    
    active_cells_data format:
    {
        "cell_id": {"id": "cell_id", "name": "Cell Name"},
        ...
    }
    """
    # Filter out self
    targets = [
        f"{data['name']} ({cid})"
        for cid, data in active_cells_data.items()
        if cid != self.session_id
    ]
    
    self.nexus_cb['values'] = ["Select..."] + targets
    
    # Store mapping for lookup
    self._nexus_id_map = {
        f"{data['name']} ({cid})": cid
        for cid, data in active_cells_data.items()
    }

def _on_push_to_nexus(self):
    """Push result content to the selected target cell."""
    display_name = self.nexus_var.get()
    if display_name in ["Select...", ""]:
        return
    
    # Lookup actual cell ID from display name
    target_id = self._nexus_id_map.get(display_name)
    if not target_id:
        return
    
    content = self.result_text.get("1.0", "end-1c")
    self.backend.push_to_target(target_id, content)


# =============================================================================
# STEP 7: Add Cell Name Display in UI
# =============================================================================

"""
Add a visual indicator of the cell's name and lineage:
"""

def _add_cell_info_bar(self):
    """Adds an info bar showing cell identity."""
    info_bar = tk.Frame(self.container, bg=self.colors.get('panel_bg'))
    info_bar.pack(fill='x', padx=10, pady=(5, 0))
    
    # Cell name (clickable to rename)
    self.cell_name_label = tk.Label(
        info_bar,
        text=self.backend.cell_name,
        bg=self.colors.get('panel_bg'),
        fg=self.colors.get('accent'),
        font=("Segoe UI", 10, "bold"),
        cursor="hand2"
    )
    self.cell_name_label.pack(side='left', padx=5)
    self.cell_name_label.bind("<Button-1>", lambda e: self._open_rename_dialog())
    
    # Cell ID (smaller, grayed out)
    id_label = tk.Label(
        info_bar,
        text=f"({self.backend.cell_id})",
        bg=self.colors.get('panel_bg'),
        fg=self.colors.get('foreground'),
        font=("Segoe UI", 8)
    )
    id_label.pack(side='left')
    
    # Parent info (if applicable)
    if self.backend.parent_id:
        parent_identity = self.backend.registry.get_cell(self.backend.parent_id)
        if parent_identity:
            parent_label = tk.Label(
                info_bar,
                text=f"← Child of: {parent_identity.cell_name}",
                bg=self.colors.get('panel_bg'),
                fg=self.colors.get('foreground'),
                font=("Segoe UI", 8, "italic")
            )
            parent_label.pack(side='left', padx=(10, 0))


# =============================================================================
# STEP 8: Testing Checklist
# =============================================================================

"""
After integration, test these scenarios:

1. ✓ Create root cell - verify unique ID generated
2. ✓ Rename root cell - verify name updates in:
   - Window title
   - Cell info bar
   - Registry
3. ✓ Spawn child cell - verify:
   - Child has unique ID
   - Child's default name reflects parent
   - Parent's children list includes child
   - Child's parent_id points to parent
4. ✓ Rename parent cell - verify:
   - Child's record of parent name updates
   - No errors in console
5. ✓ Spawn grandchild - verify:
   - 3-generation lineage tracks correctly
   - get_lineage() returns proper chain
6. ✓ Close child cell - verify:
   - Registry removes child
   - Parent's children list updates
7. ✓ Nexus dropdown - verify:
   - Shows cell names (not just IDs)
   - Only shows other cells (not self)
   - Updates when cells renamed
8. ✓ Export registry - verify JSON structure correct
"""


# =============================================================================
# STEP 9: Optional Enhancements
# =============================================================================

"""
Consider these future enhancements:

1. PERSISTENCE
   - Save registry to disk on changes
   - Restore on app restart
   - Store in SQLite alongside other app data

2. VISUALIZATION
   - Create a tree view widget showing cell hierarchy
   - Show active cells in a graph
   - Highlight parent-child relationships

3. SEARCH
   - Search cells by name
   - Find cells by relationship
   - Filter by lineage depth

4. CELL METADATA
   - Add tags/labels to cells
   - Track cell purpose/specialization
   - Store creation time, activity stats

5. SMART NAMING
   - Auto-suggest names based on cell's first inference
   - Learn naming patterns from user
   - Detect duplicate names
"""

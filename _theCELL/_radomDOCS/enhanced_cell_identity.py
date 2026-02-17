"""
Enhanced Cell Identity System for _theCELL
==========================================

This module provides the architecture for:
1. Unique ID generation at cell instantiation
2. User-renameable cell names with defaults
3. Bidirectional parent-child relationship tracking
4. Name change propagation across the cell registry
"""

import uuid
from typing import Dict, List, Optional, Set
from datetime import datetime
import json
import threading


class CellIdentity:
    """Manages unique identity and relationships for a single cell."""
    
    def __init__(self, cell_id: str = None, cell_name: str = None, parent_id: str = None):
        # Unique identifier - generated if not provided
        self.cell_id: str = cell_id or self._generate_unique_id()
        
        # Human-readable name - defaults to ID-based name if not provided
        self.cell_name: str = cell_name or self._generate_default_name()
        
        # Relationship tracking
        self.parent_id: Optional[str] = parent_id
        self.children: Dict[str, str] = {}  # {child_id: child_name}
        
        # Metadata
        self.created_at: str = datetime.now().isoformat()
        self.renamed_at: Optional[str] = None
        
    def _generate_unique_id(self) -> str:
        """Generates a unique, collision-resistant cell ID."""
        # Format: cell_<timestamp>_<uuid_segment>
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        uuid_segment = uuid.uuid4().hex[:8]
        return f"cell_{timestamp}_{uuid_segment}"
    
    def _generate_default_name(self) -> str:
        """Generates a default name based on the cell ID."""
        # Extract the last 8 chars for readability
        short_id = self.cell_id.split('_')[-1]
        return f"Cell-{short_id.upper()}"
    
    def rename(self, new_name: str) -> tuple[str, str]:
        """
        Renames the cell and returns (old_name, new_name) for propagation.
        """
        old_name = self.cell_name
        self.cell_name = new_name
        self.renamed_at = datetime.now().isoformat()
        return old_name, new_name
    
    def add_child(self, child_id: str, child_name: str):
        """Records a child cell."""
        self.children[child_id] = child_name
    
    def update_child_name(self, child_id: str, new_name: str):
        """Updates a child's name in this parent's record."""
        if child_id in self.children:
            self.children[child_id] = new_name
    
    def to_dict(self) -> dict:
        """Serializes identity to dictionary."""
        return {
            "cell_id": self.cell_id,
            "cell_name": self.cell_name,
            "parent_id": self.parent_id,
            "children": self.children,
            "created_at": self.created_at,
            "renamed_at": self.renamed_at
        }


class CellRegistry:
    """
    Global registry that tracks all active cells and manages name propagation.
    This is the "Nexus" for cell-to-cell identity awareness.
    """
    
    def __init__(self):
        self._cells: Dict[str, CellIdentity] = {}  # {cell_id: CellIdentity}
        self._lock = threading.Lock()
        self._change_listeners: List[callable] = []  # For UI updates
        
    def register_cell(self, identity: CellIdentity) -> None:
        """Registers a new cell in the global registry."""
        with self._lock:
            self._cells[identity.cell_id] = identity
            
            # If this cell has a parent, update parent's children list
            if identity.parent_id and identity.parent_id in self._cells:
                parent = self._cells[identity.parent_id]
                parent.add_child(identity.cell_id, identity.cell_name)
            
            self._notify_listeners("cell_registered", identity)
    
    def unregister_cell(self, cell_id: str) -> None:
        """Removes a cell from the registry (on cell close)."""
        with self._lock:
            if cell_id in self._cells:
                identity = self._cells[cell_id]
                
                # Notify parent of child removal
                if identity.parent_id and identity.parent_id in self._cells:
                    parent = self._cells[identity.parent_id]
                    if cell_id in parent.children:
                        del parent.children[cell_id]
                
                del self._cells[cell_id]
                self._notify_listeners("cell_unregistered", identity)
    
    def rename_cell(self, cell_id: str, new_name: str) -> None:
        """
        Renames a cell and propagates the change to all references.
        This is the core propagation mechanism.
        """
        with self._lock:
            if cell_id not in self._cells:
                return
            
            identity = self._cells[cell_id]
            old_name, new_name = identity.rename(new_name)
            
            # Propagate to parent
            if identity.parent_id and identity.parent_id in self._cells:
                parent = self._cells[identity.parent_id]
                parent.update_child_name(cell_id, new_name)
            
            # Propagate to all children
            for child_id in identity.children.keys():
                if child_id in self._cells:
                    # Children might display parent name in their UI
                    # Emit a signal they can listen to
                    pass
            
            # Notify all listeners of the name change
            self._notify_listeners("cell_renamed", {
                "cell_id": cell_id,
                "old_name": old_name,
                "new_name": new_name
            })
    
    def get_cell(self, cell_id: str) -> Optional[CellIdentity]:
        """Retrieves a cell's identity by ID."""
        with self._lock:
            return self._cells.get(cell_id)
    
    def get_all_cells(self) -> Dict[str, CellIdentity]:
        """Returns a copy of all registered cells."""
        with self._lock:
            return self._cells.copy()
    
    def get_children(self, cell_id: str) -> Dict[str, str]:
        """Returns all children of a given cell."""
        with self._lock:
            if cell_id in self._cells:
                return self._cells[cell_id].children.copy()
            return {}
    
    def get_lineage(self, cell_id: str) -> List[str]:
        """
        Returns the full lineage from root to this cell.
        Format: [root_id, ..., parent_id, cell_id]
        """
        lineage = []
        current_id = cell_id
        
        with self._lock:
            while current_id and current_id in self._cells:
                lineage.insert(0, current_id)
                current_id = self._cells[current_id].parent_id
        
        return lineage
    
    def get_descendants(self, cell_id: str) -> Set[str]:
        """
        Returns all descendant cell IDs recursively.
        """
        descendants = set()
        
        def _recurse(cid: str):
            if cid in self._cells:
                for child_id in self._cells[cid].children.keys():
                    descendants.add(child_id)
                    _recurse(child_id)
        
        with self._lock:
            _recurse(cell_id)
        
        return descendants
    
    def add_change_listener(self, listener: callable):
        """Register a callback for registry changes."""
        self._change_listeners.append(listener)
    
    def _notify_listeners(self, event_type: str, data):
        """Notifies all listeners of a registry change."""
        for listener in self._change_listeners:
            try:
                listener(event_type, data)
            except Exception as e:
                print(f"Listener error: {e}")
    
    def export_registry(self) -> str:
        """Exports the entire registry as JSON."""
        with self._lock:
            data = {
                "cells": {cid: identity.to_dict() for cid, identity in self._cells.items()},
                "timestamp": datetime.now().isoformat()
            }
            return json.dumps(data, indent=2)


# =============================================================================
# Integration Example for Backend Class
# =============================================================================

class EnhancedBackend:
    """
    Example of how to integrate the identity system into your existing Backend class.
    """
    
    def __init__(self, 
                 registry: CellRegistry,
                 cell_id: str = None,
                 cell_name: str = None,
                 parent_id: str = None,
                 **kwargs):
        
        # Create identity
        self.identity = CellIdentity(cell_id, cell_name, parent_id)
        
        # Convenience accessors (backward compatible)
        self.cell_id = self.identity.cell_id
        self.cell_name = self.identity.cell_name
        self.parent_id = self.identity.parent_id
        
        # Register in global registry
        self.registry = registry
        self.registry.register_cell(self.identity)
        
        # ... rest of your existing Backend init ...
    
    def rename_cell(self, new_name: str):
        """User-facing method to rename this cell."""
        self.registry.rename_cell(self.cell_id, new_name)
        # Update local reference
        self.cell_name = self.identity.cell_name
    
    def spawn_child(self, inherited_context: str = "") -> 'EnhancedBackend':
        """
        Enhanced spawning that properly tracks relationships.
        """
        # Generate child identity
        child_id = None  # Will auto-generate
        child_name = f"Child of {self.cell_name}"
        
        # Create child backend
        child_backend = EnhancedBackend(
            registry=self.registry,
            cell_id=child_id,
            cell_name=child_name,
            parent_id=self.cell_id
        )
        
        # Parent's children list is auto-updated via registry
        
        return child_backend
    
    def get_family_tree(self) -> dict:
        """Returns a visualization of this cell's family relationships."""
        lineage = self.registry.get_lineage(self.cell_id)
        children = self.registry.get_children(self.cell_id)
        descendants = self.registry.get_descendants(self.cell_id)
        
        return {
            "cell_id": self.cell_id,
            "cell_name": self.cell_name,
            "lineage": lineage,
            "direct_children": children,
            "all_descendants": list(descendants)
        }
    
    def close(self):
        """Clean up when cell is destroyed."""
        self.registry.unregister_cell(self.cell_id)


# =============================================================================
# UI Integration Example
# =============================================================================

def create_rename_dialog(parent_window, backend: EnhancedBackend):
    """
    Example tkinter dialog for renaming a cell.
    This would integrate with your existing CELL_UI class.
    """
    import tkinter as tk
    from tkinter import simpledialog
    
    def rename_cell_callback():
        new_name = simpledialog.askstring(
            "Rename Cell",
            f"Enter new name for {backend.cell_name}:",
            initialvalue=backend.cell_name,
            parent=parent_window
        )
        
        if new_name and new_name.strip():
            backend.rename_cell(new_name.strip())
            # UI will be updated via signal bus
    
    return rename_cell_callback


# =============================================================================
# Signal Bus Integration
# =============================================================================

def integrate_with_signal_bus(registry: CellRegistry, signal_bus):
    """
    Connects the registry to your existing SignalBusMS for event propagation.
    """
    
    def on_registry_change(event_type: str, data):
        """Broadcasts registry changes through the signal bus."""
        signal_bus.emit(f"registry_{event_type}", data)
    
    registry.add_change_listener(on_registry_change)


# =============================================================================
# Usage Example
# =============================================================================

if __name__ == "__main__":
    # Create global registry (singleton in your app.py)
    global_registry = CellRegistry()
    
    # Create root cell
    root_cell = EnhancedBackend(
        registry=global_registry,
        cell_name="Root Cognition"
    )
    
    print(f"Root Cell: {root_cell.cell_id} | Name: {root_cell.cell_name}")
    
    # Spawn children
    child1 = root_cell.spawn_child()
    child2 = root_cell.spawn_child()
    
    print(f"Child 1: {child1.cell_id} | Name: {child1.cell_name}")
    print(f"Child 2: {child2.cell_id} | Name: {child2.cell_name}")
    
    # Spawn grandchild
    grandchild = child1.spawn_child()
    print(f"Grandchild: {grandchild.cell_id} | Name: {grandchild.cell_name}")
    
    # Show family tree
    print("\nRoot's Family Tree:")
    print(json.dumps(root_cell.get_family_tree(), indent=2))
    
    # Rename child
    print("\n--- Renaming Child 1 ---")
    child1.rename_cell("Memory Specialist")
    
    # Check propagation
    print(f"Child 1 new name: {child1.cell_name}")
    print(f"Root's children: {global_registry.get_children(root_cell.cell_id)}")
    print(f"Grandchild's parent: {grandchild.parent_id}")
    
    # Export registry
    print("\n--- Full Registry ---")
    print(global_registry.export_registry())

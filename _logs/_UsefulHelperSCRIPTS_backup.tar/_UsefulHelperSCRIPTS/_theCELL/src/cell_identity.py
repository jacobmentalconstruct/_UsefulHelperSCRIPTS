"""
Cell Identity Management System for _theCELL
============================================

This module provides identity and relationship tracking for the cognitive cell
architecture. Each cell has a unique ID, user-renameable name, and maintains
bidirectional parent-child relationships with automatic name propagation.

Classes:
    CellIdentity: Manages a single cell's identity and relationships
    CellRegistry: Global registry coordinating all cells with name propagation

Author: Jacob Lambert
License: MIT
"""

import uuid
import threading
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime


class CellIdentity:
    """
    Represents the identity and relationship data for a single cognitive cell.
    
    Each cell has:
    - A unique, collision-resistant ID (auto-generated if not provided)
    - A human-readable name (auto-generated default, user-renameable)
    - Parent cell reference (if spawned from another cell)
    - Children cell references (if this cell has spawned others)
    - Creation and rename timestamps
    
    Attributes:
        cell_id (str): Unique identifier for this cell
        cell_name (str): Human-readable name
        parent_id (Optional[str]): ID of parent cell, None if root
        children (Dict[str, str]): Map of child_id -> child_name
        created_at (str): ISO timestamp of creation
        renamed_at (Optional[str]): ISO timestamp of last rename, None if never renamed
    """
    
    def __init__(self, 
                 cell_id: str = None, 
                 cell_name: str = None, 
                 parent_id: str = None):
        """
        Initialize a cell identity.
        
        Args:
            cell_id: Unique ID (auto-generated if None)
            cell_name: Display name (auto-generated default if None)
            parent_id: Parent cell ID (None for root cells)
        """
        # Generate unique ID if not provided
        self.cell_id: str = cell_id if cell_id else self._generate_unique_id()
        
        # Generate default name if not provided
        self.cell_name: str = cell_name if cell_name else self._generate_default_name()
        
        # Relationship tracking
        self.parent_id: Optional[str] = parent_id
        self.children: Dict[str, str] = {}  # {child_id: child_name}
        
        # Metadata
        self.created_at: str = datetime.now().isoformat()
        self.renamed_at: Optional[str] = None
    
    def _generate_unique_id(self) -> str:
        """
        Generates a unique, collision-resistant cell ID.
        
        Format: cell_YYYYMMDDHHmmSS_<8-char-uuid>
        Example: cell_20260217033045_a1b2c3d4
        
        Returns:
            Unique cell identifier string
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        uuid_segment = uuid.uuid4().hex[:8]
        return f"cell_{timestamp}_{uuid_segment}"
    
    def _generate_default_name(self) -> str:
        """
        Generates a human-readable default name from the cell ID.
        
        Extracts the last 8 characters of the ID for readability.
        Example: "Cell-A1B2C3D4"
        
        Returns:
            Default display name string
        """
        short_id = self.cell_id.split('_')[-1]
        return f"Cell-{short_id.upper()}"
    
    def rename(self, new_name: str) -> Tuple[str, str]:
        """
        Renames the cell and records the timestamp.
        
        Args:
            new_name: New display name for the cell
            
        Returns:
            Tuple of (old_name, new_name) for propagation tracking
        """
        old_name = self.cell_name
        self.cell_name = new_name.strip()
        self.renamed_at = datetime.now().isoformat()
        return old_name, new_name
    
    def add_child(self, child_id: str, child_name: str) -> None:
        """
        Records a child cell in this parent's registry.
        
        Args:
            child_id: Unique ID of child cell
            child_name: Display name of child cell
        """
        self.children[child_id] = child_name
    
    def remove_child(self, child_id: str) -> None:
        """
        Removes a child cell from this parent's registry.
        
        Args:
            child_id: ID of child cell to remove
        """
        if child_id in self.children:
            del self.children[child_id]
    
    def update_child_name(self, child_id: str, new_name: str) -> None:
        """
        Updates a child's name in this parent's record.
        
        Called automatically when a child cell is renamed.
        
        Args:
            child_id: ID of child cell
            new_name: Updated name of child cell
        """
        if child_id in self.children:
            self.children[child_id] = new_name
    
    def to_dict(self) -> dict:
        """
        Serializes identity to dictionary format.
        
        Useful for persistence, debugging, and export.
        
        Returns:
            Dictionary representation of this cell's identity
        """
        return {
            "cell_id": self.cell_id,
            "cell_name": self.cell_name,
            "parent_id": self.parent_id,
            "children": self.children.copy(),
            "created_at": self.created_at,
            "renamed_at": self.renamed_at
        }
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        parent_str = f"parent={self.parent_id}" if self.parent_id else "root"
        children_count = len(self.children)
        return f"CellIdentity({self.cell_name!r}, id={self.cell_id}, {parent_str}, children={children_count})"


class CellRegistry:
    """
    Global registry that tracks all active cells and manages name propagation.
    
    This is the coordination layer that:
    - Maintains the master list of all active cells
    - Enforces parent-child relationship consistency
    - Propagates name changes bidirectionally
    - Provides lineage and descendant queries
    - Thread-safe for concurrent cell operations
    
    The registry should be created once as a singleton in app.py and passed
    to all Backend instances.
    
    Attributes:
        _cells (Dict[str, CellIdentity]): Master registry of all cells
        _lock (threading.Lock): Ensures thread-safe operations
        _change_listeners (List[callable]): Callbacks for registry events
    """
    
    def __init__(self):
        """Initialize an empty cell registry."""
        self._cells: Dict[str, CellIdentity] = {}
        self._lock = threading.Lock()
        self._change_listeners: List[callable] = []
    
    def register_cell(self, identity: CellIdentity) -> None:
        """
        Registers a new cell in the global registry.
        
        Automatically updates parent's children list if parent exists.
        Notifies listeners of the registration.
        
        Args:
            identity: CellIdentity instance to register
        """
        with self._lock:
            self._cells[identity.cell_id] = identity
            
            # If this cell has a parent, update parent's children list
            if identity.parent_id and identity.parent_id in self._cells:
                parent = self._cells[identity.parent_id]
                parent.add_child(identity.cell_id, identity.cell_name)
            
            self._notify_listeners("cell_registered", identity)
    
    def unregister_cell(self, cell_id: str) -> None:
        """
        Removes a cell from the registry (called when cell window closes).
        
        Automatically removes cell from parent's children list.
        Notifies listeners of the removal.
        
        Args:
            cell_id: ID of cell to unregister
        """
        with self._lock:
            if cell_id not in self._cells:
                return
            
            identity = self._cells[cell_id]
            
            # Notify parent of child removal
            if identity.parent_id and identity.parent_id in self._cells:
                parent = self._cells[identity.parent_id]
                parent.remove_child(cell_id)
            
            # Remove from registry
            del self._cells[cell_id]
            self._notify_listeners("cell_unregistered", identity)
    
    def rename_cell(self, cell_id: str, new_name: str) -> None:
        """
        Renames a cell and propagates the change to all references.
        
        This is the core propagation mechanism:
        1. Renames the cell itself
        2. Updates parent's record of this child's name
        3. Notifies all listeners so UIs can update
        
        Args:
            cell_id: ID of cell to rename
            new_name: New display name
        """
        with self._lock:
            if cell_id not in self._cells:
                return
            
            identity = self._cells[cell_id]
            old_name, new_name = identity.rename(new_name)
            
            # Propagate to parent's children list
            if identity.parent_id and identity.parent_id in self._cells:
                parent = self._cells[identity.parent_id]
                parent.update_child_name(cell_id, new_name)
            
            # Notify all listeners of the name change
            self._notify_listeners("cell_renamed", {
                "cell_id": cell_id,
                "old_name": old_name,
                "new_name": new_name,
                "identity": identity
            })
    
    def get_cell(self, cell_id: str) -> Optional[CellIdentity]:
        """
        Retrieves a cell's identity by ID.
        
        Args:
            cell_id: ID of cell to retrieve
            
        Returns:
            CellIdentity instance or None if not found
        """
        with self._lock:
            return self._cells.get(cell_id)
    
    def get_all_cells(self) -> Dict[str, CellIdentity]:
        """
        Returns a copy of all registered cells.
        
        Safe to iterate over without holding the lock.
        
        Returns:
            Dictionary mapping cell_id -> CellIdentity
        """
        with self._lock:
            return self._cells.copy()
    
    def get_children(self, cell_id: str) -> Dict[str, str]:
        """
        Returns all direct children of a given cell.
        
        Args:
            cell_id: ID of parent cell
            
        Returns:
            Dictionary mapping child_id -> child_name (empty dict if no children)
        """
        with self._lock:
            if cell_id in self._cells:
                return self._cells[cell_id].children.copy()
            return {}
    
    def get_lineage(self, cell_id: str) -> List[str]:
        """
        Returns the full lineage from root to this cell.
        
        Walks up the parent chain to build the ancestry.
        
        Args:
            cell_id: ID of cell to get lineage for
            
        Returns:
            List of cell IDs from root to current cell
            Example: [root_id, parent_id, grandparent_id, cell_id]
        """
        lineage = []
        current_id = cell_id
        
        with self._lock:
            # Walk up the parent chain
            while current_id and current_id in self._cells:
                lineage.insert(0, current_id)
                current_id = self._cells[current_id].parent_id
        
        return lineage
    
    def get_descendants(self, cell_id: str) -> Set[str]:
        """
        Returns all descendant cell IDs recursively.
        
        Includes children, grandchildren, great-grandchildren, etc.
        
        Args:
            cell_id: ID of ancestor cell
            
        Returns:
            Set of all descendant cell IDs (empty set if no descendants)
        """
        descendants = set()
        
        def _recurse(cid: str):
            """Recursive helper to walk down the tree."""
            if cid in self._cells:
                for child_id in self._cells[cid].children.keys():
                    descendants.add(child_id)
                    _recurse(child_id)
        
        with self._lock:
            _recurse(cell_id)
        
        return descendants
    
    def get_all_roots(self) -> List[str]:
        """
        Returns IDs of all root cells (cells with no parent).
        
        Useful for displaying cell hierarchies or finding orphaned trees.
        
        Returns:
            List of root cell IDs
        """
        with self._lock:
            return [
                cid for cid, identity in self._cells.items()
                if identity.parent_id is None
            ]
    
    def cell_exists(self, cell_id: str) -> bool:
        """
        Checks if a cell ID exists in the registry.
        
        Args:
            cell_id: ID to check
            
        Returns:
            True if cell exists, False otherwise
        """
        with self._lock:
            return cell_id in self._cells
    
    def add_change_listener(self, listener: callable) -> None:
        """
        Registers a callback for registry change events.
        
        Listener signature: listener(event_type: str, data: any)
        
        Events emitted:
        - "cell_registered": data is CellIdentity
        - "cell_unregistered": data is CellIdentity
        - "cell_renamed": data is dict with cell_id, old_name, new_name
        
        Args:
            listener: Callback function to register
        """
        self._change_listeners.append(listener)
    
    def remove_change_listener(self, listener: callable) -> None:
        """
        Unregisters a change listener callback.
        
        Args:
            listener: Callback function to remove
        """
        if listener in self._change_listeners:
            self._change_listeners.remove(listener)
    
    def _notify_listeners(self, event_type: str, data) -> None:
        """
        Notifies all registered listeners of a registry change.
        
        Called internally when registry state changes.
        Listeners are called outside the lock to avoid deadlocks.
        
        Args:
            event_type: Type of event ("cell_registered", etc.)
            data: Event-specific data
        """
        # Make a copy of listeners to iterate safely
        listeners = self._change_listeners.copy()
        
        for listener in listeners:
            try:
                listener(event_type, data)
            except Exception as e:
                # Don't let listener errors crash the registry
                print(f"[CellRegistry] Listener error in {listener}: {e}")
    
    def export_registry(self) -> dict:
        """
        Exports the entire registry state as a dictionary.
        
        Useful for debugging, persistence, or analysis.
        
        Returns:
            Dictionary with registry state:
            {
                "cells": {cell_id: identity_dict, ...},
                "timestamp": ISO timestamp,
                "total_cells": count,
                "root_cells": [root_ids]
            }
        """
        with self._lock:
            return {
                "cells": {
                    cid: identity.to_dict() 
                    for cid, identity in self._cells.items()
                },
                "timestamp": datetime.now().isoformat(),
                "total_cells": len(self._cells),
                "root_cells": self.get_all_roots()
            }
    
    def get_statistics(self) -> dict:
        """
        Returns registry statistics for monitoring.
        
        Returns:
            Dictionary with statistics:
            {
                "total_cells": count,
                "root_cells": count,
                "max_depth": int,
                "average_children": float
            }
        """
        with self._lock:
            total = len(self._cells)
            roots = len(self.get_all_roots())
            
            # Calculate max depth
            max_depth = 0
            for cell_id in self._cells.keys():
                depth = len(self.get_lineage(cell_id)) - 1
                max_depth = max(max_depth, depth)
            
            # Calculate average children per cell
            total_children = sum(
                len(identity.children) 
                for identity in self._cells.values()
            )
            avg_children = total_children / total if total > 0 else 0
            
            return {
                "total_cells": total,
                "root_cells": roots,
                "max_depth": max_depth,
                "average_children": round(avg_children, 2)
            }
    
    def __len__(self) -> int:
        """Returns the number of registered cells."""
        with self._lock:
            return len(self._cells)
    
    def __contains__(self, cell_id: str) -> bool:
        """Checks if a cell ID exists (supports 'in' operator)."""
        return self.cell_exists(cell_id)
    
    def __repr__(self) -> str:
        """String representation for debugging."""
        stats = self.get_statistics()
        return (
            f"CellRegistry(cells={stats['total_cells']}, "
            f"roots={stats['root_cells']}, "
            f"max_depth={stats['max_depth']})"
        )

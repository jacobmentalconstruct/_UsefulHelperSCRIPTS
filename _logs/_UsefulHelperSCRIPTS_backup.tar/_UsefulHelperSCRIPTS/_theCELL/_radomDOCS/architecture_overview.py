"""
Enhanced Cell Identity System - Architecture Overview
=====================================================

ASCII ARCHITECTURE DIAGRAM
==========================

                         ┌─────────────────────────────┐
                         │   CellRegistry (Singleton)   │
                         │                             │
                         │  • Tracks all active cells  │
                         │  • Manages relationships    │
                         │  • Propagates name changes  │
                         └──────────────┬──────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    │                   │                   │
            ┌───────▼────────┐  ┌──────▼───────┐  ┌───────▼────────┐
            │  CellIdentity  │  │ CellIdentity │  │  CellIdentity  │
            │   (Root Cell)  │  │  (Child 1)   │  │  (Child 2)     │
            │                │  │              │  │                │
            │ ID: cell_abc   │  │ ID: cell_def │  │ ID: cell_ghi   │
            │ Name: "Root"   │  │ Name: "Mem"  │  │ Name: "Reason" │
            │ Parent: None   │  │ Parent: abc  │  │ Parent: abc    │
            │ Children:      │  │ Children:    │  │ Children:      │
            │  - cell_def    │  │  - cell_jkl  │  │   []           │
            │  - cell_ghi    │  │              │  │                │
            └────────────────┘  └──────┬───────┘  └────────────────┘
                                       │
                               ┌───────▼────────┐
                               │  CellIdentity  │
                               │  (Grandchild)  │
                               │                │
                               │ ID: cell_jkl   │
                               │ Name: "Store"  │
                               │ Parent: def    │
                               │ Children: []   │
                               └────────────────┘


NAME PROPAGATION FLOW
=====================

Step 1: User renames Child 1 from "Mem" to "Memory Specialist"
    │
    ├─> CellIdentity.rename("Memory Specialist")
    │       └─> Returns: ("Mem", "Memory Specialist")
    │
    ├─> CellRegistry.rename_cell(cell_def, "Memory Specialist")
    │       ├─> Updates Cell's own identity
    │       ├─> Finds Parent (cell_abc)
    │       │       └─> Updates parent.children["cell_def"] = "Memory Specialist"
    │       └─> Emits "cell_renamed" signal to all listeners
    │
    └─> SignalBus broadcasts to all Backends
            ├─> Root Cell UI updates its children list display
            ├─> Grandchild UI updates "Parent: Memory Specialist"
            └─> Nexus dropdowns update to show new name


RELATIONSHIP TRACKING
=====================

Parent → Child Relationship:
    parent.identity.children = {
        "cell_id_1": "Child Name 1",
        "cell_id_2": "Child Name 2"
    }

Child → Parent Relationship:
    child.identity.parent_id = "parent_cell_id"

Registry maintains BOTH directions simultaneously.


QUICK START INTEGRATION
========================

1. Copy enhanced_cell_identity.py to your src/ directory

2. In src/app.py, create global registry:
   
   from enhanced_cell_identity import CellRegistry
   
   global_registry = CellRegistry()

3. Pass registry to all Backend instances:
   
   backend = Backend(registry=global_registry, ...)

4. Add rename capability to UI:
   
   # In your settings or context menu:
   def rename_cell():
       new_name = simpledialog.askstring("Rename", "New name:")
       if new_name:
           backend.rename_cell(new_name)

5. Subscribe to rename events:
   
   backend.bus.subscribe("cell_renamed", handle_rename)


DATA STRUCTURES
===============

CellIdentity {
    cell_id: str                    # "cell_20260216210345_a3b4c5d6"
    cell_name: str                  # "Memory Specialist"
    parent_id: Optional[str]        # "cell_20260216205500_x1y2z3a4"
    children: Dict[str, str]        # {"child_id": "Child Name", ...}
    created_at: str                 # ISO timestamp
    renamed_at: Optional[str]       # ISO timestamp of last rename
}

CellRegistry {
    _cells: Dict[str, CellIdentity]  # All registered cells
    _lock: threading.Lock            # Thread-safe operations
    _change_listeners: List[callable] # For UI updates
}


EXAMPLE USAGE
=============

# Create registry
registry = CellRegistry()

# Create root cell
root = Backend(
    registry=registry,
    cell_name="Root Cognition"
)

# Spawn child
child = Backend(
    registry=registry,
    parent_id=root.cell_id,
    cell_name=f"Child of {root.cell_name}"
)

# Registry automatically updated!
print(root.identity.children)
# Output: {"cell_..._xyz": "Child of Root Cognition"}

# Rename child
child.rename_cell("Memory Module")

# Parent's record automatically updated!
print(root.identity.children)
# Output: {"cell_..._xyz": "Memory Module"}

# Get full lineage
lineage = registry.get_lineage(child.cell_id)
# Output: [root.cell_id, child.cell_id]


SIGNAL BUS EVENTS
=================

The system emits these events through your existing SignalBusMS:

1. "cell_registered"
   Data: CellIdentity object
   When: New cell created

2. "cell_unregistered"
   Data: CellIdentity object
   When: Cell window closed

3. "cell_renamed"
   Data: {
       "cell_id": "...",
       "old_name": "...",
       "new_name": "..."
   }
   When: Cell renamed

4. "update_window_title"
   Data: "New Title String"
   When: Cell renamed (convenience event)


THREADING CONSIDERATIONS
=========================

The CellRegistry uses a threading.Lock to ensure thread-safety.

All registry operations are atomic:
- register_cell()
- unregister_cell()
- rename_cell()
- get_cell()
- get_all_cells()

You can safely call these from:
- Main UI thread
- Background inference threads
- Signal bus callbacks


PERSISTENCE STRATEGY (Optional)
================================

To persist the registry across app restarts:

1. On registry change, save to disk:
   
   def save_registry():
       data = registry.export_registry()
       with open('registry.json', 'w') as f:
           f.write(data)

2. On app startup, restore:
   
   def load_registry():
       if os.path.exists('registry.json'):
           with open('registry.json') as f:
               data = json.load(f)
               # Recreate cells from saved data
               for cell_data in data['cells'].values():
                   # Restore backend instances...

3. Consider using SQLite instead of JSON for better concurrent access


DEBUGGING TIPS
==============

1. Export registry to see full state:
   print(registry.export_registry())

2. Check cell lineage:
   lineage = registry.get_lineage(cell_id)
   for cid in lineage:
       cell = registry.get_cell(cid)
       print(f"  {cell.cell_name} ({cid})")

3. Verify bidirectional relationships:
   parent = registry.get_cell(parent_id)
   child = registry.get_cell(child_id)
   
   assert child_id in parent.children
   assert child.parent_id == parent_id

4. Monitor events:
   def debug_listener(event_type, data):
       print(f"[REGISTRY EVENT] {event_type}: {data}")
   
   registry.add_change_listener(debug_listener)


MIGRATION CHECKLIST
===================

□ Copy enhanced_cell_identity.py to src/
□ Import CellRegistry in app.py
□ Create global_registry = CellRegistry()
□ Modify Backend.__init__ to accept registry
□ Pass registry to all Backend instances
□ Add backend.rename_cell() method
□ Add rename UI (dialog + menu item)
□ Subscribe to cell_renamed signal
□ Update window title on rename
□ Update nexus dropdown to show names
□ Test: create → rename → spawn → rename parent → verify propagation
□ Optional: Add cell info bar showing name/ID
□ Optional: Add family tree viewer
□ Optional: Persist registry to disk


NEXT STEPS
==========

Once integrated, you can build on this foundation:

1. Cell Specialization
   - Add cell_type field to CellIdentity
   - Track what each cell is good at
   - Auto-route tasks to specialized cells

2. Emergent Behavior Tracking
   - Record successful inference patterns per cell
   - Identify which cells produce best results
   - Spawn more of successful cell types

3. Cell Communication Patterns
   - Track which cells talk to which
   - Identify communication bottlenecks
   - Optimize information flow

4. Evolutionary Selection
   - Track cell performance metrics
   - "Kill" underperforming cells
   - Spawn from high-performers
"""


# =============================================================================
# VISUAL EXAMPLE: Cell Hierarchy Display
# =============================================================================

def print_cell_tree(registry: CellRegistry, root_id: str, indent: int = 0):
    """
    Pretty-prints the cell hierarchy as a tree.
    
    Example output:
    
    Root Cognition [cell_abc]
    ├── Memory Specialist [cell_def]
    │   └── Knowledge Store [cell_jkl]
    └── Reasoning Module [cell_ghi]
    """
    cell = registry.get_cell(root_id)
    if not cell:
        return
    
    prefix = "│   " * indent
    connector = "├── " if indent > 0 else ""
    
    print(f"{prefix}{connector}{cell.cell_name} [{cell.cell_id}]")
    
    children_ids = list(cell.children.keys())
    for i, child_id in enumerate(children_ids):
        is_last = (i == len(children_ids) - 1)
        child_connector = "└── " if is_last else "├── "
        child_prefix = "    " if is_last else "│   "
        
        child_cell = registry.get_cell(child_id)
        if child_cell:
            print(f"{prefix}{'│   ' * indent}{child_connector}{child_cell.cell_name} [{child_id}]")
            
            # Recurse for grandchildren
            if child_cell.children:
                print_cell_tree(registry, child_id, indent + 1)


if __name__ == "__main__":
    # Demonstration
    from enhanced_cell_identity import CellRegistry, CellIdentity
    
    registry = CellRegistry()
    
    # Create root
    root = CellIdentity(cell_id="cell_abc", cell_name="Root Cognition")
    registry.register_cell(root)
    
    # Create children
    mem = CellIdentity(
        cell_id="cell_def",
        cell_name="Memory Specialist",
        parent_id="cell_abc"
    )
    registry.register_cell(mem)
    
    reason = CellIdentity(
        cell_id="cell_ghi",
        cell_name="Reasoning Module",
        parent_id="cell_abc"
    )
    registry.register_cell(reason)
    
    # Create grandchild
    store = CellIdentity(
        cell_id="cell_jkl",
        cell_name="Knowledge Store",
        parent_id="cell_def"
    )
    registry.register_cell(store)
    
    print("=" * 60)
    print("CELL HIERARCHY")
    print("=" * 60)
    print_cell_tree(registry, "cell_abc")
    print()
    
    print("=" * 60)
    print("RENAME PROPAGATION TEST")
    print("=" * 60)
    print("Before rename:")
    print(f"  Parent's children: {root.children}")
    print()
    
    registry.rename_cell("cell_def", "Long-Term Memory System")
    
    print("After rename:")
    print(f"  Parent's children: {root.children}")
    print(f"  Cell's own name: {mem.cell_name}")

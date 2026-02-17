import uuid
from datetime import datetime
from .backend import Backend
from .ui import CELL_UI
from src.microservices._TkinterAppShellMS import TkinterAppShellMS
from src.cell_identity import CellRegistry

def main():
    # Create global cell registry (singleton for the application)
    global_registry = CellRegistry()
    
    # Initialize the logic hub
    backend = Backend(registry=global_registry)

    # Load persisted theme preference (default Dark)
    theme = (backend.get_setting('theme_preference') or 'Dark').strip().title()
    if theme not in ('Dark', 'Light'):
        theme = 'Dark'
    
    # Initialize the Mother Ship (Shell)
    shell = TkinterAppShellMS({
        "title": f"_theCELL [{backend.cell_name}]",
        "geometry": "1000x800",
        "theme": theme
    })
    
    # --- Global Orchestration State ---
    cell_registry = {}  # { session_id: backend_instance }

    def broadcast_registry_update():
        """Informs all cells of the current list of available targets."""
        active_cells = global_registry.get_all_cells()
        cell_data = {
            cid: {"id": cid, "name": identity.cell_name}
            for cid, identity in active_cells.items()
        }
        for b_instance in cell_registry.values():
            b_instance.bus.emit("update_registry", cell_data)

    def register_cell_orchestration(target_backend):
        """Wires a backend into the global recursive and nexus pipelines."""
        
        # 1. Handle Recursive Spawning
        def on_spawn_request(data):
            print(f"[System] Spawning child from: {data.get('spawn_timestamp')}")
            
            # Determine parent identity
            p_id = getattr(target_backend, 'cell_id', 'unknown')
            
            # Create unique session file (timestamp-based, independent of cell_id)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            unique_session_id = f"session_{timestamp}.jsonl"
            
            # Create child backend (identity auto-generated via CellRegistry)
            child_backend = Backend(
                registry=global_registry,
                memory_path=unique_session_id,
                cell_id=None,      # Auto-generate unique ID
                parent_id=p_id,
                cell_name=None     # Auto-generate default name
            )
            
            # Create window with auto-generated cell name
            child_win = shell.spawn_window(title=f"_theCELL [{child_backend.cell_name}]", geometry="900x700")
            
            # Parent-child relationship auto-managed by registry (no manual children_ids)
            
            # Shell Proxy for Child Window
            class ShellProxy:
                def __init__(self, root, colors):
                    self.root = root
                    self.colors = colors
                def get_main_container(self): return self.root
            
            child_proxy = ShellProxy(child_win, shell.colors)
            
            # Wire orchestration BEFORE CELL_UI fires register_cell signal
            register_cell_orchestration(child_backend)
            
            child_ui = CELL_UI(child_proxy, child_backend)
            
            # Hydrate DNA into child cell based on send destination
            source = data.get('source_artifact', {})
            send_dest = source.get('send_destination', 'steps')
            send_content = source.get('send_content', source.get('payload', ''))
            source_name = source.get('source_name', getattr(target_backend, 'cell_name', 'Unknown'))

            if send_dest == 'steps':
                child_ui.add_onto_step(source_name, send_content)
            else:
                child_ui.append_to_task(send_content)

            child_ui.prompt_text.delete("1.0", "end")
            child_ui.prompt_text.insert("1.0", source.get('instructions', {}).get('system_prompt', ''))

        target_backend.bus.subscribe("cell_spawn_requested", on_spawn_request)

        # 2. Handle Identity & Registry
        def on_cell_registered(reg_data):
            cid = reg_data['id']
            cell_registry[cid] = target_backend
            print(f"[Registry] Cell Registered: {cid}")
            broadcast_registry_update()
        
        target_backend.bus.subscribe("register_cell", on_cell_registered)

        # 3. Handle Nexus/Data Pushing (The Router)
        def on_push_request(payload):
            target_id = payload.get('target_id')
            if target_id in cell_registry:
                print(f"[Nexus] Routing data from {payload.get('source_id')} to {target_id}")
                cell_registry[target_id].bus.emit("push_to_nexus", payload)

        target_backend.bus.subscribe("push_to_nexus", on_push_request)

    # Wire orchestration BEFORE CELL_UI fires register_cell signal
    register_cell_orchestration(backend)

    # Dock the UI into the shell
    app_ui = CELL_UI(shell, backend)
    
    # Ignition
    shell.launch()

if __name__ == "__main__":
    main()









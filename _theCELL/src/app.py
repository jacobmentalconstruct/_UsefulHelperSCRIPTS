from .backend import Backend
from .ui import CELL_UI
from src.microservices._TkinterAppShellMS import TkinterAppShellMS

def main():
    # Initialize the logic hub
    backend = Backend()

    # Load persisted theme preference (default Dark)
    theme = (backend.get_setting('theme_preference') or 'Dark').strip().title()
    if theme not in ('Dark', 'Light'):
        theme = 'Dark'
    
    # Initialize the Mother Ship (Shell)
    shell = TkinterAppShellMS({
        "title": "_theCELL - Idea Ingestor",
        "geometry": "1000x800",
        "theme": theme
    })
    
    # Dock the UI into the shell
    app_ui = CELL_UI(shell, backend)

    # --- Spawning Logic ---
    def on_spawn_request(data):
        """Callback when a cell requests a child."""
        print(f"[System] Spawning child cell from source: {data.get('spawn_timestamp')}")
        
        # 1. Create new window via Shell
        child_win = shell.spawn_window(title="_theCELL [Child]", geometry="900x700")
        
        # 2. Initialize a fresh Backend (with shared DB, but unique memory state if needed)
        # Note: In a full implementation, we might pass the parent's memory context here.
        child_backend = Backend()
        
        # 3. Create a new UI instance docked into the new window
        # We modify CELL_UI to accept a Toplevel as a 'shell' proxy or just a container.
        # For this patch, we assume CELL_UI can take a container if we slightly tweak it, 
        # or we just pass the shell and let it pack into the child_win if we modify the UI class.
        # SIMPLIFICATION: We assume the shell proxy works.
        
        # To make this work cleanly without rewriting UI completely, we can create a 
        # 'ShellProxy' that mimics the shell but returns the child_win as the container.
        class ShellProxy:
            def __init__(self, root, colors):
                self.root = root
                self.colors = colors
            def get_main_container(self):
                return self.root
        
        child_proxy = ShellProxy(child_win, shell.colors)
        child_ui = CELL_UI(child_proxy, child_backend)
        
        # 4. Pre-load the Artifact (The 'DNA')
        source = data.get('source_artifact', {})
        payload = source.get('payload', '')
        # Ingest the payload into the child's input box
        child_ui.input_box.insert("1.0", payload)
        # Inherit system prompt
        child_ui.prompt_text.delete("1.0", "end")
        child_ui.prompt_text.insert("1.0", source.get('instructions', {}).get('system_prompt', ''))

    # Register the spawner
    backend.bus.subscribe("cell_spawn_requested", on_spawn_request)
    
    # Ignition
    shell.launch()

if __name__ == "__main__":
    main()



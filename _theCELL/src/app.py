from .backend import Backend
from .ui import CELL_UI
from src.microservices._TkinterAppShellMS import TkinterAppShellMS

def main():
    # Initialize the logic hub
    backend = Backend()
    
    # Initialize the Mother Ship (Shell)
    shell = TkinterAppShellMS({
        "title": "_theCELL - Idea Ingestor",
        "geometry": "1000x800"
    })
    
    # Dock the UI into the shell
    app_ui = CELL_UI(shell, backend)
    
    # Ignition
    shell.launch()

if __name__ == "__main__":
    main()

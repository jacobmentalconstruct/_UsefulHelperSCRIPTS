"""
Project: ARCHITECT
ROLE: Master Entry Point & Initialization
"""
import logging
import sys
from state import AppState
from ui import AppUI
from backend import ArchitectBackend
from microservices._TkinterAppShellMS import TkinterAppShellMS

def main():
    # Setup master logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)]
    )
    logger = logging.getLogger("ARCHITECT-CORE")
    logger.info("Initializing ARCHITECT Engine...")

    try:
        # 1. Initialize Authority State (SQLite & Persistence)
        state = AppState()
        
        # 2. Initialize Logic Backend (AI & Artifacts)
        backend = ArchitectBackend(state)
        
        # 3. Initialize UI Shell (The Window)
        shell = TkinterAppShellMS({
            'title': 'Project ARCHITECT | Deconstructive Synthesis',
            'geometry': '1200x850'
        })
        
        # 4. Initialize UI Orchestration (The Interface)
        app_ui = AppUI(shell, state, backend)
        
        # 5. Launch
        logger.info("Application ready.")
        shell.launch()

    except Exception as e:
        logger.critical(f"BOOT FAILURE: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
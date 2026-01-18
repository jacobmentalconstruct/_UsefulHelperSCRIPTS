import sys
import os

# --- 1. Path Setup ---
# Get the absolute path to the 'src' folder
src_path = os.path.dirname(os.path.abspath(__file__))

# Add the project root to path (so we can find 'src')
sys.path.append(os.path.dirname(src_path))

# CRITICAL FIX: Add 'src/microservices' to path 
# This allows files like _TkinterAppShellMS to find 'microservice_std_lib' directly
sys.path.append(os.path.join(src_path, "microservices"))

# --- 2. Microservice Imports ---
# (Keep the rest of your imports the same, but now they will work safely)
from src.microservices._TkinterAppShellMS import TkinterAppShellMS
from src.microservices._TkinterThemeManagerMS import TkinterThemeManagerMS
from src.microservices._TkinterUniButtonMS import TkinterUniButtonMS
from src.microservices._ThoughtStreamMS import ThoughtStreamMS

# Logic / Brain
from src.microservices._NeuralServiceMS import NeuralServiceMS
from src.microservices._CognitiveMemoryMS import CognitiveMemoryMS
from src.microservices._RoleManagerMS import RoleManagerMS

# RAG / Data
from src.microservices._CartridgeServiceMS import CartridgeServiceMS
from src.microservices._IngestEngineMS import IngestEngineMS
from src.microservices._SearchEngineMS import SearchEngineMS
from src.microservices._ContentExtractorMS import ContentExtractorMS

# Orchestration
from src.orchestrator import MainOrchestrator

def main():
    print('--- Booting Mindshard Scaffold ---')

    # A. Initialize Core Services (The Toolbox)
    # We store them in a dictionary to pass to the Orchestrator
    services = {}

    # 1. UI Foundation
    services['theme'] = TkinterThemeManagerMS()
    services['shell'] = TkinterAppShellMS({
        "title": "Mindshard: Cognitive Scaffold", 
        "geometry": "1400x900",
        "theme_manager": services['theme']
    })
    
    # 2. The Brain
    services['neural'] = NeuralServiceMS()
    
    # 3. Memory Systems
    # Short Term
    services['memory'] = CognitiveMemoryMS({
        "persistence_path": "active_chat_log.jsonl"
    }) 
    # Long Term (RAG)
    services['cartridge'] = CartridgeServiceMS(db_path="knowledge_base.db")
    
    # 4. Utilities
    services['extractor'] = ContentExtractorMS()
    services['search'] = SearchEngineMS({"model_name": "phi3:mini-128k"}) # Or qwen
    services['ingest'] = IngestEngineMS({"db_path": "knowledge_base.db"}) # Must match Cartridge DB
    services['roles'] = RoleManagerMS()

    # 5. UI Widgets (These need the Root, so we init them after shell)
    # We pass the shell's main container as parent implicitly in orchestrator, 
    # but ThoughtStream is a widget class we can instantiate early if we give it a parent later,
    # or we just pass the Class. Here we instantiate it with the shell's container.
    # actually, best to let Orchestrator pack it, but we can init it here:
    services['thought_stream'] = ThoughtStreamMS({
        "parent": services['shell'].get_main_container() 
        # Note: In orchestrator we might repack this, or we let orchestrator init it.
        # For this setup, we'll instantiate it here but not pack it yet.
    })

    # B. Launch Orchestrator (The Pilot)
    print("--- Services Loaded. Handing control to Orchestrator ---")
    app_logic = MainOrchestrator(services)

    # C. Ignition
    services['shell'].launch()

if __name__ == '__main__':
    main()
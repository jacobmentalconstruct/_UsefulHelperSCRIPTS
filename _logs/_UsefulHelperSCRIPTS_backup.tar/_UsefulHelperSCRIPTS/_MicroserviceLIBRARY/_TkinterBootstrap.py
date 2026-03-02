"""
SERVICE_NAME: _TkinterBootstrap
ENTRY_POINT: _TkinterBootstrap.py
DEPENDENCIES: None
"""
# --- 1. Import The UI Fabric ---
from _TkinterThemeManagerMS import TkinterThemeManagerMS
from _TkinterAppShellMS import TkinterAppShellMS
from _TkinterSmartExplorerMS import TkinterSmartExplorerMS

# --- 2. Import Capabilities (The Brains) ---
# Assuming you have these from previous steps
try:
    from _ScoutMS import ScoutMS
except ImportError:
    ScoutMS = None

def main():
    print("--- BOOTING MICROSERVICE UI ---")

    # A. Initialize Theme
    theme_mgr = TkinterThemeManagerMS()
    
    # B. Initialize Shell (Pass the theme manager so it knows the colors)
    app = TkinterAppShellMS({
        "theme_manager": theme_mgr, 
        "title": "Neural Command Center",
        "geometry": "1000x700"
    })
    
    # C. Initialize Logic Services
    scout = ScoutMS() if ScoutMS else None

    # --- D. COMPOSE THE UI ---
    # Get the docking bay
    main_deck = app.get_main_container()

    # 1. Dock the Explorer on the Left
    explorer = TkinterSmartExplorerMS({
        "parent": main_deck, 
        "theme": theme_mgr.get_theme()
    })
    explorer.pack(side="left", fill="y", padx=2, pady=2)

    # 2. Load Data (If Scout is available)
    if scout:
        print("Scanning current directory...")
        data = scout.scan_directory(".") # Scan root
        explorer.load_data(data)
    else:
        # Fallback data if Scout isn't found
        explorer.load_data({"name": "No Scout Found", "type": "error", "children": []})

    # --- E. LAUNCH ---
    app.launch()

if __name__ == "__main__":
    main()
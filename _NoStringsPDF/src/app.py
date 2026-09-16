import sys
import os

# --- PATH SETUP ---
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(current_dir))
sys.path.append(os.path.join(current_dir, 'microservices'))
# Add orchestrators to path if needed, though we import directly below
sys.path.append(os.path.join(current_dir, 'orchestrators'))

# --- Core Services ---
from src.microservices._TkinterAppShellMS import TkinterAppShellMS
from src.microservices._TkinterThemeManagerMS import TkinterThemeManagerMS
from src.microservices._PdfEngineMS import PdfEngineMS

# --- Orchestrators ---
from src.orchestrators.ui_orchestrator import MainUIOrchestrator

class NoStringsPDFApp:
    def __init__(self):
        # 1. Initialize Services (The Tools)
        self.shell = TkinterAppShellMS({"title": "_NoStringsPDF", "geometry": "1400x900"})
        self.theme_mgr = TkinterThemeManagerMS()
        self.engine = PdfEngineMS()
        
        # 2. Initialize Orchestrator (The Brain)
        # This will build the UI inside the shell using the engine
        self.ui = MainUIOrchestrator(
            root=self.shell.root,
            shell=self.shell,
            theme_mgr=self.theme_mgr,
            engine=self.engine
        )

    def run(self):
        self.shell.launch()

if __name__ == '__main__':
    NoStringsPDFApp().run()
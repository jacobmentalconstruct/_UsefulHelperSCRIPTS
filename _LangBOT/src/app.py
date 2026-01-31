from src.microservices._TkinterAppShellMS import TkinterAppShellMS
from src.backend import LangBotBackend
from src.ui import LangBotUI

def main():
    # Initialize Backend logic first
    backend = LangBotBackend()
    
    # Initialize the Mother Ship (UI Shell) [cite: 121]
    shell = TkinterAppShellMS({'title': 'LangBOT - Modular Agent (Local)'})
    
    # Dock the UI into the Shell
    view = LangBotUI(shell, backend)
    
    # Ignition
    shell.launch() # [cite: 124]

if __name__ == "__main__":
    main()
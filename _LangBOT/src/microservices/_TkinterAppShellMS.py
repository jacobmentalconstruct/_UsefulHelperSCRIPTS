"""
SERVICE_NAME: _TkinterAppShellMS
ENTRY_POINT: _TkinterAppShellMS.py
INTERNAL_DEPENDENCIES: _TkinterThemeManagerMS, microservice_std_lib
EXTERNAL_DEPENDENCIES: None
"""
import tkinter as tk
from tkinter import ttk
import logging
from typing import Dict, Any, Optional
from src.microservices.microservice_std_lib import service_metadata, service_endpoint
try:
    from src.microservices._TkinterThemeManagerMS import TkinterThemeManagerMS
except ImportError:
    TkinterThemeManagerMS = None
logger = logging.getLogger('AppShell')

@service_metadata(name='TkinterAppShell', version='2.0.0', description='The Application Container. Manages the root window, main loop, and global layout.', tags=['ui', 'core', 'lifecycle'], capabilities=['ui:root', 'ui:gui'], internal_dependencies=['_TkinterThemeManagerMS', 'microservice_std_lib'], external_dependencies=[])
class TkinterAppShellMS:
    """
    The Mother Ship.
    Owns the Tkinter Root. All other UI microservices dock into this.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.root = tk.Tk()
        self.root.withdraw()
        self.theme_svc = self.config.get('theme_manager')
        if not self.theme_svc and TkinterThemeManagerMS:
            self.theme_svc = TkinterThemeManagerMS()
        self.colors = self.theme_svc.get_theme() if self.theme_svc else {}
        self._configure_root()

    def _configure_root(self):
        self.root.title(self.config.get('title', 'Microservice OS'))
        self.root.geometry(self.config.get('geometry', '1200x800'))
        bg = self.colors.get('background', '#1e1e1e')
        self.root.configure(bg=bg)
        style = ttk.Style()
        style.theme_use('clam')
        style.configure('TFrame', background=bg)
        style.configure('TLabel', background=bg, foreground=self.colors.get('foreground', '#ccc'))
        style.configure('TButton', background=self.colors.get('panel_bg', '#333'), foreground='white')
        self.main_container = tk.Frame(self.root, bg=bg)
        self.main_container.pack(fill='both', expand=True, padx=5, pady=5)

    @service_endpoint(inputs={}, outputs={}, description='Starts the GUI Main Loop.', tags=['lifecycle', 'start'], mode='sync', side_effects=['ui:block'])
    def launch(self):
        """Ignition sequence start."""
        self.root.deiconify()
        logger.info('AppShell Launched.')
        self.root.mainloop()

    @service_endpoint(inputs={}, outputs={'container': 'tk.Frame'}, description='Returns the main content area for other services to dock into.', tags=['ui', 'layout'])
    def get_main_container(self):
        """Other services call this to know where to .pack() themselves."""
        return self.main_container

    @service_endpoint(inputs={}, outputs={}, description='Gracefully shuts down the application.', tags=['lifecycle', 'stop'], side_effects=['ui:close'])
    def shutdown(self):
        self.root.quit()
if __name__ == '__main__':
    shell = TkinterAppShellMS({'title': 'Test Shell'})
    shell.launch()

"""
SERVICE_NAME: _OllamaModelSelectorMS
ENTRY_POINT: _OllamaModelSelectorMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib
EXTERNAL_DEPENDENCIES: requests
"""
import tkinter as tk
from tkinter import ttk
import requests
import threading
import logging
from typing import Dict, Any, Optional, List, Callable
from .base_service import BaseService
from .microservice_std_lib import service_metadata, service_endpoint

OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"

@service_metadata(
    name='OllamaModelSelector', 
    version='1.0.0', 
    description='The Lens: A UI widget that fetches and displays available local Ollama models.', 
    tags=['ui', 'ai', 'ollama', 'widget'], 
    capabilities=['ui:gui', 'network:outbound'], 
    internal_dependencies=['base_service', 'microservice_std_lib'], 
    external_dependencies=['requests']
)
class OllamaModelSelectorMS(tk.Frame, BaseService):
    """
    The Lens.
    A dropdown widget that automatically polls the local Ollama API for models.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None, theme: Optional[Dict[str, Any]] = None, bus: Optional[Any] = None):
        # Initialize BaseService first for logging
        BaseService.__init__(self, 'OllamaModelSelector')
        
        self.config_data = config or {}
        self.colors = theme or {}
        self.bus = bus
        
        parent = self.config_data.get('parent')
        self.on_change_callback = self.config_data.get('on_change')
        
        # Initialize the Tkinter Frame
        tk.Frame.__init__(self, parent, bg=self.colors.get('panel_bg', '#252526'))

        if self.bus:
            self.bus.subscribe("theme_updated", self.refresh_theme)
        
        self.models: List[str] = ["Scanning..."]
        self._build_ui()
        
        # Start background scan so the UI doesn't hang
        threading.Thread(target=self.refresh_models, daemon=True).start()

    def _build_ui(self):
        """Creates the label and combobox."""
        self.label = tk.Label(
            self, text="AI MODEL:", 
            bg=self.colors.get('panel_bg', self.cget('bg')), 
            fg=self.colors.get('foreground', 'white'), 
            font=('Segoe UI', 9, 'bold')
        )
        self.label.pack(side='left', padx=(5, 10))

        self.combo = ttk.Combobox(self, values=self.models, state="readonly", width=25)
        self.combo.set(self.models[0])
        self.combo.pack(side='left', padx=5)
        self.combo.bind("<<ComboboxSelected>>", self._on_selection)

    @service_endpoint(
        inputs={}, 
        outputs={'models': 'List[str]'}, 
        description='Queries local Ollama API to refresh the list of available models.', 
        tags=['network', 'refresh']
    )
    # ROLE: Queries local Ollama API to refresh the list of available models.
    # INPUTS: {}
    # OUTPUTS: {"models": "List[str]"}
    def refresh_models(self) -> List[str]:
        """Fetches models from Ollama tags endpoint."""
        try:
            response = requests.get(OLLAMA_TAGS_URL, timeout=3)
            if response.status_code == 200:
                data = response.json()
                self.models = [m['name'] for m in data.get('models', [])]
                self.log_info(f"Discovered {len(self.models)} local models.")
            else:
                self.models = ["Ollama Offline"]
        except Exception as e:
            self.log_error(f"Failed to reach Ollama: {e}")
            self.models = ["Connection Error"]

        # Update the UI from the main thread
        self.after(0, lambda: self.combo.config(values=self.models))
        if self.models and self.models[0] not in ["Connection Error", "Ollama Offline"]:
            self.after(0, lambda: self.combo.current(0))
        
        return self.models

    def _on_selection(self, event):
        """Triggered when the user picks a new model."""
        selected = self.combo.get()
        self.log_info(f"Model selected: {selected}")
        if self.on_change_callback:
            self.on_change_callback(selected)

    @service_endpoint(
        inputs={}, 
        outputs={'selected_model': 'str'}, 
        description='Returns the currently selected model string.', 
        tags=['ui', 'read']
    )
    # ROLE: Returns the currently selected model string.
    # INPUTS: {}
    # OUTPUTS: {"selected_model": "str"}
    def get_selected_model(self) -> str:
        """Retrieves current selection from the combobox."""
        return self.combo.get()

    def refresh_theme(self, new_colors):
        """Re-applies new theme colors to the widget."""
        self.colors = new_colors
        self.configure(bg=self.colors.get('panel_bg'))
        self.label.configure(
            bg=self.colors.get('panel_bg'), 
            fg=self.colors.get('foreground')
        )

if __name__ == '__main__':
    root = tk.Tk()
    root.title("Ollama Selector Test")
    root.geometry("400x100")
    
    # Simple callback test
    def log_change(m): print(f"Signal emitted for model: {m}")
    
    selector = OllamaModelSelectorMS({'parent': root, 'on_change': log_change})
    selector.pack(pady=20)
    
    root.mainloop()


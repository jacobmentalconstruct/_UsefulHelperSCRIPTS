"""
SERVICE_NAME: _TkinterThemeManagerMS
ENTRY_POINT: _TkinterThemeManagerMS.py
DEPENDENCIES: None
"""
from typing import Dict, Any, Optional
from microservice_std_lib import service_metadata, service_endpoint

# Default "Dark Modern" Theme
DEFAULT_THEME = {
    'background': '#1e1e1e',
    'foreground': '#d4d4d4',
    'panel_bg':   '#252526',
    'border':     '#3c3c3c',
    'accent':     '#007acc',
    'error':      '#f48771',
    'success':    '#89d185',
    'font_main':  ('Segoe UI', 10),
    'font_mono':  ('Consolas', 10)
}

@service_metadata(
    name="TkinterThemeManager",
    version="1.0.0",
    description="Centralized configuration for UI colors and fonts.",
    tags=["ui", "config", "theme"],
    capabilities=["ui:style"]
)
class TkinterThemeManagerMS:
    """
    The Stylist: Holds the color palette and font settings.
    All UI components query this service to decide how to draw themselves.
    """
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.theme = DEFAULT_THEME.copy()
        
        # Allow override from config
        if "overrides" in self.config:
            self.theme.update(self.config["overrides"])

    @service_endpoint(
        inputs={},
        outputs={"theme": "Dict"},
        description="Returns the current active theme dictionary.",
        tags=["ui", "read"]
    )
    def get_theme(self) -> Dict[str, Any]:
        return self.theme

    @service_endpoint(
        inputs={"key": "str", "value": "Any"},
        outputs={},
        description="Updates a specific theme attribute (e.g., changing accent color).",
        tags=["ui", "write"],
        side_effects=["ui:refresh"]
    )
    def update_key(self, key: str, value: Any):
        self.theme[key] = value

if __name__ == "__main__":
    svc = TkinterThemeManagerMS()
    print("Theme Ready:", svc.get_theme()['accent'])
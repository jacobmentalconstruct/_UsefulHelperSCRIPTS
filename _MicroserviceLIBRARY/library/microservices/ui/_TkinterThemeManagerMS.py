"""
SERVICE_NAME: _TkinterThemeManagerMS
ENTRY_POINT: _TkinterThemeManagerMS.py
INTERNAL_DEPENDENCIES: microservice_std_lib
EXTERNAL_DEPENDENCIES: None
"""

import time
from typing import Any, Dict, Optional

from microservice_std_lib import service_metadata, service_endpoint

DEFAULT_THEME = {
    'background': '#1e1e1e',
    'panel_bg': '#252526',
    'surface_bg': '#2d2d2d',
    'border': '#3c3c3c',
    'accent': '#007acc',
    'accent2': '#0e639c',
    'accent3': '#1177bb',
    'foreground': '#d4d4d4',
    'foreground_dim': '#858585',
    'foreground_muted': '#6a6a6a',
    'success': '#6a9955',
    'warning': '#dcdcaa',
    'error': '#f44747',
    'info': '#9cdcfe',
    'font_ui': ('Segoe UI', 10),
    'font_sm': ('Segoe UI', 9),
    'font_xs': ('Segoe UI', 8),
    'font_h': ('Segoe UI Semibold', 11),
    'font_mono': ('Consolas', 10),
    'font_mono_sm': ('Consolas', 9),
    'font_mono_xs': ('Consolas', 8),
    'pad': 8,
    'bg': '#1e1e1e',
    'bg2': '#252526',
    'bg3': '#2d2d2d',
    'fg': '#d4d4d4',
    'fg_dim': '#858585',
    'fg_muted': '#6a6a6a',
    }

DEFAULT_NODE_ICONS = {
    'root': '🗄',
    'directory': '📁',
    'file': '📄',
    'virtual_file': '📎',
    'compound_summary': '📋',
    'module': '📦',
    'class_def': '🔷',
    'function_def': '⚡',
    'method_def': '⚡',
    'async_function': '⚡',
    'decorator': '🏷',
    'import': '📎',
    'document': '📄',
    'document_summary': '📋',
    'section': '§',
    'subsection': '§',
    'heading': '§',
    'paragraph': '¶',
    'list_item': '•',
    'object': '{ }',
    'array': '[ ]',
    'key_value': '→',
    'table': '▦',
    'html_element': '◇',
    'html_section': '◈',
    'css_rule': '🎨',
    'xml_element': '◇',
    'chunk': '▪',
}


@service_metadata(
    name='TkinterThemeManager',
    version='1.2.0',
    description='Centralized modern Tkinter theme tokens and icon maps used by UI microservices.',
    tags=['ui', 'config', 'theme'],
    capabilities=['ui:style'],
    side_effects=['ui:refresh'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class TkinterThemeManagerMS:
    """Holds theme tokens and icon maps for modernized Tkinter components."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.start_time = time.time()
        self.config = config or {}
        self.theme = dict(DEFAULT_THEME)
        self.node_icons = dict(DEFAULT_NODE_ICONS)

        overrides = self.config.get('overrides')
        if isinstance(overrides, dict):
            self.theme.update(overrides)

        icon_overrides = self.config.get('icon_overrides')
        if isinstance(icon_overrides, dict):
            self.node_icons.update(icon_overrides)

    @service_endpoint(inputs={}, outputs={'theme': 'dict'}, description='Return active theme token dictionary.', tags=['ui', 'read'])
    def get_theme(self) -> Dict[str, Any]:
        return dict(self.theme)

    @service_endpoint(inputs={}, outputs={'icons': 'dict'}, description='Return active node icon map.', tags=['ui', 'read'])
    def get_node_icons(self) -> Dict[str, str]:
        return dict(self.node_icons)

    @service_endpoint(inputs={}, outputs={'aliases': 'dict'}, description='Return legacy theme alias map for compatibility with older Tkinter components.', tags=['ui', 'read', 'compat'])
    def get_legacy_aliases(self) -> Dict[str, Any]:
        return {
            'BG': self.theme.get('bg', self.theme.get('background')),
            'BG2': self.theme.get('bg2', self.theme.get('panel_bg')),
            'BG3': self.theme.get('bg3', self.theme.get('surface_bg')),
            'FG': self.theme.get('fg', self.theme.get('foreground')),
            'FG_DIM': self.theme.get('fg_dim', self.theme.get('foreground_dim')),
            'FG_MUTED': self.theme.get('fg_muted', self.theme.get('foreground_muted')),
            'ACCENT': self.theme.get('accent'),
            'ACCENT2': self.theme.get('accent2'),
            'ACCENT3': self.theme.get('accent3'),
            'BORDER': self.theme.get('border'),
            'PAD': self.theme.get('pad', 8),
        }

    @service_endpoint(inputs={'key': 'str', 'value': 'Any'}, outputs={'ok': 'bool'}, description='Update a single theme token at runtime.', tags=['ui', 'write'], side_effects=['ui:refresh'])
    def update_key(self, key: str, value: Any) -> bool:
        self.theme[key] = value
        return True

    @service_endpoint(inputs={'node_type': 'str', 'icon': 'str'}, outputs={'ok': 'bool'}, description='Update or add icon mapping for a node type.', tags=['ui', 'write'], side_effects=['ui:refresh'])
    def update_icon(self, node_type: str, icon: str) -> bool:
        self.node_icons[node_type] = icon
        return True

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float', 'token_count': 'int', 'icon_count': 'int'}, description='Standardized health check for theme manager state.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {
            'status': 'online',
            'uptime': time.time() - self.start_time,
            'token_count': len(self.theme),
            'icon_count': len(self.node_icons),
        }


if __name__ == '__main__':
    svc = TkinterThemeManagerMS()
    print('Theme Ready:', svc.get_theme()['accent'])

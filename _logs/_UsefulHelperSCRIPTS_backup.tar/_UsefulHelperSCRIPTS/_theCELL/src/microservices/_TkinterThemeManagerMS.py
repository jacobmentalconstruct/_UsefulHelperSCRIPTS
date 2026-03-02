"""
SERVICE_NAME: _TkinterThemeManagerMS
ENTRY_POINT: _TkinterThemeManagerMS.py
INTERNAL_DEPENDENCIES: microservice_std_lib
EXTERNAL_DEPENDENCIES: None

This module defines and manages the colour palette used throughout the
application.  A `TkinterThemeManagerMS` class encapsulates two
predefined themes—`Dark` and `Light`—inspired by the Visual Studio
Code default themes.  Themes can be swapped at runtime and are
returned as mutable dictionaries so that UI components can reference
their values directly and respond to changes.

To add a new theme, extend the `THEMES` dictionary with the
appropriate keys.  See the definitions of `DARK_THEME` and
`LIGHT_THEME` for guidance on required keys.
"""

from typing import Dict, Any, Optional
from .microservice_std_lib import service_metadata, service_endpoint


"""
Defines colour palettes for supported themes.

These palettes draw inspiration from the Visual Studio Code default
dark and light themes to provide a comfortable and familiar
development environment.  Colours are carefully chosen to avoid
high‑contrast combinations that can lead to eye strain while still
maintaining adequate contrast for accessibility.  Should additional
themes be added in the future, follow the same structure and include
keys for all UI elements consumed throughout the UI.
"""

# Visual Studio Code inspired dark theme.  The underlying palette
# uses neutral greys and blue accents similar to VS Code’s default
# dark theme.  Colours have been adjusted to be less harsh while
# maintaining sufficient contrast.
DARK_THEME: Dict[str, Any] = {
    'name': 'Dark',
    # Primary backgrounds and foregrounds
    'background': '#1e1e1e',        # main window background
    'foreground': '#d4d4d4',        # primary text colour
    'panel_bg': '#252526',          # toolbar, config panels
    'border': '#3c3c3c',            # borders and separators
    'accent': '#007acc',            # accent colour for buttons and highlights
    'error': '#f44747',             # error messages / destructive actions
    'success': '#89d185',           # success messages

    # Fonts (kept here for completeness but rarely overridden)
    'font_main': ('Segoe UI', 10),
    'font_mono': ('Consolas', 11),

    # Button styling
    'button_bg': '#0e639c',         # primary button background
    'button_fg': '#ffffff',         # primary button text colour

    # Input/entry styling
    'entry_bg': '#1e1e1e',          # entry and text box background
    'entry_fg': '#d4d4d4',          # entry text colour

    # Selection colours
    'select_bg': '#264f78',         # selection background (lists/text)
    'select_fg': '#ffffff',         # selection text colour

    # Table/heading styling
    'heading_bg': '#3c3c3c',        # table headings background
    'heading_fg': '#ffffff',        # table headings text colour
    'heading_font': ('Segoe UI', 12, 'bold'),
}

# Visual Studio Code inspired light theme.  The palette uses soft
# greys with a blue accent, mirroring VS Code’s light theme while
# avoiding stark white backgrounds.  Text colours are dark greys
# to maintain readability without excessive contrast.
LIGHT_THEME: Dict[str, Any] = {
    'name': 'Light',
    # Primary backgrounds and foregrounds
    'background': '#ffffff',        # main window background (pure white)
    'foreground': '#333333',        # primary text colour (dark grey)
    'panel_bg': '#f3f3f3',          # toolbar, config panels
    'border': '#dcdcdc',            # borders and separators
    'accent': '#0066b8',            # accent colour for buttons and highlights
    'error': '#d13438',             # error messages / destructive actions
    'success': '#107c10',           # success messages

    # Fonts
    'font_main': ('Segoe UI', 10),
    'font_mono': ('Consolas', 11),

    # Button styling
    'button_bg': '#e7e7e7',         # primary button background
    'button_fg': '#333333',         # primary button text colour

    # Input/entry styling
    'entry_bg': '#ffffff',          # entry and text box background
    'entry_fg': '#333333',          # entry text colour

    # Selection colours
    'select_bg': '#add6ff',         # selection background (lists/text)
    'select_fg': '#000000',         # selection text colour

    # Table/heading styling
    'heading_bg': '#e2e2e2',        # table headings background
    'heading_fg': '#333333',        # table headings text colour
    'heading_font': ('Segoe UI', 12, 'bold'),
}

# Registry of all supported themes.  Keys should be title‑cased to
# simplify lookups when user preferences are normalised by
# `TkinterThemeManagerMS.set_theme()`.
THEMES: Dict[str, Dict[str, Any]] = {
    'Dark': DARK_THEME,
    'Light': LIGHT_THEME,
}


@service_metadata(
    name='TkinterThemeManager',
    version='1.2.0',
    description='Centralised configuration for UI colours and fonts.',
    tags=['ui', 'config', 'theme'],
    capabilities=['ui:style'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class TkinterThemeManagerMS:
    """
    The Stylist: Holds the colour palette and font settings.

    All UI components query this service to decide how to draw themselves.
    The palette is returned as a mutable dictionary so that callers can
    hold a reference and receive updates in place when switching themes.

    Configuration options:
      - ``theme``: one of the keys defined in ``THEMES`` (default ``'Dark'``)
      - ``overrides``: a dictionary of key/value pairs used to override
        default theme values.  Overrides persist across theme changes.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}

        # Determine the requested base theme, falling back to Dark if unknown.
        requested = self.config.get('theme', 'Dark')
        requested = (requested or 'Dark').strip().title()
        if requested not in THEMES:
            requested = 'Dark'

        # Active theme name and palette.  ``self.theme`` is mutable and
        # updated in place on theme changes to preserve object identity.
        self.theme_name: str = requested
        # copy() to ensure modifications on ``self.theme`` do not affect
        # the global template stored in ``THEMES``.
        self.theme: Dict[str, Any] = THEMES[self.theme_name].copy()

        # Persist any user overrides.  If overrides are supplied they
        # should override defaults on initialisation and on subsequent
        # theme changes.  A shallow copy is sufficient because values
        # should be primitives or tuples.
        self._overrides = dict(self.config.get('overrides', {}))
        if self._overrides:
            self.theme.update(self._overrides)

    @service_endpoint(
        inputs={},
        outputs={'theme': 'Dict'},
        description='Returns the current active theme dictionary.',
        tags=['ui', 'read'],
    )
    # ROLE: Returns the current active theme dictionary.
    # INPUTS: {}
    # OUTPUTS: {"theme": "Dict"}
    def get_theme(self) -> Dict[str, Any]:
        """Return the current theme palette."""
        return self.theme

    @service_endpoint(
        inputs={},
        outputs={'theme_name': 'str'},
        description='Returns the current active theme name.',
        tags=['ui', 'read'],
    )
    # ROLE: Returns the current active theme name.
    # INPUTS: {}
    # OUTPUTS: {"theme_name": "str"}
    def get_theme_name(self) -> str:
        """Return the name of the current theme (e.g. ``'Dark'``)."""
        return self.theme_name

    @service_endpoint(
        inputs={'theme_name': 'str'},
        outputs={'applied': 'bool'},
        description='Switches the active theme (Dark/Light).',
        tags=['ui', 'write'],
        side_effects=['ui:refresh'],
    )
    # ROLE: Switches the active theme (Dark/Light).
    # INPUTS: {"theme_name": "str"}
    # OUTPUTS: {"applied": "bool"}
    def set_theme(self, theme_name: str) -> bool:
        """
        Switch the current theme to ``theme_name``.

        Unknown theme names fall back to ``'Dark'``.  Overrides stored
        during initialisation are re‑applied after the base palette is
        swapped so that user customisations persist across theme changes.
        The method always returns ``True``.
        """
        name = (theme_name or 'Dark').strip().title()
        if name not in THEMES:
            name = 'Dark'
        self.theme_name = name

        # Build a fresh palette from the base and reapply overrides.  The
        # resulting palette is merged into the existing ``self.theme``
        # dictionary to preserve its identity for any UI components holding
        # references.  This ensures calls like ``refresh_theme()`` only need
        # to reconfigure widget properties rather than replace entire dicts.
        new_theme: Dict[str, Any] = THEMES[self.theme_name].copy()
        if self._overrides:
            new_theme.update(self._overrides)

        # Update the existing dict in place rather than reassigning.
        self.theme.clear()
        self.theme.update(new_theme)
        return True

    @service_endpoint(
        inputs={'key': 'str', 'value': 'Any'},
        outputs={},
        description='Updates a specific theme attribute (e.g., changing accent colour).',
        tags=['ui', 'write'],
        side_effects=['ui:refresh'],
    )
    # ROLE: Updates a specific theme attribute (e.g., changing accent colour).
    # INPUTS: {"key": "str", "value": "Any"}
    # OUTPUTS: {}
    def update_key(self, key: str, value: Any) -> None:
        """
        Update an individual key in the current theme.

        Overrides are persisted so that subsequent calls to
        ``set_theme()`` do not wipe out the change.  A missing key will
        simply be added to the palette.
        """
        # Update the current palette
        self.theme[key] = value
        # Persist override for future theme switches
        self._overrides[key] = value


if __name__ == '__main__':  # pragma: no cover
    # Simple manual test: print palette names and accents
    svc = TkinterThemeManagerMS({'theme': 'Dark'})
    print('Initial:', svc.get_theme_name(), svc.get_theme()['accent'])
    svc.set_theme('Light')
    print('After switch:', svc.get_theme_name(), svc.get_theme()['accent'])
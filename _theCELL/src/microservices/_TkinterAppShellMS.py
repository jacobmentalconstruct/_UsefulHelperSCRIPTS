"""
SERVICE_NAME: _TkinterAppShellMS
ENTRY_POINT: _TkinterAppShellMS.py
INTERNAL_DEPENDENCIES: _TkinterThemeManagerMS, microservice_std_lib
EXTERNAL_DEPENDENCIES: None

This module provides the root Tkinter application shell.  It owns the
Tkinter root window, manages global theme propagation and hosts
embedded UI components.  The accompanying theme manager can be
configured via the ``theme`` parameter in the configuration dictionary
passed to ``TkinterAppShellMS``.  Themes can be switched at runtime
through the ``set_theme`` method.
"""

import tkinter as tk
from tkinter import ttk
import logging
from typing import Dict, Any, Optional

from .microservice_std_lib import service_metadata, service_endpoint

# Attempt to import our theme manager.  If unavailable (e.g. missing
# dependencies), theme switching will be disabled and default colours
# will be used.  Import failures are logged for easier debugging.
try:
    from ._TkinterThemeManagerMS import TkinterThemeManagerMS  # type: ignore
except Exception as ex:  # pragma: no cover - runtime import guard
    TkinterThemeManagerMS = None  # type: ignore
    logging.getLogger('AppShell').warning(
        'Theme manager could not be imported: %s.  Falling back to defaults.', ex
    )

logger = logging.getLogger('AppShell')


@service_metadata(
    name='TkinterAppShell',
    version='2.1.0',
    description='The Application Container. Manages the root window, main loop, and global layout.',
    tags=['ui', 'core', 'lifecycle'],
    capabilities=['ui:root', 'ui:gui'],
    internal_dependencies=['_TkinterThemeManagerMS', 'microservice_std_lib'],
    external_dependencies=[],
)
class TkinterAppShellMS:
    """
    The Mother Ship.

    Owns the Tkinter root.  All other UI microservices dock into this
    container.  It initialises and applies theme settings, creates a
    main content frame, and exposes lifecycle hooks such as
    ``launch`` and ``shutdown``.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}

        # Create the root window.  Withdraw initially to avoid a flash
        # of the default theme before we have a chance to apply our
        # selected colours.
        self.root: tk.Tk = tk.Tk()
        self.root.withdraw()

        # Theme manager (microservice).  Allow callers to supply
        # their own instance via ``theme_manager`` to support custom
        # themes or stub implementations.  Otherwise fall back to our
        # built‑in manager if available.
        self.theme_svc = self.config.get('theme_manager')
        if not self.theme_svc and TkinterThemeManagerMS is not None:
            # Pass through initial theme selection to the theme service
            self.theme_svc = TkinterThemeManagerMS({'theme': self.config.get('theme', 'Dark')})

        # Initialise colours from the theme manager.  ``get_theme()``
        # returns a mutable dictionary.  If no theme manager is
        # available, use an empty dict and rely on default Tk
        # colours.
        self.colors: Dict[str, Any] = self.theme_svc.get_theme() if self.theme_svc else {}

        # Configure the root window and create the main content
        # container before applying the initial theme.  The geometry
        # must be set before calling ``set_theme`` so that we can
        # update the frame backgrounds appropriately.
        self._configure_root()

        # Ensure initial theme is applied to ttk styles and surfaces.
        initial_theme = (self.config.get('theme') or 'Dark')
        self.set_theme(initial_theme)

    def _configure_root(self) -> None:
        """Configure basic properties of the root window."""
        self.root.title(self.config.get('title', 'Microservice OS'))
        self.root.geometry(self.config.get('geometry', '1200x800'))
        bg = self.colors.get('background', '#1e1e1e')
        self.root.configure(bg=bg)

        # Main container
        self.main_container: tk.Frame = tk.Frame(self.root, bg=bg)
        self.main_container.pack(fill='both', expand=True, padx=5, pady=5)

    def _apply_ttk_theme(self) -> None:
        """Applies ttk styling based on the current palette."""
        # Provide sensible defaults to avoid KeyError if a palette is
        # missing keys.  Fallback values mirror VS Code’s colours.
        bg = self.colors.get('background', '#1e1e1e')
        fg = self.colors.get('foreground', '#d4d4d4')
        panel = self.colors.get('panel_bg', '#252526')
        border = self.colors.get('border', '#3c3c3c')
        btn_bg = self.colors.get('button_bg', panel)
        btn_fg = self.colors.get('button_fg', fg)
        entry_bg = self.colors.get('entry_bg', bg)
        entry_fg = self.colors.get('entry_fg', fg)
        select_bg = self.colors.get('select_bg', self.colors.get('accent', '#007acc'))
        select_fg = self.colors.get('select_fg', '#ffffff')
        heading_bg = self.colors.get('heading_bg', panel)
        heading_fg = self.colors.get('heading_fg', fg)

        style = ttk.Style()
        try:
            # Use 'clam' for better cross‑platform consistency
            style.theme_use('clam')
        except Exception:
            pass

        style.configure('TFrame', background=bg)
        style.configure('TLabel', background=bg, foreground=fg)
        style.configure('TButton', background=btn_bg, foreground=btn_fg)
        style.map('TButton',
                  background=[('active', btn_bg)],
                  foreground=[('active', btn_fg)])

        style.configure('TEntry', fieldbackground=entry_bg, foreground=entry_fg)
        style.configure('TCombobox', fieldbackground=entry_bg, foreground=entry_fg)
        style.map('TCombobox',
                  fieldbackground=[('readonly', entry_bg)],
                  foreground=[('readonly', entry_fg)])

        style.configure('Treeview', background=entry_bg, fieldbackground=entry_bg, foreground=entry_fg, bordercolor=border)
        style.configure('Treeview.Heading', background=heading_bg, foreground=heading_fg)
        style.map('Treeview', background=[('selected', select_bg)], foreground=[('selected', select_fg)])

    @service_endpoint(
        inputs={'theme_name': 'str'},
        outputs={'applied': 'bool'},
        description='Applies a named theme (Dark/Light) via the ThemeManager and refreshes ttk styling.',
        tags=['ui', 'theme'],
        mode='sync',
        side_effects=['ui:refresh'],
    )
    def set_theme(self, theme_name: str) -> bool:
        """
        Switch the active theme.

        The theme manager updates its internal palette in place.  To
        preserve the identity of ``self.colors`` for code that holds
        references to it (e.g. nested UIs), we only refresh the
        mapping if the theme manager returns a *different* dictionary.
        If the returned palette is the same object as ``self.colors``,
        the colours have already been updated in place and clearing
        would wipe them out.  Therefore, we only clear and update
        when necessary.
        """
        name = (theme_name or 'Dark').strip().title()
        if self.theme_svc and hasattr(self.theme_svc, 'set_theme'):
            self.theme_svc.set_theme(name)
            # Acquire the (possibly updated) palette from the theme service
            new_colors = self.theme_svc.get_theme() or {}
            # If the palette is a different object, we want to update
            # our colours dict in place.  Otherwise, the theme manager
            # mutated the existing dict and we must not clear it.
            if new_colors is not self.colors:
                try:
                    self.colors.clear()
                    self.colors.update(new_colors)
                except Exception:
                    # Fall back to assignment if clear/update fails
                    self.colors = dict(new_colors)

        # Apply surfaces to the main window and container
        bg = self.colors.get('background', '#1e1e1e')
        self.root.configure(bg=bg)
        if hasattr(self, 'main_container') and self.main_container.winfo_exists():
            self.main_container.configure(bg=bg)

        # Refresh all ttk widget styles
        self._apply_ttk_theme()

        try:
            # Force Tkinter to process geometry and color updates immediately
            self.root.update_idletasks()
        except Exception:
            pass

        return True

    @service_endpoint(
        inputs={},
        outputs={},
        description='Starts the GUI main loop.',
        tags=['lifecycle', 'start'],
        mode='sync',
        side_effects=['ui:block'],
    )
    def launch(self) -> None:
        """Ignition sequence start."""
        self.root.deiconify()
        logger.info('AppShell Launched.')
        self.root.mainloop()

    @service_endpoint(
        inputs={},
        outputs={'container': 'tk.Frame'},
        description='Returns the main content area for other services to dock into.',
        tags=['ui', 'layout'],
    )
    def get_main_container(self) -> tk.Frame:
        """Other services call this to know where to ``pack()`` themselves."""
        return self.main_container

    @service_endpoint(
        inputs={},
        outputs={},
        description='Gracefully shuts down the application.',
        tags=['lifecycle', 'stop'],
        side_effects=['ui:close'],
    )
    def shutdown(self) -> None:
        self.root.quit()


if __name__ == '__main__':  # pragma: no cover
    # Simple manual test.  Note that running Tkinter in a headless
    # environment will raise, so this is primarily for local testing.
    shell = TkinterAppShellMS({'title': 'Test Shell'})
    shell.launch()
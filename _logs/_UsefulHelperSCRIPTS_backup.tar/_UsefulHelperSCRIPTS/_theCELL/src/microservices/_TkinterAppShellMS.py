"""
SERVICE_NAME: _TkinterAppShellMS
ENTRY_POINT: _TkinterAppShellMS.py
INTERNAL_DEPENDENCIES: _TkinterThemeManagerMS, microservice_std_lib, base_service
EXTERNAL_DEPENDENCIES: None

This module provides the root Tkinter application shell. It owns the
Tkinter root window, manages global theme propagation and hosts
embedded UI components.
"""

import tkinter as tk
from tkinter import ttk
import logging
from typing import Dict, Any, Optional

from .microservice_std_lib import service_metadata, service_endpoint
from .base_service import BaseService

# Attempt to import our theme manager.
try:
    from ._TkinterThemeManagerMS import TkinterThemeManagerMS  # type: ignore
except Exception as ex:
    TkinterThemeManagerMS = None
    logging.getLogger("AppShell").warning(
        "Theme manager could not be imported: %s. Falling back to defaults.", ex
    )

logger = logging.getLogger("AppShell")


@service_metadata(
    name="TkinterAppShell",
    version="2.1.1",
    description="The Mother Ship: Root UI container that manages the lifecycle of recursive Cell windows.",
    tags=["ui", "shell", "container"],
    capabilities=["ui:gui", "window-management"],
    internal_dependencies=["_TkinterThemeManagerMS", "microservice_std_lib", "base_service"],
)
class TkinterAppShellMS(BaseService):
    """
    The Mother Ship.
    Owns the Tk root window and provides a stable lifecycle contract for the app.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("TkinterAppShell")
        self.config = config or {}

        # 1) Root Window
        self.root = tk.Tk()
        self.root.title(self.config.get("title", "_theCELL - Idea Ingestor"))
        self.root.geometry(self.config.get("geometry", "1000x800"))

        # 2) Theme Management
        self.theme_manager = None
        self.colors = {
            "background": "#1e1e1e",
            "foreground": "#cccccc",
            "panel_bg": "#252526",
            "accent": "#007acc",
            # optional UI keys some screens may ask for:
            "entry_bg": "#1e1e1e",
            "entry_fg": "#cccccc",
            "select_bg": "#264f78",
            "button_fg": "#cccccc",
        }

        if TkinterThemeManagerMS:
            theme_pref = (self.config.get("theme") or "Dark").strip().title()
            self.theme_manager = TkinterThemeManagerMS({"theme": theme_pref})
            try:
                self.colors = self.theme_manager.get_theme()
            except Exception:
                # fallback to defaults if theme manager is partially implemented
                pass
            self.log_info(f"Theme Manager initialized with '{theme_pref}' theme.")

        self.root.configure(bg=self.colors.get("background"))

        # 3) Main Container (the docking zone)
        self.main_container = tk.Frame(self.root, bg=self.colors.get("background"))
        self.main_container.pack(fill="both", expand=True)

        # If any build withdraws to avoid a flash, we still safely deiconify in launch()
        # (no-op if not withdrawn).
        # self.root.withdraw()

    # -------------------------------------------------------------------------
    # LIFECYCLE (IMPORTANT: app.py expects shell.launch())
    # -------------------------------------------------------------------------

    @service_endpoint(
        inputs={},
        outputs={},
        description="Starts the GUI main loop.",
        tags=["lifecycle", "start"],
        side_effects=["ui:block"],
    )
    # ROLE: Starts the GUI main loop.
    # INPUTS: {}
    # OUTPUTS: {}
    def launch(self) -> None:
        """Ignition sequence start."""
        try:
            self.root.deiconify()
        except Exception:
            pass

        try:
            self.log_info("AppShell Launched.")
        except Exception:
            logger.info("AppShell Launched.")

        self.root.mainloop()

    @service_endpoint(
        inputs={},
        outputs={},
        description="Gracefully shuts down the application.",
        tags=["lifecycle", "stop"],
        side_effects=["ui:close"],
    )
    # ROLE: Gracefully shuts down the application.
    # INPUTS: {}
    # OUTPUTS: {}
    def shutdown(self) -> None:
        """Closes the Tkinter event loop and destroys the root window."""
        self.log_info("Shutting down Application Shell.")
        try:
            # quit() exits mainloop; destroy() removes windows
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass

    # -------------------------------------------------------------------------
    # THEME
    # -------------------------------------------------------------------------

    @service_endpoint(
        inputs={"theme_name": "str"},
        outputs={"success": "bool"},
        description="Switches the global application theme (e.g., Dark, Light).",
        tags=["ui", "theme"],
        side_effects=["ui:refresh"],
    )
    # ROLE: Switches the global application theme (e.g., Dark, Light).
    # INPUTS: {"theme_name": "str"}
    # OUTPUTS: {"success": "bool"}
    def set_theme(self, theme_name: str) -> bool:
        """Updates the theme and propagates colors to the shell."""
        if not self.theme_manager:
            return False

        theme_name = (theme_name or "Dark").strip().title()
        success = False
        try:
            success = bool(self.theme_manager.set_theme(theme_name))
        except Exception:
            success = False

        if success:
            try:
                self.colors = self.theme_manager.get_theme()
            except Exception:
                pass
            self.root.configure(bg=self.colors.get("background"))
            self.main_container.configure(bg=self.colors.get("background"))
            self.log_info(f"Theme switched to {theme_name}")

        return success

    # -------------------------------------------------------------------------
    # LAYOUT + WINDOWS
    # -------------------------------------------------------------------------

    @service_endpoint(
        inputs={},
        outputs={"container": "tk.Frame"},
        description="Returns the main content area for other services to dock into.",
        tags=["ui", "layout"],
    )
    # ROLE: Returns the main content area for other services to dock into.
    # INPUTS: {}
    # OUTPUTS: {"container": "tk.Frame"}
    def get_main_container(self) -> tk.Frame:
        """Other services call this to know where to pack() themselves."""
        return self.main_container

    @service_endpoint(
        inputs={"title": "str", "geometry": "str"},
        outputs={"window": "tk.Toplevel"},
        description="Spawns a new top-level window for a child cell.",
        tags=["ui", "lifecycle"],
    )
    # ROLE: Spawns a new top-level window for a child cell.
    # INPUTS: {"geometry": "str", "title": "str"}
    # OUTPUTS: {"window": "tk.Toplevel"}
    def spawn_window(self, title: str = "Child Cell", geometry: str = "1000x800") -> tk.Toplevel:
        """Creates a new Toplevel window that inherits the shell's theme."""
        new_window = tk.Toplevel(self.root)
        new_window.title(title)
        new_window.geometry(geometry)
        bg = self.colors.get("background", "#1e1e1e")
        new_window.configure(bg=bg)
        self.log_info(f"Spawned new window: {title}")
        return new_window


if __name__ == "__main__":
    # Test Harness
    logging.basicConfig(level=logging.INFO)
    shell = TkinterAppShellMS({"title": "Shell Test Window"})
    print(f"Shell Ready: {shell._service_info['id']}")
    shell.launch()

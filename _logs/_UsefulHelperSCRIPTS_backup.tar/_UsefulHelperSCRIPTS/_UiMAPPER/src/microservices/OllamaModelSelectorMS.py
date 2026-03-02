"""
SERVICE_NAME: OllamaModelSelectorMS
ENTRY_POINT: OllamaModelSelectorMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib, OllamaClientMS
EXTERNAL_DEPENDENCIES: (none)
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Dict, List, Optional

from .base_service import BaseService
from .microservice_std_lib import service_metadata, service_endpoint
from .OllamaClientMS import OllamaClientMS, OllamaClientConfig


@service_metadata(
    name="OllamaModelSelector",
    version="1.1.0",
    description="UI Lens: A dropdown widget that displays available local Ollama models via OllamaClientMS.",
    tags=["ui", "ai", "ollama", "widget"],
    capabilities=["ui:gui", "network:outbound"],
    internal_dependencies=["base_service", "microservice_std_lib", "OllamaClientMS"],
    external_dependencies=[],
)
class OllamaModelSelectorMS(tk.Frame, BaseService):
    """
    A small Tkinter UI microservice (Lens) that:
      - lists local Ollama models using OllamaClientMS.list_models()
      - displays them in a readonly ttk.Combobox
      - emits selection changes via on_change callback

    Config keys (config dict):
      - parent: required Tk parent
      - on_change: Optional[Callable[[str], None]]
      - client: Optional[OllamaClientMS] (if not provided, one will be created)
      - base_url: Optional[str] (only used if creating client)
      - timeout_sec: Optional[float] (only used if creating client)
      - auto_refresh: bool (default True; initial refresh in background)

    Theme keys (theme dict):
      - panel_bg: background color
      - foreground: foreground color
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        theme: Optional[Dict[str, Any]] = None,
        bus: Optional[Any] = None,
    ):
        BaseService.__init__(self, "OllamaModelSelector")

        self.config_data = config or {}
        self.colors = theme or {}
        self.bus = bus

        parent = self.config_data.get("parent")
        if parent is None:
            raise ValueError("OllamaModelSelectorMS requires config['parent'].")

        self.on_change_callback: Optional[Callable[[str], None]] = self.config_data.get("on_change")

        client = self.config_data.get("client")
        if isinstance(client, OllamaClientMS):
            self.client = client
        else:
            base_url = str(self.config_data.get("base_url") or "http://127.0.0.1:11434")
            timeout_sec = float(self.config_data.get("timeout_sec") or 3.0)
            self.client = OllamaClientMS(
                OllamaClientConfig(base_url=base_url, timeout_sec=timeout_sec, user_agent="UiMapper/OllamaModelSelectorMS")
            )

        tk.Frame.__init__(self, parent, bg=self.colors.get("panel_bg", "#252526"))

        if self.bus:
            try:
                self.bus.subscribe("theme_updated", self.refresh_theme)
            except Exception:
                pass

        self.models: List[str] = ["Scanning..."]

        self.label: Optional[tk.Label] = None
        self.combo: Optional[ttk.Combobox] = None
        self.refresh_btn: Optional[ttk.Button] = None

        self._build_ui()

        auto_refresh = bool(self.config_data.get("auto_refresh", True))
        if auto_refresh:
            threading.Thread(target=self.refresh_models, daemon=True).start()

    def _build_ui(self) -> None:
        self.label = tk.Label(
            self,
            text="AI MODEL:",
            bg=self.colors.get("panel_bg", self.cget("bg")),
            fg=self.colors.get("foreground", "white"),
            font=("Segoe UI", 9, "bold"),
        )
        self.label.pack(side="left", padx=(5, 10))

        self.combo = ttk.Combobox(self, values=self.models, state="readonly", width=30)
        self.combo.set(self.models[0])
        self.combo.pack(side="left", padx=5)
        self.combo.bind("<<ComboboxSelected>>", self._on_selection)

        self.refresh_btn = ttk.Button(self, text="Refresh", command=self._refresh_in_bg)
        self.refresh_btn.pack(side="left", padx=(8, 5))

    def _refresh_in_bg(self) -> None:
        threading.Thread(target=self.refresh_models, daemon=True).start()

    @service_endpoint(
        inputs={},
        outputs={"models": "List[str]"},
        description="Queries local Ollama API via OllamaClientMS to refresh available models.",
        tags=["network", "refresh"],
    )
    def refresh_models(self) -> List[str]:
        """
        Fetches models from Ollama using OllamaClientMS.list_models().

        UI updates are scheduled via after(0, ...) to keep Tk thread-safe.
        """
        names: List[str] = []
        try:
            resp = self.client.list_models()
            if resp.ok and isinstance(resp.raw, dict):
                models = resp.raw.get("models") or []
                for m in models:
                    try:
                        name = (m or {}).get("name")
                        if isinstance(name, str) and name.strip():
                            names.append(name.strip())
                    except Exception:
                        continue
                names = sorted(set(names))
                if not names:
                    names = ["(no local models)"]
            else:
                names = ["Ollama Offline"]
                if resp.error and getattr(resp.error, "detail", None):
                    self.log_error(f"Ollama list_models failed: {resp.error.detail}")
        except Exception as e:
            self.log_error(f"refresh_models exception: {e}")
            names = ["Connection Error"]

        self.models = names

        def _apply_ui() -> None:
            if self.combo is None:
                return
            try:
                self.combo.config(values=self.models)
                # If current selection is invalid, choose first item
                cur = str(self.combo.get() or "")
                if cur not in self.models and self.models:
                    self.combo.set(self.models[0])
            except Exception:
                pass

        try:
            self.after(0, _apply_ui)
        except Exception:
            pass

        return self.models

    def _on_selection(self, _event: Any) -> None:
        if self.combo is None:
            return
        selected = self.combo.get()
        self.log_info(f"Model selected: {selected}")
        if self.on_change_callback:
            try:
                self.on_change_callback(selected)
            except Exception as e:
                self.log_error(f"on_change callback failed: {e}")

    @service_endpoint(
        inputs={},
        outputs={"selected_model": "str"},
        description="Returns the currently selected model string.",
        tags=["ui", "read"],
    )
    def get_selected_model(self) -> str:
        if self.combo is None:
            return ""
        return str(self.combo.get() or "")

    def refresh_theme(self, new_colors: Dict[str, Any]) -> None:
        self.colors = new_colors or {}
        try:
            self.configure(bg=self.colors.get("panel_bg", self.cget("bg")))
        except Exception:
            pass
        if self.label is not None:
            try:
                self.label.configure(
                    bg=self.colors.get("panel_bg", self.cget("bg")),
                    fg=self.colors.get("foreground", "white"),
                )
            except Exception:
                pass


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Ollama Selector Test")
    root.geometry("520x120")

    def log_change(m: str) -> None:
        print(f"Selected: {m}")

    selector = OllamaModelSelectorMS({"parent": root, "on_change": log_change, "auto_refresh": True})
    selector.pack(pady=20, padx=20, fill="x")

    root.mainloop()


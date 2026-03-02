"""
Ollama model selector widget.
Async-fetches available local models and presents them in a dropdown.
"""
import tkinter as tk
from tkinter import ttk
import threading
import requests
from theme import THEME

OLLAMA_TAGS_URL = "http://localhost:11434/api/tags"


class ModelSelector(tk.Frame):
    """
    Dropdown that polls the local Ollama API for available models.
    Non-blocking: the fetch runs in a daemon thread.
    """

    def __init__(self, parent, on_change=None, **kwargs):
        super().__init__(parent, bg=THEME["bg2"], **kwargs)
        self._on_change = on_change
        self.models = ["Scanning..."]

        self.label = tk.Label(
            self,
            text="MODEL:",
            bg=THEME["bg2"],
            fg=THEME["fg"],
            font=THEME["font_interface_bold"],
        )
        self.label.pack(side="left", padx=(4, 8))

        self.combo = ttk.Combobox(
            self,
            values=self.models,
            state="readonly",
            width=22,
            font=THEME["font_interface_small"],
        )
        self.combo.set(self.models[0])
        self.combo.pack(side="left", padx=4)
        self.combo.bind("<<ComboboxSelected>>", self._on_selection)

        self.btn_refresh = tk.Button(
            self,
            text="\u21BB",
            command=self.refresh,
            bg=THEME["bg2"],
            fg=THEME["fg_dim"],
            font=("Consolas", 11),
            relief="flat",
            cursor="hand2",
        )
        self.btn_refresh.pack(side="left", padx=2)

        threading.Thread(target=self._fetch_models, daemon=True).start()

    def refresh(self):
        """Trigger a manual model list refresh."""
        self.combo.set("Scanning...")
        threading.Thread(target=self._fetch_models, daemon=True).start()

    def get_selected(self):
        return self.combo.get()

    def _fetch_models(self):
        try:
            resp = requests.get(OLLAMA_TAGS_URL, timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                self.models = [m["name"] for m in data.get("models", [])]
                if not self.models:
                    self.models = ["No models found"]
            else:
                self.models = ["Ollama Offline"]
        except Exception:
            self.models = ["Connection Error"]

        self.after(0, self._apply_models)

    def _apply_models(self):
        self.combo["values"] = self.models
        if self.models and self.models[0] not in ("Connection Error", "Ollama Offline", "No models found"):
            self.combo.current(0)
            if self._on_change:
                self._on_change(self.models[0])
        else:
            self.combo.set(self.models[0])

    def _on_selection(self, _event):
        selected = self.combo.get()
        if self._on_change:
            self._on_change(selected)

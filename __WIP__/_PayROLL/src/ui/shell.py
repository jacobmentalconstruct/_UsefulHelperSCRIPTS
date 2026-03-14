from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ApplicationShell:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.page_frames: dict[str, ttk.Frame] = {}
        self.nav_buttons: dict[str, ttk.Button] = {}

        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.sidebar = ttk.Frame(root, style="Panel.TFrame", padding=12)
        self.sidebar.grid(row=0, column=0, sticky="nsw")
        self.sidebar.columnconfigure(0, weight=1)

        self.main = ttk.Frame(root, style="App.TFrame", padding=(12, 12, 12, 6))
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.columnconfigure(0, weight=1)
        self.main.rowconfigure(1, weight=1)

        self.header = ttk.Frame(self.main, style="App.TFrame")
        self.header.grid(row=0, column=0, sticky="ew")
        self.header.columnconfigure(0, weight=1)

        self.title_var = tk.StringVar(value="Payroll Prototype")
        self.status_var = tk.StringVar(value="Ready")
        self.title_label = ttk.Label(self.header, textvariable=self.title_var, style="App.TLabel", font=("Segoe UI Semibold", 15))
        self.title_label.grid(row=0, column=0, sticky="w")

        self.actions = ttk.Frame(self.header, style="App.TFrame")
        self.actions.grid(row=0, column=1, sticky="e")

        self.content = ttk.Frame(self.main, style="App.TFrame")
        self.content.grid(row=1, column=0, sticky="nsew", pady=(10, 6))
        self.content.columnconfigure(0, weight=1)
        self.content.rowconfigure(0, weight=1)

        self.status_label = ttk.Label(self.main, textvariable=self.status_var, style="Muted.TLabel")
        self.status_label.grid(row=2, column=0, sticky="ew", pady=(6, 0))

    def set_title(self, text: str) -> None:
        self.title_var.set(text)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)

    def add_action(self, text: str, command) -> None:
        button = ttk.Button(self.actions, text=text, style="App.TButton", command=command)
        button.pack(side="left", padx=(0, 8))

    def add_nav(self, page_id: str, label: str, command) -> None:
        button = ttk.Button(self.sidebar, text=label, style="Nav.TButton", command=command)
        button.pack(fill="x", pady=2)
        self.nav_buttons[page_id] = button

    def register_page(self, page_id: str, frame: ttk.Frame) -> None:
        frame.grid(row=0, column=0, sticky="nsew")
        self.page_frames[page_id] = frame

    def show_page(self, page_id: str) -> None:
        frame = self.page_frames[page_id]
        frame.tkraise()

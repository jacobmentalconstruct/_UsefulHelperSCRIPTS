"""
app.py
------
Dumb shell for UiMAPPER.

Responsibilities:
- Create Tk root
- Apply icon/title if desired
- Instantiate backend orchestrator
- Instantiate UI orchestrator
- Start Tk mainloop

Non-goals:
- Any business logic
- Any pipeline code
- Any microservice wiring beyond "backend + ui orchestrators"
"""

from __future__ import annotations

import tkinter as tk

# Adjust imports if your package/module paths differ
from . import backend as backend_mod
from .backend import get_backend
from .ui import build_ui


APP_TITLE = "UiMAPPER"


def main() -> None:
    root = tk.Tk()
    root.title(APP_TITLE)

    # Optional: set minimum size + initial geometry
    root.minsize(1100, 720)
    root.geometry("1180x760")

    # Optional: icon
    # If you have an .ico in assets/icons, wire it here.
    # try:
    #     root.iconbitmap("assets/icons/uimapper.ico")
    # except Exception:
    #     pass

    backend = get_backend()

    # Debug: show which backend module is actually being imported/executed.
    # If you patched a different copy than the one on sys.path, this will reveal it.
    try:
        print(f"[UiMAPPER] backend module: {getattr(backend_mod, '__file__', None)}")
    except Exception:
        pass

    build_ui(root, backend)

    root.mainloop()


if __name__ == "__main__":
    main()



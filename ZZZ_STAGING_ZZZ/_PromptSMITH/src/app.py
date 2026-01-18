# src/app.py
import tkinter as tk
from tkinter import ttk

from src.services.db_service import DatabaseManager
from src.services.schema_engine import SchemaEngine
from src.services.export_service import ExportService
from src.ui.main_window import MainWindow


def main() -> None:
    # ---- Root window setup (dumb orchestration) ----
    root = tk.Tk()
    root.title("PromptArchitect - Schema Manager")
    root.geometry("1100x700")
    root.minsize(900, 550)
    root.resizable(True, True)

    # Use a standard ttk theme for a clean native-ish look
    style = ttk.Style(root)
    # Prefer clam; fallback if unavailable.
    try:
        style.theme_use("clam")
    except tk.TclError:
        style.theme_use(style.theme_names()[0])

    # ---- Instantiate services (logic lives outside UI) ----
    db = DatabaseManager(db_path="promptarchitect.db")
    schema_engine = SchemaEngine(schemas_dir="schemas")
    exporter = ExportService()

    # ---- Build UI and pass services in ----
    app = MainWindow(
        root=root,
        db=db,
        schema_engine=schema_engine,
        exporter=exporter,
    )
    app.pack(fill="both", expand=True)

    # Start schema discovery polling (runtime updates)
    schema_engine.start_polling(root, on_change=app.on_schemas_changed)

    root.mainloop()


if __name__ == "__main__":
    main()

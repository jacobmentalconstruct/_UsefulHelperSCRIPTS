from __future__ import annotations

import logging
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

from .backend import BackendOrchestrator
from .ui import UIOrchestrator


class ApplicationOrchestrator:
    def __init__(self, workspace_root: Path):
        self.workspace_root = Path(workspace_root)
        self.logger = logging.getLogger("payroll.app")
        self.root = tk.Tk()
        self.backend = BackendOrchestrator()
        self.ui = UIOrchestrator(self.root, self.backend)
        self._shutting_down = False

    @property
    def database_path(self) -> Path:
        return self.workspace_root / "data" / "payroll.sqlite3"

    def start(self) -> None:
        self.backend.create_or_open_database(self.database_path)
        self.ui.build_shell()
        self.ui.apply_snapshot(self.backend.snapshot())
        self.root.protocol("WM_DELETE_WINDOW", self.request_shutdown)
        self.root.report_callback_exception = self.handle_ui_exception
        self._schedule_health_tick()
        self.root.mainloop()

    def _schedule_health_tick(self) -> None:
        if self._shutting_down:
            return
        health = self.health_snapshot()
        if self.ui.shell is not None:
            dirty_text = "Unsaved" if health.get("dirty") else "Saved"
            self.ui.shell.set_status(
                f"{dirty_text} | Active Period {health.get('active_period_id')} | Page {health.get('current_page')}"
            )
        self.root.after(8000, self._schedule_health_tick)

    def request_shutdown(self) -> None:
        choice = self.ui.confirm_close()
        if choice is None:
            return
        self.shutdown(save_changes=bool(choice), reason="window_close")

    def shutdown(self, save_changes: bool, reason: str) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.logger.info("Shutting down payroll prototype", extra={"reason": reason, "save_changes": save_changes})
        try:
            self.backend.close(save_changes=save_changes)
        finally:
            try:
                self.root.destroy()
            except tk.TclError:
                pass

    def handle_ui_exception(self, exc_type, exc_value, exc_traceback) -> None:
        self.logger.exception("Unhandled Tk callback exception", exc_info=(exc_type, exc_value, exc_traceback))
        messagebox.showerror("Unexpected Error", f"{exc_value}\n\nThe app will close after saving pending changes.")
        self.shutdown(save_changes=True, reason="ui_exception")

    def health_snapshot(self) -> dict[str, object]:
        snapshot = self.backend.health_snapshot()
        snapshot["current_page"] = self.ui.current_page
        return snapshot

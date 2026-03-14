from __future__ import annotations

import sys
from pathlib import Path
import tempfile
import tkinter as tk
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from orchestration.backend import BackendOrchestrator  # noqa: E402
from orchestration.ui import UIOrchestrator  # noqa: E402


class UISmokeTests(unittest.TestCase):
    def test_shell_builds_and_applies_snapshot(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        root.withdraw()
        temp_dir = tempfile.TemporaryDirectory()
        backend = BackendOrchestrator()
        backend.create_or_open_database(Path(temp_dir.name) / "payroll.sqlite3")
        ui = UIOrchestrator(root, backend)
        try:
            ui.build_shell()
            ui.apply_snapshot(backend.snapshot())
            self.assertIsNotNone(ui.shell)
            self.assertIn("Sunday", ui.day_pages)
        finally:
            backend.close(save_changes=False)
            root.destroy()
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()

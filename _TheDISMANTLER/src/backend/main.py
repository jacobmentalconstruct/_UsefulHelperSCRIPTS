"""
BackendEngine – The command center that routes tasks through
specialized controllers.
"""
import os
from backend.file_controller import FileController
from backend.ai_controller import AIController
from backend.modules.sliding_window import SlidingWindow
from backend.modules.db_schema import init_db


class BackendEngine:
    """
    Central orchestrator for all backend operations.
    Receives structured schemas from the UI and delegates them
    to the appropriate controller.
    """

    def __init__(self, log_callback=None):
        self.log = log_callback or (lambda msg: None)
        self.controllers = {}
        self.project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )

    def boot(self):
        """Initialize the database, spin up controllers, and register them."""
        self.log("Initializing context database...")
        init_db()

        self.log("Registering FileController...")
        self.controllers["file"] = FileController(self.project_root, self.log)

        self.log("Registering AIController...")
        self.controllers["ai"] = AIController(self.log)

        self.log("Initializing SlidingWindow context module...")
        self.sliding_window = SlidingWindow()

        self.log("Backend Ready.")

    def execute_task(self, schema):
        """
        Standardized entry point for the UI to request logic.
        Schema must include a 'system' key that maps to a controller name
        (e.g. 'file', 'ai') and an 'action' key for the specific operation.
        """
        target = schema.get("system")
        if target in self.controllers:
            try:
                return self.controllers[target].handle(schema)
            except Exception as e:
                self.log(f"Controller error [{target}]: {e}")
                return {"status": "error", "message": str(e)}
        return {"status": "error", "message": f"Unknown controller: {target}"}

    def get_context_for_cursor(self, file_path, cursor_line, budget=None):
        """Convenience method: get sliding-window context for the AI."""
        return self.sliding_window.get_context(file_path, cursor_line, budget)

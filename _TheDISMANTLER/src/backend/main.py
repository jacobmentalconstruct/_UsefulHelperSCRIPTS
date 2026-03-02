"""
BackendEngine – The command center that routes tasks through
specialized controllers and modular tools.
"""
import os
import sys
import importlib
import inspect
from backend.file_controller import FileController
from backend.ai_controller import AIController
from backend.transformer_controller import TransformerController
from backend.modules.sliding_window import SlidingWindow
from backend.modules.db_schema import init_db
from backend.tools.base_tool import BaseTool


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
        """Initialize the database, spin up controllers, and auto-discover tools."""
        self.log("Initializing context database...")
        init_db()

        self.log("Registering FileController...")
        self.controllers["file"] = FileController(self.project_root, self.log)

        self.log("Registering AIController...")
        self.controllers["ai"] = AIController(self.log)

        self.log("Registering TransformerController...")
        self.controllers["transformer"] = TransformerController(self.project_root, self.log)

        self.log("Auto-discovering tools...")
        self._discover_and_load_tools()

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

    # ── Tool Auto-Discovery ────────────────────────────────

    def _discover_and_load_tools(self):
        """
        Auto-discover and load all tools from src/backend/tools/.
        Each tool must be a BaseTool subclass in its own .py file.
        """
        tools_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "tools"
        )

        if not os.path.isdir(tools_dir):
            self.log("No tools directory found.")
            return

        # Discover tool modules
        for filename in os.listdir(tools_dir):
            if not filename.endswith(".py") or filename.startswith("_"):
                continue

            module_name = filename[:-3]  # Remove .py

            try:
                # Dynamically import the module
                spec = importlib.util.spec_from_file_location(
                    f"backend.tools.{module_name}",
                    os.path.join(tools_dir, filename),
                )
                if not spec or not spec.loader:
                    continue

                module = importlib.util.module_from_spec(spec)
                sys.modules[spec.name] = module
                spec.loader.exec_module(module)

                # Find BaseTool subclasses in the module
                for name, obj in inspect.getmembers(module):
                    if (
                        inspect.isclass(obj)
                        and issubclass(obj, BaseTool)
                        and obj is not BaseTool
                    ):
                        # Instantiate and register the tool
                        tool = obj(log=self.log)

                        # Initialize the tool
                        if not tool.initialize():
                            self.log(f"  ✗ {tool.name} initialization failed")
                            continue

                        # Register by tool name (lowercase, no spaces)
                        tool_key = tool.name.lower().replace(" ", "_")
                        self.controllers[tool_key] = tool
                        self.log(f"  ✓ Loaded: {tool.name} (v{tool.version})")

            except Exception as e:
                self.log(f"  ✗ Failed to load {module_name}: {e}")

    def list_tools(self):
        """Return a list of all available tools with metadata."""
        tools = {}
        for key, controller in self.controllers.items():
            if isinstance(controller, BaseTool):
                tools[key] = controller.get_metadata()
        return tools

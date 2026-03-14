"""
Boilerplate Tool – Template for creating new Dismantler tools.

Copy this file and customize it to create your own tool.
Save it in src/backend/tools/ and it will be auto-discovered.
"""
from backend.tools.base_tool import BaseTool
from typing import Dict, Any


class BoilerplateTool(BaseTool):
    """
    Template tool demonstrating the tool interface.

    Customize:
    1. Change class name to your tool name
    2. Update metadata (name, version, description, tags)
    3. Implement the handle() method
    4. Add helper methods as needed
    5. Save as src/backend/tools/my_tool_name.py
    """

    # ── Metadata ───────────────────────────────────────────
    name = "Boilerplate Tool"
    version = "1.0.0"
    description = "Template tool - customize this"
    tags = ["template", "example"]
    requires = []  # List external packages like ["requests", "numpy"]

    # ── Initialization ─────────────────────────────────────

    def initialize(self) -> bool:
        """
        Called once when tool is loaded.
        Perform setup here (check configs, init connections, etc).
        """
        self.log(f"Initializing {self.name}...")

        # Example: check dependencies
        ok, missing = self.validate_dependencies()
        if not ok:
            self.log(f"Missing dependencies: {missing}")
            return False

        # Your initialization code here
        self.log(f"{self.name} ready.")
        return super().initialize()

    # ── Main Handler ───────────────────────────────────────

    def handle(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the tool.

        Schema format:
        {
            "system": "boilerplate",  # Tool name (auto-set by BackendEngine)
            "action": "process",       # What to do
            "data": "...",            # Your custom fields
        }
        """
        action = schema.get("action")

        if action == "process":
            return self._process(schema)
        elif action == "info":
            return self.success(
                message="Tool info",
                metadata=self.get_metadata()
            )
        else:
            return self.error(f"Unknown action: {action}")

    # ── Action Handlers ────────────────────────────────────

    def _process(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process action.
        Override this to implement your tool's logic.
        """
        # Example validation
        ok, err = self.validate_schema(schema, required_keys=["data"])
        if not ok:
            return self.error(err)

        data = schema.get("data")

        # Your logic here
        result = self._do_work(data)

        return self.success(
            message="Processing complete",
            result=result
        )

    def _do_work(self, data):
        """
        Implement your tool's core logic here.
        """
        self.log(f"Processing: {data}")

        # Example: transform data
        return {
            "input": data,
            "output": str(data).upper(),  # Replace with real logic
        }

    # ── Shutdown ───────────────────────────────────────────

    def shutdown(self):
        """Called when tool is unloaded. Cleanup here."""
        self.log(f"Shutting down {self.name}...")


# ── Usage Example ──────────────────────────────────────
#
# In BackendEngine or UI:
#
#   result = backend.execute_task({
#       "system": "boilerplate",
#       "action": "process",
#       "data": "hello world"
#   })
#
#   # Returns:
#   # {
#   #     "status": "ok",
#   #     "message": "Processing complete",
#   #     "result": {"input": "hello world", "output": "HELLO WORLD"}
#   # }

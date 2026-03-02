"""
Base Tool Class – Standard interface for all Dismantler tools.
Every tool must inherit from this base class and implement the required methods.
"""
from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class BaseTool(ABC):
    """
    Abstract base class for all Dismantler tools.

    Tools are modular extensions that:
    - Perform domain-specific operations
    - Accept structured schemas as input
    - Return standardized result dicts
    - Are auto-discovered and registered by BackendEngine

    Example:
        class MyTool(BaseTool):
            name = "My Custom Tool"
            version = "1.0.0"
            description = "Does something useful"

            def handle(self, schema):
                return {"status": "ok", "result": ...}
    """

    # ── Tool Metadata (required in subclasses) ──────────────

    name: str = "Unnamed Tool"
    version: str = "0.1.0"
    description: str = "Tool description not provided"
    tags: List[str] = []
    requires: List[str] = []  # External dependencies like "requests", "numpy"

    # ── Lifecycle ──────────────────────────────────────────

    def __init__(self, log=None):
        """
        Initialize the tool.

        Args:
            log: Optional logging callback function
        """
        self.log = log or (lambda msg: None)
        self._initialized = False

    def initialize(self) -> bool:
        """
        Called once when the tool is loaded.
        Override to perform setup, dependency checks, etc.

        Returns:
            True if initialization successful, False otherwise.
        """
        self._initialized = True
        return True

    def shutdown(self):
        """Called when the tool is being unloaded. Cleanup here."""
        pass

    # ── Main Interface ─────────────────────────────────────

    @abstractmethod
    def handle(self, schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the tool with a structured input schema.

        Args:
            schema: Dictionary with tool-specific parameters.
                    Usually contains "action" key for multi-action tools.

        Returns:
            Dictionary with "status" key and result data:
            {
                "status": "ok" | "error",
                "message": "Optional message",
                ... other fields depend on the tool
            }
        """
        pass

    # ── Validation ─────────────────────────────────────────

    def validate_schema(self, schema: Dict, required_keys: List[str] = None) -> tuple[bool, Optional[str]]:
        """
        Validate that the schema has all required keys.

        Args:
            schema: Input schema to validate
            required_keys: List of keys that must be present

        Returns:
            (is_valid, error_message)
        """
        if not required_keys:
            required_keys = []

        for key in required_keys:
            if key not in schema:
                return False, f"Missing required key: {key}"

        return True, None

    def validate_dependencies(self) -> tuple[bool, List[str]]:
        """
        Check if all required external packages are installed.

        Returns:
            (all_available, list_of_missing)
        """
        missing = []
        for package in self.requires:
            try:
                __import__(package)
            except ImportError:
                missing.append(package)

        return len(missing) == 0, missing

    # ── Utilities ──────────────────────────────────────────

    def success(self, message: str = "OK", **kwargs) -> Dict[str, Any]:
        """Return a success response."""
        result = {"status": "ok", "message": message}
        result.update(kwargs)
        return result

    def error(self, message: str, **kwargs) -> Dict[str, Any]:
        """Return an error response."""
        self.log(f"ERROR: {message}")
        result = {"status": "error", "message": message}
        result.update(kwargs)
        return result

    def get_metadata(self) -> Dict[str, Any]:
        """Return tool metadata as a dictionary."""
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "tags": self.tags,
            "requires": self.requires,
            "initialized": self._initialized,
        }

from src._microservices.microservice_std_lib import service_metadata, service_endpoint
from typing import Dict, Any, Optional
from pathlib import Path


@service_metadata(
    name="FileSaverService",
    version="1.0.0",
    description="Safely writes text to a file inside a sandbox directory.",
    tags=["filesystem", "write", "utility"],
    capabilities=["filesystem:write"]
)
class FileSaverMS:
    """
    A minimal microservice that writes text to a file.
    It enforces strict sandboxing: the resolved path must remain inside base_dir.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        base_dir = self.config.get("base_dir")
        if not base_dir:
            raise ValueError("FileSaverMS requires a 'base_dir' for safety.")

        self.base_dir = Path(base_dir).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @service_endpoint(
        inputs={
            "relative_path": "str  # Path relative to sandbox root.",
            "content": "str  # Text to write to the file."
        },
        outputs={
            "success": "bool",
            "message": "str",
            "written_path": "str"
        },
        description="Writes text to a file inside the sandbox. Overwrites existing files.",
        tags=["action", "filesystem"],
        side_effects=["filesystem:write"]
    )
    def save_file(self, relative_path: str, content: str) -> Dict[str, Any]:
        """
        Write text to a file inside the sandbox.
        The path must remain inside base_dir after resolution.
        """

        try:
            # Resolve path inside sandbox
            target = (self.base_dir / relative_path).resolve()

            # Enforce sandbox boundary
            try:
                target.relative_to(self.base_dir)
            except ValueError:
                return {
                    "success": False,
                    "message": "Refused: path escapes sandbox.",
                    "written_path": ""
                }

            # Ensure parent directories exist
            target.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            with target.open("w", encoding="utf-8") as f:
                f.write(content)

            return {
                "success": True,
                "message": "File written successfully.",
                "written_path": str(target)
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Error writing file: {e}",
                "written_path": ""
            }


if __name__ == "__main__":
    svc = FileSaverMS(config={"base_dir": "./sandbox"})
    print("Service ready:", svc)


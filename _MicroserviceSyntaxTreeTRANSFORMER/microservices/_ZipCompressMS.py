from microservice_std_lib import service_metadata, service_endpoint
from typing import Dict, Any, Optional, List
from pathlib import Path
import zipfile
import os


@service_metadata(
    name="ZipperService",
    version="1.0.0",
    description="Zips all files in a directory with optional exclusion filters.",
    tags=["filesystem", "utility", "backup"],
    capabilities=["filesystem:read", "filesystem:write"]
)
class ZipperMS:
    """
    A simple microservice that zips all files in a directory.
    Exclusions are substring-based: if any exclusion string appears
    in the file or folder name, it is skipped.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

        base_dir = self.config.get("base_dir")
        self.base_dir: Optional[Path] = Path(base_dir).resolve() if base_dir else None

        self.allow_absolute_paths: bool = bool(
            self.config.get("allow_absolute_paths", False)
        )

    # -------------------------------------------------------------------------
    # Endpoint: zip a directory
    # -------------------------------------------------------------------------

    @service_endpoint(
        inputs={
            "target_dir": "str  # Directory to zip.",
            "output_zip": "str (optional)  # Output zip filename.",
            "exclusions": "list[str] (optional)  # Skip files containing these substrings."
        },
        outputs={
            "success": "bool",
            "message": "str",
            "zip_path": "str",
            "skipped": "list[str]",
            "included": "list[str]"
        },
        description="Zips all files in a directory, skipping any whose names contain exclusion substrings.",
        tags=["action", "filesystem"],
        side_effects=["filesystem:read", "filesystem:write"]
    )
    def zip_directory(
        self,
        target_dir: str,
        output_zip: Optional[str] = None,
        exclusions: Optional[List[str]] = None
    ) -> Dict[str, Any]:

        exclusions = exclusions or []

        # -------------------------------------------------------------
        # 1. Resolve directory path (sandbox-aware)
        # -------------------------------------------------------------
        try:
            raw_path = Path(target_dir)

            if self.base_dir:
                if raw_path.is_absolute() and not self.allow_absolute_paths:
                    return {
                        "success": False,
                        "message": "Absolute paths not allowed when sandboxing is enabled.",
                        "zip_path": "",
                        "skipped": [],
                        "included": []
                    }

                resolved_dir = (self.base_dir / raw_path).resolve() if not raw_path.is_absolute() else raw_path.resolve()

                try:
                    resolved_dir.relative_to(self.base_dir)
                except ValueError:
                    return {
                        "success": False,
                        "message": "Target directory escapes sandbox.",
                        "zip_path": "",
                        "skipped": [],
                        "included": []
                    }
            else:
                resolved_dir = raw_path.resolve()

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to resolve directory: {e}",
                "zip_path": "",
                "skipped": [],
                "included": []
            }

        if not resolved_dir.exists() or not resolved_dir.is_dir():
            return {
                "success": False,
                "message": f"Directory not found: {resolved_dir}",
                "zip_path": "",
                "skipped": [],
                "included": []
            }

        # -------------------------------------------------------------
        # 2. Determine output zip path
        # -------------------------------------------------------------
        if output_zip:
            zip_path = Path(output_zip)
            if not zip_path.is_absolute():
                zip_path = resolved_dir / zip_path
        else:
            zip_path = resolved_dir / "archive.zip"

        # If sandboxing is enabled, ensure zip output stays inside base_dir
        try:
            zip_path = zip_path.resolve()
        except Exception:
            zip_path = Path(str(zip_path)).resolve()

        if self.base_dir:
            try:
                zip_path.relative_to(self.base_dir)
            except ValueError:
                return {
                    "success": False,
                    "message": "Output zip path escapes sandbox.",
                    "zip_path": "",
                    "skipped": [],
                    "included": []
                }

        # Ensure output directory exists
        try:
            zip_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to create output directory: {e}",
                "zip_path": "",
                "skipped": [],
                "included": []
            }

        # -------------------------------------------------------------
        # 3. Walk directory and collect files
        # -------------------------------------------------------------
        included = []
        skipped = []

        try:
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(resolved_dir):
                    root_path = Path(root)

                    # Skip excluded directories
                    dirs[:] = [
                        d for d in dirs
                        if not any(ex in d for ex in exclusions)
                    ]

                    for file in files:
                        if any(ex in file for ex in exclusions):
                            skipped.append(str(root_path / file))
                            continue

                        full_path = root_path / file
                        arcname = full_path.relative_to(resolved_dir)

                        zf.write(full_path, arcname)
                        included.append(str(full_path))

        except Exception as e:
            return {
                "success": False,
                "message": f"Error creating zip: {e}",
                "zip_path": "",
                "skipped": skipped,
                "included": included
            }

        return {
            "success": True,
            "message": "Directory zipped successfully.",
            "zip_path": str(zip_path),
            "skipped": skipped,
            "included": included
        }


if __name__ == "__main__":
    svc = ZipperMS()
    print("Service ready:", svc)



from typing import Dict, Any, Optional
from pathlib import Path
import json

from microservice_std_lib import service_metadata, service_endpoint

from typing import Callable, Optional, Type

# NOTE:
# Do NOT import the patch engine from the UI module at import-time.
# That creates circular imports (UI -> ToolsMS -> TokenizingPatcherMS -> UI).
# Instead, we lazy-load on demand, or allow injection via config.


@service_metadata(
    name="TokenizingPatcherService",
    version="1.0.0",
    description=(
        "Applies structured JSON patch hunks to a target text file using the "
        "_TokenizingPATCHER engine (indentation-aware, non-overlapping, deterministic)."
    ),
    tags=["patching", "filesystem", "refactor", "automation"],
    capabilities=[
        "filesystem:read",
        "filesystem:write"
    ]
)
class TokenizingPatcherMS:
    """
    Microservice wrapper around the _TokenizingPATCHER core logic.

    This service is designed to:
    - Accept a target file path and a JSON patch schema.
    - Use the existing `apply_patch_text` engine for deterministic patching.
    - Optionally run as a dry run (no write).
    - Destructively overwrite the target file when requested (for sandbox use).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Optional config keys (all are optional):

        - base_dir: str
            If set, all target paths are resolved relative to this directory.
            Useful for sandboxing. Example: "/sandbox/workspace"

        - default_force_indent: bool
            Default for force_indent when the endpoint caller does not specify it.
            (Defaults to False if not provided.)

        - allow_absolute_paths: bool
            If False (default), absolute paths are rejected when base_dir is set,
            to enforce sandboxing. If True, caller can pass absolute paths.

        - patch_engine: callable
            Optional injection point for the patch engine function.
            Signature: (original_text: str, patch_obj: dict, global_force_indent: bool) -> str

        - patch_error_type: Exception type
            Optional injection point for the patch engine's expected exception class.
        """
        self.config = config or {}

        base_dir = self.config.get("base_dir")
        self.base_dir: Optional[Path] = Path(base_dir).resolve() if base_dir else None

        self.default_force_indent: bool = bool(
            self.config.get("default_force_indent", False)
        )
        self.allow_absolute_paths: bool = bool(
            self.config.get("allow_absolute_paths", False)
        )

        self._patch_engine: Optional[Callable[..., str]] = self.config.get("patch_engine")
        self._patch_error_type: Optional[Type[BaseException]] = self.config.get("patch_error_type")

    # -------------------------------------------------------------------------
    # Core endpoint: apply patch to a file
    # -------------------------------------------------------------------------

    @service_endpoint(
        inputs={
            "target_path": "str  # Relative or absolute path to the file to patch.",
            "patch_schema": (
                "str  # JSON string matching the _TokenizingPATCHER schema "
                "with a top-level 'hunks' list."
            ),
            "force_indent": (
                "bool (optional)  # If true, use patch indentation as-is; "
                "otherwise adapt indentation relative to target file."
            ),
            "dry_run": "bool (optional)  # If true, do not write back to disk.",
            "return_preview": (
                "bool (optional)  # If true, include patched text in response "
                "even for destructive runs."
            ),
        },
        outputs={
            "success": "bool",
            "message": "str",
            "target_path": "str",
            "dry_run": "bool",
            "force_indent_used": "bool",
            "written": "bool  # True if file was actually overwritten.",
            "patched_preview": "str (optional)  # May be omitted for large files.",
        },
        description=(
            "Apply a structured JSON patch to a target file using the "
            "_TokenizingPATCHER engine. Supports dry runs and destructive "
            "overwrites, with optional sandboxing via service config."
        ),
        tags=["action", "patch", "filesystem"],
        side_effects=[
            "filesystem:read",
            "filesystem:write"
        ]
    )
    def apply_patch_to_file(
        self,
        target_path: str,
        patch_schema: str,
        force_indent: Optional[bool] = None,
        dry_run: bool = False,
        return_preview: bool = True,
    ) -> Dict[str, Any]:
        """
        Apply patch hunks defined in `patch_schema` to the file at `target_path`.

        - Reads the target file from disk.
        - Parses the JSON schema into a patch object.
        - Uses `apply_patch_text(...)` to compute the new text.
        - Writes back to the SAME file when not in dry_run mode.
        - Returns a structured result describing what happened.
        """

        # -------------------------------------------------------------
        # 1. Resolve target path (respecting optional sandboxing)
        # -------------------------------------------------------------
        try:
            raw_path = Path(target_path)

            # Enforce sandboxing when base_dir is configured
            if self.base_dir:
                if raw_path.is_absolute():
                    if not self.allow_absolute_paths:
                        return {
                            "success": False,
                            "message": (
                                "Absolute paths are not allowed when 'base_dir' is configured. "
                                "Pass a path relative to the sandbox."
                            ),
                            "target_path": str(raw_path),
                            "dry_run": dry_run,
                            "force_indent_used": bool(
                                self.default_force_indent if force_indent is None else force_indent
                            ),
                            "written": False,
                        }
                    resolved_target = raw_path.resolve()
                else:
                    resolved_target = (self.base_dir / raw_path).resolve()

                # Optional: enforce that resolved_target stays inside base_dir
                try:
                    resolved_target.relative_to(self.base_dir)
                except ValueError:
                    return {
                        "success": False,
                        "message": (
                            "Resolved target path escapes the configured base_dir sandbox. "
                            "Refusing to patch."
                        ),
                        "target_path": str(resolved_target),
                        "dry_run": dry_run,
                        "force_indent_used": bool(
                            self.default_force_indent if force_indent is None else force_indent
                        ),
                        "written": False,
                    }
            else:
                # No base_dir configured; trust the caller
                resolved_target = raw_path.resolve()

        except Exception as e:
            return {
                "success": False,
                "message": f"Failed to resolve target path: {e}",
                "target_path": target_path,
                "dry_run": dry_run,
                "force_indent_used": bool(
                    self.default_force_indent if force_indent is None else force_indent
                ),
                "written": False,
            }

        # -------------------------------------------------------------
        # 2. Read target file
        # -------------------------------------------------------------
        try:
            with resolved_target.open("r", encoding="utf-8") as f:
                original_text = f.read()
        except FileNotFoundError:
            return {
                "success": False,
                "message": f"Target file not found: {resolved_target}",
                "target_path": str(resolved_target),
                "dry_run": dry_run,
                "force_indent_used": bool(
                    self.default_force_indent if force_indent is None else force_indent
                ),
                "written": False,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error reading target file: {e}",
                "target_path": str(resolved_target),
                "dry_run": dry_run,
                "force_indent_used": bool(
                    self.default_force_indent if force_indent is None else force_indent
                ),
                "written": False,
            }

        # -------------------------------------------------------------
        # 3. Parse patch schema JSON
        # -------------------------------------------------------------
        try:
            patch_obj = json.loads(patch_schema)
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "message": f"Patch schema is not valid JSON: {e}",
                "target_path": str(resolved_target),
                "dry_run": dry_run,
                "force_indent_used": bool(
                    self.default_force_indent if force_indent is None else force_indent
                ),
                "written": False,
            }

        # -------------------------------------------------------------
        # 4. Apply patch using core engine
        # -------------------------------------------------------------
        force_indent_used = (
            self.default_force_indent if force_indent is None else bool(force_indent)
        )

        # Lazy-load engine if not injected
        patch_engine = self._patch_engine
        patch_error_type = self._patch_error_type

        if patch_engine is None:
            # Prefer the repo's UI module path (src.app) if available
            try:
                from src.app import apply_patch_text as _apply_patch_text  # type: ignore
                from src.app import PatchError as _PatchError  # type: ignore
                patch_engine = _apply_patch_text
                patch_error_type = _PatchError
            except Exception as e:
                return {
                    "success": False,
                    "message": (
                        "Patch engine not available. Provide config.patch_engine / config.patch_error_type "
                        "or ensure src.app exports apply_patch_text and PatchError. "
                        f"Import error: {e}"
                    ),
                    "target_path": str(resolved_target),
                    "dry_run": dry_run,
                    "force_indent_used": force_indent_used,
                    "written": False,
                }

        try:
            new_text = patch_engine(
                original_text,
                patch_obj,
                global_force_indent=force_indent_used,
            )
        except Exception as e:
            if patch_error_type and isinstance(e, patch_error_type):
                return {
                    "success": False,
                    "message": f"Patch engine failure: {e}",
                    "target_path": str(resolved_target),
                    "dry_run": dry_run,
                    "force_indent_used": force_indent_used,
                    "written": False,
                }
            return {
                "success": False,
                "message": f"Unexpected error during patching: {e}",
                "target_path": str(resolved_target),
                "dry_run": dry_run,
                "force_indent_used": force_indent_used,
                "written": False,
            }

        # -------------------------------------------------------------
        # 5. Optionally write back to disk (destructive overwrite)
        # -------------------------------------------------------------
        written = False
        if not dry_run:
            try:
                with resolved_target.open("w", encoding="utf-8") as f:
                    f.write(new_text)
                written = True
            except Exception as e:
                return {
                    "success": False,
                    "message": f"Failed to write patched file: {e}",
                    "target_path": str(resolved_target),
                    "dry_run": dry_run,
                    "force_indent_used": force_indent_used,
                    "written": False,
                }

        # -------------------------------------------------------------
        # 6. Build response payload
        # -------------------------------------------------------------
        result: Dict[str, Any] = {
            "success": True,
            "message": (
                "Dry run successful; patch applies cleanly."
                if dry_run
                else "Patch applied and file overwritten successfully."
            ),
            "target_path": str(resolved_target),
            "dry_run": dry_run,
            "force_indent_used": force_indent_used,
            "written": written,
        }

        if return_preview:
            # In dry_run mode, preview is the only observable side effect
            # In destructive mode, this is still useful for logging/inspection
            result["patched_preview"] = new_text

        return result


if __name__ == "__main__":
    # Standard independent test block for the catalogue
    svc = TokenizingPatcherMS(
        config={
            # Example: point this at a known sandbox root
            # "base_dir": "/path/to/sandbox",
            # "default_force_indent": False,
            # "allow_absolute_paths": False,
        }
    )
    print("Service ready:", svc)
    # Example manual smoke test (adjust paths and patch as needed):
    #
    # dummy_patch = json.dumps({
    #     "hunks": [
    #         {
    #             "description": "Example no-op hunk",
    #             "search_block": "original text",
    #             "replace_block": "modified text",
    #             "use_patch_indent": False
    #         }
    #     ]
    # })
    # print(
    #     svc.apply_patch_to_file(
    #         target_path="relative/or/absolute/path/to/file.py",
    #         patch_schema=dummy_patch,
    #         dry_run=True,
    #         return_preview=True,
    #     )
    # )



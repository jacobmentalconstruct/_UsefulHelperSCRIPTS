import ast
import os
import json
from typing import Dict, Any, List

# Import your existing patcher engine
from src._microservices._TokenizingPatcherMS import TokenizingPatcherMS

class MicroserviceTools:
    """
    The 'Cartridge' tools for the Microservice Refactor Domain.
    These are deterministic functions that the AI or Orchestrator can call.
    """

    def __init__(self, base_dir: str):
        self.base_dir = base_dir
        # Initialize the mechanical patcher once
        self.patcher = TokenizingPatcherMS(config={
            "base_dir": base_dir,
            "default_force_indent": False,
            "allow_absolute_paths": False
        })

    # --- THE SCOUT (Parser) ---
    def scan_file_structure(self, file_path: str) -> Dict[str, Any]:
        """
        Reads a Python file and extracts structured metadata via AST.
        Replaces the old 'ParserRole'.
        """
        # Resolve path inside the configured base_dir
        full_path = os.path.join(self.base_dir, file_path)
        if not os.path.exists(full_path):
            return {"error": f"File not found: {file_path} (resolved: {full_path})"}

        with open(full_path, "r", encoding="utf-8") as f:
            source = f.read()

        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            return {"error": f"Syntax Error: {e}"}

        ir = {
            "file_path": file_path,
            "imports": [],
            "classes": [],
            "functions": []
        }

        for node in tree.body:
            # Extract Imports
            if isinstance(node, ast.Import):
                for alias in node.names:
                    ir["imports"].append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    ir["imports"].append(f"{module}.{alias.name}")
            
            # Extract Classes (Potential Services)
            elif isinstance(node, ast.ClassDef):
                class_info = {"name": node.name, "decorators": []}
                for deco in node.decorator_list:
                    if isinstance(deco, ast.Call) and hasattr(deco.func, "id"):
                        class_info["decorators"].append(deco.func.id)
                ir["classes"].append(class_info)

            # Extract Functions (Potential Endpoints)
            elif isinstance(node, ast.FunctionDef):
                ir["functions"].append(node.name)

        return ir

    # --- THE SURGEON (Patcher) ---
    def apply_patch(self, file_path: str, patch_json_str: str, dry_run: bool = True) -> Dict[str, Any]:
        """
        Applies a JSON patch to a file.
        Replaces 'PatchRole._apply_patch'.

        This tool is intentionally defensive:
        - If the model returns markdown fences (```json ... ```), it will extract the JSON object.
        - If the model returns an empty object ({}), it will fail with a schema error.
        """

        def _extract_json_object(text: str) -> str:
            """Return the first {...} JSON object substring, or "" if not found."""
            if not text:
                return ""
            s = text.strip()

            # Remove common markdown code fences
            if s.startswith("```"):
                # Strip leading fence line
                first_nl = s.find("\n")
                if first_nl != -1:
                    s = s[first_nl + 1 :]
                # Strip trailing fence
                if s.rstrip().endswith("```"):
                    s = s.rstrip()
                    s = s[: -3]
                s = s.strip()

            # Extract the largest valid JSON object block
            start = s.find("{")
            end = s.rfind("}")
            if start == -1 or end == -1 or end < start:
                return ""
            
            # Return the raw slice for json.loads to handle final validation
            return s[start : end + 1].strip()

        try:
            # Normalize incoming patch schema
            patch_obj = None

            if isinstance(patch_json_str, dict):
                patch_obj = patch_json_str
            elif isinstance(patch_json_str, str):
                extracted = _extract_json_object(patch_json_str)
                if not extracted:
                    return {
                        "success": False,
                        "message": "Patch schema did not contain a JSON object. Output must be a JSON object with top-level 'hunks'.",
                    }
                try:
                    patch_obj = json.loads(extracted)
                except json.JSONDecodeError as e:
                    return {
                        "success": False,
                        "message": f"Patch schema is not valid JSON after extraction: {e}",
                    }
            else:
                return {
                    "success": False,
                    "message": "Patch schema must be a JSON string or dict.",
                }

            # Validate required schema
            if not isinstance(patch_obj, dict) or "hunks" not in patch_obj or not isinstance(patch_obj.get("hunks"), list):
                return {
                    "success": False,
                    "message": "Patch schema must be a JSON object with a top-level 'hunks' list.",
                }

            # Re-serialize to a clean JSON string for the patcher
            clean_schema_str = json.dumps(patch_obj)

            result = self.patcher.apply_patch_to_file(
                target_path=file_path,
                patch_schema=clean_schema_str,
                dry_run=dry_run,
                return_preview=True,
            )
            return result

        except Exception as e:
            return {"success": False, "message": str(e)}

    # --- THE JANITOR (Helpers) ---
    def generate_cleanup_patch(self) -> str:
        """
        Returns the standard regex cleanup patch for this domain.
        Replaces 'PatchRole._generate_patch_hunk(final_cleanup)'.
        """
        cleanup_hunks = [
            {
                "description": "Collapse double blank lines",
                "search_block": "\n\n\n",
                "replace_block": "\n\n",
                "use_patch_indent": False
            }
        ]
        return json.dumps({"hunks": cleanup_hunks})




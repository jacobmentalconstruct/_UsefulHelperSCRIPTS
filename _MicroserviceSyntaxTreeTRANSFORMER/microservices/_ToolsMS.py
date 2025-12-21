import ast
import os
import json
from typing import Dict, Any, List

# Import your existing patcher engine
from microservices._TokenizingPatcherMS import TokenizingPatcherMS

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
        full_path = os.path.join(self.base_dir, file_path)
        if not os.path.exists(full_path):
            return {"error": f"File not found: {file_path}"}

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
        """
        try:
            # Verify JSON validity before passing to engine
            if isinstance(patch_json_str, str):
                # Ensure it's valid JSON
                json.loads(patch_json_str)
            
            result = self.patcher.apply_patch_to_file(
                target_path=file_path,
                patch_schema=patch_json_str,
                dry_run=dry_run,
                return_preview=True
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

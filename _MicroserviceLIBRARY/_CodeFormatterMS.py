"""
SERVICE_NAME: _CodeFormatterMS
ENTRY_POINT: _CodeFormatterMS.py
DEPENDENCIES: None
"""

import re
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from microservice_std_lib import service_metadata, service_endpoint

logger = logging.getLogger("CodeFormatter")

# ==============================================================================
# LOGIC ENGINE (Extracted from IndentArchitect)
# ==============================================================================

class WhitespaceEngine:
    """
    Parses code into a granular map of (Indent + Content + Trailing).
    Can Normalize structure and generate 'Hunk' patches.
    """
    def __init__(self):
        self.raw_lines = []
        self.nodes = []
        self.normalized_text = ""
        self.patch_data = {"hunks": []}

    def load_source(self, text):
        self.raw_lines = text.splitlines()
        self.nodes = []
        
        # State trackers
        indent_stack = [0] # Stack of indentation widths
        last_line_was_block_starter = False # Did previous line end with ':'?
        
        for i, line in enumerate(self.raw_lines):
            # 1. Parse content
            match = re.match(r"^([ \t]*)(.*?)([ \t]*)$", line)
            if not match:
                self.nodes.append({"id": i, "indent": "", "content": line, "depth": 0, "is_empty": True})
                continue
            
            indent, content, trailing = match.groups()
            is_empty = (len(content) == 0)
            
            # 2. Calculate Raw Width (Tab = 4 spaces)
            current_width = 0
            for char in indent:
                current_width += 4 if char == '\t' else 1

            # 3. Determine Depth
            if is_empty:
                # Empty lines preserve the current context
                depth = len(indent_stack) - 1
            else:
                # --- THE COLON GUARD ---
                # Logic: Should we indent deeper?
                if current_width > indent_stack[-1]:
                    if last_line_was_block_starter:
                        # Legitimate block entry
                        indent_stack.append(current_width)
                    else:
                        # "False Nesting" detected (Staircase Effect). 
                        pass 

                # Logic: Should we dedent?
                while len(indent_stack) > 1 and current_width < indent_stack[-1]:
                    indent_stack.pop()
                
                depth = len(indent_stack) - 1
                
                # Update tracker for NEXT line
                clean_content = content.split("#")[0].strip()
                last_line_was_block_starter = clean_content.endswith(":")

            self.nodes.append({
                "id": i,
                "raw_indent": indent,
                "depth": depth, 
                "content": content,
                "trailing": trailing,
                "is_empty": is_empty
            })

    def normalize(self, use_tabs=False, space_count=4):
        """Reconstructs the code with strict indentation rules."""
        char = "\t" if use_tabs else (" " * space_count)
        clean_lines = []
        
        for node in self.nodes:
            if node["is_empty"]:
                clean_lines.append("") # Strip whitespace on empty lines
            else:
                new_indent = char * node["depth"]
                clean_lines.append(f"{new_indent}{node['content']}")
        
        self.normalized_text = "\n".join(clean_lines)
        return self.normalized_text

    def generate_patch(self):
        """Compares Raw vs Normalized and generates JSON Schema Hunks."""
        clean_lines = self.normalized_text.splitlines()
        if not clean_lines: 
            return {"hunks": []}

        hunks = []
        current_hunk = None
        
        for i, (raw, clean) in enumerate(zip(self.raw_lines, clean_lines)):
            if raw != clean:
                if current_hunk is None:
                    current_hunk = {
                        "start_line": i,
                        "raw_block": [raw],
                        "clean_block": [clean]
                    }
                else:
                    # Check continuity
                    if i == current_hunk["start_line"] + len(current_hunk["raw_block"]):
                        current_hunk["raw_block"].append(raw)
                        current_hunk["clean_block"].append(clean)
                    else:
                        self._finalize_hunk(hunks, current_hunk)
                        current_hunk = {
                            "start_line": i,
                            "raw_block": [raw],
                            "clean_block": [clean]
                        }
            else:
                if current_hunk:
                    self._finalize_hunk(hunks, current_hunk)
                    current_hunk = None

        if current_hunk:
            self._finalize_hunk(hunks, current_hunk)

        self.patch_data = {"hunks": hunks}
        return self.patch_data

    def _finalize_hunk(self, hunks_list, hunk_data):
        search_txt = "\n".join(hunk_data["raw_block"])
        replace_txt = "\n".join(hunk_data["clean_block"])
        schema_hunk = {
            "description": f"Normalize indentation (Lines {hunk_data['start_line']}-{hunk_data['start_line'] + len(hunk_data['raw_block'])})",
            "search_block": search_txt,
            "replace_block": replace_txt
        }
        hunks_list.append(schema_hunk)


# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="CodeFormatter",
    version="1.0.0",
    description="The Architect: Intelligent whitespace normalization and structural repair engine.",
    tags=["formatting", "code", "utility"],
    capabilities=["compute", "filesystem:write"]
)
class CodeFormatterMS:
    """
    The Architect.
    Uses the WhitespaceEngine to enforce strict indentation rules, 
    fixing 'staircase' formatting and mixed tabs/spaces.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @service_endpoint(
        inputs={"content": "str", "use_tabs": "bool", "spaces": "int"},
        outputs={"normalized": "str", "patch": "Dict"},
        description="Takes raw code and returns the normalized version plus a JSON patch of changes.",
        tags=["formatting", "compute"],
        side_effects=[]
    )
    def normalize_code(self, content: str, use_tabs: bool = False, spaces: int = 4) -> Dict[str, Any]:
        """
        Pure logic endpoint: Takes string, returns string + patch.
        Does not touch the filesystem.
        """
        engine = WhitespaceEngine()
        engine.load_source(content)
        normalized = engine.normalize(use_tabs=use_tabs, space_count=spaces)
        patch = engine.generate_patch()
        
        return {
            "normalized": normalized,
            "patch": patch
        }

    @service_endpoint(
        inputs={"file_path": "str", "use_tabs": "bool", "spaces": "int"},
        outputs={"status": "str", "changes": "int"},
        description="Reads a file, normalizes it, and overwrites it if changes are needed.",
        tags=["formatting", "filesystem"],
        side_effects=["filesystem:read", "filesystem:write"]
    )
    def format_file(self, file_path: str, use_tabs: bool = False, spaces: int = 4) -> Dict[str, Any]:
        """
        Filesystem endpoint: In-place repair of a file.
        """
        path = Path(file_path).resolve()
        if not path.exists():
            return {"status": "error", "message": "File not found"}
            
        try:
            content = path.read_text(encoding="utf-8")
            
            engine = WhitespaceEngine()
            engine.load_source(content)
            normalized = engine.normalize(use_tabs=use_tabs, space_count=spaces)
            patch = engine.generate_patch()
            
            changes = len(patch["hunks"])
            
            if changes > 0:
                path.write_text(normalized, encoding="utf-8")
                logger.info(f"Formatted {path.name}: {changes} hunks applied.")
                return {"status": "modified", "changes": changes}
            else:
                return {"status": "clean", "changes": 0}
                
        except Exception as e:
            logger.error(f"Formatting failed for {path}: {e}")
            return {"status": "error", "message": str(e)}


# --- Independent Test Block ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    svc = CodeFormatterMS()
    print("Service ready:", svc)
    
    # Test with broken indentation
    broken_code = """
def hello():
  print("Indented with 2 spaces")
      print("Suddenly 6 spaces!")
    """
    print("\n--- Processing Broken Code ---")
    result = svc.normalize_code(broken_code, spaces=4)
    
    print(f"Hunks Detected: {len(result['patch']['hunks'])}")
    print("\n--- Normalized Output ---")
    print(result['normalized'])

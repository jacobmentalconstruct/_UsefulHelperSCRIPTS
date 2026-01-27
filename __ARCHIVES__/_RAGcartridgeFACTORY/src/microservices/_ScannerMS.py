"""
SERVICE_NAME: _ScannerMS
ENTRY_POINT: _ScannerMS.py
DEPENDENCIES: None
"""

import os
import time
from typing import Dict, List, Any, Optional
from microservice_std_lib import service_metadata, service_endpoint
# [FIX] Import BaseService
from base_service import BaseService

@service_metadata(
    name="ScannerMS",
    version="1.0.0",
    description="Recursively scans directories, filters junk, and detects binaries.",
    tags=["filesystem", "scanner", "tree"],
    capabilities=["filesystem:read"],
    dependencies=["os", "time"],
    side_effects=["filesystem:read"]
)
class ScannerMS(BaseService):
    """
    The Scanner: Walks the file system, filters junk, and detects binary files.
    Generates the tree structure used by the UI.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("ScannerMS")
        self.config = config or {}

        # Folders to completely ignore (Standard developer noise)
        self.IGNORE_DIRS = {
            '.git', '__pycache__', 'node_modules', 'venv', '.env',
            '.idea', '.vscode', 'dist', 'build', 'coverage'
        }

        # Extensions that are explicitly binary/junk
        self.BINARY_EXTENSIONS = {
            '.pyc', '.pyd', '.exe', '.dll', '.so', '.dylib', '.class',
            '.jpg', '.png', '.gif', '.ico', '.zip', '.tar', '.gz'
        }

    @service_endpoint(
        inputs={"path": "str", "depth": "int"},
        outputs={"tree": "Dict"},
        description="Scans the target directory and returns a nested dictionary tree of valid files.",
        tags=["filesystem", "scan"],
        side_effects=["filesystem:read"]
    )
    def scan_directory(self, path: str, depth: int = 0) -> Dict[str, Any]:
        """
        Recursively scans a directory, building a tree.
        Excludes ignored directories and binary files.
        """
        if not os.path.exists(path):
            self.log_error(f"Path not found: {path}")
            return {}

        root_name = os.path.basename(path) or path
        tree = {
            "name": root_name,
            "path": path,
            "type": "folder",
            "children": []
        }

        try:
            with os.scandir(path) as it:
                # Sort: Folders first, then files
                entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
                
                for entry in entries:
                    # 1. Skip Ignore List
                    if entry.name in self.IGNORE_DIRS:
                        continue
                    
                    # 2. Handle Directories
                    if entry.is_dir():
                        # Recurse
                        child_tree = self.scan_directory(entry.path, depth + 1)
                        if child_tree: # Only add if not empty (optional, but cleaner)
                            tree["children"].append(child_tree)

                    # 3. Handle Files
                    elif entry.is_file():
                        # Skip binaries
                        _, ext = os.path.splitext(entry.name)
                        if ext.lower() in self.BINARY_EXTENSIONS:
                            continue
                            
                        tree["children"].append({
                            "name": entry.name,
                            "path": entry.path,
                            "type": "file",
                            "size": entry.stat().st_size
                        })

        except PermissionError:
            self.log_warning(f"Permission denied: {path}")

        return tree

    @service_endpoint(
        inputs={"tree_node": "Dict"},
        outputs={"files": "List[str]"},
        description="Flattens a tree node into a list of file paths.",
        tags=["filesystem", "utility"],
        side_effects=[]
    )
    def flatten_tree(self, tree_node: Dict[str, Any]) -> List[str]:
        """
        Helper to extract all valid file paths from a tree node 
        (e.g., when the user clicks 'Start Ingest').
        """
        files = []
        
        if not tree_node:
            return []

        if tree_node.get('type') == 'file':
            files.append(tree_node['path'])

        elif tree_node.get('type') == 'folder' and 'children' in tree_node:
            for child in tree_node['children']:
                files.extend(self.flatten_tree(child))

        return files

# --- Independent Test Block ---
if __name__ == "__main__":
    scanner = ScannerMS()
    print("Service ready:", scanner._service_info)

    # Scan the current directory
    cwd = os.getcwd()
    print(f"Scanning: {cwd} ...")

    start_time = time.time()
    tree = scanner.scan_directory(cwd)
    duration = time.time() - start_time

    if tree:
        file_count = len(scanner.flatten_tree(tree))
        print(f"Scan complete in {duration:.4f}s")
        print(f"Found {file_count} files.")
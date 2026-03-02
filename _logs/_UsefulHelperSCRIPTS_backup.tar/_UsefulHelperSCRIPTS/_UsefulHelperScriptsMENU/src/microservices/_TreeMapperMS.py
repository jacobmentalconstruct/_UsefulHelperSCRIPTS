import os
import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Set, Optional

from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION
# ==============================================================================
DEFAULT_EXCLUDES = {
    '.git', '__pycache__', '.idea', '.vscode', 'node_modules', 
    '.venv', 'env', 'venv', 'dist', 'build', '.DS_Store'
}
logger = logging.getLogger("TreeMapper")

# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="TreeMapper",
    version="1.0.0",
    description="Generates ASCII-art style directory maps of the file system.",
    tags=["filesystem", "map", "visualization"],
    capabilities=["filesystem:read"]
)
class TreeMapperMS:
    """
    The Cartographer: Generates ASCII-art style directory maps.
    Useful for creating context snapshots for LLMs.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @service_endpoint(
        inputs={"root_path": "str", "additional_exclusions": "Set[str]", "use_default_exclusions": "bool"},
        outputs={"tree_map": "str"},
        description="Generates an ASCII tree map of the directory.",
        tags=["filesystem", "visualization"],
        side_effects=["filesystem:read"]
    )
    def generate_tree(self, 
                      root_path: str, 
                      additional_exclusions: Optional[Set[str]] = None,
                      use_default_exclusions: bool = True) -> str:
        
        start_path = Path(root_path).resolve()
        if not start_path.exists(): 
            return f"Error: Path '{root_path}' does not exist."

        exclusions = set()
        if use_default_exclusions:
            exclusions.update(DEFAULT_EXCLUDES)
        if additional_exclusions:
            exclusions.update(additional_exclusions)

        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        lines = [
            f"Project Map: {start_path.name}",
            f"Generated: {timestamp}",
            "-" * 40,
            f"📁 {start_path.name}/"
        ]

        logger.info(f"Mapping directory: {start_path}")
        self._walk(start_path, "", lines, exclusions)
        return "\n".join(lines)

    def _walk(self, directory: Path, prefix: str, lines: List[str], exclusions: Set[str]):
        try:
            # Sort: Directories first, then files (alphabetical)
            children = sorted(
                [p for p in directory.iterdir() if p.name not in exclusions],
                key=lambda x: (not x.is_dir(), x.name.lower())
            )
        except PermissionError:
            lines.append(f"{prefix}└── 🚫 [Permission Denied]")
            return

        count = len(children)
        for index, path in enumerate(children):
            is_last = (index == count - 1)
            connector = "└── " if is_last else "├── "
            
            if path.is_dir():
                lines.append(f"{prefix}{connector}📁 {path.name}/")
                extension = "    " if is_last else "│   "
                self._walk(path, prefix + extension, lines, exclusions)
            else:
                lines.append(f"{prefix}{connector}📄 {path.name}")


# --- Independent Test Block ---
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    svc = TreeMapperMS()
    print("Service ready:", svc)
    
    # Map the current directory
    print("\n--- Map of Current Dir ---")
    tree = svc.generate_tree(".", additional_exclusions={"__pycache__"})
    print(tree)
"""
SERVICE_NAME: _ContextPackerMS
ENTRY_POINT: __ContextPackerMS.py
DEPENDENCIES: None
"""

import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION
# ==============================================================================
DEFAULT_EXCLUDES = {
    '.git', '__pycache__', '.idea', '.vscode', 'node_modules', 
    'venv', '.venv', 'dist', 'build', '.DS_Store', 'file-dump.txt'
}

logger = logging.getLogger("ContextPacker")

# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="ContextPacker",
    version="1.0.0",
    description="Flattens a directory of source code into a single text file (useful for LLM context stuffing).",
    tags=["filesystem", "export", "utility"],
    capabilities=["filesystem:read", "filesystem:write"]
)
class ContextPackerMS:
    """
    The Packer: Walks a directory and dumps all text-readable files 
    into a single monolithic text file with delimiters.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @service_endpoint(
        inputs={"root_path": "str", "output_filename": "str", "additional_excludes": "Set[str]"},
        outputs={"output_path": "str", "file_count": "int"},
        description="Packs directory contents into a single text file.",
        tags=["export", "dump"],
        side_effects=["filesystem:read", "filesystem:write"]
    )
    def pack_directory(self, 
                       root_path: str, 
                       output_filename: str = "context_dump.txt", 
                       additional_excludes: Optional[Set[str]] = None) -> Dict[str, Any]:
        """
        Walks the directory and writes file contents to the output file.
        """
        root = Path(root_path).resolve()
        output_file = root / output_filename
        
        # Merge excludes
        excludes = DEFAULT_EXCLUDES.copy()
        if additional_excludes:
            excludes.update(additional_excludes)
            
        # Ensure we don't pack the output file itself if it already exists
        excludes.add(output_filename)

        count = 0
        logger.info(f"Packing context from {root} into {output_filename}...")

        try:
            with open(output_file, 'w', encoding='utf-8') as out_f:
                # Add Header
                out_f.write(f"CONTEXT PACKER DUMP\n")
                out_f.write(f"SOURCE: {root}\n")
                out_f.write("="*60 + "\n\n")

                for current_dir, dirs, files in os.walk(root):
                    # In-place modification of dirs to skip excluded folders during walk
                    dirs[:] = [d for d in dirs if d not in excludes and not d.startswith('.')]
                    
                    for file in files:
                        if file in excludes or file.startswith('.'):
                            continue
                            
                        file_path = Path(current_dir) / file
                        
                        # Process the file
                        self._append_file(file_path, root, out_f)
                        count += 1
                        
            return {
                "output_path": str(output_file),
                "file_count": count
            }
            
        except Exception as e:
            logger.error(f"Packing failed: {e}")
            raise

    def _append_file(self, file_path: Path, root: Path, out_f):
        """Helper to append a single file's content to the dump."""
        rel_path = file_path.relative_to(root)
        
        try:
            # Try reading as text
            content = file_path.read_text(encoding='utf-8')
            
            out_f.write(f"==================================================\n")
            out_f.write(f"FILE: {rel_path}\n")
            out_f.write(f"==================================================\n")
            out_f.write(content + "\n\n")
            
        except UnicodeDecodeError:
            # It's a binary file (image, pyc, etc.)
            out_f.write(f"==================================================\n")
            out_f.write(f"FILE: {rel_path} [SKIPPED - BINARY]\n")
            out_f.write(f"==================================================\n\n")
        except Exception as e:
            logger.warning(f"Could not read {rel_path}: {e}")


# --- Independent Test Block ---
if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')

    packer = ContextPackerMS()
    print("Service ready:", packer)
    
    # Run a test pack on the current folder
    print("\n--- Packing Current Directory ---")
    result = packer.pack_directory(".", "test_dump.txt")
    print(f"Packed {result['file_count']} files to: {result['output_path']}")

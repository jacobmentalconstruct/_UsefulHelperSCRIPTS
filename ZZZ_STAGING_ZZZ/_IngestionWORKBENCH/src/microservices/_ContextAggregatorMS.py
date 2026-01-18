"""
SERVICE_NAME: _ContextAggregatorMS
ENTRY_POINT: _ContextAggregatorMS.py
DEPENDENCIES: None
"""

import os
import fnmatch
import datetime
import logging
from pathlib import Path
from typing import Set, Optional, Dict, Any
from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# USER CONFIGURATION: DEFAULTS
# ==============================================================================
# Extensions known to be binary/non-text (Images, Archives, Executables)
DEFAULT_BINARY_EXTENSIONS = {
    ".tar.gz", ".gz", ".zip", ".rar", ".7z", ".bz2", ".xz", ".tgz",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".tif", ".tiff",
    ".mp3", ".wav", ".ogg", ".flac", ".mp4", ".mkv", ".avi", ".mov", ".webm",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx", ".exe", ".dll", ".so",
    ".db", ".sqlite", ".mdb", ".pyc", ".pyo", ".class", ".jar", ".wasm"
}

# Folders to ignore by default
DEFAULT_IGNORE_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv", ".env", 
    "dist", "build", "coverage", ".idea", ".vscode"
}

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("ContextAggregator")
# ==============================================================================

@service_metadata(
    name="ContextAggregator",
    version="1.0.0",
    description="Flattens a project folder into a single readable text file.",
    tags=["filesystem", "context", "compilation"],
    capabilities=["filesystem:read", "filesystem:write"],
    dependencies=["os", "fnmatch", "datetime"],
    side_effects=["filesystem:read", "filesystem:write"]
)
class ContextAggregatorMS:
    """
    The Context Builder: Flattens a project folder into a single readable text file.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        max_file_size_mb = self.config.get("max_file_size_mb", 1)
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    @service_endpoint(
        inputs={"root_path": "str", "output_file": "str", "extra_exclusions": "Set[str]", "use_default_exclusions": "bool"},
        outputs={"file_count": "int"},
        description="Aggregates project files into a single text dump.",
        tags=["filesystem", "dump"],
        side_effects=["filesystem:read", "filesystem:write"]
    )
    def aggregate(self, 
                  root_path: str, 
                  output_file: str, 
                  extra_exclusions: Optional[Set[str]] = None,
                  use_default_exclusions: bool = True) -> int:
        
        project_root = Path(root_path).resolve()
        out_path = Path(output_file).resolve()
        
        # Build Exclusions
        exclusions = set()
        if use_default_exclusions:
            exclusions.update(DEFAULT_IGNORE_DIRS)
        if extra_exclusions:
            exclusions.update(extra_exclusions)

        # Build Binary List
        binary_exts = DEFAULT_BINARY_EXTENSIONS.copy()
        
        file_count = 0
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        try:
            with open(out_path, "w", encoding="utf-8") as out_f:
                out_f.write(f"File Dump from Project: {project_root.name}\nGenerated: {timestamp}\n{'='*60}\n\n")

                for root, dirs, files in os.walk(project_root):
                    # In-place filtering of directories
                    dirs[:] = [d for d in dirs if d not in exclusions]
                    
                    for filename in files:
                        if self._should_exclude(filename, exclusions): continue

                        file_path = Path(root) / filename
                        if file_path.resolve() == out_path: continue

                        if self._is_safe_to_dump(file_path, binary_exts):
                            self._write_file_content(out_f, file_path, project_root)
                            file_count += 1                            
        except IOError as e:
            log.error(f"Error writing dump: {e}")
            
        return file_count

    def _should_exclude(self, filename: str, exclusions: Set[str]) -> bool:
        return any(fnmatch.fnmatch(filename, pattern) for pattern in exclusions)

    def _is_safe_to_dump(self, file_path: Path, binary_exts: Set[str]) -> bool:
        if "".join(file_path.suffixes).lower() in binary_exts: return False
        try:
            if file_path.stat().st_size > self.max_file_size_bytes: return False
            with open(file_path, 'rb') as f:
                if b'\0' in f.read(1024): return False
        except (IOError, OSError): return False
        return True

    def _write_file_content(self, out_f, file_path: Path, project_root: Path):
        relative_path = file_path.relative_to(project_root)
        header = f"\n{'-'*20} FILE: {relative_path} {'-'*20}\n"
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as in_f:
                out_f.write(header + in_f.read() + f"\n{'-'*60}\n")
        except Exception as e:
            out_f.write(f"\n[Error reading file: {e}]\n")

if __name__ == "__main__":
    svc = ContextAggregatorMS()
    print("Service ready:", svc)
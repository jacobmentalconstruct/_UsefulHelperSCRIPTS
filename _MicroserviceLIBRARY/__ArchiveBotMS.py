"""
SERVICE_NAME: _ArchiveBotMS
ENTRY_POINT: __ArchiveBotMS.py
DEPENDENCIES: None
"""

import datetime
import fnmatch
import logging
import os
import tarfile
from pathlib import Path
from typing import Any, Dict, Optional, Set, Tuple

from microservice_std_lib import service_metadata, service_endpoint, BaseService

# ==============================================================================
# CONFIGURATION
# ==============================================================================
SERVICE_TITLE = "ArchiveBot"
SERVICE_VERSION = "1.1.0"
LOG_LEVEL = logging.INFO

# Default exclusions (Dev artifacts, caches, system files)
DEFAULT_IGNORE_DIRS: Set[str] = {
    "node_modules", ".git", "__pycache__", ".venv", "venv", "env",
    ".mypy_cache", ".pytest_cache", ".idea", ".vscode", "dist",
    "build", "coverage", "target", "out", "bin", "obj"
}

DEFAULT_IGNORE_FILES: Set[str] = {
    ".DS_Store", "Thumbs.db", "*.pyc", "*.pyo", "*.log", "*.tmp"
}

logging.basicConfig(level=LOG_LEVEL, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(SERVICE_TITLE)

# ==============================================================================
# SERVICE DEFINITION
# ==============================================================================
@service_metadata(
    name=SERVICE_TITLE,
    version=SERVICE_VERSION,
    description="Creates timestamped .tar.gz backups of directory trees.",
    tags=["utility", "backup", "filesystem"],
    capabilities=["filesystem:read", "filesystem:write"],
    dependencies=["tarfile", "pathlib", "datetime"],
    side_effects=["filesystem:write"]
)
class ArchiveBotMS(BaseService):
    
    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(SERVICE_TITLE)
        self.config = config or {}

    @service_endpoint(
        inputs={
            "source_path": "str",
            "output_dir": "str",
            "extra_exclusions": "List[str]",
            "use_default_exclusions": "bool"
        },
        outputs={
            "archive_path": "str",
            "file_count": "int"
        },
        description="Compresses a directory into a .tar.gz archive.",
        tags=["action", "backup"],
        side_effects=["filesystem:write"]
    )
    def create_backup(
        self,
        source_path: str,
        output_dir: str,
        extra_exclusions: Optional[Set[str]] = None,
        use_default_exclusions: bool = True,
    ) -> Dict[str, Any]:
        
        src = Path(source_path).resolve()
        out = Path(output_dir).resolve()

        if not src.exists():
            logger.error(f"Source not found: {src}")
            raise FileNotFoundError(f"Source path does not exist: {src}")

        out.mkdir(parents=True, exist_ok=True)

        # Build exclusion set
        exclude_patterns: Set[str] = set()
        if use_default_exclusions:
            exclude_patterns.update(DEFAULT_IGNORE_DIRS)
            exclude_patterns.update(DEFAULT_IGNORE_FILES)
        if extra_exclusions:
            exclude_patterns.update(extra_exclusions)

        # Generate filename: backup_FOLDERNAME_YYYY-MM-DD_HH-MM-SS.tar.gz
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        archive_name = f"backup_{src.name}_{timestamp}.tar.gz"
        archive_path = out / archive_name

        file_count = 0

        try:
            with tarfile.open(archive_path, "w:gz") as tar:
                for root, dirs, files in os.walk(src):
                    # Filter directories in-place to prevent walking into them
                    dirs[:] = [d for d in dirs if not self._is_excluded(d, exclude_patterns)]

                    for file_name in files:
                        if self._is_excluded(file_name, exclude_patterns):
                            continue

                        full_path = Path(root) / file_name
                        
                        # Don't zip the file if we are writing it inside the source folder
                        if full_path == archive_path: 
                            continue

                        rel_path = full_path.relative_to(src)
                        tar.add(full_path, arcname=rel_path)
                        file_count += 1

            logger.info(f"Archive created: {archive_path} ({file_count} files)")
            return {
                "archive_path": str(archive_path),
                "file_count": file_count
            }

        except Exception as exc:
            logger.exception(f"Backup failed: {exc}")
            if archive_path.exists():
                try:
                    archive_path.unlink()
                except Exception: pass
            raise exc

    # --- Helpers ---
    def _is_excluded(self, name: str, patterns: Set[str]) -> bool:
        for pattern in patterns:
            if name == pattern or fnmatch.fnmatch(name, pattern):
                return True
        return False

# ==============================================================================
# SELF-TEST / RUNNER
# ==============================================================================
if __name__ == "__main__":
    import tempfile
    
    bot = ArchiveBotMS()
    print(f"Service Ready: {bot}")

    with tempfile.TemporaryDirectory() as tmp_source:
        with tempfile.TemporaryDirectory() as tmp_out:
            # Create a test file
            p = Path(tmp_source) / "test_file.txt"
            p.write_text("Hello Archive")
            
            print(f"Backing up {tmp_source} to {tmp_out}...")
            result = bot.create_backup(tmp_source, tmp_out)
            print(f"Result: {result}")
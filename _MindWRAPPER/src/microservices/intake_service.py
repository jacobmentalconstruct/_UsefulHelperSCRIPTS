import os
import mimetypes
from pathlib import Path
from typing import List, Dict
from .base_service import BaseService
from .cartridge_service import CartridgeService

class IntakeService(BaseService):
    """
    The Vacuum.
    Crawls local directories and ingests raw files into the Cartridge.
    Performs NO analysis, only storage.
    """

    # Files to absolutely ignore
    IGNORE_DIRS = {'.git', '__pycache__', 'node_modules', '.venv', 'dist', 'build', '.idea', '.vscode'}
    IGNORE_EXTS = {'.pyc', '.pyd', '.db', '.sqlite', '.sqlite3'}

    def __init__(self, cartridge_service: CartridgeService):
        super().__init__("IntakeService")
        self.cartridge = cartridge_service

    def scan_directory(self, root_path: str) -> Dict[str, int]:
        """
        Recursively walks the directory and stores everything in the DB.
        Returns a report of what it did.
        """
        root = Path(root_path).resolve()
        stats = {"text": 0, "binary": 0, "skipped": 0, "total": 0}

        self.log_info(f"Starting scan of {root}...")

        for current_dir, dirs, files in os.walk(root):
            # In-place modification of dirs to prune IGNORED directories
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]

            for filename in files:
                file_path = Path(current_dir) / filename
                
                # Check extension blacklist
                if file_path.suffix.lower() in self.IGNORE_EXTS:
                    stats["skipped"] += 1
                    continue

                # Calculate the "Virtual Path" (relative to project root)
                try:
                    vfs_path = file_path.relative_to(root).as_posix()
                except ValueError:
                    vfs_path = filename

                # Attempt Ingestion
                if self._ingest_file(file_path, vfs_path, stats):
                    stats["total"] += 1
                else:
                    stats["skipped"] += 1

        self.log_info(f"Scan Complete. {stats}")
        return stats

    def _ingest_file(self, real_path: Path, vfs_path: str, stats: Dict) -> bool:
        """Reads the file and pushes to CartridgeService."""
        mime_type, _ = mimetypes.guess_type(real_path)
        if not mime_type:
            mime_type = "application/octet-stream"

        # Strategy: Try to read as Text first. If that fails, treat as Binary.
        content = None
        blob = None
        
        try:
            # Try Text
            with open(real_path, 'r', encoding='utf-8') as f:
                content = f.read()
            stats["text"] += 1
        except UnicodeDecodeError:
            # Fallback to Binary
            try:
                with open(real_path, 'rb') as f:
                    blob = f.read()
                stats["binary"] += 1
                # Ensure mime reflects binary if we guessed wrong
                if mime_type.startswith("text"): 
                    mime_type = "application/octet-stream"
            except Exception as e:
                self.log_error(f"Access denied or read error {vfs_path}: {e}")
                return False

        # Store in DB
        return self.cartridge.store_raw_file(
            path=vfs_path,
            content=content,
            blob=blob,
            mime_type=mime_type
        )

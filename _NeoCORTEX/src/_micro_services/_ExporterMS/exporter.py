import os
import sqlite3
import logging
from pathlib import Path
from typing import List, Tuple, Optional

# ==============================================================================
# CONFIGURATION
# ==============================================================================
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("Exporter")
# ==============================================================================

class ExporterMS:
    """
    The Reconstructor: Reads the latest file snapshots from a Cortex Knowledge Base
    and rebuilds the directory structure on the local file system.
    
    UPGRADE: Uses 'vfs_path' for precise reconstruction of mixed sources (Web/File).
    """

    def export_knowledge_base(self, db_path: str, output_dir: str) -> Tuple[int, List[str]]:
        """
        Exports all files from the KB to the target directory.
        :return: (count_of_files_exported, list_of_errors)
        """
        db = Path(db_path).resolve()
        out_root = Path(output_dir).resolve()
        
        if not db.exists():
            raise FileNotFoundError(f"Database not found: {db}")

        # Create output directory if it doesn't exist
        out_root.mkdir(parents=True, exist_ok=True)

        log.info(f"Starting Export: {db.name} -> {out_root}")
        
        exported_count = 0
        errors = []

        try:
            conn = sqlite3.connect(db)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 1. Fetch all files
            # We use vfs_path (Virtual File System) as the truth for where it goes.
            cursor.execute("SELECT vfs_path, content, origin_type FROM files")
            rows = cursor.fetchall()

            for row in rows:
                vfs_path = row['vfs_path']
                content = row['content']
                origin = row['origin_type']

                if not vfs_path: continue

                # 2. Construct Destination Path
                # Security Check: Prevent path traversal (e.g. ../../etc/passwd)
                safe_rel = self._sanitize_path(vfs_path)
                
                dest_path = out_root / safe_rel

                try:
                    # 3. Write File
                    # Ensure parent dirs exist
                    dest_path.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Write content (UTF-8)
                    with open(dest_path, 'w', encoding='utf-8', newline='') as f:
                        if content:
                            f.write(content)
                    
                    exported_count += 1
                    
                except Exception as e:
                    err_msg = f"Failed to write {vfs_path}: {e}"
                    log.error(err_msg)
                    errors.append(err_msg)

            conn.close()
            log.info(f"Export Complete. {exported_count} files written. {len(errors)} errors.")
            return exported_count, errors

        except Exception as e:
            log.critical(f"Critical Export Failure: {e}")
            raise e

    def _sanitize_path(self, path_str: str) -> Path:
        """
        Ensures the path is relative and does not escape the root.
        """
        # Strip leading slashes/dots/drive letters
        clean = path_str.lstrip("/\\.").replace("..", "").replace(":", "")
        return Path(clean)

if __name__ == "__main__":
    pass
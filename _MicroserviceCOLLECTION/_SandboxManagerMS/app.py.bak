import shutil
import hashlib
import os
import logging
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Default folders to ignore when syncing or diffing
DEFAULT_EXCLUDES = {
    "node_modules", ".git", "__pycache__", ".venv", ".mypy_cache",
    "_logs", "dist", "build", ".vscode", ".idea", "_sandbox", "_project_library"
}
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("SandboxMgr")
# ==============================================================================

class SandboxManagerMS:
    """
    The Safety Harness: Manages a 'Sandbox' mirror of a 'Live' project.
    Allows for safe experimentation, diffing, and atomic promotion of changes.
    """
    def __init__(self, live_path: str, sandbox_path: str):
        self.live_root = Path(live_path).resolve()
        self.sandbox_root = Path(sandbox_path).resolve()

    def init_sandbox(self, force: bool = False):
        """
        Creates or resets the sandbox by mirroring the live project.
        """
        if self.sandbox_root.exists():
            if not force:
                raise FileExistsError(f"Sandbox already exists at {self.sandbox_root}")
            log.info("Wiping existing sandbox...")
            shutil.rmtree(self.sandbox_root)
        
        log.info(f"Cloning {self.live_root} -> {self.sandbox_root}...")
        self._mirror_tree(self.live_root, self.sandbox_root)
        log.info("Sandbox initialized.")

    def reset_sandbox(self):
        """
        Discards all sandbox changes and re-syncs from live.
        """
        self.init_sandbox(force=True)

    def get_diff(self) -> Dict[str, List[str]]:
        """
        Compares Sandbox vs Live. Returns added, modified, and deleted files.
        """
        sandbox_files = self._scan_files(self.sandbox_root)
        live_files = self._scan_files(self.live_root)
        
        sandbox_paths = set(sandbox_files.keys())
        live_paths = set(live_files.keys())

        # 1. Added: In sandbox but not in live
        added = sorted(list(sandbox_paths - live_paths))
        
        # 2. Deleted: In live but not in sandbox
        deleted = sorted(list(live_paths - sandbox_paths))
        
        # 3. Modified: In both, but hashes differ
        common = sandbox_paths.intersection(live_paths)
        modified = []
        for rel_path in common:
            if sandbox_files[rel_path] != live_files[rel_path]:
                modified.append(rel_path)
        modified.sort()

        return {
            "added": added,
            "modified": modified,
            "deleted": deleted
        }

    def promote_changes(self) -> Tuple[int, int, int]:
        """
        Applies changes from Sandbox to Live.
        Returns (added_count, modified_count, deleted_count).
        """
        diff = self.get_diff()
        
        # 1. Additions & Modifications (Copy file -> file)
        for rel_path in diff['added'] + diff['modified']:
            src = self.sandbox_root / rel_path
            dst = self.live_root / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            
        # 2. Deletions (Remove file)
        for rel_path in diff['deleted']:
            target = self.live_root / rel_path
            if target.exists():
                os.remove(target)
                
        log.info(f"Promoted: {len(diff['added'])} added, {len(diff['modified'])} modified, {len(diff['deleted'])} deleted.")
        return len(diff['added']), len(diff['modified']), len(diff['deleted'])

    # --- Internal Helpers ---

    def _mirror_tree(self, src_root: Path, dst_root: Path):
        """Recursive copy that respects the exclusion list."""
        if not dst_root.exists():
            dst_root.mkdir(parents=True, exist_ok=True)

        for item in src_root.iterdir():
            if item.name in DEFAULT_EXCLUDES:
                continue
                
            dst_path = dst_root / item.name
            
            if item.is_dir():
                self._mirror_tree(item, dst_path)
            else:
                shutil.copy2(item, dst_path)

    def _scan_files(self, root: Path) -> Dict[str, str]:
        """
        Scans directory and returns {relative_path: sha256_hash}.
        """
        file_map = {}
        if not root.exists():
            return {}
            
        for path in root.rglob("*"):
            if path.is_file() and not self._is_excluded(path, root):
                rel = str(path.relative_to(root)).replace("\\", "/")
                file_map[rel] = self._get_hash(path)
        return file_map

    def _is_excluded(self, path: Path, root: Path) -> bool:
        """Checks if any part of the path is in the exclusion list."""
        try:
            rel_parts = path.relative_to(root).parts
            return any(p in DEFAULT_EXCLUDES for p in rel_parts)
        except ValueError:
            return False

    def _get_hash(self, path: Path) -> str:
        """Fast SHA-256 for file content."""
        try:
            # Skip binary files if needed, or hash them too (hashing is safe)
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            return "read_error"

# --- Independent Test Block ---
if __name__ == "__main__":
    # Setup test environment
    base = Path("test_env")
    live = base / "live_project"
    box = base / "sandbox"
    
    if base.exists(): shutil.rmtree(base)
    live.mkdir(parents=True)
    
    # 1. Create Mock Live Project
    (live / "main.py").write_text("print('v1')")
    (live / "utils.py").write_text("def help(): pass")
    (live / "node_modules").mkdir() # Should be ignored
    (live / "node_modules" / "junk.js").write_text("junk")
    
    print("--- Initializing Sandbox ---")
    mgr = SandboxManagerMS(str(live), str(box))
    mgr.init_sandbox()
    
    # 2. Make Changes in Sandbox
    print("\n--- Modifying Sandbox ---")
    (box / "main.py").write_text("print('v2')") # Modify
    (box / "new_feature.py").write_text("print('new')") # Add
    os.remove(box / "utils.py") # Delete
    
    # 3. Check Diff
    diff = mgr.get_diff()
    print(f"Diff Analysis:\n Added: {diff['added']}\n Modified: {diff['modified']}\n Deleted: {diff['deleted']}")
    
    # 4. Promote
    print("\n--- Promoting Changes ---")
    mgr.promote_changes()
    
    # Verify Live
    print(f"Live 'main.py' content: {(live / 'main.py').read_text()}")
    print(f"Live 'utils.py' exists? {(live / 'utils.py').exists()}")
    
    # Cleanup
    if base.exists(): shutil.rmtree(base)
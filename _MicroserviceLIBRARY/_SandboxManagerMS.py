import shutil
import hashlib
import os
import logging
from pathlib import Path
from typing import List, Dict, Set, Optional, Tuple, Any
from microservice_std_lib import service_metadata, service_endpoint
DEFAULT_EXCLUDES = {'node_modules', '.git', '__pycache__', '.venv', '.mypy_cache', '_logs', 'dist', 'build', '.vscode', '.idea', '_sandbox', '_project_library'}
logger = logging.getLogger('SandboxMgr')

@service_metadata(name='SandboxManager', version='1.0.0', description="The Safety Harness: Manages a 'Sandbox' mirror of a 'Live' project for safe experimentation.", tags=['filesystem', 'safety', 'versioning'], capabilities=['filesystem:read', 'filesystem:write'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class SandboxManagerMS:
    """
    The Safety Harness: Manages a 'Sandbox' mirror of a 'Live' project.
    Allows for safe experimentation, diffing, and atomic promotion of changes.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.live_root = Path(self.config.get('live_path', './project')).resolve()
        self.sandbox_root = Path(self.config.get('sandbox_path', './_sandbox')).resolve()

    @service_endpoint(inputs={'force': 'bool'}, outputs={}, description='Creates or resets the sandbox by mirroring the live project.', tags=['sandbox', 'reset'], side_effects=['filesystem:write'])
    def init_sandbox(self, force: bool=False):
        """
        Creates or resets the sandbox by mirroring the live project.
        """
        if self.sandbox_root.exists():
            if not force:
                raise FileExistsError(f'Sandbox already exists at {self.sandbox_root}')
            logger.info('Wiping existing sandbox...')
            shutil.rmtree(self.sandbox_root)
        logger.info(f'Cloning {self.live_root} -> {self.sandbox_root}...')
        self._mirror_tree(self.live_root, self.sandbox_root)
        logger.info('Sandbox initialized.')

    @service_endpoint(inputs={}, outputs={}, description='Discards all sandbox changes and re-syncs from live.', tags=['sandbox', 'reset'], side_effects=['filesystem:write'])
    def reset_sandbox(self):
        """
        Discards all sandbox changes and re-syncs from live.
        """
        self.init_sandbox(force=True)

    @service_endpoint(inputs={}, outputs={'diff': 'Dict[str, List[str]]'}, description='Compares Sandbox vs Live. Returns added, modified, and deleted files.', tags=['sandbox', 'diff'], side_effects=['filesystem:read'])
    def get_diff(self) -> Dict[str, List[str]]:
        """
        Compares Sandbox vs Live. Returns added, modified, and deleted files.
        """
        sandbox_files = self._scan_files(self.sandbox_root)
        live_files = self._scan_files(self.live_root)
        sandbox_paths = set(sandbox_files.keys())
        live_paths = set(live_files.keys())
        added = sorted(list(sandbox_paths - live_paths))
        deleted = sorted(list(live_paths - sandbox_paths))
        common = sandbox_paths.intersection(live_paths)
        modified = []
        for rel_path in common:
            if sandbox_files[rel_path] != live_files[rel_path]:
                modified.append(rel_path)
        modified.sort()
        return {'added': added, 'modified': modified, 'deleted': deleted}

    @service_endpoint(inputs={}, outputs={'added': 'int', 'modified': 'int', 'deleted': 'int'}, description='Applies changes from Sandbox to Live.', tags=['sandbox', 'promote'], side_effects=['filesystem:write'])
    def promote_changes(self) -> Tuple[int, int, int]:
        """
        Applies changes from Sandbox to Live.
        Returns (added_count, modified_count, deleted_count).
        """
        diff = self.get_diff()
        for rel_path in diff['added'] + diff['modified']:
            src = self.sandbox_root / rel_path
            dst = self.live_root / rel_path
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        for rel_path in diff['deleted']:
            target = self.live_root / rel_path
            if target.exists():
                os.remove(target)
        logger.info(f"Promoted: {len(diff['added'])} added, {len(diff['modified'])} modified, {len(diff['deleted'])} deleted.")
        return (len(diff['added']), len(diff['modified']), len(diff['deleted']))

    def _mirror_tree(self, src_root: Path, dst_root: Path):
        """Recursive copy that respects the exclusion list."""
        if not dst_root.exists():
            dst_root.mkdir(parents=True, exist_ok=True)
        if not src_root.exists():
            return
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
        for path in root.rglob('*'):
            if path.is_file() and (not self._is_excluded(path, root)):
                rel = str(path.relative_to(root)).replace('\\', '/')
                file_map[rel] = self._get_hash(path)
        return file_map

    def _is_excluded(self, path: Path, root: Path) -> bool:
        """Checks if any part of the path is in the exclusion list."""
        try:
            rel_parts = path.relative_to(root).parts
            return any((p in DEFAULT_EXCLUDES for p in rel_parts))
        except ValueError:
            return False

    def _get_hash(self, path: Path) -> str:
        """Fast SHA-256 for file content."""
        try:
            return hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            return 'read_error'
if __name__ == '__main__':
    base = Path('test_env')
    live = base / 'live_project'
    box = base / 'sandbox'
    if base.exists():
        shutil.rmtree(base)
    live.mkdir(parents=True)
    (live / 'main.py').write_text("print('v1')")
    (live / 'utils.py').write_text('def help(): pass')
    (live / 'node_modules').mkdir()
    (live / 'node_modules' / 'junk.js').write_text('junk')
    print('--- Initializing Sandbox ---')
    mgr = SandboxManagerMS({'live_path': str(live), 'sandbox_path': str(box)})
    mgr.init_sandbox()
    print('\n--- Modifying Sandbox ---')
    (box / 'main.py').write_text("print('v2')")
    (box / 'new_feature.py').write_text("print('new')")
    os.remove(box / 'utils.py')
    diff = mgr.get_diff()
    print(f"Diff Analysis:\n Added: {diff['added']}\n Modified: {diff['modified']}\n Deleted: {diff['deleted']}")
    print('\n--- Promoting Changes ---')
    mgr.promote_changes()
    print(f"Live 'main.py' content: {(live / 'main.py').read_text()}")
    print(f"Live 'utils.py' exists? {(live / 'utils.py').exists()}")
    if base.exists():
        shutil.rmtree(base)

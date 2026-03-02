"""
SERVICE_NAME: _FingerprintScannerMS
ENTRY_POINT: _FingerprintScannerMS.py
INTERNAL_DEPENDENCIES: microservice_std_lib
EXTERNAL_DEPENDENCIES: None
"""
import hashlib
import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Set, Optional, Tuple
from microservice_std_lib import service_metadata, service_endpoint
DEFAULT_IGNORE_DIRS = {'node_modules', '.git', '__pycache__', '.venv', 'venv', 'env', '.mypy_cache', '.pytest_cache', '.idea', '.vscode', 'dist', 'build', 'coverage', 'target', 'out', 'bin', 'obj', '_project_library', '_sandbox', '_logs'}
DEFAULT_IGNORE_FILES = {'.DS_Store', 'Thumbs.db', '*.log', '*.tmp', '*.lock'}
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('Fingerprint')

@service_metadata(name='FingerprintScannerMS', version='1.0.0', description='Scans a directory tree and generates a deterministic SHA-256 fingerprint.', tags=['scanning', 'integrity', 'hashing'], capabilities=['filesystem:read'], side_effects=['filesystem:read'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class FingerprintScannerMS:
    """
    The Detective: Scans a directory tree and generates a deterministic
    'Fingerprint' (SHA-256 Merkle Root) representing its exact state.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}

    @service_endpoint(inputs={'root_path': 'str'}, outputs={'state': 'Dict[str, Any]'}, description='Scans the project and returns a comprehensive state object (hashes + Merkle root).', tags=['scanning', 'read'], side_effects=['filesystem:read'])
    def scan_project(self, root_path: str) -> Dict[str, Any]:
        """
        Scans the project and returns a comprehensive state object.
        """
        root = Path(root_path).resolve()
        if not root.exists():
            raise FileNotFoundError(f'Path not found: {root}')
        file_map = {}
        for path in sorted(root.rglob('*')):
            if path.is_file():
                if self._should_ignore(path, root):
                    continue
                rel_path = str(path.relative_to(root)).replace('\\', '/')
                file_hash = self._hash_file(path)
                if file_hash:
                    file_map[rel_path] = file_hash
        sorted_hashes = [file_map[p] for p in sorted(file_map.keys())]
        combined_data = ''.join(sorted_hashes).encode('utf-8')
        project_fingerprint = hashlib.sha256(combined_data).hexdigest()
        log.info(f'Scanned {len(file_map)} files. Fingerprint: {project_fingerprint[:8]}...')
        return {'root': str(root), 'project_fingerprint': project_fingerprint, 'file_hashes': file_map, 'file_count': len(file_map)}

    def _should_ignore(self, path: Path, root: Path) -> bool:
        """Checks path against exclusion lists."""
        try:
            rel_parts = path.relative_to(root).parts
            for part in rel_parts[:-1]:
                if part in DEFAULT_IGNORE_DIRS:
                    return True
            import fnmatch
            name = path.name
            if name in DEFAULT_IGNORE_FILES:
                return True
            if any((fnmatch.fnmatch(name, pat) for pat in DEFAULT_IGNORE_FILES)):
                return True
            return False
        except ValueError:
            return True

    def _hash_file(self, path: Path) -> Optional[str]:
        try:
            content = path.read_bytes()
            return hashlib.sha256(content).hexdigest()
        except (PermissionError, OSError):
            log.warning(f'Could not read/hash: {path}')
            return None
if __name__ == '__main__':
    import time
    test_dir = Path('test_fingerprint_proj')
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
    test_dir.mkdir()
    (test_dir / 'main.py').write_text("print('hello')")
    scanner = FingerprintScannerMS()
    print('Service ready:', scanner)
    print('--- Scan 1 (Initial) ---')
    state_1 = scanner.scan_project(str(test_dir))
    print(f"Fingerprint 1: {state_1['project_fingerprint']}")
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)

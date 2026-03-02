"""
SERVICE_NAME: _IntakeServiceMS
ENTRY_POINT: _IntakeServiceMS.py
INTERNAL_DEPENDENCIES: _CartridgeServiceMS, _ScannerMS, base_service, document_utils, microservice_std_lib
EXTERNAL_DEPENDENCIES: bs4, requests
"""
import os
import mimetypes
import requests
import fnmatch
import json
from pathlib import Path
from typing import Dict, Set, List, Any
from src.microservices.base_service import BaseService
from src.microservices._CartridgeServiceMS import CartridgeServiceMS
from src.microservices._ScannerMS import ScannerMS
import document_utils
from src.microservices.microservice_std_lib import service_metadata, service_endpoint
from src.microservices.base_service import BaseService

DEFAULT_MEMORY_FILE = Path('working_memory.jsonl')
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

@service_metadata(name='IntakeServiceMS', version='1.2.0', description='The Vacuum: Handles two-phase ingestion by scanning sources and processing selected paths into the cartridge.', tags=['ingestion', 'scanner', 'vfs'], capabilities=['filesystem:read', 'web:crawl'], side_effects=['filesystem:read', 'cartridge:write'], internal_dependencies=['_CartridgeServiceMS', '_ScannerMS', 'base_service', 'document_utils', 'microservice_std_lib'], external_dependencies=['bs4', 'requests'])
class IntakeServiceMS(BaseService):
    """
    The Vacuum. 
    Now supports two-phase ingestion:
    1. Scan -> Build Tree (with .gitignore respect)
    2. Ingest -> Process selected paths
    """
    DEFAULT_IGNORE_DIRS = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'env', '.env', '.idea', '.vscode', 'dist', 'build', 'target', 'bin', 'obj', '__cartridge__'}
    DEFAULT_IGNORE_EXTS = {'.pyc', '.pyd', '.exe', '.dll', '.so', '.db', '.sqlite', '.sqlite3', '.bin', '.iso', '.img', '.zip', '.tar', '.gz', '.7z', '.jpg', '.png'}

    def __init__(self, cartridge: CartridgeService):
        super().__init__('IntakeServiceMS')
        self.start_time = time.time()

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float', 'cartridge_connected': 'bool'}, description='Standardized health check to verify service status and cartridge connectivity.', tags=['diagnostic', 'health'])
    def get_health(self) -> Dict[str, Any]:
        """Returns the operational status of the IntakeServiceMS."""
        return {'status': 'online', 'uptime': time.time() - self.start_time, 'cartridge_connected': self.cartridge is not None}
        self.cartridge = cartridge
        self.ignore_patterns: Set[str] = set()

    def ingest_source(self, source_path: str) -> Dict[str, int]:
        """Headless/CLI Entry point: Scans and Ingests in one go."""
        self.cartridge.initialize_manifest()
        self.cartridge.set_manifest('source_root', source_path)
        is_web = source_path.startswith('http')
        self.cartridge.set_manifest('source_type', 'web_root' if is_web else 'filesystem_dir')
        scanner = ScoutMS()
        tree_node = scanner.scan_directory(source_path, web_depth=1 if is_web else 0)
        if not tree_node:
            return {'error': 'Source not found'}
        files_to_ingest = scanner.flatten_tree(tree_node)
        self.cartridge.set_manifest('ingest_config', {'auto_flattened': True, 'count': len(files_to_ingest)})
        return self.ingest_selected(files_to_ingest, source_path)

    @service_endpoint(inputs={'root_path': 'str', 'web_depth': 'int'}, outputs={'tree': 'dict'}, description='Scans a local directory or URL to build a hierarchical tree structure of available files.', tags=['scan', 'discovery'])
    def scan_path(self, root_path: str, web_depth: int=0) -> Dict[str, Any]:
        """
        Unified Scanner Interface.
        Delegates to ScoutMS for both Web and Local FS to ensure consistent node structure.
        """
        scanner = ScannerMS()
        tree_root = scanner.scan_directory(root_path, web_depth=web_depth)
        if not tree_root:
            return None
        if not root_path.startswith('http'):
            saved_config = self._load_persistence(os.path.abspath(root_path))
            self._apply_persistence(tree_root, saved_config)
        return tree_root

    def _apply_persistence(self, node: Dict, saved_config: Dict):
        """Recursively applies checked state from saved config."""
        if 'rel_path' in node and node['rel_path'] in saved_config:
            node['checked'] = saved_config[node['rel_path']]
        elif 'children' in node:
            pass
        if 'children' in node:
            for child in node['children']:
                self._apply_persistence(child, saved_config)

    def _scan_recursive(self, current_path: str, root_path: str, saved_config: Dict) -> Dict:
        name = os.path.basename(current_path)
        is_dir = os.path.isdir(current_path)
        rel_path = os.path.relpath(current_path, root_path).replace('\\', '/')
        node = {'name': name, 'path': current_path, 'rel_path': rel_path, 'type': 'dir' if is_dir else 'file', 'children': [], 'checked': True}
        if saved_config and rel_path in saved_config:
            node['checked'] = saved_config[rel_path]
        elif self._is_ignored(name) or (not is_dir and self._is_binary_ext(name)):
            node['checked'] = False
        if is_dir:
            try:
                with os.scandir(current_path) as it:
                    entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
                    for entry in entries:
                        child = self._scan_recursive(entry.path, root_path, saved_config)
                        node['children'].append(child)
            except PermissionError:
                pass
        return node

    @service_endpoint(inputs={'file_list': 'list', 'root_path': 'str'}, outputs={'stats': 'dict'}, description='Processes a specific list of files into the cartridge storage, handling text extraction and VFS indexing.', tags=['ingest', 'write'], side_effects=['cartridge:write'])
    def ingest_selected(self, file_list: List[str], root_path: str) -> Dict[str, int]:
        """Ingests only the specific files passed in the list."""
        stats = {'added': 0, 'skipped': 0, 'errors': 0}
        for file_path in file_list:
            try:
                try:
                    vfs_path = os.path.relpath(file_path, root_path).replace('\\', '/')
                except ValueError:
                    vfs_path = os.path.basename(file_path)
                self._read_and_store(Path(file_path), vfs_path, 'filesystem', stats)
            except Exception as e:
                self.log_error(f'Error ingesting {file_path}: {e}')
                stats['errors'] += 1
        self._rebuild_directory_index()
        return stats

    def _rebuild_directory_index(self):
        """
        Scans 'files' table and populates 'directories' table.
        This creates the navigable VFS structure.
        """
        self.log_info('Rebuilding VFS Directory Index...')
        conn = self.cartridge._get_conn()
        try:
            rows = conn.execute('SELECT vfs_path FROM files').fetchall()
            seen_dirs = set()
            for r in rows:
                path = r[0]
                current = os.path.dirname(path).replace('\\', '/')
                while current and current != '.' and (current not in seen_dirs):
                    self.cartridge.ensure_directory(current)
                    seen_dirs.add(current)
                    current = os.path.dirname(current).replace('\\', '/')
        except Exception as e:
            self.log_error(f'Directory Index Error: {e}')
        finally:
            conn.close()

    def _load_persistence(self, root_path: str) -> Dict[str, bool]:
        """Loads config from DB Manifest (Portable) or fallback to local."""
        try:
            conn = self.cartridge._get_conn()
            row = conn.execute("SELECT value FROM manifest WHERE key='ingest_config'").fetchone()
            conn.close()
            if row:
                return json.loads(row[0])
        except:
            pass
        cfg_path = os.path.join(root_path, '.ragforge.json')
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def save_persistence(self, root_path: str, checked_map: Dict[str, bool]):
        """Saves user selections into the Cartridge Manifest (Portable)."""
        try:
            conn = self.cartridge._get_conn()
            conn.execute('INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)', ('ingest_config', json.dumps(checked_map)))
            conn.commit()
            conn.close()
        except Exception as e:
            self.log_error(f'Failed to save persistence to DB: {e}')
        cfg_path = os.path.join(root_path, '.ragforge.json')
        try:
            with open(cfg_path, 'w') as f:
                json.dump(checked_map, f, indent=2)
        except:
            pass

    def _load_gitignore(self, root_path: str):
        gitignore_path = os.path.join(root_path, '.gitignore')
        self.ignore_patterns = self.DEFAULT_IGNORE_DIRS.copy()
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and (not line.startswith('#')):
                            if line.endswith('/'):
                                line = line[:-1]
                            self.ignore_patterns.add(line)
            except:
                pass

    def _is_ignored(self, name: str) -> bool:
        if name in self.ignore_patterns:
            return True
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True
        return False

    def _is_binary_ext(self, name: str) -> bool:
        _, ext = os.path.splitext(name)
        return ext.lower() in self.DEFAULT_IGNORE_EXTS

    def _read_and_store(self, real_path: Path, vfs_path: str, origin_type: str, stats: Dict):
        mime_type, _ = mimetypes.guess_type(real_path)
        if not mime_type:
            mime_type = 'application/octet-stream'
        content = None
        blob = None
        try:
            with open(real_path, 'rb') as f:
                blob = f.read()
        except Exception as e:
            self.log_error(f'Read error {real_path}: {e}')
            stats['errors'] += 1
            return
        lower_path = str(real_path).lower()
        if lower_path.endswith('.pdf'):
            content = document_utils.extract_text_from_pdf(blob)
            if not content:
                mime_type = 'application/pdf'
        elif lower_path.endswith('.html') or lower_path.endswith('.htm'):
            try:
                raw_text = blob.decode('utf-8', errors='ignore')
                content = document_utils.extract_text_from_html(raw_text)
            except:
                pass
        else:
            try:
                content = blob.decode('utf-8')
            except UnicodeDecodeError:
                content = None
        success = self.cartridge.store_file(vfs_path, str(real_path), content=content, blob=blob, mime_type=mime_type, origin_type=origin_type)
        if success:
            stats['added'] += 1
        else:
            stats['errors'] += 1
        if __name__ == '__main__':
            from src.microservices._CartridgeServiceMS import CartridgeService
            mock_cartridge = CartridgeService(':memory:')
            svc = IntakeServiceMS(mock_cartridge)
            print('Service ready:', svc._service_info['name'])

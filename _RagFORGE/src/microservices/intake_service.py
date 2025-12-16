import os
import mimetypes
import requests
import fnmatch
import json
from pathlib import Path
from typing import Dict, Set, List, Any
from .base_service import BaseService
from .cartridge_service import CartridgeService

# Optional import for Web
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

class IntakeService(BaseService):
    """
    The Vacuum. 
    Now supports two-phase ingestion:
    1. Scan -> Build Tree (with .gitignore respect)
    2. Ingest -> Process selected paths
    """

    DEFAULT_IGNORE_DIRS = {
        '.git', '__pycache__', 'node_modules', 'venv', '.venv', 'env', '.env', 
        '.idea', '.vscode', 'dist', 'build', 'target', 'bin', 'obj', 
        '__cartridge__'
    }
    
    DEFAULT_IGNORE_EXTS = {
        '.pyc', '.pyd', '.exe', '.dll', '.so', '.db', '.sqlite', '.sqlite3', 
        '.bin', '.iso', '.img', '.zip', '.tar', '.gz', '.7z', '.pdf', '.jpg', '.png'
    }

    def __init__(self, cartridge: CartridgeService):
        super().__init__("IntakeService")
        self.cartridge = cartridge
        self.ignore_patterns: Set[str] = set()

    # --- PHASE 1: SCANNING ---

    def scan_path(self, root_path: str) -> Dict[str, Any]:
        """
        Builds a file tree dict.
        Returns: { 'name': 'root', 'path': '...', 'type': 'dir', 'children': [...], 'checked': bool }
        """
        # 1. Web URL
        if root_path.startswith("http://") or root_path.startswith("https://"):
            return {
                'name': root_path,
                'path': root_path,
                'rel_path': root_path,
                'type': 'web',
                'children': [],
                'checked': True
            }

        # 2. Local Path
        root_path = os.path.abspath(root_path)
        
        if os.path.isfile(root_path):
            # Single File Mode
            return {
                'name': os.path.basename(root_path),
                'path': root_path,
                'rel_path': os.path.basename(root_path),
                'type': 'file',
                'children': [],
                'checked': True
            }
            
        # 3. Directory Mode
        self._load_gitignore(root_path)
        saved_config = self._load_persistence(root_path)
        return self._scan_recursive(root_path, root_path, saved_config)

    def _scan_recursive(self, current_path: str, root_path: str, saved_config: Dict) -> Dict:
        name = os.path.basename(current_path)
        is_dir = os.path.isdir(current_path)
        rel_path = os.path.relpath(current_path, root_path).replace("\\", "/")
        
        node = {
            'name': name,
            'path': current_path,
            'rel_path': rel_path,
            'type': 'dir' if is_dir else 'file',
            'children': [],
            'checked': True
        }

        # Determine Check State
        if saved_config and rel_path in saved_config:
            # Respect user persistence
            node['checked'] = saved_config[rel_path]
        elif self._is_ignored(name) or (not is_dir and self._is_binary_ext(name)):
            # Default to unchecked if ignored
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

    # --- PHASE 2: INGESTION ---

    def ingest_selected(self, file_list: List[str], root_path: str) -> Dict[str, int]:
        """Ingests only the specific files passed in the list."""
        stats = {"added": 0, "skipped": 0, "errors": 0}
        
        for file_path in file_list:
            try:
                # Calculate VFS Path
                try:
                    vfs_path = os.path.relpath(file_path, root_path).replace("\\", "/")
                except ValueError:
                    vfs_path = os.path.basename(file_path)

                self._read_and_store(Path(file_path), vfs_path, "filesystem", stats)
            except Exception as e:
                self.log_error(f"Error ingesting {file_path}: {e}")
                stats["errors"] += 1
        
        # --- POST-INGESTION: Update Manifest ---
        self._rebuild_directory_index()
        
        return stats

    def _rebuild_directory_index(self):
        """
        Scans 'files' table and populates 'directories' table.
        This creates the navigable VFS structure.
        """
        self.log_info("Rebuilding VFS Directory Index...")
        conn = self.cartridge._get_conn()
        try:
            rows = conn.execute("SELECT vfs_path FROM files").fetchall()
            seen_dirs = set()
            
            for r in rows:
                path = r[0]
                # Walk up the path to register all parents
                current = os.path.dirname(path).replace("\\", "/")
                while current and current != "." and current not in seen_dirs:
                    self.cartridge.ensure_directory(current)
                    seen_dirs.add(current)
                    current = os.path.dirname(current).replace("\\", "/")
            
        except Exception as e:
            self.log_error(f"Directory Index Error: {e}")
        finally:
            conn.close()

    # --- HELPERS ---

    def _load_persistence(self, root_path: str) -> Dict[str, bool]:
        """Loads config from DB Manifest (Portable) or fallback to local."""
        # 1. Try DB Manifest
        try:
            conn = self.cartridge._get_conn()
            row = conn.execute("SELECT value FROM manifest WHERE key='ingest_config'").fetchone()
            conn.close()
            if row:
                return json.loads(row[0])
        except: pass
        
        # 2. Fallback to local (Legacy)
        cfg_path = os.path.join(root_path, ".ragforge.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, 'r') as f: return json.load(f)
            except: pass
        return {}

    def save_persistence(self, root_path: str, checked_map: Dict[str, bool]):
        """Saves user selections into the Cartridge Manifest (Portable)."""
        # 1. Save to DB
        try:
            conn = self.cartridge._get_conn()
            conn.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", 
                         ("ingest_config", json.dumps(checked_map)))
            conn.commit()
            conn.close()
        except Exception as e:
            self.log_error(f"Failed to save persistence to DB: {e}")

        # 2. Save local backup (Optional, keeps scan state if DB is deleted)
        cfg_path = os.path.join(root_path, ".ragforge.json")
        try:
            with open(cfg_path, 'w') as f: json.dump(checked_map, f, indent=2)
        except: pass

    def _load_gitignore(self, root_path: str):
        gitignore_path = os.path.join(root_path, '.gitignore')
        self.ignore_patterns = self.DEFAULT_IGNORE_DIRS.copy()
        if os.path.exists(gitignore_path):
            try:
                with open(gitignore_path, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if line.endswith('/'): line = line[:-1]
                            self.ignore_patterns.add(line)
            except: pass

    def _is_ignored(self, name: str) -> bool:
        if name in self.ignore_patterns: return True
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(name, pattern): return True
        return False

    def _is_binary_ext(self, name: str) -> bool:
        _, ext = os.path.splitext(name)
        return ext.lower() in self.DEFAULT_IGNORE_EXTS

    def _read_and_store(self, real_path: Path, vfs_path: str, origin_type: str, stats: Dict):
        mime_type, _ = mimetypes.guess_type(real_path)
        if not mime_type: mime_type = "application/octet-stream"
        try:
            with open(real_path, 'r', encoding='utf-8') as f:
                content = f.read()
                self.cartridge.store_file(vfs_path, str(real_path), content=content, mime_type=mime_type, origin_type=origin_type)
        except UnicodeDecodeError:
            try:
                with open(real_path, 'rb') as f:
                    blob = f.read()
                    self.cartridge.store_file(vfs_path, str(real_path), blob=blob, mime_type=mime_type, origin_type=origin_type)
            except: pass
        stats["added"] += 1

import os
import time
import requests
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Any, Optional
from microservice_std_lib import service_metadata, service_endpoint
try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

@service_metadata(name='Scout', version='1.0.0', description='The Scout: A depth-aware utility for recursively walking local file systems or crawling websites.', tags=['utility', 'scanner', 'crawler'], capabilities=['filesystem:read', 'web:crawl'], internal_dependencies=['microservice_std_lib'], external_dependencies=['bs4', 'requests'])
class ScoutMS:
    """
    The Scanner: Walks file systems OR crawls websites (Depth-Aware).
    """

    def __init__(self):
        self.IGNORE_DIRS = {'.git', '__pycache__', 'node_modules', 'venv', '.env', '.idea', '.vscode', 'dist', 'build', 'coverage', 'site-packages'}
        self.BINARY_EXTENSIONS = {'.pyc', '.pyd', '.exe', '.dll', '.so', '.dylib', '.class', '.jpg', '.jpeg', '.png', '.gif', '.ico', '.zip', '.tar', '.gz', '.docx', '.xlsx', '.db', '.sqlite', '.sqlite3'}
        self.visited_urls = set()

    def is_binary(self, file_path: str) -> bool:
        _, ext = os.path.splitext(file_path)
        if ext.lower() in self.BINARY_EXTENSIONS:
            return True
        return False

    @service_endpoint(inputs={'root_path': 'str', 'web_depth': 'int'}, outputs={'tree': 'dict'}, description='Main entry point to perform a recursive scan of a directory or a web crawl.', tags=['discovery', 'recursive'], side_effects=['filesystem:read', 'network:read'])
    def scan_directory(self, root_path: str, web_depth: int=0) -> Optional[Dict[str, Any]]:
        """
        Main Entry Point.
        :param root_path: File path or URL.
        :param web_depth: How many links deep to crawl (0 = single page).
        """
        if root_path.startswith('http://') or root_path.startswith('https://'):
            self.visited_urls.clear()
            return self._crawl_web_recursive(root_path, depth=web_depth, origin_domain=urlparse(root_path).netloc)
        target = os.path.abspath(root_path)
        if not os.path.exists(target):
            return None
        if not os.path.isdir(target):
            return self._create_node(target, is_dir=False)
        return self._scan_fs_recursive(target)

    def _crawl_web_recursive(self, url: str, depth: int, origin_domain: str) -> Dict[str, Any]:
        """
        Recursively fetches links.
        """
        parsed = urlparse(url)
        clean_path = parsed.path.strip('/')
        if not clean_path:
            clean_path = 'index.html'
        rel_path = f'web/{parsed.netloc}/{clean_path}'
        node = {'name': url, 'path': url, 'rel_path': rel_path, 'type': 'web', 'children': [], 'checked': True}
        if depth < 0 or url in self.visited_urls:
            return node
        self.visited_urls.add(url)
        if depth > 0 and BeautifulSoup:
            try:
                time.sleep(0.1)
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.content, 'html.parser')
                    for link in soup.find_all('a', href=True):
                        full_url = urljoin(url, link['href'])
                        parsed = urlparse(full_url)
                        if parsed.netloc == origin_domain and parsed.scheme in ['http', 'https']:
                            if full_url not in self.visited_urls:
                                child_node = self._crawl_web_recursive(full_url, depth - 1, origin_domain)
                                node['children'].append(child_node)
            except Exception as e:
                node['error'] = str(e)
        return node

    def _scan_fs_recursive(self, current_path: str, root_path: str=None) -> Dict[str, Any]:
        if root_path is None:
            root_path = current_path
        node = self._create_node(current_path, is_dir=True, root_path=root_path)
        node['children'] = []
        try:
            with os.scandir(current_path) as it:
                entries = sorted(it, key=lambda e: (not e.is_dir(), e.name.lower()))
                for entry in entries:
                    if entry.is_dir() and entry.name in self.IGNORE_DIRS:
                        continue
                    if entry.name.startswith('.'):
                        continue
                    if entry.is_dir():
                        child = self._scan_fs_recursive(entry.path, root_path=root_path)
                        if child:
                            node['children'].append(child)
                    else:
                        node['children'].append(self._create_node(entry.path, is_dir=False, root_path=root_path))
        except PermissionError:
            node['error'] = 'Access Denied'
        return node

    def _create_node(self, path: str, is_dir: bool, root_path: str=None) -> Dict[str, Any]:
        name = os.path.basename(path)
        rel_path = name
        if root_path:
            try:
                rel_path = os.path.relpath(path, root_path).replace('\\', '/')
            except ValueError:
                pass
        node = {'name': name, 'path': path, 'rel_path': rel_path, 'type': 'folder' if is_dir else 'file', 'children': [], 'checked': False}
        return node

    @service_endpoint(inputs={'tree_node': 'dict'}, outputs={'file_list': 'list'}, description='Flattens a hierarchical tree node structure into a simple list of paths.', tags=['utility', 'processing'])
    def flatten_tree(self, tree_node: Dict[str, Any]) -> List[str]:
        files = []
        if tree_node['type'] in ['file', 'web']:
            files.append(tree_node['path'])
        elif 'children' in tree_node:
            for child in tree_node['children']:
                files.extend(self.flatten_tree(child))
        return files
if __name__ == '__main__':
    svc = ScoutMS()
    print('Service ready:', svc)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    tree = svc.scan_directory(current_dir)
    if tree:
        print(f'Scanned {len(svc.flatten_tree(tree))} files in current directory.')

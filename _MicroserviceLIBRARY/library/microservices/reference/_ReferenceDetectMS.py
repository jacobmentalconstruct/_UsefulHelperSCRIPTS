import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceDetectMS',
    version='1.0.0',
    description='Pilfered from reference pipeline detect stage. Walks source trees and normalizes text file metadata.',
    tags=['pipeline', 'detect', 'ingest'],
    capabilities=['filesystem:read'],
    side_effects=['filesystem:read'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceDetectMS:
    CODE_EXTENSIONS = {
        '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.swift', '.kt', '.scala', '.sh', '.bash', '.zsh'
    }
    PROSE_EXTENSIONS = {'.md', '.markdown', '.rst', '.txt'}
    STRUCTURED_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.xml', '.csv', '.tsv', '.html', '.htm'}
    SKIP_DIRS = {'.git', '__pycache__', '.idea', '.vscode', 'node_modules', '.venv', 'venv', 'env', 'dist', 'build', 'target'}
    SKIP_EXTENSIONS = {'.pyc', '.pyd', '.so', '.dll', '.exe', '.bin', '.db', '.sqlite', '.zip', '.7z', '.tar', '.gz', '.jpg', '.png', '.gif', '.pdf'}

    def __init__(self):
        self.start_time = time.time()

    def _detect_language(self, path: Path) -> Optional[str]:
        ext = path.suffix.lower()
        mapping = {
            '.py': 'python', '.js': 'javascript', '.ts': 'typescript', '.jsx': 'javascript', '.tsx': 'typescript', '.md': 'markdown', '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.toml': 'toml', '.xml': 'xml', '.csv': 'csv', '.html': 'html', '.htm': 'html'
        }
        return mapping.get(ext)

    def _detect_source_type(self, path: Path) -> str:
        ext = path.suffix.lower()
        if ext in self.CODE_EXTENSIONS:
            return 'code'
        if ext in self.PROSE_EXTENSIONS:
            return 'prose'
        if ext in self.STRUCTURED_EXTENSIONS:
            return 'structured'
        return 'generic'

    def _is_probably_text(self, path: Path) -> bool:
        try:
            with path.open('rb') as f:
                sample = f.read(4096)
            if b'\x00' in sample:
                return False
            return True
        except OSError:
            return False

    @service_endpoint(inputs={'root_path': 'str'}, outputs={'files': 'List[str]'}, description='Recursively walk a file or directory and return eligible text source file paths.', tags=['detect', 'walk'])
    def walk_source(self, root_path: str) -> List[str]:
        root = Path(root_path)
        if root.is_file():
            return [str(root.resolve())] if self._is_probably_text(root) else []
        out: List[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in sorted(dirnames) if d not in self.SKIP_DIRS and not d.startswith('.')]
            for fname in sorted(filenames):
                p = Path(dirpath) / fname
                if p.suffix.lower() in self.SKIP_EXTENSIONS:
                    continue
                if p.name.startswith('.'):
                    continue
                try:
                    if p.stat().st_size == 0:
                        continue
                except OSError:
                    continue
                if self._is_probably_text(p):
                    out.append(str(p.resolve()))
        return out

    @service_endpoint(inputs={'path': 'str'}, outputs={'source': 'dict'}, description='Normalize one source file into metadata + decoded text + split lines.', tags=['detect', 'normalize'])
    def detect(self, path: str) -> Optional[Dict[str, Any]]:
        p = Path(path)
        try:
            stat = p.stat()
        except OSError:
            return None
        if not self._is_probably_text(p):
            return None

        text = None
        encoding = 'utf-8'
        for enc in ('utf-8-sig', 'utf-8', 'latin-1'):
            try:
                text = p.read_text(encoding=enc)
                encoding = 'utf-8' if enc in ('utf-8-sig', 'utf-8') else 'latin-1'
                break
            except UnicodeDecodeError:
                continue
            except OSError:
                return None

        if not text or not text.strip():
            return None

        lines = text.splitlines()
        if not lines:
            return None

        return {
            'path': str(p.resolve()),
            'name': p.name,
            'source_type': self._detect_source_type(p),
            'language': self._detect_language(p),
            'encoding': encoding,
            'text': text,
            'lines': lines,
            'line_count': len(lines),
            'byte_size': stat.st_size,
        }

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

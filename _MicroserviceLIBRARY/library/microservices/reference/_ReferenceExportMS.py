import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceExportMS',
    version='1.0.0',
    description='Pilfered from export.py. Reconstructs files and emits folder-tree or file-dump exports from SQLite source tables.',
    tags=['export', 'db', 'filesystem'],
    capabilities=['db:read', 'filesystem:write'],
    side_effects=['db:read', 'filesystem:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceExportMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        return sqlite3.connect(db_path)

    @service_endpoint(inputs={'db_path': 'str', 'output_dir': 'str'}, outputs={'stats': 'dict'}, description='Reconstruct files from source_files + verbatim_lines into output directory.', tags=['export', 'files'], side_effects=['db:read', 'filesystem:write'])
    def export_to_files(self, db_path: str, output_dir: str) -> Dict[str, Any]:
        conn = self._open(db_path)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        stats = {'files_written': 0, 'bytes_written': 0, 'errors': []}
        try:
            rows = conn.execute('SELECT path, name, line_cids FROM source_files ORDER BY path').fetchall()
            for path, name, line_cids_json in rows:
                try:
                    line_cids = json.loads(line_cids_json) if line_cids_json else []
                    if line_cids:
                        placeholders = ','.join('?' * len(line_cids))
                        lines = conn.execute(
                            f'SELECT content FROM verbatim_lines WHERE line_cid IN ({placeholders})',
                            line_cids,
                        ).fetchall()
                        content = '\n'.join(line[0] for line in lines)
                    else:
                        content = ''
                    target = out / name
                    target.write_text(content, encoding='utf-8')
                    stats['files_written'] += 1
                    stats['bytes_written'] += len(content.encode('utf-8'))
                except Exception as e:
                    stats['errors'].append({'file': name, 'error': str(e)})
            return stats
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str'}, outputs={'tree': 'str'}, description='Generate a folder-tree text visualization from source file paths.', tags=['export', 'tree'], side_effects=['db:read'])
    def generate_folder_tree(self, db_path: str) -> str:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT path, name FROM source_files ORDER BY path').fetchall()
            tree = {}
            for path, name in rows:
                parts = Path(path).parts
                current = tree
                for part in parts[:-1]:
                    current = current.setdefault(part, {})
                current[name] = None

            lines = [f'Project Tree Export', f'Generated: {datetime.now()}', '']

            def walk(node, prefix=''):
                items = sorted(node.items(), key=lambda x: (x[1] is None, x[0]))
                for i, (name, child) in enumerate(items):
                    last = i == len(items) - 1
                    conn_str = '└── ' if last else '├── '
                    if child is None:
                        lines.append(f'{prefix}{conn_str}📄 {name}')
                    else:
                        lines.append(f'{prefix}{conn_str}📁 {name}/')
                        walk(child, prefix + ('    ' if last else '│   '))

            walk(tree)
            return '\n'.join(lines)
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str'}, outputs={'dump': 'str'}, description='Generate concatenated file dump with headers from source/verbatim layers.', tags=['export', 'dump'], side_effects=['db:read'])
    def generate_file_dump(self, db_path: str) -> str:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT path, line_cids FROM source_files ORDER BY path').fetchall()
            out_lines: List[str] = ['Dump: Export', '']
            for path, line_cids_json in rows:
                out_lines.append('')
                out_lines.append('-' * 80)
                out_lines.append(f'FILE: {path}')
                out_lines.append('-' * 80)
                line_cids = json.loads(line_cids_json) if line_cids_json else []
                if not line_cids:
                    out_lines.append('(empty file)')
                    continue
                placeholders = ','.join('?' * len(line_cids))
                lines = conn.execute(
                    f'SELECT content FROM verbatim_lines WHERE line_cid IN ({placeholders})',
                    line_cids,
                ).fetchall()
                out_lines.extend(line[0] for line in lines)
            return '\n'.join(out_lines)
        finally:
            conn.close()

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

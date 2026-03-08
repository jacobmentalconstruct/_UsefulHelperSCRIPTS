import hashlib
import json
import sqlite3
import time
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceVerbatimMS',
    version='1.0.0',
    description='Pilfered from reference pipeline verbatim stage. Writes deduplicated line records and source file records.',
    tags=['pipeline', 'verbatim', 'db'],
    capabilities=['db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceVerbatimMS:
    def __init__(self):
        self.start_time = time.time()

    def _line_cid(self, text: str) -> str:
        return hashlib.sha256(text.encode('utf-8')).hexdigest()

    @service_endpoint(inputs={'db_path': 'str', 'source': 'dict'}, outputs={'line_cids': 'list'}, description='Write verbatim lines with deduplication and return ordered line CIDs.', tags=['verbatim', 'db'], side_effects=['db:write'])
    def write_verbatim(self, db_path: str, source: Dict[str, Any]) -> List[str]:
        conn = sqlite3.connect(db_path)
        try:
            lines = source.get('lines', [])
            line_cids: List[str] = []
            rows: List[tuple] = []
            for line in lines:
                lcid = self._line_cid(line)
                line_cids.append(lcid)
                rows.append((lcid, line, len(line.encode('utf-8'))))

            conn.executemany(
                'INSERT OR IGNORE INTO verbatim_lines (line_cid, content, byte_len) VALUES (?, ?, ?)',
                rows,
            )
            conn.executemany(
                'INSERT INTO fts_lines (content, line_cid) SELECT ?, ? WHERE NOT EXISTS (SELECT 1 FROM fts_lines WHERE line_cid = ?)',
                [(line, lcid, lcid) for line, lcid in zip(lines, line_cids)],
            )
            conn.commit()
            return line_cids
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'source': 'dict', 'line_cids': 'list', 'pipeline_ver': 'str'}, outputs={'ok': 'bool'}, description='Upsert one source_files row linked to ordered line CIDs.', tags=['verbatim', 'source-file'], side_effects=['db:write'])
    def write_source_file(self, db_path: str, source: Dict[str, Any], line_cids: List[str], pipeline_ver: str='1.0.0') -> bool:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute(
                '''
                INSERT OR REPLACE INTO source_files
                  (file_cid, path, name, source_type, language, encoding,
                   line_count, byte_size, line_cids, pipeline_ver)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    source.get('file_cid') or self._line_cid(source.get('path', '')),
                    source.get('path', ''),
                    source.get('name', ''),
                    source.get('source_type', 'generic'),
                    source.get('language'),
                    source.get('encoding', 'utf-8'),
                    source.get('line_count', len(source.get('lines', []))),
                    source.get('byte_size', 0),
                    json.dumps(line_cids),
                    pipeline_ver,
                ),
            )
            conn.commit()
            return True
        finally:
            conn.close()

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

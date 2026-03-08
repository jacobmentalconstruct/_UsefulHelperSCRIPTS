import json
import sqlite3
import time
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceDbQueryMS',
    version='1.0.0',
    description='Pilfered from reference db.query helpers. Exposes browse/query/search endpoints over SQLite layers.',
    tags=['db', 'query', 'search'],
    capabilities=['db:read'],
    side_effects=['db:read'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceDbQueryMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @service_endpoint(inputs={'db_path': 'str'}, outputs={'files': 'list'}, description='List source file rows used by the browse panel.', tags=['db', 'browse'])
    def list_source_files(self, db_path: str) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute(
                'SELECT file_cid, path, name, source_type, language, line_count, byte_size FROM source_files ORDER BY path'
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'file_cid': 'str'}, outputs={'chunks': 'list'}, description='List chunks for a source file including tier metadata and line ranges.', tags=['db', 'browse'])
    def get_chunks_for_file(self, db_path: str, file_cid: str) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute(
                '''
                SELECT
                    cm.chunk_id, cm.chunk_type, cm.context_prefix, cm.token_count,
                    cm.embed_status, cm.semantic_depth, cm.structural_depth, cm.language_tier,
                    tn.line_start, tn.line_end
                FROM chunk_manifest cm
                JOIN tree_nodes tn ON cm.node_id = tn.node_id
                WHERE tn.file_cid = ?
                ORDER BY tn.line_start
                ''',
                (file_cid,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'chunk_id': 'str'}, outputs={'text': 'str'}, description='Reconstruct chunk text from chunk spans and verbatim lines.', tags=['db', 'reconstruct'])
    def reconstruct_chunk_text(self, db_path: str, chunk_id: str) -> str:
        conn = self._open(db_path)
        try:
            row = conn.execute('SELECT spans FROM chunk_manifest WHERE chunk_id = ?', (chunk_id,)).fetchone()
            if not row or not row['spans']:
                return ''
            spans = json.loads(row['spans'])
            if not spans:
                return ''
            lines_out: List[str] = []
            for span in spans:
                src_row = conn.execute('SELECT line_cids FROM source_files WHERE file_cid = ?', (span['source_cid'],)).fetchone()
                if not src_row or not src_row['line_cids']:
                    continue
                line_cids = json.loads(src_row['line_cids'])
                subset = line_cids[span['line_start']:span['line_end'] + 1]
                if not subset:
                    continue
                placeholders = ','.join('?' * len(subset))
                line_rows = conn.execute(
                    f'SELECT content FROM verbatim_lines WHERE line_cid IN ({placeholders})', subset
                ).fetchall()
                lines_out.extend([r['content'] for r in line_rows])
            return '\n'.join(lines_out)
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'query_text': 'str', 'limit': 'int'}, outputs={'results': 'list'}, description='Run FTS line search against fts_lines and return top matches.', tags=['db', 'search'])
    def fts_search(self, db_path: str, query_text: str, limit: int=25) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute(
                'SELECT line_cid, content FROM fts_lines WHERE fts_lines MATCH ? LIMIT ?',
                (query_text, max(1, int(limit))),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str'}, outputs={'stats': 'dict'}, description='Return basic table counts for source, chunk, and verbatim layers.', tags=['db', 'stats'])
    def get_db_stats(self, db_path: str) -> Dict[str, int]:
        conn = self._open(db_path)
        try:
            def q(sql: str) -> int:
                row = conn.execute(sql).fetchone()
                return int(row[0]) if row else 0

            return {
                'source_files': q('SELECT COUNT(*) FROM source_files'),
                'chunk_manifest': q('SELECT COUNT(*) FROM chunk_manifest'),
                'verbatim_lines': q('SELECT COUNT(*) FROM verbatim_lines'),
                'tree_nodes': q('SELECT COUNT(*) FROM tree_nodes'),
            }
        finally:
            conn.close()

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

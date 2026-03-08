import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceIngestRunnerMS',
    version='1.0.0',
    description='Pilfered from pipeline/ingest_runner.py. Provides high-level ingest scan orchestration and post-ingest DB stats.',
    tags=['pipeline', 'ingest', 'orchestration'],
    capabilities=['filesystem:read', 'db:read'],
    side_effects=['filesystem:read', 'db:read'],
    internal_dependencies=['microservice_std_lib', '_ReferenceDetectMS'],
    external_dependencies=[]
)
class ReferenceIngestRunnerMS:
    def __init__(self):
        self.start_time = time.time()
        try:
            from _ReferenceDetectMS import ReferenceDetectMS
            self.detect_service = ReferenceDetectMS()
        except Exception:
            self.detect_service = None

    @service_endpoint(inputs={'source_path': 'str', 'max_files': 'int'}, outputs={'result': 'dict'}, description='Run a high-level ingest scan loop (walk + detect metadata) without writing DB rows.', tags=['ingest', 'scan'], side_effects=['filesystem:read'])
    def run_ingest_scan(self, source_path: str, max_files: int = 0) -> Dict[str, Any]:
        result = {'processed': 0, 'chunks': 0, 'embedded': 0, 'errors': 0, 'candidates': 0, 'files': []}
        path = Path(source_path)
        if not path.exists():
            result['errors'] += 1
            result['error'] = f'Path not found: {source_path}'
            return result

        if self.detect_service is None:
            result['errors'] += 1
            result['error'] = 'ReferenceDetectMS unavailable'
            return result

        candidates = self.detect_service.walk_source(str(path))
        result['candidates'] = len(candidates)
        if max_files > 0:
            candidates = candidates[:max_files]

        for fpath in candidates:
            try:
                sf = self.detect_service.detect(fpath)
                if sf is None:
                    continue
                result['processed'] += 1
                result['files'].append({'path': sf['path'], 'language': sf.get('language'), 'source_type': sf.get('source_type'), 'line_count': sf.get('line_count', 0)})
            except Exception as e:
                result['errors'] += 1
                result['files'].append({'path': fpath, 'error': str(e)})

        return result

    @service_endpoint(inputs={'db_path': 'str'}, outputs={'stats': 'dict'}, description='Return post-ingest DB stats (files/chunks/embedded/nodes/edges/size_mb).', tags=['ingest', 'stats'], side_effects=['db:read'])
    def get_ingest_stats(self, db_path: str) -> Dict[str, Any]:
        stats = {'files': 0, 'chunks': 0, 'embedded': 0, 'nodes': 0, 'edges': 0, 'size_mb': 0.0}
        p = Path(db_path)
        if not p.exists():
            return stats

        try:
            conn = sqlite3.connect(str(p))
            def q(sql: str) -> int:
                row = conn.execute(sql).fetchone()
                return int(row[0]) if row else 0
            stats['files'] = q('SELECT COUNT(*) FROM source_files')
            stats['chunks'] = q('SELECT COUNT(*) FROM chunk_manifest')
            stats['embedded'] = q("SELECT COUNT(*) FROM chunk_manifest WHERE embed_status='done'")
            stats['nodes'] = q('SELECT COUNT(*) FROM graph_nodes')
            stats['edges'] = q('SELECT COUNT(*) FROM graph_edges')
            stats['size_mb'] = p.stat().st_size / 1_048_576
            conn.close()
        except Exception:
            pass

        return stats

    @service_endpoint(inputs={'processed': 'int', 'chunks': 'int', 'embedded': 'int', 'errors': 'int'}, outputs={'message': 'str'}, description='Build summary line matching ingest-runner completion format.', tags=['ingest', 'summary'])
    def format_summary(self, processed: int, chunks: int, embedded: int, errors: int) -> str:
        return f'Done: {processed} files, {chunks} chunks, {embedded} embedded, {errors} errors'

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

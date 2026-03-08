import json
import time
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceManifestMS',
    version='1.0.0',
    description='Pilfered from reference pipeline manifest stage. Builds chunk ids and manifest payloads for DB writes.',
    tags=['pipeline', 'manifest'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceManifestMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'chunk_text': 'str'}, outputs={'chunk_id': 'str'}, description='Compute stable chunk id from chunk text content.', tags=['manifest', 'id'])
    def chunk_id(self, chunk_text: str) -> str:
        import hashlib
        return hashlib.sha256(chunk_text.encode('utf-8')).hexdigest()

    @service_endpoint(inputs={'chunks': 'list'}, outputs={'chunk_ids': 'list'}, description='Assign chunk ids for a list of chunk dictionaries.', tags=['manifest', 'id'])
    def assign_chunk_ids(self, chunks: List[Dict[str, Any]]) -> List[str]:
        return [self.chunk_id(str(c.get('text', ''))) for c in chunks]

    @service_endpoint(inputs={'chunks': 'list', 'chunk_ids': 'list', 'node_ids': 'list', 'chunker_name': 'str', 'pipeline_version': 'str'}, outputs={'manifest_rows': 'list'}, description='Build normalized manifest rows ready for insertion into chunk_manifest.', tags=['manifest', 'build'])
    def build_manifest_rows(self, chunks: List[Dict[str, Any]], chunk_ids: List[str], node_ids: List[str], chunker_name: str, pipeline_version: str='1.0.0') -> List[Dict[str, Any]]:
        rows: List[Dict[str, Any]] = []
        idx_to_chunk_id = {i: cid for i, cid in enumerate(chunk_ids)}

        for i, chunk in enumerate(chunks):
            cid = chunk_ids[i] if i < len(chunk_ids) else self.chunk_id(str(chunk.get('text', '')))
            node_id = node_ids[i] if i < len(node_ids) else None
            heading_path = chunk.get('heading_path') or []
            parent_idx = chunk.get('parent_chunk_idx')
            prev_idx = chunk.get('prev_chunk_idx')
            next_idx = chunk.get('next_chunk_idx')

            hierarchy = {
                'parent_chunk_id': idx_to_chunk_id.get(parent_idx) if parent_idx is not None else None,
                'heading_path': heading_path,
                'depth': chunk.get('depth', 0),
                'semantic_depth': chunk.get('semantic_depth', 0),
                'structural_depth': chunk.get('structural_depth', 0),
                'language_tier': chunk.get('language_tier', 'unknown'),
            }
            overlap = {
                'prev_chunk_id': idx_to_chunk_id.get(prev_idx) if prev_idx is not None else None,
                'next_chunk_id': idx_to_chunk_id.get(next_idx) if next_idx is not None else None,
                'prefix_lines': chunk.get('overlap_prefix_lines', 0),
                'suffix_lines': chunk.get('overlap_suffix_lines', 0),
            }
            rows.append({
                'chunk_id': cid,
                'node_id': node_id,
                'chunk_type': chunk.get('chunk_type', 'generic'),
                'context_prefix': ' > '.join(heading_path) if heading_path else '',
                'token_count': max(1, len(str(chunk.get('text', '')).split())),
                'spans_json': json.dumps(chunk.get('spans', [])),
                'hierarchy_json': json.dumps(hierarchy),
                'overlap_json': json.dumps(overlap),
                'semantic_depth': chunk.get('semantic_depth', 0),
                'structural_depth': chunk.get('structural_depth', 0),
                'language_tier': chunk.get('language_tier', 'unknown'),
                'chunker': chunker_name,
                'pipeline_ver': pipeline_version,
            })
        return rows

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

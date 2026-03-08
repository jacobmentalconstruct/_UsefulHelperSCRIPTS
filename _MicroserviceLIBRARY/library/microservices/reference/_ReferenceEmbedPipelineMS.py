import sqlite3
import struct
import time
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceEmbedPipelineMS',
    version='1.0.0',
    description='Pilfered from pipeline/embed.py. Builds context prefixes, plans embedding batches, and updates embed statuses.',
    tags=['pipeline', 'embed', 'db'],
    capabilities=['compute', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceEmbedPipelineMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'heading_path': 'list'}, outputs={'prefix': 'str'}, description='Create context prefix from heading path.', tags=['embed', 'context'])
    def make_context_prefix(self, heading_path: List[str]) -> str:
        return ' > '.join([p for p in heading_path if p])

    @service_endpoint(inputs={'chunks': 'list', 'batch_size': 'int'}, outputs={'batches': 'list'}, description='Plan chunk processing batches for embedding stage.', tags=['embed', 'batching'])
    def plan_batches(self, chunks: List[Dict[str, Any]], batch_size: int = 64) -> List[Dict[str, int]]:
        size = max(1, int(batch_size))
        total = len(chunks)
        out = []
        for start in range(0, total, size):
            end = min(start + size, total)
            out.append({'start': start, 'end': end, 'count': end - start})
        return out

    @service_endpoint(inputs={'vector': 'list'}, outputs={'blob': 'bytes'}, description='Pack float vector as little-endian float32 blob.', tags=['embed', 'vector'])
    def pack_vector(self, vector: List[float]) -> bytes:
        if not vector:
            return b''
        return struct.pack(f'<{len(vector)}f', *vector)

    @service_endpoint(inputs={'blob': 'bytes'}, outputs={'vector': 'list'}, description='Unpack little-endian float32 vector blob.', tags=['embed', 'vector'])
    def unpack_vector(self, blob: bytes) -> List[float]:
        if not blob:
            return []
        n = len(blob) // 4
        return list(struct.unpack(f'<{n}f', blob))

    @service_endpoint(inputs={'db_path': 'str', 'chunk_ids': 'list'}, outputs={'updated': 'int'}, description='Mark all listed chunks as pending in chunk_manifest.', tags=['embed', 'status'], side_effects=['db:write'])
    def mark_all_pending(self, db_path: str, chunk_ids: List[str]) -> int:
        if not chunk_ids:
            return 0
        conn = sqlite3.connect(db_path)
        try:
            for cid in chunk_ids:
                conn.execute("UPDATE chunk_manifest SET embed_status = 'pending' WHERE chunk_id = ?", (cid,))
            conn.commit()
            return len(chunk_ids)
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'chunk_ids': 'list'}, outputs={'updated': 'int'}, description='Bulk-mark remaining chunk ids as pending via IN-clause update.', tags=['embed', 'status'], side_effects=['db:write'])
    def mark_remaining_pending(self, db_path: str, chunk_ids: List[str]) -> int:
        if not chunk_ids:
            return 0
        conn = sqlite3.connect(db_path)
        try:
            placeholders = ','.join('?' * len(chunk_ids))
            conn.execute(f"UPDATE chunk_manifest SET embed_status = 'pending' WHERE chunk_id IN ({placeholders})", chunk_ids)
            conn.commit()
            return len(chunk_ids)
        finally:
            conn.close()

    @service_endpoint(inputs={'a': 'list', 'b': 'list'}, outputs={'score': 'float'}, description='Compute cosine similarity between two vectors.', tags=['embed', 'similarity'])
    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(y * y for y in b) ** 0.5
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

import json
import math
import sqlite3
import struct
import time
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceDbSearchMS',
    version='1.0.0',
    description='Pilfered from db/search and query helpers. Provides verbatim and semantic-style search over SQLite layers.',
    tags=['db', 'search', 'fts'],
    capabilities=['db:read'],
    side_effects=['db:read'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceDbSearchMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _unpack_vector(self, blob: bytes) -> List[float]:
        if not blob:
            return []
        count = len(blob) // 4
        return list(struct.unpack(f'<{count}f', blob))

    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    @service_endpoint(inputs={'db_path': 'str', 'query_text': 'str', 'limit': 'int'}, outputs={'results': 'list'}, description='Verbatim search against FTS line index.', tags=['search', 'verbatim'])
    def query_verbatim_layer(self, db_path: str, query_text: str, limit: int=25) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute(
                'SELECT line_cid, content FROM fts_lines WHERE fts_lines MATCH ? LIMIT ?',
                (query_text, max(1, int(limit))),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'query_vector': 'list', 'limit': 'int'}, outputs={'results': 'list'}, description='Semantic-style search over chunk_embeddings using cosine similarity.', tags=['search', 'semantic'])
    def query_semantic_layer(self, db_path: str, query_vector: List[float], limit: int=25) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        scored: List[Dict[str, Any]] = []
        try:
            rows = conn.execute('SELECT chunk_id, embedding FROM chunk_embeddings').fetchall()
            for row in rows:
                emb = self._unpack_vector(row['embedding'])
                score = self._cosine_similarity(query_vector, emb)
                scored.append({'chunk_id': row['chunk_id'], 'score': score})
            scored.sort(key=lambda x: x['score'], reverse=True)
            return scored[: max(1, int(limit))]
        finally:
            conn.close()

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

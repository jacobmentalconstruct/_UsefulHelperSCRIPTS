import math
import struct
import time
from typing import List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceEmbedUtilsMS',
    version='1.0.0',
    description='Pilfered from pipeline embed/query helpers. Provides embedding vector utility endpoints for similarity workflows.',
    tags=['pipeline', 'embed', 'vector'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceEmbedUtilsMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'vector': 'list'}, outputs={'blob': 'bytes'}, description='Pack float vector into SQLite-friendly binary blob.', tags=['vector', 'pack'])
    def pack_vector(self, vector: List[float]) -> bytes:
        return struct.pack(f'<{len(vector)}f', *vector)

    @service_endpoint(inputs={'blob': 'bytes'}, outputs={'vector': 'list'}, description='Unpack SQLite blob into float vector.', tags=['vector', 'unpack'])
    def unpack_vector(self, blob: bytes) -> List[float]:
        if not blob:
            return []
        count = len(blob) // 4
        return list(struct.unpack(f'<{count}f', blob))

    @service_endpoint(inputs={'a': 'list', 'b': 'list'}, outputs={'score': 'float'}, description='Compute cosine similarity between vectors.', tags=['vector', 'similarity'])
    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

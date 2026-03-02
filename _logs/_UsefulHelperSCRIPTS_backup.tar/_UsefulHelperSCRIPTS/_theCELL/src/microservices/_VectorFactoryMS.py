import importlib.util
import sys
import os
import uuid
import logging
import shutil
from typing import List, Dict, Any, Optional, Protocol, Union
from pathlib import Path

# Dependency Check
REQUIRED = ['chromadb', 'faiss-cpu', 'numpy']
MISSING = []
for lib in REQUIRED:
    clean_lib = lib.split('>=')[0].replace('-', '_')
    if clean_lib == 'faiss_cpu':
        clean_lib = 'faiss'
    if importlib.util.find_spec(clean_lib) is None:
        MISSING.append(lib)

if MISSING:
    print('\n' + '!' * 60)
    print(f'MISSING DEPENDENCIES for _VectorFactoryMS:')
    print(f"Run:  pip install {' '.join(MISSING)}")
    print('!' * 60 + '\\n')

from .microservice_std_lib import service_metadata, service_endpoint
from .base_service import BaseService

logger = logging.getLogger('VectorFactory')

class VectorStore(Protocol):
    """The contract that all vector backends must fulfill."""
    def add(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> None: ...
    def search(self, query_vector: List[float], k: int) -> List[Dict[str, Any]]: ...
    def count(self) -> int: ...
    def clear(self) -> None: ...

class FaissStore(VectorStore):
    """Local-first vector store using FAISS and flat-file metadata."""
    def __init__(self, path: str, dim: int):
        import faiss
        import numpy as np
        self.path = Path(path)
        self.meta_path = self.path.with_suffix(self.path.suffix + '.meta.json')
        self.dim = dim
        self.index = faiss.IndexFlatL2(dim)
        self.metadata = []
        self._load()

    def _load(self):
        import faiss
        if self.path.exists():
            self.index = faiss.read_index(str(self.path))
            if self.meta_path.exists():
                with open(self.meta_path, 'r') as f:
                    self.metadata = json.load(f)

    def _save(self):
        import faiss
        faiss.write_index(self.index, str(self.path))
        with open(self.meta_path, 'w') as f:
            json.dump(self.metadata, f)

    def add(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]):
        import numpy as np
        vecs = np.array(embeddings).astype('float32')
        self.index.add(vecs)
        self.metadata.extend(metadatas)
        self._save()

    def search(self, query_vector: List[float], k: int) -> List[Dict[str, Any]]:
        import numpy as np
        vec = np.array([query_vector]).astype('float32')
        distances, indices = self.index.search(vec, k)
        results = []
        for idx in indices[0]:
            if idx != -1 and idx < len(self.metadata):
                results.append(self.metadata[idx])
        return results

    def count(self) -> int:
        return self.index.ntotal

    def clear(self) -> None:
        import faiss
        self.index = faiss.IndexFlatL2(self.dim)
        self.metadata = []
        if self.path.exists(): os.remove(self.path)
        if self.meta_path.exists(): os.remove(self.meta_path)

class ChromaStore(VectorStore):
    """Persistent vector store using ChromaDB."""
    def __init__(self, path: str, collection_name: str):
        import chromadb
        self.client = chromadb.PersistentClient(path=path)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def add(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]):
        ids = [str(uuid.uuid4()) for _ in range(len(embeddings))]
        self.collection.add(embeddings=embeddings, metadatas=metadatas, ids=ids)

    def search(self, query_vector: List[float], k: int) -> List[Dict[str, Any]]:
        results = self.collection.query(query_embeddings=[query_vector], n_results=k)
        return results.get('metadatas', [[]])[0]

    def count(self) -> int:
        return self.collection.count()

    def clear(self) -> None:
        self.client.delete_collection(self.collection.name)

@service_metadata(
    name='VectorFactory',
    version='1.0.0',
    description='The Switchboard: Factory for creating and managing vector stores.',
    tags=['ai', 'vector', 'storage', 'factory'],
    capabilities=['db:vector'],
    internal_dependencies=['base_service', 'microservice_std_lib'],
    external_dependencies=['chromadb', 'faiss-cpu', 'numpy']
)
class VectorFactoryMS(BaseService):
    """
    The Switchboard: Standardized factory for vector store generation.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__('VectorFactory')
        self.config = config or {}

    @service_endpoint(
        inputs={'backend': 'str', 'params': 'Dict'},
        outputs={'store': 'VectorStore'},
        description='Creates a vector store instance (faiss or chroma).',
        tags=['factory', 'create']
    )
    # ROLE: Creates a vector store instance (faiss or chroma).
    # INPUTS: {"backend": "str", "params": "Dict"}
    # OUTPUTS: {"store": "VectorStore"}
    def create(self, backend: str, params: Dict[str, Any]) -> VectorStore:
        """
        Instantiates a vector store backend.
        """
        backend = backend.lower()
        if backend == 'faiss':
            return FaissStore(params.get('path', 'vector.index'), params.get('dim', 384))
        elif backend == 'chroma':
            return ChromaStore(params.get('path', './chroma_db'), params.get('collection', 'default'))
        else:
            raise ValueError(f"Unsupported vector backend: {backend}")

if __name__ == '__main__':
    import json
    # Basic Test Harness
    logging.basicConfig(level=logging.INFO)
    factory = VectorFactoryMS()
    print(f"Service Ready: {factory}")
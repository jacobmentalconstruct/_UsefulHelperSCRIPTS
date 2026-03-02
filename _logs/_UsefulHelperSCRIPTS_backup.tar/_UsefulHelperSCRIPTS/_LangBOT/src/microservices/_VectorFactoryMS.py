import importlib.util
import sys
import os
import uuid
import logging
import shutil
from typing import List, Dict, Any, Optional, Protocol, Union
from pathlib import Path
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
    print('!' * 60 + '\n')
from src.microservices.microservice_std_lib import service_metadata, service_endpoint
from src.microservices.base_service import BaseService

DEFAULT_MEMORY_FILE = Path('working_memory.jsonl')
logger = logging.getLogger('VectorFactory')

class VectorStore(Protocol):
    """The contract that all vector backends must fulfill."""

    def add(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]) -> None:
        ...

    def search(self, query_vector: List[float], k: int) -> List[Dict[str, Any]]:
        ...

    def count(self) -> int:
        ...

    def clear(self) -> None:
        ...

class FaissVectorStore:
    """Local, RAM-heavy, fast vector store using FAISS."""

    def __init__(self, index_path: str, dimension: int):
        import numpy as np
        import faiss
        self.np = np
        self.faiss = faiss
        self.index_path = index_path
        self.dim = dimension
        self.metadata_store = []
        if os.path.exists(index_path):
            try:
                self.index = faiss.read_index(index_path)
                meta_path = index_path + '.meta.json'
                if os.path.exists(meta_path):
                    import json
                    with open(meta_path, 'r') as f:
                        self.metadata_store = json.load(f)
            except Exception as e:
                logger.error(f'Failed to load FAISS index: {e}')
                self.index = faiss.IndexFlatL2(dimension)
        else:
            self.index = faiss.IndexFlatL2(dimension)

    def add(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]):
        if not embeddings:
            return
        vecs = self.np.array(embeddings).astype('float32')
        self.index.add(vecs)
        self.metadata_store.extend(metadatas)
        self._save()

    def search(self, query_vector: List[float], k: int) -> List[Dict[str, Any]]:
        if self.index.ntotal == 0:
            return []
        q_vec = self.np.array([query_vector]).astype('float32')
        distances, indices = self.index.search(q_vec, k)
        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx != -1 and idx < len(self.metadata_store):
                entry = self.metadata_store[idx].copy()
                entry['score'] = float(dist)
                results.append(entry)
        return results

    def count(self) -> int:
        return self.index.ntotal

    def clear(self):
        self.index.reset()
        self.metadata_store = []
        self._save()

    def _save(self):
        self.faiss.write_index(self.index, self.index_path)
        import json
        with open(self.index_path + '.meta.json', 'w') as f:
            json.dump(self.metadata_store, f)

class ChromaVectorStore:
    """Persistent, feature-rich vector store using ChromaDB."""

    def __init__(self, persist_dir: str, collection_name: str):
        import chromadb
        logging.getLogger('chromadb').setLevel(logging.ERROR)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(collection_name)

    def add(self, embeddings: List[List[float]], metadatas: List[Dict[str, Any]]):
        if not embeddings:
            return
        ids = [str(uuid.uuid4()) for _ in embeddings]
        clean_metas = [{k: str(v) if isinstance(v, (list, dict)) else v for k, v in m.items()} for m in metadatas]
        docs = [m.get('content', '') for m in metadatas]
        self.collection.add(ids=ids, embeddings=embeddings, metadatas=clean_metas, documents=docs)

    def search(self, query_vector: List[float], k: int) -> List[Dict[str, Any]]:
        results = self.collection.query(query_embeddings=[query_vector], n_results=k)
        output = []
        if not results['ids']:
            return []
        for i in range(len(results['ids'][0])):
            meta = results['metadatas'][0][i]
            if meta:
                entry = meta.copy()
                entry['score'] = results['distances'][0][i] if results['distances'] else 0.0
                entry['id'] = results['ids'][0][i]
                output.append(entry)
        return output

    def count(self) -> int:
        return self.collection.count()

    def clear(self):
        name = self.collection.name
        self.client.delete_collection(name)
        self.collection = self.client.get_or_create_collection(name)

@service_metadata(name='VectorFactory', version='1.0.0', description='Factory for creating VectorStore instances (FAISS, Chroma).', tags=['vector', 'factory', 'db'], capabilities=['filesystem:read', 'filesystem:write'], internal_dependencies=['microservice_std_lib'], external_dependencies=['chromadb', 'faiss', 'numpy'])
class VectorFactoryMS:
    """
    The Switchboard: Returns the appropriate VectorStore implementation
    based on configuration.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}

    @service_endpoint(inputs={'backend': 'str', 'config': 'Dict'}, outputs={'store': 'VectorStore'}, description='Creates and returns a configured VectorStore instance.', tags=['vector', 'create'], side_effects=[])
    def create(self, backend: str, config: Dict[str, Any]) -> VectorStore:
        """
        :param backend: 'faiss' or 'chroma'
        :param config: Dict containing 'path', 'dim' (for FAISS), or 'collection' (for Chroma)
        """
        logger.info(f'Initializing Vector Store: {backend.upper()}')
        if backend == 'faiss':
            path = config.get('path', 'vector_index.bin')
            dim = config.get('dim', 384)
            return FaissVectorStore(path, dim)
        elif backend == 'chroma':
            path = config.get('path', './chroma_db')
            name = config.get('collection', 'default_collection')
            return ChromaVectorStore(path, name)
        else:
            raise ValueError(f'Unknown backend: {backend}')
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    print('--- Testing VectorFactoryMS ---')
    mock_vec = [0.1, 0.2, 0.3, 0.4]
    mock_meta = {'text': 'Hello World', 'source': 'test'}
    factory = VectorFactoryMS()
    print('Service ready:', factory)
    print('\n[Testing FAISS]')
    try:
        faiss_store = factory.create('faiss', {'path': 'test_faiss.index', 'dim': 4})
        faiss_store.add([mock_vec], [mock_meta])
        print(f'Count: {faiss_store.count()}')
        res = faiss_store.search(mock_vec, 1)
        if res:
            print(f"Search Result: {res[0]['text']}")
        if os.path.exists('test_faiss.index'):
            os.remove('test_faiss.index')
        if os.path.exists('test_faiss.index.meta.json'):
            os.remove('test_faiss.index.meta.json')
    except ImportError:
        print('Skipping FAISS test (library not installed)')
    except Exception as e:
        print(f'FAISS Test Failed: {e}')
    print('\n[Testing Chroma]')
    try:
        chroma_store = factory.create('chroma', {'path': './test_chroma_db', 'collection': 'test_col'})
        chroma_store.add([mock_vec], [mock_meta])
        print(f'Count: {chroma_store.count()}')
        res = chroma_store.search(mock_vec, 1)
        if res:
            print(f"Search Result: {res[0]['text']}")
        if os.path.exists('./test_chroma_db'):
            shutil.rmtree('./test_chroma_db')
    except ImportError:
        print('Skipping Chroma test (library not installed)')
    except Exception as e:
        print(f'Chroma Test Failed: {e}')

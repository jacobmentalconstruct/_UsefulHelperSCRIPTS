import sys
sys.path.append('..')
from orchestration import *
import json
from sklearn.neighbors import NearestNeighbors
from gensim.models import Doc2Vec
from gensim.models.doc2vec import TaggedDocument

class VectorStore:
    """Doc2Vec-based vector store with nearest-neighbour search."""

    def __init__(self) -> None:
        self.model: Optional[Doc2Vec] = None
        self.ids: List[str] = []
        self.matrix: Optional[np.ndarray] = None
        self.nn: Optional[NearestNeighbors] = None

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r"\b\w+\b", text.lower())

    def fit(self, texts: List[str], ids: List[str], vector_size: int = 128, epochs: int = 40) -> None:
        docs = [TaggedDocument(words=self._tokenize(t), tags=[ids[i]]) for i, t in enumerate(texts)]
        model = Doc2Vec(vector_size=vector_size, min_count=1, workers=max(1, os.cpu_count() or 1))
        model.build_vocab(docs)
        model.train(docs, total_examples=len(docs), epochs=epochs)
        self.model = model
        self.ids = list(ids)
        vectors = [model.dv[doc_id] for doc_id in self.ids]
        self.matrix = np.vstack(vectors)
        self.nn = NearestNeighbors(n_neighbors=min(5, len(self.ids)), metric='cosine')
        self.nn.fit(self.matrix)

    def infer(self, text: str) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("VectorStore not fitted")
        return self.model.infer_vector(self._tokenize(text))

    def query(self, query_text: str, k: int = 5) -> List[Tuple[str, float]]:
        if self.matrix is None or self.nn is None or self.model is None:
            raise RuntimeError("VectorStore not fitted")
        qvec = self.infer(query_text).reshape(1, -1)
        distances, indices = self.nn.kneighbors(qvec, n_neighbors=min(k, len(self.ids)))
        results: List[Tuple[str, float]] = []
        for dist, idx in zip(distances[0], indices[0]):
            results.append((self.ids[idx], float(1 - dist)))
        return results

    def save(self, path: str) -> None:
        if self.model is None:
            raise RuntimeError("VectorStore not fitted")
        base, _ = os.path.splitext(path)
        self.model.save(base + '.model')
        with open(base + '.ids', 'w', encoding='utf-8') as f:
            json.dump(self.ids, f)

    def load(self, path: str) -> None:
        base, _ = os.path.splitext(path)
        self.model = Doc2Vec.load(base + '.model')
        with open(base + '.ids', 'r', encoding='utf-8') as f:
            self.ids = json.load(f)
        vectors = [self.model.dv[doc_id] for doc_id in self.ids]
        self.matrix = np.vstack(vectors)
        self.nn = NearestNeighbors(n_neighbors=min(5, len(self.ids)), metric='cosine')
        self.nn.fit(self.matrix)
"""
Deterministic Embedding Provider — local BPE-SVD embedding backend.

Ownership: src/core/model_bridge/deterministic_provider.py
    Owns the local deterministic embedding logic: BPE tokenization,
    pre-trained vector lookup, and mean pooling. This is the inference
    side only — it loads pre-built artifacts (tokenizer.json and
    embeddings.npy) and produces embedding vectors without any HTTP
    calls or running model servers.

    The training pipeline (tokenizer training, co-occurrence counting,
    NPMI friction matrix, SVD spectral compression) that produces
    these artifacts is a separate concern, not owned by this module.

Responsibilities:
    - Load BPE tokenizer specification (vocab + merge rules) from JSON
    - Load pre-computed embedding matrix from .npy
    - Encode text via BPE into token IDs
    - Look up token vectors from embedding matrix
    - Mean-pool token vectors into a single pooled vector per text
    - Return structured result with pooled vectors and token-level artifacts

Design constraints:
    - numpy imported lazily inside _load_embeddings() only
    - Module-level imports are stdlib only
    - All numpy arrays converted to plain Python lists before leaving
      the provider (no numpy types leak into EmbedResponse)
    - Empty text produces a zero vector of correct dimensions
    - Unknown tokens map to zero vectors (do not degrade pooled result)
    - Fully deterministic: same input always produces identical output

# Extracted from: _STUFF-TO-INTEGRATE/deterministic_embedder/inference_engine.py :: DeterministicEmbedder
# Scope: BPE encoding (_encode_word, _encode) + vector lookup + mean pooling
# Rewritten per EXTRACTION_RULES.md — not verbatim copy
# Training pipeline (tokenizer, co-occurrence, NPMI, SVD) → src/core/training/
# Standalone distributable package → packages/bpe_svd/
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class DeterministicEmbedResult:
    """Result from deterministic embedding.

    Carries pooled vectors (one per input text) plus token-level
    artifacts for verbatim grounding and traceability.
    """

    vectors: List[List[float]]
    """Pooled embedding vectors, one per input text."""

    dimensions: int
    """Embedding dimensionality (k)."""

    token_counts: List[int]
    """Number of tokens produced per input text."""

    token_artifacts: List[Dict[str, Any]] = field(default_factory=list)
    """Per-text token-level artifacts: {"token_ids": List[int]}."""


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class DeterministicEmbedProvider:
    """Local deterministic embedding backend.

    Loads a BPE tokenizer (JSON) and pre-trained embedding matrix (.npy)
    at construction. Embeds text by encoding tokens via BPE, looking up
    corresponding rows in the embedding matrix, and mean-pooling.

    The returned pooled vectors are semantically equivalent to what a
    neural embedding model produces — they can be used for cosine
    similarity scoring in the same pipeline.
    """

    def __init__(self, tokenizer_path: str, embeddings_path: str) -> None:
        """Load tokenizer specification and embedding matrix.

        Args:
            tokenizer_path: Path to JSON tokenizer spec (vocab + merges).
            embeddings_path: Path to .npy embedding matrix (vocab_size x dim).

        Raises:
            FileNotFoundError: If either path does not exist.
            ValueError: If embedding matrix is not 2D.
            ImportError: If numpy is not installed.
        """
        self._vocab: Dict[str, int] = {}
        self._merges: List[Tuple[str, str]] = []
        self._end_of_word: str = "</w>"
        self._embeddings: Any = None  # numpy ndarray, typed as Any to avoid import
        self._dimensions: int = 0
        self._unknown_id: int = -1
        self._inverse_vocab_cache: Optional[Dict[int, str]] = None

        self._load_tokenizer(tokenizer_path)
        self._load_embeddings(embeddings_path)

        logger.info(
            "DeterministicEmbedProvider: loaded vocab=%d, merges=%d, "
            "embedding_matrix=%dx%d",
            len(self._vocab),
            len(self._merges),
            self._embeddings.shape[0],
            self._dimensions,
        )

    # -------------------------------------------------------------------
    # Loading
    # -------------------------------------------------------------------

    def _load_tokenizer(self, path: str) -> None:
        """Load BPE tokenizer specification from JSON.

        Expected JSON keys:
            - "vocab": Dict[str, int] — token string to integer ID
            - "merges": List[List[str, str]] — ordered merge pairs
            - "end_of_word": str — end-of-word marker (default "</w>")
        """
        with open(path, "r", encoding="utf-8") as f:
            spec = json.load(f)

        self._vocab = {
            token: int(idx) for token, idx in spec["vocab"].items()
        }

        merges_raw = spec.get("merges", [])
        self._merges = []
        for entry in merges_raw:
            if isinstance(entry, (list, tuple)) and len(entry) == 2:
                self._merges.append((str(entry[0]), str(entry[1])))
            elif isinstance(entry, str):
                # Fallback for concatenated string serialization
                half = len(entry) // 2
                self._merges.append((entry[:half], entry[half:]))

        self._end_of_word = spec.get("end_of_word", "</w>")

    def _load_embeddings(self, path: str) -> None:
        """Load pre-computed embedding matrix from .npy file.

        Raises:
            ImportError: If numpy is not available.
            ValueError: If the loaded array is not 2D.
        """
        try:
            import numpy as np
        except ImportError as exc:
            raise ImportError(
                "numpy is required for the deterministic embedding backend. "
                "Install it with: pip install numpy"
            ) from exc

        self._embeddings = np.load(path)

        if self._embeddings.ndim != 2:
            raise ValueError(
                f"Embedding matrix must be 2D (vocab_size x dim), "
                f"got shape {self._embeddings.shape}"
            )

        self._dimensions = int(self._embeddings.shape[1])

    # -------------------------------------------------------------------
    # BPE Encoding
    # -------------------------------------------------------------------

    def _encode_word(self, word: str) -> List[str]:
        """Encode a single word into BPE symbols.

        Splits the word into characters, appends the end-of-word marker,
        then iteratively applies learned merge rules in order.
        """
        symbols: List[str] = list(word) + [self._end_of_word]

        for left, right in self._merges:
            merged = left + right
            i = 0
            new_symbols: List[str] = []
            while i < len(symbols):
                if (
                    i < len(symbols) - 1
                    and symbols[i] == left
                    and symbols[i + 1] == right
                ):
                    new_symbols.append(merged)
                    i += 2
                else:
                    new_symbols.append(symbols[i])
                    i += 1
            symbols = new_symbols

        return symbols

    def _encode(self, text: str) -> List[int]:
        """Encode text into a list of token IDs.

        Splits on whitespace, encodes each word via BPE, maps symbols
        to vocabulary IDs. Unknown symbols map to -1.
        """
        token_ids: List[int] = []
        for word in text.strip().split():
            symbols = self._encode_word(word)
            for sym in symbols:
                token_ids.append(self._vocab.get(sym, self._unknown_id))
        return token_ids

    # -------------------------------------------------------------------
    # Embedding
    # -------------------------------------------------------------------

    def _embed_single(self, text: str) -> Tuple[List[float], int, Dict[str, Any]]:
        """Embed a single text string.

        Returns:
            Tuple of (pooled_vector, token_count, token_artifact).
        """
        import numpy as np

        token_ids = self._encode(text)
        token_count = len(token_ids)

        if token_count == 0:
            # Empty text: return zero vector
            pooled = [0.0] * self._dimensions
            return pooled, 0, {"token_ids": []}

        # Gather vectors: known tokens get their row, unknowns get zero
        vectors = []
        for tid in token_ids:
            if 0 <= tid < self._embeddings.shape[0]:
                vectors.append(self._embeddings[tid])
            else:
                vectors.append(
                    np.zeros(self._dimensions, dtype=self._embeddings.dtype)
                )

        # Stack and mean-pool
        stacked = np.vstack(vectors)
        pooled_np = stacked.mean(axis=0)

        # Convert to plain Python lists (no numpy types leak out)
        pooled = pooled_np.tolist()

        return pooled, token_count, {"token_ids": token_ids}

    def embed_texts(self, texts: List[str]) -> DeterministicEmbedResult:
        """Embed one or more texts into pooled vectors.

        Args:
            texts: List of strings to embed. May be empty.

        Returns:
            DeterministicEmbedResult with vectors, dimensions, token
            counts, and per-text token-level artifacts.
        """
        if not texts:
            return DeterministicEmbedResult(
                vectors=[],
                dimensions=self._dimensions,
                token_counts=[],
                token_artifacts=[],
            )

        all_vectors: List[List[float]] = []
        all_token_counts: List[int] = []
        all_artifacts: List[Dict[str, Any]] = []

        for text in texts:
            pooled, count, artifact = self._embed_single(text)
            all_vectors.append(pooled)
            all_token_counts.append(count)
            all_artifacts.append(artifact)

        return DeterministicEmbedResult(
            vectors=all_vectors,
            dimensions=self._dimensions,
            token_counts=all_token_counts,
            token_artifacts=all_artifacts,
        )

    # -------------------------------------------------------------------
    # Reverse Lookup
    # -------------------------------------------------------------------

    @property
    def vocab(self) -> Dict[str, int]:
        """Read-only copy of the token vocabulary (symbol -> ID)."""
        return dict(self._vocab)

    @property
    def inverse_vocab(self) -> Dict[int, str]:
        """Cached inverse vocabulary mapping (ID -> symbol).

        Built lazily on first access by inverting self._vocab.
        Returns a copy to prevent external mutation.
        """
        if self._inverse_vocab_cache is None:
            self._inverse_vocab_cache = {
                idx: sym for sym, idx in self._vocab.items()
            }
        return dict(self._inverse_vocab_cache)

    def decode_token_ids(self, token_ids: List[int]) -> List[str]:
        """Map token IDs back to their symbol strings.

        Args:
            token_ids: List of integer token IDs.

        Returns:
            List of symbol strings. Unknown IDs map to "<unk:{id}>".
        """
        inv = self.inverse_vocab
        return [inv.get(tid, f"<unk:{tid}>") for tid in token_ids]

    def nearest_tokens(
        self, vector: List[float], k: int = 10,
    ) -> List[Tuple[str, float, List[float]]]:
        """Find tokens whose embeddings are nearest to a given vector.

        Computes cosine similarity between the input vector and every
        row of the embedding matrix. Returns the top-k results sorted
        by descending similarity.

        Args:
            vector: Query vector (plain Python list of floats).
            k: Number of nearest tokens to return.

        Returns:
            List of (symbol, cosine_similarity, token_vector) tuples,
            sorted by similarity descending. All numpy arrays are
            converted to Python lists before returning.
            Returns empty list if the query vector has zero norm.
        """
        import numpy as np

        query = np.array(vector, dtype=np.float64)
        query_norm = np.linalg.norm(query)
        if query_norm < 1e-12:
            return []

        query_unit = query / query_norm

        # Compute norms for all token embeddings
        emb = self._embeddings.astype(np.float64)
        norms = np.linalg.norm(emb, axis=1)

        # Avoid division by zero for zero-norm rows
        safe_norms = np.where(norms > 1e-12, norms, 1.0)
        emb_unit = emb / safe_norms[:, np.newaxis]

        # Cosine similarities (dot product of unit vectors)
        similarities = emb_unit @ query_unit

        # Zero out rows that had zero norm
        similarities = np.where(norms > 1e-12, similarities, 0.0)

        # Top-k indices
        k = min(k, len(similarities))
        top_indices = np.argsort(similarities)[::-1][:k]

        inv = self.inverse_vocab
        results: List[Tuple[str, float, List[float]]] = []
        for idx in top_indices:
            idx_int = int(idx)
            symbol = inv.get(idx_int, f"<unk:{idx_int}>")
            sim = float(similarities[idx_int])
            token_vec = emb[idx_int].tolist()
            results.append((symbol, sim, token_vec))

        return results

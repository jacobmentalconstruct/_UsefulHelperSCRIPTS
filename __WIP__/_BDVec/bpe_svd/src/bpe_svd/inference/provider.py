"""
bpe_svd.inference.provider — standalone BPE-SVD embedding provider.

This is the distributable inference engine.  It is intentionally
self-contained: no imports from the parent Graph Manifold project.

Loads two artifact files produced by the training pipeline:
    tokenizer.json  — BPE vocabulary + merge rules
    embeddings.npy  — dense (vocab_size × k) embedding matrix

At query time: tokenises text via BPE, looks up token vectors, and
mean-pools them into a single k-dimensional embedding per input string.

Reverse lookup: given a vector, find the nearest tokens in the embedding
space via cosine similarity.

Dependencies: stdlib + numpy only (no scipy, no torch, no network).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ── Result type ──────────────────────────────────────────────────────

@dataclass
class EmbedResult:
    """Structured result from a call to DeterministicEmbedProvider."""

    vectors: List[List[float]]
    """One pooled embedding vector per input text."""

    dimensions: int
    """Dimensionality of each vector (k)."""

    token_counts: List[int]
    """Number of BPE tokens produced for each input text."""

    token_ids: List[List[int]]
    """Raw BPE token ID sequences, one per input text."""


# ── Provider ─────────────────────────────────────────────────────────

class DeterministicEmbedProvider:
    """BPE-SVD deterministic embedding provider.

    Load once, embed many times.  Fully deterministic: identical input
    always produces identical output on any machine.

    Parameters
    ----------
    tokenizer_path : str | Path
        Path to tokenizer.json produced by BPETrainer.save().
    embeddings_path : str | Path
        Path to embeddings.npy produced by compute_embeddings() + np.save().
    """

    def __init__(
        self,
        tokenizer_path: str | Path,
        embeddings_path: str | Path,
    ) -> None:
        self._vocab: Dict[str, int]
        self._merges: List[Tuple[str, str]]
        self._end_of_word: str
        self._inverse_vocab_cache: Optional[Dict[int, str]] = None
        self._load_tokenizer(Path(tokenizer_path))
        self._embeddings = self._load_embeddings(Path(embeddings_path))

    # ── Artifact loading ─────────────────────────────────────────────

    def _load_tokenizer(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(f"Tokenizer not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            spec = json.load(f)
        self._vocab = {str(k): int(v) for k, v in spec["vocab"].items()}
        raw = spec.get("merges", [])
        self._merges = [
            (m[0], m[1]) if isinstance(m, (list, tuple)) else (m[: len(m) // 2], m[len(m) // 2 :])
            for m in raw
        ]
        self._end_of_word = spec.get("end_of_word", "</w>")

    def _load_embeddings(self, path: Path):  # noqa: ANN201
        try:
            import numpy as np  # lazy import
        except ImportError as exc:
            raise ImportError("numpy is required: pip install numpy") from exc
        if not path.is_file():
            raise FileNotFoundError(f"Embeddings not found: {path}")
        arr = np.load(str(path))
        if arr.ndim != 2:
            raise ValueError(f"embeddings.npy must be 2-D, got shape {arr.shape}")
        return arr

    # ── BPE encoding ─────────────────────────────────────────────────

    def _encode_word(self, word: str) -> List[str]:
        symbols: List[str] = list(word) + [self._end_of_word]
        for a, b in self._merges:
            merged = a + b
            i = 0
            new: List[str] = []
            while i < len(symbols):
                if i < len(symbols) - 1 and symbols[i] == a and symbols[i + 1] == b:
                    new.append(merged)
                    i += 2
                else:
                    new.append(symbols[i])
                    i += 1
            symbols = new
        return symbols

    def _encode(self, text: str) -> List[int]:
        ids: List[int] = []
        for word in text.strip().split():
            for sym in self._encode_word(word):
                ids.append(self._vocab.get(sym, -1))
        return ids

    # ── Embedding ────────────────────────────────────────────────────

    def _embed_single(self, text: str):  # noqa: ANN201
        import numpy as np

        token_ids = self._encode(text)
        k = self._embeddings.shape[1]
        if not token_ids:
            return np.zeros(k, dtype=float), token_ids

        rows = []
        for tid in token_ids:
            if 0 <= tid < len(self._embeddings):
                rows.append(self._embeddings[tid])
            else:
                rows.append(np.zeros(k, dtype=float))

        return np.mean(rows, axis=0), token_ids

    def embed_texts(self, texts: List[str]) -> EmbedResult:
        """Embed a list of texts, returning one pooled vector per text.

        Parameters
        ----------
        texts : List[str]
            Input strings to embed.

        Returns
        -------
        EmbedResult
            Pooled vectors, dimensions, token counts, and token ID sequences.
        """
        if not texts:
            return EmbedResult(vectors=[], dimensions=0, token_counts=[], token_ids=[])

        vectors: List[List[float]] = []
        token_counts: List[int] = []
        all_token_ids: List[List[int]] = []

        for text in texts:
            vec, ids = self._embed_single(text)
            vectors.append(vec.tolist())
            token_counts.append(len(ids))
            all_token_ids.append(ids)

        dims = self._embeddings.shape[1]
        return EmbedResult(
            vectors=vectors,
            dimensions=dims,
            token_counts=token_counts,
            token_ids=all_token_ids,
        )

    # ── Reverse lookup ────────────────────────────────────────────────

    @property
    def vocab(self) -> Dict[str, int]:
        """Read-only copy of token vocabulary (symbol → ID)."""
        return dict(self._vocab)

    @property
    def inverse_vocab(self) -> Dict[int, str]:
        """Lazily-built ID → symbol mapping."""
        if self._inverse_vocab_cache is None:
            self._inverse_vocab_cache = {v: k for k, v in self._vocab.items()}
        return dict(self._inverse_vocab_cache)

    def decode_token_ids(self, token_ids: List[int]) -> List[str]:
        """Map integer token IDs back to their symbol strings.

        Unknown IDs are represented as ``<unk:{id}>``.
        """
        inv = self.inverse_vocab
        return [inv.get(tid, f"<unk:{tid}>") for tid in token_ids]

    def nearest_tokens(
        self,
        vector: List[float],
        k: int = 10,
    ) -> List[Tuple[str, float, List[float]]]:
        """Find the k tokens whose embeddings are nearest to vector.

        Returns a list of (symbol, cosine_similarity, token_vector)
        sorted by descending similarity.  All values are plain Python types.
        """
        import numpy as np

        q = np.array(vector, dtype=float)
        q_norm = np.linalg.norm(q)
        if q_norm == 0.0:
            return []

        q_unit = q / q_norm
        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1.0, norms)
        unit_emb = self._embeddings / norms
        sims = unit_emb @ q_unit

        effective_k = min(k, len(sims))
        top_idx = np.argpartition(sims, -effective_k)[-effective_k:]
        top_idx = top_idx[np.argsort(sims[top_idx])[::-1]]

        inv = self.inverse_vocab
        return [
            (
                inv.get(int(i), f"<unk:{i}>"),
                float(sims[i]),
                self._embeddings[i].tolist(),
            )
            for i in top_idx
        ]

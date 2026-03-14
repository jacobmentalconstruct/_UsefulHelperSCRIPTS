"""Core interface for the BDVE embedder demo.

Every public function here defines the contract that the UI and CLI consume.
When no trained model is loaded, they return placeholder data (stubs).
After training, they use the real BPE-SVD pipeline transparently.

Only this file changes when wiring the real embedder — the UI and CLI
stay untouched.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


# ── Data shapes (unchanged — UI and CLI depend on these) ─────────────

@dataclass
class TokenResult:
    """Result of tokenising a single text."""

    text: str
    symbols: List[str]
    token_ids: List[int]


@dataclass
class Hunk:
    """A budget-bounded slice of tokens."""

    index: int
    symbols: List[str]
    token_ids: List[int]
    token_count: int


@dataclass
class ChunkResult:
    """Result of chunking text into budget-bounded hunks."""

    text: str
    budget: int
    hunks: List[Hunk] = field(default_factory=list)
    total_tokens: int = 0


@dataclass
class EmbeddingResult:
    """Vectors produced for a single hunk."""

    hunk_index: int
    vector: List[float]
    dimensions: int
    symbols: List[str]


@dataclass
class NearestToken:
    """A single token recovered by reverse lookup."""

    symbol: str
    similarity: float


@dataclass
class ReverseResult:
    """Nearest tokens recovered from a vector."""

    hunk_index: int
    nearest: List[NearestToken]


# ── Module-level state ───────────────────────────────────────────────

_provider = None  # type: ignore[assignment]
"""Loaded DeterministicEmbedProvider instance, or None if untrained."""

_ARTIFACTS_DIR: Path = Path(__file__).resolve().parent.parent / "artifacts"
_TOKENIZER_PATH: Path = _ARTIFACTS_DIR / "tokenizer.json"
_EMBEDDINGS_PATH: Path = _ARTIFACTS_DIR / "embeddings.npy"


# ── Private helpers ──────────────────────────────────────────────────

def _bpe_encode(
    text: str,
    vocab: Dict[str, int],
    merges: List[Tuple[str, str]],
    eow: str,
) -> List[int]:
    """Encode text to token IDs using BPE vocab + merges (no provider needed).

    This standalone encoder replicates the provider's encoding logic so that
    the training pipeline can produce token ID streams *before* embeddings
    exist (bootstrapping).
    """
    ids: List[int] = []
    for word in text.strip().split():
        symbols: List[str] = list(word) + [eow]
        for a, b in merges:
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
        for sym in symbols:
            ids.append(vocab.get(sym, -1))
    return ids


def _progress(on_progress: Optional[Callable[[str], None]], msg: str) -> None:
    """Call progress callback if provided."""
    if on_progress is not None:
        on_progress(msg)


# ── Training API ─────────────────────────────────────────────────────

def is_trained() -> bool:
    """Whether a trained model is loaded and ready."""
    return _provider is not None


def load_if_available() -> bool:
    """Try to load provider from saved artifacts on disk.

    Returns True if a provider was successfully loaded, False otherwise.
    Call this at startup so that previously trained models are available
    immediately without re-training.
    """
    global _provider
    if _provider is not None:
        return True
    if _TOKENIZER_PATH.is_file() and _EMBEDDINGS_PATH.is_file():
        try:
            from bpe_svd.inference.provider import DeterministicEmbedProvider

            _provider = DeterministicEmbedProvider(
                str(_TOKENIZER_PATH),
                str(_EMBEDDINGS_PATH),
            )
            return True
        except Exception:
            return False
    return False


def train_from_file(
    file_path: str,
    vocab_size: int = 2000,
    embedding_dims: int = 64,
    window_size: int = 5,
    on_progress: Optional[Callable[[str], None]] = None,
) -> None:
    """Full training pipeline: file -> tokenizer -> co-occurrence -> NPMI -> SVD -> provider.

    Parameters
    ----------
    file_path : str
        Path to a text file to train on.
    vocab_size : int
        Target BPE vocabulary size.
    embedding_dims : int
        Number of SVD dimensions (columns in the embedding matrix).
    window_size : int
        Co-occurrence sliding window width.
    on_progress : callable, optional
        Callback receiving progress messages (for UI status bar).
    """
    global _provider

    import numpy as np
    from bpe_svd.inference.provider import DeterministicEmbedProvider
    from bpe_svd.training.bpe_trainer import BPETrainer
    from bpe_svd.training.cooccurrence import compute_counts
    from bpe_svd.training.npmi_matrix import build_npmi_matrix
    from bpe_svd.training.spectral import compute_embeddings

    src = Path(file_path)
    if not src.is_file():
        raise FileNotFoundError(f"Training file not found: {file_path}")

    # ── Step 1: Copy file to temp directory ──────────────────────────
    # BPETrainer.train() requires a directory of .txt files.
    _progress(on_progress, "Preparing corpus...")
    tmp_dir = tempfile.mkdtemp(prefix="bdve_train_")
    try:
        dest = Path(tmp_dir) / src.name
        # Ensure the file has a .txt extension for the trainer
        if not dest.suffix.lower() == ".txt":
            dest = dest.with_suffix(".txt")
        shutil.copy2(str(src), str(dest))

        # ── Step 2: Train BPE tokenizer ──────────────────────────────
        _progress(on_progress, "Training BPE tokenizer...")
        trainer = BPETrainer(vocab_size=vocab_size)
        trainer.train(tmp_dir)

        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
        trainer.save(str(_TOKENIZER_PATH))
        vocab = trainer.vocab
        merges = trainer.merges
        eow = trainer.end_of_word
        _progress(
            on_progress,
            f"Tokenizer trained: {len(vocab)} symbols, {len(merges)} merges",
        )

        # ── Step 3: Encode corpus into token streams ─────────────────
        _progress(on_progress, "Encoding corpus...")
        with open(str(src), "r", encoding="utf-8", errors="ignore") as f:
            corpus_text = f.read()

        # Split into lines and encode each line as a separate stream
        token_streams: List[List[int]] = []
        for line in corpus_text.splitlines():
            line = line.strip()
            if line:
                ids = _bpe_encode(line, vocab, merges, eow)
                if ids:
                    token_streams.append(ids)

        if not token_streams:
            raise ValueError("Corpus produced no token streams — file may be empty.")

        total_tokens = sum(len(s) for s in token_streams)
        _progress(on_progress, f"Encoded: {total_tokens} tokens in {len(token_streams)} lines")

        # ── Step 4: Co-occurrence counting ───────────────────────────
        _progress(on_progress, "Computing co-occurrence statistics...")
        pair_counts, token_counts = compute_counts(
            token_streams,
            window_size=window_size,
        )
        _progress(on_progress, f"Co-occurrence: {len(pair_counts)} pairs observed")

        # ── Step 5: NPMI association matrix ──────────────────────────
        _progress(on_progress, "Building NPMI association matrix...")
        npmi_mat = build_npmi_matrix(pair_counts, token_counts, len(vocab))
        _progress(on_progress, f"Association matrix: {npmi_mat.shape[0]}x{npmi_mat.shape[1]}, {npmi_mat.nnz} nonzero")

        # ── Step 6: SVD compression ──────────────────────────────────
        # Clamp dims to be at most vocab_size - 1 (SVD constraint)
        effective_dims = min(embedding_dims, len(vocab) - 1)
        if effective_dims < 1:
            raise ValueError(
                f"Vocabulary too small ({len(vocab)}) for embedding. "
                "Try a larger training file."
            )
        _progress(on_progress, f"Computing SVD ({effective_dims} dimensions)...")
        embeddings = compute_embeddings(npmi_mat, k=effective_dims)
        _progress(on_progress, f"Embeddings: {embeddings.shape[0]} tokens x {embeddings.shape[1]} dims")

        # ── Step 7: Save artifacts ───────────────────────────────────
        _progress(on_progress, "Saving artifacts...")
        np.save(str(_EMBEDDINGS_PATH), embeddings)

        # ── Step 8: Load provider ────────────────────────────────────
        _progress(on_progress, "Loading provider...")
        _provider = DeterministicEmbedProvider(
            str(_TOKENIZER_PATH),
            str(_EMBEDDINGS_PATH),
        )
        _progress(on_progress, "Training complete — model ready")

    finally:
        # Clean up temp directory
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ── Public API (stub fallback when untrained) ────────────────────────

def tokenize(text: str) -> TokenResult:
    """Convert raw text into BPE tokens.

    Uses real BPE encoding if a model is trained, otherwise returns
    placeholder tokens.
    """
    if _provider is None:
        # Stub: split on characters to simulate BPE output shape
        fake_symbols = list(text.replace(" ", " </w> ").strip().split())
        fake_ids = list(range(len(fake_symbols)))
        return TokenResult(text=text, symbols=fake_symbols, token_ids=fake_ids)

    ids = _provider._encode(text)
    symbols = _provider.decode_token_ids(ids)
    return TokenResult(text=text, symbols=symbols, token_ids=ids)


def chunk(text: str, budget: int) -> ChunkResult:
    """Tokenise text and split into budget-bounded hunks."""
    tok = tokenize(text)
    hunks: List[Hunk] = []
    for i in range(0, len(tok.symbols), budget):
        slice_syms = tok.symbols[i : i + budget]
        slice_ids = tok.token_ids[i : i + budget]
        hunks.append(
            Hunk(
                index=len(hunks),
                symbols=slice_syms,
                token_ids=slice_ids,
                token_count=len(slice_syms),
            )
        )
    return ChunkResult(
        text=text,
        budget=budget,
        hunks=hunks,
        total_tokens=len(tok.symbols),
    )


def embed_hunk(hunk: Hunk) -> EmbeddingResult:
    """Produce an embedding vector for a single hunk.

    Uses real matrix lookup + mean pooling if a model is trained,
    otherwise returns a placeholder vector.
    """
    if _provider is None:
        dims = 8  # placeholder dimensionality
        fake_vector = [round(0.1 * (i + hunk.index), 4) for i in range(dims)]
        return EmbeddingResult(
            hunk_index=hunk.index,
            vector=fake_vector,
            dimensions=dims,
            symbols=hunk.symbols,
        )

    import numpy as np

    emb_matrix = _provider._embeddings
    k = emb_matrix.shape[1]
    rows = []
    for tid in hunk.token_ids:
        if 0 <= tid < len(emb_matrix):
            rows.append(emb_matrix[tid])
        else:
            rows.append(np.zeros(k, dtype=float))
    if rows:
        vector = np.mean(rows, axis=0).tolist()
    else:
        vector = [0.0] * k

    return EmbeddingResult(
        hunk_index=hunk.index,
        vector=vector,
        dimensions=k,
        symbols=hunk.symbols,
    )


def reverse_vector(vector: List[float], k: int = 5) -> List[NearestToken]:
    """Find the nearest tokens to a given vector.

    Uses real cosine-similarity search if a model is trained,
    otherwise returns placeholder results.
    """
    if _provider is None:
        placeholders = [
            ("token_a", 0.95),
            ("token_b", 0.87),
            ("token_c", 0.73),
            ("token_d", 0.61),
            ("token_e", 0.44),
        ]
        return [
            NearestToken(symbol=sym, similarity=sim)
            for sym, sim in placeholders[:k]
        ]

    results = _provider.nearest_tokens(vector, k=k)
    return [
        NearestToken(symbol=sym, similarity=sim)
        for sym, sim, _ in results
    ]

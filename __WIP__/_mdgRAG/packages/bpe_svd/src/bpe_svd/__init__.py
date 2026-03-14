"""
bpe_svd — Deterministic BPE-SVD text embedding library.

Inference (numpy only):
    from bpe_svd import DeterministicEmbedProvider

Training (requires scipy extra):
    from bpe_svd.training import BPETrainer, compute_counts
    from bpe_svd.training import build_npmi_matrix, compute_embeddings

Part of the Graph Manifold project.
See https://github.com/... for the full documentation and whitepaper.
"""

from bpe_svd.inference.provider import DeterministicEmbedProvider, EmbedResult

__all__ = [
    "DeterministicEmbedProvider",
    "EmbedResult",
]

__version__ = "0.1.0"

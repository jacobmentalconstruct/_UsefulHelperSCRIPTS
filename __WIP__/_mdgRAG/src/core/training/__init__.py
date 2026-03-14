"""
src.core.training — BPE-SVD offline training pipeline.

This package owns the four-stage pipeline that converts a text corpus into
the artifact files consumed by the inference provider at query time:

    Stage 1  bpe_trainer.py   BPETrainer           → tokenizer.json
    Stage 2  cooccurrence.py  compute_counts        → pair_counts, token_counts
    Stage 3  npmi_matrix.py   build_npmi_matrix     → scipy sparse matrix
    Stage 4  spectral.py      compute_embeddings    → embeddings.npy  (V × k)

These artifacts are loaded by:
    src.core.model_bridge.deterministic_provider.DeterministicEmbedProvider

Training is offline (runs once per corpus).  Inference is online (runs per
query).  The two concerns share no imports and are connected only through
the artifact files on disk.
"""

from src.core.training.bpe_trainer import BPETrainer
from src.core.training.cooccurrence import compute_counts, sliding_window_cooccurrence
from src.core.training.npmi_matrix import build_npmi_matrix, export_association_matrix_to_json
from src.core.training.spectral import compute_embeddings, export_embeddings_to_json

__all__ = [
    "BPETrainer",
    "compute_counts",
    "sliding_window_cooccurrence",
    "build_npmi_matrix",
    "export_association_matrix_to_json",
    "compute_embeddings",
    "export_embeddings_to_json",
]

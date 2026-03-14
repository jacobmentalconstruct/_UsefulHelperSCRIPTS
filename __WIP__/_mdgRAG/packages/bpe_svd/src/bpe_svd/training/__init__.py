"""bpe_svd.training — offline training pipeline (requires scipy extra).

Install with:  pip install bpe-svd[training]
"""

from bpe_svd.training.bpe_trainer import BPETrainer
from bpe_svd.training.cooccurrence import compute_counts, sliding_window_cooccurrence
from bpe_svd.training.npmi_matrix import build_npmi_matrix, export_association_matrix_to_json
from bpe_svd.training.spectral import compute_embeddings, export_embeddings_to_json

__all__ = [
    "BPETrainer",
    "compute_counts",
    "sliding_window_cooccurrence",
    "build_npmi_matrix",
    "export_association_matrix_to_json",
    "compute_embeddings",
    "export_embeddings_to_json",
]

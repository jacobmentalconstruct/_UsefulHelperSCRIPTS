"""
NPMI Association Matrix Builder — co-occurrence counts → sparse association matrix.

Ownership: bpe_svd/training/npmi_matrix.py
    Owns NPMI normalisation and construction of the positive association
    matrix.  Converts raw pair/token counts (from cooccurrence.py) into a
    symmetric sparse CSR matrix of positive NPMI values suitable for
    truncated SVD.

Responsibilities:
    - Compute marginal and joint co-occurrence probabilities
    - Compute NPMI (Normalised Pointwise Mutual Information)
    - Apply positive-only clamping: A[a,b] = max(0, NPMI(a,b))
    - Return a symmetric scipy.sparse.csr_matrix (V × V)

Design constraints:
    - scipy.sparse imported at module level (training-only dependency)
    - numpy NOT imported at module level (math.log used for scalar ops)
    - No side effects at import time
    - Single ownership: does not tokenise text or perform SVD

# Extracted from: _STUFF-TO-INTEGRATE/deterministic_embedder/pmi_matrix.py :: build_npmi_matrix
# Scope: NPMI calculation + association matrix construction
# Rewritten per EXTRACTION_RULES.md — not verbatim copy

# @HITL_PERMS: DO NOT MODIFY THE MATHEMATICS IN THIS FILE WITHOUT EXPLICIT
# HUMAN-IN-THE-LOOP PERMISSION.  This module defines the positive association
# matrix used for spectral factorisation.  Alterations here will impact
# determinism and semantic fidelity across the entire embedding pipeline.
"""

from __future__ import annotations

import math
from typing import Dict, Tuple

from scipy.sparse import csr_matrix, dok_matrix  # type: ignore[import-untyped]


def build_npmi_matrix(
    pair_counts: Dict[Tuple[int, int], float],
    token_counts: Dict[int, int],
    vocab_size: int,
    *,
    positive_only: bool = True,
    smoothing: float = 0.0,
    ) -> csr_matrix:
    """Build a symmetric sparse **association** matrix from co-occurrence counts.

    This function computes Normalised Pointwise Mutual Information (NPMI)
    for every observed token pair and constructs a sparse matrix A where
    ``A[a,b] = max(0, NPMI(a,b))`` when ``positive_only=True`` (the default).
    Using positive-only NPMI (PNPMI) ensures that zero represents "no
    positive evidence" in the implicit state of the sparse matrix.  If
    ``positive_only`` is False, raw NPMI values (in [-1, 1]) are stored.

    The resulting matrix is suitable for truncated SVD.  A separate
    friction or cost interpretation should be derived from this matrix
    for graph traversal; do not factorize the friction matrix directly.

    Parameters
    ----------
    pair_counts : Dict[Tuple[int, int], float]
        Unordered token pair co-occurrence counts (from cooccurrence.py).
        Counts may be weighted by distance if ``distance_weighting`` was
        enabled during counting.  Values can be floats.
    token_counts : Dict[int, int]
        Per-token frequency counts (from cooccurrence.py).
    vocab_size : int
        Total vocabulary size — defines the matrix dimensions (V × V).
    positive_only : bool, optional
        If True (default), negative NPMI values are set to zero.  This
        yields the Positive NPMI (PNPMI) matrix.  If False, raw NPMI
        values are stored, which may lead to implicit negative values.
    smoothing : float, optional
        Additive smoothing applied to the joint probability ``P(a,b)``
        to avoid division by zero or log(0).  Defaults to 0.0 (no smoothing).

    Returns
    -------
    scipy.sparse.csr_matrix
        Symmetric association matrix of shape ``(vocab_size, vocab_size)``.
        Unobserved pairs have a stored value of 0 (representing no
        positive semantic evidence).
    """
    total_tokens = sum(token_counts.values())
    total_pairs = sum(pair_counts.values())

    if total_tokens == 0 or total_pairs == 0:
        return csr_matrix((vocab_size, vocab_size), dtype=float)

    # Use a DOK matrix for efficient incremental updates
    matrix = dok_matrix((vocab_size, vocab_size), dtype=float)

    # Precompute token probabilities to avoid repeated division
    p_a_cache: Dict[int, float] = {}
    for tok, cnt in token_counts.items():
        if cnt > 0:
            p_a_cache[tok] = cnt / total_tokens

    for (a, b), count_ab in pair_counts.items():
        if a < 0 or b < 0 or a >= vocab_size or b >= vocab_size:
            continue
        # Skip zero counts explicitly (may happen with weighting)
        if count_ab <= 0.0:
            continue

        p_ab = (count_ab + smoothing) / (total_pairs + smoothing * vocab_size * vocab_size)
        p_a = p_a_cache.get(a, 0.0)
        p_b = p_a_cache.get(b, 0.0)

        # If any marginal is zero, skip this pair (shouldn't happen with proper counts)
        if p_a == 0.0 or p_b == 0.0 or p_ab <= 0.0:
            continue

        # PMI and NPMI
        pmi = math.log(p_ab / (p_a * p_b))
        npmi = pmi / (-math.log(p_ab))

        # Optionally clamp to positive-only NPMI
        value = npmi if not positive_only else max(0.0, npmi)

        # Skip if value is zero to keep the sparse structure minimal
        if value <= 0.0:
            continue

        # Store symmetric value
        matrix[a, b] = value
        matrix[b, a] = value

    return matrix.tocsr()


def export_association_matrix_to_json(matrix: csr_matrix, path: str | Path) -> None:
    """Export a sparse association matrix to a JSON file.

    The JSON file contains a dictionary with two keys:

    ``"shape"`` : A tuple ``(n_rows, n_cols)`` specifying the matrix dimensions.
    ``"data"``  : A list of triplets ``[row, col, value]`` for each non-zero entry.

    This function is useful for logging or auditing the learned association
    matrix for future analysis.  Note that saving very large matrices to
    JSON can produce large files; this is intended primarily for small
    corpora or debugging purposes.

    Parameters
    ----------
    matrix : scipy.sparse.csr_matrix
        The association matrix to export.  Must be in CSR format.
    path : str | Path
        The destination file path.  Parent directories are created if
        necessary.
    """
    from pathlib import Path
    import json

    if not isinstance(matrix, csr_matrix):
        raise TypeError("matrix must be a csr_matrix")

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    rows, cols = matrix.nonzero()
    data = matrix.data
    entries = []
    for r, c, v in zip(rows, cols, data):
        entries.append([int(r), int(c), float(v)])

    export = {
        "shape": [int(matrix.shape[0]), int(matrix.shape[1])],
        "data": entries,
    }

    with open(dest, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

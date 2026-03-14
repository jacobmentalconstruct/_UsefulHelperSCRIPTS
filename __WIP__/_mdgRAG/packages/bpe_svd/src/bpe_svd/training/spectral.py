"""
Spectral Compression — truncated SVD on the NPMI association matrix.

Ownership: bpe_svd/training/spectral.py
    Owns the SVD step that compresses the (V × V) sparse association matrix
    into a dense (V × k) token embedding matrix.  This is the ONLY module
    in src/ that is permitted to import scipy.

Responsibilities:
    - Accept a scipy sparse matrix from npmi_matrix.py
    - Run truncated SVD (scipy.sparse.linalg.svds)
    - Return the top-k left singular vectors (U_k), shape (V, k)
    - Ensure singular values are ordered descending (most significant first)

Design constraints:
    - scipy and numpy imported at module level (training-only dep)
    - Explicit guard for trivial/empty matrices
    - Returns U_k scaled by s^0.5 for geometric fidelity (configurable)
    - Sign canonicalisation for cross-platform determinism
    - Single ownership: does not own NPMI calculation or inference pooling

# Extracted from: _STUFF-TO-INTEGRATE/deterministic_embedder/spectral_compression.py :: compute_embeddings
# Scope: truncated SVD + descending sort
# Rewritten per EXTRACTION_RULES.md — not verbatim copy

# @HITL_PERMS: DO NOT MODIFY THE MATHEMATICS IN THIS FILE WITHOUT EXPLICIT
# HUMAN-IN-THE-LOOP PERMISSION.  This module defines the truncated SVD
# factorisation used to derive dense embeddings from the association matrix.
# Changing scaling or canonicalisation logic can break semantic correctness
# and reproducibility.
"""

from __future__ import annotations

import numpy as np  # type: ignore[import-untyped]
from scipy.sparse import spmatrix  # type: ignore[import-untyped]
from scipy.sparse.linalg import svds  # type: ignore[import-untyped]


def compute_embeddings(
    association_matrix: spmatrix,
    k: int = 300,
    *,
    apply_scaling: bool = True,
    scaling_power: float = 0.5,
    canonicalize_sign: bool = True,
) -> np.ndarray:
    """Compute token embeddings via truncated SVD of the association matrix.

    Decomposes ``association_matrix`` ≈ U · diag(s) · V^T and returns a
    dense matrix E of shape (V, k).  Each row E[i] is the embedding for
    token ``i``.  Singular vectors are ordered by descending singular
    values.  Optionally scales each dimension by the singular values to
    preserve variance, and canonicalises the sign of each latent dimension
    for reproducibility.

    Parameters
    ----------
    association_matrix : scipy.sparse.spmatrix
        The symmetric (V × V) positive-association matrix from
        :func:`build_npmi_matrix`.  Row/column index corresponds to token
        vocabulary ID.
    k : int, optional
        Number of dimensions to retain (default 300).  Must be less than
        both dimensions of the matrix.
    apply_scaling : bool, optional
        If True (default), scale the left singular vectors by ``s^scaling_power``.
        If False, return the raw U matrix (orthonormal).  Using scaling
        improves geometric fidelity of the resulting vectors.  See also
        ``scaling_power``.
    scaling_power : float, optional
        The exponent applied to singular values when scaling.  A value of
        0.5 corresponds to classical LSA/LSI (square-root scaling).  A value
        of 1.0 applies full singular values (linear scaling).  Only used
        when ``apply_scaling`` is True.  Defaults to 0.5.
    canonicalize_sign : bool, optional
        If True (default), flip the sign of each column so that the element
        with the largest absolute value is always positive.  Singular vector
        directions are arbitrary up to a sign flip; canonicalisation
        stabilises the output across different machines and solvers.

    Returns
    -------
    np.ndarray
        Dense array of shape (V, k).  Row ``i`` is the embedding for token
        ``i``.  The matrix may be padded with zeros if ``effective_k < k``
        (e.g., when vocab size is very small).
    """
    v = association_matrix.shape[0]
    # Early exit for empty matrices
    if v == 0 or association_matrix.shape[1] == 0:
        return np.empty((0, k), dtype=float)

    # svds requires k < v; clamp if necessary
    effective_k = min(k, v - 1)
    if effective_k <= 0:
        return np.zeros((v, k), dtype=float)

    # Perform truncated SVD.  Note: svds returns singular values in
    # ascending order; reverse to descending for easier interpretation.
    U, s, Vt = svds(association_matrix, k=effective_k)
    U = U[:, ::-1]
    s = s[::-1]

    # Optionally scale by singular values^power
    if apply_scaling:
        # Avoid scaling by zero singular values (shouldn't happen for
        # positive semidefinite matrices but guard anyway)
        with np.errstate(divide="ignore", invalid="ignore"):
            scaled = np.power(s, scaling_power, dtype=float)
        # Multiply each column of U by corresponding scaled singular value
        U = U * scaled[np.newaxis, :]

    # Optionally canonicalise signs for determinism
    if canonicalize_sign:
        # For each latent dimension, ensure the entry with largest
        # magnitude is positive by possibly flipping the entire column.
        for j in range(U.shape[1]):
            col = U[:, j]
            if col.size == 0:
                continue
            idx = int(np.argmax(np.abs(col)))
            if col[idx] < 0:
                U[:, j] = -col

    # Pad with zeros if effective_k < k (rare, but possible for small vocab)
    if effective_k < k:
        padding = np.zeros((v, k - effective_k), dtype=float)
        U = np.hstack((U, padding))

    return U


def export_embeddings_to_json(embeddings: np.ndarray, path: str | Path) -> None:
    """Export a dense embedding matrix to a JSON file.

    The JSON file contains a dictionary with two keys:

    ``"shape"`` : A tuple ``(n_tokens, n_dims)`` specifying the matrix dimensions.
    ``"data"``  : A list of rows, each of which is a list of floats.

    Note that this format is only suitable for small vocabularies and
    dimensions; large matrices will produce very large JSON files.  The
    recommended format for storing embeddings at scale is ``npy`` via
    :func:`numpy.save`.  This function is intended for debugging,
    inspection, or portability when binary formats are not desirable.

    Parameters
    ----------
    embeddings : numpy.ndarray
        Dense array of shape ``(n_tokens, n_dims)``.
    path : str | Path
        Destination file path.  Parent directories are created if needed.
    """
    from pathlib import Path
    import json

    if not isinstance(embeddings, np.ndarray) or embeddings.ndim != 2:
        raise TypeError("embeddings must be a 2-D numpy.ndarray")

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    rows = embeddings.tolist()
    export = {
        "shape": [int(embeddings.shape[0]), int(embeddings.shape[1])],
        "data": rows,
    }
    with open(dest, "w", encoding="utf-8") as f:
        json.dump(export, f, ensure_ascii=False, indent=2)

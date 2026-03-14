"""
Co-occurrence Counter — sliding-window token pair statistics.

Ownership: src/core/training/cooccurrence.py
    Owns sliding-window co-occurrence counting over token ID streams.
    Pure statistics: receives pre-tokenised streams, returns counts.
    Does NOT own tokenisation logic — callers encode text before passing
    streams here.

Responsibilities:
    - Slide a fixed-width window over a token ID stream
    - Count unordered (min, max) token pairs within each window
    - Count individual token frequencies
    - Aggregate counts across multiple streams

Design constraints:
    - No side effects at import time
    - Stdlib only (no numpy, no scipy)
    - Single ownership: does not own BPE encoding or NPMI calculation
    - Pairs are canonicalised as (min_id, max_id) for symmetry

# Extracted from: _STUFF-TO-INTEGRATE/deterministic_embedder/cooccurrence_graph.py :: sliding_window_cooccurrence, compute_counts
# Scope: sliding window statistics only
# Rewritten per EXTRACTION_RULES.md — not verbatim copy
# Architecture change: BPETokenizer class dropped (violated single-ownership);
#   compute_counts() now accepts pre-tokenised streams instead of tokenizer path + corpus dir

# @HITL_PERMS: DO NOT MODIFY THE MATHEMATICAL IMPLEMENTATION BELOW WITHOUT EXPLICIT
# HUMAN-IN-THE-LOOP APPROVAL.  This code forms the deterministic statistical
# backbone of the BPE-SVD embedding pipeline.  Changes here could break
# reproducibility and semantic correctness.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Dict, Iterable, List, Tuple


# ── Core counting functions ──────────────────────────────────────────

def sliding_window_cooccurrence(
    token_stream: Iterable[int],
    window_size: int = 5,
    *,
    distance_weighting: bool = True,
) -> Tuple[Dict[Tuple[int, int], float], Dict[int, int]]:
    """Compute pair co-occurrence counts from a single token ID stream.

    Slides a window of ``window_size`` over the stream.  For every new
    token, each token already in the window is paired with it.  Pairs
    are stored canonically as ``(min_id, max_id)`` for symmetry.  If
    ``distance_weighting`` is True (the default), pairs are weighted by
    the reciprocal of the distance between the two tokens in the stream.

    Parameters
    ----------
    token_stream : Iterable[int]
        Sequence of integer token IDs for one text unit (e.g. one line).
    window_size : int
        Number of tokens to keep in the sliding window (default 5).
    distance_weighting : bool, optional
        If True, weight each co-occurrence by ``1/|i - j|`` where
        ``i`` and ``j`` are the positions of the two tokens in the stream.
        If False, each co-occurrence increments the count by 1.  Defaults
        to True.

    Returns
    -------
    pair_counts : Dict[Tuple[int, int], float]
        Unordered token pair → weighted co-occurrence count within this stream.
    token_counts : Dict[int, int]
        Token ID → frequency within this stream.
    """
    # The sliding window stores tuples of (token_id, position) when
    # distance weighting is enabled, otherwise just token IDs.  Using
    # positions allows us to compute the distance between the new token
    # and each token currently in the window.
    if distance_weighting:
        window: deque[Tuple[int, int]] = deque(maxlen=window_size)
    else:
        window: deque[int] = deque(maxlen=window_size)  # type: ignore[assignment]

    pair_counts: Dict[Tuple[int, int], float] = defaultdict(float)
    token_counts: Dict[int, int] = defaultdict(int)

    # Track the index of each token as we slide through the stream
    position = 0
    for token in token_stream:
        token_counts[token] += 1
        if distance_weighting:
            # When distance weighting is on, the window holds (token, pos)
            for seen, pos in window:  # type: ignore[assignment]
                if seen == token:
                    continue
                distance = position - pos
                if distance <= 0:
                    # Should not happen because pos < position
                    continue
                weight = 1.0 / float(distance)
                pair = (seen, token) if seen < token else (token, seen)
                pair_counts[pair] += weight
            # Append the new token and its position
            window.append((token, position))  # type: ignore[assignment]
        else:
            # Unweighted counts: treat the window as containing just IDs
            for seen in window:  # type: ignore[assignment]
                if seen == token:
                    continue
                pair = (seen, token) if seen < token else (token, seen)
                pair_counts[pair] += 1.0
            window.append(token)  # type: ignore[assignment]
        position += 1

    return dict(pair_counts), dict(token_counts)


def compute_counts(
    token_streams: Iterable[List[int]],
    window_size: int = 5,
    *,
    distance_weighting: bool = True,
) -> Tuple[Dict[Tuple[int, int], float], Dict[int, int]]:
    """Aggregate co-occurrence counts over many pre-tokenised streams.

    Calls :func:`sliding_window_cooccurrence` on each stream and accumulates
    the results into a single global ``pair_counts`` and ``token_counts`` mapping.

    Parameters
    ----------
    token_streams : Iterable[List[int]]
        One list of token IDs per text unit (sentence, line, document).
        Callers are responsible for encoding text into token IDs before
        passing streams to this function.
    window_size : int
        Sliding window size forwarded to :func:`sliding_window_cooccurrence`.
    distance_weighting : bool, optional
        Whether to weight co-occurrence counts by the reciprocal of the
        token distance.  Defaults to True.

    Returns
    -------
    pair_counts : Dict[Tuple[int, int], float]
        Global unordered pair co-occurrence counts (weighted if enabled).
    token_counts : Dict[int, int]
        Global individual token frequency counts.
    """
    total_pairs: Dict[Tuple[int, int], float] = defaultdict(float)
    total_tokens: Dict[int, int] = defaultdict(int)

    for stream in token_streams:
        line_pairs, line_tokens = sliding_window_cooccurrence(
            stream,
            window_size,
            distance_weighting=distance_weighting,
        )
        for pair, cnt in line_pairs.items():
            total_pairs[pair] += cnt
        for tok, cnt in line_tokens.items():
            total_tokens[tok] += cnt

    return dict(total_pairs), dict(total_tokens)

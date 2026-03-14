"""
Scoring — real graph scoring algorithms for the manifold system.

Ownership: src/core/math/scoring.py
    This module owns all score computation, normalisation, and graph
    traversal algorithms. Pure math over graph structures — no I/O,
    no persistence, no model calls.

Algorithms:
    - normalize_min_max: Min-max normalisation to [0, 1]
    - structural_score: PageRank via iterative power method
    - semantic_score: Cosine similarity between node and query embeddings
    - gravity_score: Fused structural + semantic scoring
    - spreading_activation: BFS-style propagation from seed nodes

Legacy context:
    - PageRank on seam subgraph from GravityScorerMS
    - Dot product scoring on L2-normalised embeddings
    - Gravity formula: G(v) = alpha * S_norm(v) + beta * T_norm(v)
    - Min-max normalisation of score vectors

Design constraints:
    - Pure Python — no numpy, no NetworkX
    - Determinism via sorted() iteration throughout
    - Graph parameter typed as Any to avoid importing manifold classes
      (duck typing contract: must have get_nodes() and get_edges())
    - All functions return Dict[NodeId, float]
"""

from __future__ import annotations

import math
from typing import Any, Dict, List

from src.core.types.ids import NodeId
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalize_min_max(scores: Dict[NodeId, float]) -> Dict[NodeId, float]:
    """
    Min-max normalize a dictionary of scores to [0, 1] range.

    Handles edge cases:
        - Empty dict → empty dict
        - Single value or all-equal values → all 0.5
        - Spread < 1e-10 → degenerate, all 0.5

    Args:
        scores: Node ID → raw score mapping.

    Returns:
        Node ID → normalised score in [0, 1].
    """
    if not scores:
        return {}

    vals = list(scores.values())
    lo = min(vals)
    hi = max(vals)
    spread = hi - lo

    if spread < 1e-10:
        # Degenerate case: all values effectively equal
        return {nid: 0.5 for nid in sorted(scores)}

    return {
        nid: (scores[nid] - lo) / spread
        for nid in sorted(scores)
    }


# ---------------------------------------------------------------------------
# Structural scoring — PageRank (power iteration)
# ---------------------------------------------------------------------------

def structural_score(
    graph: Any,
    *,
    damping: float = 0.85,
    max_iterations: int = 100,
    tolerance: float = 1e-8,
) -> Dict[NodeId, float]:
    """
    Compute structural importance scores via PageRank power iteration.

    Builds a directed adjacency from graph.get_edges(), iterates until
    convergence or max_iterations. Dangling nodes (no outgoing edges)
    redistribute their rank equally across all nodes.

    Args:
        graph: Object with get_nodes() -> Dict[NodeId, Node] and
               get_edges() -> Dict[EdgeId, Edge]. Duck-typed to avoid
               coupling the math layer to manifold classes.
        damping: PageRank damping factor. Default 0.85.
        max_iterations: Maximum power iterations. Default 100.
        tolerance: Convergence threshold (L1 norm). Default 1e-8.

    Returns:
        Dict[NodeId, float] — raw PageRank scores (sum ≈ 1.0).
        Empty dict for empty graphs.
    """
    nodes = graph.get_nodes()
    edges = graph.get_edges()

    if not nodes:
        return {}

    node_ids = sorted(nodes.keys())
    n = len(node_ids)
    idx = {nid: i for i, nid in enumerate(node_ids)}

    # Build adjacency: out_links[i] = list of target indices
    out_links: List[List[int]] = [[] for _ in range(n)]
    for edge in edges.values():
        src = edge.from_node_id
        tgt = edge.to_node_id
        if src in idx and tgt in idx:
            out_links[idx[src]].append(idx[tgt])

    # Initialise uniform rank
    rank = [1.0 / n] * n

    # Check for edgeless graph — return uniform scores
    has_edges = any(len(out) > 0 for out in out_links)
    if not has_edges:
        return {nid: 1.0 / n for nid in node_ids}

    teleport = (1.0 - damping) / n

    iterations_done = 0
    for iteration in range(max_iterations):
        new_rank = [0.0] * n

        # Accumulate dangling node mass
        dangling_sum = 0.0
        for i in range(n):
            if not out_links[i]:
                dangling_sum += rank[i]

        dangling_contrib = damping * dangling_sum / n

        # Distribute rank along edges
        for i in range(n):
            if out_links[i]:
                share = damping * rank[i] / len(out_links[i])
                for j in out_links[i]:
                    new_rank[j] += share

        # Add teleport and dangling contributions
        for i in range(n):
            new_rank[i] += teleport + dangling_contrib

        # Convergence check (L1 norm)
        diff = sum(abs(new_rank[i] - rank[i]) for i in range(n))
        rank = new_rank
        iterations_done = iteration + 1
        if diff < tolerance:
            break

    logger.info(
        "Scoring: PageRank converged in %d/%d iterations "
        "(nodes=%d, edges=%d, damping=%.2f)",
        iterations_done, max_iterations, n, len(edges), damping,
    )

    return {node_ids[i]: rank[i] for i in range(n)}


# ---------------------------------------------------------------------------
# Semantic scoring — cosine similarity
# ---------------------------------------------------------------------------

def _dot(a: List[float], b: List[float]) -> float:
    """Dot product of two vectors."""
    return sum(x * y for x, y in zip(a, b))


def _l2_norm(v: List[float]) -> float:
    """L2 norm (Euclidean length) of a vector."""
    return math.sqrt(sum(x * x for x in v))


def _normalize_vector(v: List[float]) -> List[float]:
    """L2-normalize a vector. Returns zero vector if norm is near zero."""
    norm = _l2_norm(v)
    if norm < 1e-12:
        return [0.0] * len(v)
    return [x / norm for x in v]


def semantic_score(
    node_embeddings: Dict[NodeId, List[float]],
    query_embedding: List[float],
) -> Dict[NodeId, float]:
    """
    Compute semantic similarity between each node embedding and a query.

    Uses cosine similarity: dot(normalize(query), normalize(node_vec)).
    Negative similarities are clamped to 0.0.

    Args:
        node_embeddings: Node ID → embedding vector mapping.
        query_embedding: The query vector to compare against.

    Returns:
        Dict[NodeId, float] — similarity scores in [0, 1].
        Empty dict if no node embeddings provided.
    """
    if not node_embeddings:
        return {}

    q_norm = _normalize_vector(query_embedding)
    results: Dict[NodeId, float] = {}

    for nid in sorted(node_embeddings):
        n_norm = _normalize_vector(node_embeddings[nid])
        sim = _dot(q_norm, n_norm)
        # Clamp negatives to zero
        results[nid] = max(0.0, sim)

    return results


# ---------------------------------------------------------------------------
# Gravity scoring — fused structural + semantic
# ---------------------------------------------------------------------------

def gravity_score(
    structural_scores: Dict[NodeId, float],
    semantic_scores: Dict[NodeId, float],
    alpha: float = 0.6,
    beta: float = 0.4,
) -> Dict[NodeId, float]:
    """
    Fuse structural and semantic scores into a gravity score.

    Formula: G(v) = alpha * min_max(structural[v]) + beta * min_max(semantic[v])

    Both input dicts are min-max normalised internally before fusion.
    Nodes present in only one dict receive 0.0 for the missing component.

    Args:
        structural_scores: Node ID → raw structural score.
        semantic_scores: Node ID → raw semantic score.
        alpha: Weight for structural component. Default 0.6.
        beta: Weight for semantic component. Default 0.4.

    Returns:
        Dict[NodeId, float] — gravity scores for the union of all node IDs.
    """
    if not structural_scores and not semantic_scores:
        return {}

    s_norm = normalize_min_max(structural_scores)
    t_norm = normalize_min_max(semantic_scores)

    all_nids = sorted(set(s_norm) | set(t_norm))

    return {
        nid: alpha * s_norm.get(nid, 0.0) + beta * t_norm.get(nid, 0.0)
        for nid in all_nids
    }


# ---------------------------------------------------------------------------
# Spreading activation
# ---------------------------------------------------------------------------

def spreading_activation(
    graph: Any,
    seed_nodes: List[NodeId],
    iterations: int = 3,
    decay: float = 0.5,
) -> Dict[NodeId, float]:
    """
    BFS-style spreading activation from seed nodes with exponential decay.

    Activation starts at 1.0 for seeds and propagates outward through
    undirected adjacency. Each hop multiplies activation by the decay factor.
    Accumulation uses max() — a node keeps the highest activation it receives.
    Seeds never lose their initial 1.0 activation.

    Args:
        graph: Object with get_nodes() and get_edges() (duck-typed).
        seed_nodes: Starting nodes for activation spread.
        iterations: Number of propagation hops. Default 3.
        decay: Multiplicative decay per hop. Default 0.5.

    Returns:
        Dict[NodeId, float] — activation levels for all reached nodes.
        Unreached nodes are not included. Empty dict for empty input.
    """
    nodes = graph.get_nodes()
    edges = graph.get_edges()

    if not nodes or not seed_nodes:
        return {}

    # Build undirected adjacency
    adj: Dict[NodeId, List[NodeId]] = {nid: [] for nid in nodes}
    for edge in edges.values():
        src = edge.from_node_id
        tgt = edge.to_node_id
        if src in adj and tgt in adj:
            adj[src].append(tgt)
            adj[tgt].append(src)

    # Initialise activation for seeds
    activation: Dict[NodeId, float] = {}
    frontier: List[NodeId] = []

    for nid in seed_nodes:
        if nid in nodes:
            activation[nid] = 1.0
            frontier.append(nid)

    # Propagate
    for hop in range(iterations):
        hop_decay = decay ** (hop + 1)
        next_frontier: List[NodeId] = []

        for nid in frontier:
            for neighbor in adj.get(nid, []):
                new_val = hop_decay
                old_val = activation.get(neighbor, 0.0)
                if new_val > old_val:
                    activation[neighbor] = new_val
                    next_frontier.append(neighbor)

        frontier = next_frontier

    # Ensure seeds keep their 1.0 activation
    for nid in seed_nodes:
        if nid in nodes:
            activation[nid] = 1.0

    return activation

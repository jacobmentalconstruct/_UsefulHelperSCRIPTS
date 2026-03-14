"""
Friction Detection — quality signals that detect scoring pathologies.

Ownership: src/core/math/friction.py
    This module owns graph-level quality checks that flag potential
    scoring problems. These are diagnostic signals, not fixes.

Detectors:
    - detect_island_effect: Disconnected components in the graph
    - detect_gravity_collapse: Score spread too narrow to discriminate
    - detect_normalization_extrema: All scores effectively zero
    - detect_all_friction: Run all detectors, return summary dict

Legacy context:
    - FrictionDetectorMS flagged pathological seam states
    - Island detection from disconnected NetworkX subgraphs
    - Score collapse detection from gravity output analysis

Design constraints:
    - Pure Python — no external graph libraries
    - Graph parameter typed as Any (duck typing: get_nodes(), get_edges())
    - Depends only on ids.NodeId from the types layer
"""

from __future__ import annotations

from typing import Any, Dict, List

from src.core.types.ids import NodeId


def detect_island_effect(graph: Any) -> bool:
    """
    Detect disconnected components in the graph (island effect).

    Uses BFS to count connected components in an undirected view of
    the graph. Returns True if there are more than one connected
    component — meaning some nodes cannot reach others.

    Args:
        graph: Object with get_nodes() and get_edges() (duck-typed).

    Returns:
        True if the graph has disconnected islands, False otherwise.
        Returns False for empty graphs or single-node graphs.
    """
    nodes = graph.get_nodes()
    edges = graph.get_edges()

    if len(nodes) <= 1:
        return False

    # Build undirected adjacency
    adj: Dict[NodeId, List[NodeId]] = {nid: [] for nid in nodes}
    for edge in edges.values():
        src = edge.from_node_id
        tgt = edge.to_node_id
        if src in adj and tgt in adj:
            adj[src].append(tgt)
            adj[tgt].append(src)

    # BFS from first node
    visited: set = set()
    start = next(iter(sorted(nodes.keys())))
    queue: List[NodeId] = [start]
    visited.add(start)

    while queue:
        current = queue.pop(0)
        for neighbor in adj.get(current, []):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    return len(visited) < len(nodes)


def detect_gravity_collapse(
    scores: Dict[NodeId, float],
    threshold: float = 0.1,
) -> bool:
    """
    Detect gravity collapse — score spread too narrow to discriminate.

    Returns True if the difference between max and min scores is below
    the threshold. This means ranking is effectively meaningless.

    Args:
        scores: Node ID → gravity score mapping.
        threshold: Minimum acceptable spread. Default 0.1.

    Returns:
        True if scores are collapsed (spread < threshold).
        Returns False for empty or single-value dicts.
    """
    if len(scores) <= 1:
        return False

    vals = list(scores.values())
    spread = max(vals) - min(vals)
    return spread < threshold


def detect_normalization_extrema(scores: Dict[NodeId, float]) -> bool:
    """
    Detect normalization extrema — all scores effectively zero.

    Returns True if every score is below 1e-10 in absolute value.
    This indicates a degenerate scoring state where no node has
    meaningful weight.

    Args:
        scores: Node ID → score mapping.

    Returns:
        True if all scores are effectively zero.
        Returns False for empty dicts.
    """
    if not scores:
        return False

    return all(abs(v) < 1e-10 for v in scores.values())


def detect_all_friction(
    graph: Any,
    gravity_scores: Dict[NodeId, float],
) -> Dict[str, bool]:
    """
    Run all friction detectors and return a summary dict.

    Args:
        graph: Object with get_nodes() and get_edges() (duck-typed).
        gravity_scores: Node ID → gravity score mapping.

    Returns:
        Dict with keys:
            - "island_effect": True if graph has disconnected components
            - "gravity_collapse": True if score spread is too narrow
            - "normalization_extrema": True if all scores near zero
    """
    return {
        "island_effect": detect_island_effect(graph),
        "gravity_collapse": detect_gravity_collapse(gravity_scores),
        "normalization_extrema": detect_normalization_extrema(gravity_scores),
    }

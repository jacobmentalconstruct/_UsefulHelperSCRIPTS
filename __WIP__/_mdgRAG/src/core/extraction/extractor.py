"""
Evidence Bag Extractor — deterministic graph-native subgraph extraction.

Ownership: src/core/extraction/extractor.py
    This module owns the extraction of bounded, token-budgeted, graph-native
    evidence bags from a scored VirtualManifold. Extraction is read-only —
    the VirtualManifold is never mutated.

Algorithm (gravity_greedy):
    1. Rank all VM nodes by gravity score (descending, node_id tie-break)
    2. Select top max_seed_nodes as seeds
    3. BFS expand from seeds up to max_hops (undirected adjacency)
    4. Collect connecting edges (both endpoints in expanded set)
    5. For each expanded node (gravity order): collect chunk + hierarchy bindings
    6. Greedy token budget enforcement: add nodes in gravity order while
       within token_budget, max_nodes, max_chunks limits
    7. Enforce max_edges on collected edges
    8. Build EvidenceBag with trace, provenance, and token budget metadata

Design constraints:
    - Pure Python — no external dependencies
    - Determinism via sorted() iteration throughout
    - VM parameter typed as Any (duck typing: get_nodes(), get_edges(),
      get_chunks(), get_node_chunk_bindings(), get_node_hierarchy_bindings(),
      get_metadata(), runtime_annotations)
    - Read-only against VM — same VM can be extracted multiple times
    - Reuses existing contracts: EvidenceBag, TokenBudget, EvidenceBagTrace,
      ScoreAnnotation from evidence_bag_contract

Legacy context:
    - Ego-graph extraction from SeamBuilderMS (radius=2 around anchors)
    - Token-budgeted packing from TokenPackerMS (greedy max-heap, 8000 tokens)
    - Friction detection from FrictionDetectorMS
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from src.core.types.ids import (
    ChunkHash,
    EdgeId,
    EvidenceBagId,
    HierarchyId,
    ManifoldId,
    NodeId,
    deterministic_hash,
)
from src.core.types.enums import ProvenanceStage, ProvenanceRelationOrigin
from src.core.types.provenance import Provenance
from src.core.contracts.evidence_bag_contract import (
    EvidenceBag,
    EvidenceBagTrace,
    ScoreAnnotation,
    TokenBudget,
)
from src.core.math.annotator import read_score_annotation


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ExtractionConfig:
    """
    Configuration for evidence bag extraction.

    All limits are hard caps — extraction stops when any is reached.
    Token budget uses Chunk.token_estimate for cost estimation.
    """

    max_seed_nodes: int = 3
    max_hops: int = 1
    token_budget: int = 2048
    max_nodes: int = 25
    max_edges: int = 40
    max_chunks: int = 12


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _rank_nodes_by_gravity(vm: Any) -> List[Tuple[NodeId, float]]:
    """
    Rank all VM nodes by gravity score.

    Reads ScoreAnnotation from vm.runtime_annotations for each node.
    Nodes without annotations get gravity=0.0.

    Returns:
        List of (node_id, gravity_score) sorted descending by gravity,
        then ascending by node_id (string) for deterministic tie-breaking.
    """
    nodes = vm.get_nodes()
    ranked: List[Tuple[NodeId, float]] = []

    for nid in sorted(nodes.keys()):
        annot = read_score_annotation(vm, nid)
        gravity = annot.gravity if annot is not None else 0.0
        ranked.append((nid, gravity))

    # Sort: descending gravity, ascending node_id for ties
    ranked.sort(key=lambda pair: (-pair[1], pair[0]))
    return ranked


def _select_seeds(
    ranked_nodes: List[Tuple[NodeId, float]],
    max_seed_nodes: int,
) -> List[NodeId]:
    """
    Select the top max_seed_nodes from the ranked list.

    Returns node IDs in gravity-descending order.
    If fewer nodes than max_seed_nodes, returns all.
    """
    return [nid for nid, _ in ranked_nodes[:max_seed_nodes]]


def _build_undirected_adjacency(vm: Any) -> Dict[NodeId, List[NodeId]]:
    """
    Build undirected adjacency from vm.get_edges().

    Both from_node_id and to_node_id treated as neighbors.
    Neighbor lists are sorted for determinism.
    Only includes nodes that exist in vm.get_nodes().
    """
    nodes = vm.get_nodes()
    adj: Dict[NodeId, List[NodeId]] = {nid: [] for nid in nodes}

    for edge in vm.get_edges().values():
        src = edge.from_node_id
        tgt = edge.to_node_id
        if src in adj and tgt in adj:
            adj[src].append(tgt)
            adj[tgt].append(src)

    # Sort neighbor lists for determinism
    for nid in adj:
        adj[nid] = sorted(set(adj[nid]))

    return adj


def _expand_bfs(
    seeds: List[NodeId],
    adjacency: Dict[NodeId, List[NodeId]],
    max_hops: int,
    all_node_ids: Set[NodeId],
) -> Set[NodeId]:
    """
    BFS expansion from seeds up to max_hops.

    Uses undirected adjacency. Only expands to nodes in all_node_ids.

    Returns:
        Set of expanded node IDs (includes seeds).
    """
    expanded: Set[NodeId] = set()
    frontier: List[NodeId] = []

    for nid in seeds:
        if nid in all_node_ids:
            expanded.add(nid)
            frontier.append(nid)

    for _ in range(max_hops):
        next_frontier: List[NodeId] = []
        for nid in frontier:
            for neighbor in adjacency.get(nid, []):
                if neighbor not in expanded:
                    expanded.add(neighbor)
                    next_frontier.append(neighbor)
        frontier = sorted(next_frontier)  # deterministic ordering for next hop

    return expanded


def _collect_connecting_edges(
    vm: Any,
    expanded_nodes: Set[NodeId],
) -> List[EdgeId]:
    """
    Collect edges where both endpoints are in the expanded set.

    Returns edge IDs sorted for determinism.
    """
    edges = vm.get_edges()
    result: List[EdgeId] = []

    for eid in sorted(edges.keys()):
        edge = edges[eid]
        if edge.from_node_id in expanded_nodes and edge.to_node_id in expanded_nodes:
            result.append(eid)

    return result


def _collect_chunk_bindings(
    vm: Any,
    node_id: NodeId,
) -> List[ChunkHash]:
    """
    Collect chunk hashes bound to a node, ordered by binding ordinal.

    Filters vm.get_node_chunk_bindings() for matching node_id.
    Returns chunk hashes sorted by ordinal, then by chunk_hash for ties.
    """
    bindings = vm.get_node_chunk_bindings()
    node_bindings = [
        b for b in bindings if b.node_id == node_id
    ]
    node_bindings.sort(key=lambda b: (b.ordinal, b.chunk_hash))
    return [b.chunk_hash for b in node_bindings]


def _collect_hierarchy_bindings(
    vm: Any,
    node_id: NodeId,
) -> List[HierarchyId]:
    """
    Collect hierarchy IDs bound to a node, sorted for determinism.

    Filters vm.get_node_hierarchy_bindings() for matching node_id.
    Returns hierarchy IDs sorted by string value.
    """
    bindings = vm.get_node_hierarchy_bindings()
    node_bindings = [
        b for b in bindings if b.node_id == node_id
    ]
    return sorted(b.hierarchy_id for b in node_bindings)


def _enforce_budget(
    ordered_nodes: List[Tuple[NodeId, float]],
    chunk_map: Dict[NodeId, List[ChunkHash]],
    chunk_token_lookup: Dict[ChunkHash, int],
    config: ExtractionConfig,
) -> Tuple[List[NodeId], Dict[NodeId, List[ChunkHash]], int]:
    """
    Greedy budget enforcement in gravity order.

    Iterates nodes in gravity order. For each node, computes token cost
    from its bound chunks. If adding the node stays within budget and
    hard limits, include it. Uses skip-not-break: if a node is too
    expensive, skip it and try the next one.

    If adding all of a node's chunks would exceed max_chunks, truncate
    to the remaining chunk slots (preserving ordinal order).

    Returns:
        (selected_node_ids, selected_chunk_refs, used_tokens)
    """
    selected_nodes: List[NodeId] = []
    selected_chunks: Dict[NodeId, List[ChunkHash]] = {}
    used_tokens = 0
    total_chunks = 0

    for nid, _ in ordered_nodes:
        # Hard limit: max nodes
        if len(selected_nodes) >= config.max_nodes:
            break

        node_chunks = list(chunk_map.get(nid, []))

        # Hard limit: max chunks — truncate if needed
        remaining_chunk_slots = config.max_chunks - total_chunks
        if remaining_chunk_slots <= 0 and node_chunks:
            # No chunk room — include node without chunks (preserves topology)
            node_chunks = []
        elif len(node_chunks) > remaining_chunk_slots:
            node_chunks = node_chunks[:remaining_chunk_slots]

        # Compute token cost for this node's chunks
        node_token_cost = sum(
            chunk_token_lookup.get(ch, 0) for ch in node_chunks
        )

        # Token budget check
        if used_tokens + node_token_cost > config.token_budget:
            # Try without chunks (node-only, zero token cost)
            if node_chunks:
                # Skip this node — it's too expensive with chunks
                continue
            # Node has no chunks, zero cost — include it

        selected_nodes.append(nid)
        selected_chunks[nid] = node_chunks
        used_tokens += node_token_cost
        total_chunks += len(node_chunks)

    return selected_nodes, selected_chunks, used_tokens


def _make_bag_id(
    selected_node_ids: List[NodeId],
    manifold_id: ManifoldId,
) -> EvidenceBagId:
    """
    Create a deterministic EvidenceBagId from selected nodes and manifold ID.

    Hash input: sorted node IDs joined by '|', followed by '|' and manifold_id.
    """
    sorted_ids = sorted(selected_node_ids)
    canonical = "|".join(sorted_ids) + "|" + manifold_id
    return EvidenceBagId(deterministic_hash(canonical))


def _make_provenance(
    bag_id: EvidenceBagId,
    manifold_id: ManifoldId,
) -> Provenance:
    """
    Create a Provenance record for the evidence bag extraction.
    """
    return Provenance(
        owner_kind="evidence_bag",
        owner_id=bag_id,
        source_manifold_id=manifold_id,
        stage=ProvenanceStage.EXTRACTION,
        relation_origin=ProvenanceRelationOrigin.COMPUTED,
        details={"extraction_strategy": "gravity_greedy"},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_evidence_bag(
    vm: Any,
    config: Optional[ExtractionConfig] = None,
) -> EvidenceBag:
    """
    Extract a deterministic, graph-native evidence bag from a scored VirtualManifold.

    Reads gravity scores from vm.runtime_annotations, selects seed nodes,
    expands via BFS, collects chunk and hierarchy bindings, enforces a
    token budget with hard caps, and packages everything into an EvidenceBag.

    The extraction is read-only — the VirtualManifold is not modified.

    Args:
        vm: Scored VirtualManifold (duck-typed). Must provide:
            get_nodes(), get_edges(), get_chunks(),
            get_node_chunk_bindings(), get_node_hierarchy_bindings(),
            get_metadata(), runtime_annotations.
        config: ExtractionConfig. If None, uses defaults.

    Returns:
        EvidenceBag with selected nodes, edges, chunk refs, hierarchy refs,
        score annotations, provenance, token budget, and construction trace.
    """
    if config is None:
        config = ExtractionConfig()

    nodes = vm.get_nodes()
    manifold_id = vm.get_metadata().manifold_id

    # Empty VM → empty bag
    if not nodes:
        bag_id = _make_bag_id([], manifold_id)
        return EvidenceBag(
            bag_id=bag_id,
            token_budget=TokenBudget(
                max_tokens=config.token_budget,
                used_tokens=0,
                remaining_tokens=config.token_budget,
                estimator="split_heuristic",
            ),
            trace=EvidenceBagTrace(
                source_virtual_manifold_id=manifold_id,
                extraction_strategy="gravity_greedy",
                hop_depth=config.max_hops,
                seed_node_count=0,
                total_candidates=0,
                selected_count=0,
                parameters=_config_to_params(config),
            ),
            provenance=[_make_provenance(bag_id, manifold_id)],
        )

    # Step 1: Rank nodes by gravity
    ranked = _rank_nodes_by_gravity(vm)

    # Step 2: Select seeds
    seeds = _select_seeds(ranked, config.max_seed_nodes)

    # Step 3: BFS expansion
    adjacency = _build_undirected_adjacency(vm)
    all_node_ids = set(nodes.keys())
    expanded_nodes = _expand_bfs(seeds, adjacency, config.max_hops, all_node_ids)
    total_candidates = len(expanded_nodes)

    # Step 4: Collect connecting edges
    connecting_edges = _collect_connecting_edges(vm, expanded_nodes)

    # Step 5: Order expanded nodes by gravity for greedy selection
    expanded_gravity_order: List[Tuple[NodeId, float]] = [
        (nid, gravity) for nid, gravity in ranked if nid in expanded_nodes
    ]

    # Step 5b: Collect chunk and hierarchy bindings for expanded nodes
    chunk_map: Dict[NodeId, List[ChunkHash]] = {}
    hierarchy_map: Dict[NodeId, List[HierarchyId]] = {}
    for nid, _ in expanded_gravity_order:
        chunk_map[nid] = _collect_chunk_bindings(vm, nid)
        hierarchy_map[nid] = _collect_hierarchy_bindings(vm, nid)

    # Build chunk token lookup
    chunks_dict = vm.get_chunks()
    chunk_token_lookup: Dict[ChunkHash, int] = {
        ch: chunks_dict[ch].token_estimate
        for ch in chunks_dict
    }

    # Step 6: Greedy budget enforcement
    selected_nodes, selected_chunk_refs, used_tokens = _enforce_budget(
        expanded_gravity_order, chunk_map, chunk_token_lookup, config,
    )

    # Step 7: Enforce max_edges — only edges connecting selected nodes
    selected_node_set = set(selected_nodes)
    edges_dict = vm.get_edges()
    final_edges: List[EdgeId] = []
    for eid in connecting_edges:
        edge = edges_dict[eid]
        if edge.from_node_id in selected_node_set and edge.to_node_id in selected_node_set:
            final_edges.append(eid)
            if len(final_edges) >= config.max_edges:
                break

    # Step 8: Build hierarchy refs for selected nodes
    selected_hierarchy_refs: Dict[NodeId, List[HierarchyId]] = {
        nid: hierarchy_map.get(nid, [])
        for nid in selected_nodes
        if hierarchy_map.get(nid, [])
    }

    # Step 9: Score annotations for selected nodes
    scores: Dict[NodeId, ScoreAnnotation] = {}
    for nid in selected_nodes:
        annot = read_score_annotation(vm, nid)
        scores[nid] = annot if annot is not None else ScoreAnnotation()

    # Step 10: Build bag ID, trace, provenance, token budget
    bag_id = _make_bag_id(selected_nodes, manifold_id)

    trace = EvidenceBagTrace(
        source_virtual_manifold_id=manifold_id,
        extraction_strategy="gravity_greedy",
        hop_depth=config.max_hops,
        seed_node_count=len(seeds),
        total_candidates=total_candidates,
        selected_count=len(selected_nodes),
        parameters=_config_to_params(config),
    )

    provenance = _make_provenance(bag_id, manifold_id)

    token_budget = TokenBudget(
        max_tokens=config.token_budget,
        used_tokens=used_tokens,
        remaining_tokens=config.token_budget - used_tokens,
        estimator="split_heuristic",
    )

    return EvidenceBag(
        bag_id=bag_id,
        node_ids=selected_nodes,
        edge_ids=final_edges,
        chunk_refs=selected_chunk_refs,
        hierarchy_refs=selected_hierarchy_refs,
        scores=scores,
        provenance=[provenance],
        token_budget=token_budget,
        trace=trace,
    )


def _config_to_params(config: ExtractionConfig) -> Dict[str, Any]:
    """Convert ExtractionConfig to a parameters dict for trace metadata."""
    return {
        "max_seed_nodes": config.max_seed_nodes,
        "max_hops": config.max_hops,
        "token_budget": config.token_budget,
        "max_nodes": config.max_nodes,
        "max_edges": config.max_edges,
        "max_chunks": config.max_chunks,
    }

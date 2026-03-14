"""
Evidence Hydrator — deterministic content materialisation from evidence bags.

Ownership: src/core/hydration/hydrator.py
    This module owns the hydration of evidence bags into structured,
    model-readable HydratedBundles. Hydration resolves abstract references
    (node IDs, chunk hashes, hierarchy IDs) into concrete content payloads
    and translated edge relationships. Hydration is read-only — the
    VirtualManifold and EvidenceBag are never mutated.

Algorithm:
    1. Read EvidenceBag node_ids (already gravity-ordered from extraction)
    2. For each node: resolve chunk_refs to chunk text via VM.get_chunks()
    3. For each node: resolve hierarchy_refs to hierarchy context via VM.get_hierarchy()
    4. For each node: build HydratedNode with content, scores, metadata
    5. For each edge: translate to HydratedEdge with human-readable relation
    6. Budget enforcement: if budget_target set and total tokens exceed it,
       truncate from end (lowest gravity nodes first)
    7. Build HydratedBundle with provenance, budget metadata, and mode

Design constraints:
    - Pure Python — no external dependencies
    - Determinism via ordered iteration (EvidenceBag node order preserved)
    - VM parameter typed as Any (duck typing: get_nodes(), get_edges(),
      get_chunks(), get_hierarchy())
    - Read-only against VM and EvidenceBag — neither is modified
    - Reuses existing contracts: HydratedBundle, HydratedNode, HydratedEdge
      from hydration_contract
    - No model calls, no embedding, no scoring, no extraction

Pipeline position: Extraction → Hydration → Synthesis

Legacy context:
    - Content retrieval from ContentStoreMS
    - Context string assembly from TokenPackerMS
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.core.types.ids import (
    ChunkHash,
    EdgeId,
    HierarchyId,
    ManifoldId,
    NodeId,
)
from src.core.types.enums import (
    HydrationMode,
    ProvenanceStage,
    ProvenanceRelationOrigin,
)
from src.core.types.provenance import Provenance
from src.core.contracts.hydration_contract import (
    HydratedBundle,
    HydratedEdge,
    HydratedNode,
)
from src.core.contracts.evidence_bag_contract import (
    EvidenceBag,
    ScoreAnnotation,
)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class HydrationConfig:
    """
    Configuration for evidence bag hydration.

    Controls which metadata is included, how content is materialised,
    and optional budget enforcement for the receiving model slot.
    """

    mode: HydrationMode = HydrationMode.FULL
    budget_target: Optional[int] = None   # If set, truncate nodes to fit
    include_scores: bool = True           # Include score annotations in metadata
    include_hierarchy: bool = True        # Include hierarchy context in metadata
    include_provenance: bool = True       # Include provenance in bundle properties


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_node_content(
    evidence_bag: EvidenceBag,
    vm: Any,
    node_id: NodeId,
    mode: HydrationMode,
) -> Tuple[str, int, List[ChunkHash]]:
    """
    Resolve chunk references for a single node into content.

    For FULL/SUMMARY mode: concatenates chunk_text values separated by
    "\\n\\n", sums token_estimate values.
    For REFERENCE mode: returns empty content and zero tokens, but
    still returns chunk_hashes list for traceability.

    Returns:
        (content_text, token_estimate, chunk_hashes_list)
    """
    chunk_hashes = list(evidence_bag.chunk_refs.get(node_id, []))
    chunks_dict = vm.get_chunks()

    if mode == HydrationMode.REFERENCE:
        return "", 0, chunk_hashes

    texts: List[str] = []
    total_tokens = 0

    for ch in chunk_hashes:
        chunk = chunks_dict.get(ch)
        if chunk is None:
            continue  # Defensive: skip missing chunks
        texts.append(chunk.chunk_text)
        total_tokens += chunk.token_estimate

    content = "\n\n".join(texts)
    return content, total_tokens, chunk_hashes


def _resolve_hierarchy_context(
    evidence_bag: EvidenceBag,
    vm: Any,
    node_id: NodeId,
) -> List[Dict[str, Any]]:
    """
    Resolve hierarchy references for a single node into structured context.

    Returns a list of dicts with hierarchy_id, depth, sort_order,
    path_label, and parent_id. Sorted by (depth, sort_order, hierarchy_id)
    for determinism.
    """
    hierarchy_ids = evidence_bag.hierarchy_refs.get(node_id, [])
    if not hierarchy_ids:
        return []

    hierarchy_dict = vm.get_hierarchy()
    result: List[Dict[str, Any]] = []

    for hid in hierarchy_ids:
        entry = hierarchy_dict.get(hid)
        if entry is None:
            continue  # Defensive: skip missing entries
        result.append({
            "hierarchy_id": str(hid),
            "depth": entry.depth,
            "sort_order": entry.sort_order,
            "path_label": entry.path_label,
            "parent_id": str(entry.parent_id) if entry.parent_id else None,
        })

    # Sort for determinism
    result.sort(key=lambda d: (d["depth"], d["sort_order"], d["hierarchy_id"]))
    return result


def _build_node_metadata(
    evidence_bag: EvidenceBag,
    vm: Any,
    node_id: NodeId,
    config: HydrationConfig,
) -> Dict[str, Any]:
    """
    Assemble the metadata dict for a HydratedNode.

    Includes score annotations, hierarchy context, and node properties
    depending on config flags.
    """
    metadata: Dict[str, Any] = {}

    # Score annotation
    if config.include_scores and node_id in evidence_bag.scores:
        score = evidence_bag.scores[node_id]
        metadata["score"] = {
            "structural": score.structural,
            "semantic": score.semantic,
            "gravity": score.gravity,
            "raw_scores": dict(score.raw_scores),
        }

    # Hierarchy context
    if config.include_hierarchy:
        hierarchy = _resolve_hierarchy_context(evidence_bag, vm, node_id)
        if hierarchy:
            metadata["hierarchy"] = hierarchy

    # Node properties from VM
    node = vm.get_nodes().get(node_id)
    if node is not None and node.properties:
        metadata["properties"] = dict(node.properties)

    return metadata


def _hydrate_single_node(
    evidence_bag: EvidenceBag,
    vm: Any,
    node_id: NodeId,
    config: HydrationConfig,
) -> HydratedNode:
    """
    Hydrate a single node into a HydratedNode contract type.

    Resolves chunk content, label, type, and metadata.
    """
    node = vm.get_nodes().get(node_id)

    content, token_estimate, chunk_hashes = _resolve_node_content(
        evidence_bag, vm, node_id, config.mode,
    )

    metadata = _build_node_metadata(evidence_bag, vm, node_id, config)

    return HydratedNode(
        node_id=node_id,
        content=content,
        token_estimate=token_estimate,
        chunk_hashes=chunk_hashes,
        label=node.label if node is not None else "",
        node_type=node.node_type.name if node is not None else "",
        metadata=metadata,
    )


def _translate_single_edge(
    vm: Any,
    edge_id: EdgeId,
) -> Optional[HydratedEdge]:
    """
    Translate a single edge into a HydratedEdge.

    Returns None if the edge is not found in the VM (defensive).
    """
    edge = vm.get_edges().get(edge_id)
    if edge is None:
        return None

    metadata: Dict[str, Any] = {}
    if edge.properties:
        metadata = dict(edge.properties)

    return HydratedEdge(
        edge_id=edge_id,
        source_id=edge.from_node_id,
        target_id=edge.to_node_id,
        relation=edge.edge_type.name,
        weight=edge.weight,
        metadata=metadata,
    )


def _enforce_hydration_budget(
    nodes: List[HydratedNode],
    budget_target: Optional[int],
) -> Tuple[List[HydratedNode], int]:
    """
    Budget enforcement — truncate from end if total tokens exceed budget.

    Nodes are already gravity-ordered (from extraction). Walk forward and
    include nodes while within budget. Always keep at least one node.

    Returns:
        (included_nodes, total_tokens)
    """
    if budget_target is None or not nodes:
        total = sum(n.token_estimate for n in nodes)
        return nodes, total

    included: List[HydratedNode] = []
    running_total = 0

    for i, node in enumerate(nodes):
        if i == 0:
            # Always include the first (highest gravity) node
            included.append(node)
            running_total += node.token_estimate
            continue

        if running_total + node.token_estimate <= budget_target:
            included.append(node)
            running_total += node.token_estimate
        # else: skip — over budget

    return included, running_total


def _make_hydration_provenance(
    evidence_bag: EvidenceBag,
    manifold_id: Optional[ManifoldId],
) -> Dict[str, Any]:
    """
    Create a provenance record dict for the hydration stage.

    Returns a serialisable dict (not a Provenance object) for inclusion
    in HydratedBundle.properties.
    """
    return {
        "owner_kind": "hydrated_bundle",
        "owner_id": str(evidence_bag.bag_id),
        "source_manifold_id": str(manifold_id) if manifold_id else None,
        "stage": ProvenanceStage.HYDRATION.name,
        "relation_origin": ProvenanceRelationOrigin.COMPUTED.name,
        "details": {
            "hydration_source": "evidence_bag",
            "bag_id": str(evidence_bag.bag_id),
        },
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def hydrate_evidence_bag(
    evidence_bag: EvidenceBag,
    vm: Any,
    config: Optional[HydrationConfig] = None,
) -> HydratedBundle:
    """
    Hydrate an evidence bag into a structured, model-readable bundle.

    Resolves chunk references to text, translates edge relationships,
    assembles hierarchy context, and produces a deterministic HydratedBundle
    using the existing contract types.

    The hydration is read-only — neither the VM nor the EvidenceBag is modified.

    Args:
        evidence_bag: EvidenceBag with node_ids, edge_ids, chunk_refs,
            hierarchy_refs, scores, provenance, token_budget, trace.
        vm: Scored VirtualManifold (duck-typed). Must provide:
            get_nodes(), get_edges(), get_chunks(), get_hierarchy().
        config: HydrationConfig. If None, uses defaults (FULL mode).

    Returns:
        HydratedBundle with hydrated nodes, translated edges, token totals,
        provenance, budget metadata, and mode indicator.
    """
    if config is None:
        config = HydrationConfig()

    manifold_id = evidence_bag.trace.source_virtual_manifold_id

    # Empty bag → empty bundle
    if not evidence_bag.node_ids:
        source_ids = [manifold_id] if manifold_id else []
        return HydratedBundle(
            mode=config.mode,
            source_manifold_ids=source_ids,
            properties={
                "bag_id": str(evidence_bag.bag_id),
                "budget": {
                    "budget_target": config.budget_target,
                    "total_tokens": 0,
                    "nodes_hydrated": 0,
                    "nodes_available": 0,
                    "topology_preserved": True,
                },
            },
        )

    # Step 1: Hydrate nodes (preserving gravity order from extraction)
    hydrated_nodes: List[HydratedNode] = []
    for nid in evidence_bag.node_ids:
        hydrated_nodes.append(
            _hydrate_single_node(evidence_bag, vm, nid, config)
        )

    # Step 2: Translate edges
    hydrated_edges: List[HydratedEdge] = []
    for eid in evidence_bag.edge_ids:
        translated = _translate_single_edge(vm, eid)
        if translated is not None:
            hydrated_edges.append(translated)

    # Stable secondary sort for edges
    hydrated_edges.sort(
        key=lambda e: (str(e.source_id), str(e.target_id), str(e.edge_id))
    )

    # Step 3: Budget enforcement
    original_count = len(hydrated_nodes)
    hydrated_nodes, total_tokens = _enforce_hydration_budget(
        hydrated_nodes, config.budget_target,
    )
    topology_preserved = len(hydrated_nodes) == original_count

    # Step 4: Filter edges — only those connecting remaining nodes
    if not topology_preserved:
        remaining_nids = {n.node_id for n in hydrated_nodes}
        hydrated_edges = [
            e for e in hydrated_edges
            if e.source_id in remaining_nids and e.target_id in remaining_nids
        ]

    # Step 5: Build source manifold IDs
    source_ids: List[ManifoldId] = []
    if manifold_id:
        source_ids.append(manifold_id)

    # Step 6: Build properties
    properties: Dict[str, Any] = {
        "bag_id": str(evidence_bag.bag_id),
        "extraction_strategy": evidence_bag.trace.extraction_strategy,
        "budget": {
            "budget_target": config.budget_target,
            "total_tokens": total_tokens,
            "nodes_hydrated": len(hydrated_nodes),
            "nodes_available": original_count,
            "topology_preserved": topology_preserved,
        },
    }

    if config.include_provenance:
        properties["provenance"] = _make_hydration_provenance(
            evidence_bag, manifold_id,
        )

    return HydratedBundle(
        nodes=hydrated_nodes,
        edges=hydrated_edges,
        topology_preserved=topology_preserved,
        total_tokens=total_tokens,
        mode=config.mode,
        source_manifold_ids=source_ids,
        properties=properties,
    )


# ---------------------------------------------------------------------------
# Backward-compatible helpers (match hydrator_placeholder signatures)
# ---------------------------------------------------------------------------

def hydrate_node_payloads(
    evidence_bag: Any,
    content_resolver: Any,
) -> Dict[NodeId, str]:
    """
    Resolve evidence bag node references to full content payloads.

    Backward-compatible helper matching the Phase 1 placeholder signature.
    The content_resolver is treated as a duck-typed VM (must provide
    get_chunks()).

    Args:
        evidence_bag: EvidenceBag instance.
        content_resolver: VM or content source with get_chunks().

    Returns:
        Dict mapping NodeId to resolved content text.
    """
    result: Dict[NodeId, str] = {}

    for nid in evidence_bag.node_ids:
        content, _, _ = _resolve_node_content(
            evidence_bag, content_resolver, nid, HydrationMode.FULL,
        )
        result[nid] = content

    return result


def translate_edges(
    evidence_bag: Any,
) -> List[Dict[str, Any]]:
    """
    Translate evidence bag edges into presentable form.

    Backward-compatible helper matching the Phase 1 placeholder signature.
    Without a VM reference, returns edge ID dicts only.

    Args:
        evidence_bag: EvidenceBag instance.

    Returns:
        List of dicts, each containing at minimum an edge_id key.
    """
    result: List[Dict[str, Any]] = []

    for eid in evidence_bag.edge_ids:
        result.append({"edge_id": str(eid)})

    return result


def format_evidence_bundle(
    hydrated_nodes: Dict[NodeId, str],
    translated_edges: List[Dict[str, Any]],
    preserve_topology: bool = True,
) -> str:
    """
    Format a complete evidence bundle as structured text.

    Backward-compatible helper matching the Phase 1 placeholder signature.
    Produces a deterministic, human/model-readable text representation.

    Args:
        hydrated_nodes: Dict mapping NodeId to content text.
        translated_edges: List of edge dicts.
        preserve_topology: Whether topology was preserved.

    Returns:
        Formatted evidence bundle string.
    """
    sections: List[str] = []

    sections.append("=== EVIDENCE BUNDLE ===")
    sections.append(f"Topology preserved: {preserve_topology}")
    sections.append(f"Nodes: {len(hydrated_nodes)}")
    sections.append(f"Edges: {len(translated_edges)}")
    sections.append("")

    # Nodes section — sorted by node_id for determinism
    sections.append("--- NODES ---")
    for nid in sorted(hydrated_nodes.keys()):
        content = hydrated_nodes[nid]
        sections.append(f"[{nid}]")
        sections.append(content if content else "(no content)")
        sections.append("")

    # Edges section
    if translated_edges:
        sections.append("--- EDGES ---")
        for edge_dict in translated_edges:
            parts = [f"{k}={v}" for k, v in sorted(edge_dict.items())]
            sections.append(", ".join(parts))
        sections.append("")

    return "\n".join(sections)

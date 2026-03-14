"""
Inspection helpers — structured dump functions for pipeline artifacts.

Ownership: src/core/debug/inspection.py
    Development-time diagnostic helpers for inspecting major pipeline
    artifacts. Each function takes a typed artifact and returns a
    structured dict suitable for logging or REPL inspection.

    Inspection stays in debug tooling — not embedded as ad-hoc
    runtime prints.

Usage:
    from src.core.debug.inspection import dump_projection_summary
    summary = dump_projection_summary(projected_slice)
    print(summary)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def dump_projection_summary(projected_slice: Any) -> Dict[str, Any]:
    """
    Summarise a ProjectedSlice for developer inspection.

    Args:
        projected_slice: A ProjectedSlice instance (duck-typed).

    Returns:
        Dict with source, counts for nodes/edges/chunks/embeddings/
        hierarchy/bindings, and the node IDs list.
    """
    meta = projected_slice.metadata
    return {
        "source_manifold_id": str(meta.source_manifold_id),
        "source_kind": meta.source_kind.name if hasattr(meta.source_kind, "name") else str(meta.source_kind),
        "timestamp": meta.timestamp,
        "description": meta.description,
        "node_count": len(projected_slice.nodes),
        "edge_count": len(projected_slice.edges),
        "chunk_count": len(projected_slice.chunks),
        "embedding_count": len(projected_slice.embeddings),
        "hierarchy_count": len(projected_slice.hierarchy_entries),
        "nc_bindings": len(projected_slice.node_chunk_bindings),
        "ne_bindings": len(projected_slice.node_embedding_bindings),
        "nh_bindings": len(projected_slice.node_hierarchy_bindings),
        "provenance_count": len(projected_slice.provenance_entries),
        "node_ids": [str(nid) for nid in projected_slice.node_ids],
    }


def dump_fusion_result(fusion_result: Any) -> Dict[str, Any]:
    """
    Summarise a FusionResult for developer inspection.

    Args:
        fusion_result: A FusionResult instance (duck-typed).

    Returns:
        Dict with VM identity, population counts, bridge breakdown
        by match_type, ancestry info, and provenance count.
    """
    vm = fusion_result.virtual_manifold
    vm_meta = vm.get_metadata()

    # Categorise bridges by match_type
    bridge_types: Dict[str, int] = {}
    for be in fusion_result.bridge_edges:
        mt = be.properties.get("match_type", "explicit")
        bridge_types[mt] = bridge_types.get(mt, 0) + 1

    return {
        "vm_id": str(vm_meta.manifold_id),
        "vm_node_count": len(vm.get_nodes()),
        "vm_edge_count": len(vm.get_edges()),
        "bridge_count": len(fusion_result.bridge_edges),
        "bridge_types": bridge_types,
        "source_manifold_ids": [
            str(mid) for mid in fusion_result.ancestry.source_manifold_ids
        ],
        "projection_count": fusion_result.ancestry.projection_count,
        "strategy": fusion_result.ancestry.strategy,
        "provenance_count": len(fusion_result.provenance),
    }


def dump_evidence_bag(evidence_bag: Any) -> Dict[str, Any]:
    """
    Summarise an EvidenceBag for developer inspection.

    Args:
        evidence_bag: An EvidenceBag instance (duck-typed).

    Returns:
        Dict with bag_id, node/edge/chunk counts, token budget,
        top-scored nodes, and trace summary.
    """
    # Top nodes by gravity score (descending)
    top_gravity: List[Dict[str, Any]] = []
    for nid in evidence_bag.node_ids[:10]:
        score = evidence_bag.scores.get(nid)
        if score is not None:
            top_gravity.append({
                "node_id": str(nid),
                "gravity": round(score.gravity, 6),
                "structural": round(score.structural, 6),
                "semantic": round(score.semantic, 6),
            })

    total_chunks = sum(
        len(refs) for refs in evidence_bag.chunk_refs.values()
    )

    # manifold_id lives on the trace, not the bag itself
    vm_id = getattr(evidence_bag.trace, "source_virtual_manifold_id", None)

    return {
        "bag_id": str(evidence_bag.bag_id),
        "source_virtual_manifold_id": str(vm_id) if vm_id else None,
        "node_count": len(evidence_bag.node_ids),
        "edge_count": len(evidence_bag.edge_ids),
        "chunk_ref_count": total_chunks,
        "hierarchy_ref_count": sum(
            len(refs) for refs in evidence_bag.hierarchy_refs.values()
        ),
        "token_budget": {
            "used": evidence_bag.token_budget.used_tokens,
            "max": evidence_bag.token_budget.max_tokens,
            "utilization": round(
                evidence_bag.token_budget.used_tokens
                / max(evidence_bag.token_budget.max_tokens, 1),
                4,
            ),
        },
        "top_gravity": top_gravity,
    }


def dump_hydrated_bundle(hydrated_bundle: Any) -> Dict[str, Any]:
    """
    Summarise a HydratedBundle for developer inspection.

    Args:
        hydrated_bundle: A HydratedBundle instance (duck-typed).

    Returns:
        Dict with node/edge/token counts, mode, topology preserved
        flag, and content lengths per node.
    """
    content_lengths: List[Dict[str, Any]] = []
    for node in hydrated_bundle.nodes:
        content_lengths.append({
            "node_id": str(node.node_id),
            "label": node.label,
            "content_length": len(node.content),
        })

    return {
        "node_count": len(hydrated_bundle.nodes),
        "edge_count": len(hydrated_bundle.edges),
        "total_tokens": hydrated_bundle.total_tokens,
        "mode": hydrated_bundle.mode.value if hasattr(hydrated_bundle.mode, "value") else str(hydrated_bundle.mode),
        "topology_preserved": hydrated_bundle.topology_preserved,
        "content_lengths": content_lengths,
    }


def inspect_pipeline_result(pipeline_result: Any) -> Dict[str, Any]:
    """
    Summarise a PipelineResult for developer inspection.

    Args:
        pipeline_result: A PipelineResult instance (duck-typed).

    Returns:
        Dict with overall status, stage count, timing breakdown,
        degraded flag, skipped stages, and artifact presence flags.
    """
    return {
        "answer_length": len(pipeline_result.answer_text),
        "has_synthesis": pipeline_result.synthesis_response is not None,
        "degraded": pipeline_result.degraded,
        "skipped_stages": list(pipeline_result.skipped_stages),
        "stage_count": pipeline_result.stage_count,
        "timing": {k: round(v, 4) for k, v in pipeline_result.timing.items()},
        "artifacts": {
            "query_artifact": pipeline_result.query_artifact is not None,
            "identity_slice": pipeline_result.identity_slice is not None,
            "external_slice": pipeline_result.external_slice is not None,
            "fusion_result": pipeline_result.fusion_result is not None,
            "evidence_bag": pipeline_result.evidence_bag is not None,
            "hydrated_bundle": pipeline_result.hydrated_bundle is not None,
        },
        "scoring_summary": {
            "structural_nodes": len(pipeline_result.structural_scores),
            "semantic_nodes": len(pipeline_result.semantic_scores),
            "gravity_nodes": len(pipeline_result.gravity_scores),
        },
    }

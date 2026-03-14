"""
Score Annotator — bridges pure math output to VirtualManifold runtime annotations.

Ownership: src/core/math/annotator.py
    This module writes pre-computed score dicts into a VirtualManifold's
    runtime_annotations dict. It does NOT compute scores — that is
    scoring.py's job. This is the write bridge only.

The canonical storage key for score annotations is "score". Downstream
consumers (extraction, hydration) look up scores at this key.

Storage layout:
    vm.runtime_annotations[node_id]["score"] = ScoreAnnotation(
        structural=..., semantic=..., gravity=..., raw_scores={...}
    )

Design constraints:
    - Imports ScoreAnnotation from evidence_bag_contract
    - VM parameter typed as Any (duck typing: must have runtime_annotations)
    - Does not compute — only writes and reads
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from src.core.types.ids import NodeId
from src.core.contracts.evidence_bag_contract import ScoreAnnotation


# Canonical key in runtime_annotations for score data
SCORE_ANNOTATION_KEY = "score"


def annotate_scores(
    vm: Any,
    structural: Dict[NodeId, float],
    semantic: Dict[NodeId, float],
    gravity: Dict[NodeId, float],
    raw_scores: Optional[Dict[str, Dict[NodeId, float]]] = None,
) -> None:
    """
    Write score annotations into a VirtualManifold's runtime_annotations.

    For each node that appears in any of the score dicts, creates a
    ScoreAnnotation and stores it at vm.runtime_annotations[nid]["score"].

    Preserves any existing annotations on the node — only the "score" key
    is set/overwritten.

    Args:
        vm: Object with runtime_annotations property (Dict[NodeId, Dict[str, Any]]).
            Duck-typed to avoid importing VirtualManifold.
        structural: Node ID → structural (PageRank) score.
        semantic: Node ID → semantic (cosine) score.
        gravity: Node ID → gravity (fused) score.
        raw_scores: Optional extra scores dict. Keys are score names,
            values are per-node score dicts. Stored in ScoreAnnotation.raw_scores.
    """
    all_nids = sorted(set(structural) | set(semantic) | set(gravity))

    for nid in all_nids:
        # Build raw_scores for this node
        node_raw: Dict[str, float] = {}
        if raw_scores:
            for score_name, score_dict in raw_scores.items():
                if nid in score_dict:
                    node_raw[score_name] = score_dict[nid]

        annotation = ScoreAnnotation(
            structural=structural.get(nid, 0.0),
            semantic=semantic.get(nid, 0.0),
            gravity=gravity.get(nid, 0.0),
            raw_scores=node_raw,
        )

        # Ensure the node has an annotations dict
        if nid not in vm.runtime_annotations:
            vm.runtime_annotations[nid] = {}

        vm.runtime_annotations[nid][SCORE_ANNOTATION_KEY] = annotation


def read_score_annotation(
    vm: Any,
    node_id: NodeId,
) -> Optional[ScoreAnnotation]:
    """
    Read a ScoreAnnotation from a VirtualManifold's runtime_annotations.

    Args:
        vm: Object with runtime_annotations property (Dict[NodeId, Dict[str, Any]]).
        node_id: The node to look up.

    Returns:
        ScoreAnnotation if found, None otherwise.
    """
    node_annots = vm.runtime_annotations.get(node_id)
    if node_annots is None:
        return None
    return node_annots.get(SCORE_ANNOTATION_KEY)

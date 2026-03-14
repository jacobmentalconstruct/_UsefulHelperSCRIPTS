"""
Score Dump — readable scoring summary from a VirtualManifold.

Ownership: src/core/debug/score_dump.py
    Development-time diagnostic helper. Extracts score annotations
    from a VirtualManifold's runtime_annotations and formats them
    for human inspection.

Usage:
    from src.core.debug.score_dump import dump_virtual_scores
    summary = dump_virtual_scores(vm)
    print(summary)

Output shape:
    {
        "node_count": int,
        "annotated_count": int,
        "scores": {
            node_id: {
                "structural": float,
                "semantic": float,
                "gravity": float,
            }
        },
        "top_gravity": [
            (node_id, gravity_score),
            ...  # top 10 by gravity, descending
        ]
    }
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from src.core.types.ids import NodeId
from src.core.math.annotator import SCORE_ANNOTATION_KEY


def dump_virtual_scores(vm: Any) -> Dict[str, Any]:
    """
    Extract a readable scoring summary from a VirtualManifold.

    Reads score annotations from vm.runtime_annotations and produces
    a structured summary dict suitable for logging or inspection.

    Args:
        vm: Object with get_nodes() and runtime_annotations property.
            Duck-typed to avoid importing VirtualManifold.

    Returns:
        Dict with node_count, annotated_count, per-node scores (rounded
        to 6 decimals), and top_gravity (top 10 by gravity, descending).
    """
    nodes = vm.get_nodes()
    annotations = vm.runtime_annotations

    node_count = len(nodes)
    annotated_count = 0
    scores: Dict[str, Dict[str, float]] = {}
    gravity_pairs: List[Tuple[str, float]] = []

    for nid in sorted(nodes.keys()):
        node_annots = annotations.get(nid)
        if node_annots is None:
            continue

        score_annot = node_annots.get(SCORE_ANNOTATION_KEY)
        if score_annot is None:
            continue

        annotated_count += 1
        scores[nid] = {
            "structural": round(score_annot.structural, 6),
            "semantic": round(score_annot.semantic, 6),
            "gravity": round(score_annot.gravity, 6),
        }
        gravity_pairs.append((nid, score_annot.gravity))

    # Sort by gravity descending, take top 10
    gravity_pairs.sort(key=lambda x: x[1], reverse=True)
    top_gravity = [
        (nid, round(g, 6)) for nid, g in gravity_pairs[:10]
    ]

    return {
        "node_count": node_count,
        "annotated_count": annotated_count,
        "scores": scores,
        "top_gravity": top_gravity,
    }

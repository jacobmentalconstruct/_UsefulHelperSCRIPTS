"""
External Projection — project relevant external graph slices.

Ownership: src/core/projection/external_projection.py
    - Projects selected external nodes by ID
    - Projects connected edges between selected nodes
    - Projects linked chunks/embeddings/hierarchy/metadata/provenance
    - Preserves source manifold ID and source object IDs

This projection selects relevant portions of the external manifold
(corpus, domain knowledge, source evidence) based on query criteria.
It operates solely on the external manifold — isolated from identity.

Future extraction targets (from legacy):
    - Anchor discovery from AnchorDiscoveryMS (FAISS top-K)
    - Ego-graph extraction from SeamBuilderMS
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from src.core.contracts.projection_contract import (
    ProjectedSlice,
    ProjectionContract,
)
from src.core.projection._projection_core import gather_slice_by_node_ids
from src.core.store.manifold_store import ManifoldStore
from src.core.types.ids import NodeId
from src.core.types.enums import ProjectionSourceKind


class ExternalProjection(ProjectionContract):
    """
    Project relevant external graph slices for fusion.

    Constructor accepts an optional ManifoldStore for SQLite-backed
    external manifolds. For RAM manifolds, store can be None.
    """

    def __init__(self, store: Optional[ManifoldStore] = None) -> None:
        self._store = store

    def project(
        self,
        manifold: Any,
        criteria: Dict[str, Any],
    ) -> ProjectedSlice:
        """
        Project external manifold slice based on criteria.

        Supported criteria keys:
            - "node_ids": List[str] -- explicit node IDs to project

        Future criteria (not yet implemented):
            - "topic": project by topic cluster
            - "embedding_query": project by embedding similarity
            - "anchor_ids": project FAISS anchor neighborhoods
        """
        node_ids_raw = criteria.get("node_ids", [])
        node_ids = [NodeId(nid) for nid in node_ids_raw]

        conn = getattr(manifold, "connection", None)

        return gather_slice_by_node_ids(
            manifold=manifold,
            node_ids=node_ids,
            source_kind=ProjectionSourceKind.EXTERNAL,
            store=self._store,
            conn=conn,
            criteria=criteria,
            description="External projection",
        )

    def project_by_ids(
        self,
        manifold: Any,
        node_ids: List[NodeId],
    ) -> ProjectedSlice:
        """Convenience: project specific node IDs from the external manifold."""
        return self.project(manifold, {"node_ids": node_ids})

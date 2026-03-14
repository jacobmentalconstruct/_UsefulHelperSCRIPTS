"""
Identity Projection — project relevant identity/session state.

Ownership: src/core/projection/identity_projection.py
    - Projects selected identity nodes by ID
    - Projects connected edges between selected nodes
    - Projects linked chunks/embeddings/hierarchy/metadata/provenance
    - Preserves source manifold ID and source object IDs

Same-schema rule: operates on identity manifold data only. External
corpus content is never mixed in at the projection stage.

Future extraction targets (from legacy):
    - Session context selection patterns from Mind 2
    - Chat history windowing from Backend orchestrator
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


class IdentityProjection(ProjectionContract):
    """
    Project relevant identity and session state into a materialised slice.

    The prompt enters the identity side first — this is the crucial
    ordering rule for the projection pipeline.

    Constructor accepts an optional ManifoldStore for SQLite-backed
    identity manifolds. For RAM manifolds, store can be None.
    """

    def __init__(self, store: Optional[ManifoldStore] = None) -> None:
        self._store = store

    def project(
        self,
        manifold: Any,
        criteria: Dict[str, Any],
    ) -> ProjectedSlice:
        """
        Project identity manifold slice based on criteria.

        Supported criteria keys:
            - "node_ids": List[str] -- explicit node IDs to project

        Future criteria (not yet implemented):
            - "session_id": project all nodes in a session
            - "user_id": project all nodes for a user
            - "role": project by role type
        """
        node_ids_raw = criteria.get("node_ids", [])
        node_ids = [NodeId(nid) for nid in node_ids_raw]

        conn = getattr(manifold, "connection", None)

        return gather_slice_by_node_ids(
            manifold=manifold,
            node_ids=node_ids,
            source_kind=ProjectionSourceKind.IDENTITY,
            store=self._store,
            conn=conn,
            criteria=criteria,
            description="Identity projection",
        )

    def project_by_ids(
        self,
        manifold: Any,
        node_ids: List[NodeId],
    ) -> ProjectedSlice:
        """Convenience: project specific node IDs from the identity manifold."""
        return self.project(manifold, {"node_ids": node_ids})

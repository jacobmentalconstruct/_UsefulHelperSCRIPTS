"""
Virtual Manifold — ephemeral fused workspace.

Ownership: src/core/manifolds/virtual_manifold.py
    - Ephemeral fused manifold created at query time
    - Projected identities from identity and external manifolds preserved
    - Runtime-only score annotations are permitted here
    - Destroyed after synthesis is complete

This manifold is clearly marked as TEMPORARY and DERIVED. It does not
own persistent data. It exists only for the duration of a single
query-processing lifecycle.

Same-schema rule: the structural contract is preserved — same
collections as identity and external manifolds, enforced by
inheriting BaseManifold.

Additional capabilities (beyond base):
    - Tracks which source manifolds contributed via projection
    - Holds runtime-only score annotations
    - Can be disposed after synthesis

Future extraction targets (from legacy):
    - Gravity score annotation from GravityScorerMS
    - Seam composition from SeamBuilderMS
    - Token-packed context from TokenPackerMS
"""

from __future__ import annotations

from dataclasses import field
from typing import Any, Dict, List, Optional

from src.core.manifolds.base_manifold import BaseManifold
from src.core.types.ids import ManifoldId, NodeId
from src.core.types.enums import ManifoldRole, StorageMode


class VirtualManifold(BaseManifold):
    """
    Virtual manifold — ephemeral fused workspace for query processing.

    Created by fusion, consumed by extraction and synthesis, then destroyed.
    Runtime-only score annotations are allowed on this manifold's nodes.

    Uses the same structural contract as all manifolds (same-schema rule)
    but adds ephemeral-specific tracking for source projections and
    runtime annotations.
    """

    def __init__(
        self,
        manifold_id: ManifoldId,
    ) -> None:
        super().__init__(
            manifold_id=manifold_id,
            role=ManifoldRole.VIRTUAL,
            storage_mode=StorageMode.PYTHON_RAM,
        )
        # --- virtual-specific state (same schema, different lifecycle) ---
        self._source_manifold_ids: List[ManifoldId] = []
        self._runtime_annotations: Dict[NodeId, Dict[str, Any]] = {}

    @property
    def source_manifold_ids(self) -> List[ManifoldId]:
        """IDs of the manifolds whose projections were fused into this one."""
        return self._source_manifold_ids

    @property
    def runtime_annotations(self) -> Dict[NodeId, Dict[str, Any]]:
        """Runtime-only score/metadata annotations on nodes."""
        return self._runtime_annotations

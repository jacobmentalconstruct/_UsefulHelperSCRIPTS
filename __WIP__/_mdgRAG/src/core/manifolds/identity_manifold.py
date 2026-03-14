"""
Identity Manifold — session memory and user/agent/role graph.

Ownership: src/core/manifolds/identity_manifold.py
    - Identity-side population only
    - Session memory structures
    - User, agent, and role graph nodes/edges
    - Persists across sessions

Same-schema rule: this manifold differs from external and virtual
manifolds by role and content, NOT by schema. The graph-native
collections are identical — enforced by inheriting BaseManifold.

Future extraction targets (from legacy):
    - Session context patterns from Mind 2 session seam
    - Chat history structures from Backend orchestrator
"""

from __future__ import annotations

from src.core.manifolds.base_manifold import BaseManifold
from src.core.types.ids import ManifoldId
from src.core.types.enums import ManifoldRole, StorageMode


class IdentityManifold(BaseManifold):
    """
    Identity manifold — owns session memory and user/agent context.

    Population is identity-side only. External corpus content does
    not belong here. Uses the same structural contract as all manifolds.
    """

    def __init__(
        self,
        manifold_id: ManifoldId,
        storage_mode: StorageMode = StorageMode.SQLITE_DISK,
    ) -> None:
        super().__init__(
            manifold_id=manifold_id,
            role=ManifoldRole.IDENTITY,
            storage_mode=storage_mode,
        )

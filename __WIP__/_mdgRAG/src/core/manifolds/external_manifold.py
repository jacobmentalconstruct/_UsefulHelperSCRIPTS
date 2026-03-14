"""
External Manifold — persistent corpus, source evidence, and domain knowledge.

Ownership: src/core/manifolds/external_manifold.py
    - External corpus graph
    - Source evidence graph (documents, files, ingested content)
    - Domain knowledge content
    - Persists independently of sessions

Same-schema rule: this manifold uses the same contract as identity
and virtual manifolds. The graph-native collections are identical —
enforced by inheriting BaseManifold.

Future extraction targets (from legacy):
    - CIS chunk storage patterns from ContentStoreMS
    - KG structure from NetworkX knowledge graph
    - FAISS vector binding from FaissIndexMS
    - Cartridge loading from CartridgeServiceMS
"""

from __future__ import annotations

from src.core.manifolds.base_manifold import BaseManifold
from src.core.types.ids import ManifoldId
from src.core.types.enums import ManifoldRole, StorageMode


class ExternalManifold(BaseManifold):
    """
    External manifold — owns the persistent corpus and domain knowledge.

    Content is ingested from outside sources. Session-specific context
    does not belong here. Uses the same structural contract as all manifolds.
    """

    def __init__(
        self,
        manifold_id: ManifoldId,
        storage_mode: StorageMode = StorageMode.SQLITE_DISK,
    ) -> None:
        super().__init__(
            manifold_id=manifold_id,
            role=ManifoldRole.EXTERNAL,
            storage_mode=storage_mode,
        )

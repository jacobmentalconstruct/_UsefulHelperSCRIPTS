"""
Manifold Contract — canonical graph-native schema for all manifolds.

Ownership: src/core/contracts/manifold_contract.py
    Defines the abstract interface and metadata that ALL manifolds share.
    The same-schema rule is the architectural invariant: identity, external,
    and virtual manifolds expose identical typed collections. They differ
    only in role, content ownership, and lifecycle.

Collections governed by this contract:
    - nodes:              typed vertices (Node)
    - edges:              typed directed relations (Edge)
    - chunks:             content-addressed segments (Chunk)
    - chunk_occurrences:  location records for chunks (ChunkOccurrence)
    - embeddings:         vector representations (Embedding)
    - hierarchy:          structural containment (HierarchyEntry)
    - metadata:           owner-bound key/value metadata (MetadataEntry)
    - provenance:         lineage/origin records (Provenance)
    - node_chunk_bindings:     explicit node ↔ chunk links
    - node_embedding_bindings: explicit node ↔ embedding links
    - node_hierarchy_bindings: explicit node ↔ hierarchy links
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.types.ids import (
    ChunkHash,
    EdgeId,
    EmbeddingId,
    HierarchyId,
    ManifoldId,
    NodeId,
)
from src.core.types.enums import ManifoldRole, StorageMode
from src.core.types.graph import (
    Chunk,
    ChunkOccurrence,
    Edge,
    Embedding,
    HierarchyEntry,
    MetadataEntry,
    Node,
)
from src.core.types.provenance import Provenance
from src.core.types.bindings import (
    NodeChunkBinding,
    NodeEmbeddingBinding,
    NodeHierarchyBinding,
)
from src.core.types.manifests import FileManifest, ProjectManifest


@dataclass
class ManifoldMetadata:
    """
    Metadata envelope for a manifold instance.

    Every manifold carries this envelope identifying its role, storage
    mode, schema version, and creation context.
    """

    manifold_id: ManifoldId
    role: ManifoldRole
    storage_mode: StorageMode
    schema_version: str = "0.1.0"
    created_at: Optional[str] = None
    description: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


class ManifoldContract(ABC):
    """
    Abstract contract for all manifold types.

    Every manifold implementation must expose the same graph-native
    typed collections. No manifold gets extra fields or a special schema.
    The contract enforces structural symmetry across all three roles.
    """

    # --- identity ---

    @abstractmethod
    def get_metadata(self) -> ManifoldMetadata:
        """Return the manifold's metadata envelope."""
        ...

    # --- graph collections ---

    @abstractmethod
    def get_nodes(self) -> Dict[NodeId, Node]:
        """Return all nodes in this manifold."""
        ...

    @abstractmethod
    def get_edges(self) -> Dict[EdgeId, Edge]:
        """Return all edges in this manifold."""
        ...

    @abstractmethod
    def get_chunks(self) -> Dict[ChunkHash, Chunk]:
        """Return all chunks in this manifold."""
        ...

    @abstractmethod
    def get_chunk_occurrences(self) -> List[ChunkOccurrence]:
        """Return all chunk occurrence records."""
        ...

    @abstractmethod
    def get_embeddings(self) -> Dict[EmbeddingId, Embedding]:
        """Return all embeddings in this manifold."""
        ...

    @abstractmethod
    def get_hierarchy(self) -> Dict[HierarchyId, HierarchyEntry]:
        """Return all hierarchy entries in this manifold."""
        ...

    # --- metadata & provenance ---

    @abstractmethod
    def get_metadata_entries(self) -> List[MetadataEntry]:
        """Return all owner-bound metadata entries."""
        ...

    @abstractmethod
    def get_provenance_entries(self) -> List[Provenance]:
        """Return all provenance records."""
        ...

    # --- cross-layer bindings ---

    @abstractmethod
    def get_node_chunk_bindings(self) -> List[NodeChunkBinding]:
        """Return all node ↔ chunk bindings."""
        ...

    @abstractmethod
    def get_node_embedding_bindings(self) -> List[NodeEmbeddingBinding]:
        """Return all node ↔ embedding bindings."""
        ...

    @abstractmethod
    def get_node_hierarchy_bindings(self) -> List[NodeHierarchyBinding]:
        """Return all node ↔ hierarchy bindings."""
        ...

    # --- manifests ---

    @abstractmethod
    def get_file_manifest(self) -> Optional[FileManifest]:
        """Return the file manifest, if one exists."""
        ...

    @abstractmethod
    def get_project_manifest(self) -> Optional[ProjectManifest]:
        """Return the project manifest, if one exists."""
        ...

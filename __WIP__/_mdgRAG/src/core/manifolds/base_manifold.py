"""
Base Manifold — shared graph-native structure for all manifold types.

Ownership: src/core/manifolds/base_manifold.py
    This is the neutral, reusable base that enforces the same-schema rule.
    Every manifold — identity, external, or virtual — inherits this
    structure with identical typed collections.

The base manifold does NOT bake in any role-specific assumptions.
It provides:
    - Typed graph collections (nodes, edges, chunks, embeddings, hierarchy)
    - Chunk occurrence records
    - Cross-layer bindings (node↔chunk, node↔embedding, node↔hierarchy)
    - Metadata and provenance registries
    - Optional file/project manifest slots

No storage-specific logic lives here. Storage is the store's job.
"""

from __future__ import annotations

import sqlite3
from typing import Dict, List, Optional

from src.core.contracts.manifold_contract import ManifoldContract, ManifoldMetadata
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


class BaseManifold(ManifoldContract):
    """
    Base manifold implementing the full same-schema contract.

    All collections start empty. Population is the responsibility of
    the specific manifold role and its associated subsystems.

    Every manifold role (identity, external, virtual) inherits from
    this class with identical structure. The same-schema invariant
    is structurally enforced.
    """

    def __init__(
        self,
        manifold_id: ManifoldId,
        role: ManifoldRole,
        storage_mode: StorageMode = StorageMode.PYTHON_RAM,
    ) -> None:
        self._metadata = ManifoldMetadata(
            manifold_id=manifold_id,
            role=role,
            storage_mode=storage_mode,
        )

        # --- storage handle (set by ManifoldFactory, None for RAM) ---
        self._connection: Optional[sqlite3.Connection] = None

        # --- graph collections (typed) ---
        self._nodes: Dict[NodeId, Node] = {}
        self._edges: Dict[EdgeId, Edge] = {}
        self._chunks: Dict[ChunkHash, Chunk] = {}
        self._chunk_occurrences: List[ChunkOccurrence] = []
        self._embeddings: Dict[EmbeddingId, Embedding] = {}
        self._hierarchy: Dict[HierarchyId, HierarchyEntry] = {}

        # --- metadata & provenance ---
        self._metadata_entries: List[MetadataEntry] = []
        self._provenance_entries: List[Provenance] = []

        # --- cross-layer bindings ---
        self._node_chunk_bindings: List[NodeChunkBinding] = []
        self._node_embedding_bindings: List[NodeEmbeddingBinding] = []
        self._node_hierarchy_bindings: List[NodeHierarchyBinding] = []

        # --- manifests ---
        self._file_manifest: Optional[FileManifest] = None
        self._project_manifest: Optional[ProjectManifest] = None

    # --- storage access ---

    @property
    def connection(self) -> Optional[sqlite3.Connection]:
        """The live SQLite connection, or None for RAM-only manifolds."""
        return self._connection

    def close(self) -> None:
        """Close the underlying SQLite connection if present.

        No-op for RAM manifolds (connection is None) or already-closed connections.
        Safe to call multiple times.
        """
        if self._connection is not None:
            try:
                self._connection.close()
            except Exception:
                pass  # Already closed or unusable
            self._connection = None

    def __enter__(self):
        """Enter context manager. Returns self."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Exit context manager. Closes the connection."""
        self.close()

    # --- identity ---

    def get_metadata(self) -> ManifoldMetadata:
        return self._metadata

    # --- graph collections ---

    def get_nodes(self) -> Dict[NodeId, Node]:
        return self._nodes

    def get_edges(self) -> Dict[EdgeId, Edge]:
        return self._edges

    def get_chunks(self) -> Dict[ChunkHash, Chunk]:
        return self._chunks

    def get_chunk_occurrences(self) -> List[ChunkOccurrence]:
        return self._chunk_occurrences

    def get_embeddings(self) -> Dict[EmbeddingId, Embedding]:
        return self._embeddings

    def get_hierarchy(self) -> Dict[HierarchyId, HierarchyEntry]:
        return self._hierarchy

    # --- metadata & provenance ---

    def get_metadata_entries(self) -> List[MetadataEntry]:
        return self._metadata_entries

    def get_provenance_entries(self) -> List[Provenance]:
        return self._provenance_entries

    # --- cross-layer bindings ---

    def get_node_chunk_bindings(self) -> List[NodeChunkBinding]:
        return self._node_chunk_bindings

    def get_node_embedding_bindings(self) -> List[NodeEmbeddingBinding]:
        return self._node_embedding_bindings

    def get_node_hierarchy_bindings(self) -> List[NodeHierarchyBinding]:
        return self._node_hierarchy_bindings

    # --- manifests ---

    def get_file_manifest(self) -> Optional[FileManifest]:
        return self._file_manifest

    def get_project_manifest(self) -> Optional[ProjectManifest]:
        return self._project_manifest

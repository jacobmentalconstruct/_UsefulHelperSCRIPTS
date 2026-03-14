"""
Projection Contract — manifold slice creation for fusion input.

Ownership: src/core/contracts/projection_contract.py
    Defines the typed output shape of projections and the abstract
    interface that projection implementations must satisfy.

A projection creates a working slice of a manifold for use in fusion.
Projections are DISTINCT from fusion: projection selects and shapes,
fusion combines.

Each projection:
    - References its source manifold
    - Contains projected node and edge identities
    - Carries actual typed objects for fusion consumption
    - Carries projection metadata (criteria, timestamp, scope)
    - May include query-derived artifacts (for query projection)
    - Does NOT modify the source manifold

Projection types:
    - Identity projection: session/user/role context
    - External projection: corpus/domain knowledge slices
    - Query projection: structured query working object

Legacy context:
    - Anchor discovery patterns from AnchorDiscoveryMS
    - Ego-graph extraction from SeamBuilderMS
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.types.ids import ChunkHash, EdgeId, ManifoldId, NodeId
from src.core.types.enums import ProjectionSourceKind
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


# ---------------------------------------------------------------------------
# Projection metadata
# ---------------------------------------------------------------------------

@dataclass
class ProjectionMetadata:
    """Metadata describing how and when a projection was created."""

    source_manifold_id: ManifoldId
    source_kind: ProjectionSourceKind
    criteria: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None
    description: str = ""


# ---------------------------------------------------------------------------
# Projected slice (output of projection)
# ---------------------------------------------------------------------------

@dataclass
class ProjectedSlice:
    """
    A projected slice of a manifold — the output of any projection step.

    Contains both ID-level references AND actual typed objects from the
    source manifold. The typed object lists allow fusion to populate
    the VirtualManifold without needing the source manifold's connection.
    """

    metadata: ProjectionMetadata

    # --- ID-level references (preserved from Phase 2) ---
    node_ids: List[NodeId] = field(default_factory=list)
    edge_ids: List[EdgeId] = field(default_factory=list)
    chunk_refs: List[ChunkHash] = field(default_factory=list)
    projected_data: Dict[str, Any] = field(default_factory=dict)

    # --- materialized typed objects for fusion ---
    nodes: List[Node] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    chunks: List[Chunk] = field(default_factory=list)
    chunk_occurrences: List[ChunkOccurrence] = field(default_factory=list)
    embeddings: List[Embedding] = field(default_factory=list)
    hierarchy_entries: List[HierarchyEntry] = field(default_factory=list)
    metadata_entries: List[MetadataEntry] = field(default_factory=list)
    provenance_entries: List[Provenance] = field(default_factory=list)
    node_chunk_bindings: List[NodeChunkBinding] = field(default_factory=list)
    node_embedding_bindings: List[NodeEmbeddingBinding] = field(default_factory=list)
    node_hierarchy_bindings: List[NodeHierarchyBinding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Query projection artifact
# ---------------------------------------------------------------------------

@dataclass
class QueryProjectionArtifact:
    """
    Structured output of a query projection.

    The query is NOT just a flat search string. It becomes a structured
    working object with parsed intent, embedding reference, scope, and
    a first-class graph node representation.
    """

    raw_query: str
    embedding_ref: Optional[str] = None     # Reference to query embedding
    parsed_intent: Dict[str, Any] = field(default_factory=dict)
    scope_constraints: Dict[str, Any] = field(default_factory=dict)
    properties: Dict[str, Any] = field(default_factory=dict)

    # --- query as a graph node (Phase 4) ---
    query_node_id: Optional[NodeId] = None
    query_node: Optional[Node] = None


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class ProjectionContract(ABC):
    """
    Abstract contract for manifold projections.

    Projections create working slices without modifying the source.
    """

    @abstractmethod
    def project(
        self,
        manifold: Any,
        criteria: Dict[str, Any],
    ) -> ProjectedSlice:
        """
        Project a slice of the given manifold based on criteria.

        Args:
            manifold: Source manifold conforming to ManifoldContract.
            criteria: Selection criteria for the projection.

        Returns:
            ProjectedSlice containing the selected nodes, edges, and
            materialized typed objects.
        """
        ...

    def project_by_ids(
        self,
        manifold: Any,
        node_ids: List[NodeId],
    ) -> ProjectedSlice:
        """
        Convenience: project by explicit node IDs.

        Default delegates to project() with node_ids in criteria.
        Subclasses may override for optimized paths.
        """
        return self.project(manifold, {"node_ids": node_ids})

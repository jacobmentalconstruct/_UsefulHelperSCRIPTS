"""
Graph Entity Types — canonical typed structures for manifold graph elements.

Ownership: src/core/types/graph.py
    Defines the concrete data shapes for every element that lives inside
    a manifold's graph. These are pure data containers — no behaviour,
    no storage logic, no retrieval.

All manifolds (identity, external, virtual) store these same types.
The same-schema rule is enforced by using identical structures everywhere.

Legacy context:
    - Node fields informed by legacy KG nodes (NetworkX)
    - Chunk fields informed by legacy CIS schema (SQLite chunks table)
    - Embedding fields informed by legacy FAISS IndexFlatIP + id_map
    - Hierarchy fields informed by legacy lineage DAG
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.core.types.ids import (
    ChunkHash,
    EdgeId,
    EmbeddingId,
    HierarchyId,
    ManifoldId,
    NodeId,
)
from src.core.types.enums import (
    EdgeType,
    EmbeddingMetricType,
    EmbeddingTargetKind,
    NodeType,
)


def _utcnow() -> str:
    """ISO-8601 UTC timestamp for default factory use."""
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Node
# ---------------------------------------------------------------------------

@dataclass
class Node:
    """
    A vertex in a manifold's knowledge graph.

    Nodes are typed and carry a canonical key for deduplication, a
    human-readable label, and an extensible properties dict.
    """

    node_id: NodeId
    manifold_id: ManifoldId
    node_type: NodeType
    canonical_key: str = ""
    label: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)
    source_refs: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Edge
# ---------------------------------------------------------------------------

@dataclass
class Edge:
    """
    A typed, directed relation between two nodes in a manifold's graph.

    Edges carry a type, optional weight, and extensible properties.
    Both endpoints must reside in the same manifold.
    """

    edge_id: EdgeId
    manifold_id: ManifoldId
    from_node_id: NodeId
    to_node_id: NodeId
    edge_type: EdgeType
    weight: float = 1.0
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)
    updated_at: str = field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Chunk
# ---------------------------------------------------------------------------

@dataclass
class Chunk:
    """
    An immutable content segment identified by a deterministic hash.

    A Chunk is content-addressed: two chunks with the same text produce
    the same ChunkHash. Location information lives in ChunkOccurrence.

    Legacy context:
        Legacy CIS schema: chunks table with SHA256 IDs, source paths,
        text, token counts, type, line numbers.
    """

    chunk_hash: ChunkHash
    chunk_text: str
    byte_length: int = 0
    char_length: int = 0
    token_estimate: int = 0
    hash_algorithm: str = "sha256"
    created_at: str = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        if not self.byte_length:
            self.byte_length = len(self.chunk_text.encode("utf-8"))
        if not self.char_length:
            self.char_length = len(self.chunk_text)
        if not self.token_estimate:
            # Simple heuristic matching legacy: len(text.split()) * 1.3 + 1
            self.token_estimate = int(len(self.chunk_text.split()) * 1.3 + 1)


# ---------------------------------------------------------------------------
# ChunkOccurrence
# ---------------------------------------------------------------------------

@dataclass
class ChunkOccurrence:
    """
    Records where a chunk appears within a source context.

    Separated from Chunk identity so the same chunk text can appear
    in multiple files or at multiple positions without duplication.
    """

    chunk_hash: ChunkHash
    manifold_id: ManifoldId
    source_path: str = ""
    chunk_index: int = 0
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    start_offset: Optional[int] = None
    end_offset: Optional[int] = None
    context_label: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

@dataclass
class Embedding:
    """
    A vector representation bound to a graph element.

    The actual vector data is held as a reference or placeholder —
    Phase 2 does not integrate FAISS or numpy.

    Legacy context:
        Legacy used FAISS IndexFlatIP with L2-normalised 1024-d vectors
        from mxbai-embed-large via Ollama.
    """

    embedding_id: EmbeddingId
    target_kind: EmbeddingTargetKind
    target_id: str                      # NodeId or ChunkHash as string
    model_name: str = ""
    model_version: str = ""
    dimensions: int = 0
    metric_type: EmbeddingMetricType = EmbeddingMetricType.COSINE
    is_normalized: bool = True
    vector_ref: Optional[str] = None    # Opaque ref/path to vector data
    vector_blob: Optional[bytes] = None # Inline packed vector (optional)
    created_at: str = field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Hierarchy
# ---------------------------------------------------------------------------

@dataclass
class HierarchyEntry:
    """
    A structural containment entry supporting parent/child topology.

    Hierarchy captures how elements are nested: project → directory →
    file → section → chunk. Each entry knows its parent, depth, and
    position among siblings.
    """

    hierarchy_id: HierarchyId
    manifold_id: ManifoldId
    node_id: NodeId
    parent_id: Optional[HierarchyId] = None
    depth: int = 0
    sort_order: int = 0
    path_label: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

@dataclass
class MetadataEntry:
    """
    Generic owner-bound metadata attached to any graph element.

    Allows arbitrary key/value metadata to be associated with a
    specific owner (node, edge, chunk, etc.) without polluting the
    owner's own fields.
    """

    owner_kind: str         # "node", "edge", "chunk", "manifold", etc.
    owner_id: str           # The ID of the owning element
    manifold_id: ManifoldId
    key: str = ""
    value: Any = None
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=_utcnow)

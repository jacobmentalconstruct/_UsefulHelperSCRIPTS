"""
Cross-Layer Bindings — explicit typed links between graph elements.

Ownership: src/core/types/bindings.py
    Defines the typed structures that connect nodes to chunks, nodes to
    embeddings, and nodes to hierarchy entries. These are explicit link
    objects — not collapsed into generic dict blobs.

Why explicit bindings?
    A node can reference multiple chunks (a source file has many chunks).
    A chunk can be embedded by multiple models. A node can appear at
    multiple levels of the hierarchy. Explicit binding types make these
    relationships first-class, queryable, and provenance-trackable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.core.types.ids import (
    ChunkHash,
    EmbeddingId,
    HierarchyId,
    ManifoldId,
    NodeId,
)


@dataclass
class NodeChunkBinding:
    """
    Links a node to a chunk it contains or references.

    A content node (e.g. SOURCE or SECTION) may bind to many chunks.
    A CHUNK-typed node typically binds to exactly one chunk.
    """

    node_id: NodeId
    chunk_hash: ChunkHash
    manifold_id: ManifoldId
    binding_role: str = "contains"      # "contains", "references", "summarises"
    ordinal: int = 0                    # Position within the node's chunk list
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeEmbeddingBinding:
    """
    Links a node to an embedding vector representing it.

    A node may have multiple embeddings (different models, different
    granularities). Each binding records which embedding belongs to
    which node and in what capacity.
    """

    node_id: NodeId
    embedding_id: EmbeddingId
    manifold_id: ManifoldId
    binding_role: str = "primary"       # "primary", "auxiliary", "contextual"
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class NodeHierarchyBinding:
    """
    Links a node to its position in the structural hierarchy.

    A node may appear at multiple hierarchy levels (e.g. a function
    node is both inside a file and inside a class).
    """

    node_id: NodeId
    hierarchy_id: HierarchyId
    manifold_id: ManifoldId
    binding_role: str = "member"        # "member", "root", "leaf"
    properties: Dict[str, Any] = field(default_factory=dict)

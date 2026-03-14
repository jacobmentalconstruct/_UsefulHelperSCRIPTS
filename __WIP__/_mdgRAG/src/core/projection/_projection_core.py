"""
Projection Core — shared gathering logic for identity and external projectors.

Ownership: src/core/projection/_projection_core.py
    Internal helper module. Both identity and external projectors need to:
        1. Resolve nodes by ID
        2. Find connected edges (closed subgraph)
        3. Gather linked chunks, embeddings, hierarchy entries
        4. Gather metadata and provenance
        5. Gather cross-layer bindings
        6. Stamp PROJECTION provenance on every gathered object

    This module provides the shared implementation to avoid duplication.
    Handles two code paths: SQLite-backed (via ManifoldStore) and RAM
    (via in-memory collections).
"""

from __future__ import annotations

import sqlite3
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.core.contracts.manifold_contract import ManifoldContract
from src.core.contracts.projection_contract import (
    ProjectedSlice,
    ProjectionMetadata,
)
from src.core.store.manifold_store import ManifoldStore
from src.core.types.ids import (
    ChunkHash,
    EmbeddingId,
    HierarchyId,
    ManifoldId,
    NodeId,
)
from src.core.types.enums import (
    ProjectionSourceKind,
    ProvenanceRelationOrigin,
    ProvenanceStage,
)
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
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_projection_provenance(
    owner_kind: str,
    owner_id: str,
    source_manifold_id: ManifoldId,
) -> Provenance:
    """Create a PROJECTION-stage provenance record for a projected object."""
    return Provenance(
        owner_kind=owner_kind,
        owner_id=owner_id,
        source_manifold_id=source_manifold_id,
        stage=ProvenanceStage.PROJECTION,
        relation_origin=ProvenanceRelationOrigin.COMPUTED,
        timestamp=_utcnow_iso(),
    )


def _build_binding_index(
    bindings: list,
    key_attr: str = "node_id",
) -> Dict[str, list]:
    """Pre-index a binding list by node_id for O(1) lookup per node.

    Converts the O(nodes × bindings) RAM scan into O(bindings) build +
    O(1) per-node lookup.  Addresses O-011.
    """
    index: Dict[str, list] = defaultdict(list)
    for b in bindings:
        index[getattr(b, key_attr)].append(b)
    return index


def gather_slice_by_node_ids(
    manifold: ManifoldContract,
    node_ids: List[NodeId],
    source_kind: ProjectionSourceKind,
    store: Optional[ManifoldStore] = None,
    conn: Optional[sqlite3.Connection] = None,
    criteria: Optional[Dict[str, Any]] = None,
    description: str = "",
) -> ProjectedSlice:
    """
    Core projection logic: given node IDs, gather all connected
    typed objects into a ProjectedSlice.

    For SQLite-backed manifolds: uses store + conn.
    For RAM manifolds (conn is None): reads from in-memory collections.

    Steps:
        1. Resolve requested nodes.
        2. Find edges where both endpoints are in the node set.
        3. For each node, gather linked chunks, embeddings, hierarchy.
        4. Gather metadata and provenance for all gathered objects.
        5. Create PROJECTION provenance for every gathered entity.
    """
    t_start = time.perf_counter()

    meta = manifold.get_metadata()
    manifold_id = meta.manifold_id

    # Validation: warn on empty node_ids (likely caller bug)
    if not node_ids:
        logger.warning(
            "Projection: gather_slice_by_node_ids called with empty node_ids "
            "(manifold=%s, source_kind=%s) — returning empty slice",
            manifold_id, source_kind.name,
        )

    projection_meta = ProjectionMetadata(
        source_manifold_id=manifold_id,
        source_kind=source_kind,
        criteria=criteria or {},
        timestamp=_utcnow_iso(),
        description=description,
    )

    # Result accumulators
    gathered_nodes: List[Node] = []
    gathered_edges: List[Edge] = []
    gathered_chunks: List[Chunk] = []
    gathered_chunk_occurrences: List[ChunkOccurrence] = []
    gathered_embeddings: List[Embedding] = []
    gathered_hierarchy: List[HierarchyEntry] = []
    gathered_metadata: List[MetadataEntry] = []
    gathered_provenance: List[Provenance] = []
    gathered_nc_bindings: List[NodeChunkBinding] = []
    gathered_ne_bindings: List[NodeEmbeddingBinding] = []
    gathered_nh_bindings: List[NodeHierarchyBinding] = []

    use_store = conn is not None and store is not None

    # --- Step 1: Resolve nodes ---
    if use_store:
        for nid in node_ids:
            node = store.get_node(conn, nid)
            if node is not None:
                gathered_nodes.append(node)
    else:
        all_nodes = manifold.get_nodes()
        for nid in node_ids:
            if nid in all_nodes:
                gathered_nodes.append(all_nodes[nid])

    # Only include actually-found nodes
    found_ids: Set[NodeId] = {n.node_id for n in gathered_nodes}

    requested_count = len(node_ids)
    found_count = len(found_ids)
    if found_count < requested_count:
        logger.warning(
            "Projection: %d/%d requested nodes resolved (manifold=%s)",
            found_count, requested_count, manifold_id,
        )

    # --- Step 2: Find internal edges (closed subgraph) ---
    if use_store:
        all_edges = store.list_edges(conn, ManifoldId(manifold_id))
    else:
        all_edges = list(manifold.get_edges().values())

    for edge in all_edges:
        if edge.from_node_id in found_ids and edge.to_node_id in found_ids:
            gathered_edges.append(edge)

    # --- Step 3: Gather linked records per node ---
    seen_chunks: Set[ChunkHash] = set()
    seen_embeddings: Set[EmbeddingId] = set()
    seen_hierarchy: Set[HierarchyId] = set()

    # Pre-index bindings for O(1) per-node lookup on the RAM path (O-011)
    nc_index: Optional[Dict[str, list]] = None
    ne_index: Optional[Dict[str, list]] = None
    nh_index: Optional[Dict[str, list]] = None
    if not use_store:
        nc_index = _build_binding_index(manifold.get_node_chunk_bindings())
        ne_index = _build_binding_index(manifold.get_node_embedding_bindings())
        nh_index = _build_binding_index(manifold.get_node_hierarchy_bindings())

    for nid in sorted(found_ids):  # sorted for determinism
        # Chunk bindings
        if use_store:
            nc_links = store.get_node_chunk_links(conn, nid)
        else:
            nc_links = nc_index.get(nid, [])  # type: ignore[union-attr]
        gathered_nc_bindings.extend(nc_links)

        for binding in nc_links:
            if binding.chunk_hash not in seen_chunks:
                seen_chunks.add(binding.chunk_hash)
                if use_store:
                    chunk = store.get_chunk(conn, binding.chunk_hash)
                    if chunk:
                        gathered_chunks.append(chunk)
                else:
                    chunks_dict = manifold.get_chunks()
                    if binding.chunk_hash in chunks_dict:
                        gathered_chunks.append(chunks_dict[binding.chunk_hash])

        # Embedding bindings
        if use_store:
            ne_links = store.get_node_embedding_links(conn, nid)
        else:
            ne_links = ne_index.get(nid, [])  # type: ignore[union-attr]
        gathered_ne_bindings.extend(ne_links)

        for binding in ne_links:
            if binding.embedding_id not in seen_embeddings:
                seen_embeddings.add(binding.embedding_id)
                if use_store:
                    emb = store.get_embedding(conn, binding.embedding_id)
                    if emb:
                        gathered_embeddings.append(emb)
                else:
                    embs_dict = manifold.get_embeddings()
                    if binding.embedding_id in embs_dict:
                        gathered_embeddings.append(embs_dict[binding.embedding_id])

        # Hierarchy bindings
        if use_store:
            nh_links = store.get_node_hierarchy_links(conn, nid)
        else:
            nh_links = nh_index.get(nid, [])  # type: ignore[union-attr]
        gathered_nh_bindings.extend(nh_links)

        for binding in nh_links:
            if binding.hierarchy_id not in seen_hierarchy:
                seen_hierarchy.add(binding.hierarchy_id)
                if use_store:
                    h = store.get_hierarchy(conn, binding.hierarchy_id)
                    if h:
                        gathered_hierarchy.append(h)
                else:
                    hier_dict = manifold.get_hierarchy()
                    if binding.hierarchy_id in hier_dict:
                        gathered_hierarchy.append(hier_dict[binding.hierarchy_id])

        # Metadata for this node
        if use_store:
            node_meta = store.get_metadata_for_owner(
                conn, "node", nid, ManifoldId(manifold_id),
            )
        else:
            node_meta = [
                m for m in manifold.get_metadata_entries()
                if m.owner_kind == "node" and m.owner_id == nid
            ]
        gathered_metadata.extend(node_meta)

        # Existing provenance for this node
        if use_store:
            node_prov = store.get_provenance_for_owner(conn, "node", nid)
        else:
            node_prov = [
                p for p in manifold.get_provenance_entries()
                if p.owner_kind == "node" and p.owner_id == nid
            ]
        gathered_provenance.extend(node_prov)

    # --- Step 4: Create PROJECTION provenance for gathered entities ---
    for node in gathered_nodes:
        gathered_provenance.append(
            _make_projection_provenance("node", node.node_id, ManifoldId(manifold_id))
        )
    for edge in gathered_edges:
        gathered_provenance.append(
            _make_projection_provenance("edge", edge.edge_id, ManifoldId(manifold_id))
        )
    for chunk in gathered_chunks:
        gathered_provenance.append(
            _make_projection_provenance(
                "chunk", chunk.chunk_hash, ManifoldId(manifold_id),
            )
        )

    elapsed = time.perf_counter() - t_start
    logger.info(
        "Projection: gathered %d/%d nodes, %d edges, %d chunks, "
        "%d embeddings, %d hierarchy from %s in %.3fs",
        found_count, requested_count,
        len(gathered_edges), len(gathered_chunks),
        len(gathered_embeddings), len(gathered_hierarchy),
        manifold_id, elapsed,
    )

    # --- Build slice ---
    return ProjectedSlice(
        metadata=projection_meta,
        node_ids=sorted(found_ids),
        edge_ids=[e.edge_id for e in gathered_edges],
        chunk_refs=[c.chunk_hash for c in gathered_chunks],
        nodes=gathered_nodes,
        edges=gathered_edges,
        chunks=gathered_chunks,
        chunk_occurrences=gathered_chunk_occurrences,
        embeddings=gathered_embeddings,
        hierarchy_entries=gathered_hierarchy,
        metadata_entries=gathered_metadata,
        provenance_entries=gathered_provenance,
        node_chunk_bindings=gathered_nc_bindings,
        node_embedding_bindings=gathered_ne_bindings,
        node_hierarchy_bindings=gathered_nh_bindings,
    )

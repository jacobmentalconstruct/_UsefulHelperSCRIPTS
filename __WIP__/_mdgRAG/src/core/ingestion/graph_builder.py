"""
Graph object construction from raw chunks.

Translates RawChunk objects (output of chunking step) into graph-native
Node / Edge / Chunk / HierarchyEntry / Binding / Provenance objects
ready for storage via ManifoldStore.

This module is written fresh for Graph Manifold — no legacy extraction.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..types.bindings import (
    NodeChunkBinding,
    NodeEmbeddingBinding,
    NodeHierarchyBinding,
)
from ..types.enums import (
    EdgeType,
    EmbeddingMetricType,
    EmbeddingTargetKind,
    NodeType,
    ProvenanceRelationOrigin,
    ProvenanceStage,
)
from ..types.graph import Chunk, ChunkOccurrence, Embedding, HierarchyEntry, Node, Edge
from ..types.ids import (
    ChunkHash,
    EdgeId,
    EmbeddingId,
    HierarchyId,
    ManifoldId,
    NodeId,
    deterministic_hash,
    make_chunk_hash,
    HASH_TRUNCATION_LENGTH,
)
from ..types.provenance import Provenance

from .chunking import RawChunk
from .config import IngestionConfig
from .detection import SourceFile

logger = logging.getLogger(__name__)


# ── Output container ──────────────────────────────────────────────────────────

@dataclass
class IngestionArtifacts:
    """
    All graph objects produced by ingesting a single file.

    Consumed by the storage step to persist into a manifold.
    """
    source_node: Node
    chunk_nodes: List[Node] = field(default_factory=list)
    section_nodes: List[Node] = field(default_factory=list)
    chunks: List[Chunk] = field(default_factory=list)
    chunk_occurrences: List[ChunkOccurrence] = field(default_factory=list)
    edges: List[Edge] = field(default_factory=list)
    hierarchy_entries: List[HierarchyEntry] = field(default_factory=list)
    node_chunk_bindings: List[NodeChunkBinding] = field(default_factory=list)
    node_hierarchy_bindings: List[NodeHierarchyBinding] = field(default_factory=list)
    provenance: List[Provenance] = field(default_factory=list)

    @property
    def all_nodes(self) -> List[Node]:
        return [self.source_node] + self.section_nodes + self.chunk_nodes


# ── ID helpers ────────────────────────────────────────────────────────────────

def _make_node_id(prefix: str, key: str) -> NodeId:
    """Create a deterministic NodeId from a prefix and key."""
    return NodeId(f"{prefix}-{deterministic_hash(key)[:HASH_TRUNCATION_LENGTH]}")


def _make_edge_id(from_id: str, to_id: str, edge_type: str) -> EdgeId:
    """Create a deterministic EdgeId."""
    return EdgeId(
        f"edge-{deterministic_hash(f'{from_id}:{to_id}:{edge_type}')[:HASH_TRUNCATION_LENGTH]}"
    )


def _make_hierarchy_id(manifold_id: str, node_id: str, depth: int) -> HierarchyId:
    """Create a deterministic HierarchyId."""
    return HierarchyId(
        f"hier-{deterministic_hash(f'{manifold_id}:{node_id}:{depth}')[:HASH_TRUNCATION_LENGTH]}"
    )


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Provenance factory ────────────────────────────────────────────────────────

def _make_provenance(
    owner_kind: str,
    owner_id: str,
    source_manifold_id: str,
    source_document: str,
    config: IngestionConfig,
    relation_origin: ProvenanceRelationOrigin = ProvenanceRelationOrigin.PARSED,
) -> Provenance:
    """Create a standard INGESTION-stage provenance record."""
    return Provenance(
        owner_kind=owner_kind,
        owner_id=owner_id,
        source_manifold_id=ManifoldId(source_manifold_id),
        source_document=source_document,
        stage=ProvenanceStage.INGESTION,
        relation_origin=relation_origin,
        parser_name=config.parser_name,
        parser_version=config.parser_version,
        timestamp=_utcnow(),
    )


# ── Public API ────────────────────────────────────────────────────────────────

def build_graph_objects(
    raw_chunks: List[RawChunk],
    source: SourceFile,
    manifold_id: str,
    config: Optional[IngestionConfig] = None,
) -> IngestionArtifacts:
    """
    Transform raw chunks into graph-native objects.

    Creates:
        - 1 SOURCE node per file
        - N SECTION nodes from unique heading paths
        - M CHUNK nodes (one per raw chunk)
        - M Chunk objects (content-addressed)
        - M ChunkOccurrences (source location)
        - CONTAINS edges (SOURCE→SECTION→CHUNK)
        - NEXT edges between sequential chunks
        - HierarchyEntry records
        - NodeChunkBindings, NodeHierarchyBindings
        - Provenance records for all objects
    """
    if config is None:
        config = IngestionConfig()

    mid = ManifoldId(manifold_id)
    file_path_str = str(source.path)
    timestamp = _utcnow()

    # ── SOURCE node ───────────────────────────────────────────────────────
    source_node_id = _make_node_id("src", f"{manifold_id}:{file_path_str}")
    source_node = Node(
        node_id=source_node_id,
        manifold_id=mid,
        node_type=NodeType.SOURCE,
        canonical_key=source.file_hash[:HASH_TRUNCATION_LENGTH],
        label=source.path.name,
        properties={
            "file_path": file_path_str,
            "file_hash": source.file_hash,
            "source_type": source.source_type,
            "language": source.language or "",
            "encoding": source.encoding,
            "byte_size": source.byte_size,
            "line_count": len(source.lines),
        },
        source_refs=[file_path_str],
    )

    artifacts = IngestionArtifacts(source_node=source_node)

    # Provenance for SOURCE node
    artifacts.provenance.append(_make_provenance(
        "node", str(source_node_id), manifold_id, file_path_str, config,
    ))

    # ── SECTION nodes from heading paths ──────────────────────────────────
    # Track unique sections to avoid duplicates
    section_map: Dict[str, NodeId] = {}  # heading_path_key → NodeId

    for raw_chunk in raw_chunks:
        if len(raw_chunk.heading_path) > 1:
            # Build section nodes for intermediate path segments
            for depth in range(1, len(raw_chunk.heading_path)):
                section_path = raw_chunk.heading_path[:depth + 1]
                section_key = "::".join(section_path)

                if section_key in section_map:
                    continue

                section_node_id = _make_node_id(
                    "sec", f"{manifold_id}:{file_path_str}:{section_key}"
                )
                section_map[section_key] = section_node_id

                section_label = section_path[-1]
                section_node = Node(
                    node_id=section_node_id,
                    manifold_id=mid,
                    node_type=NodeType.SECTION,
                    canonical_key=deterministic_hash(section_key)[:HASH_TRUNCATION_LENGTH],
                    label=section_label,
                    properties={
                        "heading_path": section_path,
                        "depth": depth,
                    },
                    source_refs=[file_path_str],
                )
                artifacts.section_nodes.append(section_node)
                artifacts.provenance.append(_make_provenance(
                    "node", str(section_node_id), manifold_id, file_path_str, config,
                ))

    # ── CONTAINS edges for section hierarchy ──────────────────────────────
    # SOURCE → top-level sections
    # parent sections → child sections
    for section_key, section_nid in section_map.items():
        parts = section_key.split("::")
        if len(parts) <= 2:
            # Top-level section: SOURCE → SECTION
            parent_id = source_node_id
        else:
            # Nested section: parent section → this section
            parent_key = "::".join(parts[:-1])
            parent_id = section_map.get(parent_key, source_node_id)

        edge_id = _make_edge_id(str(parent_id), str(section_nid), "CONTAINS")
        artifacts.edges.append(Edge(
            edge_id=edge_id,
            manifold_id=mid,
            from_node_id=parent_id,
            to_node_id=section_nid,
            edge_type=EdgeType.CONTAINS,
        ))
        artifacts.provenance.append(_make_provenance(
            "edge", str(edge_id), manifold_id, file_path_str, config,
            relation_origin=ProvenanceRelationOrigin.PARSED,
        ))

    # ── CHUNK nodes and objects ───────────────────────────────────────────
    prev_chunk_node_id: Optional[NodeId] = None

    for i, raw_chunk in enumerate(raw_chunks):
        chunk_text = raw_chunk.text
        chunk_hash = make_chunk_hash(chunk_text)

        # CHUNK node
        chunk_node_id = _make_node_id(
            "chk", f"{manifold_id}:{file_path_str}:{i}:{str(chunk_hash)[:8]}"
        )
        chunk_node = Node(
            node_id=chunk_node_id,
            manifold_id=mid,
            node_type=NodeType.CHUNK,
            canonical_key=str(chunk_hash)[:HASH_TRUNCATION_LENGTH],
            label=raw_chunk.name,
            properties={
                "chunk_type": raw_chunk.chunk_type,
                "chunk_index": i,
                "language_tier": raw_chunk.language_tier,
                "semantic_depth": raw_chunk.semantic_depth,
                "structural_depth": raw_chunk.structural_depth,
                "heading_path": raw_chunk.heading_path,
                "line_start": raw_chunk.line_start,
                "line_end": raw_chunk.line_end,
            },
            source_refs=[file_path_str],
        )
        artifacts.chunk_nodes.append(chunk_node)

        # Chunk object (content-addressed, deduplicates naturally)
        chunk_obj = Chunk(chunk_hash=chunk_hash, chunk_text=chunk_text)
        artifacts.chunks.append(chunk_obj)

        # ChunkOccurrence (location data)
        occ = ChunkOccurrence(
            chunk_hash=chunk_hash,
            manifold_id=mid,
            source_path=file_path_str,
            chunk_index=i,
            start_line=raw_chunk.line_start,
            end_line=raw_chunk.line_end,
            context_label=" > ".join(raw_chunk.heading_path),
        )
        artifacts.chunk_occurrences.append(occ)

        # NodeChunkBinding
        artifacts.node_chunk_bindings.append(NodeChunkBinding(
            node_id=chunk_node_id,
            chunk_hash=chunk_hash,
            manifold_id=mid,
            binding_role="contains",
            ordinal=i,
        ))

        # CONTAINS edge: nearest section (or source) → chunk
        if raw_chunk.heading_path and len(raw_chunk.heading_path) > 1:
            # Find the deepest matching section
            for depth in range(len(raw_chunk.heading_path), 0, -1):
                section_key = "::".join(raw_chunk.heading_path[:depth])
                parent_nid = section_map.get(section_key)
                if parent_nid is not None:
                    break
            else:
                parent_nid = source_node_id
        else:
            parent_nid = source_node_id

        contains_edge_id = _make_edge_id(str(parent_nid), str(chunk_node_id), "CONTAINS")
        artifacts.edges.append(Edge(
            edge_id=contains_edge_id,
            manifold_id=mid,
            from_node_id=parent_nid,
            to_node_id=chunk_node_id,
            edge_type=EdgeType.CONTAINS,
        ))

        # NEXT edge: previous chunk → this chunk
        if prev_chunk_node_id is not None:
            next_edge_id = _make_edge_id(
                str(prev_chunk_node_id), str(chunk_node_id), "NEXT"
            )
            artifacts.edges.append(Edge(
                edge_id=next_edge_id,
                manifold_id=mid,
                from_node_id=prev_chunk_node_id,
                to_node_id=chunk_node_id,
                edge_type=EdgeType.NEXT,
            ))

        prev_chunk_node_id = chunk_node_id

        # HierarchyEntry
        hier_id = _make_hierarchy_id(manifold_id, str(chunk_node_id), raw_chunk.semantic_depth)
        path_label = " > ".join(raw_chunk.heading_path)

        # Find parent hierarchy ID
        parent_hier_id: Optional[HierarchyId] = None
        if raw_chunk.heading_path and len(raw_chunk.heading_path) > 1:
            parent_section_key = "::".join(raw_chunk.heading_path[:-1])
            parent_section_nid = section_map.get(parent_section_key)
            if parent_section_nid:
                parent_hier_id = _make_hierarchy_id(
                    manifold_id, str(parent_section_nid),
                    max(0, raw_chunk.semantic_depth - 1),
                )

        hierarchy_entry = HierarchyEntry(
            hierarchy_id=hier_id,
            manifold_id=mid,
            node_id=chunk_node_id,
            parent_id=parent_hier_id,
            depth=raw_chunk.semantic_depth,
            sort_order=i,
            path_label=path_label,
        )
        artifacts.hierarchy_entries.append(hierarchy_entry)

        # NodeHierarchyBinding
        artifacts.node_hierarchy_bindings.append(NodeHierarchyBinding(
            node_id=chunk_node_id,
            hierarchy_id=hier_id,
            manifold_id=mid,
            binding_role="member",
        ))

        # Provenance for chunk node, chunk object, edge
        artifacts.provenance.append(_make_provenance(
            "node", str(chunk_node_id), manifold_id, file_path_str, config,
        ))
        artifacts.provenance.append(_make_provenance(
            "chunk", str(chunk_hash), manifold_id, file_path_str, config,
        ))
        artifacts.provenance.append(_make_provenance(
            "edge", str(contains_edge_id), manifold_id, file_path_str, config,
        ))

    node_count = len(artifacts.all_nodes)
    edge_count = len(artifacts.edges)
    chunk_count = len(artifacts.chunks)
    logger.info(
        "build_graph_objects: %s → %d nodes, %d edges, %d chunks",
        source.path.name, node_count, edge_count, chunk_count,
    )

    return artifacts

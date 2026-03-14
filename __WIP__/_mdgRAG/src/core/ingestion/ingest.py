"""
Ingestion pipeline — public entry points.

Orchestrates: detection → chunking → graph construction → storage → embedding.

Public API:
    ingest_file()       — Ingest a single file into an External manifold.
    ingest_directory()  — Walk a directory tree, ingest all supported files.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from ..store.manifold_store import ManifoldStore
from ..types.bindings import NodeEmbeddingBinding
from ..types.enums import (
    EdgeType,
    EmbeddingMetricType,
    EmbeddingTargetKind,
    NodeType,
    ProvenanceRelationOrigin,
    ProvenanceStage,
)
from ..types.graph import Edge, Embedding, Node
from ..types.ids import (
    EdgeId,
    EmbeddingId,
    ManifoldId,
    NodeId,
    deterministic_hash,
    HASH_TRUNCATION_LENGTH,
)
from ..types.provenance import Provenance

from .chunking import RawChunk, chunk_prose
from .config import IngestionConfig
from .detection import SourceFile, detect_file, walk_sources
from .graph_builder import IngestionArtifacts, build_graph_objects, _make_provenance

logger = logging.getLogger(__name__)


# ── Embed function type alias ─────────────────────────────────────────────────

EmbedFn = Callable[[str], Sequence[float]]


# ── Result dataclass ──────────────────────────────────────────────────────────

@dataclass
class IngestionResult:
    """Summary of an ingestion run."""
    files_processed: int = 0
    files_skipped: int = 0
    chunks_created: int = 0
    nodes_created: int = 0
    edges_created: int = 0
    embeddings_created: int = 0
    warnings: List[str] = field(default_factory=list)
    timing_seconds: float = 0.0

    def merge(self, other: IngestionResult) -> None:
        """Merge another result into this one."""
        self.files_processed += other.files_processed
        self.files_skipped += other.files_skipped
        self.chunks_created += other.chunks_created
        self.nodes_created += other.nodes_created
        self.edges_created += other.edges_created
        self.embeddings_created += other.embeddings_created
        self.warnings.extend(other.warnings)


# ── Chunker routing ───────────────────────────────────────────────────────────

def _route_chunker(
    source: SourceFile,
    config: IngestionConfig,
) -> List[RawChunk]:
    """
    Route source file to the appropriate chunker.

    Priority:
      1. Tree-sitter for code, structured, and markup files
      2. Prose chunker for text/markdown and fallback
    """
    # Try tree-sitter first for non-prose files
    if source.source_type in ("code", "structured", "markup"):
        from .tree_sitter_chunker import chunk_tree_sitter
        ts_chunks = chunk_tree_sitter(source, config)
        if ts_chunks is not None:
            return ts_chunks
        # Tree-sitter unavailable or failed — fall through to prose

    # Prose chunker for text/markdown or as fallback
    return chunk_prose(source, config)


# ── Storage ───────────────────────────────────────────────────────────────────

def _persist_artifacts(
    artifacts: IngestionArtifacts,
    conn,
    store: ManifoldStore,
) -> None:
    """Write all graph objects to the manifold store."""
    # Nodes
    for node in artifacts.all_nodes:
        store.add_node(conn, node)

    # Chunks (content-addressed, INSERT OR IGNORE handles dedup)
    for chunk in artifacts.chunks:
        store.add_chunk(conn, chunk)

    # Chunk occurrences
    for occ in artifacts.chunk_occurrences:
        store.add_chunk_occurrence(conn, occ)

    # Edges
    for edge in artifacts.edges:
        store.add_edge(conn, edge)

    # Hierarchy entries
    for entry in artifacts.hierarchy_entries:
        store.add_hierarchy(conn, entry)

    # Bindings
    for binding in artifacts.node_chunk_bindings:
        store.link_node_chunk(conn, binding)

    for binding in artifacts.node_hierarchy_bindings:
        store.link_node_hierarchy(conn, binding)

    # Provenance
    for prov in artifacts.provenance:
        store.add_provenance(conn, prov)


# ── Embedding ─────────────────────────────────────────────────────────────────

def _embed_chunks(
    artifacts: IngestionArtifacts,
    embed_fn: EmbedFn,
    conn,
    store: ManifoldStore,
    manifold_id: str,
    config: IngestionConfig,
) -> int:
    """
    Generate embeddings for chunk nodes and store them.

    Prepends context_prefix (heading_path breadcrumb) to chunk text before
    embedding, so semantic context is never lost.

    Returns count of embeddings created.
    """
    count = 0

    for i, (chunk_node, chunk_obj) in enumerate(
        zip(artifacts.chunk_nodes, artifacts.chunks)
    ):
        # Build context prefix from heading_path
        heading_path = chunk_node.properties.get("heading_path", [])
        if heading_path:
            context_prefix = " > ".join(heading_path) + "\n\n"
        else:
            context_prefix = ""

        text_to_embed = context_prefix + chunk_obj.chunk_text

        try:
            vector = embed_fn(text_to_embed)
        except Exception as e:
            logger.warning("Embed failed for chunk %s: %s", chunk_node.label, e)
            continue

        if not vector:
            continue

        vector_list = list(vector)
        dimensions = len(vector_list)

        # Create Embedding object
        emb_id = EmbeddingId(
            f"emb-{deterministic_hash(f'{manifold_id}:{chunk_obj.chunk_hash}:{i}')[:HASH_TRUNCATION_LENGTH]}"
        )
        embedding = Embedding(
            embedding_id=emb_id,
            target_kind=EmbeddingTargetKind.CHUNK,
            target_id=str(chunk_obj.chunk_hash),
            model_name=config.parser_name,
            dimensions=dimensions,
            metric_type=EmbeddingMetricType.COSINE,
            is_normalized=True,
        )
        store.add_embedding(conn, embedding)

        # NodeEmbeddingBinding
        binding = NodeEmbeddingBinding(
            node_id=chunk_node.node_id,
            embedding_id=emb_id,
            manifold_id=ManifoldId(manifold_id),
            binding_role="primary",
        )
        store.link_node_embedding(conn, binding)

        # Provenance for embedding
        prov = Provenance(
            owner_kind="embedding",
            owner_id=str(emb_id),
            source_manifold_id=ManifoldId(manifold_id),
            source_document=str(chunk_node.properties.get("heading_path", [""])[0]),
            stage=ProvenanceStage.EMBEDDING,
            relation_origin=ProvenanceRelationOrigin.COMPUTED,
            parser_name=config.parser_name,
            parser_version=config.parser_version,
        )
        store.add_provenance(conn, prov)

        count += 1

    return count


# ── Public API ────────────────────────────────────────────────────────────────

def ingest_file(
    file_path,
    manifold,
    store: ManifoldStore,
    config: Optional[IngestionConfig] = None,
    embed_fn: Optional[EmbedFn] = None,
) -> IngestionResult:
    """
    Ingest a single file into a manifold.

    Orchestrates: detect → chunk → build graph → store → embed.

    Args:
        file_path: Path to the file to ingest.
        manifold: Target manifold (BaseManifold with connection).
        store: ManifoldStore for persistence.
        config: Optional ingestion configuration.
        embed_fn: Optional embedding function. When provided, generates
                  embeddings for each chunk during ingestion.

    Returns:
        IngestionResult with counts and timing.
    """
    if config is None:
        config = IngestionConfig()

    result = IngestionResult()
    t0 = time.perf_counter()

    path = Path(file_path)
    manifold_id = str(manifold.get_metadata().manifold_id)
    conn = manifold.connection

    # 1. Detection
    source = detect_file(path)
    if source is None:
        result.files_skipped += 1
        result.warnings.append(f"Skipped (binary/empty/unreadable): {path}")
        result.timing_seconds = time.perf_counter() - t0
        return result

    logger.info("Ingesting: %s (%s, %s)", path.name, source.source_type, source.language or "unknown")

    # 2. Chunking
    raw_chunks = _route_chunker(source, config)
    if not raw_chunks:
        result.files_skipped += 1
        result.warnings.append(f"No chunks produced: {path}")
        result.timing_seconds = time.perf_counter() - t0
        return result

    # 3. Graph construction
    artifacts = build_graph_objects(raw_chunks, source, manifold_id, config)

    # 4. Storage
    _persist_artifacts(artifacts, conn, store)

    # 5. Embedding (optional)
    embed_count = 0
    if embed_fn is not None and config.enable_embeddings:
        embed_count = _embed_chunks(
            artifacts, embed_fn, conn, store, manifold_id, config,
        )

    # 6. Result
    result.files_processed = 1
    result.chunks_created = len(artifacts.chunks)
    result.nodes_created = len(artifacts.all_nodes)
    result.edges_created = len(artifacts.edges)
    result.embeddings_created = embed_count
    result.timing_seconds = time.perf_counter() - t0

    logger.info(
        "Ingested %s: %d nodes, %d edges, %d chunks, %d embeddings (%.2fs)",
        path.name, result.nodes_created, result.edges_created,
        result.chunks_created, result.embeddings_created, result.timing_seconds,
    )

    return result


def ingest_directory(
    directory_path,
    manifold,
    store: ManifoldStore,
    config: Optional[IngestionConfig] = None,
    embed_fn: Optional[EmbedFn] = None,
) -> IngestionResult:
    """
    Walk a directory tree and ingest all supported files.

    Creates DIRECTORY and PROJECT nodes with CONTAINS edges representing
    the directory tree structure.

    Args:
        directory_path: Root directory to walk.
        manifold: Target manifold (BaseManifold with connection).
        store: ManifoldStore for persistence.
        config: Optional ingestion configuration.
        embed_fn: Optional embedding function.

    Returns:
        IngestionResult with aggregate counts and timing.
    """
    if config is None:
        config = IngestionConfig()

    result = IngestionResult()
    t0 = time.perf_counter()

    root = Path(directory_path).resolve()
    manifold_id = str(manifold.get_metadata().manifold_id)
    conn = manifold.connection
    mid = ManifoldId(manifold_id)

    if not root.is_dir():
        result.warnings.append(f"Not a directory: {root}")
        result.timing_seconds = time.perf_counter() - t0
        return result

    # ── PROJECT node for the root ─────────────────────────────────────────
    project_node_id = NodeId(
        f"proj-{deterministic_hash(f'{manifold_id}:{root}')[:HASH_TRUNCATION_LENGTH]}"
    )
    project_node = Node(
        node_id=project_node_id,
        manifold_id=mid,
        node_type=NodeType.PROJECT,
        canonical_key=deterministic_hash(str(root))[:HASH_TRUNCATION_LENGTH],
        label=root.name,
        properties={"directory_path": str(root)},
        source_refs=[str(root)],
    )
    store.add_node(conn, project_node)
    store.add_provenance(conn, _make_provenance(
        "node", str(project_node_id), manifold_id, str(root), config,
    ))

    # ── Track directory nodes for CONTAINS edges ──────────────────────────
    dir_node_map: dict = {str(root): project_node_id}

    def _ensure_dir_node(dir_path: Path) -> NodeId:
        """Ensure a DIRECTORY node exists for this path, creating parents as needed."""
        dir_str = str(dir_path)
        if dir_str in dir_node_map:
            return dir_node_map[dir_str]

        # Ensure parent exists first
        parent_nid = _ensure_dir_node(dir_path.parent)

        # Create DIRECTORY node
        dir_nid = NodeId(
            f"dir-{deterministic_hash(f'{manifold_id}:{dir_str}')[:HASH_TRUNCATION_LENGTH]}"
        )
        dir_node = Node(
            node_id=dir_nid,
            manifold_id=mid,
            node_type=NodeType.DIRECTORY,
            canonical_key=deterministic_hash(dir_str)[:HASH_TRUNCATION_LENGTH],
            label=dir_path.name,
            properties={"directory_path": dir_str},
            source_refs=[dir_str],
        )
        store.add_node(conn, dir_node)
        store.add_provenance(conn, _make_provenance(
            "node", str(dir_nid), manifold_id, dir_str, config,
        ))

        # CONTAINS edge: parent → this dir
        edge_id = EdgeId(
            f"edge-{deterministic_hash(f'{parent_nid}:{dir_nid}:CONTAINS')[:HASH_TRUNCATION_LENGTH]}"
        )
        store.add_edge(conn, Edge(
            edge_id=edge_id,
            manifold_id=mid,
            from_node_id=parent_nid,
            to_node_id=dir_nid,
            edge_type=EdgeType.CONTAINS,
        ))

        dir_node_map[dir_str] = dir_nid
        return dir_nid

    # ── Walk and ingest files ─────────────────────────────────────────────
    for source_file in walk_sources(root, config):
        # Ensure directory nodes exist for this file's parent
        file_dir = source_file.path.parent
        dir_nid = _ensure_dir_node(file_dir)

        # Ingest the file
        file_result = ingest_file(
            source_file.path, manifold, store, config, embed_fn,
        )
        result.merge(file_result)

        # CONTAINS edge: directory → source node
        if file_result.files_processed > 0:
            source_node_id = NodeId(
                f"src-{deterministic_hash(f'{manifold_id}:{source_file.path}')[:HASH_TRUNCATION_LENGTH]}"
            )
            edge_id = EdgeId(
                f"edge-{deterministic_hash(f'{dir_nid}:{source_node_id}:CONTAINS')[:HASH_TRUNCATION_LENGTH]}"
            )
            store.add_edge(conn, Edge(
                edge_id=edge_id,
                manifold_id=mid,
                from_node_id=dir_nid,
                to_node_id=source_node_id,
                edge_type=EdgeType.CONTAINS,
            ))

    result.timing_seconds = time.perf_counter() - t0

    logger.info(
        "Directory ingestion complete: %s — %d files processed, %d skipped, "
        "%d nodes, %d edges, %d chunks, %d embeddings (%.2fs)",
        root.name, result.files_processed, result.files_skipped,
        result.nodes_created, result.edges_created,
        result.chunks_created, result.embeddings_created, result.timing_seconds,
    )

    return result

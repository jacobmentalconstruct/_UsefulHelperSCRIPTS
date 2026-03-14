"""
Manifold Store — typed CRUD operations on manifold contents via SQLite.

Ownership: src/core/store/manifold_store.py
    Handles all write and read operations against a manifold's SQLite
    database. Converts between typed Phase 2 objects and SQLite rows.
    The store speaks in typed objects — not raw dicts or tuples.

The store is role-agnostic. It operates on a connection + manifold_id.
The same store works identically for identity, external, and virtual
manifolds because they share the same schema.
"""

from __future__ import annotations

import json
import logging
import sqlite3
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


def _json_dumps(obj: Any) -> str:
    """Compact JSON serialisation for storage."""
    return json.dumps(obj, separators=(",", ":"), default=str)


def _json_loads(text: Optional[str]) -> Any:
    """Safe JSON deserialisation from storage."""
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Store: JSON parse failure (returning {}): %s", exc)
        return {}


def _json_loads_list(text: Optional[str]) -> list:
    """Safe JSON list deserialisation."""
    if not text:
        return []
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Store: JSON list parse failure (returning []): %s", exc)
        return []


class ManifoldStore:
    """
    Typed CRUD operations against a manifold's SQLite database.

    All write methods insert records. All read methods return typed
    Phase 2 objects. The store is stateless — it takes a connection
    and manifold_id per operation.
    """

    # =================================================================
    # WRITE — Nodes
    # =================================================================

    def add_node(self, conn: sqlite3.Connection, node: Node) -> None:
        """Insert a node record."""
        if not node.node_id:
            raise ValueError("add_node: node_id must not be empty")
        if not node.manifold_id:
            raise ValueError("add_node: manifold_id must not be empty")
        logger.debug("Store: add_node %s (manifold=%s)", node.node_id, node.manifold_id)
        conn.execute(
            """INSERT OR REPLACE INTO nodes
               (node_id, manifold_id, node_type, canonical_key, label,
                properties_json, source_refs_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                node.node_id,
                node.manifold_id,
                node.node_type.name,
                node.canonical_key,
                node.label,
                _json_dumps(node.properties),
                _json_dumps(node.source_refs),
                node.created_at,
                node.updated_at,
            ),
        )
        conn.commit()

    # =================================================================
    # WRITE — Edges
    # =================================================================

    def add_edge(self, conn: sqlite3.Connection, edge: Edge) -> None:
        """Insert an edge record."""
        if not edge.edge_id:
            raise ValueError("add_edge: edge_id must not be empty")
        if not edge.from_node_id or not edge.to_node_id:
            raise ValueError("add_edge: from_node_id and to_node_id must not be empty")
        if edge.from_node_id == edge.to_node_id:
            logger.warning(
                "Store: self-loop edge detected (edge=%s, node=%s)",
                edge.edge_id, edge.from_node_id,
            )
        logger.debug("Store: add_edge %s", edge.edge_id)
        conn.execute(
            """INSERT OR REPLACE INTO edges
               (edge_id, manifold_id, from_node_id, to_node_id, edge_type,
                weight, properties_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                edge.edge_id,
                edge.manifold_id,
                edge.from_node_id,
                edge.to_node_id,
                edge.edge_type.name,
                edge.weight,
                _json_dumps(edge.properties),
                edge.created_at,
                edge.updated_at,
            ),
        )
        conn.commit()

    # =================================================================
    # WRITE — Chunks
    # =================================================================

    def add_chunk(self, conn: sqlite3.Connection, chunk: Chunk) -> None:
        """Insert a chunk record (content-addressed, deduplicated)."""
        if not chunk.chunk_hash:
            raise ValueError("add_chunk: chunk_hash must not be empty")
        if not chunk.chunk_text:
            raise ValueError("add_chunk: chunk_text must not be empty")
        logger.debug("Store: add_chunk %s", chunk.chunk_hash)
        conn.execute(
            """INSERT OR IGNORE INTO chunks
               (chunk_hash, chunk_text, byte_length, char_length,
                token_estimate, hash_algorithm, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                chunk.chunk_hash,
                chunk.chunk_text,
                chunk.byte_length,
                chunk.char_length,
                chunk.token_estimate,
                chunk.hash_algorithm,
                chunk.created_at,
            ),
        )
        conn.commit()

    def add_chunk_occurrence(
        self, conn: sqlite3.Connection, occ: ChunkOccurrence
    ) -> None:
        """Insert a chunk occurrence (location-based)."""
        conn.execute(
            """INSERT OR REPLACE INTO chunk_occurrences
               (chunk_hash, manifold_id, source_path, chunk_index,
                start_line, end_line, start_offset, end_offset,
                context_label, properties_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                occ.chunk_hash,
                occ.manifold_id,
                occ.source_path,
                occ.chunk_index,
                occ.start_line,
                occ.end_line,
                occ.start_offset,
                occ.end_offset,
                occ.context_label,
                _json_dumps(occ.properties),
            ),
        )
        conn.commit()

    # =================================================================
    # WRITE — Embeddings
    # =================================================================

    def add_embedding(self, conn: sqlite3.Connection, emb: Embedding) -> None:
        """Insert an embedding record."""
        conn.execute(
            """INSERT OR REPLACE INTO embeddings
               (embedding_id, target_kind, target_id, model_name,
                model_version, dimensions, metric_type, is_normalized,
                vector_ref, vector_blob, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                emb.embedding_id,
                emb.target_kind.name,
                emb.target_id,
                emb.model_name,
                emb.model_version,
                emb.dimensions,
                emb.metric_type.name,
                1 if emb.is_normalized else 0,
                emb.vector_ref,
                emb.vector_blob,
                emb.created_at,
            ),
        )
        conn.commit()

    # =================================================================
    # WRITE — Hierarchy
    # =================================================================

    def add_hierarchy(
        self, conn: sqlite3.Connection, entry: HierarchyEntry
    ) -> None:
        """Insert a hierarchy record."""
        conn.execute(
            """INSERT OR REPLACE INTO hierarchy
               (hierarchy_id, manifold_id, node_id, parent_id, depth,
                sort_order, path_label, properties_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.hierarchy_id,
                entry.manifold_id,
                entry.node_id,
                entry.parent_id,
                entry.depth,
                entry.sort_order,
                entry.path_label,
                _json_dumps(entry.properties),
            ),
        )
        conn.commit()

    # =================================================================
    # WRITE — Metadata
    # =================================================================

    def add_metadata(
        self, conn: sqlite3.Connection, entry: MetadataEntry
    ) -> None:
        """Insert a metadata record."""
        conn.execute(
            """INSERT OR REPLACE INTO metadata
               (owner_kind, owner_id, manifold_id, key, value_json,
                properties_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                entry.owner_kind,
                entry.owner_id,
                entry.manifold_id,
                entry.key,
                _json_dumps(entry.value),
                _json_dumps(entry.properties),
                entry.created_at,
            ),
        )
        conn.commit()

    # =================================================================
    # WRITE — Provenance
    # =================================================================

    def add_provenance(self, conn: sqlite3.Connection, prov: Provenance) -> None:
        """Insert a provenance record."""
        conn.execute(
            """INSERT INTO provenance
               (owner_kind, owner_id, source_manifold_id, source_document,
                source_snapshot, stage, relation_origin, parser_name,
                parser_version, evidence_ref, upstream_ids_json,
                details_json, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                prov.owner_kind,
                prov.owner_id,
                prov.source_manifold_id,
                prov.source_document,
                prov.source_snapshot,
                prov.stage.name,
                prov.relation_origin.name,
                prov.parser_name,
                prov.parser_version,
                prov.evidence_ref,
                _json_dumps(prov.upstream_ids),
                _json_dumps(prov.details),
                prov.timestamp,
            ),
        )
        conn.commit()

    # =================================================================
    # WRITE — Cross-layer links
    # =================================================================

    def link_node_chunk(
        self, conn: sqlite3.Connection, binding: NodeChunkBinding
    ) -> None:
        """Insert a node ↔ chunk link."""
        conn.execute(
            """INSERT OR REPLACE INTO node_chunk_links
               (node_id, chunk_hash, manifold_id, binding_role, ordinal,
                properties_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (
                binding.node_id,
                binding.chunk_hash,
                binding.manifold_id,
                binding.binding_role,
                binding.ordinal,
                _json_dumps(binding.properties),
            ),
        )
        conn.commit()

    def link_node_embedding(
        self, conn: sqlite3.Connection, binding: NodeEmbeddingBinding
    ) -> None:
        """Insert a node ↔ embedding link."""
        conn.execute(
            """INSERT OR REPLACE INTO node_embedding_links
               (node_id, embedding_id, manifold_id, binding_role,
                properties_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                binding.node_id,
                binding.embedding_id,
                binding.manifold_id,
                binding.binding_role,
                _json_dumps(binding.properties),
            ),
        )
        conn.commit()

    def link_node_hierarchy(
        self, conn: sqlite3.Connection, binding: NodeHierarchyBinding
    ) -> None:
        """Insert a node ↔ hierarchy link."""
        conn.execute(
            """INSERT OR REPLACE INTO node_hierarchy_links
               (node_id, hierarchy_id, manifold_id, binding_role,
                properties_json)
               VALUES (?, ?, ?, ?, ?)""",
            (
                binding.node_id,
                binding.hierarchy_id,
                binding.manifold_id,
                binding.binding_role,
                _json_dumps(binding.properties),
            ),
        )
        conn.commit()

    # =================================================================
    # READ — Nodes
    # =================================================================

    def get_node(
        self, conn: sqlite3.Connection, node_id: NodeId
    ) -> Optional[Node]:
        """Fetch a single node by ID, or None if not found."""
        row = conn.execute(
            "SELECT * FROM nodes WHERE node_id = ?", (node_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_node(row)

    def list_nodes(
        self, conn: sqlite3.Connection, manifold_id: ManifoldId
    ) -> List[Node]:
        """List all nodes in a manifold."""
        rows = conn.execute(
            "SELECT * FROM nodes WHERE manifold_id = ?", (manifold_id,)
        ).fetchall()
        return [self._row_to_node(r) for r in rows]

    @staticmethod
    def _row_to_node(row: sqlite3.Row) -> Node:
        return Node(
            node_id=NodeId(row["node_id"]),
            manifold_id=ManifoldId(row["manifold_id"]),
            node_type=NodeType[row["node_type"]],
            canonical_key=row["canonical_key"] or "",
            label=row["label"] or "",
            properties=_json_loads(row["properties_json"]),
            source_refs=_json_loads_list(row["source_refs_json"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    # =================================================================
    # READ — Edges
    # =================================================================

    def get_edge(
        self, conn: sqlite3.Connection, edge_id: EdgeId
    ) -> Optional[Edge]:
        """Fetch a single edge by ID."""
        row = conn.execute(
            "SELECT * FROM edges WHERE edge_id = ?", (edge_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_edge(row)

    def list_edges(
        self, conn: sqlite3.Connection, manifold_id: ManifoldId
    ) -> List[Edge]:
        """List all edges in a manifold."""
        rows = conn.execute(
            "SELECT * FROM edges WHERE manifold_id = ?", (manifold_id,)
        ).fetchall()
        return [self._row_to_edge(r) for r in rows]

    @staticmethod
    def _row_to_edge(row: sqlite3.Row) -> Edge:
        return Edge(
            edge_id=EdgeId(row["edge_id"]),
            manifold_id=ManifoldId(row["manifold_id"]),
            from_node_id=NodeId(row["from_node_id"]),
            to_node_id=NodeId(row["to_node_id"]),
            edge_type=EdgeType[row["edge_type"]],
            weight=row["weight"],
            properties=_json_loads(row["properties_json"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
        )

    # =================================================================
    # READ — Chunks
    # =================================================================

    def get_chunk(
        self, conn: sqlite3.Connection, chunk_hash: ChunkHash
    ) -> Optional[Chunk]:
        """Fetch a single chunk by hash."""
        row = conn.execute(
            "SELECT * FROM chunks WHERE chunk_hash = ?", (chunk_hash,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_chunk(row)

    @staticmethod
    def _row_to_chunk(row: sqlite3.Row) -> Chunk:
        return Chunk(
            chunk_hash=ChunkHash(row["chunk_hash"]),
            chunk_text=row["chunk_text"],
            byte_length=row["byte_length"],
            char_length=row["char_length"],
            token_estimate=row["token_estimate"],
            hash_algorithm=row["hash_algorithm"] or "sha256",
            created_at=row["created_at"] or "",
        )

    # =================================================================
    # READ — Embeddings
    # =================================================================

    def get_embedding(
        self, conn: sqlite3.Connection, embedding_id: EmbeddingId
    ) -> Optional[Embedding]:
        """Fetch a single embedding by ID."""
        row = conn.execute(
            "SELECT * FROM embeddings WHERE embedding_id = ?", (embedding_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_embedding(row)

    @staticmethod
    def _row_to_embedding(row: sqlite3.Row) -> Embedding:
        return Embedding(
            embedding_id=EmbeddingId(row["embedding_id"]),
            target_kind=EmbeddingTargetKind[row["target_kind"]],
            target_id=row["target_id"],
            model_name=row["model_name"] or "",
            model_version=row["model_version"] or "",
            dimensions=row["dimensions"],
            metric_type=EmbeddingMetricType[row["metric_type"]],
            is_normalized=bool(row["is_normalized"]),
            vector_ref=row["vector_ref"],
            vector_blob=row["vector_blob"],
            created_at=row["created_at"] or "",
        )

    # =================================================================
    # READ — Hierarchy
    # =================================================================

    def get_hierarchy(
        self, conn: sqlite3.Connection, hierarchy_id: HierarchyId
    ) -> Optional[HierarchyEntry]:
        """Fetch a single hierarchy entry by ID."""
        row = conn.execute(
            "SELECT * FROM hierarchy WHERE hierarchy_id = ?", (hierarchy_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_hierarchy(row)

    @staticmethod
    def _row_to_hierarchy(row: sqlite3.Row) -> HierarchyEntry:
        return HierarchyEntry(
            hierarchy_id=HierarchyId(row["hierarchy_id"]),
            manifold_id=ManifoldId(row["manifold_id"]),
            node_id=NodeId(row["node_id"]),
            parent_id=HierarchyId(row["parent_id"]) if row["parent_id"] else None,
            depth=row["depth"],
            sort_order=row["sort_order"],
            path_label=row["path_label"] or "",
            properties=_json_loads(row["properties_json"]),
        )

    # =================================================================
    # READ — Metadata
    # =================================================================

    def get_metadata_for_owner(
        self,
        conn: sqlite3.Connection,
        owner_kind: str,
        owner_id: str,
        manifold_id: ManifoldId,
    ) -> List[MetadataEntry]:
        """Fetch all metadata entries for a specific owner."""
        rows = conn.execute(
            """SELECT * FROM metadata
               WHERE owner_kind = ? AND owner_id = ? AND manifold_id = ?""",
            (owner_kind, owner_id, manifold_id),
        ).fetchall()
        return [
            MetadataEntry(
                owner_kind=r["owner_kind"],
                owner_id=r["owner_id"],
                manifold_id=ManifoldId(r["manifold_id"]),
                key=r["key"] or "",
                value=_json_loads(r["value_json"]),
                properties=_json_loads(r["properties_json"]),
                created_at=r["created_at"] or "",
            )
            for r in rows
        ]

    # =================================================================
    # READ — Provenance
    # =================================================================

    def get_provenance_for_owner(
        self,
        conn: sqlite3.Connection,
        owner_kind: str,
        owner_id: str,
    ) -> List[Provenance]:
        """Fetch all provenance records for a specific owner."""
        rows = conn.execute(
            "SELECT * FROM provenance WHERE owner_kind = ? AND owner_id = ?",
            (owner_kind, owner_id),
        ).fetchall()
        return [self._row_to_provenance(r) for r in rows]

    @staticmethod
    def _row_to_provenance(row: sqlite3.Row) -> Provenance:
        return Provenance(
            owner_kind=row["owner_kind"],
            owner_id=row["owner_id"],
            source_manifold_id=(
                ManifoldId(row["source_manifold_id"])
                if row["source_manifold_id"]
                else None
            ),
            source_document=row["source_document"],
            source_snapshot=row["source_snapshot"],
            stage=ProvenanceStage[row["stage"]],
            relation_origin=ProvenanceRelationOrigin[row["relation_origin"]],
            parser_name=row["parser_name"],
            parser_version=row["parser_version"],
            evidence_ref=row["evidence_ref"],
            upstream_ids=_json_loads_list(row["upstream_ids_json"]),
            details=_json_loads(row["details_json"]),
            timestamp=row["timestamp"],
        )

    # =================================================================
    # READ — Cross-layer links
    # =================================================================

    def get_node_chunk_links(
        self, conn: sqlite3.Connection, node_id: NodeId
    ) -> List[NodeChunkBinding]:
        """Fetch all chunk bindings for a node."""
        rows = conn.execute(
            "SELECT * FROM node_chunk_links WHERE node_id = ?", (node_id,)
        ).fetchall()
        return [
            NodeChunkBinding(
                node_id=NodeId(r["node_id"]),
                chunk_hash=ChunkHash(r["chunk_hash"]),
                manifold_id=ManifoldId(r["manifold_id"]),
                binding_role=r["binding_role"] or "contains",
                ordinal=r["ordinal"],
                properties=_json_loads(r["properties_json"]),
            )
            for r in rows
        ]

    def get_node_embedding_links(
        self, conn: sqlite3.Connection, node_id: NodeId
    ) -> List[NodeEmbeddingBinding]:
        """Fetch all embedding bindings for a node."""
        rows = conn.execute(
            "SELECT * FROM node_embedding_links WHERE node_id = ?", (node_id,)
        ).fetchall()
        return [
            NodeEmbeddingBinding(
                node_id=NodeId(r["node_id"]),
                embedding_id=EmbeddingId(r["embedding_id"]),
                manifold_id=ManifoldId(r["manifold_id"]),
                binding_role=r["binding_role"] or "primary",
                properties=_json_loads(r["properties_json"]),
            )
            for r in rows
        ]

    def get_node_hierarchy_links(
        self, conn: sqlite3.Connection, node_id: NodeId
    ) -> List[NodeHierarchyBinding]:
        """Fetch all hierarchy bindings for a node."""
        rows = conn.execute(
            "SELECT * FROM node_hierarchy_links WHERE node_id = ?", (node_id,)
        ).fetchall()
        return [
            NodeHierarchyBinding(
                node_id=NodeId(r["node_id"]),
                hierarchy_id=HierarchyId(r["hierarchy_id"]),
                manifold_id=ManifoldId(r["manifold_id"]),
                binding_role=r["binding_role"] or "member",
                properties=_json_loads(r["properties_json"]),
            )
            for r in rows
        ]

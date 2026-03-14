"""
Phase 3 Tests — Persistent Manifold Storage and Factory Basics.

Covers:
    - Schema initialisation and table verification
    - ManifoldFactory disk/memory/RAM creation
    - ManifoldFactory open_manifold round-trip
    - ManifoldStore full CRUD (all entity types)
    - Cross-layer links (node↔chunk, node↔embedding, node↔hierarchy)
    - Round-trip typed object serialisation (write → read equality)
    - Same-schema symmetry: identical tables for all three roles
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from src.core.factory.manifold_factory import ManifoldFactory
from src.core.store._schema import (
    EXPECTED_TABLES,
    SCHEMA_VERSION,
    initialize_schema,
    verify_schema,
)
from src.core.store.manifold_store import ManifoldStore
from src.core.types.ids import (
    ChunkHash,
    EdgeId,
    EmbeddingId,
    HierarchyId,
    ManifoldId,
    NodeId,
    make_chunk_hash,
)
from src.core.types.enums import (
    EdgeType,
    EmbeddingMetricType,
    EmbeddingTargetKind,
    ManifoldRole,
    NodeType,
    ProvenanceRelationOrigin,
    ProvenanceStage,
    StorageMode,
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


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def factory() -> ManifoldFactory:
    return ManifoldFactory()


@pytest.fixture
def store() -> ManifoldStore:
    return ManifoldStore()


@pytest.fixture
def memory_conn() -> sqlite3.Connection:
    """A fresh in-memory SQLite connection with schema initialised."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    return conn


MID = ManifoldId("test-manifold-001")


# ===================================================================
# Schema Tests
# ===================================================================

class TestSchema:
    """Verify DDL and initialisation."""

    def test_schema_version_is_string(self) -> None:
        assert isinstance(SCHEMA_VERSION, str)
        assert SCHEMA_VERSION == "0.1.0"

    def test_expected_tables_count(self) -> None:
        assert len(EXPECTED_TABLES) == 16

    def test_initialize_creates_all_tables(self, memory_conn: sqlite3.Connection) -> None:
        tables = verify_schema(memory_conn)
        assert EXPECTED_TABLES.issubset(tables), (
            f"Missing tables: {EXPECTED_TABLES - tables}"
        )

    def test_initialize_is_idempotent(self, memory_conn: sqlite3.Connection) -> None:
        """Calling initialize_schema twice must not raise."""
        initialize_schema(memory_conn)
        tables = verify_schema(memory_conn)
        assert EXPECTED_TABLES.issubset(tables)

    def test_foreign_keys_enabled(self, memory_conn: sqlite3.Connection) -> None:
        fk = memory_conn.execute("PRAGMA foreign_keys").fetchone()[0]
        assert fk == 1

    def test_wal_mode(self) -> None:
        """WAL mode only applies to disk databases (memory uses :memory:)."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            conn = sqlite3.connect(db_path)
            initialize_schema(conn)
            mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
            assert mode == "wal"
            conn.close()
        finally:
            Path(db_path).unlink(missing_ok=True)
            # WAL creates companion files
            Path(db_path + "-wal").unlink(missing_ok=True)
            Path(db_path + "-shm").unlink(missing_ok=True)


# ===================================================================
# Factory Tests
# ===================================================================

class TestManifoldFactory:
    """Verify factory creation and opening of manifolds."""

    def test_create_memory_manifold_identity(self, factory: ManifoldFactory) -> None:
        m = factory.create_memory_manifold(
            ManifoldId("mem-id-1"), ManifoldRole.IDENTITY
        )
        meta = m.get_metadata()
        assert meta.manifold_id == "mem-id-1"
        assert meta.role == ManifoldRole.IDENTITY
        assert meta.storage_mode == StorageMode.SQLITE_MEMORY
        assert m.connection is not None

    def test_create_memory_manifold_external(self, factory: ManifoldFactory) -> None:
        m = factory.create_memory_manifold(
            ManifoldId("mem-ext-1"), ManifoldRole.EXTERNAL
        )
        meta = m.get_metadata()
        assert meta.role == ManifoldRole.EXTERNAL
        assert meta.storage_mode == StorageMode.SQLITE_MEMORY

    def test_create_memory_manifold_virtual(self, factory: ManifoldFactory) -> None:
        m = factory.create_memory_manifold(
            ManifoldId("mem-virt-1"), ManifoldRole.VIRTUAL
        )
        meta = m.get_metadata()
        assert meta.role == ManifoldRole.VIRTUAL
        assert meta.storage_mode == StorageMode.SQLITE_MEMORY

    def test_create_disk_manifold(self, factory: ManifoldFactory) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            m = factory.create_disk_manifold(
                ManifoldId("disk-1"), ManifoldRole.EXTERNAL, db_path,
            )
            meta = m.get_metadata()
            assert meta.manifold_id == "disk-1"
            assert meta.storage_mode == StorageMode.SQLITE_DISK
            assert m.connection is not None
            # Verify database file exists and has tables
            tables = verify_schema(m.connection)
            assert EXPECTED_TABLES.issubset(tables)
            m.connection.close()
        finally:
            Path(db_path).unlink(missing_ok=True)
            Path(db_path + "-wal").unlink(missing_ok=True)
            Path(db_path + "-shm").unlink(missing_ok=True)

    def test_open_manifold_roundtrip(self, factory: ManifoldFactory) -> None:
        """Create on disk, close, re-open and verify metadata matches."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            m1 = factory.create_disk_manifold(
                ManifoldId("open-rt-1"), ManifoldRole.IDENTITY, db_path,
            )
            m1.connection.close()

            m2 = factory.open_manifold(db_path)
            assert m2.get_metadata().manifold_id == "open-rt-1"
            assert m2.get_metadata().role == ManifoldRole.IDENTITY
            assert m2.get_metadata().storage_mode == StorageMode.SQLITE_DISK
            m2.connection.close()
        finally:
            Path(db_path).unlink(missing_ok=True)
            Path(db_path + "-wal").unlink(missing_ok=True)
            Path(db_path + "-shm").unlink(missing_ok=True)

    def test_create_manifold_unified_dispatch_disk(self, factory: ManifoldFactory) -> None:
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            m = factory.create_manifold(
                ManifoldId("uni-disk"), ManifoldRole.EXTERNAL,
                StorageMode.SQLITE_DISK, db_path,
            )
            assert m.get_metadata().storage_mode == StorageMode.SQLITE_DISK
            m.connection.close()
        finally:
            Path(db_path).unlink(missing_ok=True)
            Path(db_path + "-wal").unlink(missing_ok=True)
            Path(db_path + "-shm").unlink(missing_ok=True)

    def test_create_manifold_unified_dispatch_memory(self, factory: ManifoldFactory) -> None:
        m = factory.create_manifold(
            ManifoldId("uni-mem"), ManifoldRole.IDENTITY,
            StorageMode.SQLITE_MEMORY,
        )
        assert m.get_metadata().storage_mode == StorageMode.SQLITE_MEMORY

    def test_create_manifold_unified_dispatch_ram(self, factory: ManifoldFactory) -> None:
        m = factory.create_manifold(
            ManifoldId("uni-ram"), ManifoldRole.VIRTUAL,
            StorageMode.PYTHON_RAM,
        )
        assert m.get_metadata().storage_mode == StorageMode.PYTHON_RAM
        assert m.connection is None

    def test_create_disk_requires_path(self, factory: ManifoldFactory) -> None:
        with pytest.raises(ValueError, match="db_path is required"):
            factory.create_manifold(
                ManifoldId("no-path"), ManifoldRole.EXTERNAL,
                StorageMode.SQLITE_DISK,
            )

    def test_manifold_row_written(self, factory: ManifoldFactory) -> None:
        """Factory must write a manifolds row that open_manifold can read."""
        m = factory.create_memory_manifold(
            ManifoldId("row-check"), ManifoldRole.IDENTITY, "test desc"
        )
        row = m.connection.execute(
            "SELECT * FROM manifolds WHERE manifold_id = ?", ("row-check",)
        ).fetchone()
        assert row is not None
        assert row["role"] == "IDENTITY"
        assert row["description"] == "test desc"
        assert row["schema_version"] == SCHEMA_VERSION


# ===================================================================
# Same-Schema Symmetry
# ===================================================================

class TestSameSchemaSymmetry:
    """All three roles produce the same set of tables."""

    def test_identity_and_external_same_tables(self, factory: ManifoldFactory) -> None:
        m_id = factory.create_memory_manifold(ManifoldId("sym-id"), ManifoldRole.IDENTITY)
        m_ext = factory.create_memory_manifold(ManifoldId("sym-ext"), ManifoldRole.EXTERNAL)
        assert verify_schema(m_id.connection) == verify_schema(m_ext.connection)

    def test_identity_and_virtual_same_tables(self, factory: ManifoldFactory) -> None:
        m_id = factory.create_memory_manifold(ManifoldId("sym-id2"), ManifoldRole.IDENTITY)
        m_virt = factory.create_memory_manifold(ManifoldId("sym-virt"), ManifoldRole.VIRTUAL)
        assert verify_schema(m_id.connection) == verify_schema(m_virt.connection)


# ===================================================================
# Store CRUD — Nodes
# ===================================================================

class TestStoreNodes:
    """Node write/read round-trip."""

    def test_add_and_get_node(self, memory_conn: sqlite3.Connection, store: ManifoldStore) -> None:
        # Write manifold row first (FK constraint)
        memory_conn.execute(
            "INSERT INTO manifolds (manifold_id, role, storage_mode, schema_version) "
            "VALUES (?, ?, ?, ?)",
            (MID, "IDENTITY", "SQLITE_MEMORY", SCHEMA_VERSION),
        )
        memory_conn.commit()

        node = Node(
            node_id=NodeId("n-001"),
            manifold_id=MID,
            node_type=NodeType.SOURCE,
            canonical_key="test/file.py",
            label="file.py",
            properties={"lang": "python"},
            source_refs=["ref1", "ref2"],
        )
        store.add_node(memory_conn, node)
        got = store.get_node(memory_conn, NodeId("n-001"))

        assert got is not None
        assert got.node_id == "n-001"
        assert got.manifold_id == MID
        assert got.node_type == NodeType.SOURCE
        assert got.canonical_key == "test/file.py"
        assert got.label == "file.py"
        assert got.properties == {"lang": "python"}
        assert got.source_refs == ["ref1", "ref2"]

    def test_get_missing_node_returns_none(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        assert store.get_node(memory_conn, NodeId("nonexistent")) is None

    def test_list_nodes(self, memory_conn: sqlite3.Connection, store: ManifoldStore) -> None:
        memory_conn.execute(
            "INSERT INTO manifolds (manifold_id, role, storage_mode, schema_version) "
            "VALUES (?, ?, ?, ?)",
            (MID, "IDENTITY", "SQLITE_MEMORY", SCHEMA_VERSION),
        )
        memory_conn.commit()

        for i in range(3):
            store.add_node(memory_conn, Node(
                node_id=NodeId(f"n-list-{i}"),
                manifold_id=MID,
                node_type=NodeType.CONCEPT,
            ))
        nodes = store.list_nodes(memory_conn, MID)
        assert len(nodes) == 3


# ===================================================================
# Store CRUD — Edges
# ===================================================================

class TestStoreEdges:
    """Edge write/read round-trip."""

    def _setup(self, conn: sqlite3.Connection, store: ManifoldStore) -> None:
        conn.execute(
            "INSERT INTO manifolds (manifold_id, role, storage_mode, schema_version) "
            "VALUES (?, ?, ?, ?)",
            (MID, "EXTERNAL", "SQLITE_MEMORY", SCHEMA_VERSION),
        )
        # Need source and target nodes for FK
        store.add_node(conn, Node(
            node_id=NodeId("e-src"), manifold_id=MID, node_type=NodeType.SOURCE,
        ))
        store.add_node(conn, Node(
            node_id=NodeId("e-tgt"), manifold_id=MID, node_type=NodeType.CONCEPT,
        ))

    def test_add_and_get_edge(self, memory_conn: sqlite3.Connection, store: ManifoldStore) -> None:
        self._setup(memory_conn, store)
        edge = Edge(
            edge_id=EdgeId("ed-001"),
            manifold_id=MID,
            from_node_id=NodeId("e-src"),
            to_node_id=NodeId("e-tgt"),
            edge_type=EdgeType.CONTAINS,
            weight=0.85,
            properties={"reason": "structural"},
        )
        store.add_edge(memory_conn, edge)
        got = store.get_edge(memory_conn, EdgeId("ed-001"))

        assert got is not None
        assert got.edge_id == "ed-001"
        assert got.from_node_id == "e-src"
        assert got.to_node_id == "e-tgt"
        assert got.edge_type == EdgeType.CONTAINS
        assert got.weight == pytest.approx(0.85)
        assert got.properties == {"reason": "structural"}

    def test_list_edges(self, memory_conn: sqlite3.Connection, store: ManifoldStore) -> None:
        self._setup(memory_conn, store)
        for i in range(2):
            store.add_edge(memory_conn, Edge(
                edge_id=EdgeId(f"ed-list-{i}"),
                manifold_id=MID,
                from_node_id=NodeId("e-src"),
                to_node_id=NodeId("e-tgt"),
                edge_type=EdgeType.REFERENCES,
            ))
        edges = store.list_edges(memory_conn, MID)
        assert len(edges) == 2


# ===================================================================
# Store CRUD — Chunks
# ===================================================================

class TestStoreChunks:
    """Chunk write/read round-trip."""

    def test_add_and_get_chunk(self, memory_conn: sqlite3.Connection, store: ManifoldStore) -> None:
        ch = Chunk(
            chunk_hash=make_chunk_hash("def main():\n    pass\n"),
            chunk_text="def main():\n    pass\n",
        )
        store.add_chunk(memory_conn, ch)
        got = store.get_chunk(memory_conn, ch.chunk_hash)

        assert got is not None
        assert got.chunk_hash == ch.chunk_hash
        assert got.chunk_text == "def main():\n    pass\n"
        assert got.byte_length == ch.byte_length
        assert got.char_length == ch.char_length
        assert got.token_estimate == ch.token_estimate

    def test_chunk_deduplication(self, memory_conn: sqlite3.Connection, store: ManifoldStore) -> None:
        """INSERT OR IGNORE: same hash must not raise."""
        ch = Chunk(chunk_hash=ChunkHash("dup-hash"), chunk_text="hello")
        store.add_chunk(memory_conn, ch)
        store.add_chunk(memory_conn, ch)  # should not raise
        got = store.get_chunk(memory_conn, ChunkHash("dup-hash"))
        assert got is not None

    def test_add_chunk_occurrence(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        memory_conn.execute(
            "INSERT INTO manifolds (manifold_id, role, storage_mode, schema_version) "
            "VALUES (?, ?, ?, ?)",
            (MID, "IDENTITY", "SQLITE_MEMORY", SCHEMA_VERSION),
        )
        memory_conn.commit()

        ch = Chunk(chunk_hash=ChunkHash("occ-hash"), chunk_text="test chunk")
        store.add_chunk(memory_conn, ch)

        occ = ChunkOccurrence(
            chunk_hash=ChunkHash("occ-hash"),
            manifold_id=MID,
            source_path="src/test.py",
            chunk_index=3,
            start_line=10,
            end_line=20,
            context_label="function body",
        )
        store.add_chunk_occurrence(memory_conn, occ)

        row = memory_conn.execute(
            "SELECT * FROM chunk_occurrences WHERE chunk_hash = ?", ("occ-hash",)
        ).fetchone()
        assert row is not None
        assert row["source_path"] == "src/test.py"
        assert row["chunk_index"] == 3
        assert row["start_line"] == 10


# ===================================================================
# Store CRUD — Embeddings
# ===================================================================

class TestStoreEmbeddings:
    """Embedding write/read round-trip."""

    def test_add_and_get_embedding(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        emb = Embedding(
            embedding_id=EmbeddingId("emb-001"),
            target_kind=EmbeddingTargetKind.NODE,
            target_id="n-001",
            model_name="mxbai-embed-large",
            model_version="1.0",
            dimensions=1024,
            metric_type=EmbeddingMetricType.COSINE,
            is_normalized=True,
            vector_ref="faiss://idx/0",
        )
        store.add_embedding(memory_conn, emb)
        got = store.get_embedding(memory_conn, EmbeddingId("emb-001"))

        assert got is not None
        assert got.embedding_id == "emb-001"
        assert got.target_kind == EmbeddingTargetKind.NODE
        assert got.target_id == "n-001"
        assert got.model_name == "mxbai-embed-large"
        assert got.dimensions == 1024
        assert got.metric_type == EmbeddingMetricType.COSINE
        assert got.is_normalized is True
        assert got.vector_ref == "faiss://idx/0"

    def test_get_missing_embedding_returns_none(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        assert store.get_embedding(memory_conn, EmbeddingId("nope")) is None


# ===================================================================
# Store CRUD — Hierarchy
# ===================================================================

class TestStoreHierarchy:
    """Hierarchy write/read round-trip."""

    def test_add_and_get_hierarchy(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        memory_conn.execute(
            "INSERT INTO manifolds (manifold_id, role, storage_mode, schema_version) "
            "VALUES (?, ?, ?, ?)",
            (MID, "IDENTITY", "SQLITE_MEMORY", SCHEMA_VERSION),
        )
        store.add_node(memory_conn, Node(
            node_id=NodeId("h-node"), manifold_id=MID, node_type=NodeType.SOURCE,
        ))
        memory_conn.commit()

        h = HierarchyEntry(
            hierarchy_id=HierarchyId("hier-001"),
            manifold_id=MID,
            node_id=NodeId("h-node"),
            parent_id=None,
            depth=0,
            sort_order=1,
            path_label="/root",
            properties={"type": "directory"},
        )
        store.add_hierarchy(memory_conn, h)
        got = store.get_hierarchy(memory_conn, HierarchyId("hier-001"))

        assert got is not None
        assert got.hierarchy_id == "hier-001"
        assert got.node_id == "h-node"
        assert got.parent_id is None
        assert got.depth == 0
        assert got.path_label == "/root"
        assert got.properties == {"type": "directory"}


# ===================================================================
# Store CRUD — Metadata
# ===================================================================

class TestStoreMetadata:
    """Metadata write/read round-trip."""

    def test_add_and_get_metadata(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        memory_conn.execute(
            "INSERT INTO manifolds (manifold_id, role, storage_mode, schema_version) "
            "VALUES (?, ?, ?, ?)",
            (MID, "IDENTITY", "SQLITE_MEMORY", SCHEMA_VERSION),
        )
        memory_conn.commit()

        entry = MetadataEntry(
            owner_kind="node",
            owner_id="n-001",
            manifold_id=MID,
            key="importance",
            value={"score": 0.95},
            properties={"source": "manual"},
        )
        store.add_metadata(memory_conn, entry)
        results = store.get_metadata_for_owner(memory_conn, "node", "n-001", MID)

        assert len(results) == 1
        assert results[0].key == "importance"
        assert results[0].value == {"score": 0.95}
        assert results[0].properties == {"source": "manual"}


# ===================================================================
# Store CRUD — Provenance
# ===================================================================

class TestStoreProvenance:
    """Provenance write/read round-trip."""

    def test_add_and_get_provenance(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        prov = Provenance(
            owner_kind="node",
            owner_id="n-001",
            source_manifold_id=MID,
            source_document="src/main.py",
            source_snapshot="abc123",
            stage=ProvenanceStage.INGESTION,
            relation_origin=ProvenanceRelationOrigin.PARSED,
            parser_name="python_ast",
            parser_version="1.0",
            evidence_ref="ev-001",
            upstream_ids=["parent-1", "parent-2"],
            details={"lines": "1-50"},
            timestamp="2025-01-01T00:00:00Z",
        )
        store.add_provenance(memory_conn, prov)
        results = store.get_provenance_for_owner(memory_conn, "node", "n-001")

        assert len(results) == 1
        p = results[0]
        assert p.owner_kind == "node"
        assert p.source_manifold_id == MID
        assert p.source_document == "src/main.py"
        assert p.stage == ProvenanceStage.INGESTION
        assert p.relation_origin == ProvenanceRelationOrigin.PARSED
        assert p.parser_name == "python_ast"
        assert p.upstream_ids == ["parent-1", "parent-2"]
        assert p.details == {"lines": "1-50"}


# ===================================================================
# Store CRUD — Cross-Layer Links
# ===================================================================

class TestStoreCrossLayerLinks:
    """Cross-layer binding write/read round-trip."""

    def _setup_manifold_and_node(
        self, conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        conn.execute(
            "INSERT INTO manifolds (manifold_id, role, storage_mode, schema_version) "
            "VALUES (?, ?, ?, ?)",
            (MID, "EXTERNAL", "SQLITE_MEMORY", SCHEMA_VERSION),
        )
        store.add_node(conn, Node(
            node_id=NodeId("cl-node"), manifold_id=MID, node_type=NodeType.SOURCE,
        ))
        conn.commit()

    def test_link_node_chunk_roundtrip(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        self._setup_manifold_and_node(memory_conn, store)
        ch = Chunk(chunk_hash=ChunkHash("cl-chunk"), chunk_text="content")
        store.add_chunk(memory_conn, ch)

        binding = NodeChunkBinding(
            node_id=NodeId("cl-node"),
            chunk_hash=ChunkHash("cl-chunk"),
            manifold_id=MID,
            binding_role="contains",
            ordinal=0,
            properties={"position": "start"},
        )
        store.link_node_chunk(memory_conn, binding)
        links = store.get_node_chunk_links(memory_conn, NodeId("cl-node"))

        assert len(links) == 1
        assert links[0].chunk_hash == "cl-chunk"
        assert links[0].binding_role == "contains"
        assert links[0].ordinal == 0
        assert links[0].properties == {"position": "start"}

    def test_link_node_embedding_roundtrip(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        self._setup_manifold_and_node(memory_conn, store)
        emb = Embedding(
            embedding_id=EmbeddingId("cl-emb"),
            target_kind=EmbeddingTargetKind.NODE,
            target_id="cl-node",
        )
        store.add_embedding(memory_conn, emb)

        binding = NodeEmbeddingBinding(
            node_id=NodeId("cl-node"),
            embedding_id=EmbeddingId("cl-emb"),
            manifold_id=MID,
            binding_role="primary",
        )
        store.link_node_embedding(memory_conn, binding)
        links = store.get_node_embedding_links(memory_conn, NodeId("cl-node"))

        assert len(links) == 1
        assert links[0].embedding_id == "cl-emb"
        assert links[0].binding_role == "primary"

    def test_link_node_hierarchy_roundtrip(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        self._setup_manifold_and_node(memory_conn, store)
        h = HierarchyEntry(
            hierarchy_id=HierarchyId("cl-hier"),
            manifold_id=MID,
            node_id=NodeId("cl-node"),
        )
        store.add_hierarchy(memory_conn, h)

        binding = NodeHierarchyBinding(
            node_id=NodeId("cl-node"),
            hierarchy_id=HierarchyId("cl-hier"),
            manifold_id=MID,
            binding_role="member",
        )
        store.link_node_hierarchy(memory_conn, binding)
        links = store.get_node_hierarchy_links(memory_conn, NodeId("cl-node"))

        assert len(links) == 1
        assert links[0].hierarchy_id == "cl-hier"
        assert links[0].binding_role == "member"

    def test_multiple_chunks_per_node(
        self, memory_conn: sqlite3.Connection, store: ManifoldStore
    ) -> None:
        """A node can bind to many chunks at different ordinals."""
        self._setup_manifold_and_node(memory_conn, store)
        for i in range(3):
            ch = Chunk(chunk_hash=ChunkHash(f"multi-ch-{i}"), chunk_text=f"text {i}")
            store.add_chunk(memory_conn, ch)
            store.link_node_chunk(memory_conn, NodeChunkBinding(
                node_id=NodeId("cl-node"),
                chunk_hash=ChunkHash(f"multi-ch-{i}"),
                manifold_id=MID,
                ordinal=i,
            ))
        links = store.get_node_chunk_links(memory_conn, NodeId("cl-node"))
        assert len(links) == 3
        ordinals = sorted(link.ordinal for link in links)
        assert ordinals == [0, 1, 2]


# ===================================================================
# Factory + Store Integration
# ===================================================================

class TestFactoryStoreIntegration:
    """Factory creates manifolds that the store can operate on."""

    def test_factory_memory_then_store_crud(
        self, factory: ManifoldFactory, store: ManifoldStore
    ) -> None:
        m = factory.create_memory_manifold(
            ManifoldId("int-mem"), ManifoldRole.EXTERNAL
        )
        conn = m.connection
        mid = m.get_metadata().manifold_id

        # Write a node
        node = Node(
            node_id=NodeId("int-n1"),
            manifold_id=ManifoldId(mid),
            node_type=NodeType.SOURCE,
            label="integration test node",
        )
        store.add_node(conn, node)

        # Read it back
        got = store.get_node(conn, NodeId("int-n1"))
        assert got is not None
        assert got.label == "integration test node"

    def test_factory_disk_then_reopen_with_data(
        self, factory: ManifoldFactory, store: ManifoldStore
    ) -> None:
        """Write data via factory+store, close, reopen and verify data persists."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db_path = f.name
        try:
            # Create and populate
            m1 = factory.create_disk_manifold(
                ManifoldId("persist-1"), ManifoldRole.IDENTITY, db_path,
            )
            store.add_node(m1.connection, Node(
                node_id=NodeId("persist-n1"),
                manifold_id=ManifoldId("persist-1"),
                node_type=NodeType.CONCEPT,
                label="persisted node",
            ))
            m1.connection.close()

            # Re-open and verify
            m2 = factory.open_manifold(db_path)
            got = store.get_node(m2.connection, NodeId("persist-n1"))
            assert got is not None
            assert got.label == "persisted node"
            m2.connection.close()
        finally:
            Path(db_path).unlink(missing_ok=True)
            Path(db_path + "-wal").unlink(missing_ok=True)
            Path(db_path + "-shm").unlink(missing_ok=True)

    def test_full_entity_roundtrip(
        self, factory: ManifoldFactory, store: ManifoldStore
    ) -> None:
        """Write all entity types and verify each one reads back correctly."""
        m = factory.create_memory_manifold(
            ManifoldId("full-rt"), ManifoldRole.EXTERNAL
        )
        conn = m.connection
        mid = ManifoldId("full-rt")

        # Node
        store.add_node(conn, Node(
            node_id=NodeId("frt-n1"), manifold_id=mid, node_type=NodeType.SOURCE,
        ))

        # Edge (needs two nodes)
        store.add_node(conn, Node(
            node_id=NodeId("frt-n2"), manifold_id=mid, node_type=NodeType.CONCEPT,
        ))
        store.add_edge(conn, Edge(
            edge_id=EdgeId("frt-e1"), manifold_id=mid,
            from_node_id=NodeId("frt-n1"), to_node_id=NodeId("frt-n2"),
            edge_type=EdgeType.CONTAINS,
        ))

        # Chunk + occurrence
        ch = Chunk(chunk_hash=ChunkHash("frt-ch1"), chunk_text="full roundtrip text")
        store.add_chunk(conn, ch)
        store.add_chunk_occurrence(conn, ChunkOccurrence(
            chunk_hash=ChunkHash("frt-ch1"), manifold_id=mid,
            source_path="test.py", chunk_index=0,
        ))

        # Embedding
        store.add_embedding(conn, Embedding(
            embedding_id=EmbeddingId("frt-emb1"),
            target_kind=EmbeddingTargetKind.NODE,
            target_id="frt-n1",
        ))

        # Hierarchy
        store.add_hierarchy(conn, HierarchyEntry(
            hierarchy_id=HierarchyId("frt-h1"), manifold_id=mid,
            node_id=NodeId("frt-n1"),
        ))

        # Metadata
        store.add_metadata(conn, MetadataEntry(
            owner_kind="node", owner_id="frt-n1", manifold_id=mid,
            key="tag", value="important",
        ))

        # Provenance
        store.add_provenance(conn, Provenance(
            owner_kind="node", owner_id="frt-n1",
            stage=ProvenanceStage.INGESTION,
            relation_origin=ProvenanceRelationOrigin.PARSED,
        ))

        # Cross-layer links
        store.link_node_chunk(conn, NodeChunkBinding(
            node_id=NodeId("frt-n1"), chunk_hash=ChunkHash("frt-ch1"),
            manifold_id=mid,
        ))
        store.link_node_embedding(conn, NodeEmbeddingBinding(
            node_id=NodeId("frt-n1"), embedding_id=EmbeddingId("frt-emb1"),
            manifold_id=mid,
        ))
        store.link_node_hierarchy(conn, NodeHierarchyBinding(
            node_id=NodeId("frt-n1"), hierarchy_id=HierarchyId("frt-h1"),
            manifold_id=mid,
        ))

        # Verify all reads
        assert store.get_node(conn, NodeId("frt-n1")) is not None
        assert store.get_edge(conn, EdgeId("frt-e1")) is not None
        assert store.get_chunk(conn, ChunkHash("frt-ch1")) is not None
        assert store.get_embedding(conn, EmbeddingId("frt-emb1")) is not None
        assert store.get_hierarchy(conn, HierarchyId("frt-h1")) is not None
        assert len(store.list_nodes(conn, mid)) == 2
        assert len(store.list_edges(conn, mid)) == 1
        assert len(store.get_metadata_for_owner(conn, "node", "frt-n1", mid)) == 1
        assert len(store.get_provenance_for_owner(conn, "node", "frt-n1")) == 1
        assert len(store.get_node_chunk_links(conn, NodeId("frt-n1"))) == 1
        assert len(store.get_node_embedding_links(conn, NodeId("frt-n1"))) == 1
        assert len(store.get_node_hierarchy_links(conn, NodeId("frt-n1"))) == 1


# ===================================================================
# BaseManifold Connection Property
# ===================================================================

class TestBaseManifoldConnection:
    """Verify the connection attribute on manifold objects."""

    def test_ram_manifold_has_no_connection(self, factory: ManifoldFactory) -> None:
        m = factory.create_manifold(
            ManifoldId("ram-conn"), ManifoldRole.VIRTUAL, StorageMode.PYTHON_RAM,
        )
        assert m.connection is None

    def test_memory_manifold_has_connection(self, factory: ManifoldFactory) -> None:
        m = factory.create_memory_manifold(
            ManifoldId("mem-conn"), ManifoldRole.IDENTITY,
        )
        assert m.connection is not None
        assert isinstance(m.connection, sqlite3.Connection)

    def test_connection_is_usable(self, factory: ManifoldFactory) -> None:
        m = factory.create_memory_manifold(
            ManifoldId("use-conn"), ManifoldRole.EXTERNAL,
        )
        # Should be able to execute queries on the connection
        tables = verify_schema(m.connection)
        assert len(tables) >= 16

"""
Phase 4 Tests — Projection and Fusion.

Covers:
    - NodeType.QUERY enum existence
    - ProjectedSlice expanded fields (backward compatibility)
    - Identity projection by node ID (SQLite memory manifold)
    - External projection by node ID
    - Projection provenance stamping
    - Linked chunks/metadata/provenance included in projected slice
    - Query projection creates stable typed artifact
    - Fusion merges projected slices into VirtualManifold
    - Fusion preserves source manifold ancestry
    - Explicit bridge edges
    - Auto canonical_key bridging
    - Label fallback bridging
    - Fusion without bridges
    - Fusion with query artifact
    - Deterministic repeat of same fusion inputs
    - Virtual manifold same-schema check
"""

import pytest

from src.core.contracts.fusion_contract import (
    BridgeEdge,
    BridgeRequest,
    FusionAncestry,
    FusionResult,
)
from src.core.contracts.projection_contract import (
    ProjectedSlice,
    ProjectionMetadata,
    QueryProjectionArtifact,
)
from src.core.factory.manifold_factory import ManifoldFactory
from src.core.fusion.fusion_engine import FusionEngine
from src.core.manifolds.virtual_manifold import VirtualManifold
from src.core.projection.external_projection import ExternalProjection
from src.core.projection.identity_projection import IdentityProjection
from src.core.projection.query_projection import QueryProjection
from src.core.store.manifold_store import ManifoldStore
from src.core.types.bindings import NodeChunkBinding
from src.core.types.enums import (
    EdgeType,
    ManifoldRole,
    NodeType,
    ProjectionSourceKind,
    ProvenanceRelationOrigin,
    ProvenanceStage,
    StorageMode,
)
from src.core.types.graph import Chunk, Edge, MetadataEntry, Node
from src.core.types.ids import (
    ChunkHash,
    EdgeId,
    ManifoldId,
    NodeId,
    deterministic_hash,
)
from src.core.types.provenance import Provenance


# ===================================================================
# Fixtures
# ===================================================================

@pytest.fixture
def factory() -> ManifoldFactory:
    return ManifoldFactory()


@pytest.fixture
def store() -> ManifoldStore:
    return ManifoldStore()


def _populate_identity_manifold(factory, store):
    """Create and populate an identity manifold with test data."""
    m = factory.create_memory_manifold(
        ManifoldId("id-manifold"), ManifoldRole.IDENTITY,
    )
    conn = m.connection
    mid = ManifoldId("id-manifold")

    # Nodes
    store.add_node(conn, Node(
        node_id=NodeId("id-n1"), manifold_id=mid,
        node_type=NodeType.SESSION, canonical_key="session-alpha",
        label="Session Alpha",
    ))
    store.add_node(conn, Node(
        node_id=NodeId("id-n2"), manifold_id=mid,
        node_type=NodeType.USER, canonical_key="user-bob",
        label="Bob",
    ))
    store.add_node(conn, Node(
        node_id=NodeId("id-n3"), manifold_id=mid,
        node_type=NodeType.AGENT, label="Assistant",
    ))

    # Edges (id-n1 -> id-n2, id-n2 -> id-n3)
    store.add_edge(conn, Edge(
        edge_id=EdgeId("id-e1"), manifold_id=mid,
        from_node_id=NodeId("id-n1"), to_node_id=NodeId("id-n2"),
        edge_type=EdgeType.CONTAINS,
    ))
    store.add_edge(conn, Edge(
        edge_id=EdgeId("id-e2"), manifold_id=mid,
        from_node_id=NodeId("id-n2"), to_node_id=NodeId("id-n3"),
        edge_type=EdgeType.REFERENCES,
    ))

    # Chunk + binding
    ch = Chunk(chunk_hash=ChunkHash("id-ch1"), chunk_text="session context data")
    store.add_chunk(conn, ch)
    store.link_node_chunk(conn, NodeChunkBinding(
        node_id=NodeId("id-n1"), chunk_hash=ChunkHash("id-ch1"),
        manifold_id=mid, ordinal=0,
    ))

    # Metadata
    store.add_metadata(conn, MetadataEntry(
        owner_kind="node", owner_id="id-n1", manifold_id=mid,
        key="importance", value={"score": 0.9},
    ))

    # Provenance
    store.add_provenance(conn, Provenance(
        owner_kind="node", owner_id="id-n1",
        source_manifold_id=mid,
        stage=ProvenanceStage.INGESTION,
        relation_origin=ProvenanceRelationOrigin.DECLARED,
    ))

    return m


def _populate_external_manifold(factory, store):
    """Create and populate an external manifold with test data."""
    m = factory.create_memory_manifold(
        ManifoldId("ext-manifold"), ManifoldRole.EXTERNAL,
    )
    conn = m.connection
    mid = ManifoldId("ext-manifold")

    # Nodes — note ext-n2 shares canonical_key "user-bob" with id-n2
    store.add_node(conn, Node(
        node_id=NodeId("ext-n1"), manifold_id=mid,
        node_type=NodeType.SOURCE, canonical_key="docs/readme.md",
        label="README",
    ))
    store.add_node(conn, Node(
        node_id=NodeId("ext-n2"), manifold_id=mid,
        node_type=NodeType.CONCEPT, canonical_key="user-bob",
        label="Bob Entity",
    ))
    store.add_node(conn, Node(
        node_id=NodeId("ext-n3"), manifold_id=mid,
        node_type=NodeType.TOPIC, label="GraphRAG",
    ))

    # Edge
    store.add_edge(conn, Edge(
        edge_id=EdgeId("ext-e1"), manifold_id=mid,
        from_node_id=NodeId("ext-n1"), to_node_id=NodeId("ext-n2"),
        edge_type=EdgeType.CONTAINS,
    ))

    # Chunk + binding
    ch = Chunk(chunk_hash=ChunkHash("ext-ch1"), chunk_text="external corpus text")
    store.add_chunk(conn, ch)
    store.link_node_chunk(conn, NodeChunkBinding(
        node_id=NodeId("ext-n1"), chunk_hash=ChunkHash("ext-ch1"),
        manifold_id=mid, ordinal=0,
    ))

    return m


# ===================================================================
# NodeType.QUERY
# ===================================================================

class TestNodeTypeQuery:
    def test_query_enum_exists(self) -> None:
        assert NodeType.QUERY is not None
        assert NodeType.QUERY.name == "QUERY"


# ===================================================================
# ProjectedSlice Backward Compatibility
# ===================================================================

class TestProjectedSliceExpanded:
    def test_new_fields_default_to_empty(self) -> None:
        """New typed object lists default to empty — no breakage."""
        ps = ProjectedSlice(
            metadata=ProjectionMetadata(
                source_manifold_id=ManifoldId("test"),
                source_kind=ProjectionSourceKind.IDENTITY,
            ),
        )
        assert ps.nodes == []
        assert ps.edges == []
        assert ps.chunks == []
        assert ps.embeddings == []
        assert ps.provenance_entries == []
        assert ps.node_chunk_bindings == []

    def test_backward_compatible_construction(self) -> None:
        """Phase 2 style construction still works."""
        ps = ProjectedSlice(
            metadata=ProjectionMetadata(
                source_manifold_id=ManifoldId("id-1"),
                source_kind=ProjectionSourceKind.IDENTITY,
            ),
            node_ids=[NodeId("n1"), NodeId("n2")],
            edge_ids=[EdgeId("e1")],
        )
        assert len(ps.node_ids) == 2
        assert len(ps.edge_ids) == 1


# ===================================================================
# Identity Projection
# ===================================================================

class TestIdentityProjection:
    def test_project_by_node_ids(self, factory, store) -> None:
        m = _populate_identity_manifold(factory, store)
        proj = IdentityProjection(store=store)
        sl = proj.project_by_ids(m, [NodeId("id-n1"), NodeId("id-n2")])

        assert sl.metadata.source_kind == ProjectionSourceKind.IDENTITY
        assert sl.metadata.source_manifold_id == "id-manifold"
        assert len(sl.nodes) == 2
        node_ids = {n.node_id for n in sl.nodes}
        assert NodeId("id-n1") in node_ids
        assert NodeId("id-n2") in node_ids

    def test_edges_closed_subgraph(self, factory, store) -> None:
        """Only edges with BOTH endpoints in selected set are included."""
        m = _populate_identity_manifold(factory, store)
        proj = IdentityProjection(store=store)
        # Select n1 and n2 — edge n1->n2 included, edge n2->n3 excluded
        sl = proj.project_by_ids(m, [NodeId("id-n1"), NodeId("id-n2")])
        assert len(sl.edges) == 1
        assert sl.edges[0].edge_id == "id-e1"

    def test_linked_chunks_included(self, factory, store) -> None:
        m = _populate_identity_manifold(factory, store)
        proj = IdentityProjection(store=store)
        sl = proj.project_by_ids(m, [NodeId("id-n1")])
        assert len(sl.chunks) == 1
        assert sl.chunks[0].chunk_hash == "id-ch1"
        assert len(sl.node_chunk_bindings) == 1


# ===================================================================
# External Projection
# ===================================================================

class TestExternalProjection:
    def test_project_by_node_ids(self, factory, store) -> None:
        m = _populate_external_manifold(factory, store)
        proj = ExternalProjection(store=store)
        sl = proj.project_by_ids(m, [NodeId("ext-n1"), NodeId("ext-n2")])

        assert sl.metadata.source_kind == ProjectionSourceKind.EXTERNAL
        assert len(sl.nodes) == 2

    def test_missing_node_skipped(self, factory, store) -> None:
        """Requesting a nonexistent node ID does not crash."""
        m = _populate_external_manifold(factory, store)
        proj = ExternalProjection(store=store)
        sl = proj.project_by_ids(m, [NodeId("ext-n1"), NodeId("nonexistent")])
        assert len(sl.nodes) == 1


# ===================================================================
# Projection Provenance
# ===================================================================

class TestProjectionProvenance:
    def test_projected_nodes_have_projection_provenance(self, factory, store) -> None:
        m = _populate_identity_manifold(factory, store)
        proj = IdentityProjection(store=store)
        sl = proj.project_by_ids(m, [NodeId("id-n1")])

        proj_provs = [
            p for p in sl.provenance_entries
            if p.stage == ProvenanceStage.PROJECTION
        ]
        assert len(proj_provs) >= 1
        node_proj = [p for p in proj_provs if p.owner_kind == "node"]
        assert any(p.owner_id == "id-n1" for p in node_proj)

    def test_source_manifold_preserved_in_provenance(self, factory, store) -> None:
        m = _populate_identity_manifold(factory, store)
        proj = IdentityProjection(store=store)
        sl = proj.project_by_ids(m, [NodeId("id-n1")])

        proj_provs = [
            p for p in sl.provenance_entries
            if p.stage == ProvenanceStage.PROJECTION and p.owner_kind == "node"
        ]
        assert all(
            p.source_manifold_id == "id-manifold" for p in proj_provs
        )


# ===================================================================
# Query Projection
# ===================================================================

class TestQueryProjection:
    def test_creates_query_typed_node(self) -> None:
        proj = QueryProjection()
        sl = proj.project(None, {"raw_query": "explain gravity scoring"})
        assert len(sl.nodes) == 1
        assert sl.nodes[0].node_type == NodeType.QUERY

    def test_deterministic_id(self) -> None:
        proj = QueryProjection()
        sl1 = proj.project(None, {"raw_query": "test query"})
        sl2 = proj.project(None, {"raw_query": "test query"})
        assert sl1.nodes[0].node_id == sl2.nodes[0].node_id

    def test_artifact_in_projected_data(self) -> None:
        proj = QueryProjection()
        sl = proj.project(None, {
            "raw_query": "what is fusion?",
            "parsed_intent": {"topic": "fusion"},
        })
        artifact = sl.projected_data.get("query_artifact")
        assert artifact is not None
        assert isinstance(artifact, QueryProjectionArtifact)
        assert artifact.raw_query == "what is fusion?"
        assert artifact.query_node is not None
        assert artifact.query_node_id == sl.nodes[0].node_id

    def test_missing_query_raises(self) -> None:
        proj = QueryProjection()
        with pytest.raises(ValueError, match="raw_query"):
            proj.project(None, {})


# ===================================================================
# Fusion Engine — Basic Merge
# ===================================================================

class TestFusionEngine:
    def test_merges_slices_into_vm(self, factory, store) -> None:
        id_m = _populate_identity_manifold(factory, store)
        ext_m = _populate_external_manifold(factory, store)

        id_proj = IdentityProjection(store=store)
        ext_proj = ExternalProjection(store=store)

        id_slice = id_proj.project_by_ids(id_m, [NodeId("id-n1"), NodeId("id-n2")])
        ext_slice = ext_proj.project_by_ids(ext_m, [NodeId("ext-n1"), NodeId("ext-n2")])

        engine = FusionEngine()
        result = engine.fuse(identity_slice=id_slice, external_slice=ext_slice)

        vm = result.virtual_manifold
        assert isinstance(vm, VirtualManifold)
        # All 4 nodes present
        assert len(vm.get_nodes()) == 4

    def test_source_manifold_ids_tracked(self, factory, store) -> None:
        id_m = _populate_identity_manifold(factory, store)
        ext_m = _populate_external_manifold(factory, store)

        id_slice = IdentityProjection(store=store).project_by_ids(
            id_m, [NodeId("id-n1")],
        )
        ext_slice = ExternalProjection(store=store).project_by_ids(
            ext_m, [NodeId("ext-n1")],
        )

        result = FusionEngine().fuse(
            identity_slice=id_slice, external_slice=ext_slice,
        )
        vm = result.virtual_manifold
        assert ManifoldId("id-manifold") in vm.source_manifold_ids
        assert ManifoldId("ext-manifold") in vm.source_manifold_ids

    def test_ancestry_recorded(self, factory, store) -> None:
        id_m = _populate_identity_manifold(factory, store)
        ext_m = _populate_external_manifold(factory, store)

        id_slice = IdentityProjection(store=store).project_by_ids(
            id_m, [NodeId("id-n1")],
        )
        ext_slice = ExternalProjection(store=store).project_by_ids(
            ext_m, [NodeId("ext-n1")],
        )
        result = FusionEngine().fuse(
            identity_slice=id_slice, external_slice=ext_slice,
        )
        assert result.ancestry.projection_count == 2
        assert len(result.ancestry.source_manifold_ids) == 2

    def test_vm_edges_include_projected_edges(self, factory, store) -> None:
        id_m = _populate_identity_manifold(factory, store)
        id_slice = IdentityProjection(store=store).project_by_ids(
            id_m, [NodeId("id-n1"), NodeId("id-n2")],
        )
        result = FusionEngine().fuse(identity_slice=id_slice)
        vm = result.virtual_manifold
        # Edge id-e1 (n1->n2) should be in VM
        assert EdgeId("id-e1") in vm.get_edges()


# ===================================================================
# Bridge Creation
# ===================================================================

class TestBridgeCreation:
    def test_explicit_bridge(self, factory, store) -> None:
        id_m = _populate_identity_manifold(factory, store)
        ext_m = _populate_external_manifold(factory, store)

        id_slice = IdentityProjection(store=store).project_by_ids(
            id_m, [NodeId("id-n1")],
        )
        ext_slice = ExternalProjection(store=store).project_by_ids(
            ext_m, [NodeId("ext-n1")],
        )

        req = BridgeRequest(
            source_node=NodeId("id-n1"), target_node=NodeId("ext-n1"),
            source_manifold=ManifoldId("id-manifold"),
            target_manifold=ManifoldId("ext-manifold"),
        )
        result = FusionEngine().fuse(
            identity_slice=id_slice, external_slice=ext_slice,
            bridge_requests=[req],
        )
        assert len(result.bridge_edges) >= 1
        be = result.bridge_edges[0]
        assert be.source_node == "id-n1"
        assert be.target_node == "ext-n1"
        assert be.edge_type == EdgeType.BRIDGE

    def test_auto_bridge_by_canonical_key(self, factory, store) -> None:
        """id-n2 and ext-n2 share canonical_key 'user-bob'."""
        id_m = _populate_identity_manifold(factory, store)
        ext_m = _populate_external_manifold(factory, store)

        id_slice = IdentityProjection(store=store).project_by_ids(
            id_m, [NodeId("id-n2")],
        )
        ext_slice = ExternalProjection(store=store).project_by_ids(
            ext_m, [NodeId("ext-n2")],
        )

        result = FusionEngine().fuse(
            identity_slice=id_slice, external_slice=ext_slice,
        )
        # Should auto-bridge on canonical_key "user-bob"
        assert len(result.bridge_edges) == 1
        be = result.bridge_edges[0]
        assert be.properties.get("match_type") == "canonical_key"
        assert be.properties.get("key") == "user-bob"
        assert be.weight == 1.0

    def test_label_fallback_bridge(self, factory, store) -> None:
        """When no canonical_key matches, fall back to label matching."""
        id_m = factory.create_memory_manifold(
            ManifoldId("id-label"), ManifoldRole.IDENTITY,
        )
        ext_m = factory.create_memory_manifold(
            ManifoldId("ext-label"), ManifoldRole.EXTERNAL,
        )

        # Nodes with matching labels but no canonical_key overlap
        store.add_node(id_m.connection, Node(
            node_id=NodeId("lb-id1"), manifold_id=ManifoldId("id-label"),
            node_type=NodeType.CONCEPT, label="GraphRAG",
        ))
        store.add_node(ext_m.connection, Node(
            node_id=NodeId("lb-ext1"), manifold_id=ManifoldId("ext-label"),
            node_type=NodeType.TOPIC, label="graphrag",  # lowercase match
        ))

        id_slice = IdentityProjection(store=store).project_by_ids(
            id_m, [NodeId("lb-id1")],
        )
        ext_slice = ExternalProjection(store=store).project_by_ids(
            ext_m, [NodeId("lb-ext1")],
        )

        result = FusionEngine().fuse(
            identity_slice=id_slice, external_slice=ext_slice,
        )
        assert len(result.bridge_edges) == 1
        assert result.bridge_edges[0].properties.get("match_type") == "label"
        assert result.bridge_edges[0].weight == pytest.approx(0.7)

    def test_bridge_has_fusion_provenance(self, factory, store) -> None:
        id_m = _populate_identity_manifold(factory, store)
        ext_m = _populate_external_manifold(factory, store)

        id_slice = IdentityProjection(store=store).project_by_ids(
            id_m, [NodeId("id-n2")],
        )
        ext_slice = ExternalProjection(store=store).project_by_ids(
            ext_m, [NodeId("ext-n2")],
        )
        result = FusionEngine().fuse(
            identity_slice=id_slice, external_slice=ext_slice,
        )
        # Find FUSION-stage provenance
        fusion_provs = [
            p for p in result.provenance
            if p.stage == ProvenanceStage.FUSION
        ]
        assert len(fusion_provs) >= 1
        assert all(
            p.relation_origin == ProvenanceRelationOrigin.FUSED
            for p in fusion_provs
        )


# ===================================================================
# Fusion Without Bridges
# ===================================================================

class TestFusionWithoutBridges:
    def test_disjoint_regions_valid(self, factory, store) -> None:
        """Fusion succeeds even when no bridges can be created."""
        id_m = _populate_identity_manifold(factory, store)
        ext_m = _populate_external_manifold(factory, store)

        # Pick nodes with no shared canonical_key or label
        id_slice = IdentityProjection(store=store).project_by_ids(
            id_m, [NodeId("id-n3")],  # AGENT, label="Assistant"
        )
        ext_slice = ExternalProjection(store=store).project_by_ids(
            ext_m, [NodeId("ext-n1")],  # SOURCE, label="README"
        )

        result = FusionEngine().fuse(
            identity_slice=id_slice, external_slice=ext_slice,
        )
        vm = result.virtual_manifold
        assert len(vm.get_nodes()) == 2
        assert len(result.bridge_edges) == 0


# ===================================================================
# Fusion With Query
# ===================================================================

class TestFusionWithQuery:
    def test_query_node_in_vm(self, factory, store) -> None:
        id_m = _populate_identity_manifold(factory, store)
        id_slice = IdentityProjection(store=store).project_by_ids(
            id_m, [NodeId("id-n1")],
        )

        q_proj = QueryProjection()
        q_slice = q_proj.project(None, {"raw_query": "what is GraphRAG?"})
        artifact = q_slice.projected_data["query_artifact"]

        result = FusionEngine().fuse(
            identity_slice=id_slice, query_artifact=artifact,
        )
        vm = result.virtual_manifold
        # Should have id-n1 + query node
        assert len(vm.get_nodes()) == 2
        query_nodes = [
            n for n in vm.get_nodes().values()
            if n.node_type == NodeType.QUERY
        ]
        assert len(query_nodes) == 1


# ===================================================================
# Fusion Determinism
# ===================================================================

class TestFusionDeterminism:
    def test_same_inputs_same_shape(self, factory, store) -> None:
        """Same projection inputs produce same node/edge/bridge counts."""
        id_m = _populate_identity_manifold(factory, store)
        ext_m = _populate_external_manifold(factory, store)

        id_proj = IdentityProjection(store=store)
        ext_proj = ExternalProjection(store=store)

        id_slice = id_proj.project_by_ids(id_m, [NodeId("id-n2")])
        ext_slice = ext_proj.project_by_ids(ext_m, [NodeId("ext-n2")])

        r1 = FusionEngine().fuse(
            identity_slice=id_slice, external_slice=ext_slice,
        )
        r2 = FusionEngine().fuse(
            identity_slice=id_slice, external_slice=ext_slice,
        )

        assert len(r1.virtual_manifold.get_nodes()) == len(
            r2.virtual_manifold.get_nodes()
        )
        assert len(r1.bridge_edges) == len(r2.bridge_edges)
        # Bridge edge IDs are deterministic from endpoints
        if r1.bridge_edges:
            assert r1.bridge_edges[0].edge_id == r2.bridge_edges[0].edge_id


# ===================================================================
# Virtual Manifold Same-Schema
# ===================================================================

class TestVirtualManifoldSameSchema:
    def test_vm_has_all_collection_methods(self) -> None:
        vm = VirtualManifold(manifold_id=ManifoldId("test-vm"))
        assert hasattr(vm, "get_nodes")
        assert hasattr(vm, "get_edges")
        assert hasattr(vm, "get_chunks")
        assert hasattr(vm, "get_chunk_occurrences")
        assert hasattr(vm, "get_embeddings")
        assert hasattr(vm, "get_hierarchy")
        assert hasattr(vm, "get_metadata_entries")
        assert hasattr(vm, "get_provenance_entries")
        assert hasattr(vm, "get_node_chunk_bindings")
        assert hasattr(vm, "get_node_embedding_bindings")
        assert hasattr(vm, "get_node_hierarchy_bindings")
        assert hasattr(vm, "get_file_manifest")
        assert hasattr(vm, "get_project_manifest")
        # VM-specific
        assert hasattr(vm, "source_manifold_ids")
        assert hasattr(vm, "runtime_annotations")


# ===================================================================
# Projected vs Fusion-Created Objects
# ===================================================================

class TestProjectedVsBridgeDistinction:
    def test_bridge_edges_distinguishable(self, factory, store) -> None:
        """Bridge edges in VM have EdgeType.BRIDGE and source_manifold metadata."""
        id_m = _populate_identity_manifold(factory, store)
        ext_m = _populate_external_manifold(factory, store)

        id_slice = IdentityProjection(store=store).project_by_ids(
            id_m, [NodeId("id-n1"), NodeId("id-n2")],
        )
        ext_slice = ExternalProjection(store=store).project_by_ids(
            ext_m, [NodeId("ext-n1"), NodeId("ext-n2")],
        )
        result = FusionEngine().fuse(
            identity_slice=id_slice, external_slice=ext_slice,
        )
        vm = result.virtual_manifold

        bridge_edges = [
            e for e in vm.get_edges().values()
            if e.edge_type == EdgeType.BRIDGE
        ]
        projected_edges = [
            e for e in vm.get_edges().values()
            if e.edge_type != EdgeType.BRIDGE
        ]

        # Should have both bridge and projected edges
        assert len(bridge_edges) >= 1
        assert len(projected_edges) >= 1

        # Bridge edges carry source_manifold in properties
        for be in bridge_edges:
            assert "source_manifold" in be.properties
            assert "target_manifold" in be.properties

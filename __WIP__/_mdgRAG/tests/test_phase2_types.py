"""
Phase 2 Tests — core type construction, schema symmetry, and hashing.

Verifies:
    1. All core dataclasses can be instantiated with defaults
    2. Identity/external/virtual manifolds share the same base structure
    3. Evidence Bag can be constructed with node/edge/chunk refs
    4. Deterministic chunk hashing helper is stable
    5. Runtime state can hold manifold references cleanly
    6. Cross-layer bindings are explicit and constructible
"""

import pytest

from src.core.types.ids import (
    ManifoldId,
    NodeId,
    EdgeId,
    ChunkHash,
    EmbeddingId,
    HierarchyId,
    EvidenceBagId,
    FileManifestHash,
    ProjectRootHash,
    deterministic_hash,
    make_chunk_hash,
    make_legacy_chunk_hash,
)
from src.core.types.enums import (
    ManifoldRole,
    StorageMode,
    NodeType,
    EdgeType,
    ProvenanceStage,
    HydrationMode,
    EmbeddingMetricType,
    EmbeddingTargetKind,
)
from src.core.types.graph import (
    Node,
    Edge,
    Chunk,
    ChunkOccurrence,
    Embedding,
    HierarchyEntry,
    MetadataEntry,
)
from src.core.types.provenance import Provenance
from src.core.types.bindings import (
    NodeChunkBinding,
    NodeEmbeddingBinding,
    NodeHierarchyBinding,
)
from src.core.types.manifests import (
    FileManifest,
    FileManifestEntry,
    ProjectManifest,
    ProjectManifestEntry,
)
from src.core.types.runtime_state import RuntimeState, ModelBridgeState
from src.core.contracts.evidence_bag_contract import (
    EvidenceBag,
    ScoreAnnotation,
    TokenBudget,
    EvidenceBagTrace,
)
from src.core.contracts.manifold_contract import ManifoldMetadata
from src.core.contracts.projection_contract import (
    ProjectedSlice,
    ProjectionMetadata,
    QueryProjectionArtifact,
)
from src.core.contracts.fusion_contract import BridgeEdge, FusionResult, FusionAncestry
from src.core.contracts.hydration_contract import (
    HydrationInput,
    HydratedNode,
    HydratedEdge,
    HydratedBundle,
)
from src.core.contracts.model_bridge_contract import (
    EmbedRequest,
    EmbedResponse,
    SynthesisRequest,
    SynthesisResponse,
    ModelIdentity,
    TokenBudgetMetadata,
)
from src.core.manifolds.base_manifold import BaseManifold
from src.core.manifolds.identity_manifold import IdentityManifold
from src.core.manifolds.external_manifold import ExternalManifold
from src.core.manifolds.virtual_manifold import VirtualManifold


# ===================================================================
# 1. Core dataclass instantiation
# ===================================================================

class TestCoreTypeConstruction:
    """Every core dataclass must be constructible with minimal args."""

    def test_node(self) -> None:
        n = Node(
            node_id=NodeId("n1"),
            manifold_id=ManifoldId("m1"),
            node_type=NodeType.CHUNK,
        )
        assert n.node_id == "n1"
        assert n.node_type == NodeType.CHUNK

    def test_edge(self) -> None:
        e = Edge(
            edge_id=EdgeId("e1"),
            manifold_id=ManifoldId("m1"),
            from_node_id=NodeId("n1"),
            to_node_id=NodeId("n2"),
            edge_type=EdgeType.ADJACENT,
        )
        assert e.from_node_id == "n1"
        assert e.to_node_id == "n2"

    def test_chunk(self) -> None:
        c = Chunk(chunk_hash=ChunkHash("abc123"), chunk_text="hello world")
        assert c.char_length == 11
        assert c.byte_length == 11
        assert c.token_estimate > 0
        assert c.hash_algorithm == "sha256"

    def test_chunk_auto_fields(self) -> None:
        text = "This is a test with several words for token estimation"
        c = Chunk(chunk_hash=ChunkHash("x"), chunk_text=text)
        assert c.char_length == len(text)
        assert c.byte_length == len(text.encode("utf-8"))
        expected_tokens = int(len(text.split()) * 1.3 + 1)
        assert c.token_estimate == expected_tokens

    def test_chunk_occurrence(self) -> None:
        co = ChunkOccurrence(
            chunk_hash=ChunkHash("abc"),
            manifold_id=ManifoldId("m1"),
            source_path="src/app.py",
            chunk_index=3,
        )
        assert co.source_path == "src/app.py"
        assert co.chunk_index == 3

    def test_embedding(self) -> None:
        emb = Embedding(
            embedding_id=EmbeddingId("emb1"),
            target_kind=EmbeddingTargetKind.CHUNK,
            target_id="chunk_abc",
            model_name="mxbai-embed-large",
            dimensions=1024,
        )
        assert emb.dimensions == 1024
        assert emb.is_normalized is True

    def test_hierarchy_entry(self) -> None:
        h = HierarchyEntry(
            hierarchy_id=HierarchyId("h1"),
            manifold_id=ManifoldId("m1"),
            node_id=NodeId("n1"),
            depth=2,
        )
        assert h.depth == 2

    def test_metadata_entry(self) -> None:
        m = MetadataEntry(
            owner_kind="node",
            owner_id="n1",
            manifold_id=ManifoldId("m1"),
            key="language",
            value="python",
        )
        assert m.key == "language"

    def test_provenance(self) -> None:
        p = Provenance(
            owner_kind="chunk",
            owner_id="c1",
            stage=ProvenanceStage.CHUNKING,
            parser_name="python_ast",
        )
        assert p.stage == ProvenanceStage.CHUNKING

    def test_node_chunk_binding(self) -> None:
        b = NodeChunkBinding(
            node_id=NodeId("n1"),
            chunk_hash=ChunkHash("c1"),
            manifold_id=ManifoldId("m1"),
        )
        assert b.binding_role == "contains"

    def test_node_embedding_binding(self) -> None:
        b = NodeEmbeddingBinding(
            node_id=NodeId("n1"),
            embedding_id=EmbeddingId("e1"),
            manifold_id=ManifoldId("m1"),
        )
        assert b.binding_role == "primary"

    def test_node_hierarchy_binding(self) -> None:
        b = NodeHierarchyBinding(
            node_id=NodeId("n1"),
            hierarchy_id=HierarchyId("h1"),
            manifold_id=ManifoldId("m1"),
        )
        assert b.binding_role == "member"

    def test_file_manifest_entry(self) -> None:
        e = FileManifestEntry(
            file_hash=FileManifestHash("fh1"),
            path="src/app.py",
            size_bytes=1024,
        )
        assert e.path == "src/app.py"

    def test_file_manifest(self) -> None:
        fm = FileManifest(manifest_hash=FileManifestHash("mh1"), total_files=5)
        assert fm.total_files == 5

    def test_project_manifest_entry(self) -> None:
        pe = ProjectManifestEntry(entry_id="pe1", vfs_path="/src/app.py")
        assert pe.vfs_path == "/src/app.py"

    def test_project_manifest(self) -> None:
        pm = ProjectManifest(
            project_root_hash=ProjectRootHash("prh1"),
            project_id="test-project",
            name="Test Project",
        )
        assert pm.project_id == "test-project"


# ===================================================================
# 2. Same-schema manifold symmetry
# ===================================================================

class TestManifoldSymmetry:
    """Identity, external, and virtual manifolds share identical structure."""

    @pytest.fixture
    def manifolds(self):
        return [
            IdentityManifold(ManifoldId("identity-1")),
            ExternalManifold(ManifoldId("external-1")),
            VirtualManifold(ManifoldId("virtual-1")),
        ]

    def test_all_have_same_collection_methods(self, manifolds) -> None:
        """Every manifold exposes the same set of collection methods."""
        required_methods = [
            "get_metadata",
            "get_nodes",
            "get_edges",
            "get_chunks",
            "get_chunk_occurrences",
            "get_embeddings",
            "get_hierarchy",
            "get_metadata_entries",
            "get_provenance_entries",
            "get_node_chunk_bindings",
            "get_node_embedding_bindings",
            "get_node_hierarchy_bindings",
            "get_file_manifest",
            "get_project_manifest",
        ]
        for m in manifolds:
            for method_name in required_methods:
                assert hasattr(m, method_name), (
                    f"{type(m).__name__} missing {method_name}"
                )

    def test_all_collections_start_empty(self, manifolds) -> None:
        """All collections are empty at creation."""
        for m in manifolds:
            assert len(m.get_nodes()) == 0
            assert len(m.get_edges()) == 0
            assert len(m.get_chunks()) == 0
            assert len(m.get_chunk_occurrences()) == 0
            assert len(m.get_embeddings()) == 0
            assert len(m.get_hierarchy()) == 0
            assert len(m.get_metadata_entries()) == 0
            assert len(m.get_provenance_entries()) == 0
            assert len(m.get_node_chunk_bindings()) == 0
            assert len(m.get_node_embedding_bindings()) == 0
            assert len(m.get_node_hierarchy_bindings()) == 0
            assert m.get_file_manifest() is None
            assert m.get_project_manifest() is None

    def test_roles_are_distinct(self, manifolds) -> None:
        """Each manifold reports its correct role."""
        identity, external, virtual = manifolds
        assert identity.get_metadata().role == ManifoldRole.IDENTITY
        assert external.get_metadata().role == ManifoldRole.EXTERNAL
        assert virtual.get_metadata().role == ManifoldRole.VIRTUAL

    def test_virtual_is_ephemeral(self, manifolds) -> None:
        """Virtual manifold uses ephemeral storage mode."""
        _, _, virtual = manifolds
        assert virtual.get_metadata().storage_mode == StorageMode.PYTHON_RAM

    def test_virtual_has_source_tracking(self) -> None:
        """Virtual manifold tracks source manifold IDs."""
        vm = VirtualManifold(ManifoldId("vm-1"))
        assert vm.source_manifold_ids == []
        assert vm.runtime_annotations == {}

    def test_manifold_ids_preserved(self, manifolds) -> None:
        """Each manifold reports its assigned ID."""
        identity, external, virtual = manifolds
        assert identity.get_metadata().manifold_id == "identity-1"
        assert external.get_metadata().manifold_id == "external-1"
        assert virtual.get_metadata().manifold_id == "virtual-1"

    def test_collections_return_typed_dicts(self, manifolds) -> None:
        """Collection getters return dicts (not some other container)."""
        for m in manifolds:
            assert isinstance(m.get_nodes(), dict)
            assert isinstance(m.get_edges(), dict)
            assert isinstance(m.get_chunks(), dict)
            assert isinstance(m.get_embeddings(), dict)
            assert isinstance(m.get_hierarchy(), dict)


# ===================================================================
# 3. Evidence Bag construction
# ===================================================================

class TestEvidenceBag:
    """Evidence Bag must be constructible as a graph-native object."""

    def test_minimal_construction(self) -> None:
        bag = EvidenceBag(bag_id=EvidenceBagId("eb-1"))
        assert bag.bag_id == "eb-1"
        assert bag.node_ids == []
        assert bag.edge_ids == []

    def test_with_node_edge_chunk_refs(self) -> None:
        bag = EvidenceBag(
            bag_id=EvidenceBagId("eb-2"),
            node_ids=[NodeId("n1"), NodeId("n2"), NodeId("n3")],
            edge_ids=[EdgeId("e1"), EdgeId("e2")],
            chunk_refs={
                NodeId("n1"): [ChunkHash("ch1")],
                NodeId("n2"): [ChunkHash("ch2"), ChunkHash("ch3")],
            },
        )
        assert len(bag.node_ids) == 3
        assert len(bag.edge_ids) == 2
        assert len(bag.chunk_refs) == 2
        assert len(bag.chunk_refs[NodeId("n2")]) == 2

    def test_with_scores(self) -> None:
        bag = EvidenceBag(
            bag_id=EvidenceBagId("eb-3"),
            node_ids=[NodeId("n1")],
            scores={
                NodeId("n1"): ScoreAnnotation(
                    structural=0.7,
                    semantic=0.9,
                    gravity=0.82,
                ),
            },
        )
        score = bag.scores[NodeId("n1")]
        assert score.gravity == 0.82

    def test_with_token_budget(self) -> None:
        bag = EvidenceBag(
            bag_id=EvidenceBagId("eb-4"),
            token_budget=TokenBudget(max_tokens=4000, used_tokens=3200),
        )
        assert bag.token_budget.max_tokens == 4000
        assert bag.token_budget.used_tokens == 3200

    def test_with_trace(self) -> None:
        bag = EvidenceBag(
            bag_id=EvidenceBagId("eb-5"),
            trace=EvidenceBagTrace(
                extraction_strategy="ego_graph",
                hop_depth=2,
                seed_node_count=5,
            ),
        )
        assert bag.trace.hop_depth == 2


# ===================================================================
# 4. Deterministic hashing
# ===================================================================

class TestDeterministicHashing:
    """SHA256 hashing helper must be stable and reproducible."""

    def test_same_input_same_output(self) -> None:
        h1 = deterministic_hash("hello world")
        h2 = deterministic_hash("hello world")
        assert h1 == h2

    def test_different_input_different_output(self) -> None:
        h1 = deterministic_hash("hello")
        h2 = deterministic_hash("world")
        assert h1 != h2

    def test_returns_64_char_hex(self) -> None:
        h = deterministic_hash("test")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_make_chunk_hash_is_content_addressed(self) -> None:
        """make_chunk_hash hashes the content text, not location."""
        text = "def main():\n    pass\n"
        ch = make_chunk_hash(text)
        expected = deterministic_hash(text)
        assert ch == expected

    def test_make_chunk_hash_deterministic(self) -> None:
        ch1 = make_chunk_hash("hello world")
        ch2 = make_chunk_hash("hello world")
        assert ch1 == ch2

    def test_make_chunk_hash_varies_by_content(self) -> None:
        ch0 = make_chunk_hash("alpha")
        ch1 = make_chunk_hash("beta")
        assert ch0 != ch1

    def test_same_content_same_hash_regardless_of_origin(self) -> None:
        """Two chunks from different files but same text get same hash."""
        text = "shared content"
        ch = make_chunk_hash(text)
        assert ch == make_chunk_hash(text)

    def test_make_legacy_chunk_hash_matches_location_convention(self) -> None:
        """Legacy helper: SHA256(path:index) for migration compatibility."""
        ch = make_legacy_chunk_hash("src/app.py", 0)
        expected = deterministic_hash("src/app.py:0")
        assert ch == expected

    def test_make_legacy_chunk_hash_varies_by_index(self) -> None:
        ch0 = make_legacy_chunk_hash("file.py", 0)
        ch1 = make_legacy_chunk_hash("file.py", 1)
        assert ch0 != ch1


# ===================================================================
# 5. Runtime state
# ===================================================================

class TestRuntimeState:
    """Runtime state must hold manifold references cleanly."""

    def test_default_construction(self) -> None:
        state = RuntimeState()
        assert state.identity_manifold_id is None
        assert state.external_manifold_id is None
        assert state.virtual_manifold_id is None
        assert state.current_query is None
        assert state.current_evidence_bag_id is None

    def test_with_manifold_refs(self) -> None:
        state = RuntimeState(
            identity_manifold_id=ManifoldId("id-1"),
            external_manifold_id=ManifoldId("ext-1"),
            virtual_manifold_id=ManifoldId("virt-1"),
        )
        assert state.identity_manifold_id == "id-1"
        assert state.external_manifold_id == "ext-1"
        assert state.virtual_manifold_id == "virt-1"

    def test_with_query_and_evidence(self) -> None:
        state = RuntimeState(
            current_query="What is gravity scoring?",
            current_evidence_bag_id=EvidenceBagId("eb-1"),
        )
        assert state.current_query == "What is gravity scoring?"
        assert state.current_evidence_bag_id == "eb-1"

    def test_model_bridge_state(self) -> None:
        state = RuntimeState(
            model_bridge_state=ModelBridgeState(
                active_model="mxbai-embed-large",
                embedding_dimensions=1024,
            ),
        )
        assert state.model_bridge_state.active_model == "mxbai-embed-large"
        assert state.model_bridge_state.embedding_dimensions == 1024


# ===================================================================
# 6. Contract data structures
# ===================================================================

class TestContractStructures:
    """Contract-level data structures are constructible."""

    def test_manifold_metadata(self) -> None:
        mm = ManifoldMetadata(
            manifold_id=ManifoldId("m1"),
            role=ManifoldRole.EXTERNAL,
            storage_mode=StorageMode.SQLITE_DISK,
        )
        assert mm.schema_version == "0.1.0"

    def test_projection_metadata(self) -> None:
        pm = ProjectionMetadata(
            source_manifold_id=ManifoldId("ext-1"),
            source_kind=__import__(
                "src.core.types.enums", fromlist=["ProjectionSourceKind"]
            ).ProjectionSourceKind.EXTERNAL,
        )
        assert pm.source_manifold_id == "ext-1"

    def test_projected_slice(self) -> None:
        ps = ProjectedSlice(
            metadata=ProjectionMetadata(
                source_manifold_id=ManifoldId("id-1"),
                source_kind=__import__(
                    "src.core.types.enums", fromlist=["ProjectionSourceKind"]
                ).ProjectionSourceKind.IDENTITY,
            ),
            node_ids=[NodeId("n1"), NodeId("n2")],
            edge_ids=[EdgeId("e1")],
        )
        assert len(ps.node_ids) == 2

    def test_query_projection_artifact(self) -> None:
        qa = QueryProjectionArtifact(
            raw_query="explain gravity scoring",
            parsed_intent={"topic": "gravity_scoring"},
        )
        assert qa.raw_query == "explain gravity scoring"

    def test_bridge_edge(self) -> None:
        be = BridgeEdge(
            edge_id=EdgeId("bridge-1"),
            source_node=NodeId("id-n1"),
            target_node=NodeId("ext-n1"),
            source_manifold=ManifoldId("identity-1"),
            target_manifold=ManifoldId("external-1"),
        )
        assert be.edge_type == EdgeType.BRIDGE

    def test_hydration_input(self) -> None:
        hi = HydrationInput(
            evidence_bag=None,
            source_manifold_ids=[ManifoldId("ext-1")],
            mode=HydrationMode.FULL,
        )
        assert hi.mode == HydrationMode.FULL

    def test_hydrated_bundle(self) -> None:
        hb = HydratedBundle(
            nodes=[
                HydratedNode(node_id=NodeId("n1"), content="hello", token_estimate=2),
            ],
            edges=[
                HydratedEdge(
                    edge_id=EdgeId("e1"),
                    source_id=NodeId("n1"),
                    target_id=NodeId("n2"),
                    relation="ADJACENT",
                ),
            ],
            total_tokens=2,
        )
        assert len(hb.nodes) == 1
        assert hb.topology_preserved is True

    def test_embed_request(self) -> None:
        er = EmbedRequest(texts=["hello", "world"], model="mxbai-embed-large")
        assert len(er.texts) == 2

    def test_synthesis_request(self) -> None:
        sr = SynthesisRequest(
            evidence_context="context here",
            query="what is this?",
            model="llama3",
        )
        assert sr.temperature == 0.0

    def test_model_identity(self) -> None:
        mi = ModelIdentity(
            model_name="mxbai-embed-large",
            embedding_dimensions=1024,
        )
        assert mi.embedding_dimensions == 1024

    def test_token_budget_metadata(self) -> None:
        tb = TokenBudgetMetadata(
            context_window=32768,
            evidence_budget=8000,
            synthesis_budget=4096,
        )
        assert tb.context_window == 32768

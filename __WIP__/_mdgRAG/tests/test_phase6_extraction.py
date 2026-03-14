"""
Phase 6 Tests — Evidence Bag Extraction.

Tests for:
    - ExtractionConfig defaults and overrides
    - Node ranking by gravity with deterministic tie-breaking
    - Seed selection from ranked nodes
    - BFS expansion with hop limits
    - Chunk and hierarchy binding collection
    - Token budget enforcement (greedy)
    - Hard limits (max_nodes, max_edges, max_chunks)
    - Evidence bag ID determinism
    - Trace metadata and provenance
    - End-to-end extraction pipeline
    - Backward compatibility imports
"""

import dataclasses

import pytest

from src.core.types.ids import (
    ChunkHash,
    EdgeId,
    EvidenceBagId,
    HierarchyId,
    ManifoldId,
    NodeId,
)
from src.core.types.enums import (
    EdgeType,
    ManifoldRole,
    NodeType,
    ProvenanceStage,
    ProvenanceRelationOrigin,
)
from src.core.types.graph import Chunk, Edge, HierarchyEntry, Node
from src.core.types.bindings import NodeChunkBinding, NodeHierarchyBinding
from src.core.manifolds.virtual_manifold import VirtualManifold
from src.core.math.annotator import annotate_scores
from src.core.contracts.evidence_bag_contract import ScoreAnnotation

from src.core.extraction.extractor import (
    ExtractionConfig,
    extract_evidence_bag,
)


# ---------------------------------------------------------------------------
# Helper: build a scored VirtualManifold
# ---------------------------------------------------------------------------

def _make_scored_vm(
    node_ids: list,
    edges: list = None,
    chunks: dict = None,
    chunk_bindings: list = None,
    hierarchy_entries: list = None,
    hierarchy_bindings: list = None,
    gravity_scores: dict = None,
    manifold_id: str = "vm-extract-test",
) -> VirtualManifold:
    """
    Build a VirtualManifold with nodes, edges, chunks, bindings, and scores.

    Args:
        node_ids: List of string node IDs.
        edges: List of (from_id, to_id) tuples.
        chunks: Dict of chunk_hash_str -> chunk_text.
        chunk_bindings: List of (node_id_str, chunk_hash_str, ordinal) tuples.
        hierarchy_entries: List of hierarchy_id strings.
        hierarchy_bindings: List of (node_id_str, hierarchy_id_str) tuples.
        gravity_scores: Dict of node_id_str -> gravity float.
        manifold_id: Manifold ID string.

    Returns:
        Populated and scored VirtualManifold.
    """
    mid = ManifoldId(manifold_id)
    vm = VirtualManifold(mid)

    # Add nodes
    for nid_str in node_ids:
        nid = NodeId(nid_str)
        vm.get_nodes()[nid] = Node(
            node_id=nid,
            manifold_id=mid,
            node_type=NodeType.CONCEPT,
            label=nid_str,
        )

    # Add edges
    if edges:
        for i, (src, tgt) in enumerate(edges):
            eid = EdgeId(f"edge-{i}")
            vm.get_edges()[eid] = Edge(
                edge_id=eid,
                manifold_id=mid,
                from_node_id=NodeId(src),
                to_node_id=NodeId(tgt),
                edge_type=EdgeType.SEMANTIC,
            )

    # Add chunks
    if chunks:
        for ch_str, ch_text in chunks.items():
            ch = ChunkHash(ch_str)
            vm.get_chunks()[ch] = Chunk(
                chunk_hash=ch,
                chunk_text=ch_text,
            )

    # Add chunk bindings
    if chunk_bindings:
        for nid_str, ch_str, ordinal in chunk_bindings:
            vm.get_node_chunk_bindings().append(NodeChunkBinding(
                node_id=NodeId(nid_str),
                chunk_hash=ChunkHash(ch_str),
                manifold_id=mid,
                ordinal=ordinal,
            ))

    # Add hierarchy entries
    if hierarchy_entries:
        for hid_str in hierarchy_entries:
            hid = HierarchyId(hid_str)
            # Pick first node as the owner (simplistic for testing)
            vm.get_hierarchy()[hid] = HierarchyEntry(
                hierarchy_id=hid,
                manifold_id=mid,
                node_id=NodeId(node_ids[0]) if node_ids else NodeId(""),
            )

    # Add hierarchy bindings
    if hierarchy_bindings:
        for nid_str, hid_str in hierarchy_bindings:
            vm.get_node_hierarchy_bindings().append(NodeHierarchyBinding(
                node_id=NodeId(nid_str),
                hierarchy_id=HierarchyId(hid_str),
                manifold_id=mid,
            ))

    # Annotate gravity scores
    if gravity_scores:
        structural = {}
        semantic = {}
        gravity = {}
        for nid_str, g in gravity_scores.items():
            nid = NodeId(nid_str)
            structural[nid] = g  # Simplification: use gravity as structural
            semantic[nid] = 0.0
            gravity[nid] = g
        annotate_scores(vm, structural, semantic, gravity)

    return vm


# ===========================================================================
# TestExtractionConfig
# ===========================================================================

class TestExtractionConfig:
    """Tests for ExtractionConfig dataclass."""

    def test_default_values(self):
        config = ExtractionConfig()
        assert config.max_seed_nodes == 3
        assert config.max_hops == 1
        assert config.token_budget == 2048
        assert config.max_nodes == 25
        assert config.max_edges == 40
        assert config.max_chunks == 12

    def test_custom_values(self):
        config = ExtractionConfig(
            max_seed_nodes=5,
            max_hops=2,
            token_budget=4096,
            max_nodes=10,
            max_edges=20,
            max_chunks=8,
        )
        assert config.max_seed_nodes == 5
        assert config.max_hops == 2
        assert config.token_budget == 4096

    def test_is_dataclass(self):
        assert dataclasses.is_dataclass(ExtractionConfig)


# ===========================================================================
# TestNodeRanking
# ===========================================================================

class TestNodeRanking:
    """Tests for node ranking by gravity."""

    def test_nodes_ranked_by_gravity_descending(self):
        vm = _make_scored_vm(
            ["A", "B", "C"],
            gravity_scores={"A": 0.3, "B": 0.9, "C": 0.6},
        )
        config = ExtractionConfig(max_seed_nodes=3, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        # B (0.9) should come first, then C (0.6), then A (0.3)
        assert bag.node_ids[0] == NodeId("B")
        assert bag.node_ids[1] == NodeId("C")
        assert bag.node_ids[2] == NodeId("A")

    def test_tie_breaking_by_node_id(self):
        vm = _make_scored_vm(
            ["X", "A", "M"],
            gravity_scores={"X": 0.5, "A": 0.5, "M": 0.5},
        )
        config = ExtractionConfig(max_seed_nodes=3, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        # All equal gravity — tie-break by ascending node_id
        assert bag.node_ids == [NodeId("A"), NodeId("M"), NodeId("X")]

    def test_unscored_nodes_get_zero(self):
        vm = _make_scored_vm(
            ["A", "B", "C"],
            gravity_scores={"A": 0.8},  # B and C unscored
        )
        config = ExtractionConfig(max_seed_nodes=3, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        # A first (0.8), then B and C (0.0, tie-broken by ID)
        assert bag.node_ids[0] == NodeId("A")
        assert bag.node_ids[1] == NodeId("B")
        assert bag.node_ids[2] == NodeId("C")

    def test_empty_vm_returns_empty(self):
        vm = _make_scored_vm([])
        bag = extract_evidence_bag(vm)
        assert bag.node_ids == []
        assert bag.edge_ids == []
        assert bag.chunk_refs == {}


# ===========================================================================
# TestSeedSelection
# ===========================================================================

class TestSeedSelection:
    """Tests for seed selection from ranked nodes."""

    def test_selects_top_n_seeds(self):
        vm = _make_scored_vm(
            ["A", "B", "C", "D", "E"],
            gravity_scores={"A": 0.1, "B": 0.5, "C": 0.9, "D": 0.3, "E": 0.7},
        )
        # max_seed=3, max_hops=0 → only seeds included
        config = ExtractionConfig(max_seed_nodes=3, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        # Top 3: C(0.9), E(0.7), B(0.5)
        assert len(bag.node_ids) == 3
        assert NodeId("C") in bag.node_ids
        assert NodeId("E") in bag.node_ids
        assert NodeId("B") in bag.node_ids

    def test_fewer_nodes_than_seeds(self):
        vm = _make_scored_vm(
            ["A", "B"],
            gravity_scores={"A": 0.5, "B": 0.8},
        )
        config = ExtractionConfig(max_seed_nodes=5, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        assert len(bag.node_ids) == 2

    def test_seed_order_is_gravity_descending(self):
        vm = _make_scored_vm(
            ["A", "B", "C"],
            gravity_scores={"A": 0.1, "B": 0.9, "C": 0.5},
        )
        config = ExtractionConfig(max_seed_nodes=3, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        assert bag.node_ids[0] == NodeId("B")


# ===========================================================================
# TestBFSExpansion
# ===========================================================================

class TestBFSExpansion:
    """Tests for BFS expansion from seeds."""

    def test_hop_zero_returns_seeds_only(self):
        vm = _make_scored_vm(
            ["A", "B", "C"],
            edges=[("A", "B"), ("B", "C")],
            gravity_scores={"A": 0.9, "B": 0.1, "C": 0.1},
        )
        config = ExtractionConfig(max_seed_nodes=1, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        # Only seed A, no expansion
        assert NodeId("A") in bag.node_ids
        assert NodeId("B") not in bag.node_ids
        assert NodeId("C") not in bag.node_ids

    def test_hop_one_includes_neighbors(self):
        vm = _make_scored_vm(
            ["A", "B", "C", "D"],
            edges=[("A", "B"), ("B", "C"), ("C", "D")],
            gravity_scores={"A": 0.9, "B": 0.1, "C": 0.1, "D": 0.1},
        )
        config = ExtractionConfig(max_seed_nodes=1, max_hops=1)
        bag = extract_evidence_bag(vm, config)
        # Seed A + neighbor B (1-hop)
        assert NodeId("A") in bag.node_ids
        assert NodeId("B") in bag.node_ids
        # C is 2-hops away, D is 3-hops — excluded
        assert NodeId("C") not in bag.node_ids
        assert NodeId("D") not in bag.node_ids

    def test_undirected_expansion(self):
        """BFS treats directed edges as undirected."""
        vm = _make_scored_vm(
            ["A", "B"],
            edges=[("B", "A")],  # Edge points TO A, but A should still reach B
            gravity_scores={"A": 0.9, "B": 0.1},
        )
        config = ExtractionConfig(max_seed_nodes=1, max_hops=1)
        bag = extract_evidence_bag(vm, config)
        assert NodeId("A") in bag.node_ids
        assert NodeId("B") in bag.node_ids

    def test_disconnected_nodes_not_reached(self):
        vm = _make_scored_vm(
            ["A", "B", "C", "D"],
            edges=[("A", "B")],  # C and D are disconnected
            gravity_scores={"A": 0.9, "B": 0.1, "C": 0.05, "D": 0.05},
        )
        config = ExtractionConfig(max_seed_nodes=1, max_hops=1)
        bag = extract_evidence_bag(vm, config)
        assert NodeId("A") in bag.node_ids
        assert NodeId("B") in bag.node_ids
        assert NodeId("C") not in bag.node_ids
        assert NodeId("D") not in bag.node_ids


# ===========================================================================
# TestChunkCollection
# ===========================================================================

class TestChunkCollection:
    """Tests for chunk binding collection."""

    def test_chunks_collected_by_binding_ordinal(self):
        vm = _make_scored_vm(
            ["A"],
            chunks={"ch1": "first chunk text", "ch2": "second chunk text"},
            chunk_bindings=[("A", "ch1", 0), ("A", "ch2", 1)],
            gravity_scores={"A": 0.9},
        )
        config = ExtractionConfig(max_seed_nodes=1, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        assert NodeId("A") in bag.chunk_refs
        assert bag.chunk_refs[NodeId("A")] == [ChunkHash("ch1"), ChunkHash("ch2")]

    def test_node_without_chunks(self):
        vm = _make_scored_vm(
            ["A"],
            gravity_scores={"A": 0.9},
        )
        config = ExtractionConfig(max_seed_nodes=1, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        # Node included but no chunk refs
        assert NodeId("A") in bag.node_ids
        # chunk_refs may be empty dict or not have the key
        assert bag.chunk_refs.get(NodeId("A"), []) == []

    def test_multiple_nodes_get_separate_chunks(self):
        vm = _make_scored_vm(
            ["A", "B"],
            edges=[("A", "B")],
            chunks={"chA": "chunk for A", "chB": "chunk for B"},
            chunk_bindings=[("A", "chA", 0), ("B", "chB", 0)],
            gravity_scores={"A": 0.9, "B": 0.8},
        )
        config = ExtractionConfig(max_seed_nodes=2, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        assert bag.chunk_refs[NodeId("A")] == [ChunkHash("chA")]
        assert bag.chunk_refs[NodeId("B")] == [ChunkHash("chB")]


# ===========================================================================
# TestHierarchyCollection
# ===========================================================================

class TestHierarchyCollection:
    """Tests for hierarchy binding collection."""

    def test_hierarchy_refs_collected(self):
        vm = _make_scored_vm(
            ["A"],
            hierarchy_entries=["h1", "h2"],
            hierarchy_bindings=[("A", "h1"), ("A", "h2")],
            gravity_scores={"A": 0.9},
        )
        config = ExtractionConfig(max_seed_nodes=1, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        assert NodeId("A") in bag.hierarchy_refs
        assert sorted(bag.hierarchy_refs[NodeId("A")]) == [
            HierarchyId("h1"), HierarchyId("h2"),
        ]

    def test_node_without_hierarchy(self):
        vm = _make_scored_vm(
            ["A"],
            gravity_scores={"A": 0.9},
        )
        config = ExtractionConfig(max_seed_nodes=1, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        # No hierarchy refs for this node
        assert NodeId("A") not in bag.hierarchy_refs


# ===========================================================================
# TestTokenBudget
# ===========================================================================

class TestTokenBudget:
    """Tests for token budget enforcement."""

    def test_all_nodes_fit_within_budget(self):
        vm = _make_scored_vm(
            ["A", "B"],
            chunks={"chA": "short", "chB": "short"},
            chunk_bindings=[("A", "chA", 0), ("B", "chB", 0)],
            gravity_scores={"A": 0.9, "B": 0.8},
        )
        config = ExtractionConfig(max_seed_nodes=2, max_hops=0, token_budget=5000)
        bag = extract_evidence_bag(vm, config)
        assert len(bag.node_ids) == 2
        assert bag.token_budget.used_tokens < config.token_budget

    def test_budget_exceeded_skips_node(self):
        # Create chunks with known token estimates
        # "short" has few tokens, large text has many
        large_text = " ".join(["word"] * 500)  # ~651 tokens estimate
        vm = _make_scored_vm(
            ["A", "B", "C"],
            chunks={"chA": large_text, "chB": large_text, "chC": "tiny"},
            chunk_bindings=[("A", "chA", 0), ("B", "chB", 0), ("C", "chC", 0)],
            gravity_scores={"A": 0.9, "B": 0.7, "C": 0.5},
        )
        # Budget tight enough for A's chunk but not A+B
        chunk_a_tokens = vm.get_chunks()[ChunkHash("chA")].token_estimate
        config = ExtractionConfig(
            max_seed_nodes=3,
            max_hops=0,
            token_budget=chunk_a_tokens + 50,  # Room for A and C but not B
        )
        bag = extract_evidence_bag(vm, config)
        # A (highest gravity, fits) should be in
        assert NodeId("A") in bag.node_ids
        # C (small, fits) should be in despite lower gravity
        assert NodeId("C") in bag.node_ids

    def test_greedy_order_is_gravity(self):
        """Highest gravity nodes should be included first."""
        vm = _make_scored_vm(
            ["A", "B", "C"],
            chunks={"chA": "some text", "chB": "some text", "chC": "some text"},
            chunk_bindings=[("A", "chA", 0), ("B", "chB", 0), ("C", "chC", 0)],
            gravity_scores={"A": 0.3, "B": 0.9, "C": 0.6},
        )
        config = ExtractionConfig(max_seed_nodes=3, max_hops=0)
        bag = extract_evidence_bag(vm, config)
        # B should come first (highest gravity)
        assert bag.node_ids[0] == NodeId("B")

    def test_zero_budget_includes_chunkless_nodes(self):
        """With zero budget, nodes without chunks can still be included."""
        vm = _make_scored_vm(
            ["A", "B"],
            gravity_scores={"A": 0.9, "B": 0.8},
        )
        config = ExtractionConfig(max_seed_nodes=2, max_hops=0, token_budget=0)
        bag = extract_evidence_bag(vm, config)
        # Nodes have no chunks, zero cost — should be included
        assert len(bag.node_ids) == 2

    def test_budget_tracks_used_and_remaining(self):
        vm = _make_scored_vm(
            ["A"],
            chunks={"chA": "hello world test"},
            chunk_bindings=[("A", "chA", 0)],
            gravity_scores={"A": 0.9},
        )
        config = ExtractionConfig(max_seed_nodes=1, max_hops=0, token_budget=5000)
        bag = extract_evidence_bag(vm, config)
        assert bag.token_budget.max_tokens == 5000
        assert bag.token_budget.used_tokens > 0
        assert bag.token_budget.remaining_tokens == 5000 - bag.token_budget.used_tokens


# ===========================================================================
# TestHardLimits
# ===========================================================================

class TestHardLimits:
    """Tests for hard limit enforcement."""

    def test_max_nodes_enforced(self):
        vm = _make_scored_vm(
            [f"N{i}" for i in range(10)],
            gravity_scores={f"N{i}": 0.5 for i in range(10)},
        )
        config = ExtractionConfig(max_seed_nodes=10, max_hops=0, max_nodes=3)
        bag = extract_evidence_bag(vm, config)
        assert len(bag.node_ids) <= 3

    def test_max_edges_enforced(self):
        # Create a fully connected graph with many edges
        nodes = ["A", "B", "C", "D"]
        edges = [(a, b) for a in nodes for b in nodes if a != b]
        vm = _make_scored_vm(
            nodes,
            edges=edges,
            gravity_scores={n: 0.8 for n in nodes},
        )
        config = ExtractionConfig(max_seed_nodes=4, max_hops=0, max_edges=2)
        bag = extract_evidence_bag(vm, config)
        assert len(bag.edge_ids) <= 2

    def test_max_chunks_enforced(self):
        vm = _make_scored_vm(
            ["A", "B", "C"],
            chunks={
                "ch1": "text one", "ch2": "text two", "ch3": "text three",
                "ch4": "text four", "ch5": "text five",
            },
            chunk_bindings=[
                ("A", "ch1", 0), ("A", "ch2", 1),
                ("B", "ch3", 0), ("B", "ch4", 1),
                ("C", "ch5", 0),
            ],
            gravity_scores={"A": 0.9, "B": 0.7, "C": 0.5},
        )
        config = ExtractionConfig(
            max_seed_nodes=3, max_hops=0, max_chunks=3, token_budget=50000,
        )
        bag = extract_evidence_bag(vm, config)
        total_chunks = sum(len(chs) for chs in bag.chunk_refs.values())
        assert total_chunks <= 3


# ===========================================================================
# TestBagId
# ===========================================================================

class TestBagId:
    """Tests for evidence bag ID determinism."""

    def test_bag_id_is_deterministic(self):
        vm = _make_scored_vm(
            ["A", "B", "C"],
            gravity_scores={"A": 0.9, "B": 0.5, "C": 0.3},
        )
        config = ExtractionConfig(max_seed_nodes=3, max_hops=0)
        bag1 = extract_evidence_bag(vm, config)
        bag2 = extract_evidence_bag(vm, config)
        assert bag1.bag_id == bag2.bag_id

    def test_different_nodes_different_id(self):
        vm = _make_scored_vm(
            ["A", "B", "C", "D"],
            gravity_scores={"A": 0.9, "B": 0.8, "C": 0.7, "D": 0.6},
        )
        bag1 = extract_evidence_bag(vm, ExtractionConfig(max_seed_nodes=2, max_hops=0))
        bag2 = extract_evidence_bag(vm, ExtractionConfig(max_seed_nodes=4, max_hops=0))
        assert bag1.bag_id != bag2.bag_id

    def test_different_manifold_id_different_bag_id(self):
        vm1 = _make_scored_vm(["A"], gravity_scores={"A": 0.9}, manifold_id="vm-1")
        vm2 = _make_scored_vm(["A"], gravity_scores={"A": 0.9}, manifold_id="vm-2")
        config = ExtractionConfig(max_seed_nodes=1, max_hops=0)
        bag1 = extract_evidence_bag(vm1, config)
        bag2 = extract_evidence_bag(vm2, config)
        assert bag1.bag_id != bag2.bag_id


# ===========================================================================
# TestTrace
# ===========================================================================

class TestTrace:
    """Tests for EvidenceBagTrace metadata."""

    def test_trace_fields_populated(self):
        vm = _make_scored_vm(
            ["A", "B", "C", "D"],
            edges=[("A", "B"), ("B", "C")],
            gravity_scores={"A": 0.9, "B": 0.7, "C": 0.5, "D": 0.1},
        )
        config = ExtractionConfig(max_seed_nodes=2, max_hops=1)
        bag = extract_evidence_bag(vm, config)
        assert bag.trace.extraction_strategy == "gravity_greedy"
        assert bag.trace.hop_depth == 1
        assert bag.trace.seed_node_count == 2
        assert bag.trace.total_candidates > 0
        assert bag.trace.selected_count == len(bag.node_ids)
        assert bag.trace.source_virtual_manifold_id == ManifoldId("vm-extract-test")

    def test_trace_parameters_match_config(self):
        config = ExtractionConfig(
            max_seed_nodes=5,
            max_hops=2,
            token_budget=4096,
            max_nodes=10,
            max_edges=20,
            max_chunks=8,
        )
        vm = _make_scored_vm(["A"], gravity_scores={"A": 0.9})
        bag = extract_evidence_bag(vm, config)
        params = bag.trace.parameters
        assert params["max_seed_nodes"] == 5
        assert params["max_hops"] == 2
        assert params["token_budget"] == 4096
        assert params["max_nodes"] == 10
        assert params["max_edges"] == 20
        assert params["max_chunks"] == 8


# ===========================================================================
# TestProvenance
# ===========================================================================

class TestProvenance:
    """Tests for extraction provenance records."""

    def test_provenance_fields(self):
        vm = _make_scored_vm(["A"], gravity_scores={"A": 0.9})
        bag = extract_evidence_bag(vm)
        assert len(bag.provenance) == 1
        prov = bag.provenance[0]
        assert prov.owner_kind == "evidence_bag"
        assert prov.owner_id == bag.bag_id
        assert prov.source_manifold_id == ManifoldId("vm-extract-test")
        assert prov.stage == ProvenanceStage.EXTRACTION
        assert prov.relation_origin == ProvenanceRelationOrigin.COMPUTED

    def test_provenance_list_has_one_entry(self):
        vm = _make_scored_vm(["A", "B"], gravity_scores={"A": 0.9, "B": 0.5})
        bag = extract_evidence_bag(vm)
        assert len(bag.provenance) == 1


# ===========================================================================
# TestEndToEnd
# ===========================================================================

class TestEndToEnd:
    """End-to-end extraction pipeline tests."""

    def test_full_pipeline_vm_to_bag(self):
        """Complete extraction: nodes, edges, chunks, hierarchy, scores, trace."""
        vm = _make_scored_vm(
            ["A", "B", "C", "D"],
            edges=[("A", "B"), ("B", "C"), ("C", "D")],
            chunks={"chA": "text for A", "chB": "text for B", "chC": "text for C"},
            chunk_bindings=[("A", "chA", 0), ("B", "chB", 0), ("C", "chC", 0)],
            hierarchy_entries=["h1"],
            hierarchy_bindings=[("A", "h1")],
            gravity_scores={"A": 0.9, "B": 0.7, "C": 0.5, "D": 0.1},
        )
        config = ExtractionConfig(max_seed_nodes=2, max_hops=1, token_budget=50000)
        bag = extract_evidence_bag(vm, config)

        # Nodes: seeds A(0.9), B(0.7) + 1-hop neighbors C (from B)
        assert NodeId("A") in bag.node_ids
        assert NodeId("B") in bag.node_ids
        # Edges connecting selected nodes
        assert len(bag.edge_ids) > 0
        # Chunks collected
        assert NodeId("A") in bag.chunk_refs
        # Hierarchy refs
        assert NodeId("A") in bag.hierarchy_refs
        # Score annotations
        assert NodeId("A") in bag.scores
        assert bag.scores[NodeId("A")].gravity == pytest.approx(0.9)
        # Trace
        assert bag.trace.extraction_strategy == "gravity_greedy"
        # Token budget
        assert bag.token_budget.used_tokens > 0

    def test_deterministic_repeat(self):
        """Running extraction twice produces identical bags."""
        vm = _make_scored_vm(
            ["A", "B", "C"],
            edges=[("A", "B"), ("B", "C")],
            chunks={"chA": "text A", "chB": "text B"},
            chunk_bindings=[("A", "chA", 0), ("B", "chB", 0)],
            gravity_scores={"A": 0.9, "B": 0.6, "C": 0.3},
        )
        config = ExtractionConfig(max_seed_nodes=2, max_hops=1)
        bag1 = extract_evidence_bag(vm, config)
        bag2 = extract_evidence_bag(vm, config)

        assert bag1.bag_id == bag2.bag_id
        assert bag1.node_ids == bag2.node_ids
        assert bag1.edge_ids == bag2.edge_ids
        assert bag1.chunk_refs == bag2.chunk_refs
        assert bag1.token_budget.used_tokens == bag2.token_budget.used_tokens

    def test_empty_vm_produces_empty_bag(self):
        vm = _make_scored_vm([])
        bag = extract_evidence_bag(vm)
        assert bag.node_ids == []
        assert bag.edge_ids == []
        assert bag.chunk_refs == {}
        assert bag.hierarchy_refs == {}
        assert bag.scores == {}
        assert bag.trace.selected_count == 0
        assert bag.trace.extraction_strategy == "gravity_greedy"
        assert isinstance(bag.bag_id, str)  # EvidenceBagId is NewType(str)


# ===========================================================================
# TestBackwardCompat
# ===========================================================================

class TestBackwardCompat:
    """Verify backward-compatible imports still work."""

    def test_import_from_extractor_placeholder(self):
        from src.core.extraction.extractor_placeholder import (
            ExtractionConfig as EC,
            extract_evidence_bag as eeb,
        )
        assert callable(eeb)
        assert EC is ExtractionConfig

    def test_import_from_extraction_init(self):
        from src.core.extraction import (
            ExtractionConfig as EC,
            extract_evidence_bag as eeb,
        )
        assert callable(eeb)
        assert EC is ExtractionConfig

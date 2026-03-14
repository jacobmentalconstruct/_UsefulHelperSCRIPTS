"""
Phase 7 Tests — Evidence Hydration.

Tests for:
    - HydrationConfig defaults and overrides
    - Node content resolution from chunk refs
    - Hierarchy context resolution
    - Score annotation inclusion in metadata
    - Node hydration (label, type, token estimate)
    - Edge translation (relation, weight, missing edge handling)
    - Edge ordering and post-budget filtering
    - Budget enforcement (truncation, first node guarantee, topology flag)
    - Hydration modes (FULL, SUMMARY, REFERENCE)
    - Provenance in bundle properties
    - Bundle properties (bag_id, budget, source_manifold_ids)
    - End-to-end hydration pipeline
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
    HydrationMode,
    NodeType,
    ProvenanceStage,
)
from src.core.types.graph import Chunk, Edge, HierarchyEntry, Node
from src.core.types.bindings import NodeChunkBinding, NodeHierarchyBinding
from src.core.manifolds.virtual_manifold import VirtualManifold
from src.core.math.annotator import annotate_scores
from src.core.contracts.evidence_bag_contract import (
    EvidenceBag,
    EvidenceBagTrace,
    ScoreAnnotation,
    TokenBudget,
)
from src.core.contracts.hydration_contract import (
    HydratedBundle,
    HydratedEdge,
    HydratedNode,
)

from src.core.hydration.hydrator import (
    HydrationConfig,
    hydrate_evidence_bag,
)


# ---------------------------------------------------------------------------
# Helper: build a VM and EvidenceBag for hydration tests
# ---------------------------------------------------------------------------

def _make_hydration_fixtures(
    node_ids: list,
    edges: list = None,
    chunks: dict = None,
    chunk_bindings: list = None,
    hierarchy_entries: list = None,
    hierarchy_bindings: list = None,
    gravity_scores: dict = None,
    manifold_id: str = "vm-hydrate-test",
) -> tuple:
    """
    Build a VirtualManifold and a matching EvidenceBag for hydration tests.

    This helper builds the VM directly (same pattern as Phase 6 tests)
    and manually constructs an EvidenceBag (no extraction dependency).

    Args:
        node_ids: List of string node IDs (in desired gravity order).
        edges: List of (from_id, to_id) tuples.
        chunks: Dict of chunk_hash_str -> chunk_text.
        chunk_bindings: List of (node_id_str, chunk_hash_str, ordinal) tuples.
        hierarchy_entries: List of (hierarchy_id_str, depth, sort_order, path_label) tuples.
        hierarchy_bindings: List of (node_id_str, hierarchy_id_str) tuples.
        gravity_scores: Dict of node_id_str -> gravity float.
        manifold_id: Manifold ID string.

    Returns:
        (evidence_bag, vm) tuple.
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
    edge_ids_list = []
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
            edge_ids_list.append(eid)

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
        for entry_tuple in hierarchy_entries:
            hid_str, depth, sort_order, path_label = entry_tuple
            hid = HierarchyId(hid_str)
            vm.get_hierarchy()[hid] = HierarchyEntry(
                hierarchy_id=hid,
                manifold_id=mid,
                node_id=NodeId(node_ids[0]) if node_ids else NodeId(""),
                depth=depth,
                sort_order=sort_order,
                path_label=path_label,
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
            structural[nid] = g
            semantic[nid] = 0.0
            gravity[nid] = g
        annotate_scores(vm, structural, semantic, gravity)

    # Build EvidenceBag manually
    node_id_list = [NodeId(n) for n in node_ids]
    chunk_refs = {}
    if chunk_bindings:
        for nid_str, ch_str, ordinal in chunk_bindings:
            nid = NodeId(nid_str)
            if nid not in chunk_refs:
                chunk_refs[nid] = []
            chunk_refs[nid].append(ChunkHash(ch_str))

    hierarchy_refs = {}
    if hierarchy_bindings:
        for nid_str, hid_str in hierarchy_bindings:
            nid = NodeId(nid_str)
            if nid not in hierarchy_refs:
                hierarchy_refs[nid] = []
            hierarchy_refs[nid].append(HierarchyId(hid_str))

    scores = {}
    if gravity_scores:
        for nid_str, g in gravity_scores.items():
            nid = NodeId(nid_str)
            scores[nid] = ScoreAnnotation(
                structural=g,
                semantic=0.0,
                gravity=g,
            )

    bag = EvidenceBag(
        bag_id=EvidenceBagId("bag-test-001"),
        node_ids=node_id_list,
        edge_ids=edge_ids_list,
        chunk_refs=chunk_refs,
        hierarchy_refs=hierarchy_refs,
        scores=scores,
        token_budget=TokenBudget(
            max_tokens=2048,
            used_tokens=0,
            remaining_tokens=2048,
        ),
        trace=EvidenceBagTrace(
            source_virtual_manifold_id=mid,
            extraction_strategy="gravity_greedy",
        ),
    )

    return bag, vm


# ===========================================================================
# TestHydrationConfig
# ===========================================================================

class TestHydrationConfig:
    """HydrationConfig defaults and overrides."""

    def test_default_values(self) -> None:
        cfg = HydrationConfig()
        assert cfg.mode == HydrationMode.FULL
        assert cfg.budget_target is None
        assert cfg.include_scores is True
        assert cfg.include_hierarchy is True
        assert cfg.include_provenance is True

    def test_custom_values(self) -> None:
        cfg = HydrationConfig(
            mode=HydrationMode.REFERENCE,
            budget_target=500,
            include_scores=False,
            include_hierarchy=False,
            include_provenance=False,
        )
        assert cfg.mode == HydrationMode.REFERENCE
        assert cfg.budget_target == 500
        assert cfg.include_scores is False
        assert cfg.include_hierarchy is False
        assert cfg.include_provenance is False

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(HydrationConfig)


# ===========================================================================
# TestNodeContentResolution
# ===========================================================================

class TestNodeContentResolution:
    """Chunk reference resolution into content text."""

    def test_single_chunk_resolved(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            chunks={"c1": "Hello world"},
            chunk_bindings=[("n1", "c1", 0)],
        )
        bundle = hydrate_evidence_bag(bag, vm)
        assert len(bundle.nodes) == 1
        assert bundle.nodes[0].content == "Hello world"

    def test_multiple_chunks_concatenated(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            chunks={"c1": "First chunk", "c2": "Second chunk"},
            chunk_bindings=[("n1", "c1", 0), ("n1", "c2", 1)],
        )
        bundle = hydrate_evidence_bag(bag, vm)
        assert bundle.nodes[0].content == "First chunk\n\nSecond chunk"

    def test_node_without_chunks_gets_empty_content(self) -> None:
        bag, vm = _make_hydration_fixtures(node_ids=["n1"])
        bundle = hydrate_evidence_bag(bag, vm)
        assert bundle.nodes[0].content == ""

    def test_missing_chunk_in_vm_skipped(self) -> None:
        """Chunk hash in evidence bag but not in VM is skipped."""
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            chunks={"c1": "Present chunk"},
            chunk_bindings=[("n1", "c1", 0), ("n1", "c_missing", 1)],
        )
        bundle = hydrate_evidence_bag(bag, vm)
        assert bundle.nodes[0].content == "Present chunk"


# ===========================================================================
# TestHierarchyResolution
# ===========================================================================

class TestHierarchyResolution:
    """Hierarchy reference resolution into context metadata."""

    def test_hierarchy_context_included(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            hierarchy_entries=[("h1", 0, 0, "project/src")],
            hierarchy_bindings=[("n1", "h1")],
        )
        bundle = hydrate_evidence_bag(bag, vm)
        meta = bundle.nodes[0].metadata
        assert "hierarchy" in meta
        assert len(meta["hierarchy"]) == 1
        assert meta["hierarchy"][0]["path_label"] == "project/src"

    def test_hierarchy_sorted_by_depth(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            hierarchy_entries=[
                ("h1", 2, 0, "deep"),
                ("h2", 0, 0, "root"),
                ("h3", 1, 0, "mid"),
            ],
            hierarchy_bindings=[("n1", "h1"), ("n1", "h2"), ("n1", "h3")],
        )
        bundle = hydrate_evidence_bag(bag, vm)
        hierarchy = bundle.nodes[0].metadata["hierarchy"]
        depths = [h["depth"] for h in hierarchy]
        assert depths == [0, 1, 2]

    def test_no_hierarchy_no_metadata_key(self) -> None:
        bag, vm = _make_hydration_fixtures(node_ids=["n1"])
        bundle = hydrate_evidence_bag(bag, vm)
        assert "hierarchy" not in bundle.nodes[0].metadata


# ===========================================================================
# TestScoreAnnotations
# ===========================================================================

class TestScoreAnnotations:
    """Score annotation inclusion in node metadata."""

    def test_score_in_node_metadata(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            gravity_scores={"n1": 0.85},
        )
        bundle = hydrate_evidence_bag(bag, vm)
        meta = bundle.nodes[0].metadata
        assert "score" in meta
        assert meta["score"]["gravity"] == 0.85
        assert meta["score"]["structural"] == 0.85

    def test_scores_excluded_when_disabled(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            gravity_scores={"n1": 0.85},
        )
        config = HydrationConfig(include_scores=False)
        bundle = hydrate_evidence_bag(bag, vm, config)
        assert "score" not in bundle.nodes[0].metadata

    def test_unscored_node_has_no_score_key(self) -> None:
        """Node not in evidence_bag.scores has no 'score' metadata key."""
        bag, vm = _make_hydration_fixtures(node_ids=["n1"])
        bundle = hydrate_evidence_bag(bag, vm)
        assert "score" not in bundle.nodes[0].metadata


# ===========================================================================
# TestNodeHydration
# ===========================================================================

class TestNodeHydration:
    """Node-level hydration correctness."""

    def test_hydrated_node_has_label(self) -> None:
        bag, vm = _make_hydration_fixtures(node_ids=["my-concept"])
        bundle = hydrate_evidence_bag(bag, vm)
        assert bundle.nodes[0].label == "my-concept"

    def test_hydrated_node_has_type(self) -> None:
        bag, vm = _make_hydration_fixtures(node_ids=["n1"])
        bundle = hydrate_evidence_bag(bag, vm)
        assert bundle.nodes[0].node_type == "CONCEPT"

    def test_hydrated_node_token_estimate(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            chunks={"c1": "Hello world test", "c2": "Another chunk text here"},
            chunk_bindings=[("n1", "c1", 0), ("n1", "c2", 1)],
        )
        bundle = hydrate_evidence_bag(bag, vm)
        # token_estimate = sum of Chunk.token_estimate for both chunks
        c1 = vm.get_chunks()[ChunkHash("c1")]
        c2 = vm.get_chunks()[ChunkHash("c2")]
        expected = c1.token_estimate + c2.token_estimate
        assert bundle.nodes[0].token_estimate == expected


# ===========================================================================
# TestEdgeTranslation
# ===========================================================================

class TestEdgeTranslation:
    """Edge translation into HydratedEdge."""

    def test_edge_translated_with_relation(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1", "n2"],
            edges=[("n1", "n2")],
        )
        bundle = hydrate_evidence_bag(bag, vm)
        assert len(bundle.edges) == 1
        assert bundle.edges[0].relation == "SEMANTIC"
        assert bundle.edges[0].source_id == NodeId("n1")
        assert bundle.edges[0].target_id == NodeId("n2")

    def test_edge_weight_preserved(self) -> None:
        mid = ManifoldId("vm-weight-test")
        vm = VirtualManifold(mid)

        # Add nodes
        for nid_str in ["n1", "n2"]:
            nid = NodeId(nid_str)
            vm.get_nodes()[nid] = Node(
                node_id=nid, manifold_id=mid,
                node_type=NodeType.CONCEPT, label=nid_str,
            )

        # Add edge with custom weight
        eid = EdgeId("e-custom")
        vm.get_edges()[eid] = Edge(
            edge_id=eid, manifold_id=mid,
            from_node_id=NodeId("n1"), to_node_id=NodeId("n2"),
            edge_type=EdgeType.BRIDGE, weight=0.7,
        )

        bag = EvidenceBag(
            bag_id=EvidenceBagId("bag-weight"),
            node_ids=[NodeId("n1"), NodeId("n2")],
            edge_ids=[eid],
            trace=EvidenceBagTrace(source_virtual_manifold_id=mid),
        )

        bundle = hydrate_evidence_bag(bag, vm)
        assert bundle.edges[0].weight == 0.7
        assert bundle.edges[0].relation == "BRIDGE"

    def test_missing_edge_in_vm_skipped(self) -> None:
        bag, vm = _make_hydration_fixtures(node_ids=["n1", "n2"])
        # Add a fake edge ID to the bag that doesn't exist in VM
        bag.edge_ids.append(EdgeId("nonexistent-edge"))
        bundle = hydrate_evidence_bag(bag, vm)
        assert len(bundle.edges) == 0


# ===========================================================================
# TestEdgeOrdering
# ===========================================================================

class TestEdgeOrdering:
    """Edge ordering and post-budget filtering."""

    def test_edges_sorted_stably(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1", "n2", "n3"],
            edges=[("n3", "n1"), ("n1", "n2"), ("n2", "n3")],
        )
        bundle = hydrate_evidence_bag(bag, vm)
        # Edges sorted by (source_id, target_id, edge_id)
        sources = [(str(e.source_id), str(e.target_id)) for e in bundle.edges]
        assert sources == sorted(sources)

    def test_edges_filtered_after_budget_truncation(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1", "n2", "n3"],
            edges=[("n1", "n2"), ("n2", "n3"), ("n1", "n3")],
            chunks={
                "c1": "A " * 500,  # Large chunk for n1
                "c2": "B " * 500,  # Large chunk for n2
            },
            chunk_bindings=[("n1", "c1", 0), ("n2", "c2", 0)],
            gravity_scores={"n1": 0.9, "n2": 0.5, "n3": 0.2},
        )
        # Tight budget — only first node should fit
        c1 = vm.get_chunks()[ChunkHash("c1")]
        budget = c1.token_estimate + 1  # Just enough for n1 only
        config = HydrationConfig(budget_target=budget)
        bundle = hydrate_evidence_bag(bag, vm, config)

        # Edges connecting dropped nodes should be removed
        remaining_nids = {n.node_id for n in bundle.nodes}
        for edge in bundle.edges:
            assert edge.source_id in remaining_nids
            assert edge.target_id in remaining_nids


# ===========================================================================
# TestBudgetEnforcement
# ===========================================================================

class TestBudgetEnforcement:
    """Budget enforcement — truncation and topology_preserved flag."""

    def test_no_budget_keeps_all_nodes(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1", "n2", "n3"],
            chunks={"c1": "Text one", "c2": "Text two", "c3": "Text three"},
            chunk_bindings=[("n1", "c1", 0), ("n2", "c2", 0), ("n3", "c3", 0)],
        )
        bundle = hydrate_evidence_bag(bag, vm)
        assert len(bundle.nodes) == 3
        assert bundle.topology_preserved is True

    def test_budget_truncates_lowest_gravity(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1", "n2", "n3"],
            chunks={
                "c1": "Short",
                "c2": "A slightly longer chunk of text here",
                "c3": "Another chunk",
            },
            chunk_bindings=[("n1", "c1", 0), ("n2", "c2", 0), ("n3", "c3", 0)],
            gravity_scores={"n1": 0.9, "n2": 0.5, "n3": 0.2},
        )
        # Very tight budget
        config = HydrationConfig(budget_target=5)
        bundle = hydrate_evidence_bag(bag, vm, config)
        # First node always kept; others may be dropped
        assert len(bundle.nodes) >= 1
        assert bundle.nodes[0].node_id == NodeId("n1")

    def test_budget_always_keeps_first_node(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            chunks={"c1": "A " * 5000},  # Very large chunk
            chunk_bindings=[("n1", "c1", 0)],
        )
        config = HydrationConfig(budget_target=1)  # Impossible budget
        bundle = hydrate_evidence_bag(bag, vm, config)
        assert len(bundle.nodes) == 1  # First node always kept

    def test_topology_preserved_flag(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1", "n2"],
            chunks={"c1": "A " * 500, "c2": "B " * 500},
            chunk_bindings=[("n1", "c1", 0), ("n2", "c2", 0)],
            gravity_scores={"n1": 0.9, "n2": 0.5},
        )
        c1 = vm.get_chunks()[ChunkHash("c1")]
        # Budget for first node only
        config = HydrationConfig(budget_target=c1.token_estimate + 1)
        bundle = hydrate_evidence_bag(bag, vm, config)
        assert bundle.topology_preserved is False


# ===========================================================================
# TestHydrationModes
# ===========================================================================

class TestHydrationModes:
    """Hydration mode behavior (FULL, SUMMARY, REFERENCE)."""

    def test_full_mode_includes_content(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            chunks={"c1": "Content here"},
            chunk_bindings=[("n1", "c1", 0)],
        )
        config = HydrationConfig(mode=HydrationMode.FULL)
        bundle = hydrate_evidence_bag(bag, vm, config)
        assert bundle.nodes[0].content == "Content here"
        assert bundle.nodes[0].token_estimate > 0
        assert bundle.mode == HydrationMode.FULL

    def test_reference_mode_excludes_content(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            chunks={"c1": "Content here"},
            chunk_bindings=[("n1", "c1", 0)],
        )
        config = HydrationConfig(mode=HydrationMode.REFERENCE)
        bundle = hydrate_evidence_bag(bag, vm, config)
        assert bundle.nodes[0].content == ""
        assert bundle.nodes[0].token_estimate == 0
        # chunk_hashes still populated for traceability
        assert ChunkHash("c1") in bundle.nodes[0].chunk_hashes
        assert bundle.mode == HydrationMode.REFERENCE

    def test_summary_mode_same_as_full(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1"],
            chunks={"c1": "Content here"},
            chunk_bindings=[("n1", "c1", 0)],
        )
        full_bundle = hydrate_evidence_bag(
            bag, vm, HydrationConfig(mode=HydrationMode.FULL),
        )
        summary_bundle = hydrate_evidence_bag(
            bag, vm, HydrationConfig(mode=HydrationMode.SUMMARY),
        )
        assert full_bundle.nodes[0].content == summary_bundle.nodes[0].content
        assert summary_bundle.mode == HydrationMode.SUMMARY


# ===========================================================================
# TestProvenance
# ===========================================================================

class TestProvenance:
    """Provenance inclusion in bundle properties."""

    def test_provenance_in_properties(self) -> None:
        bag, vm = _make_hydration_fixtures(node_ids=["n1"])
        config = HydrationConfig(include_provenance=True)
        bundle = hydrate_evidence_bag(bag, vm, config)
        assert "provenance" in bundle.properties
        prov = bundle.properties["provenance"]
        assert prov["stage"] == "HYDRATION"
        assert prov["owner_kind"] == "hydrated_bundle"

    def test_provenance_excluded_when_disabled(self) -> None:
        bag, vm = _make_hydration_fixtures(node_ids=["n1"])
        config = HydrationConfig(include_provenance=False)
        bundle = hydrate_evidence_bag(bag, vm, config)
        assert "provenance" not in bundle.properties


# ===========================================================================
# TestBundleProperties
# ===========================================================================

class TestBundleProperties:
    """Bundle-level properties and metadata."""

    def test_bag_id_in_properties(self) -> None:
        bag, vm = _make_hydration_fixtures(node_ids=["n1"])
        bundle = hydrate_evidence_bag(bag, vm)
        assert bundle.properties["bag_id"] == str(bag.bag_id)

    def test_budget_metadata_in_properties(self) -> None:
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1", "n2"],
            chunks={"c1": "Text one", "c2": "Text two"},
            chunk_bindings=[("n1", "c1", 0), ("n2", "c2", 0)],
        )
        bundle = hydrate_evidence_bag(bag, vm)
        budget = bundle.properties["budget"]
        assert "budget_target" in budget
        assert "total_tokens" in budget
        assert "nodes_hydrated" in budget
        assert "nodes_available" in budget
        assert "topology_preserved" in budget
        assert budget["nodes_hydrated"] == 2
        assert budget["nodes_available"] == 2

    def test_source_manifold_ids_populated(self) -> None:
        bag, vm = _make_hydration_fixtures(node_ids=["n1"])
        bundle = hydrate_evidence_bag(bag, vm)
        assert len(bundle.source_manifold_ids) == 1
        assert bundle.source_manifold_ids[0] == ManifoldId("vm-hydrate-test")


# ===========================================================================
# TestEndToEnd
# ===========================================================================

class TestEndToEnd:
    """Full pipeline hydration tests."""

    def test_full_pipeline_bag_to_bundle(self) -> None:
        """Complete hydration: nodes with content, edges, scores, hierarchy."""
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1", "n2", "n3"],
            edges=[("n1", "n2"), ("n2", "n3")],
            chunks={
                "c1": "First node content",
                "c2": "Second node content",
            },
            chunk_bindings=[("n1", "c1", 0), ("n2", "c2", 0)],
            hierarchy_entries=[("h1", 0, 0, "root/section")],
            hierarchy_bindings=[("n1", "h1")],
            gravity_scores={"n1": 0.9, "n2": 0.6, "n3": 0.2},
        )
        bundle = hydrate_evidence_bag(bag, vm)

        # All nodes present
        assert len(bundle.nodes) == 3
        assert bundle.nodes[0].content == "First node content"
        assert bundle.nodes[1].content == "Second node content"
        assert bundle.nodes[2].content == ""  # No chunks

        # Edges present
        assert len(bundle.edges) == 2

        # Scores in metadata
        assert bundle.nodes[0].metadata["score"]["gravity"] == 0.9

        # Hierarchy in metadata
        assert "hierarchy" in bundle.nodes[0].metadata
        assert bundle.nodes[0].metadata["hierarchy"][0]["path_label"] == "root/section"

        # Bundle-level metadata
        assert bundle.topology_preserved is True
        assert bundle.total_tokens > 0
        assert bundle.mode == HydrationMode.FULL

    def test_deterministic_repeat(self) -> None:
        """Hydrating the same bag+VM twice produces identical bundles."""
        bag, vm = _make_hydration_fixtures(
            node_ids=["n1", "n2"],
            edges=[("n1", "n2")],
            chunks={"c1": "Content A", "c2": "Content B"},
            chunk_bindings=[("n1", "c1", 0), ("n2", "c2", 0)],
            gravity_scores={"n1": 0.8, "n2": 0.4},
        )
        bundle_1 = hydrate_evidence_bag(bag, vm)
        bundle_2 = hydrate_evidence_bag(bag, vm)

        assert len(bundle_1.nodes) == len(bundle_2.nodes)
        assert len(bundle_1.edges) == len(bundle_2.edges)
        assert bundle_1.total_tokens == bundle_2.total_tokens
        for n1, n2 in zip(bundle_1.nodes, bundle_2.nodes):
            assert n1.node_id == n2.node_id
            assert n1.content == n2.content
            assert n1.token_estimate == n2.token_estimate
        for e1, e2 in zip(bundle_1.edges, bundle_2.edges):
            assert e1.edge_id == e2.edge_id
            assert e1.source_id == e2.source_id
            assert e1.relation == e2.relation

    def test_empty_bag_produces_empty_bundle(self) -> None:
        bag, vm = _make_hydration_fixtures(node_ids=[])
        bundle = hydrate_evidence_bag(bag, vm)
        assert len(bundle.nodes) == 0
        assert len(bundle.edges) == 0
        assert bundle.total_tokens == 0
        assert bundle.topology_preserved is True


# ===========================================================================
# TestBackwardCompat
# ===========================================================================

class TestBackwardCompat:
    """Backward compatibility: imports from placeholder and __init__."""

    def test_import_from_hydrator_placeholder(self) -> None:
        from src.core.hydration.hydrator_placeholder import (
            HydrationConfig as HC,
            hydrate_evidence_bag as heb,
            hydrate_node_payloads,
            translate_edges,
            format_evidence_bundle,
        )
        assert HC is HydrationConfig
        assert heb is hydrate_evidence_bag
        assert callable(hydrate_node_payloads)
        assert callable(translate_edges)
        assert callable(format_evidence_bundle)

    def test_import_from_hydration_init(self) -> None:
        from src.core.hydration import (
            HydrationConfig as HC,
            hydrate_evidence_bag as heb,
        )
        assert HC is HydrationConfig
        assert heb is hydrate_evidence_bag

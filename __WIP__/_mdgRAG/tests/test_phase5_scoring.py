"""
Phase 5 Tests — Scoring and Graph Math.

Tests for:
    - normalize_min_max: Min-max normalisation
    - structural_score: PageRank via power iteration
    - semantic_score: Cosine similarity
    - gravity_score: Fused structural + semantic
    - spreading_activation: BFS propagation from seeds
    - Friction detection: island effect, gravity collapse, normalization extrema
    - Score annotator: write/read ScoreAnnotation to/from VM
    - Full pipeline: VM → score → annotate → read roundtrip
    - Backward compatibility: import from scoring_placeholders and math.__init__
"""

import math

import pytest

from src.core.types.ids import ManifoldId, NodeId, EdgeId
from src.core.types.enums import ManifoldRole, NodeType, EdgeType
from src.core.types.graph import Node, Edge
from src.core.manifolds.virtual_manifold import VirtualManifold

from src.core.math.scoring import (
    normalize_min_max,
    structural_score,
    semantic_score,
    gravity_score,
    spreading_activation,
)
from src.core.math.friction import (
    detect_island_effect,
    detect_gravity_collapse,
    detect_normalization_extrema,
    detect_all_friction,
)
from src.core.math.annotator import (
    SCORE_ANNOTATION_KEY,
    annotate_scores,
    read_score_annotation,
)
from src.core.contracts.evidence_bag_contract import ScoreAnnotation
from src.core.debug.score_dump import dump_virtual_scores


# ---------------------------------------------------------------------------
# Helper: build a VirtualManifold with given topology
# ---------------------------------------------------------------------------

def _make_vm(
    node_ids: list,
    edges: list = None,
    manifold_id: str = "vm-test",
) -> VirtualManifold:
    """
    Build a VirtualManifold with given nodes and edges.

    Args:
        node_ids: List of string node IDs.
        edges: List of (from_id, to_id) tuples. Optional.
        manifold_id: Manifold ID string.

    Returns:
        Populated VirtualManifold.
    """
    vm = VirtualManifold(ManifoldId(manifold_id))

    for nid_str in node_ids:
        nid = NodeId(nid_str)
        vm.get_nodes()[nid] = Node(
            node_id=nid,
            manifold_id=ManifoldId(manifold_id),
            node_type=NodeType.CONCEPT,
            label=nid_str,
        )

    if edges:
        for i, (src, tgt) in enumerate(edges):
            eid = EdgeId(f"edge-{i}")
            vm.get_edges()[eid] = Edge(
                edge_id=eid,
                manifold_id=ManifoldId(manifold_id),
                from_node_id=NodeId(src),
                to_node_id=NodeId(tgt),
                edge_type=EdgeType.SEMANTIC,
            )

    return vm


# ===========================================================================
# TestNormalizeMinMax
# ===========================================================================

class TestNormalizeMinMax:
    """Tests for normalize_min_max."""

    def test_empty_dict(self):
        assert normalize_min_max({}) == {}

    def test_single_value(self):
        result = normalize_min_max({NodeId("a"): 5.0})
        assert result == {NodeId("a"): 0.5}

    def test_identical_values(self):
        scores = {NodeId("a"): 3.0, NodeId("b"): 3.0, NodeId("c"): 3.0}
        result = normalize_min_max(scores)
        for v in result.values():
            assert v == 0.5

    def test_two_values(self):
        scores = {NodeId("a"): 0.0, NodeId("b"): 10.0}
        result = normalize_min_max(scores)
        assert result[NodeId("a")] == pytest.approx(0.0)
        assert result[NodeId("b")] == pytest.approx(1.0)

    def test_known_three_values(self):
        scores = {NodeId("a"): 2.0, NodeId("b"): 6.0, NodeId("c"): 10.0}
        result = normalize_min_max(scores)
        assert result[NodeId("a")] == pytest.approx(0.0)
        assert result[NodeId("b")] == pytest.approx(0.5)
        assert result[NodeId("c")] == pytest.approx(1.0)

    def test_negative_values(self):
        scores = {NodeId("a"): -10.0, NodeId("b"): 0.0, NodeId("c"): 10.0}
        result = normalize_min_max(scores)
        assert result[NodeId("a")] == pytest.approx(0.0)
        assert result[NodeId("b")] == pytest.approx(0.5)
        assert result[NodeId("c")] == pytest.approx(1.0)

    def test_near_threshold_degenerate(self):
        """Values within 1e-10 of each other → all 0.5."""
        scores = {NodeId("a"): 1.0, NodeId("b"): 1.0 + 1e-11}
        result = normalize_min_max(scores)
        for v in result.values():
            assert v == 0.5


# ===========================================================================
# TestStructuralScore
# ===========================================================================

class TestStructuralScore:
    """Tests for structural_score (PageRank)."""

    def test_empty_graph(self):
        vm = _make_vm([])
        result = structural_score(vm)
        assert result == {}

    def test_single_node(self):
        vm = _make_vm(["A"])
        result = structural_score(vm)
        assert NodeId("A") in result
        assert result[NodeId("A")] == pytest.approx(1.0)

    def test_star_topology(self):
        """Hub node should have highest rank in star graph."""
        vm = _make_vm(
            ["hub", "s1", "s2", "s3"],
            [("s1", "hub"), ("s2", "hub"), ("s3", "hub")],
        )
        result = structural_score(vm)
        assert result[NodeId("hub")] > result[NodeId("s1")]
        assert result[NodeId("hub")] > result[NodeId("s2")]
        assert result[NodeId("hub")] > result[NodeId("s3")]

    def test_chain(self):
        """In a directed chain A→B→C, rank should flow toward C."""
        vm = _make_vm(["A", "B", "C"], [("A", "B"), ("B", "C")])
        result = structural_score(vm)
        # C is the sink — should accumulate most rank
        assert result[NodeId("C")] > result[NodeId("A")]

    def test_cycle(self):
        """All nodes in a symmetric cycle should have equal rank."""
        vm = _make_vm(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")])
        result = structural_score(vm)
        vals = list(result.values())
        # All should be approximately equal
        for v in vals:
            assert v == pytest.approx(vals[0], abs=1e-6)

    def test_isolated_nodes(self):
        """Nodes with no edges should get uniform rank."""
        vm = _make_vm(["A", "B", "C"])
        result = structural_score(vm)
        expected = 1.0 / 3.0
        for v in result.values():
            assert v == pytest.approx(expected)


# ===========================================================================
# TestSemanticScore
# ===========================================================================

class TestSemanticScore:
    """Tests for semantic_score (cosine similarity)."""

    def test_empty(self):
        result = semantic_score({}, [1.0, 0.0])
        assert result == {}

    def test_identical_vectors(self):
        embeddings = {NodeId("a"): [1.0, 0.0, 0.0]}
        result = semantic_score(embeddings, [1.0, 0.0, 0.0])
        assert result[NodeId("a")] == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        embeddings = {NodeId("a"): [1.0, 0.0]}
        result = semantic_score(embeddings, [0.0, 1.0])
        assert result[NodeId("a")] == pytest.approx(0.0)

    def test_opposite_vectors_clamped(self):
        """Opposite vectors should clamp to 0.0, not -1.0."""
        embeddings = {NodeId("a"): [1.0, 0.0]}
        result = semantic_score(embeddings, [-1.0, 0.0])
        assert result[NodeId("a")] == pytest.approx(0.0)

    def test_known_similarity(self):
        """Known cosine similarity: cos(45°) ≈ 0.7071."""
        embeddings = {NodeId("a"): [1.0, 0.0]}
        result = semantic_score(embeddings, [1.0, 1.0])
        expected = 1.0 / math.sqrt(2)  # ≈ 0.7071
        assert result[NodeId("a")] == pytest.approx(expected, abs=1e-4)

    def test_zero_vector(self):
        """Zero vector node embedding should give zero similarity."""
        embeddings = {NodeId("a"): [0.0, 0.0, 0.0]}
        result = semantic_score(embeddings, [1.0, 0.0, 0.0])
        assert result[NodeId("a")] == pytest.approx(0.0)


# ===========================================================================
# TestGravityScore
# ===========================================================================

class TestGravityScore:
    """Tests for gravity_score (fused scoring)."""

    def test_empty(self):
        result = gravity_score({}, {})
        assert result == {}

    def test_known_fusion(self):
        """With identical normalised inputs, gravity = alpha * v + beta * v."""
        structural = {NodeId("a"): 0.0, NodeId("b"): 10.0}
        semantic = {NodeId("a"): 0.0, NodeId("b"): 1.0}
        result = gravity_score(structural, semantic)
        # After min-max: both a=0.0, b=1.0
        # gravity(a) = 0.6*0 + 0.4*0 = 0.0
        # gravity(b) = 0.6*1 + 0.4*1 = 1.0
        assert result[NodeId("a")] == pytest.approx(0.0)
        assert result[NodeId("b")] == pytest.approx(1.0)

    def test_custom_alpha_beta(self):
        structural = {NodeId("a"): 0.0, NodeId("b"): 1.0}
        semantic = {NodeId("a"): 0.0, NodeId("b"): 1.0}
        result = gravity_score(structural, semantic, alpha=0.3, beta=0.7)
        # After min-max: a=0, b=1; gravity(b) = 0.3*1 + 0.7*1 = 1.0
        assert result[NodeId("b")] == pytest.approx(1.0)

    def test_partial_node_overlap(self):
        """Nodes in only one dict get 0.0 for the missing component."""
        structural = {NodeId("a"): 5.0, NodeId("b"): 10.0}
        semantic = {NodeId("b"): 1.0, NodeId("c"): 2.0}
        result = gravity_score(structural, semantic)
        # a only has structural, c only has semantic
        assert NodeId("a") in result
        assert NodeId("b") in result
        assert NodeId("c") in result

    def test_degenerate_single_structural(self):
        """Single-value structural normalises to 0.5."""
        structural = {NodeId("a"): 5.0}
        semantic = {NodeId("a"): 0.0, NodeId("b"): 1.0}
        result = gravity_score(structural, semantic)
        # structural normalises: a=0.5 (degenerate)
        # semantic normalises: a=0.0, b=1.0
        # gravity(a) = 0.6*0.5 + 0.4*0.0 = 0.3
        assert result[NodeId("a")] == pytest.approx(0.3)


# ===========================================================================
# TestSpreadingActivation
# ===========================================================================

class TestSpreadingActivation:
    """Tests for spreading_activation."""

    def test_empty_graph(self):
        vm = _make_vm([])
        result = spreading_activation(vm, [NodeId("A")])
        assert result == {}

    def test_single_seed_chain(self):
        """Seed at start of chain, activation propagates with decay."""
        vm = _make_vm(["A", "B", "C"], [("A", "B"), ("B", "C")])
        result = spreading_activation(vm, [NodeId("A")], iterations=3, decay=0.5)
        assert result[NodeId("A")] == pytest.approx(1.0)
        assert result[NodeId("B")] == pytest.approx(0.5)
        assert result[NodeId("C")] == pytest.approx(0.25)

    def test_seed_retention(self):
        """Seeds always keep 1.0 activation even after propagation."""
        vm = _make_vm(["A", "B"], [("A", "B"), ("B", "A")])
        result = spreading_activation(vm, [NodeId("A")], iterations=5, decay=0.5)
        assert result[NodeId("A")] == pytest.approx(1.0)

    def test_multiple_seeds(self):
        """Multiple seeds all start at 1.0."""
        vm = _make_vm(["A", "B", "C"], [("A", "B"), ("B", "C")])
        result = spreading_activation(
            vm, [NodeId("A"), NodeId("C")], iterations=2, decay=0.5,
        )
        assert result[NodeId("A")] == pytest.approx(1.0)
        assert result[NodeId("C")] == pytest.approx(1.0)
        # B gets activation from both directions
        assert result[NodeId("B")] == pytest.approx(0.5)

    def test_depth_effect(self):
        """Nodes farther from seed get less activation."""
        vm = _make_vm(
            ["A", "B", "C", "D"],
            [("A", "B"), ("B", "C"), ("C", "D")],
        )
        result = spreading_activation(vm, [NodeId("A")], iterations=3, decay=0.5)
        assert result[NodeId("A")] > result[NodeId("B")]
        assert result[NodeId("B")] > result[NodeId("C")]
        assert result[NodeId("C")] > result[NodeId("D")]


# ===========================================================================
# TestFrictionDetection
# ===========================================================================

class TestFrictionDetection:
    """Tests for friction detection functions."""

    def test_connected_graph_no_islands(self):
        vm = _make_vm(["A", "B", "C"], [("A", "B"), ("B", "C")])
        assert detect_island_effect(vm) is False

    def test_disconnected_graph_has_islands(self):
        vm = _make_vm(["A", "B", "C", "D"], [("A", "B")])
        # C and D are disconnected from A-B
        assert detect_island_effect(vm) is True

    def test_wide_spread_no_collapse(self):
        scores = {NodeId("a"): 0.0, NodeId("b"): 0.5, NodeId("c"): 1.0}
        assert detect_gravity_collapse(scores) is False

    def test_narrow_spread_collapse(self):
        scores = {NodeId("a"): 0.50, NodeId("b"): 0.51, NodeId("c"): 0.52}
        assert detect_gravity_collapse(scores, threshold=0.1) is True

    def test_all_zero_extrema(self):
        scores = {NodeId("a"): 0.0, NodeId("b"): 0.0}
        assert detect_normalization_extrema(scores) is True

    def test_detect_all_friction_summary(self):
        vm = _make_vm(["A", "B", "C", "D"], [("A", "B")])
        scores = {NodeId("A"): 0.5, NodeId("B"): 0.51}
        result = detect_all_friction(vm, scores)
        assert result["island_effect"] is True
        assert result["gravity_collapse"] is True
        assert result["normalization_extrema"] is False


# ===========================================================================
# TestScoreAnnotator
# ===========================================================================

class TestScoreAnnotator:
    """Tests for score annotator (write/read bridge)."""

    def test_structural_only(self):
        vm = _make_vm(["A", "B"])
        structural = {NodeId("A"): 0.8, NodeId("B"): 0.2}
        annotate_scores(vm, structural, {}, {})
        annot = read_score_annotation(vm, NodeId("A"))
        assert annot is not None
        assert annot.structural == pytest.approx(0.8)
        assert annot.semantic == pytest.approx(0.0)
        assert annot.gravity == pytest.approx(0.0)

    def test_all_three_scores(self):
        vm = _make_vm(["A"])
        structural = {NodeId("A"): 0.6}
        semantic = {NodeId("A"): 0.8}
        gravity = {NodeId("A"): 0.72}
        annotate_scores(vm, structural, semantic, gravity)
        annot = read_score_annotation(vm, NodeId("A"))
        assert annot is not None
        assert annot.structural == pytest.approx(0.6)
        assert annot.semantic == pytest.approx(0.8)
        assert annot.gravity == pytest.approx(0.72)

    def test_missing_node(self):
        vm = _make_vm(["A"])
        assert read_score_annotation(vm, NodeId("MISSING")) is None

    def test_preserves_existing_annotations(self):
        vm = _make_vm(["A"])
        # Set a custom annotation first
        vm.runtime_annotations[NodeId("A")] = {"custom_key": "custom_value"}
        annotate_scores(vm, {NodeId("A"): 0.5}, {}, {})
        # Custom annotation should still be there
        assert vm.runtime_annotations[NodeId("A")]["custom_key"] == "custom_value"
        # Score annotation should also be there
        annot = read_score_annotation(vm, NodeId("A"))
        assert annot is not None
        assert annot.structural == pytest.approx(0.5)


# ===========================================================================
# TestFullPipeline
# ===========================================================================

class TestFullPipeline:
    """End-to-end pipeline tests: VM → score → annotate → read."""

    def test_roundtrip(self):
        """Full pipeline: structural + semantic → gravity → annotate → read."""
        vm = _make_vm(
            ["A", "B", "C"],
            [("A", "B"), ("B", "C"), ("C", "A")],
        )

        # Score
        s_scores = structural_score(vm)
        embeddings = {
            NodeId("A"): [1.0, 0.0],
            NodeId("B"): [0.0, 1.0],
            NodeId("C"): [0.7, 0.7],
        }
        query = [1.0, 0.0]
        t_scores = semantic_score(embeddings, query)
        g_scores = gravity_score(s_scores, t_scores)

        # Annotate
        annotate_scores(vm, s_scores, t_scores, g_scores)

        # Read back
        for nid_str in ["A", "B", "C"]:
            nid = NodeId(nid_str)
            annot = read_score_annotation(vm, nid)
            assert annot is not None
            assert annot.gravity == pytest.approx(g_scores[nid])

    def test_score_dump_integration(self):
        """dump_virtual_scores returns correct structure after scoring."""
        vm = _make_vm(["X", "Y"], [("X", "Y")])
        s_scores = structural_score(vm)
        t_scores = {NodeId("X"): 0.9, NodeId("Y"): 0.1}
        g_scores = gravity_score(s_scores, t_scores)
        annotate_scores(vm, s_scores, t_scores, g_scores)

        summary = dump_virtual_scores(vm)
        assert summary["node_count"] == 2
        assert summary["annotated_count"] == 2
        assert len(summary["top_gravity"]) == 2
        assert NodeId("X") in summary["scores"]
        assert NodeId("Y") in summary["scores"]

    def test_deterministic_repeat(self):
        """Running the same scoring twice produces identical results."""
        vm1 = _make_vm(["A", "B", "C"], [("A", "B"), ("B", "C")])
        vm2 = _make_vm(["A", "B", "C"], [("A", "B"), ("B", "C")])

        r1 = structural_score(vm1)
        r2 = structural_score(vm2)

        for nid in r1:
            assert r1[nid] == pytest.approx(r2[nid])


# ===========================================================================
# TestBackwardCompatibility
# ===========================================================================

class TestBackwardCompatibility:
    """Verify backward-compatible imports still work."""

    def test_import_from_scoring_placeholders(self):
        """Old import path: scoring_placeholders module."""
        from src.core.math.scoring_placeholders import (
            structural_score as ss,
            semantic_score as sem,
            gravity_score as gs,
            normalize_min_max as nmm,
            spreading_activation as sa,
        )
        # These should be the real implementations, not stubs
        assert callable(ss)
        assert callable(sem)
        assert callable(gs)
        assert callable(nmm)
        assert callable(sa)
        # Verify they don't raise NotImplementedError
        assert nmm({}) == {}

    def test_import_from_math_init(self):
        """Package-level import: from src.core.math."""
        from src.core.math import (
            structural_score as ss,
            semantic_score as sem,
            gravity_score as gs,
            normalize_min_max as nmm,
            spreading_activation as sa,
            detect_island_effect,
            detect_gravity_collapse,
            detect_normalization_extrema,
            detect_all_friction,
            SCORE_ANNOTATION_KEY as key,
            annotate_scores as ann,
            read_score_annotation as rsa,
        )
        assert callable(ss)
        assert callable(detect_island_effect)
        assert callable(ann)
        assert key == "score"

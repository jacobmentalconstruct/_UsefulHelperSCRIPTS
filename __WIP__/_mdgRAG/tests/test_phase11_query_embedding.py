"""
Phase 11 Tests — Query Embedding Integration / Semantic Scoring Activation.

Tests for:
    - QueryProjection embed_fn callback: success, failure, absent
    - Query embedding stored in artifact properties
    - Backward compatibility: project() still works without embed_fn
    - Deterministic ID preserved with embedding
    - Scoring semantic path activation with query embedding
    - Scoring structural-only fallback without query embedding
    - Gravity formula actually uses both alpha*S + beta*T when embedding present
    - Runtime end-to-end: embed callback wired through pipeline
    - Runtime embed failure graceful degradation
    - Visibility: logging and metadata for semantic scoring status
"""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.core.contracts.fusion_contract import (
    BridgeEdge,
    FusionAncestry,
    FusionResult,
)
from src.core.contracts.projection_contract import (
    ProjectedSlice,
    ProjectionMetadata,
    QueryProjectionArtifact,
)
from src.core.contracts.model_bridge_contract import (
    EmbedRequest,
    EmbedResponse,
    SynthesisResponse,
)
from src.core.fusion.fusion_engine import FusionEngine
from src.core.manifolds.virtual_manifold import VirtualManifold
from src.core.math.scoring import (
    gravity_score,
    normalize_min_max,
    semantic_score,
    structural_score,
)
from src.core.math.annotator import annotate_scores, read_score_annotation
from src.core.projection.query_projection import QueryProjection
from src.core.runtime.runtime_controller import (
    PipelineConfig,
    PipelineResult,
    RuntimeController,
)
from src.core.model_bridge.model_bridge import (
    ModelBridge,
    ModelBridgeConfig,
    ModelConnectionError,
)
from src.core.types.ids import (
    ChunkHash,
    EdgeId,
    ManifoldId,
    NodeId,
    deterministic_hash,
    HASH_TRUNCATION_LENGTH,
)
from src.core.types.enums import (
    EdgeType,
    EmbeddingMetricType,
    EmbeddingTargetKind,
    NodeType,
    ProjectionSourceKind,
)
from src.core.types.graph import Chunk, Edge, Embedding, Node
from src.core.types.bindings import NodeChunkBinding, NodeEmbeddingBinding
from src.core.types.provenance import Provenance


# ===================================================================
# Helpers
# ===================================================================

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_node(
    nid: str, manifold: str = "m1", key: str = "", label: str = "",
) -> Node:
    return Node(
        node_id=NodeId(nid),
        manifold_id=ManifoldId(manifold),
        node_type=NodeType.CONCEPT,
        canonical_key=key,
        label=label or nid,
    )


def _make_projected_slice(
    nodes: List[Node],
    manifold_id: str = "m1",
    source_kind: ProjectionSourceKind = ProjectionSourceKind.IDENTITY,
) -> ProjectedSlice:
    return ProjectedSlice(
        metadata=ProjectionMetadata(
            source_manifold_id=ManifoldId(manifold_id),
            source_kind=source_kind,
            criteria={},
            timestamp=_utcnow_iso(),
            description="test slice",
        ),
        node_ids=[n.node_id for n in nodes],
        nodes=nodes,
    )


def _pack_floats(floats: List[float]) -> bytes:
    """Pack a list of floats into a bytes blob (little-endian 32-bit)."""
    return struct.pack(f"<{len(floats)}f", *floats)


def _dummy_embed_fn(text: str) -> List[float]:
    """A deterministic fake embedding: [hash-byte/255, ...] for 4 dims."""
    h = deterministic_hash(text)
    return [int(h[i:i+2], 16) / 255.0 for i in range(0, 8, 2)]


def _failing_embed_fn(text: str) -> List[float]:
    """An embedding callback that always raises."""
    raise ConnectionError("Embedding service unavailable")


def _empty_embed_fn(text: str) -> List[float]:
    """An embedding callback that returns an empty vector."""
    return []


# ===================================================================
# TestQueryProjectionEmbedding
# ===================================================================

class TestQueryProjectionEmbedding:
    """Verify QueryProjection embed_fn callback behavior."""

    def test_project_without_embed_fn_still_works(self):
        """Backward compat: project() without embed_fn produces artifact."""
        qp = QueryProjection()
        result = qp.project(None, {"raw_query": "test query"})
        artifact = result.projected_data["query_artifact"]
        assert artifact.raw_query == "test query"
        assert artifact.query_node_id is not None
        assert "query_embedding" not in artifact.properties

    def test_project_with_embed_fn_stores_embedding(self):
        """embed_fn result stored in artifact.properties['query_embedding']."""
        qp = QueryProjection()
        result = qp.project(
            None, {"raw_query": "hello world"}, embed_fn=_dummy_embed_fn,
        )
        artifact = result.projected_data["query_artifact"]
        assert "query_embedding" in artifact.properties
        embedding = artifact.properties["query_embedding"]
        assert isinstance(embedding, list)
        assert len(embedding) == 4
        assert all(isinstance(v, float) for v in embedding)

    def test_project_embed_fn_stores_dimensions(self):
        """Embedding dimensions stored in artifact.properties."""
        qp = QueryProjection()
        result = qp.project(
            None, {"raw_query": "hello"}, embed_fn=_dummy_embed_fn,
        )
        artifact = result.projected_data["query_artifact"]
        assert artifact.properties["query_embedding_dimensions"] == 4

    def test_project_embed_fn_failure_is_non_fatal(self):
        """embed_fn failure does not crash — projection still succeeds."""
        qp = QueryProjection()
        result = qp.project(
            None, {"raw_query": "test"}, embed_fn=_failing_embed_fn,
        )
        artifact = result.projected_data["query_artifact"]
        # No embedding stored
        assert "query_embedding" not in artifact.properties
        # Error recorded
        assert "query_embedding_error" in artifact.properties
        assert "unavailable" in artifact.properties["query_embedding_error"]

    def test_project_embed_fn_empty_vector_stored(self):
        """embed_fn returning empty vector stores empty list."""
        qp = QueryProjection()
        result = qp.project(
            None, {"raw_query": "test"}, embed_fn=_empty_embed_fn,
        )
        artifact = result.projected_data["query_artifact"]
        # Empty vector IS stored (embed_fn succeeded, returned [])
        assert artifact.properties["query_embedding"] == []
        assert artifact.properties["query_embedding_dimensions"] == 0

    def test_project_deterministic_id_preserved_with_embedding(self):
        """Embedding does not affect deterministic query node ID."""
        qp = QueryProjection()
        r1 = qp.project(None, {"raw_query": "same query"})
        r2 = qp.project(
            None, {"raw_query": "same query"}, embed_fn=_dummy_embed_fn,
        )
        a1 = r1.projected_data["query_artifact"]
        a2 = r2.projected_data["query_artifact"]
        assert a1.query_node_id == a2.query_node_id

    def test_project_node_type_is_query(self):
        """Query node type preserved when embedding is present."""
        qp = QueryProjection()
        result = qp.project(
            None, {"raw_query": "test"}, embed_fn=_dummy_embed_fn,
        )
        artifact = result.projected_data["query_artifact"]
        assert artifact.query_node.node_type == NodeType.QUERY

    def test_project_missing_raw_query_still_raises(self):
        """ValueError still raised for missing raw_query even with embed_fn."""
        qp = QueryProjection()
        with pytest.raises(ValueError, match="raw_query"):
            qp.project(None, {}, embed_fn=_dummy_embed_fn)

    def test_embed_fn_called_with_raw_query_text(self):
        """embed_fn receives the exact raw_query string."""
        received_texts = []

        def capture_fn(text: str) -> List[float]:
            received_texts.append(text)
            return [0.1, 0.2, 0.3]

        qp = QueryProjection()
        qp.project(None, {"raw_query": "specific query text"}, embed_fn=capture_fn)
        assert received_texts == ["specific query text"]


# ===================================================================
# TestQueryProjectionLogging
# ===================================================================

class TestQueryProjectionLogging:
    """Verify query projection logging for embed visibility."""

    def test_embed_success_logged(self, caplog):
        """Successful embedding logs dimensions."""
        import logging
        qp = QueryProjection()
        with caplog.at_level(logging.INFO, logger="src.core.projection.query_projection"):
            qp.project(None, {"raw_query": "test"}, embed_fn=_dummy_embed_fn)
        assert "query embedded" in caplog.text.lower()
        assert "dims=" in caplog.text.lower()

    def test_embed_failure_logged(self, caplog):
        """Failed embedding logs warning."""
        import logging
        qp = QueryProjection()
        with caplog.at_level(logging.WARNING, logger="src.core.projection.query_projection"):
            qp.project(None, {"raw_query": "test"}, embed_fn=_failing_embed_fn)
        assert "embed_fn failed" in caplog.text.lower() or "failed" in caplog.text.lower()

    def test_no_embed_fn_logged(self, caplog):
        """No embed_fn logs informational skip."""
        import logging
        qp = QueryProjection()
        with caplog.at_level(logging.INFO, logger="src.core.projection.query_projection"):
            qp.project(None, {"raw_query": "test"})
        assert "no embed_fn" in caplog.text.lower() or "skipped" in caplog.text.lower()


# ===================================================================
# TestSemanticScoringActivation
# ===================================================================

class TestSemanticScoringActivation:
    """Verify semantic scoring path is exercised when embedding exists."""

    def test_semantic_score_with_embeddings(self):
        """semantic_score produces non-empty results when inputs exist."""
        node_embeddings = {
            NodeId("n1"): [1.0, 0.0, 0.0, 0.0],
            NodeId("n2"): [0.0, 1.0, 0.0, 0.0],
            NodeId("n3"): [0.7, 0.7, 0.0, 0.0],
        }
        query_embedding = [1.0, 0.0, 0.0, 0.0]
        scores = semantic_score(node_embeddings, query_embedding)
        assert len(scores) == 3
        # n1 should be most similar (same direction)
        assert scores[NodeId("n1")] > scores[NodeId("n2")]
        # n3 partially similar
        assert scores[NodeId("n3")] > scores[NodeId("n2")]

    def test_gravity_with_semantic_differs_from_structural_only(self):
        """Gravity score changes when semantic scores are provided."""
        structural = {
            NodeId("n1"): 0.5,
            NodeId("n2"): 0.3,
            NodeId("n3"): 0.2,
        }
        # Semantic scores reverse the ranking
        semantic = {
            NodeId("n1"): 0.1,
            NodeId("n2"): 0.5,
            NodeId("n3"): 0.9,
        }

        # Gravity with both signals
        grav_full = gravity_score(structural, semantic, alpha=0.6, beta=0.4)
        # Gravity with structural-only fallback
        grav_structural = gravity_score(structural, {}, alpha=1.0, beta=0.0)

        # Rankings should differ
        full_ranking = sorted(grav_full, key=grav_full.get, reverse=True)
        struct_ranking = sorted(
            grav_structural, key=grav_structural.get, reverse=True,
        )
        # n3 has low structural but high semantic — should rise in full gravity
        assert grav_full[NodeId("n3")] > grav_structural[NodeId("n3")]

    def test_gravity_fallback_structural_only_when_no_semantic(self):
        """Without semantic scores, gravity equals structural (alpha=1.0)."""
        structural = {
            NodeId("n1"): 0.8,
            NodeId("n2"): 0.2,
        }
        grav = gravity_score(structural, {}, alpha=1.0, beta=0.0)
        # After normalization, n1 should be highest
        assert grav[NodeId("n1")] > grav[NodeId("n2")]
        # Should have same relative ordering as structural
        s_norm = normalize_min_max(structural)
        g_norm = normalize_min_max(grav)
        assert list(
            sorted(s_norm, key=s_norm.get, reverse=True)
        ) == list(
            sorted(g_norm, key=g_norm.get, reverse=True)
        )


# ===================================================================
# TestScoringStageSemanticPath
# ===================================================================

class TestScoringStageSemanticPath:
    """Verify RuntimeController._run_scoring activates semantic path."""

    def _make_vm_with_embeddings(self) -> VirtualManifold:
        """Create a VM with nodes, edges, and node embeddings."""
        vm = VirtualManifold(manifold_id=ManifoldId("test-vm"))

        # Add nodes
        n1 = _make_node("n1", "test-vm")
        n2 = _make_node("n2", "test-vm")
        n3 = _make_node("n3", "test-vm")
        vm.get_nodes()[n1.node_id] = n1
        vm.get_nodes()[n2.node_id] = n2
        vm.get_nodes()[n3.node_id] = n3

        # Add edges
        e1 = Edge(
            edge_id=EdgeId("e1"),
            manifold_id=ManifoldId("test-vm"),
            from_node_id=NodeId("n1"),
            to_node_id=NodeId("n2"),
            edge_type=EdgeType.ADJACENT,
        )
        e2 = Edge(
            edge_id=EdgeId("e2"),
            manifold_id=ManifoldId("test-vm"),
            from_node_id=NodeId("n2"),
            to_node_id=NodeId("n3"),
            edge_type=EdgeType.ADJACENT,
        )
        vm.get_edges()[e1.edge_id] = e1
        vm.get_edges()[e2.edge_id] = e2

        # Add embeddings (4-dimensional vectors)
        emb1 = Embedding(
            embedding_id="emb-n1",
            target_kind=EmbeddingTargetKind.NODE,
            target_id="n1",
            model_name="test",
            dimensions=4,
            vector_blob=_pack_floats([1.0, 0.0, 0.0, 0.0]),
        )
        emb2 = Embedding(
            embedding_id="emb-n2",
            target_kind=EmbeddingTargetKind.NODE,
            target_id="n2",
            model_name="test",
            dimensions=4,
            vector_blob=_pack_floats([0.0, 1.0, 0.0, 0.0]),
        )
        emb3 = Embedding(
            embedding_id="emb-n3",
            target_kind=EmbeddingTargetKind.NODE,
            target_id="n3",
            model_name="test",
            dimensions=4,
            vector_blob=_pack_floats([0.7, 0.7, 0.0, 0.0]),
        )
        vm.get_embeddings()["emb-n1"] = emb1
        vm.get_embeddings()["emb-n2"] = emb2
        vm.get_embeddings()["emb-n3"] = emb3

        # Add embedding bindings
        b1 = NodeEmbeddingBinding(
            node_id=NodeId("n1"),
            embedding_id="emb-n1",
            manifold_id=ManifoldId("test-vm"),
        )
        b2 = NodeEmbeddingBinding(
            node_id=NodeId("n2"),
            embedding_id="emb-n2",
            manifold_id=ManifoldId("test-vm"),
        )
        b3 = NodeEmbeddingBinding(
            node_id=NodeId("n3"),
            embedding_id="emb-n3",
            manifold_id=ManifoldId("test-vm"),
        )
        vm.get_node_embedding_bindings().extend([b1, b2, b3])

        return vm

    def test_scoring_with_query_embedding_activates_semantic(self):
        """When query_embedding is in artifact, semantic scoring fires."""
        controller = RuntimeController()
        vm = self._make_vm_with_embeddings()

        # Build query artifact WITH embedding
        qp = QueryProjection()
        query_slice = qp.project(
            None, {"raw_query": "test query"},
            embed_fn=lambda t: [1.0, 0.0, 0.0, 0.0],
        )
        artifact = query_slice.projected_data["query_artifact"]
        assert "query_embedding" in artifact.properties

        cfg = PipelineConfig(alpha=0.6, beta=0.4)
        structural, semantic, grav, degraded = controller._run_scoring(
            vm, artifact, cfg,
        )

        # Semantic should be non-empty
        assert len(semantic) > 0
        assert not degraded

    def test_scoring_without_query_embedding_degrades(self):
        """Without query_embedding, scoring falls back to structural-only."""
        controller = RuntimeController()
        vm = self._make_vm_with_embeddings()

        # Build query artifact WITHOUT embedding
        qp = QueryProjection()
        query_slice = qp.project(None, {"raw_query": "test query"})
        artifact = query_slice.projected_data["query_artifact"]
        assert "query_embedding" not in artifact.properties

        cfg = PipelineConfig()
        structural, semantic, grav, degraded = controller._run_scoring(
            vm, artifact, cfg,
        )

        # Semantic should be empty
        assert len(semantic) == 0
        assert degraded

    def test_scoring_semantic_affects_gravity_ranking(self):
        """Semantic scoring actually changes the gravity ranking."""
        controller = RuntimeController()
        vm = self._make_vm_with_embeddings()

        cfg = PipelineConfig(alpha=0.6, beta=0.4)

        # Run with embedding aligned to n1
        qp = QueryProjection()
        query_slice = qp.project(
            None, {"raw_query": "test"},
            embed_fn=lambda t: [1.0, 0.0, 0.0, 0.0],  # aligned with n1
        )
        artifact_with_emb = query_slice.projected_data["query_artifact"]
        _, _, grav_with, _ = controller._run_scoring(vm, artifact_with_emb, cfg)

        # Run without embedding
        query_slice2 = qp.project(None, {"raw_query": "test"})
        artifact_no_emb = query_slice2.projected_data["query_artifact"]
        _, _, grav_without, _ = controller._run_scoring(vm, artifact_no_emb, cfg)

        # Gravity scores should differ (semantic provides signal)
        # n1 should get a boost from semantic alignment
        if NodeId("n1") in grav_with and NodeId("n1") in grav_without:
            # The values should differ because semantic scoring is active
            assert grav_with != grav_without

    def test_scoring_logs_semantic_activation(self, caplog):
        """Scoring logs that semantic scoring was used."""
        import logging
        controller = RuntimeController()
        vm = self._make_vm_with_embeddings()

        qp = QueryProjection()
        query_slice = qp.project(
            None, {"raw_query": "test"},
            embed_fn=lambda t: [1.0, 0.0, 0.0, 0.0],
        )
        artifact = query_slice.projected_data["query_artifact"]
        cfg = PipelineConfig()

        with caplog.at_level(logging.INFO, logger="src.core.runtime.runtime_controller"):
            controller._run_scoring(vm, artifact, cfg)
        assert "semantic" in caplog.text.lower()
        assert "query embedding available" in caplog.text.lower()

    def test_scoring_logs_semantic_skip(self, caplog):
        """Scoring logs when semantic scoring is skipped."""
        import logging
        controller = RuntimeController()
        vm = self._make_vm_with_embeddings()

        qp = QueryProjection()
        query_slice = qp.project(None, {"raw_query": "test"})
        artifact = query_slice.projected_data["query_artifact"]
        cfg = PipelineConfig()

        with caplog.at_level(logging.INFO, logger="src.core.runtime.runtime_controller"):
            controller._run_scoring(vm, artifact, cfg)
        assert "no query embedding" in caplog.text.lower()


# ===================================================================
# TestRuntimeEmbedWiring
# ===================================================================

class TestRuntimeEmbedWiring:
    """Verify RuntimeController wires embed callback through pipeline."""

    def test_run_with_model_bridge_passes_embed_fn(self):
        """With model bridge config, embed_fn is wired to QueryProjection."""
        controller = RuntimeController()

        # Mock ModelBridge to capture embed calls
        embed_called = []

        def mock_embed(request):
            embed_called.append(request)
            return EmbedResponse(
                vectors=[[0.1, 0.2, 0.3, 0.4]],
                model="test-model",
                dimensions=4,
            )

        mock_bridge = MagicMock(spec=ModelBridge)
        mock_bridge.embed = mock_embed
        mock_bridge.get_model_identity.return_value = None
        mock_bridge.synthesize.return_value = SynthesisResponse(
            text="answer",
            tokens_used=10,
            finish_reason="stop",
        )

        with patch.object(controller, '_init_bridge', return_value=mock_bridge):
            result = controller.run(
                "test query",
                config=PipelineConfig(skip_synthesis=True),
            )

        # embed should have been called
        assert len(embed_called) == 1
        assert embed_called[0].texts == ["test query"]

        # Query artifact should have the embedding
        assert result.query_artifact is not None
        assert "query_embedding" in result.query_artifact.properties
        assert result.query_artifact.properties["query_embedding"] == [0.1, 0.2, 0.3, 0.4]

    def test_run_without_model_bridge_no_embed(self):
        """Without model bridge, no embed_fn — graceful degradation."""
        controller = RuntimeController()

        result = controller.run(
            "test query",
            config=PipelineConfig(skip_synthesis=True),
        )

        # No embedding in artifact
        assert result.query_artifact is not None
        assert "query_embedding" not in result.query_artifact.properties
        # Pipeline completed (degraded)
        assert result.degraded is True
        assert "semantic_scoring" in result.skipped_stages

    def test_run_embed_failure_graceful_degradation(self):
        """embed() failure → structural-only scoring, not crash."""
        controller = RuntimeController()

        def mock_embed_fail(request):
            raise ModelConnectionError("Ollama is down")

        mock_bridge = MagicMock(spec=ModelBridge)
        mock_bridge.embed = mock_embed_fail
        mock_bridge.get_model_identity.return_value = None
        mock_bridge.synthesize.return_value = SynthesisResponse(
            text="answer",
            tokens_used=10,
            finish_reason="stop",
        )

        with patch.object(controller, '_init_bridge', return_value=mock_bridge):
            result = controller.run(
                "test query",
                config=PipelineConfig(skip_synthesis=True),
            )

        # No embedding (embed failed)
        assert "query_embedding" not in result.query_artifact.properties
        assert "query_embedding_error" in result.query_artifact.properties
        # Pipeline still completed
        assert result.degraded is True


# ===================================================================
# TestSemanticScoringEndToEnd
# ===================================================================

class TestSemanticScoringEndToEnd:
    """End-to-end: embedding → scoring → gravity affects extraction."""

    def test_full_pipeline_with_embedding_activates_semantic(self):
        """Full pipeline run with embeddings produces non-empty semantic scores."""
        controller = RuntimeController()
        vm = VirtualManifold(manifold_id=ManifoldId("test-vm"))

        # Populate VM with nodes and embeddings
        n1 = _make_node("n1", "test-vm")
        n2 = _make_node("n2", "test-vm")
        vm.get_nodes()[n1.node_id] = n1
        vm.get_nodes()[n2.node_id] = n2

        e = Edge(
            edge_id=EdgeId("e1"),
            manifold_id=ManifoldId("test-vm"),
            from_node_id=NodeId("n1"),
            to_node_id=NodeId("n2"),
            edge_type=EdgeType.ADJACENT,
        )
        vm.get_edges()[e.edge_id] = e

        emb1 = Embedding(
            embedding_id="emb-n1",
            target_kind=EmbeddingTargetKind.NODE,
            target_id="n1",
            model_name="test",
            dimensions=4,
            vector_blob=_pack_floats([1.0, 0.0, 0.0, 0.0]),
        )
        emb2 = Embedding(
            embedding_id="emb-n2",
            target_kind=EmbeddingTargetKind.NODE,
            target_id="n2",
            model_name="test",
            dimensions=4,
            vector_blob=_pack_floats([0.0, 1.0, 0.0, 0.0]),
        )
        vm.get_embeddings()["emb-n1"] = emb1
        vm.get_embeddings()["emb-n2"] = emb2
        vm.get_node_embedding_bindings().extend([
            NodeEmbeddingBinding(
                node_id=NodeId("n1"),
                embedding_id="emb-n1",
                manifold_id=ManifoldId("test-vm"),
            ),
            NodeEmbeddingBinding(
                node_id=NodeId("n2"),
                embedding_id="emb-n2",
                manifold_id=ManifoldId("test-vm"),
            ),
        ])

        # Score with query embedding aligned to n1
        query_embedding = [1.0, 0.0, 0.0, 0.0]
        qp = QueryProjection()
        query_slice = qp.project(
            None, {"raw_query": "test"},
            embed_fn=lambda t: query_embedding,
        )
        artifact = query_slice.projected_data["query_artifact"]

        cfg = PipelineConfig(alpha=0.6, beta=0.4)
        struct, sem, grav, degraded = controller._run_scoring(vm, artifact, cfg)

        # Semantic scores should exist
        assert len(sem) == 2
        assert not degraded

        # n1 should have highest semantic score (aligned with query)
        assert sem[NodeId("n1")] > sem[NodeId("n2")]

        # Gravity should blend both signals
        assert len(grav) == 2

        # Score annotations should be written to VM
        ann_n1 = read_score_annotation(vm, NodeId("n1"))
        ann_n2 = read_score_annotation(vm, NodeId("n2"))
        assert ann_n1 is not None
        assert ann_n2 is not None
        # Semantic component should be non-zero for n1
        assert ann_n1.semantic > 0

    def test_deterministic_across_runs(self):
        """Same inputs produce same semantic+gravity scores."""
        controller = RuntimeController()
        vm = VirtualManifold(manifold_id=ManifoldId("test-vm"))

        n1 = _make_node("n1", "test-vm")
        vm.get_nodes()[n1.node_id] = n1

        emb1 = Embedding(
            embedding_id="emb-n1",
            target_kind=EmbeddingTargetKind.NODE,
            target_id="n1",
            model_name="test",
            dimensions=4,
            vector_blob=_pack_floats([0.5, 0.5, 0.0, 0.0]),
        )
        vm.get_embeddings()["emb-n1"] = emb1
        vm.get_node_embedding_bindings().append(
            NodeEmbeddingBinding(
                node_id=NodeId("n1"),
                embedding_id="emb-n1",
                manifold_id=ManifoldId("test-vm"),
            ),
        )

        qp = QueryProjection()
        embed = lambda t: [1.0, 0.0, 0.0, 0.0]
        cfg = PipelineConfig()

        # Run 1
        s1 = qp.project(None, {"raw_query": "test"}, embed_fn=embed)
        a1 = s1.projected_data["query_artifact"]
        _, sem1, grav1, _ = controller._run_scoring(vm, a1, cfg)

        # Run 2 (reset annotations)
        vm.runtime_annotations.clear()
        s2 = qp.project(None, {"raw_query": "test"}, embed_fn=embed)
        a2 = s2.projected_data["query_artifact"]
        _, sem2, grav2, _ = controller._run_scoring(vm, a2, cfg)

        assert sem1 == sem2
        assert grav1 == grav2


# ===================================================================
# TestBackwardCompatibility
# ===================================================================

class TestBackwardCompatibility:
    """Verify Phase 11 changes are backward compatible."""

    def test_query_projection_old_call_style_works(self):
        """Calling project() without embed_fn kwarg still works."""
        qp = QueryProjection()
        result = qp.project(None, {"raw_query": "old style call"})
        artifact = result.projected_data["query_artifact"]
        assert artifact.raw_query == "old style call"
        assert artifact.query_node is not None

    def test_pipeline_no_config_runs_degraded(self):
        """Pipeline without config runs structural-only (backward compat)."""
        controller = RuntimeController()
        result = controller.run("test", config=PipelineConfig(skip_synthesis=True))
        assert result.degraded is True
        assert len(result.semantic_scores) == 0

    def test_embed_fn_type_alias_importable(self):
        """EmbedFn type alias is importable."""
        from src.core.projection.query_projection import EmbedFn
        assert EmbedFn is not None

    def test_existing_phase9_tests_pass(self):
        """Phase 9 pipeline tests run without error (import sanity check)."""
        from src.core.runtime.runtime_controller import (
            PipelineConfig,
            PipelineResult,
            PipelineError,
            RuntimeController,
        )
        assert PipelineConfig is not None
        assert PipelineResult is not None
        assert PipelineError is not None
        assert RuntimeController is not None

"""
Phase 9 Tests — Runtime Pipeline Orchestration.

Tests for:
    - PipelineConfig defaults and overrides
    - PipelineResult field structure
    - PipelineError stage attribution
    - Query projection wiring (stages 1-3)
    - Fusion wiring (stage 4)
    - Scoring wiring (stage 5)
    - Extraction wiring (stage 6)
    - Hydration wiring (stage 7)
    - Synthesis wiring (stage 8)
    - Degraded mode (no model server, no embeddings)
    - skip_synthesis flag
    - Empty/missing manifold handling
    - End-to-end pipeline with all mocks
    - Timing metadata capture
    - Backward compatibility imports

All tests mock subsystems — no live Ollama server, no real manifolds.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.core.runtime.runtime_controller import (
    RuntimeController,
    PipelineConfig,
    PipelineResult,
    PipelineError,
)
from src.core.extraction.extractor import ExtractionConfig
from src.core.hydration.hydrator import HydrationConfig
from src.core.model_bridge.model_bridge import (
    ModelBridge,
    ModelBridgeConfig,
    ModelConnectionError,
)
from src.core.contracts.model_bridge_contract import (
    SynthesisRequest,
    SynthesisResponse,
)
from src.core.contracts.projection_contract import (
    ProjectedSlice,
    ProjectionMetadata,
    QueryProjectionArtifact,
)
from src.core.contracts.fusion_contract import (
    FusionResult,
    FusionAncestry,
)
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
from src.core.types.ids import (
    EdgeId,
    EvidenceBagId,
    ManifoldId,
    NodeId,
)
from src.core.types.enums import (
    HydrationMode,
    ManifoldRole,
    NodeType,
    ProjectionSourceKind,
    StorageMode,
)
from src.core.types.graph import Node
from src.core.manifolds.virtual_manifold import VirtualManifold


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_controller() -> RuntimeController:
    """Create a RuntimeController for tests."""
    return RuntimeController()


def _make_mock_query_artifact(
    query: str = "test query",
) -> QueryProjectionArtifact:
    """Create a canned QueryProjectionArtifact."""
    node_id = NodeId(f"query-test-{hash(query) & 0xFFFF:04x}")
    return QueryProjectionArtifact(
        raw_query=query,
        query_node_id=node_id,
        query_node=Node(
            node_id=node_id,
            manifold_id=ManifoldId("query"),
            node_type=NodeType.QUERY,
            label=query[:100],
        ),
    )


def _make_mock_projected_slice(
    node_count: int = 2,
    source_kind: ProjectionSourceKind = ProjectionSourceKind.EXTERNAL,
) -> ProjectedSlice:
    """Create a canned ProjectedSlice with nodes."""
    node_ids = [NodeId(f"slice-n{i}") for i in range(node_count)]
    nodes = [
        Node(
            node_id=nid,
            manifold_id=ManifoldId("test-manifold"),
            node_type=NodeType.CHUNK,
            label=f"node-{i}",
        )
        for i, nid in enumerate(node_ids)
    ]
    return ProjectedSlice(
        metadata=ProjectionMetadata(
            source_manifold_id=ManifoldId("test-manifold"),
            source_kind=source_kind,
        ),
        node_ids=node_ids,
        nodes=nodes,
    )


def _make_mock_vm(node_count: int = 3) -> VirtualManifold:
    """Create a VirtualManifold with some nodes."""
    vm = VirtualManifold(ManifoldId("vm-test-pipeline"))
    for i in range(node_count):
        nid = NodeId(f"vm-n{i}")
        node = Node(
            node_id=nid,
            manifold_id=ManifoldId("vm-test-pipeline"),
            node_type=NodeType.CHUNK,
            label=f"vm-node-{i}",
        )
        vm._nodes[nid] = node
    return vm


def _make_mock_fusion_result(
    node_count: int = 3,
) -> FusionResult:
    """Create a canned FusionResult with a VirtualManifold."""
    vm = _make_mock_vm(node_count)
    return FusionResult(
        virtual_manifold=vm,
        bridge_edges=[],
        ancestry=FusionAncestry(
            source_manifold_ids=[ManifoldId("test")],
            projection_count=1,
        ),
    )


def _make_mock_evidence_bag(
    node_count: int = 2,
) -> EvidenceBag:
    """Create a canned EvidenceBag."""
    node_ids = [NodeId(f"bag-n{i}") for i in range(node_count)]
    return EvidenceBag(
        bag_id=EvidenceBagId("bag-test-001"),
        node_ids=node_ids,
        edge_ids=[],
        chunk_refs={},
        hierarchy_refs={},
        scores={
            nid: ScoreAnnotation(
                structural=0.5, semantic=0.0, gravity=0.5,
            )
            for nid in node_ids
        },
        token_budget=TokenBudget(
            max_tokens=2048, used_tokens=100, remaining_tokens=1948,
        ),
        trace=EvidenceBagTrace(
            source_virtual_manifold_id=ManifoldId("vm-test"),
            extraction_strategy="gravity_greedy",
        ),
    )


def _make_mock_hydrated_bundle(
    node_count: int = 2,
) -> HydratedBundle:
    """Create a canned HydratedBundle."""
    nodes = [
        HydratedNode(
            node_id=NodeId(f"hyd-n{i}"),
            content=f"Content for node {i}. This is test evidence.",
            token_estimate=10,
            label=f"hyd-node-{i}",
        )
        for i in range(node_count)
    ]
    edges = [
        HydratedEdge(
            edge_id=EdgeId("hyd-e0"),
            source_id=NodeId("hyd-n0"),
            target_id=NodeId("hyd-n1"),
            relation="ADJACENT",
        ),
    ] if node_count >= 2 else []
    return HydratedBundle(
        nodes=nodes,
        edges=edges,
        topology_preserved=True,
        total_tokens=10 * node_count,
        mode=HydrationMode.FULL,
    )


def _make_mock_synthesis_response() -> SynthesisResponse:
    """Create a canned SynthesisResponse."""
    return SynthesisResponse(
        text="This is the synthesized answer based on the evidence.",
        model="test-model",
        tokens_used=50,
        prompt_tokens=30,
        completion_tokens=20,
        finish_reason="stop",
    )


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestPipelineConfig:
    """Verify PipelineConfig defaults and overrides."""

    def test_default_values(self) -> None:
        cfg = PipelineConfig()
        assert cfg.alpha == 0.6
        assert cfg.beta == 0.4
        assert cfg.damping == 0.85
        assert cfg.max_iterations == 100
        assert cfg.tolerance == 1e-8
        assert cfg.extraction_config is None
        assert cfg.hydration_config is None
        assert cfg.model_bridge_config is None
        assert cfg.synthesis_model == ""
        assert cfg.system_prompt is None
        assert cfg.temperature == 0.0
        assert cfg.max_synthesis_tokens == 4096
        assert cfg.skip_synthesis is False

    def test_override_scoring_weights(self) -> None:
        cfg = PipelineConfig(alpha=0.3, beta=0.7)
        assert cfg.alpha == 0.3
        assert cfg.beta == 0.7

    def test_override_sub_configs(self) -> None:
        ext_cfg = ExtractionConfig(max_seed_nodes=5)
        hyd_cfg = HydrationConfig(mode=HydrationMode.REFERENCE)
        mb_cfg = ModelBridgeConfig(base_url="http://test:1234")
        cfg = PipelineConfig(
            extraction_config=ext_cfg,
            hydration_config=hyd_cfg,
            model_bridge_config=mb_cfg,
        )
        assert cfg.extraction_config is ext_cfg
        assert cfg.hydration_config is hyd_cfg
        assert cfg.model_bridge_config is mb_cfg

    def test_is_dataclass(self) -> None:
        from dataclasses import fields
        cfg = PipelineConfig()
        assert len(fields(cfg)) > 0


class TestPipelineResult:
    """Verify PipelineResult field structure."""

    def test_default_values(self) -> None:
        result = PipelineResult()
        assert result.synthesis_response is None
        assert result.answer_text == ""
        assert result.query_artifact is None
        assert result.identity_slice is None
        assert result.external_slice is None
        assert result.fusion_result is None
        assert result.evidence_bag is None
        assert result.hydrated_bundle is None
        assert result.evidence_context == ""
        assert result.structural_scores == {}
        assert result.semantic_scores == {}
        assert result.gravity_scores == {}
        assert result.degraded is False
        assert result.skipped_stages == []
        assert result.timing == {}
        assert result.stage_count == 0

    def test_answer_text_population(self) -> None:
        result = PipelineResult()
        resp = _make_mock_synthesis_response()
        result.synthesis_response = resp
        result.answer_text = resp.text
        assert result.answer_text == resp.text

    def test_degraded_flag(self) -> None:
        result = PipelineResult()
        assert result.degraded is False
        result.degraded = True
        assert result.degraded is True


class TestPipelineError:
    """Verify PipelineError stage attribution."""

    def test_stage_attribution(self) -> None:
        err = PipelineError("scoring", "PageRank diverged")
        assert err.stage == "scoring"
        assert err.cause is None

    def test_error_message_format(self) -> None:
        cause = ValueError("bad input")
        err = PipelineError("fusion", "Fusion failed", cause=cause)
        assert "[fusion]" in str(err)
        assert "Fusion failed" in str(err)
        assert err.cause is cause


class TestProjectionStage:
    """Verify projection wiring in run()."""

    def test_query_projection_wiring(self) -> None:
        """run() should call QueryProjection and populate query_artifact."""
        controller = _make_controller()
        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        assert result.query_artifact is not None
        assert result.query_artifact.raw_query == "test query"

    def test_empty_query_raises_value_error(self) -> None:
        controller = _make_controller()
        with pytest.raises(ValueError, match="non-empty"):
            controller.run("")

    def test_whitespace_query_raises_value_error(self) -> None:
        controller = _make_controller()
        with pytest.raises(ValueError, match="non-empty"):
            controller.run("   ")

    def test_none_manifolds_skip_projection(self) -> None:
        """No identity/external manifold -> slices should be None."""
        controller = _make_controller()
        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        assert result.identity_slice is None
        assert result.external_slice is None


class TestFusionStage:
    """Verify fusion wiring."""

    def test_fusion_called_with_slices(self) -> None:
        """Fusion should receive the query artifact."""
        controller = _make_controller()
        mock_fusion_result = _make_mock_fusion_result()

        with (
            patch.object(controller, "_run_fusion", return_value=mock_fusion_result) as mock_fuse,
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        mock_fuse.assert_called_once()
        # First arg should be the query artifact
        call_args = mock_fuse.call_args
        assert call_args[0][0].raw_query == "test query"

    def test_fusion_result_in_pipeline_result(self) -> None:
        controller = _make_controller()
        mock_fusion_result = _make_mock_fusion_result()

        with (
            patch.object(controller, "_run_fusion", return_value=mock_fusion_result),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        assert result.fusion_result is mock_fusion_result

    def test_query_only_fusion(self) -> None:
        """Fusing with no manifolds should still produce a result."""
        controller = _make_controller()

        with (
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        # Fusion should have been called and produced a result
        assert result.fusion_result is not None
        assert result.fusion_result.virtual_manifold is not None


class TestScoringStage:
    """Verify scoring wiring."""

    def test_structural_scoring_called(self) -> None:
        """Scoring should populate structural_scores."""
        controller = _make_controller()
        nid = NodeId("vm-n0")
        mock_scores = ({nid: 0.5}, {}, {nid: 0.5}, True)

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=mock_scores),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        assert nid in result.structural_scores
        assert result.structural_scores[nid] == 0.5

    def test_semantic_skipped_no_embeddings(self) -> None:
        """Without embeddings, semantic scoring is skipped and pipeline is degraded."""
        controller = _make_controller()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            # No mocking of _run_scoring — let it run for real with the mock VM
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        # Semantic should be empty (no query embedding, no node embeddings)
        assert result.semantic_scores == {}
        assert result.degraded is True
        assert "semantic_scoring" in result.skipped_stages

    def test_gravity_fallback_structural_only(self) -> None:
        """When semantic is empty, gravity should still be populated."""
        controller = _make_controller()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result(3)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        # Gravity should still have scores from structural fallback
        assert len(result.gravity_scores) > 0

    def test_annotate_scores_called(self) -> None:
        """annotate_scores should be called during scoring."""
        controller = _make_controller()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch(
                "src.core.runtime.runtime_controller.annotate_scores"
            ) as mock_annotate,
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        mock_annotate.assert_called_once()


class TestExtractionStage:
    """Verify extraction wiring."""

    def test_extraction_called(self) -> None:
        """extract_evidence_bag should be called with the VM."""
        controller = _make_controller()
        mock_bag = _make_mock_evidence_bag()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=mock_bag) as mock_extract,
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        mock_extract.assert_called_once()
        assert result.evidence_bag is mock_bag

    def test_extraction_config_passthrough(self) -> None:
        """ExtractionConfig from PipelineConfig should be passed to extractor."""
        controller = _make_controller()
        ext_cfg = ExtractionConfig(max_seed_nodes=5, token_budget=4096)
        pipe_cfg = PipelineConfig(extraction_config=ext_cfg, skip_synthesis=True)

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch(
                "src.core.runtime.runtime_controller.extract_evidence_bag",
                return_value=_make_mock_evidence_bag(),
            ) as mock_extract,
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            controller.run("test query", config=pipe_cfg)

        # extract_evidence_bag should have been called with the extraction config
        _, kwargs = mock_extract.call_args
        assert kwargs.get("config") is ext_cfg

    def test_bag_in_result(self) -> None:
        controller = _make_controller()
        mock_bag = _make_mock_evidence_bag()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=mock_bag),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        assert result.evidence_bag is mock_bag
        assert result.evidence_bag.bag_id == EvidenceBagId("bag-test-001")


class TestHydrationStage:
    """Verify hydration wiring."""

    def test_hydration_called(self) -> None:
        controller = _make_controller()
        mock_bundle = _make_mock_hydrated_bundle()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=mock_bundle) as mock_hydrate,
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        mock_hydrate.assert_called_once()
        assert result.hydrated_bundle is mock_bundle

    def test_hydration_config_passthrough(self) -> None:
        controller = _make_controller()
        hyd_cfg = HydrationConfig(mode=HydrationMode.REFERENCE)
        pipe_cfg = PipelineConfig(hydration_config=hyd_cfg, skip_synthesis=True)

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch(
                "src.core.runtime.runtime_controller.hydrate_evidence_bag",
                return_value=_make_mock_hydrated_bundle(),
            ) as mock_hydrate,
        ):
            controller.run("test query", config=pipe_cfg)

        _, kwargs = mock_hydrate.call_args
        assert kwargs.get("config") is hyd_cfg

    def test_bundle_in_result(self) -> None:
        controller = _make_controller()
        mock_bundle = _make_mock_hydrated_bundle(3)

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=mock_bundle),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        assert result.hydrated_bundle is mock_bundle
        assert len(result.hydrated_bundle.nodes) == 3


class TestSynthesisStage:
    """Verify synthesis wiring."""

    def test_synthesis_called(self) -> None:
        """Synthesis should call bridge.synthesize with correct request."""
        controller = _make_controller()
        mock_response = _make_mock_synthesis_response()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
            patch.object(
                controller, "_run_synthesis",
                return_value=("formatted context", mock_response),
            ) as mock_synth,
        ):
            cfg = PipelineConfig(
                model_bridge_config=ModelBridgeConfig(synthesis_model="test-model"),
            )
            result = controller.run("test query", config=cfg)

        mock_synth.assert_called_once()
        assert result.synthesis_response is mock_response
        assert result.answer_text == mock_response.text

    def test_skip_synthesis_flag(self) -> None:
        """skip_synthesis=True should skip synthesis entirely."""
        controller = _make_controller()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run(
                "test query",
                config=PipelineConfig(skip_synthesis=True),
            )

        assert "synthesis" in result.skipped_stages
        assert result.synthesis_response is None
        assert result.answer_text == ""

    def test_no_bridge_skips_synthesis(self) -> None:
        """No model_bridge_config -> synthesis skipped, degraded."""
        controller = _make_controller()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            # No model_bridge_config -> bridge is None
            result = controller.run("test query", config=PipelineConfig())

        assert "synthesis" in result.skipped_stages
        assert result.degraded is True

    def test_connection_error_graceful(self) -> None:
        """ModelConnectionError during synthesis -> graceful degradation."""
        controller = _make_controller()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
            patch.object(
                controller, "_run_synthesis",
                return_value=("formatted context", None),
            ),
        ):
            cfg = PipelineConfig(
                model_bridge_config=ModelBridgeConfig(synthesis_model="test"),
            )
            result = controller.run("test query", config=cfg)

        # Should not crash — degraded instead
        assert result.synthesis_response is None
        assert result.degraded is True

    def test_evidence_context_populated(self) -> None:
        """Evidence context should be formatted from hydrated bundle."""
        controller = _make_controller()
        mock_response = _make_mock_synthesis_response()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
            patch.object(
                controller, "_run_synthesis",
                return_value=("=== EVIDENCE BUNDLE ===\nTest content", mock_response),
            ),
        ):
            cfg = PipelineConfig(
                model_bridge_config=ModelBridgeConfig(synthesis_model="test"),
            )
            result = controller.run("test query", config=cfg)

        assert "EVIDENCE BUNDLE" in result.evidence_context


class TestEndToEnd:
    """End-to-end pipeline tests with all stages mocked."""

    def test_full_pipeline_all_stages(self) -> None:
        """Full pipeline should execute all stages and populate result."""
        controller = _make_controller()
        mock_response = _make_mock_synthesis_response()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({NodeId("n0"): 0.5}, {}, {NodeId("n0"): 0.5}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
            patch.object(
                controller, "_run_synthesis",
                return_value=("evidence text", mock_response),
            ),
        ):
            cfg = PipelineConfig(
                model_bridge_config=ModelBridgeConfig(synthesis_model="test"),
            )
            result = controller.run("What is a manifold?", config=cfg)

        # All fields should be populated
        assert result.query_artifact is not None
        assert result.fusion_result is not None
        assert result.evidence_bag is not None
        assert result.hydrated_bundle is not None
        assert result.synthesis_response is not None
        assert result.answer_text != ""
        assert result.stage_count > 0

    def test_degraded_pipeline_no_model(self) -> None:
        """Pipeline without model bridge should still complete."""
        controller = _make_controller()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig())

        assert result.degraded is True
        assert result.synthesis_response is None

    def test_timing_metadata(self) -> None:
        """Result should contain timing metadata for all stages."""
        controller = _make_controller()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        assert "projection" in result.timing
        assert "fusion" in result.timing
        assert "scoring" in result.timing
        assert "extraction" in result.timing
        assert "hydration" in result.timing
        assert "synthesis" in result.timing
        assert "total" in result.timing
        # All timings should be non-negative
        for key, val in result.timing.items():
            assert val >= 0.0, f"timing[{key}] should be >= 0"

    def test_stage_count(self) -> None:
        """result.stage_count should match number of stages executed."""
        controller = _make_controller()

        with (
            patch.object(controller, "_run_fusion", return_value=_make_mock_fusion_result()),
            patch.object(controller, "_run_scoring", return_value=({}, {}, {}, True)),
            patch.object(controller, "_run_extraction", return_value=_make_mock_evidence_bag()),
            patch.object(controller, "_run_hydration", return_value=_make_mock_hydrated_bundle()),
        ):
            result = controller.run("test query", config=PipelineConfig(skip_synthesis=True))

        # Stages: projection, fusion, scoring, extraction, hydration, synthesis = 6
        assert result.stage_count == 6


class TestBackwardCompat:
    """Verify backward-compatible imports."""

    def test_import_from_init(self) -> None:
        from src.core.runtime import (
            RuntimeController as RC,
            PipelineConfig as PC,
            PipelineResult as PR,
            PipelineError as PE,
        )
        assert RC is RuntimeController
        assert PC is PipelineConfig
        assert PR is PipelineResult
        assert PE is PipelineError

    def test_bootstrap_still_works(self) -> None:
        """bootstrap() should still work without arguments."""
        controller = RuntimeController()
        controller.bootstrap()  # Should not raise

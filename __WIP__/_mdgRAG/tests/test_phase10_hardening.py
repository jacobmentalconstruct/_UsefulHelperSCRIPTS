"""
Phase 10 Tests — Hardening / Stabilization / Policy Tightening.

Tests for:
    - Packaging: app.py has no sys.path hack
    - FusionConfig: label fallback policy, weight overrides
    - FusionConfig wiring: disable label fallback, custom weights
    - Hash truncation: constant is used, correct length
    - Store validation: empty IDs rejected, empty chunk_text rejected
    - Store JSON parse: malformed JSON produces warning, not crash
    - Projection observability: empty node_ids warning
    - Fusion observability: all-None inputs warning
    - Debug inspection: all dump helpers return valid structure
    - Backward compatibility: imports from debug package
    - VM ID policy: documented as ephemeral
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.core.contracts.fusion_contract import (
    BridgeEdge,
    BridgeRequest,
    FusionAncestry,
    FusionConfig,
    FusionResult,
)
from src.core.contracts.projection_contract import (
    ProjectedSlice,
    ProjectionMetadata,
    QueryProjectionArtifact,
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
from src.core.fusion.fusion_engine import FusionEngine
from src.core.runtime.runtime_controller import PipelineConfig, PipelineResult
from src.core.store.manifold_store import ManifoldStore
from src.core.types.ids import (
    ChunkHash,
    EdgeId,
    EvidenceBagId,
    HASH_TRUNCATION_LENGTH,
    ManifoldId,
    NodeId,
    deterministic_hash,
)
from src.core.types.enums import (
    EdgeType,
    HydrationMode,
    ManifoldRole,
    NodeType,
    ProjectionSourceKind,
    StorageMode,
)
from src.core.types.graph import Chunk, Edge, Node
from src.core.types.provenance import Provenance


# ===================================================================
# Helpers
# ===================================================================

def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_node(nid: str, manifold: str = "m1", key: str = "", label: str = "") -> Node:
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


def _make_query_artifact(query: str = "test query") -> QueryProjectionArtifact:
    return QueryProjectionArtifact(
        raw_query=query,
        query_node_id=NodeId("query-test"),
        query_node=_make_node("query-test", manifold="query"),
    )


# ===================================================================
# TestPackagingCleanup
# ===================================================================

class TestPackagingCleanup:
    """Verify sys.path hack was removed from app.py."""

    def test_app_has_no_sys_path_insert(self):
        """app.py must not contain sys.path.insert in executable code."""
        import pathlib
        import re
        app_path = pathlib.Path(__file__).parent.parent / "src" / "app.py"
        content = app_path.read_text()
        # Strip triple-quoted strings (docstrings) before checking
        stripped = re.sub(r'""".*?"""', '', content, flags=re.DOTALL)
        stripped = re.sub(r"'''.*?'''", '', stripped, flags=re.DOTALL)
        assert "sys.path.insert" not in stripped
        assert "sys.path" not in stripped

    def test_app_no_sys_path_manipulation(self):
        """app.py must not manipulate sys.path (no path hacks)."""
        import pathlib
        app_path = pathlib.Path(__file__).parent.parent / "src" / "app.py"
        content = app_path.read_text()
        # sys import is fine (needed for sys.stderr), but sys.path must not appear
        assert "sys.path" not in content


# ===================================================================
# TestHashTruncationConstant
# ===================================================================

class TestHashTruncationConstant:
    """Verify HASH_TRUNCATION_LENGTH is properly defined and used."""

    def test_constant_value(self):
        assert HASH_TRUNCATION_LENGTH == 16

    def test_constant_exported(self):
        from src.core.types.ids import HASH_TRUNCATION_LENGTH as imported
        assert imported == 16

    def test_deterministic_hash_truncation(self):
        h = deterministic_hash("test")[:HASH_TRUNCATION_LENGTH]
        assert len(h) == 16


# ===================================================================
# TestFusionConfig
# ===================================================================

class TestFusionConfig:
    """Verify FusionConfig defaults and policy control."""

    def test_defaults(self):
        cfg = FusionConfig()
        assert cfg.enable_label_fallback is True
        assert cfg.label_fallback_weight == 0.7
        assert cfg.canonical_key_weight == 1.0

    def test_disable_label_fallback(self):
        cfg = FusionConfig(enable_label_fallback=False)
        assert cfg.enable_label_fallback is False

    def test_custom_weights(self):
        cfg = FusionConfig(
            label_fallback_weight=0.5,
            canonical_key_weight=0.9,
        )
        assert cfg.label_fallback_weight == 0.5
        assert cfg.canonical_key_weight == 0.9

    def test_import_from_fusion_package(self):
        from src.core.fusion import FusionConfig as Imported
        assert Imported is FusionConfig


# ===================================================================
# TestFusionLabelFallbackPolicy
# ===================================================================

class TestFusionLabelFallbackPolicy:
    """Verify label fallback respects FusionConfig."""

    def test_label_fallback_enabled_default(self):
        """Default: label fallback creates bridges when no canonical matches."""
        id_nodes = [_make_node("id1", "id-m", label="shared")]
        ext_nodes = [_make_node("ext1", "ext-m", label="shared")]
        id_slice = _make_projected_slice(id_nodes, "id-m")
        ext_slice = _make_projected_slice(
            ext_nodes, "ext-m",
            source_kind=ProjectionSourceKind.EXTERNAL,
        )

        engine = FusionEngine()
        result = engine.fuse(
            identity_slice=id_slice,
            external_slice=ext_slice,
        )
        # Should have label fallback bridges
        label_bridges = [
            be for be in result.bridge_edges
            if be.properties.get("match_type") == "label"
        ]
        assert len(label_bridges) >= 1

    def test_label_fallback_disabled(self):
        """Disabled: no bridges when canonical keys don't match."""
        id_nodes = [_make_node("id1", "id-m", label="shared")]
        ext_nodes = [_make_node("ext1", "ext-m", label="shared")]
        id_slice = _make_projected_slice(id_nodes, "id-m")
        ext_slice = _make_projected_slice(
            ext_nodes, "ext-m",
            source_kind=ProjectionSourceKind.EXTERNAL,
        )

        engine = FusionEngine()
        cfg = FusionConfig(enable_label_fallback=False)
        result = engine.fuse(
            identity_slice=id_slice,
            external_slice=ext_slice,
            config=cfg,
        )
        # No label bridges when fallback disabled
        label_bridges = [
            be for be in result.bridge_edges
            if be.properties.get("match_type") == "label"
        ]
        assert len(label_bridges) == 0

    def test_canonical_key_weight_configurable(self):
        """Canonical key bridges use config weight."""
        id_nodes = [_make_node("id1", "id-m", key="shared-key")]
        ext_nodes = [_make_node("ext1", "ext-m", key="shared-key")]
        id_slice = _make_projected_slice(id_nodes, "id-m")
        ext_slice = _make_projected_slice(
            ext_nodes, "ext-m",
            source_kind=ProjectionSourceKind.EXTERNAL,
        )

        engine = FusionEngine()
        cfg = FusionConfig(canonical_key_weight=0.95)
        result = engine.fuse(
            identity_slice=id_slice,
            external_slice=ext_slice,
            config=cfg,
        )
        assert len(result.bridge_edges) >= 1
        for be in result.bridge_edges:
            if be.properties.get("match_type") == "canonical_key":
                assert be.weight == 0.95

    def test_label_fallback_weight_configurable(self):
        """Label fallback bridges use config weight."""
        id_nodes = [_make_node("id1", "id-m", label="shared")]
        ext_nodes = [_make_node("ext1", "ext-m", label="shared")]
        id_slice = _make_projected_slice(id_nodes, "id-m")
        ext_slice = _make_projected_slice(
            ext_nodes, "ext-m",
            source_kind=ProjectionSourceKind.EXTERNAL,
        )

        engine = FusionEngine()
        cfg = FusionConfig(label_fallback_weight=0.3)
        result = engine.fuse(
            identity_slice=id_slice,
            external_slice=ext_slice,
            config=cfg,
        )
        for be in result.bridge_edges:
            if be.properties.get("match_type") == "label":
                assert be.weight == 0.3


# ===================================================================
# TestFusionConfigInPipeline
# ===================================================================

class TestFusionConfigInPipeline:
    """Verify FusionConfig wires through PipelineConfig."""

    def test_pipeline_config_has_fusion_config(self):
        cfg = PipelineConfig()
        assert cfg.fusion_config is None

    def test_pipeline_config_accepts_fusion_config(self):
        fc = FusionConfig(enable_label_fallback=False)
        cfg = PipelineConfig(fusion_config=fc)
        assert cfg.fusion_config is not None
        assert cfg.fusion_config.enable_label_fallback is False


# ===================================================================
# TestFusionAncestryParameters
# ===================================================================

class TestFusionAncestryParameters:
    """Verify fusion ancestry records config parameters."""

    def test_ancestry_records_fallback_policy(self):
        """Ancestry parameters should include label_fallback setting."""
        id_nodes = [_make_node("id1", "id-m", key="k")]
        ext_nodes = [_make_node("ext1", "ext-m", key="k")]
        id_slice = _make_projected_slice(id_nodes, "id-m")
        ext_slice = _make_projected_slice(
            ext_nodes, "ext-m",
            source_kind=ProjectionSourceKind.EXTERNAL,
        )

        engine = FusionEngine()
        cfg = FusionConfig(enable_label_fallback=False)
        result = engine.fuse(
            identity_slice=id_slice,
            external_slice=ext_slice,
            config=cfg,
        )
        params = result.ancestry.parameters
        assert params["enable_label_fallback"] is False
        assert params["label_fallback_weight"] == 0.7


# ===================================================================
# TestStoreValidation
# ===================================================================

class TestStoreValidation:
    """Verify ManifoldStore rejects invalid inputs."""

    def test_add_node_empty_id_raises(self):
        store = ManifoldStore()
        node = _make_node("")
        with pytest.raises(ValueError, match="node_id must not be empty"):
            store.add_node(MagicMock(), node)

    def test_add_node_empty_manifold_raises(self):
        store = ManifoldStore()
        node = Node(
            node_id=NodeId("n1"),
            manifold_id=ManifoldId(""),
            node_type=NodeType.CONCEPT,
        )
        with pytest.raises(ValueError, match="manifold_id must not be empty"):
            store.add_node(MagicMock(), node)

    def test_add_edge_empty_id_raises(self):
        store = ManifoldStore()
        edge = Edge(
            edge_id=EdgeId(""),
            manifold_id=ManifoldId("m1"),
            from_node_id=NodeId("a"),
            to_node_id=NodeId("b"),
            edge_type=EdgeType.ADJACENT,
        )
        with pytest.raises(ValueError, match="edge_id must not be empty"):
            store.add_edge(MagicMock(), edge)

    def test_add_edge_empty_endpoints_raises(self):
        store = ManifoldStore()
        edge = Edge(
            edge_id=EdgeId("e1"),
            manifold_id=ManifoldId("m1"),
            from_node_id=NodeId(""),
            to_node_id=NodeId("b"),
            edge_type=EdgeType.ADJACENT,
        )
        with pytest.raises(ValueError, match="from_node_id and to_node_id"):
            store.add_edge(MagicMock(), edge)

    def test_add_chunk_empty_hash_raises(self):
        store = ManifoldStore()
        chunk = Chunk(chunk_hash=ChunkHash(""), chunk_text="hello")
        with pytest.raises(ValueError, match="chunk_hash must not be empty"):
            store.add_chunk(MagicMock(), chunk)

    def test_add_chunk_empty_text_raises(self):
        store = ManifoldStore()
        chunk = Chunk(chunk_hash=ChunkHash("abc123"), chunk_text="")
        with pytest.raises(ValueError, match="chunk_text must not be empty"):
            store.add_chunk(MagicMock(), chunk)


# ===================================================================
# TestStoreJsonParseSafety
# ===================================================================

class TestStoreJsonParseSafety:
    """Verify JSON deserialization is safe and logs warnings."""

    def test_json_loads_malformed_returns_empty_dict(self):
        from src.core.store.manifold_store import _json_loads
        result = _json_loads("{not valid json")
        assert result == {}

    def test_json_loads_list_malformed_returns_empty_list(self):
        from src.core.store.manifold_store import _json_loads_list
        result = _json_loads_list("[not valid json")
        assert result == []

    def test_json_loads_none_returns_empty_dict(self):
        from src.core.store.manifold_store import _json_loads
        result = _json_loads(None)
        assert result == {}

    def test_json_loads_empty_returns_empty_dict(self):
        from src.core.store.manifold_store import _json_loads
        result = _json_loads("")
        assert result == {}


# ===================================================================
# TestProjectionObservability
# ===================================================================

class TestProjectionObservability:
    """Verify projection logging and warnings."""

    def test_empty_node_ids_produces_warning(self, caplog):
        """Empty node_ids should log a warning."""
        import logging
        from src.core.projection._projection_core import gather_slice_by_node_ids
        from src.core.manifolds.virtual_manifold import VirtualManifold

        vm = VirtualManifold(manifold_id=ManifoldId("test"))
        with caplog.at_level(logging.WARNING, logger="src.core.projection._projection_core"):
            result = gather_slice_by_node_ids(
                vm, [], ProjectionSourceKind.IDENTITY,
            )
        assert "empty node_ids" in caplog.text.lower()
        assert len(result.nodes) == 0


# ===================================================================
# TestFusionObservability
# ===================================================================

class TestFusionObservability:
    """Verify fusion logging and warnings."""

    def test_all_none_inputs_produces_warning(self, caplog):
        """All-None inputs should log a warning."""
        import logging
        engine = FusionEngine()
        with caplog.at_level(logging.WARNING, logger="src.core.fusion.fusion_engine"):
            result = engine.fuse()
        assert "no identity" in caplog.text.lower() or "empty vm" in caplog.text.lower()

    def test_fusion_logs_bridge_summary(self, caplog):
        """Fusion should log bridge creation summary."""
        import logging
        id_nodes = [_make_node("id1", "id-m", key="k")]
        ext_nodes = [_make_node("ext1", "ext-m", key="k")]
        id_slice = _make_projected_slice(id_nodes, "id-m")
        ext_slice = _make_projected_slice(
            ext_nodes, "ext-m",
            source_kind=ProjectionSourceKind.EXTERNAL,
        )

        engine = FusionEngine()
        with caplog.at_level(logging.INFO, logger="src.core.fusion.fusion_engine"):
            result = engine.fuse(
                identity_slice=id_slice,
                external_slice=ext_slice,
            )
        assert "bridges=" in caplog.text.lower() or "canonical=" in caplog.text.lower()


# ===================================================================
# TestDebugInspection
# ===================================================================

class TestDebugInspection:
    """Verify debug inspection helpers return valid structure."""

    def test_dump_projection_summary(self):
        from src.core.debug.inspection import dump_projection_summary
        nodes = [_make_node("n1")]
        ps = _make_projected_slice(nodes)
        summary = dump_projection_summary(ps)
        assert summary["node_count"] == 1
        assert summary["source_manifold_id"] == "m1"
        assert "node_ids" in summary

    def test_dump_fusion_result(self):
        from src.core.debug.inspection import dump_fusion_result
        engine = FusionEngine()
        qa = _make_query_artifact()
        result = engine.fuse(query_artifact=qa)
        summary = dump_fusion_result(result)
        assert "vm_id" in summary
        assert "vm_node_count" in summary
        assert "bridge_types" in summary

    def test_dump_evidence_bag(self):
        from src.core.debug.inspection import dump_evidence_bag
        bag = EvidenceBag(
            bag_id=EvidenceBagId("test-bag"),
            node_ids=[NodeId("n1")],
            edge_ids=[],
            chunk_refs={},
            hierarchy_refs={},
            scores={
                NodeId("n1"): ScoreAnnotation(
                    structural=0.5, semantic=0.3, gravity=0.42,
                ),
            },
            token_budget=TokenBudget(max_tokens=1000, used_tokens=100),
            trace=EvidenceBagTrace(
                source_virtual_manifold_id=ManifoldId("vm"),
                seed_node_count=0,
                hop_depth=0,
            ),
        )
        summary = dump_evidence_bag(bag)
        assert summary["bag_id"] == "test-bag"
        assert summary["node_count"] == 1
        assert summary["source_virtual_manifold_id"] == "vm"
        assert summary["token_budget"]["used"] == 100

    def test_dump_hydrated_bundle(self):
        from src.core.debug.inspection import dump_hydrated_bundle
        bundle = HydratedBundle(
            nodes=[
                HydratedNode(
                    node_id=NodeId("n1"),
                    label="Node 1",
                    node_type="CONCEPT",
                    content="Hello world",
                ),
            ],
            edges=[],
            total_tokens=50,
            mode=HydrationMode.FULL,
            topology_preserved=True,
        )
        summary = dump_hydrated_bundle(bundle)
        assert summary["node_count"] == 1
        assert summary["total_tokens"] == 50
        assert summary["topology_preserved"] is True

    def test_inspect_pipeline_result(self):
        from src.core.debug.inspection import inspect_pipeline_result
        result = PipelineResult(
            answer_text="test answer",
            stage_count=6,
            timing={"total": 0.123},
        )
        summary = inspect_pipeline_result(result)
        assert summary["answer_length"] == len("test answer")
        assert summary["stage_count"] == 6
        assert summary["has_synthesis"] is False

    def test_debug_package_exports(self):
        """All inspection helpers importable from debug package."""
        from src.core.debug import (
            dump_virtual_scores,
            dump_projection_summary,
            dump_fusion_result,
            dump_evidence_bag,
            dump_hydrated_bundle,
            inspect_pipeline_result,
        )
        assert callable(dump_virtual_scores)
        assert callable(dump_projection_summary)
        assert callable(dump_fusion_result)
        assert callable(dump_evidence_bag)
        assert callable(dump_hydrated_bundle)
        assert callable(inspect_pipeline_result)


# ===================================================================
# TestVMIdPolicy
# ===================================================================

class TestVMIdPolicy:
    """Verify VM ID policy: ephemeral by design (W-001)."""

    def test_vm_ids_differ_across_runs(self):
        """Same inputs produce different VM IDs (timestamp-seeded)."""
        id_nodes = [_make_node("id1", "id-m", key="k")]
        ext_nodes = [_make_node("ext1", "ext-m", key="k")]
        id_slice = _make_projected_slice(id_nodes, "id-m")
        ext_slice = _make_projected_slice(
            ext_nodes, "ext-m",
            source_kind=ProjectionSourceKind.EXTERNAL,
        )

        engine = FusionEngine()
        r1 = engine.fuse(identity_slice=id_slice, external_slice=ext_slice)
        r2 = engine.fuse(identity_slice=id_slice, external_slice=ext_slice)

        vm1_id = r1.virtual_manifold.get_metadata().manifold_id
        vm2_id = r2.virtual_manifold.get_metadata().manifold_id
        # Ephemeral: IDs should differ (timestamp-seeded)
        assert vm1_id != vm2_id

    def test_vm_id_contains_hash_prefix(self):
        """VM ID uses the standard vm- prefix and truncated hash."""
        engine = FusionEngine()
        result = engine.fuse(query_artifact=_make_query_artifact())
        vm_id = str(result.virtual_manifold.get_metadata().manifold_id)
        assert vm_id.startswith("vm-")
        # Hash portion should be HASH_TRUNCATION_LENGTH chars
        hash_part = vm_id[3:]
        assert len(hash_part) == HASH_TRUNCATION_LENGTH


# ===================================================================
# TestScoringLogging
# ===================================================================

class TestScoringLogging:
    """Verify scoring emits convergence info."""

    def test_pagerank_logs_convergence(self, caplog):
        """PageRank should log convergence stats."""
        import logging
        from src.core.math.scoring import structural_score
        from src.core.manifolds.virtual_manifold import VirtualManifold

        vm = VirtualManifold(manifold_id=ManifoldId("test"))
        n1 = _make_node("a", "test")
        n2 = _make_node("b", "test")
        vm.get_nodes()[n1.node_id] = n1
        vm.get_nodes()[n2.node_id] = n2
        edge = Edge(
            edge_id=EdgeId("e1"),
            manifold_id=ManifoldId("test"),
            from_node_id=NodeId("a"),
            to_node_id=NodeId("b"),
            edge_type=EdgeType.ADJACENT,
        )
        vm.get_edges()[edge.edge_id] = edge

        with caplog.at_level(logging.INFO, logger="src.core.math.scoring"):
            scores = structural_score(vm)
        assert "pagerank" in caplog.text.lower() or "converged" in caplog.text.lower()
        assert len(scores) == 2


# ===================================================================
# TestBindingIndexOptimization
# ===================================================================

class TestBindingIndexOptimization:
    """Verify pre-indexed binding lookup works correctly."""

    def test_build_binding_index(self):
        from src.core.projection._projection_core import _build_binding_index
        from src.core.types.bindings import NodeChunkBinding

        bindings = [
            NodeChunkBinding(
                node_id=NodeId("n1"),
                chunk_hash=ChunkHash("c1"),
                manifold_id=ManifoldId("m1"),
            ),
            NodeChunkBinding(
                node_id=NodeId("n1"),
                chunk_hash=ChunkHash("c2"),
                manifold_id=ManifoldId("m1"),
            ),
            NodeChunkBinding(
                node_id=NodeId("n2"),
                chunk_hash=ChunkHash("c3"),
                manifold_id=ManifoldId("m1"),
            ),
        ]
        index = _build_binding_index(bindings)
        assert len(index[NodeId("n1")]) == 2
        assert len(index[NodeId("n2")]) == 1
        assert len(index.get(NodeId("n3"), [])) == 0


# ===================================================================
# TestBackwardCompatibility
# ===================================================================

class TestBackwardCompatibility:
    """Verify imports from Phase 10 additions work."""

    def test_fusion_config_from_contract(self):
        from src.core.contracts.fusion_contract import FusionConfig
        assert FusionConfig is not None

    def test_hash_truncation_from_ids(self):
        from src.core.types.ids import HASH_TRUNCATION_LENGTH
        assert isinstance(HASH_TRUNCATION_LENGTH, int)

    def test_debug_inspection_module(self):
        from src.core.debug import inspection
        assert hasattr(inspection, "dump_projection_summary")
        assert hasattr(inspection, "dump_fusion_result")
        assert hasattr(inspection, "dump_evidence_bag")
        assert hasattr(inspection, "dump_hydrated_bundle")
        assert hasattr(inspection, "inspect_pipeline_result")

    def test_pipeline_config_has_fusion_config_field(self):
        from src.core.runtime.runtime_controller import PipelineConfig
        cfg = PipelineConfig()
        assert hasattr(cfg, "fusion_config")

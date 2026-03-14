"""
Test Imports — verify all scaffold modules import cleanly.

This test catches broken package paths, circular imports, and
missing dependencies early. Every scaffold module must be importable.
"""

import importlib

import pytest

# Every module in the scaffold that should import cleanly
SCAFFOLD_MODULES = [
    # Root
    "src",
    "src.app",
    # Core
    "src.core",
    # Contracts
    "src.core.contracts",
    "src.core.contracts.manifold_contract",
    "src.core.contracts.evidence_bag_contract",
    "src.core.contracts.hydration_contract",
    "src.core.contracts.projection_contract",
    "src.core.contracts.fusion_contract",
    "src.core.contracts.model_bridge_contract",
    # Types
    "src.core.types",
    "src.core.types.ids",
    "src.core.types.enums",
    "src.core.types.graph",
    "src.core.types.provenance",
    "src.core.types.bindings",
    "src.core.types.manifests",
    "src.core.types.runtime_state",
    # Manifolds
    "src.core.manifolds",
    "src.core.manifolds.base_manifold",
    "src.core.manifolds.identity_manifold",
    "src.core.manifolds.external_manifold",
    "src.core.manifolds.virtual_manifold",
    # Factory & Store
    "src.core.factory",
    "src.core.factory.manifold_factory",
    "src.core.store",
    "src.core.store._schema",
    "src.core.store.manifold_store",
    # Projection
    "src.core.projection",
    "src.core.projection._projection_core",
    "src.core.projection.identity_projection",
    "src.core.projection.external_projection",
    "src.core.projection.query_projection",
    # Fusion
    "src.core.fusion",
    "src.core.fusion.fusion_engine",
    # Math
    "src.core.math",
    "src.core.math.scoring",
    "src.core.math.scoring_placeholders",
    "src.core.math.friction",
    "src.core.math.annotator",
    # Debug
    "src.core.debug",
    "src.core.debug.score_dump",
    # Extraction
    "src.core.extraction",
    "src.core.extraction.extractor",
    "src.core.extraction.extractor_placeholder",
    # Hydration
    "src.core.hydration",
    "src.core.hydration.hydrator",
    "src.core.hydration.hydrator_placeholder",
    # Model Bridge
    "src.core.model_bridge",
    "src.core.model_bridge.model_bridge",
    "src.core.model_bridge.deterministic_provider",
    # Training pipeline
    "src.core.training",
    "src.core.training.bpe_trainer",
    "src.core.training.cooccurrence",
    "src.core.training.npmi_matrix",
    "src.core.training.spectral",
    # Ingestion
    "src.core.ingestion",
    "src.core.ingestion.config",
    "src.core.ingestion.detection",
    "src.core.ingestion.chunking",
    "src.core.ingestion.tree_sitter_chunker",
    "src.core.ingestion.graph_builder",
    "src.core.ingestion.ingest",
    # Runtime
    "src.core.runtime",
    "src.core.runtime.runtime_controller",
    # Debug - inspection
    "src.core.debug.inspection",
    # UI (web interface)
    "src.ui",
    "src.ui.server",
    # Adapters
    "src.adapters",
    # Utils
    "src.utils",
    "src.utils.logging_utils",
    "src.utils.file_utils",
]


@pytest.mark.parametrize("module_name", SCAFFOLD_MODULES)
def test_module_imports(module_name: str) -> None:
    """Every scaffold module must import without error."""
    mod = importlib.import_module(module_name)
    assert mod is not None, f"Failed to import {module_name}"

"""
Runtime Controller — pipeline orchestration coordinator.

Ownership: src/core/runtime/runtime_controller.py
    Coordinates the full query-processing pipeline:
    projection -> fusion -> scoring -> extraction -> hydration -> synthesis.

Responsibilities:
    - Wire subsystem calls in correct order
    - Pass typed outputs between pipeline stages
    - Handle degraded mode (no embeddings -> structural-only scoring)
    - Capture timing and trace metadata in PipelineResult
    - Raise PipelineError with clear stage attribution on failures
    - Update RuntimeState lifecycle fields during execution

Design constraints:
    - Stays thin — coordinate, don't accumulate
    - No subsystem logic — calls public APIs only
    - Manifolds must be pre-loaded (via factory) before run()
    - No prompt construction — SynthesisRequest arrives with pre-formatted context
    - Controller wires ModelBridge.embed as a callback into QueryProjection,
      which generates the query embedding for downstream semantic scoring
    - No new ABCs or abstract contracts
    - Provenance preserved, not generated — subsystems own their own provenance

Pipeline position: Top-level orchestrator
    projection -> fusion -> scoring -> extraction -> hydration -> synthesis

Legacy context:
    - Pipeline coordination from Mind2Manager, Mind3Manager, Backend orchestrator
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from src.core.projection.query_projection import QueryProjection
from src.core.projection.identity_projection import IdentityProjection
from src.core.projection.external_projection import ExternalProjection
from src.core.fusion.fusion_engine import FusionEngine
from src.core.math.scoring import structural_score, semantic_score, gravity_score
from src.core.math.annotator import annotate_scores
from src.core.extraction.extractor import ExtractionConfig, extract_evidence_bag
from src.core.hydration.hydrator import (
    HydrationConfig,
    hydrate_evidence_bag,
    format_evidence_bundle,
)
from src.core.model_bridge.model_bridge import (
    ModelBridge,
    ModelBridgeConfig,
    ModelConnectionError,
)
from src.core.contracts.model_bridge_contract import (
    EmbedRequest,
    SynthesisRequest,
    SynthesisResponse,
)
from src.core.contracts.projection_contract import (
    ProjectedSlice,
    QueryProjectionArtifact,
)
from src.core.contracts.fusion_contract import FusionConfig, FusionResult
from src.core.contracts.evidence_bag_contract import EvidenceBag
from src.core.contracts.hydration_contract import HydratedBundle
from src.core.factory.manifold_factory import ManifoldFactory
from src.core.store.manifold_store import ManifoldStore
from src.core.types.ids import NodeId
from src.core.types.runtime_state import RuntimeState
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class PipelineError(Exception):
    """Pipeline-level failure with stage attribution."""

    def __init__(
        self,
        stage: str,
        message: str,
        cause: Optional[Exception] = None,
    ) -> None:
        self.stage = stage
        self.cause = cause
        super().__init__(f"[{stage}] {message}")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    """
    Unified configuration for a pipeline run.

    Bundles sub-configs for each subsystem plus pipeline-level parameters.
    All fields have sensible defaults — callers can override selectively.
    """

    # Scoring weights
    alpha: float = 0.6
    beta: float = 0.4

    # PageRank parameters
    damping: float = 0.85
    max_iterations: int = 100
    tolerance: float = 1e-8

    # Fusion config
    fusion_config: Optional[FusionConfig] = None

    # Extraction config
    extraction_config: Optional[ExtractionConfig] = None

    # Hydration config
    hydration_config: Optional[HydrationConfig] = None

    # Model bridge config
    model_bridge_config: Optional[ModelBridgeConfig] = None

    # Synthesis parameters
    synthesis_model: str = ""
    system_prompt: Optional[str] = None
    temperature: float = 0.0
    max_synthesis_tokens: int = 4096

    # Pipeline behavior
    skip_synthesis: bool = False


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    """
    Complete result of a pipeline run.

    Contains the synthesis response plus every intermediate artifact
    for debugging, inspection, and provenance tracing.
    """

    # Final output
    synthesis_response: Optional[SynthesisResponse] = None
    answer_text: str = ""

    # Intermediate artifacts
    query_artifact: Optional[QueryProjectionArtifact] = None
    identity_slice: Optional[ProjectedSlice] = None
    external_slice: Optional[ProjectedSlice] = None
    fusion_result: Optional[FusionResult] = None
    evidence_bag: Optional[EvidenceBag] = None
    hydrated_bundle: Optional[HydratedBundle] = None
    evidence_context: str = ""

    # Scoring artifacts
    structural_scores: Dict[NodeId, float] = field(default_factory=dict)
    semantic_scores: Dict[NodeId, float] = field(default_factory=dict)
    gravity_scores: Dict[NodeId, float] = field(default_factory=dict)

    # Metadata
    degraded: bool = False
    skipped_stages: List[str] = field(default_factory=list)
    timing: Dict[str, float] = field(default_factory=dict)
    stage_count: int = 0


# ---------------------------------------------------------------------------
# Runtime Controller
# ---------------------------------------------------------------------------

class RuntimeController:
    """
    Pipeline orchestration coordinator.

    Thin controller that wires all subsystems into an executable pipeline.
    Manifolds must be pre-loaded before calling run(). The controller
    calls subsystems but does not implement their algorithms.
    """

    def __init__(self) -> None:
        self._state = RuntimeState()
        self._factory = ManifoldFactory()
        self._store = ManifoldStore()

    # -------------------------------------------------------------------
    # Bootstrap (unchanged from Phase 1)
    # -------------------------------------------------------------------

    def bootstrap(self) -> None:
        """
        Initialize the scaffold.

        Confirms that all components can be instantiated and the import
        graph is healthy.
        """
        logger.info("RuntimeController: bootstrap started")
        logger.info("  Factory:  %s", type(self._factory).__name__)
        logger.info("  Store:    %s", type(self._store).__name__)
        logger.info("  State:    %s", type(self._state).__name__)
        self._state.session_metadata["bootstrap_complete"] = True
        logger.info("RuntimeController: bootstrap complete — scaffold ready")

    # -------------------------------------------------------------------
    # Public API: run
    # -------------------------------------------------------------------

    def run(
        self,
        query: str,
        identity_manifold: Any = None,
        external_manifold: Any = None,
        identity_node_ids: Optional[List[NodeId]] = None,
        external_node_ids: Optional[List[NodeId]] = None,
        config: Optional[PipelineConfig] = None,
    ) -> PipelineResult:
        """
        Execute the full pipeline: projection -> fusion -> scoring ->
        extraction -> hydration -> synthesis.

        Args:
            query: Raw query string (required, non-empty).
            identity_manifold: Pre-loaded identity manifold (optional).
            external_manifold: Pre-loaded external manifold (optional).
            identity_node_ids: Node IDs to project from identity manifold.
            external_node_ids: Node IDs to project from external manifold.
            config: PipelineConfig. Uses defaults if None.

        Returns:
            PipelineResult with synthesis response and all intermediate
            artifacts.

        Raises:
            ValueError: If query is empty.
            PipelineError: If a required pipeline stage fails.
        """
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string")

        cfg = config or PipelineConfig()
        result = PipelineResult()
        t_total = time.perf_counter()

        # Update runtime state
        self._state.current_query = query
        self._state.session_metadata["current_stage"] = "initializing"

        # Initialize model bridge (may be None if no config)
        bridge = self._init_bridge(cfg)

        # ----- Stage 1-3: Projection -----
        self._state.session_metadata["current_stage"] = "projection"
        t_stage = time.perf_counter()
        try:
            query_artifact, identity_slice, external_slice = (
                self._run_projection(
                    query,
                    identity_manifold,
                    external_manifold,
                    identity_node_ids,
                    external_node_ids,
                    bridge=bridge,
                )
            )
        except PipelineError:
            raise
        except Exception as exc:
            self._state.session_metadata["last_error"] = str(exc)
            raise PipelineError(
                "projection", f"Projection failed: {exc}", cause=exc,
            ) from exc

        result.query_artifact = query_artifact
        result.identity_slice = identity_slice
        result.external_slice = external_slice
        result.timing["projection"] = time.perf_counter() - t_stage
        result.stage_count += 1
        self._state.session_metadata["last_successful_stage"] = "projection"

        # ----- Stage 4: Fusion -----
        self._state.session_metadata["current_stage"] = "fusion"
        t_stage = time.perf_counter()
        try:
            fusion_result = self._run_fusion(
                query_artifact, identity_slice, external_slice,
                fusion_config=cfg.fusion_config,
            )
        except PipelineError:
            raise
        except Exception as exc:
            self._state.session_metadata["last_error"] = str(exc)
            raise PipelineError(
                "fusion", f"Fusion failed: {exc}", cause=exc,
            ) from exc

        vm = fusion_result.virtual_manifold
        result.fusion_result = fusion_result
        result.timing["fusion"] = time.perf_counter() - t_stage
        result.stage_count += 1
        self._state.virtual_manifold_id = vm.get_metadata().manifold_id
        self._state.session_metadata["last_successful_stage"] = "fusion"

        # ----- Stage 5: Scoring -----
        self._state.session_metadata["current_stage"] = "scoring"
        t_stage = time.perf_counter()
        try:
            structural, semantic, grav, scoring_degraded = (
                self._run_scoring(vm, query_artifact, cfg)
            )
        except PipelineError:
            raise
        except Exception as exc:
            self._state.session_metadata["last_error"] = str(exc)
            raise PipelineError(
                "scoring", f"Scoring failed: {exc}", cause=exc,
            ) from exc

        result.structural_scores = structural
        result.semantic_scores = semantic
        result.gravity_scores = grav
        if scoring_degraded:
            result.degraded = True
            result.skipped_stages.append("semantic_scoring")
        result.timing["scoring"] = time.perf_counter() - t_stage
        result.stage_count += 1
        self._state.session_metadata["last_successful_stage"] = "scoring"

        # ----- Stage 6: Extraction -----
        self._state.session_metadata["current_stage"] = "extraction"
        t_stage = time.perf_counter()
        try:
            evidence_bag = self._run_extraction(vm, cfg)
        except PipelineError:
            raise
        except Exception as exc:
            self._state.session_metadata["last_error"] = str(exc)
            raise PipelineError(
                "extraction", f"Extraction failed: {exc}", cause=exc,
            ) from exc

        result.evidence_bag = evidence_bag
        result.timing["extraction"] = time.perf_counter() - t_stage
        result.stage_count += 1
        self._state.current_evidence_bag_id = evidence_bag.bag_id
        self._state.session_metadata["last_successful_stage"] = "extraction"

        # ----- Stage 7: Hydration -----
        self._state.session_metadata["current_stage"] = "hydration"
        t_stage = time.perf_counter()
        try:
            hydrated_bundle = self._run_hydration(evidence_bag, vm, cfg)
        except PipelineError:
            raise
        except Exception as exc:
            self._state.session_metadata["last_error"] = str(exc)
            raise PipelineError(
                "hydration", f"Hydration failed: {exc}", cause=exc,
            ) from exc

        result.hydrated_bundle = hydrated_bundle
        result.timing["hydration"] = time.perf_counter() - t_stage
        result.stage_count += 1
        self._state.session_metadata["last_successful_stage"] = "hydration"

        # ----- Stage 8: Synthesis -----
        self._state.session_metadata["current_stage"] = "synthesis"
        t_stage = time.perf_counter()
        if cfg.skip_synthesis:
            result.skipped_stages.append("synthesis")
            logger.info("Pipeline: synthesis skipped (skip_synthesis=True)")
        else:
            evidence_context, synthesis_response = self._run_synthesis(
                hydrated_bundle, query, bridge, cfg,
            )
            result.evidence_context = evidence_context
            result.synthesis_response = synthesis_response
            if synthesis_response is not None:
                result.answer_text = synthesis_response.text
            else:
                result.skipped_stages.append("synthesis")
                result.degraded = True
        result.timing["synthesis"] = time.perf_counter() - t_stage
        result.stage_count += 1
        self._state.session_metadata["last_successful_stage"] = "synthesis"

        # ----- Finalize -----
        result.timing["total"] = time.perf_counter() - t_total
        self._state.session_metadata["current_stage"] = "complete"
        logger.info(
            "Pipeline complete: %d stages, %.3fs total, degraded=%s, "
            "skipped=%s",
            result.stage_count,
            result.timing["total"],
            result.degraded,
            result.skipped_stages or "none",
        )
        return result

    # -------------------------------------------------------------------
    # Internal: bridge initialization
    # -------------------------------------------------------------------

    def _init_bridge(self, config: PipelineConfig) -> Optional[ModelBridge]:
        """
        Initialize the ModelBridge from config.

        Returns None if no model_bridge_config is provided.
        """
        if config.model_bridge_config is None:
            logger.info("Pipeline: no model bridge config — synthesis will be skipped")
            return None
        bridge = ModelBridge(config=config.model_bridge_config)
        identity = bridge.get_model_identity()
        if identity is not None:
            self._state.model_bridge_state.active_model = identity.model_name
            self._state.model_bridge_state.context_window = identity.context_window
            self._state.model_bridge_state.embedding_dimensions = (
                identity.embedding_dimensions
            )
        logger.info("Pipeline: model bridge initialized")
        return bridge

    # -------------------------------------------------------------------
    # Stage 1-3: Projection
    # -------------------------------------------------------------------

    def _run_projection(
        self,
        query: str,
        identity_manifold: Any,
        external_manifold: Any,
        identity_node_ids: Optional[List[NodeId]],
        external_node_ids: Optional[List[NodeId]],
        bridge: Optional[ModelBridge] = None,
    ) -> Tuple[QueryProjectionArtifact, Optional[ProjectedSlice], Optional[ProjectedSlice]]:
        """
        Stages 1-3: Project query, identity, and external slices.

        When a ModelBridge is available, its embed() method is wrapped
        as a callback and passed to QueryProjection so the query can
        be embedded for downstream semantic scoring.

        Returns:
            Tuple of (query_artifact, identity_slice, external_slice).
            Identity and external slices are None if their manifold is None.
        """
        logger.info("Pipeline stage: projection — starting")

        # Build embed callback from ModelBridge if available.
        # This keeps QueryProjection decoupled from ModelBridge —
        # it receives an embedding capability, not a backend object.
        embed_fn = None
        if bridge is not None:
            def embed_fn(text: str) -> List[float]:
                """Embed a single text string via ModelBridge."""
                response = bridge.embed(EmbedRequest(texts=[text]))
                if response.vectors:
                    return response.vectors[0]
                return []

        # Stage 1: Query projection
        query_projector = QueryProjection()
        query_slice = query_projector.project(
            None, {"raw_query": query}, embed_fn=embed_fn,
        )
        query_artifact: QueryProjectionArtifact = (
            query_slice.projected_data["query_artifact"]
        )
        has_embedding = "query_embedding" in query_artifact.properties
        logger.info(
            "  Query projected: node_id=%s, embedding=%s",
            query_artifact.query_node_id,
            "yes (dims=%d)" % len(query_artifact.properties["query_embedding"])
            if has_embedding else "no",
        )

        # Stage 2: Identity projection (optional)
        identity_slice: Optional[ProjectedSlice] = None
        if identity_manifold is not None:
            ids = identity_node_ids or []
            if ids:
                id_projector = IdentityProjection(store=self._store)
                identity_slice = id_projector.project(
                    identity_manifold, {"node_ids": ids},
                )
                logger.info(
                    "  Identity projected: %d nodes", len(identity_slice.node_ids),
                )
            else:
                logger.info("  Identity manifold provided but no node_ids — skipped")
        else:
            logger.info("  No identity manifold — skipped")

        # Stage 3: External projection (optional)
        external_slice: Optional[ProjectedSlice] = None
        if external_manifold is not None:
            ext_ids = external_node_ids or []
            if ext_ids:
                ext_projector = ExternalProjection(store=self._store)
                external_slice = ext_projector.project(
                    external_manifold, {"node_ids": ext_ids},
                )
                logger.info(
                    "  External projected: %d nodes", len(external_slice.node_ids),
                )
            else:
                logger.info("  External manifold provided but no node_ids — skipped")
        else:
            logger.info("  No external manifold — skipped")

        logger.info("Pipeline stage: projection — complete")
        return query_artifact, identity_slice, external_slice

    # -------------------------------------------------------------------
    # Stage 4: Fusion
    # -------------------------------------------------------------------

    def _run_fusion(
        self,
        query_artifact: QueryProjectionArtifact,
        identity_slice: Optional[ProjectedSlice],
        external_slice: Optional[ProjectedSlice],
        fusion_config: Optional[FusionConfig] = None,
    ) -> FusionResult:
        """
        Stage 4: Fuse projected slices into a VirtualManifold.

        Returns:
            FusionResult containing the VirtualManifold, bridge edges,
            ancestry, and provenance.
        """
        logger.info("Pipeline stage: fusion — starting")
        engine = FusionEngine()
        fusion_result = engine.fuse(
            identity_slice=identity_slice,
            external_slice=external_slice,
            query_artifact=query_artifact,
            config=fusion_config,
        )
        vm = fusion_result.virtual_manifold
        logger.info(
            "Pipeline stage: fusion — complete (VM nodes=%d, edges=%d, bridges=%d)",
            len(vm.get_nodes()),
            len(vm.get_edges()),
            len(fusion_result.bridge_edges),
        )
        return fusion_result

    # -------------------------------------------------------------------
    # Stage 5: Scoring
    # -------------------------------------------------------------------

    def _run_scoring(
        self,
        vm: Any,
        query_artifact: QueryProjectionArtifact,
        config: PipelineConfig,
    ) -> Tuple[Dict[NodeId, float], Dict[NodeId, float], Dict[NodeId, float], bool]:
        """
        Stage 5: Structural, semantic, and gravity scoring + annotation.

        Semantic scoring requires both node embeddings (from VM) and a
        query embedding (from query_artifact.properties). If either is
        missing, falls back to structural-only gravity.

        Returns:
            Tuple of (structural, semantic, gravity, degraded).
            degraded is True if semantic scoring was skipped.
        """
        logger.info("Pipeline stage: scoring — starting")
        degraded = False

        # Stage 5a: Structural scoring (PageRank)
        struct_scores = structural_score(
            vm,
            damping=config.damping,
            max_iterations=config.max_iterations,
            tolerance=config.tolerance,
        )
        logger.info("  Structural: %d nodes scored", len(struct_scores))

        # Stage 5b: Semantic scoring (requires embeddings)
        sem_scores: Dict[NodeId, float] = {}
        query_embedding = query_artifact.properties.get("query_embedding")

        if query_embedding is not None:
            node_embeddings = self._gather_node_embeddings(vm)
            if node_embeddings:
                sem_scores = semantic_score(node_embeddings, query_embedding)
                logger.info(
                    "  Semantic: %d nodes scored (query embedding available)",
                    len(sem_scores),
                )
            else:
                logger.info(
                    "  Semantic: skipped — no node embeddings in VM",
                )
                degraded = True
        else:
            logger.info(
                "  Semantic: skipped — no query embedding available "
                "(no embed_fn provided or embedding generation failed)",
            )
            degraded = True

        # Stage 5c: Gravity scoring
        if sem_scores:
            grav_scores = gravity_score(
                struct_scores, sem_scores,
                alpha=config.alpha, beta=config.beta,
            )
        else:
            # Fallback: structural-only gravity
            grav_scores = gravity_score(
                struct_scores, {},
                alpha=1.0, beta=0.0,
            )
        logger.info("  Gravity: %d nodes scored", len(grav_scores))

        # Stage 5d: Annotate scores onto VM
        annotate_scores(vm, struct_scores, sem_scores, grav_scores)
        logger.info("Pipeline stage: scoring — complete (degraded=%s)", degraded)

        return struct_scores, sem_scores, grav_scores, degraded

    # -------------------------------------------------------------------
    # Internal: gather node embeddings from VM
    # -------------------------------------------------------------------

    def _gather_node_embeddings(self, vm: Any) -> Dict[NodeId, List[float]]:
        """
        Gather node embedding vectors from the VirtualManifold.

        Traverses vm.get_node_embedding_bindings() to find embedding IDs,
        looks up Embedding objects in vm.get_embeddings(), and extracts
        vectors from vector_blob (packed 32-bit floats).

        Nodes without embedding bindings or with missing/empty vector_blob
        are silently excluded.

        Returns:
            Dict mapping NodeId to embedding vector (List[float]).
        """
        node_embeddings: Dict[NodeId, List[float]] = {}
        bindings = vm.get_node_embedding_bindings()
        embeddings_dict = vm.get_embeddings()

        for binding in bindings:
            emb = embeddings_dict.get(binding.embedding_id)
            if emb is None or emb.vector_blob is None:
                continue
            # Determine float count from dimensions or blob size
            dims = emb.dimensions if emb.dimensions > 0 else len(emb.vector_blob) // 4
            if dims <= 0:
                continue
            try:
                vector = list(struct.unpack(f"<{dims}f", emb.vector_blob))
                node_embeddings[binding.node_id] = vector
            except struct.error:
                continue  # Skip malformed blobs

        return node_embeddings

    # -------------------------------------------------------------------
    # Stage 6: Extraction
    # -------------------------------------------------------------------

    def _run_extraction(
        self,
        vm: Any,
        config: PipelineConfig,
    ) -> EvidenceBag:
        """
        Stage 6: Extract a deterministic evidence bag from the scored VM.

        Returns:
            EvidenceBag with selected nodes, edges, chunk refs, and scores.
        """
        logger.info("Pipeline stage: extraction — starting")
        evidence_bag = extract_evidence_bag(vm, config=config.extraction_config)
        logger.info(
            "Pipeline stage: extraction — complete "
            "(nodes=%d, edges=%d, chunks=%d, tokens=%d/%d)",
            len(evidence_bag.node_ids),
            len(evidence_bag.edge_ids),
            sum(len(refs) for refs in evidence_bag.chunk_refs.values()),
            evidence_bag.token_budget.used_tokens,
            evidence_bag.token_budget.max_tokens,
        )
        return evidence_bag

    # -------------------------------------------------------------------
    # Stage 7: Hydration
    # -------------------------------------------------------------------

    def _run_hydration(
        self,
        evidence_bag: EvidenceBag,
        vm: Any,
        config: PipelineConfig,
    ) -> HydratedBundle:
        """
        Stage 7: Hydrate the evidence bag into model-readable content.

        Returns:
            HydratedBundle with hydrated nodes, translated edges,
            and token totals.
        """
        logger.info("Pipeline stage: hydration — starting")
        hydrated_bundle = hydrate_evidence_bag(
            evidence_bag, vm, config=config.hydration_config,
        )
        logger.info(
            "Pipeline stage: hydration — complete "
            "(nodes=%d, edges=%d, tokens=%d, mode=%s)",
            len(hydrated_bundle.nodes),
            len(hydrated_bundle.edges),
            hydrated_bundle.total_tokens,
            hydrated_bundle.mode.value if hasattr(hydrated_bundle.mode, "value") else hydrated_bundle.mode,
        )
        return hydrated_bundle

    # -------------------------------------------------------------------
    # Stage 8: Synthesis
    # -------------------------------------------------------------------

    def _run_synthesis(
        self,
        hydrated_bundle: HydratedBundle,
        query: str,
        bridge: Optional[ModelBridge],
        config: PipelineConfig,
    ) -> Tuple[str, Optional[SynthesisResponse]]:
        """
        Stage 8: Format evidence context and synthesize answer.

        Delegates formatting to format_evidence_bundle() from hydrator.py.
        Calls ModelBridge.synthesize() for generation.

        Returns:
            Tuple of (evidence_context_string, SynthesisResponse or None).
        """
        logger.info("Pipeline stage: synthesis — starting")

        # Format evidence context (delegated to hydrator)
        hydrated_nodes: Dict[NodeId, str] = {
            node.node_id: node.content for node in hydrated_bundle.nodes
        }
        translated_edges = [
            {
                "edge_id": str(e.edge_id),
                "source": str(e.source_id),
                "target": str(e.target_id),
                "relation": e.relation,
            }
            for e in hydrated_bundle.edges
        ]
        evidence_context = format_evidence_bundle(
            hydrated_nodes,
            translated_edges,
            hydrated_bundle.topology_preserved,
        )

        # Synthesize via model bridge
        if bridge is None:
            logger.warning(
                "Pipeline stage: synthesis — no model bridge, skipping",
            )
            return evidence_context, None

        try:
            request = SynthesisRequest(
                evidence_context=evidence_context,
                query=query,
                model=config.synthesis_model,
                system_prompt=config.system_prompt,
                temperature=config.temperature,
                max_tokens=config.max_synthesis_tokens,
            )
            response = bridge.synthesize(request)
            logger.info(
                "Pipeline stage: synthesis — complete "
                "(tokens_used=%d, finish=%s)",
                response.tokens_used,
                response.finish_reason,
            )
            return evidence_context, response
        except ModelConnectionError as exc:
            logger.warning(
                "Pipeline stage: synthesis — model connection failed, "
                "skipping: %s",
                exc,
            )
            return evidence_context, None

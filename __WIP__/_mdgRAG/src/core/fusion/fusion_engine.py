"""
Fusion Engine — combine projected manifold slices into virtual manifold.

Ownership: src/core/fusion/fusion_engine.py
    Fusion is a FIRST-CLASS subsystem, not buried inside a backend monolith.

    Responsibilities:
        1. Create VirtualManifold
        2. Populate its in-memory collections from identity + external slices
        3. Create bridge edges (explicit requests + auto-bridging)
        4. Attach FUSION provenance to all bridge edges
        5. Return FusionResult

    Bridge creation strategy (Phase 4):
        - Explicit bridge requests from caller
        - Auto-bridge by shared canonical_key between identity/external nodes
        - Label fallback if no canonical_key matches

    The virtual manifold produced by fusion is the input to extraction
    and downstream synthesis.

Legacy context:
    - Seam composition logic from Mind2Manager
    - Gravity-driven fusion from Mind3Manager
    - Bridge edge creation patterns
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from src.core.contracts.fusion_contract import (
    BridgeEdge,
    BridgeRequest,
    FusionAncestry,
    FusionConfig,
    FusionContract,
    FusionResult,
)
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)
from src.core.contracts.projection_contract import (
    ProjectedSlice,
    QueryProjectionArtifact,
)
from src.core.manifolds.virtual_manifold import VirtualManifold
from src.core.types.ids import (
    EdgeId,
    HASH_TRUNCATION_LENGTH,
    ManifoldId,
    NodeId,
    deterministic_hash,
)
from src.core.types.enums import (
    EdgeType,
    ProvenanceRelationOrigin,
    ProvenanceStage,
)
from src.core.types.graph import Edge, Node
from src.core.types.provenance import Provenance


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_bridge_edge_id(source_node: NodeId, target_node: NodeId) -> EdgeId:
    """Deterministic bridge edge ID from the two endpoints."""
    return EdgeId(
        f"bridge-{deterministic_hash(f'{source_node}:{target_node}')[:HASH_TRUNCATION_LENGTH]}"
    )


class FusionEngine(FusionContract):
    """
    Combine projected identity and external graphs into a virtual manifold.

    Every bridge edge created during fusion carries provenance tracing
    it back to the source projections.
    """

    def fuse(
        self,
        identity_slice: Optional[ProjectedSlice] = None,
        external_slice: Optional[ProjectedSlice] = None,
        query_artifact: Optional[QueryProjectionArtifact] = None,
        bridge_requests: Optional[List[BridgeRequest]] = None,
        config: Optional[FusionConfig] = None,
    ) -> FusionResult:
        """
        Fuse projected slices into a virtual manifold.

        Steps:
            1. Create VirtualManifold with deterministic ID.
            2. Ingest identity slice objects into VM collections.
            3. Ingest external slice objects into VM collections.
            4. If query_artifact has a query_node, add it to VM.
            5. Process explicit bridge requests.
            6. Auto-bridge by canonical_key match.
            7. Label fallback if enabled and no canonical_key matches found.
            8. Build FusionResult with ancestry and provenance.
        """
        cfg = config or FusionConfig()
        now = _utcnow_iso()

        # Validation: warn on all-empty inputs (likely caller bug)
        if not identity_slice and not external_slice and not query_artifact:
            logger.warning(
                "Fusion: fuse() called with no identity, external, "
                "or query input — producing empty VM",
            )

        # Collect source manifold IDs and slices
        source_ids: List[ManifoldId] = []
        slices: List[ProjectedSlice] = []
        if identity_slice:
            source_ids.append(identity_slice.metadata.source_manifold_id)
            slices.append(identity_slice)
        if external_slice:
            source_ids.append(external_slice.metadata.source_manifold_id)
            slices.append(external_slice)

        # Ephemeral VM ID from source manifolds + timestamp
        # Policy: VMs are intentionally ephemeral (W-001 accepted-by-design).
        # Same fused content produces different IDs across runs. This is
        # correct while VMs are throwaway working graphs. If VMs are ever
        # cached, compared, or persisted, replace timestamp with a
        # content-derived seed.
        vm_id_seed = ":".join(sorted(str(s) for s in source_ids)) + ":" + now
        vm_id = ManifoldId(
            f"vm-{deterministic_hash(vm_id_seed)[:HASH_TRUNCATION_LENGTH]}"
        )

        vm = VirtualManifold(manifold_id=vm_id)
        vm._source_manifold_ids = list(source_ids)

        # --- Ingest slices into VM ---
        all_provenance: List[Provenance] = []
        bridge_edges: List[BridgeEdge] = []

        # Track which nodes came from which manifold (for bridging)
        node_origin: Dict[NodeId, ManifoldId] = {}

        for proj_slice in slices:
            src_mid = proj_slice.metadata.source_manifold_id
            self._ingest_slice_into_vm(vm, proj_slice, src_mid, node_origin)
            all_provenance.extend(proj_slice.provenance_entries)

        # --- Ingest query node if present ---
        if query_artifact and query_artifact.query_node:
            qn = query_artifact.query_node
            vm.get_nodes()[qn.node_id] = qn
            node_origin[qn.node_id] = ManifoldId("query")

        # Track existing bridge pairs to avoid duplicates
        existing_bridge_pairs: Set[tuple] = set()

        # --- Process explicit bridge requests ---
        explicit_ok = 0
        explicit_skip = 0
        if bridge_requests:
            vm_nodes = vm.get_nodes()
            for req in bridge_requests:
                pair = (req.source_node, req.target_node)
                if pair in existing_bridge_pairs:
                    explicit_skip += 1
                    continue
                if req.source_node not in vm_nodes or req.target_node not in vm_nodes:
                    explicit_skip += 1
                    logger.warning(
                        "Fusion: explicit bridge skipped — node(s) missing "
                        "from VM (source=%s, target=%s)",
                        req.source_node, req.target_node,
                    )
                    continue
                existing_bridge_pairs.add(pair)
                be = self._create_bridge(
                    req.source_node, req.target_node,
                    req.source_manifold, req.target_manifold,
                    weight=req.weight,
                    properties=req.properties,
                    timestamp=now,
                )
                bridge_edges.append(be)
                self._add_bridge_as_edge(vm, be, vm_id)
                all_provenance.append(
                    self._make_fusion_provenance(be.edge_id, now)
                )
                explicit_ok += 1

        # --- Auto-bridge by canonical_key / label ---
        if identity_slice and external_slice:
            auto_bridges = self._auto_bridge_by_key(
                identity_slice, external_slice,
                existing_bridge_pairs, now, cfg,
            )
            for be in auto_bridges:
                pair = (be.source_node, be.target_node)
                existing_bridge_pairs.add(pair)
                bridge_edges.append(be)
                self._add_bridge_as_edge(vm, be, vm_id)
                all_provenance.append(
                    self._make_fusion_provenance(be.edge_id, now)
                )

        # --- Build FusionResult ---
        # Count bridge types for logging
        canonical_count = sum(
            1 for be in bridge_edges
            if be.properties.get("match_type") == "canonical_key"
        )
        label_count = sum(
            1 for be in bridge_edges
            if be.properties.get("match_type") == "label"
        )

        ancestry = FusionAncestry(
            source_manifold_ids=source_ids,
            projection_count=len(slices),
            fusion_timestamp=now,
            strategy="default_keymatch",
            parameters={
                "enable_label_fallback": cfg.enable_label_fallback,
                "label_fallback_weight": cfg.label_fallback_weight,
            },
        )

        logger.info(
            "Fusion: VM=%s, nodes=%d, edges=%d, bridges=%d "
            "(explicit=%d, canonical=%d, label=%d, skipped=%d)",
            vm_id, len(vm.get_nodes()), len(vm.get_edges()),
            len(bridge_edges), explicit_ok, canonical_count,
            label_count, explicit_skip,
        )

        return FusionResult(
            virtual_manifold=vm,
            bridge_edges=bridge_edges,
            ancestry=ancestry,
            provenance=all_provenance,
        )

    # =================================================================
    # Internal helpers
    # =================================================================

    @staticmethod
    def _ingest_slice_into_vm(
        vm: VirtualManifold,
        proj_slice: ProjectedSlice,
        source_manifold_id: ManifoldId,
        node_origin: Dict[NodeId, ManifoldId],
    ) -> None:
        """Copy all typed objects from a ProjectedSlice into the VM."""
        for node in proj_slice.nodes:
            vm.get_nodes()[node.node_id] = node
            node_origin[node.node_id] = source_manifold_id

        for edge in proj_slice.edges:
            vm.get_edges()[edge.edge_id] = edge

        for chunk in proj_slice.chunks:
            vm.get_chunks()[chunk.chunk_hash] = chunk

        vm.get_chunk_occurrences().extend(proj_slice.chunk_occurrences)

        for emb in proj_slice.embeddings:
            vm.get_embeddings()[emb.embedding_id] = emb

        for h in proj_slice.hierarchy_entries:
            vm.get_hierarchy()[h.hierarchy_id] = h

        vm.get_metadata_entries().extend(proj_slice.metadata_entries)
        vm.get_provenance_entries().extend(proj_slice.provenance_entries)
        vm.get_node_chunk_bindings().extend(proj_slice.node_chunk_bindings)
        vm.get_node_embedding_bindings().extend(
            proj_slice.node_embedding_bindings,
        )
        vm.get_node_hierarchy_bindings().extend(
            proj_slice.node_hierarchy_bindings,
        )

    @staticmethod
    def _create_bridge(
        source_node: NodeId,
        target_node: NodeId,
        source_manifold: ManifoldId,
        target_manifold: ManifoldId,
        weight: float = 1.0,
        properties: Optional[Dict[str, Any]] = None,
        timestamp: Optional[str] = None,
    ) -> BridgeEdge:
        """Create a BridgeEdge between two nodes from different manifolds."""
        edge_id = _make_bridge_edge_id(source_node, target_node)
        return BridgeEdge(
            edge_id=edge_id,
            source_node=source_node,
            target_node=target_node,
            source_manifold=source_manifold,
            target_manifold=target_manifold,
            edge_type=EdgeType.BRIDGE,
            weight=weight,
            provenance=Provenance(
                owner_kind="edge",
                owner_id=edge_id,
                stage=ProvenanceStage.FUSION,
                relation_origin=ProvenanceRelationOrigin.FUSED,
                timestamp=timestamp,
            ),
            properties=properties or {},
        )

    @staticmethod
    def _add_bridge_as_edge(
        vm: VirtualManifold,
        be: BridgeEdge,
        vm_id: ManifoldId,
    ) -> None:
        """Convert BridgeEdge to a graph Edge and add to VM."""
        edge = Edge(
            edge_id=be.edge_id,
            manifold_id=vm_id,
            from_node_id=be.source_node,
            to_node_id=be.target_node,
            edge_type=EdgeType.BRIDGE,
            weight=be.weight,
            properties={
                **be.properties,
                "source_manifold": str(be.source_manifold),
                "target_manifold": str(be.target_manifold),
            },
        )
        vm.get_edges()[edge.edge_id] = edge

    @staticmethod
    def _make_fusion_provenance(edge_id: EdgeId, timestamp: str) -> Provenance:
        """Create FUSION-stage provenance for a bridge edge."""
        return Provenance(
            owner_kind="edge",
            owner_id=edge_id,
            stage=ProvenanceStage.FUSION,
            relation_origin=ProvenanceRelationOrigin.FUSED,
            timestamp=timestamp,
            details={"bridge": True},
        )

    @staticmethod
    def _auto_bridge_by_key(
        identity_slice: ProjectedSlice,
        external_slice: ProjectedSlice,
        existing_pairs: Set[tuple],
        timestamp: str,
        config: Optional[FusionConfig] = None,
    ) -> List[BridgeEdge]:
        """
        Auto-create bridge edges between identity and external nodes
        that share the same canonical_key (primary) or label (fallback).

        Label fallback is controlled by config.enable_label_fallback
        (default True for backward compatibility).  When disabled, only
        canonical-key matches produce auto-bridges.
        """
        cfg = config or FusionConfig()
        bridges: List[BridgeEdge] = []
        id_mid = identity_slice.metadata.source_manifold_id
        ext_mid = external_slice.metadata.source_manifold_id

        # Index by canonical_key
        id_by_key: Dict[str, List[Node]] = {}
        ext_by_key: Dict[str, List[Node]] = {}

        for node in identity_slice.nodes:
            if node.canonical_key:
                id_by_key.setdefault(node.canonical_key, []).append(node)
        for node in external_slice.nodes:
            if node.canonical_key:
                ext_by_key.setdefault(node.canonical_key, []).append(node)

        # Match on canonical_key
        for key in sorted(id_by_key):  # sorted for determinism
            if key in ext_by_key:
                for id_node in id_by_key[key]:
                    for ext_node in ext_by_key[key]:
                        pair = (id_node.node_id, ext_node.node_id)
                        if pair not in existing_pairs:
                            existing_pairs.add(pair)
                            be = FusionEngine._create_bridge(
                                id_node.node_id, ext_node.node_id,
                                id_mid, ext_mid,
                                weight=cfg.canonical_key_weight,
                                properties={
                                    "match_type": "canonical_key",
                                    "key": key,
                                },
                                timestamp=timestamp,
                            )
                            bridges.append(be)

        # Label fallback — only when enabled and no canonical matches found
        if not bridges and cfg.enable_label_fallback:
            id_by_label: Dict[str, List[Node]] = {}
            ext_by_label: Dict[str, List[Node]] = {}

            for node in identity_slice.nodes:
                if node.label:
                    id_by_label.setdefault(
                        node.label.lower(), [],
                    ).append(node)
            for node in external_slice.nodes:
                if node.label:
                    ext_by_label.setdefault(
                        node.label.lower(), [],
                    ).append(node)

            for label in sorted(id_by_label):  # sorted for determinism
                if label in ext_by_label:
                    for id_node in id_by_label[label]:
                        for ext_node in ext_by_label[label]:
                            pair = (id_node.node_id, ext_node.node_id)
                            if pair not in existing_pairs:
                                existing_pairs.add(pair)
                                be = FusionEngine._create_bridge(
                                    id_node.node_id, ext_node.node_id,
                                    id_mid, ext_mid,
                                    weight=cfg.label_fallback_weight,
                                    properties={
                                        "match_type": "label",
                                        "label": label,
                                    },
                                    timestamp=timestamp,
                                )
                                bridges.append(be)
        elif not bridges and not cfg.enable_label_fallback:
            logger.info(
                "Fusion: no canonical-key bridges found; "
                "label fallback disabled by config",
            )

        return bridges

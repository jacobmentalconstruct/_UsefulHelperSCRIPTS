"""
Fusion Contract — virtual manifold creation from projected slices.

Ownership: src/core/contracts/fusion_contract.py
    Defines the typed output shape of fusion and the abstract interface
    that fusion implementations must satisfy.

Fusion is a FIRST-CLASS subsystem, not buried inside a backend monolith.

Fusion responsibilities:
    - Combine projected identity and external graph slices
    - Create the virtual manifold as the ephemeral fused workspace
    - Create bridge edges connecting identity and external nodes
    - Preserve provenance for every fusion-created edge

Bridge edges:
    - Every bridge edge must record which projections it connects
    - Provenance must trace back to source manifold identities
    - Bridge edges are first-class graph elements, not annotations

Legacy context:
    - Mind 2 seam composition pattern from Mind2Manager
    - Mind 3 gravity fusion from Mind3Manager
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.types.ids import EdgeId, ManifoldId, NodeId
from src.core.types.enums import EdgeType
from src.core.types.provenance import Provenance
from src.core.contracts.projection_contract import (
    ProjectedSlice,
    QueryProjectionArtifact,
)


# ---------------------------------------------------------------------------
# Bridge request (input to fusion)
# ---------------------------------------------------------------------------

@dataclass
class BridgeRequest:
    """
    Explicit request to create a bridge edge between two nodes
    from different source manifolds during fusion.
    """

    source_node: NodeId
    target_node: NodeId
    source_manifold: ManifoldId
    target_manifold: ManifoldId
    edge_type: EdgeType = EdgeType.BRIDGE
    weight: float = 1.0
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Bridge edge (output of fusion)
# ---------------------------------------------------------------------------

@dataclass
class BridgeEdge:
    """
    An edge created by fusion to connect projected subgraphs.

    Bridge edges are first-class graph elements. Each one records:
    - The nodes it connects (which may come from different manifolds)
    - The source manifold identities on each side
    - Full provenance for how/why the bridge was created
    """

    edge_id: EdgeId
    source_node: NodeId
    target_node: NodeId
    source_manifold: ManifoldId
    target_manifold: ManifoldId
    edge_type: EdgeType = EdgeType.BRIDGE
    weight: float = 1.0
    provenance: Provenance = field(default_factory=lambda: Provenance(
        owner_kind="edge", owner_id=""
    ))
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fusion configuration
# ---------------------------------------------------------------------------

@dataclass
class FusionConfig:
    """
    Policy object controlling fusion bridge behaviour.

    Makes previously-hidden defaults explicit and configurable.
    """

    enable_label_fallback: bool = True
    """
    Allow case-insensitive label matching when no canonical-key bridges
    exist.  Label fallback is low-confidence — common labels produce
    spurious bridges.  Enabled by default for backward compatibility.
    Set to False once a canonicalization/alias layer exists.
    """

    label_fallback_weight: float = 0.7
    """Weight assigned to label-fallback bridge edges (0..1)."""

    canonical_key_weight: float = 1.0
    """Weight assigned to canonical-key bridge edges."""


# ---------------------------------------------------------------------------
# Fusion ancestry
# ---------------------------------------------------------------------------

@dataclass
class FusionAncestry:
    """
    Records the manifold sources that contributed to a fusion result.

    Tracks which projections were fused and from which manifolds,
    enabling full lineage tracing of the virtual manifold.
    """

    source_manifold_ids: List[ManifoldId] = field(default_factory=list)
    projection_count: int = 0
    fusion_timestamp: Optional[str] = None
    strategy: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Fusion result
# ---------------------------------------------------------------------------

@dataclass
class FusionResult:
    """
    Complete result of fusing projected manifold slices.

    Contains the virtual manifold, all bridge edges created during
    fusion, and full provenance/ancestry information.
    """

    virtual_manifold: Any               # Conforms to ManifoldContract
    bridge_edges: List[BridgeEdge] = field(default_factory=list)
    ancestry: FusionAncestry = field(default_factory=FusionAncestry)
    provenance: List[Provenance] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class FusionContract(ABC):
    """
    Abstract contract for manifold fusion.

    Fusion is a first-class subsystem — not buried in a backend monolith.
    """

    @abstractmethod
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

        Args:
            identity_slice: Projected slice from the identity manifold.
            external_slice: Projected slice from the external manifold.
            query_artifact: Optional query projection artifact.
            bridge_requests: Optional explicit bridge edge requests.
            config: Optional fusion policy configuration.

        Returns:
            FusionResult with virtual manifold, bridge edges, and
            full provenance.
        """
        ...

"""
Evidence Bag Contract — graph-native bounded contextual subgraph.

Ownership: src/core/contracts/evidence_bag_contract.py
    Defines the typed structure and abstract interface for evidence bags.
    An evidence bag is a contextual subgraph, NOT a flat text bundle.

An evidence bag preserves topological relationships from the virtual
manifold and carries provenance tracing each element back to its source.
It is the primary input to hydration and downstream synthesis.

Contents:
    - selected node IDs from the virtual manifold
    - selected edge IDs preserving graph topology
    - chunk references keyed by node
    - hierarchy references for structural context
    - score annotations (structural, semantic, gravity)
    - provenance references for traceability
    - token budget metadata
    - construction trace placeholder

Legacy context:
    - Seam composition from SeamBuilderMS ego-graph pattern
    - Token budget tracking from TokenPackerMS (8000 token default)
    - Gravity score annotations from GravityScorerMS
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.types.ids import (
    ChunkHash,
    EdgeId,
    EvidenceBagId,
    HierarchyId,
    ManifoldId,
    NodeId,
)
from src.core.types.provenance import Provenance


# ---------------------------------------------------------------------------
# Score annotations
# ---------------------------------------------------------------------------

@dataclass
class ScoreAnnotation:
    """
    Score vector attached to a node within an evidence bag.

    Legacy context:
        G(v) = alpha * S_norm(v) + beta * T_norm(v)
        where S_norm = min-max normalised PageRank
        and T_norm = min-max normalised semantic cosine similarity.
    """

    structural: float = 0.0     # e.g. PageRank-derived
    semantic: float = 0.0       # e.g. cosine similarity to query
    gravity: float = 0.0        # fused score
    raw_scores: Dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Token budget
# ---------------------------------------------------------------------------

@dataclass
class TokenBudget:
    """
    Token budget metadata governing evidence bag sizing.

    Legacy context:
        Legacy default was 8000 tokens, with a greedy max-heap packer.
    """

    max_tokens: int = 8000
    used_tokens: int = 0
    remaining_tokens: int = 8000
    estimator: str = "split_heuristic"  # Which estimator produced the count


# ---------------------------------------------------------------------------
# Construction trace
# ---------------------------------------------------------------------------

@dataclass
class EvidenceBagTrace:
    """
    Records how an evidence bag was constructed for debugging/audit.

    Captures the parameters, source manifold, and extraction strategy
    used during construction.
    """

    source_virtual_manifold_id: Optional[ManifoldId] = None
    extraction_strategy: str = ""
    hop_depth: int = 0
    seed_node_count: int = 0
    total_candidates: int = 0
    selected_count: int = 0
    parameters: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Evidence Bag — concrete data structure
# ---------------------------------------------------------------------------

@dataclass
class EvidenceBag:
    """
    A bounded contextual subgraph extracted from the virtual manifold.

    This is the concrete, graph-native evidence bag. It is NOT a flat
    text blob — it preserves node/edge topology, chunk bindings,
    hierarchy context, and per-node score annotations.
    """

    bag_id: EvidenceBagId
    node_ids: List[NodeId] = field(default_factory=list)
    edge_ids: List[EdgeId] = field(default_factory=list)
    chunk_refs: Dict[NodeId, List[ChunkHash]] = field(default_factory=dict)
    hierarchy_refs: Dict[NodeId, List[HierarchyId]] = field(default_factory=dict)
    scores: Dict[NodeId, ScoreAnnotation] = field(default_factory=dict)
    provenance: List[Provenance] = field(default_factory=list)
    token_budget: TokenBudget = field(default_factory=TokenBudget)
    trace: EvidenceBagTrace = field(default_factory=EvidenceBagTrace)
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class EvidenceBagContract(ABC):
    """
    Abstract contract for evidence bag producers/consumers.

    Implementations must produce evidence bags conforming to the
    graph-native EvidenceBag structure above.
    """

    @abstractmethod
    def get_evidence_bag(self) -> EvidenceBag:
        """Return the current evidence bag."""
        ...

    @abstractmethod
    def get_node_ids(self) -> List[NodeId]:
        """Return node IDs included in this evidence context."""
        ...

    @abstractmethod
    def get_edge_ids(self) -> List[EdgeId]:
        """Return edge IDs preserving topological relationships."""
        ...

    @abstractmethod
    def get_chunk_refs(self) -> Dict[NodeId, List[ChunkHash]]:
        """Return chunk references keyed by node."""
        ...

    @abstractmethod
    def get_scores(self) -> Dict[NodeId, ScoreAnnotation]:
        """Return score annotations keyed by node."""
        ...

    @abstractmethod
    def get_token_budget(self) -> TokenBudget:
        """Return token budget metadata."""
        ...

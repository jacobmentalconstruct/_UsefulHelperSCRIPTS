"""
Hydration Contract — downstream content materialisation.

Ownership: src/core/contracts/hydration_contract.py
    Defines the typed input/output shapes for hydration and the
    abstract interface that hydration implementations must satisfy.

Pipeline position:
    Extraction → **Hydration** → Synthesis

Hydration consumes:
    - An evidence bag (graph-native subgraph with node/edge/chunk refs)
    - Access to source manifold(s) for content resolution

Hydration produces:
    - A structured, model-readable evidence bundle with materialised
      content payloads and translated edge relationships

Hydration must:
    - Preserve graph topology in the output representation
    - Never modify the source manifold
    - Respect the hydration mode (full / summary / reference)

No hydration logic is implemented in this file — only contracts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.types.ids import ChunkHash, EdgeId, ManifoldId, NodeId
from src.core.types.enums import HydrationMode


# ---------------------------------------------------------------------------
# Hydration input
# ---------------------------------------------------------------------------

@dataclass
class HydrationInput:
    """
    Everything hydration needs to resolve an evidence bag into content.

    The evidence_bag field references the graph-native EvidenceBag.
    The source_manifold_ids tell the hydrator where to look up content.
    """

    evidence_bag: Any               # EvidenceBag instance
    source_manifold_ids: List[ManifoldId] = field(default_factory=list)
    mode: HydrationMode = HydrationMode.FULL
    max_tokens: Optional[int] = None
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Hydration output elements
# ---------------------------------------------------------------------------

@dataclass
class HydratedNode:
    """A node with its full content payload materialised."""

    node_id: NodeId
    content: str
    token_estimate: int = 0
    chunk_hashes: List[ChunkHash] = field(default_factory=list)
    label: str = ""
    node_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HydratedEdge:
    """An edge translated into presentable form."""

    edge_id: EdgeId
    source_id: NodeId
    target_id: NodeId
    relation: str
    weight: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HydratedBundle:
    """
    Complete hydrated output — a structured, model-readable evidence bundle.

    Preserves graph topology: nodes carry content payloads, edges carry
    translated relationships, and the overall structure mirrors the
    evidence bag's subgraph.
    """

    nodes: List[HydratedNode] = field(default_factory=list)
    edges: List[HydratedEdge] = field(default_factory=list)
    topology_preserved: bool = True
    total_tokens: int = 0
    mode: HydrationMode = HydrationMode.FULL
    source_manifold_ids: List[ManifoldId] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class HydrationContract(ABC):
    """
    Abstract contract for hydration implementations.

    Hydration resolves abstract graph references into concrete content
    while maintaining structural relationships.
    """

    @abstractmethod
    def hydrate(self, hydration_input: HydrationInput) -> HydratedBundle:
        """
        Hydrate an evidence bag into a full content bundle.

        Args:
            hydration_input: HydrationInput containing the evidence bag
                and source manifold references.

        Returns:
            HydratedBundle with materialised node payloads and
            translated edges.
        """
        ...

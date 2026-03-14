"""
Runtime State — centralized typed state for the active session.

Ownership: src/core/types/runtime_state.py
    Single source of truth for what is currently active at runtime.
    Prevents state from scattering across modules as ad-hoc globals.

All fields are Optional because the scaffold starts with nothing active.
The runtime controller owns and mutates this state as the pipeline
progresses through projection → fusion → extraction → hydration → synthesis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.core.types.ids import EvidenceBagId, ManifoldId


@dataclass
class ModelBridgeState:
    """Placeholder for current model bridge configuration at runtime."""

    active_model: Optional[str] = None
    active_tokeniser: Optional[str] = None
    embedding_dimensions: int = 0
    context_window: int = 0
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeState:
    """
    Typed runtime state for the active session.

    Holds references to all active manifolds, the current query,
    the current evidence bag, and model bridge state.
    """

    # Active manifold references
    identity_manifold_id: Optional[ManifoldId] = None
    external_manifold_id: Optional[ManifoldId] = None
    virtual_manifold_id: Optional[ManifoldId] = None

    # Current query context
    current_query: Optional[str] = None
    current_query_embedding_ref: Optional[str] = None

    # Current evidence bag reference
    current_evidence_bag_id: Optional[EvidenceBagId] = None

    # Model bridge state
    model_bridge_state: ModelBridgeState = field(default_factory=ModelBridgeState)

    # Session metadata
    session_id: Optional[str] = None
    session_metadata: Dict[str, Any] = field(default_factory=dict)

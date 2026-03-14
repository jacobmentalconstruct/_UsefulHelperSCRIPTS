"""
Model Bridge Contract — single boundary for all model interaction.

Ownership: src/core/contracts/model_bridge_contract.py
    Defines the typed request/response shapes and abstract interface
    for all model interaction. No other subsystem talks directly to
    embedding or language models.

The model bridge owns:
    - Embedding requests (text → vector)
    - Synthesis requests (evidence → generated output)
    - Token budget mediation (estimating and enforcing limits)
    - Model/tokeniser identity tracking

The model bridge is synthesis-only from the manifold perspective:
    - It consumes hydrated evidence bundles
    - It produces generated text or structured output
    - It never directly modifies manifold state

Legacy context:
    - OllamaClientMS HTTP patterns
    - Token budget estimation from TokenPackerMS
    - Batch embedding from ReferenceEmbedPipelineMS
    - mxbai-embed-large: 1024-d vectors via Ollama
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.types.enums import EmbeddingMetricType


# ---------------------------------------------------------------------------
# Model identity
# ---------------------------------------------------------------------------

@dataclass
class ModelIdentity:
    """Identifies a specific model and its tokeniser."""

    model_name: str
    model_version: str = ""
    tokeniser_name: str = ""
    tokeniser_version: str = ""
    context_window: int = 0
    embedding_dimensions: int = 0
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Embedding request / response
# ---------------------------------------------------------------------------

@dataclass
class EmbedRequest:
    """Request to embed text content into vector space."""

    texts: List[str]
    model: str = ""
    batch_size: int = 64
    normalize: bool = True
    metric_type: EmbeddingMetricType = EmbeddingMetricType.COSINE
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbedResponse:
    """Response containing embedding vectors."""

    vectors: List[List[float]]
    model: str = ""
    dimensions: int = 0
    normalized: bool = True
    metric_type: EmbeddingMetricType = EmbeddingMetricType.COSINE
    token_counts: List[int] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Synthesis request / response
# ---------------------------------------------------------------------------

@dataclass
class SynthesisRequest:
    """Request to synthesize output from evidence context."""

    evidence_context: str
    query: str
    model: str = ""
    max_tokens: int = 4096
    system_prompt: Optional[str] = None
    temperature: float = 0.0
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SynthesisResponse:
    """Response from synthesis."""

    text: str
    model: str = ""
    tokens_used: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    finish_reason: str = ""
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Token budget metadata
# ---------------------------------------------------------------------------

@dataclass
class TokenBudgetMetadata:
    """
    Token budget information for the model bridge to enforce.

    Tracks available context window space, evidence allocation,
    and synthesis reservation.
    """

    context_window: int = 0
    evidence_budget: int = 8000
    synthesis_budget: int = 4096
    system_prompt_tokens: int = 0
    remaining_for_evidence: int = 0
    estimator: str = "split_heuristic"


# ---------------------------------------------------------------------------
# Abstract contract
# ---------------------------------------------------------------------------

class ModelBridgeContract(ABC):
    """
    Abstract contract for the model bridge.

    All model interaction flows through this single boundary.
    """

    @abstractmethod
    def embed(self, request: EmbedRequest) -> EmbedResponse:
        """Embed text content into vector representations."""
        ...

    @abstractmethod
    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        """Synthesize output from evidence context and query."""
        ...

    @abstractmethod
    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for a text string."""
        ...

    @abstractmethod
    def get_model_identity(self) -> Optional[ModelIdentity]:
        """Return the current model identity, if configured."""
        ...

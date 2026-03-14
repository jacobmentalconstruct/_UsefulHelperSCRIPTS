"""
Model Bridge — centralized model interaction boundary.

Ownership: src/core/model_bridge/model_bridge.py
    This module owns ALL model interaction. No other subsystem talks
    directly to embedding or language models. The bridge translates
    between typed contract requests (EmbedRequest, SynthesisRequest)
    and the configured backend.

Responsibilities:
    - Embedding requests (text → vector) via deterministic local backend
      or Ollama HTTP /api/embed
    - Synthesis requests (evidence context → generated output) via
      Ollama /api/generate
    - Token estimation via canonical split heuristic (no HTTP needed)
    - Model identity reporting from configuration
    - Backend routing: deterministic (default, offline) or Ollama (opt-in)

Design constraints:
    - stdlib HTTP only for Ollama path (urllib.request)
    - numpy dependency deferred to deterministic provider (lazy import)
    - No prompt construction — SynthesisRequest arrives pre-built
    - estimate_tokens() works offline (pure computation, no server)
    - get_model_identity() works from config (no server discovery)
    - Model resolution: request.model → config model → error
    - Explicit error hierarchy: ModelBridgeError → Connection / Response
    - Read-only from the manifold perspective — never mutates graph state
    - Fallback chain: deterministic → Ollama → no-embedding

Pipeline position: Hydration → Model Bridge → (Runtime orchestration)

Legacy context:
    - OllamaClientMS for HTTP-based model interaction
    - ReferenceEmbedPipelineMS for batch embedding
    - TokenPackerMS for token estimation (len(text.split()) * 1.3 + 1)
    - mxbai-embed-large: 1024-d vectors via Ollama
"""

from __future__ import annotations

import json
import math
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.contracts.model_bridge_contract import (
    EmbedRequest,
    EmbedResponse,
    ModelBridgeContract,
    ModelIdentity,
    SynthesisRequest,
    SynthesisResponse,
)
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class ModelBridgeError(Exception):
    """Base error for all model bridge failures."""


class ModelConnectionError(ModelBridgeError):
    """Network-level failure: connection refused, timeout, DNS resolution."""


class ModelResponseError(ModelBridgeError):
    """Response-level failure: malformed JSON, unexpected schema, missing keys."""


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class ModelBridgeConfig:
    """
    Configuration for the model bridge.

    Controls embedding backend selection, endpoint location, model
    selection, timeouts, and metadata about model capabilities.

    Embedding backend:
        - "deterministic" (default): Local BPE-SVD embeddings via
          pre-trained artifacts. Requires tokenizer_path and
          embeddings_path to point to existing files. Falls back
          to Ollama when artifacts are unavailable.
        - "ollama": Neural embeddings via Ollama HTTP API.
    """

    # --- Ollama connection ---
    base_url: str = "http://localhost:11434"
    embed_model: str = "mxbai-embed-large"
    synthesis_model: str = ""
    timeout_seconds: float = 60.0
    context_window: int = 0
    embedding_dimensions: int = 0
    estimator: str = "split_heuristic"

    # --- Embedding backend selection ---
    embed_backend: str = "deterministic"
    deterministic_tokenizer_path: str = ""
    deterministic_embeddings_path: str = ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _normalize_l2(vector: List[float]) -> List[float]:
    """L2-normalize a single vector. Returns zero vector if norm is zero."""
    norm = math.sqrt(sum(x * x for x in vector))
    if norm == 0.0:
        return vector
    return [x / norm for x in vector]


# ---------------------------------------------------------------------------
# Model Bridge
# ---------------------------------------------------------------------------

class ModelBridge(ModelBridgeContract):
    """
    Concrete model bridge — single boundary for all model interaction.

    Supports two embedding backends:
        - deterministic: Local BPE-SVD embeddings (offline, no server)
        - ollama: Ollama HTTP API (requires running server)

    Synthesis always uses Ollama. The deterministic backend covers
    embedding only.

    Fallback chain for embedding:
        deterministic → Ollama → no-embedding (graceful degradation)
    """

    def __init__(self, config: Optional[ModelBridgeConfig] = None) -> None:
        self._config = config or ModelBridgeConfig()
        self._deterministic_provider: Any = None  # lazy init

    # -------------------------------------------------------------------
    # Internal: HTTP transport
    # -------------------------------------------------------------------

    def _http_post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST JSON to the Ollama backend and return parsed JSON.

        Raises:
            ModelConnectionError: Connection refused, timeout, DNS failure.
            ModelResponseError: Non-JSON response, unexpected status code.
        """
        url = f"{self._config.base_url}{path}"
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                req, timeout=self._config.timeout_seconds,
            ) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise ModelConnectionError(
                f"Failed to connect to {url}: {exc.reason}"
            ) from exc
        except socket.timeout as exc:
            raise ModelConnectionError(
                f"Timeout connecting to {url} after {self._config.timeout_seconds}s"
            ) from exc
        except OSError as exc:
            raise ModelConnectionError(
                f"Network error connecting to {url}: {exc}"
            ) from exc

        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ModelResponseError(
                f"Malformed JSON from {url}: {exc}"
            ) from exc

    # -------------------------------------------------------------------
    # Internal: embedding backend routing
    # -------------------------------------------------------------------

    def _resolve_embed_backend(self) -> str:
        """Determine which embedding backend to use.

        Returns "deterministic" only when ALL of:
            - config.embed_backend == "deterministic"
            - both artifact paths are non-empty strings
            - both files exist on disk

        Otherwise returns "ollama".
        """
        if self._config.embed_backend != "deterministic":
            return "ollama"

        tok_path = self._config.deterministic_tokenizer_path
        emb_path = self._config.deterministic_embeddings_path

        if not tok_path or not emb_path:
            return "ollama"

        if not os.path.isfile(tok_path) or not os.path.isfile(emb_path):
            logger.info(
                "ModelBridge: deterministic backend configured but artifacts "
                "not found (tokenizer=%s, embeddings=%s) — falling back to Ollama",
                tok_path, emb_path,
            )
            return "ollama"

        return "deterministic"

    def _get_deterministic_provider(self) -> Any:
        """Lazily create and cache the DeterministicEmbedProvider.

        Import is deferred to avoid module-level numpy dependency.
        The provider is constructed once and reused for all subsequent
        embed() calls.
        """
        if self._deterministic_provider is None:
            from src.core.model_bridge.deterministic_provider import (
                DeterministicEmbedProvider,
            )
            self._deterministic_provider = DeterministicEmbedProvider(
                tokenizer_path=self._config.deterministic_tokenizer_path,
                embeddings_path=self._config.deterministic_embeddings_path,
            )
        return self._deterministic_provider

    def _embed_deterministic(self, request: EmbedRequest) -> EmbedResponse:
        """Embed via the local deterministic BPE-SVD backend.

        Calls the provider's embed_texts(), applies L2 normalization
        if requested, and wraps the result in an EmbedResponse that
        conforms to the existing contract.

        Token-level artifacts (token_ids) are carried in
        EmbedResponse.properties["token_artifacts"].
        """
        provider = self._get_deterministic_provider()
        result = provider.embed_texts(request.texts)

        vectors = result.vectors
        if request.normalize:
            vectors = [_normalize_l2(v) for v in vectors]

        properties: Dict[str, Any] = {}
        if result.token_artifacts:
            properties["token_artifacts"] = result.token_artifacts

        return EmbedResponse(
            vectors=vectors,
            model="deterministic-bpe-svd",
            dimensions=result.dimensions,
            normalized=request.normalize,
            metric_type=request.metric_type,
            token_counts=result.token_counts,
            properties=properties,
        )

    # -------------------------------------------------------------------
    # Internal: model resolution
    # -------------------------------------------------------------------

    def _resolve_embed_model(self, request: EmbedRequest) -> str:
        """Pick embedding model: request.model → config.embed_model → error."""
        model = request.model or self._config.embed_model
        if not model:
            raise ModelBridgeError(
                "No embedding model specified in request or config"
            )
        return model

    def _resolve_synthesis_model(self, request: SynthesisRequest) -> str:
        """Pick synthesis model: request.model → config.synthesis_model → error."""
        model = request.model or self._config.synthesis_model
        if not model:
            raise ModelBridgeError(
                "No synthesis model specified in request or config"
            )
        return model

    # -------------------------------------------------------------------
    # Public API: embed
    # -------------------------------------------------------------------

    def embed(self, request: EmbedRequest) -> EmbedResponse:
        """
        Embed text content into vector representations.

        Routes to the configured embedding backend:
            - deterministic: Local BPE-SVD via pre-trained artifacts
            - ollama: HTTP POST to Ollama /api/embed

        Fallback chain: if deterministic fails, falls back to Ollama.

        Args:
            request: EmbedRequest with texts to embed.

        Returns:
            EmbedResponse with vectors, dimensions, and token counts.

        Raises:
            ModelBridgeError: No model specified (Ollama path).
            ModelConnectionError: Cannot reach Ollama (Ollama path).
            ModelResponseError: Unexpected response shape (Ollama path).
        """
        if not request.texts:
            return EmbedResponse(
                vectors=[],
                model="deterministic-bpe-svd"
                if self._resolve_embed_backend() == "deterministic"
                else self._resolve_embed_model(request),
                dimensions=0,
                normalized=request.normalize,
                metric_type=request.metric_type,
            )

        # Route to deterministic backend if configured and available
        backend = self._resolve_embed_backend()
        if backend == "deterministic":
            try:
                return self._embed_deterministic(request)
            except Exception as exc:
                logger.warning(
                    "ModelBridge: deterministic embed failed, "
                    "falling back to Ollama: %s",
                    exc,
                )
                # Fall through to Ollama path below

        model = self._resolve_embed_model(request)

        payload: Dict[str, Any] = {
            "model": model,
            "input": request.texts,
        }

        raw = self._http_post("/api/embed", payload)

        # Parse embeddings from Ollama response
        embeddings = raw.get("embeddings")
        if embeddings is None:
            raise ModelResponseError(
                "Ollama /api/embed response missing 'embeddings' key"
            )

        if not isinstance(embeddings, list):
            raise ModelResponseError(
                f"Expected list for 'embeddings', got {type(embeddings).__name__}"
            )

        vectors: List[List[float]] = embeddings

        # Normalize if requested
        if request.normalize:
            vectors = [_normalize_l2(v) for v in vectors]

        # Determine dimensions from first vector
        dimensions = len(vectors[0]) if vectors else 0

        # Extract token counts if available
        token_counts: List[int] = []
        prompt_eval_count = raw.get("prompt_eval_count")
        if prompt_eval_count is not None and len(request.texts) == 1:
            token_counts = [int(prompt_eval_count)]

        return EmbedResponse(
            vectors=vectors,
            model=raw.get("model", model),
            dimensions=dimensions,
            normalized=request.normalize,
            metric_type=request.metric_type,
            token_counts=token_counts,
        )

    # -------------------------------------------------------------------
    # Public API: synthesize
    # -------------------------------------------------------------------

    def synthesize(self, request: SynthesisRequest) -> SynthesisResponse:
        """
        Synthesize output from evidence context via Ollama /api/generate.

        The bridge does NOT own prompt construction. The request's
        evidence_context, query, and system_prompt arrive pre-built.

        Args:
            request: SynthesisRequest with evidence_context and query.

        Returns:
            SynthesisResponse with generated text and token metadata.

        Raises:
            ModelBridgeError: No model specified.
            ModelConnectionError: Cannot reach Ollama.
            ModelResponseError: Unexpected response shape.
        """
        model = self._resolve_synthesis_model(request)

        # Build the prompt: evidence context + query
        prompt_parts: List[str] = []
        if request.evidence_context:
            prompt_parts.append(request.evidence_context)
        if request.query:
            prompt_parts.append(request.query)
        prompt = "\n\n".join(prompt_parts)

        payload: Dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        if request.system_prompt:
            payload["system"] = request.system_prompt

        raw = self._http_post("/api/generate", payload)

        # Parse response
        text = raw.get("response", "")
        if not isinstance(text, str):
            raise ModelResponseError(
                f"Expected string for 'response', got {type(text).__name__}"
            )

        prompt_eval_count = raw.get("prompt_eval_count", 0)
        eval_count = raw.get("eval_count", 0)

        # Determine finish reason
        done = raw.get("done", False)
        done_reason = raw.get("done_reason", "")
        if done_reason:
            finish_reason = done_reason
        elif done:
            finish_reason = "stop"
        else:
            finish_reason = "unknown"

        return SynthesisResponse(
            text=text,
            model=raw.get("model", model),
            tokens_used=int(prompt_eval_count) + int(eval_count),
            prompt_tokens=int(prompt_eval_count),
            completion_tokens=int(eval_count),
            finish_reason=finish_reason,
        )

    # -------------------------------------------------------------------
    # Public API: estimate_tokens
    # -------------------------------------------------------------------

    def estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for a text string.

        Bridge-canonical token estimator. Uses the same split heuristic
        as Chunk.__post_init__: int(len(text.split()) * 1.3 + 1).
        Works offline — no HTTP call, no running model server needed.

        This is the single authoritative token estimation boundary for
        model-facing budgeting. Future upgrade path: swap the heuristic
        for a real tokenizer backend while preserving the same signature.

        Args:
            text: Text to estimate tokens for.

        Returns:
            Estimated token count (integer).
        """
        if not text:
            return 0
        return int(len(text.split()) * 1.3 + 1)

    # -------------------------------------------------------------------
    # Public API: get_model_identity
    # -------------------------------------------------------------------

    def get_model_identity(self) -> Optional[ModelIdentity]:
        """
        Return the current model identity from configuration.

        Config-driven — no HTTP call to discover model metadata.
        Returns None if no model is configured.

        Returns:
            ModelIdentity with model name, context window, embedding
            dimensions, and bridge configuration properties.
        """
        model_name = self._config.synthesis_model or self._config.embed_model
        if not model_name:
            return None

        return ModelIdentity(
            model_name=model_name,
            context_window=self._config.context_window,
            embedding_dimensions=self._config.embedding_dimensions,
            properties={
                "base_url": self._config.base_url,
                "estimator": self._config.estimator,
                "embed_model": self._config.embed_model,
                "synthesis_model": self._config.synthesis_model,
                "embed_backend": self._config.embed_backend,
            },
        )

"""
Phase 8 Tests — Model Bridge (Ollama HTTP).

Tests for:
    - ModelBridgeConfig defaults and overrides
    - Token estimation (heuristic, canonical bridge estimator)
    - Model identity from configuration
    - Embed request → Ollama payload → EmbedResponse
    - Synthesize request → Ollama payload → SynthesisResponse
    - Connection and response error handling
    - Empty input handling
    - Model resolution (request → config → error)
    - End-to-end flows with mocked HTTP
    - Backward compatibility imports

All tests use mock/stub HTTP — no live Ollama server required.
"""

import dataclasses
import json
from unittest.mock import patch, MagicMock

import pytest

from src.core.types.enums import EmbeddingMetricType
from src.core.types.graph import Chunk

from src.core.contracts.model_bridge_contract import (
    EmbedRequest,
    EmbedResponse,
    ModelIdentity,
    SynthesisRequest,
    SynthesisResponse,
)

from src.core.model_bridge.model_bridge import (
    ModelBridge,
    ModelBridgeConfig,
    ModelBridgeError,
    ModelConnectionError,
    ModelResponseError,
)


# ---------------------------------------------------------------------------
# Helpers: mock HTTP responses
# ---------------------------------------------------------------------------

def _make_bridge(**config_overrides) -> ModelBridge:
    """Create a ModelBridge with test-friendly defaults."""
    cfg = ModelBridgeConfig(**config_overrides)
    return ModelBridge(config=cfg)


def _mock_embed_response(
    vectors: list,
    model: str = "mxbai-embed-large",
    prompt_eval_count: int = 10,
) -> dict:
    """Return a canned Ollama /api/embed JSON response."""
    return {
        "model": model,
        "embeddings": vectors,
        "prompt_eval_count": prompt_eval_count,
    }


def _mock_synthesis_response(
    text: str = "Generated answer.",
    model: str = "llama3",
    prompt_eval_count: int = 42,
    eval_count: int = 15,
    done: bool = True,
    done_reason: str = "",
) -> dict:
    """Return a canned Ollama /api/generate JSON response."""
    result = {
        "model": model,
        "response": text,
        "done": done,
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
    }
    if done_reason:
        result["done_reason"] = done_reason
    return result


# ===========================================================================
# TestModelBridgeConfig
# ===========================================================================

class TestModelBridgeConfig:
    """ModelBridgeConfig defaults and overrides."""

    def test_default_values(self) -> None:
        cfg = ModelBridgeConfig()
        assert cfg.base_url == "http://localhost:11434"
        assert cfg.embed_model == "mxbai-embed-large"
        assert cfg.synthesis_model == ""
        assert cfg.timeout_seconds == 60.0
        assert cfg.context_window == 0
        assert cfg.embedding_dimensions == 0
        assert cfg.estimator == "split_heuristic"

    def test_custom_values(self) -> None:
        cfg = ModelBridgeConfig(
            base_url="http://remote:8080",
            embed_model="custom-embed",
            synthesis_model="custom-synth",
            timeout_seconds=30.0,
            context_window=4096,
            embedding_dimensions=768,
            estimator="tiktoken",
        )
        assert cfg.base_url == "http://remote:8080"
        assert cfg.synthesis_model == "custom-synth"
        assert cfg.context_window == 4096

    def test_is_dataclass(self) -> None:
        assert dataclasses.is_dataclass(ModelBridgeConfig)


# ===========================================================================
# TestEstimateTokens
# ===========================================================================

class TestEstimateTokens:
    """Token estimation — canonical bridge heuristic."""

    def test_heuristic_formula(self) -> None:
        bridge = _make_bridge()
        text = "hello world foo bar"  # 4 words
        expected = int(4 * 1.3 + 1)  # 6
        assert bridge.estimate_tokens(text) == expected

    def test_empty_text_returns_zero(self) -> None:
        bridge = _make_bridge()
        assert bridge.estimate_tokens("") == 0

    def test_single_word(self) -> None:
        bridge = _make_bridge()
        assert bridge.estimate_tokens("hello") == int(1 * 1.3 + 1)

    def test_matches_chunk_heuristic(self) -> None:
        """Bridge estimate_tokens matches Chunk.__post_init__ formula."""
        bridge = _make_bridge()
        text = "This is a test sentence with several words in it"
        chunk = Chunk(chunk_hash="test", chunk_text=text)
        assert bridge.estimate_tokens(text) == chunk.token_estimate


# ===========================================================================
# TestGetModelIdentity
# ===========================================================================

class TestGetModelIdentity:
    """Model identity from configuration."""

    def test_returns_model_identity(self) -> None:
        bridge = _make_bridge(synthesis_model="llama3")
        identity = bridge.get_model_identity()
        assert isinstance(identity, ModelIdentity)
        assert identity.model_name == "llama3"

    def test_falls_back_to_embed_model(self) -> None:
        bridge = _make_bridge(synthesis_model="", embed_model="mxbai-embed-large")
        identity = bridge.get_model_identity()
        assert identity.model_name == "mxbai-embed-large"

    def test_properties_include_base_url(self) -> None:
        bridge = _make_bridge(base_url="http://example:1234")
        identity = bridge.get_model_identity()
        assert identity.properties["base_url"] == "http://example:1234"


# ===========================================================================
# TestEmbedRequest
# ===========================================================================

class TestEmbedRequest:
    """Embed request transformation and response handling."""

    def test_single_text(self) -> None:
        bridge = _make_bridge()
        request = EmbedRequest(texts=["hello world"])
        mock_resp = _mock_embed_response(vectors=[[0.1, 0.2, 0.3]])

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.embed(request)

        assert len(response.vectors) == 1
        assert response.dimensions == 3

    def test_multiple_texts(self) -> None:
        bridge = _make_bridge()
        request = EmbedRequest(texts=["first", "second", "third"])
        mock_resp = _mock_embed_response(
            vectors=[[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]],
        )

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.embed(request)

        assert len(response.vectors) == 3

    def test_custom_model_override(self) -> None:
        bridge = _make_bridge(embed_model="default-model")
        request = EmbedRequest(texts=["test"], model="custom-model")
        mock_resp = _mock_embed_response(vectors=[[0.1]])

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            bridge.embed(request)

        # Verify the custom model was sent to Ollama
        call_payload = mock_post.call_args[0][1]
        assert call_payload["model"] == "custom-model"

    def test_normalize_flag_preserved(self) -> None:
        bridge = _make_bridge()
        request = EmbedRequest(texts=["test"], normalize=False)
        mock_resp = _mock_embed_response(vectors=[[3.0, 4.0]])

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.embed(request)

        # When normalize=False, vectors should pass through as-is
        assert response.vectors[0] == [3.0, 4.0]
        assert response.normalized is False


# ===========================================================================
# TestEmbedResponse
# ===========================================================================

class TestEmbedResponse:
    """Embed response parsing from Ollama."""

    def test_vectors_populated(self) -> None:
        bridge = _make_bridge()
        request = EmbedRequest(texts=["test"])
        mock_resp = _mock_embed_response(vectors=[[0.5, 0.6, 0.7]])

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.embed(request)

        assert isinstance(response, EmbedResponse)
        assert len(response.vectors[0]) == 3

    def test_dimensions_set(self) -> None:
        bridge = _make_bridge()
        request = EmbedRequest(texts=["test"])
        mock_resp = _mock_embed_response(vectors=[[0.1, 0.2, 0.3, 0.4]])

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.embed(request)

        assert response.dimensions == 4

    def test_token_counts_from_ollama(self) -> None:
        bridge = _make_bridge()
        request = EmbedRequest(texts=["test"])
        mock_resp = _mock_embed_response(
            vectors=[[0.1]], prompt_eval_count=7,
        )

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.embed(request)

        assert response.token_counts == [7]


# ===========================================================================
# TestSynthesizeRequest
# ===========================================================================

class TestSynthesizeRequest:
    """Synthesize request transformation."""

    def test_basic_query_and_evidence(self) -> None:
        bridge = _make_bridge(synthesis_model="llama3")
        request = SynthesisRequest(
            evidence_context="Evidence here.",
            query="What is the answer?",
        )
        mock_resp = _mock_synthesis_response(text="The answer is 42.")

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            response = bridge.synthesize(request)

        call_payload = mock_post.call_args[0][1]
        assert "Evidence here." in call_payload["prompt"]
        assert "What is the answer?" in call_payload["prompt"]
        assert call_payload["stream"] is False
        assert response.text == "The answer is 42."

    def test_system_prompt_passed(self) -> None:
        bridge = _make_bridge(synthesis_model="llama3")
        request = SynthesisRequest(
            evidence_context="ctx",
            query="q",
            system_prompt="You are a helpful assistant.",
        )
        mock_resp = _mock_synthesis_response()

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            bridge.synthesize(request)

        call_payload = mock_post.call_args[0][1]
        assert call_payload["system"] == "You are a helpful assistant."

    def test_temperature_passed(self) -> None:
        bridge = _make_bridge(synthesis_model="llama3")
        request = SynthesisRequest(
            evidence_context="ctx", query="q", temperature=0.7,
        )
        mock_resp = _mock_synthesis_response()

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            bridge.synthesize(request)

        call_payload = mock_post.call_args[0][1]
        assert call_payload["options"]["temperature"] == 0.7

    def test_max_tokens_as_num_predict(self) -> None:
        bridge = _make_bridge(synthesis_model="llama3")
        request = SynthesisRequest(
            evidence_context="ctx", query="q", max_tokens=2048,
        )
        mock_resp = _mock_synthesis_response()

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            bridge.synthesize(request)

        call_payload = mock_post.call_args[0][1]
        assert call_payload["options"]["num_predict"] == 2048


# ===========================================================================
# TestSynthesizeResponse
# ===========================================================================

class TestSynthesizeResponse:
    """Synthesize response parsing from Ollama."""

    def test_text_populated(self) -> None:
        bridge = _make_bridge(synthesis_model="llama3")
        request = SynthesisRequest(evidence_context="ctx", query="q")
        mock_resp = _mock_synthesis_response(text="Output text.")

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.synthesize(request)

        assert response.text == "Output text."
        assert isinstance(response, SynthesisResponse)

    def test_token_counts_mapped(self) -> None:
        bridge = _make_bridge(synthesis_model="llama3")
        request = SynthesisRequest(evidence_context="ctx", query="q")
        mock_resp = _mock_synthesis_response(
            prompt_eval_count=100, eval_count=50,
        )

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.synthesize(request)

        assert response.prompt_tokens == 100
        assert response.completion_tokens == 50
        assert response.tokens_used == 150

    def test_finish_reason_set(self) -> None:
        bridge = _make_bridge(synthesis_model="llama3")
        request = SynthesisRequest(evidence_context="ctx", query="q")

        # Test done=True without done_reason → "stop"
        mock_resp = _mock_synthesis_response(done=True, done_reason="")
        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.synthesize(request)
        assert response.finish_reason == "stop"

        # Test with explicit done_reason
        mock_resp = _mock_synthesis_response(done=True, done_reason="length")
        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.synthesize(request)
        assert response.finish_reason == "length"


# ===========================================================================
# TestConnectionErrors
# ===========================================================================

class TestConnectionErrors:
    """Network-level error handling."""

    def test_connection_refused(self) -> None:
        bridge = _make_bridge()
        request = EmbedRequest(texts=["test"])

        with patch.object(
            bridge, "_http_post",
            side_effect=ModelConnectionError("Connection refused"),
        ):
            with pytest.raises(ModelConnectionError, match="Connection refused"):
                bridge.embed(request)

    def test_timeout(self) -> None:
        bridge = _make_bridge()
        request = SynthesisRequest(
            evidence_context="ctx", query="q", model="llama3",
        )

        with patch.object(
            bridge, "_http_post",
            side_effect=ModelConnectionError("Timeout"),
        ):
            with pytest.raises(ModelConnectionError, match="Timeout"):
                bridge.synthesize(request)

    def test_malformed_json(self) -> None:
        bridge = _make_bridge()
        request = EmbedRequest(texts=["test"])

        with patch.object(
            bridge, "_http_post",
            side_effect=ModelResponseError("Malformed JSON"),
        ):
            with pytest.raises(ModelResponseError, match="Malformed"):
                bridge.embed(request)


# ===========================================================================
# TestEmptyInputs
# ===========================================================================

class TestEmptyInputs:
    """Edge cases with empty or minimal inputs."""

    def test_empty_texts_returns_empty_response(self) -> None:
        bridge = _make_bridge()
        request = EmbedRequest(texts=[])
        response = bridge.embed(request)
        assert response.vectors == []
        assert response.dimensions == 0

    def test_empty_query_handled(self) -> None:
        bridge = _make_bridge(synthesis_model="llama3")
        request = SynthesisRequest(evidence_context="ctx", query="")
        mock_resp = _mock_synthesis_response(text="Response.")

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.synthesize(request)

        assert response.text == "Response."

    def test_empty_evidence_context_handled(self) -> None:
        bridge = _make_bridge(synthesis_model="llama3")
        request = SynthesisRequest(evidence_context="", query="What?")
        mock_resp = _mock_synthesis_response(text="Answer.")

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.synthesize(request)

        assert response.text == "Answer."


# ===========================================================================
# TestModelResolution
# ===========================================================================

class TestModelResolution:
    """Model resolution: request.model → config → error."""

    def test_request_model_overrides_config(self) -> None:
        bridge = _make_bridge(embed_model="config-model")
        request = EmbedRequest(texts=["test"], model="request-model")
        mock_resp = _mock_embed_response(vectors=[[0.1]])

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            bridge.embed(request)

        call_payload = mock_post.call_args[0][1]
        assert call_payload["model"] == "request-model"

    def test_config_model_used_as_fallback(self) -> None:
        bridge = _make_bridge(embed_model="config-model")
        request = EmbedRequest(texts=["test"], model="")
        mock_resp = _mock_embed_response(vectors=[[0.1]])

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            bridge.embed(request)

        call_payload = mock_post.call_args[0][1]
        assert call_payload["model"] == "config-model"

    def test_no_model_raises_error(self) -> None:
        bridge = _make_bridge(embed_model="", synthesis_model="")
        request = EmbedRequest(texts=["test"], model="")

        with pytest.raises(ModelBridgeError, match="No embedding model"):
            bridge.embed(request)


# ===========================================================================
# TestEndToEnd
# ===========================================================================

class TestEndToEnd:
    """Full round-trip flows with mocked HTTP."""

    def test_embed_round_trip(self) -> None:
        """Full embed: request → Ollama payload → response."""
        bridge = _make_bridge(embed_model="mxbai-embed-large")
        request = EmbedRequest(
            texts=["hello world", "foo bar"],
            normalize=True,
        )
        mock_resp = _mock_embed_response(
            vectors=[[3.0, 4.0], [1.0, 0.0]],
            model="mxbai-embed-large",
        )

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            response = bridge.embed(request)

        # Verify Ollama was called correctly
        assert mock_post.call_args[0][0] == "/api/embed"
        payload = mock_post.call_args[0][1]
        assert payload["model"] == "mxbai-embed-large"
        assert payload["input"] == ["hello world", "foo bar"]

        # Verify response
        assert len(response.vectors) == 2
        assert response.model == "mxbai-embed-large"
        assert response.dimensions == 2
        assert response.normalized is True

        # Verify L2 normalization was applied
        v0 = response.vectors[0]
        norm = sum(x * x for x in v0) ** 0.5
        assert abs(norm - 1.0) < 1e-6

    def test_synthesize_round_trip(self) -> None:
        """Full synthesize: request → Ollama payload → response."""
        bridge = _make_bridge(synthesis_model="llama3")
        request = SynthesisRequest(
            evidence_context="Node A relates to Node B via SEMANTIC edge.",
            query="How are A and B related?",
            system_prompt="Answer from evidence only.",
            temperature=0.0,
            max_tokens=1024,
        )
        mock_resp = _mock_synthesis_response(
            text="A and B are semantically related.",
            model="llama3",
            prompt_eval_count=30,
            eval_count=8,
            done=True,
        )

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            response = bridge.synthesize(request)

        # Verify Ollama was called correctly
        assert mock_post.call_args[0][0] == "/api/generate"
        payload = mock_post.call_args[0][1]
        assert payload["model"] == "llama3"
        assert "Node A relates to Node B" in payload["prompt"]
        assert "How are A and B related?" in payload["prompt"]
        assert payload["system"] == "Answer from evidence only."
        assert payload["stream"] is False
        assert payload["options"]["temperature"] == 0.0
        assert payload["options"]["num_predict"] == 1024

        # Verify response
        assert response.text == "A and B are semantically related."
        assert response.prompt_tokens == 30
        assert response.completion_tokens == 8
        assert response.tokens_used == 38
        assert response.finish_reason == "stop"


# ===========================================================================
# TestBackwardCompat
# ===========================================================================

class TestBackwardCompat:
    """Backward compatibility: imports from module and __init__."""

    def test_import_from_model_bridge_module(self) -> None:
        from src.core.model_bridge.model_bridge import (
            ModelBridge as MB,
            ModelBridgeConfig as MBC,
            ModelBridgeError as MBE,
            ModelConnectionError as MCE,
            ModelResponseError as MRE,
        )
        assert MB is ModelBridge
        assert MBC is ModelBridgeConfig
        assert issubclass(MCE, MBE)
        assert issubclass(MRE, MBE)

    def test_import_from_init(self) -> None:
        from src.core.model_bridge import (
            ModelBridge as MB,
            ModelBridgeConfig as MBC,
        )
        assert MB is ModelBridge
        assert MBC is ModelBridgeConfig

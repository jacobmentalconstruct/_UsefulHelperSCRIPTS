"""
Phase 12 Tests — Deterministic Embedding Backend.

Tests for:
    - DeterministicEmbedProvider in isolation (BPE encoding, vector lookup,
      mean pooling)
    - ModelBridgeConfig deterministic-specific fields
    - Backend routing (_resolve_embed_backend)
    - ModelBridge.embed() with deterministic backend
    - ModelBridge.embed() with Ollama backend (unchanged behavior)
    - Fallback chain: deterministic -> Ollama -> error
    - Lazy numpy import isolation
    - End-to-end: deterministic embed -> QueryProjection -> query_embedding

All deterministic tests use local test artifacts (tokenizer JSON + .npy).
Ollama path tests use mock/stub HTTP — no live server required.
"""

import json
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

np = pytest.importorskip("numpy", reason="numpy required for deterministic embedding tests")

from src.core.contracts.model_bridge_contract import (
    EmbedRequest,
    EmbedResponse,
)
from src.core.types.enums import EmbeddingMetricType

from src.core.model_bridge.model_bridge import (
    ModelBridge,
    ModelBridgeConfig,
    ModelBridgeError,
    ModelConnectionError,
    ModelResponseError,
)
from src.core.model_bridge.deterministic_provider import (
    DeterministicEmbedProvider,
    DeterministicEmbedResult,
)


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_tokenizer_spec() -> dict:
    """Minimal BPE tokenizer spec for testing.

    Vocab: single chars h, e, l, o, w, r, d, plus </w>,
    plus merged symbols he, ll. 11 entries total.

    Merges (applied in order):
        h + e  -> he
        l + l  -> ll
        l + o  -> lo   (won't fire on "hello" after ll merges)

    For "hello": ['he', 'll', 'o', '</w>'] -> IDs [8, 9, 3, 4]
    For "world": ['w', 'o', 'r', 'l', 'd', '</w>'] -> IDs [5, 3, 6, 2, 7, 4]
    """
    return {
        "vocab": {
            "h": 0, "e": 1, "l": 2, "o": 3, "</w>": 4,
            "w": 5, "r": 6, "d": 7,
            "he": 8, "ll": 9, "lo": 10,
        },
        "merges": [
            ["h", "e"],
            ["l", "l"],
            ["l", "o"],
        ],
        "end_of_word": "</w>",
    }


def _make_embeddings_array(vocab_size: int = 11, dim: int = 4) -> np.ndarray:
    """Create a deterministic embedding matrix for testing."""
    rng = np.random.RandomState(42)
    return rng.randn(vocab_size, dim).astype(np.float32)


def _write_test_artifacts(tmp_path: Path, vocab_size: int = 11, dim: int = 4):
    """Write tokenizer JSON and embedding .npy to tmp_path.

    Returns (tokenizer_path, embeddings_path).
    """
    tok_path = str(tmp_path / "tokenizer.json")
    emb_path = str(tmp_path / "embeddings.npy")

    with open(tok_path, "w", encoding="utf-8") as f:
        json.dump(_make_tokenizer_spec(), f)

    np.save(emb_path, _make_embeddings_array(vocab_size, dim))

    return tok_path, emb_path


def _make_bridge_deterministic(tmp_path: Path, **overrides) -> ModelBridge:
    """Create a ModelBridge configured for deterministic embedding."""
    tok_path, emb_path = _write_test_artifacts(tmp_path)
    cfg_kwargs = {
        "embed_backend": "deterministic",
        "deterministic_tokenizer_path": tok_path,
        "deterministic_embeddings_path": emb_path,
    }
    cfg_kwargs.update(overrides)
    return ModelBridge(config=ModelBridgeConfig(**cfg_kwargs))


def _make_bridge_ollama(**overrides) -> ModelBridge:
    """Create a ModelBridge configured for Ollama embedding."""
    cfg_kwargs = {"embed_backend": "ollama"}
    cfg_kwargs.update(overrides)
    return ModelBridge(config=ModelBridgeConfig(**cfg_kwargs))


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


# ===========================================================================
# TestDeterministicEmbedProvider
# ===========================================================================

class TestDeterministicEmbedProvider:
    """DeterministicEmbedProvider in isolation."""

    def test_construction_loads_vocab_and_matrix(self, tmp_path: Path) -> None:
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        assert provider._dimensions == 4
        assert len(provider._vocab) == 11

    def test_invalid_embedding_shape_1d_raises(self, tmp_path: Path) -> None:
        tok_path = str(tmp_path / "tokenizer.json")
        emb_path = str(tmp_path / "bad_embeddings.npy")

        with open(tok_path, "w", encoding="utf-8") as f:
            json.dump(_make_tokenizer_spec(), f)

        np.save(emb_path, np.zeros(10))  # 1D, not 2D

        with pytest.raises(ValueError, match="2D"):
            DeterministicEmbedProvider(tok_path, emb_path)

    def test_missing_tokenizer_raises(self, tmp_path: Path) -> None:
        emb_path = str(tmp_path / "embeddings.npy")
        np.save(emb_path, _make_embeddings_array())

        with pytest.raises(FileNotFoundError):
            DeterministicEmbedProvider(str(tmp_path / "missing.json"), emb_path)

    def test_missing_embeddings_raises(self, tmp_path: Path) -> None:
        tok_path = str(tmp_path / "tokenizer.json")
        with open(tok_path, "w", encoding="utf-8") as f:
            json.dump(_make_tokenizer_spec(), f)

        with pytest.raises(FileNotFoundError):
            DeterministicEmbedProvider(tok_path, str(tmp_path / "missing.npy"))

    def test_bpe_encoding_known_word(self, tmp_path: Path) -> None:
        """BPE for 'hello': h+e->he, l+l->ll, result ['he','ll','o','</w>']."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        symbols = provider._encode_word("hello")
        assert symbols == ["he", "ll", "o", "</w>"]

    def test_unknown_tokens_map_to_negative_one(self, tmp_path: Path) -> None:
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        # 'z' is not in vocab
        ids = provider._encode("z")
        # 'z' -> ['z', '</w>'] -> z is unknown (-1), </w> is 4
        assert -1 in ids

    def test_embed_single_text_dimensions(self, tmp_path: Path) -> None:
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        result = provider.embed_texts(["hello"])
        assert len(result.vectors) == 1
        assert len(result.vectors[0]) == 4
        assert result.dimensions == 4

    def test_embed_multiple_texts_count(self, tmp_path: Path) -> None:
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        result = provider.embed_texts(["hello", "world", "hello world"])
        assert len(result.vectors) == 3
        assert len(result.token_counts) == 3
        assert len(result.token_artifacts) == 3

    def test_embed_empty_string_returns_zero_vector(self, tmp_path: Path) -> None:
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        result = provider.embed_texts([""])
        assert result.vectors[0] == [0.0] * 4
        assert result.token_counts[0] == 0

    def test_embed_empty_list_returns_empty(self, tmp_path: Path) -> None:
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        result = provider.embed_texts([])
        assert result.vectors == []
        assert result.token_counts == []

    def test_embed_deterministic_same_output(self, tmp_path: Path) -> None:
        """Same input text produces identical output across calls."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        r1 = provider.embed_texts(["hello world"])
        r2 = provider.embed_texts(["hello world"])
        assert r1.vectors == r2.vectors
        assert r1.token_counts == r2.token_counts

    def test_token_counts_match_encoding(self, tmp_path: Path) -> None:
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        text = "hello world"
        ids = provider._encode(text)
        result = provider.embed_texts([text])
        assert result.token_counts[0] == len(ids)

    def test_token_artifacts_contain_ids(self, tmp_path: Path) -> None:
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        result = provider.embed_texts(["hello"])
        assert "token_ids" in result.token_artifacts[0]
        assert isinstance(result.token_artifacts[0]["token_ids"], list)

    def test_vectors_are_plain_python_lists(self, tmp_path: Path) -> None:
        """No numpy types leak out of the provider."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        result = provider.embed_texts(["hello"])
        vec = result.vectors[0]
        assert isinstance(vec, list)
        assert all(isinstance(x, float) for x in vec)


# ===========================================================================
# TestReverseLookup
# ===========================================================================

class TestReverseLookup:
    """Reverse-lookup methods on DeterministicEmbedProvider."""

    def test_vocab_property_returns_copy(self, tmp_path: Path) -> None:
        """vocab property returns a copy, not the internal dict."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        v1 = provider.vocab
        v2 = provider.vocab
        assert v1 == v2
        assert v1 is not v2
        # Mutating the copy must not affect internal state
        v1["INJECTED"] = 999
        assert "INJECTED" not in provider.vocab

    def test_inverse_vocab_maps_correctly(self, tmp_path: Path) -> None:
        """inverse_vocab maps every ID back to its symbol."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        inv = provider.inverse_vocab
        vocab = provider.vocab
        for sym, idx in vocab.items():
            assert inv[idx] == sym

    def test_decode_token_ids_known(self, tmp_path: Path) -> None:
        """decode_token_ids maps known IDs back to symbols."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        decoded = provider.decode_token_ids([8, 9, 3, 4])
        assert decoded == ["he", "ll", "o", "</w>"]

    def test_decode_token_ids_unknown(self, tmp_path: Path) -> None:
        """decode_token_ids returns placeholder for unknown IDs."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        decoded = provider.decode_token_ids([-1, 999])
        assert decoded == ["<unk:-1>", "<unk:999>"]

    def test_nearest_tokens_returns_sorted(self, tmp_path: Path) -> None:
        """nearest_tokens returns results sorted by descending similarity."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        result = provider.embed_texts(["hello"])
        pooled = result.vectors[0]
        nearest = provider.nearest_tokens(pooled, k=5)
        assert len(nearest) == 5
        sims = [sim for _, sim, _ in nearest]
        assert sims == sorted(sims, reverse=True)

    def test_nearest_tokens_top_k(self, tmp_path: Path) -> None:
        """nearest_tokens respects k parameter."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        result = provider.embed_texts(["hello"])
        pooled = result.vectors[0]
        nearest_3 = provider.nearest_tokens(pooled, k=3)
        assert len(nearest_3) == 3
        # k > vocab_size should return vocab_size
        nearest_all = provider.nearest_tokens(pooled, k=100)
        assert len(nearest_all) == 11

    def test_nearest_tokens_returns_plain_python(self, tmp_path: Path) -> None:
        """nearest_tokens must not leak numpy types."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        result = provider.embed_texts(["hello"])
        pooled = result.vectors[0]
        nearest = provider.nearest_tokens(pooled, k=3)
        for symbol, sim, vec in nearest:
            assert isinstance(symbol, str)
            assert isinstance(sim, float)
            assert isinstance(vec, list)
            assert all(isinstance(v, float) for v in vec)

    def test_nearest_tokens_zero_vector(self, tmp_path: Path) -> None:
        """nearest_tokens returns empty list for zero vector."""
        tok_path, emb_path = _write_test_artifacts(tmp_path)
        provider = DeterministicEmbedProvider(tok_path, emb_path)
        nearest = provider.nearest_tokens([0.0, 0.0, 0.0, 0.0], k=5)
        assert nearest == []


# ===========================================================================
# TestModelBridgeConfigDeterministic
# ===========================================================================

class TestModelBridgeConfigDeterministic:
    """ModelBridgeConfig deterministic backend fields."""

    def test_default_embed_backend(self) -> None:
        cfg = ModelBridgeConfig()
        assert cfg.embed_backend == "deterministic"

    def test_default_paths_are_empty(self) -> None:
        cfg = ModelBridgeConfig()
        assert cfg.deterministic_tokenizer_path == ""
        assert cfg.deterministic_embeddings_path == ""

    def test_custom_paths_preserved(self) -> None:
        cfg = ModelBridgeConfig(
            deterministic_tokenizer_path="/some/tokenizer.json",
            deterministic_embeddings_path="/some/embeddings.npy",
        )
        assert cfg.deterministic_tokenizer_path == "/some/tokenizer.json"
        assert cfg.deterministic_embeddings_path == "/some/embeddings.npy"

    def test_original_fields_unchanged(self) -> None:
        """Adding deterministic fields does not change Phase 8 defaults."""
        cfg = ModelBridgeConfig()
        assert cfg.base_url == "http://localhost:11434"
        assert cfg.embed_model == "mxbai-embed-large"
        assert cfg.synthesis_model == ""
        assert cfg.timeout_seconds == 60.0
        assert cfg.context_window == 0
        assert cfg.embedding_dimensions == 0
        assert cfg.estimator == "split_heuristic"


# ===========================================================================
# TestBackendRouting
# ===========================================================================

class TestBackendRouting:
    """_resolve_embed_backend() routing logic."""

    def test_deterministic_when_all_conditions_met(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        assert bridge._resolve_embed_backend() == "deterministic"

    def test_ollama_when_paths_empty(self) -> None:
        """Default config: embed_backend=deterministic but paths empty -> ollama."""
        bridge = ModelBridge(config=ModelBridgeConfig())
        assert bridge._resolve_embed_backend() == "ollama"

    def test_ollama_when_files_missing(self) -> None:
        cfg = ModelBridgeConfig(
            embed_backend="deterministic",
            deterministic_tokenizer_path="/nonexistent/tokenizer.json",
            deterministic_embeddings_path="/nonexistent/embeddings.npy",
        )
        bridge = ModelBridge(config=cfg)
        assert bridge._resolve_embed_backend() == "ollama"

    def test_ollama_when_backend_explicit(self) -> None:
        bridge = _make_bridge_ollama()
        assert bridge._resolve_embed_backend() == "ollama"

    def test_ollama_when_only_one_path_set(self, tmp_path: Path) -> None:
        tok_path = str(tmp_path / "tokenizer.json")
        with open(tok_path, "w", encoding="utf-8") as f:
            json.dump(_make_tokenizer_spec(), f)

        cfg = ModelBridgeConfig(
            embed_backend="deterministic",
            deterministic_tokenizer_path=tok_path,
            deterministic_embeddings_path="",  # missing
        )
        bridge = ModelBridge(config=cfg)
        assert bridge._resolve_embed_backend() == "ollama"


# ===========================================================================
# TestEmbedDeterministicPath
# ===========================================================================

class TestEmbedDeterministicPath:
    """ModelBridge.embed() with deterministic backend."""

    def test_returns_valid_embed_response(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello world"])
        response = bridge.embed(request)
        assert isinstance(response, EmbedResponse)

    def test_vectors_have_correct_dimensions(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello"])
        response = bridge.embed(request)
        assert len(response.vectors) == 1
        assert len(response.vectors[0]) == 4
        assert response.dimensions == 4

    def test_l2_normalization_applied(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello world"], normalize=True)
        response = bridge.embed(request)
        vec = response.vectors[0]
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-6
        assert response.normalized is True

    def test_normalization_skipped_when_false(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello"], normalize=False)
        response = bridge.embed(request)
        assert response.normalized is False
        # Vector should NOT be unit norm (unless it happens to be)
        vec = response.vectors[0]
        norm = math.sqrt(sum(x * x for x in vec))
        # Verify it's the raw mean-pooled vector (may or may not be unit)
        assert len(vec) == 4

    def test_model_is_deterministic_bpe_svd(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello"])
        response = bridge.embed(request)
        assert response.model == "deterministic-bpe-svd"

    def test_token_counts_populated(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello world"])
        response = bridge.embed(request)
        assert len(response.token_counts) == 1
        assert response.token_counts[0] > 0

    def test_token_artifacts_in_properties(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello"])
        response = bridge.embed(request)
        assert "token_artifacts" in response.properties
        assert len(response.properties["token_artifacts"]) == 1

    def test_empty_texts_returns_empty(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=[])
        response = bridge.embed(request)
        assert response.vectors == []
        assert response.dimensions == 0
        assert response.model == "deterministic-bpe-svd"

    def test_metric_type_flows_through(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(
            texts=["hello"],
            metric_type=EmbeddingMetricType.INNER_PRODUCT,
        )
        response = bridge.embed(request)
        assert response.metric_type == EmbeddingMetricType.INNER_PRODUCT

    def test_multiple_texts_returns_multiple_vectors(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello", "world"])
        response = bridge.embed(request)
        assert len(response.vectors) == 2
        assert len(response.token_counts) == 2

    def test_no_http_call_made(self, tmp_path: Path) -> None:
        """Deterministic path should never call _http_post."""
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello"])
        with patch.object(bridge, "_http_post") as mock_post:
            bridge.embed(request)
        mock_post.assert_not_called()


# ===========================================================================
# TestEmbedOllamaPath
# ===========================================================================

class TestEmbedOllamaPath:
    """ModelBridge.embed() with Ollama backend — unchanged behavior."""

    def test_ollama_backend_calls_http(self) -> None:
        bridge = _make_bridge_ollama()
        request = EmbedRequest(texts=["hello"])
        mock_resp = _mock_embed_response(vectors=[[0.1, 0.2, 0.3]])

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            response = bridge.embed(request)

        mock_post.assert_called_once()
        assert mock_post.call_args[0][0] == "/api/embed"
        assert len(response.vectors) == 1

    def test_ollama_response_shape(self) -> None:
        bridge = _make_bridge_ollama()
        request = EmbedRequest(texts=["hello", "world"])
        mock_resp = _mock_embed_response(vectors=[[0.1, 0.2], [0.3, 0.4]])

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            response = bridge.embed(request)

        assert isinstance(response, EmbedResponse)
        assert len(response.vectors) == 2
        assert response.dimensions == 2


# ===========================================================================
# TestFallbackChain
# ===========================================================================

class TestFallbackChain:
    """Degradation: deterministic -> Ollama -> error."""

    def test_deterministic_failure_falls_back_to_ollama(self, tmp_path: Path) -> None:
        """If deterministic provider raises, fallback to Ollama."""
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello"])
        mock_resp = _mock_embed_response(vectors=[[0.5, 0.6, 0.7]])

        # Force deterministic to fail by corrupting the provider
        with patch.object(
            bridge, "_embed_deterministic",
            side_effect=RuntimeError("Corrupted artifacts"),
        ):
            with patch.object(bridge, "_http_post", return_value=mock_resp):
                response = bridge.embed(request)

        # Should succeed via Ollama fallback
        assert len(response.vectors) == 1
        assert response.model == "mxbai-embed-large"

    def test_both_fail_propagates_error(self, tmp_path: Path) -> None:
        """If deterministic fails AND Ollama fails, error propagates."""
        bridge = _make_bridge_deterministic(tmp_path)
        request = EmbedRequest(texts=["hello"])

        with patch.object(
            bridge, "_embed_deterministic",
            side_effect=RuntimeError("Corrupted"),
        ):
            with patch.object(
                bridge, "_http_post",
                side_effect=ModelConnectionError("Connection refused"),
            ):
                with pytest.raises(ModelConnectionError):
                    bridge.embed(request)

    def test_ollama_only_when_artifacts_missing(self) -> None:
        """When deterministic paths are empty, only Ollama is attempted."""
        bridge = ModelBridge(config=ModelBridgeConfig())
        request = EmbedRequest(texts=["hello"], normalize=False)
        mock_resp = _mock_embed_response(vectors=[[0.1]])

        with patch.object(bridge, "_http_post", return_value=mock_resp) as mock_post:
            response = bridge.embed(request)

        mock_post.assert_called_once()
        assert response.vectors == [[0.1]]


# ===========================================================================
# TestLazyImport
# ===========================================================================

class TestLazyImport:
    """numpy import isolation."""

    def test_model_bridge_module_importable_without_numpy_in_path(self) -> None:
        """Importing model_bridge.py does not force numpy at module level.

        We verify by checking that model_bridge.model_bridge module
        can be imported. numpy is only needed when the deterministic
        provider is actually instantiated.
        """
        # This test validates the design constraint. If model_bridge.py
        # had a top-level `import numpy`, it would fail in environments
        # without numpy. Since we're here and it imported, we just
        # confirm the module doesn't declare numpy as a module attribute.
        import src.core.model_bridge.model_bridge as mb_mod
        module_source = mb_mod.__file__
        assert module_source is not None
        # Verify no 'import numpy' at module level in the source
        with open(module_source, "r", encoding="utf-8") as f:
            source = f.read()
        # Should not have a bare 'import numpy' outside of functions
        lines = source.split("\n")
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("import numpy") or stripped.startswith("from numpy"):
                # Check if it's inside a function (indented)
                assert line[0] == " " or line[0] == "\t", (
                    f"Module-level numpy import found at line {i + 1}: {line}"
                )


# ===========================================================================
# TestModelIdentityEmbedBackend
# ===========================================================================

class TestModelIdentityEmbedBackend:
    """get_model_identity() includes embed_backend in properties."""

    def test_identity_includes_embed_backend(self, tmp_path: Path) -> None:
        bridge = _make_bridge_deterministic(tmp_path, synthesis_model="llama3")
        identity = bridge.get_model_identity()
        assert identity.properties["embed_backend"] == "deterministic"

    def test_identity_ollama_backend(self) -> None:
        bridge = _make_bridge_ollama(synthesis_model="llama3")
        identity = bridge.get_model_identity()
        assert identity.properties["embed_backend"] == "ollama"


# ===========================================================================
# TestEndToEnd
# ===========================================================================

class TestEndToEnd:
    """Full integration: deterministic embed -> embed_fn -> QueryProjection."""

    def test_deterministic_embed_to_query_projection(self, tmp_path: Path) -> None:
        """Deterministic embed wired through embed_fn produces query_embedding."""
        from src.core.projection.query_projection import QueryProjection

        bridge = _make_bridge_deterministic(tmp_path)

        def embed_fn(text: str):
            request = EmbedRequest(texts=[text], normalize=True)
            response = bridge.embed(request)
            return response.vectors[0]

        qp = QueryProjection()
        result = qp.project(
            None,
            {"raw_query": "hello world"},
            embed_fn=embed_fn,
        )
        artifact = result.projected_data["query_artifact"]
        assert "query_embedding" in artifact.properties
        vec = artifact.properties["query_embedding"]
        assert len(vec) == 4
        # Verify it's normalized (unit vector)
        norm = math.sqrt(sum(x * x for x in vec))
        assert abs(norm - 1.0) < 1e-6

    def test_ollama_embed_to_query_projection(self) -> None:
        """Ollama embed wired through embed_fn produces same shape."""
        from src.core.projection.query_projection import QueryProjection

        bridge = _make_bridge_ollama()

        def embed_fn(text: str):
            request = EmbedRequest(texts=[text], normalize=True)
            response = bridge.embed(request)
            return response.vectors[0]

        mock_resp = _mock_embed_response(vectors=[[0.6, 0.8]])
        qp = QueryProjection()

        with patch.object(bridge, "_http_post", return_value=mock_resp):
            result = qp.project(
                None,
                {"raw_query": "hello world"},
                embed_fn=embed_fn,
            )

        artifact = result.projected_data["query_artifact"]
        assert "query_embedding" in artifact.properties
        vec = artifact.properties["query_embedding"]
        assert len(vec) == 2

    def test_deterministic_embed_is_reproducible_e2e(self, tmp_path: Path) -> None:
        """Same query through same artifacts produces identical embedding."""
        bridge = _make_bridge_deterministic(tmp_path)

        def embed_fn(text: str):
            request = EmbedRequest(texts=[text], normalize=True)
            return bridge.embed(request).vectors[0]

        from src.core.projection.query_projection import QueryProjection
        qp = QueryProjection()

        r1 = qp.project(None, {"raw_query": "hello world"}, embed_fn=embed_fn)
        r2 = qp.project(None, {"raw_query": "hello world"}, embed_fn=embed_fn)

        v1 = r1.projected_data["query_artifact"].properties["query_embedding"]
        v2 = r2.projected_data["query_artifact"].properties["query_embedding"]
        assert v1 == v2

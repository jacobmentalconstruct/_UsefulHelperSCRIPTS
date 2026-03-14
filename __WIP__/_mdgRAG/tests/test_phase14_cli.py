"""
Phase 14 — CLI Query Path Tests

Tests the CLI entry point (src/app.py) including argument parsing,
ingest command, query command, output formatting, error handling,
and full end-to-end workflows.

Test structure:
    TestBuildParser      — argparse structure and defaults
    TestCmdIngest        — ingest subcommand execution
    TestCmdQuery         — query subcommand execution
    TestOutputFormatting — plain, JSON, and verbose output
    TestErrorHandling    — error formatting
    TestEndToEnd         — full ingest-then-query workflows
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from unittest.mock import patch, MagicMock

import pytest

from src.app import (
    build_parser,
    cmd_ingest,
    cmd_query,
    format_result_plain,
    format_result_json,
    format_verbose,
    handle_error,
    _sanitize_manifold_id,
    _load_all_node_ids,
    _build_embed_fn,
    _build_model_bridge_config,
    main,
)
from src.core.runtime.runtime_controller import (
    PipelineConfig,
    PipelineResult,
    PipelineError,
)
from src.core.factory.manifold_factory import ManifoldFactory
from src.core.store.manifold_store import ManifoldStore
from src.core.model_bridge.model_bridge import (
    ModelBridge,
    ModelBridgeConfig,
    ModelConnectionError,
    ModelResponseError,
)
from src.core.ingestion import (
    IngestionConfig,
    IngestionResult,
    ingest_file,
    ingest_directory,
)
from src.core.types.enums import ManifoldRole
from src.core.types.ids import ManifoldId, NodeId


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def factory() -> ManifoldFactory:
    return ManifoldFactory()


@pytest.fixture
def store() -> ManifoldStore:
    return ManifoldStore()


def _mock_embed_fn(text: str) -> Sequence[float]:
    """Mock embedding function returning a fixed-size vector."""
    return [0.1, 0.2, 0.3, 0.4, 0.5]


def _make_test_project(tmp_path: Path) -> Path:
    """Create a small test project with Python and Markdown files."""
    proj = tmp_path / "test_project"
    proj.mkdir()
    (proj / "main.py").write_text(
        'def greet(name):\n    """Say hello."""\n    return f"Hello {name}"\n\n\n'
        'def add(a, b):\n    """Add two numbers."""\n    return a + b\n',
        encoding="utf-8",
    )
    (proj / "README.md").write_text(
        "# Test Project\n\nA simple test project for CLI testing.\n\n"
        "## Features\n\n- Greeting function\n- Addition function\n\n"
        "## Usage\n\nRun `python main.py` to start.\n",
        encoding="utf-8",
    )
    sub = proj / "utils"
    sub.mkdir()
    (sub / "__init__.py").write_text("", encoding="utf-8")
    (sub / "helpers.py").write_text(
        'def sanitize(text):\n    """Clean up text."""\n    return text.strip()\n\n\n'
        'def uppercase(text):\n    """Convert to uppercase."""\n    return text.upper()\n',
        encoding="utf-8",
    )
    return proj


def _make_ingested_db(
    tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore,
) -> Path:
    """Create and return path to a pre-ingested manifold DB."""
    proj = _make_test_project(tmp_path)
    db_path = tmp_path / "test.db"
    manifold = factory.create_disk_manifold(
        ManifoldId("test-ext"), ManifoldRole.EXTERNAL, str(db_path),
        description="Test manifold",
    )
    ingest_directory(proj, manifold, store, embed_fn=_mock_embed_fn)
    return db_path


def _make_args(**kwargs) -> argparse.Namespace:
    """Build an argparse.Namespace with defaults for testing."""
    defaults = {
        "command": "query",
        "db": "test.db",
        "query": "test query",
        "alpha": 0.6,
        "beta": 0.4,
        "skip_synthesis": True,
        "synthesis_model": "",
        "ollama_url": "http://localhost:11434",
        "embed_backend": "deterministic",
        "tokenizer_path": "",
        "embeddings_path": "",
        "json_output": False,
        "verbose": False,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# TestBuildParser
# ---------------------------------------------------------------------------

class TestBuildParser:
    """Test argparse structure and defaults."""

    def test_parser_has_ingest_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["ingest", "--source", "/tmp/src", "--db", "/tmp/db"])
        assert args.command == "ingest"
        assert hasattr(args, "func")

    def test_parser_has_query_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["query", "--db", "/tmp/db", "--query", "test"])
        assert args.command == "query"
        assert hasattr(args, "func")

    def test_ingest_requires_source_and_db(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["ingest"])

    def test_query_requires_db_and_query(self):
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["query"])

    def test_query_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["query", "--db", "x.db", "--query", "q"])
        assert args.alpha == 0.6
        assert args.beta == 0.4
        assert args.skip_synthesis is True
        assert args.synthesis_model == ""
        assert args.embed_backend == "deterministic"

    def test_ingest_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["ingest", "--source", "/tmp", "--db", "x.db"])
        assert args.embed_backend == "deterministic"
        assert args.skip_embeddings is False
        assert args.max_chunk_tokens == 512

    def test_no_subcommand_prints_help(self):
        """main() returns 1 when no subcommand given."""
        with patch("sys.argv", ["prog"]):
            ret = main()
        assert ret == 1


# ---------------------------------------------------------------------------
# TestHelpers
# ---------------------------------------------------------------------------

class TestHelpers:
    """Test helper functions."""

    def test_sanitize_manifold_id_directory(self, tmp_path):
        d = tmp_path / "MyProject"
        d.mkdir()
        assert _sanitize_manifold_id(d) == "myproject"

    def test_sanitize_manifold_id_file(self, tmp_path):
        f = tmp_path / "data.txt"
        f.touch()
        assert _sanitize_manifold_id(f) == "data"

    def test_sanitize_manifold_id_special_chars(self, tmp_path):
        d = tmp_path / "My--Cool_Project!"
        d.mkdir()
        result = _sanitize_manifold_id(d)
        assert "--" not in result
        assert result.islower() or result.replace("-", "").isalnum()

    def test_build_model_bridge_config(self):
        args = _make_args(
            embed_backend="ollama",
            tokenizer_path="/tok.json",
            embeddings_path="/emb.npy",
            ollama_url="http://custom:1234",
        )
        config = _build_model_bridge_config(args)
        assert config.embed_backend == "ollama"
        assert config.deterministic_tokenizer_path == "/tok.json"
        assert config.deterministic_embeddings_path == "/emb.npy"
        assert config.base_url == "http://custom:1234"

    def test_load_all_node_ids(self, tmp_path, factory, store):
        db_path = _make_ingested_db(tmp_path, factory, store)
        manifold = factory.open_manifold(str(db_path))
        node_ids = _load_all_node_ids(manifold, store)
        assert len(node_ids) > 0
        assert all(isinstance(nid, str) for nid in node_ids)


# ---------------------------------------------------------------------------
# TestCmdIngest
# ---------------------------------------------------------------------------

class TestCmdIngest:
    """Test the ingest subcommand."""

    def test_ingest_directory_creates_db(self, tmp_path):
        proj = _make_test_project(tmp_path)
        db_path = tmp_path / "output.db"
        args = _make_args(
            command="ingest",
            source=str(proj),
            db=str(db_path),
            manifold_id=None,
            embed_backend="deterministic",
            tokenizer_path="",
            embeddings_path="",
            skip_embeddings=True,
            max_chunk_tokens=512,
            ollama_url="http://localhost:11434",
        )
        ret = cmd_ingest(args)
        assert ret == 0
        assert db_path.exists()

    def test_ingest_single_file(self, tmp_path):
        proj = _make_test_project(tmp_path)
        db_path = tmp_path / "single.db"
        args = _make_args(
            command="ingest",
            source=str(proj / "main.py"),
            db=str(db_path),
            manifold_id=None,
            embed_backend="deterministic",
            tokenizer_path="",
            embeddings_path="",
            skip_embeddings=True,
            max_chunk_tokens=512,
            ollama_url="http://localhost:11434",
        )
        ret = cmd_ingest(args)
        assert ret == 0
        assert db_path.exists()

    def test_ingest_nonexistent_source_error(self, tmp_path):
        args = _make_args(
            command="ingest",
            source=str(tmp_path / "does_not_exist"),
            db=str(tmp_path / "out.db"),
            manifold_id=None,
            embed_backend="deterministic",
            tokenizer_path="",
            embeddings_path="",
            skip_embeddings=True,
            max_chunk_tokens=512,
            ollama_url="http://localhost:11434",
        )
        ret = cmd_ingest(args)
        assert ret == 1

    def test_ingest_custom_manifold_id(self, tmp_path):
        proj = _make_test_project(tmp_path)
        db_path = tmp_path / "custom.db"
        args = _make_args(
            command="ingest",
            source=str(proj),
            db=str(db_path),
            manifold_id="my-custom-id",
            embed_backend="deterministic",
            tokenizer_path="",
            embeddings_path="",
            skip_embeddings=True,
            max_chunk_tokens=512,
            ollama_url="http://localhost:11434",
        )
        ret = cmd_ingest(args)
        assert ret == 0

        # Verify the manifold ID was used
        f = ManifoldFactory()
        m = f.open_manifold(str(db_path))
        assert str(m.get_metadata().manifold_id) == "my-custom-id"

    def test_ingest_skip_embeddings(self, tmp_path, factory, store):
        proj = _make_test_project(tmp_path)
        db_path = tmp_path / "noembed.db"
        args = _make_args(
            command="ingest",
            source=str(proj),
            db=str(db_path),
            manifold_id=None,
            embed_backend="deterministic",
            tokenizer_path="",
            embeddings_path="",
            skip_embeddings=True,
            max_chunk_tokens=512,
            ollama_url="http://localhost:11434",
        )
        ret = cmd_ingest(args)
        assert ret == 0

        # Verify no embeddings in the DB
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        conn.close()
        assert count == 0

    def test_ingest_returns_zero_on_success(self, tmp_path):
        proj = _make_test_project(tmp_path)
        db_path = tmp_path / "ok.db"
        args = _make_args(
            command="ingest",
            source=str(proj),
            db=str(db_path),
            manifold_id=None,
            embed_backend="deterministic",
            tokenizer_path="",
            embeddings_path="",
            skip_embeddings=True,
            max_chunk_tokens=512,
            ollama_url="http://localhost:11434",
        )
        assert cmd_ingest(args) == 0

    def test_ingest_has_nodes_and_edges(self, tmp_path, factory, store):
        """Verify ingested data produces nodes and edges in the DB."""
        proj = _make_test_project(tmp_path)
        db_path = tmp_path / "full.db"
        args = _make_args(
            command="ingest",
            source=str(proj),
            db=str(db_path),
            manifold_id="test-ext",
            embed_backend="deterministic",
            tokenizer_path="",
            embeddings_path="",
            skip_embeddings=True,
            max_chunk_tokens=512,
            ollama_url="http://localhost:11434",
        )
        cmd_ingest(args)

        manifold = factory.open_manifold(str(db_path))
        mid = manifold.get_metadata().manifold_id
        nodes = store.list_nodes(manifold.connection, mid)
        edges = store.list_edges(manifold.connection, mid)
        assert len(nodes) > 0, "Ingestion should produce nodes"
        assert len(edges) > 0, "Ingestion should produce edges"


# ---------------------------------------------------------------------------
# TestCmdQuery
# ---------------------------------------------------------------------------

class TestCmdQuery:
    """Test the query subcommand."""

    def test_query_skip_synthesis_returns_zero(self, tmp_path, factory, store):
        db_path = _make_ingested_db(tmp_path, factory, store)
        args = _make_args(db=str(db_path), query="How does greeting work?")
        ret = cmd_query(args)
        assert ret == 0

    def test_query_nonexistent_db_error(self, tmp_path):
        args = _make_args(db=str(tmp_path / "missing.db"), query="test")
        ret = cmd_query(args)
        assert ret == 1

    def test_query_empty_query_error(self, tmp_path, factory, store):
        db_path = _make_ingested_db(tmp_path, factory, store)
        args = _make_args(db=str(db_path), query="   ")
        ret = cmd_query(args)
        assert ret == 1

    def test_query_custom_alpha_beta(self, tmp_path, factory, store):
        """Verify custom alpha/beta are passed through to config."""
        db_path = _make_ingested_db(tmp_path, factory, store)
        args = _make_args(db=str(db_path), query="test", alpha=0.9, beta=0.1)
        # Should succeed with different weights
        ret = cmd_query(args)
        assert ret == 0

    def test_query_loads_all_node_ids(self, tmp_path, factory, store):
        """Verify query loads nodes from the manifold."""
        db_path = _make_ingested_db(tmp_path, factory, store)
        manifold = factory.open_manifold(str(db_path))
        node_ids = _load_all_node_ids(manifold, store)
        # The test project has multiple files, each producing nodes
        assert len(node_ids) >= 3  # At least SOURCE nodes for each file

    def test_query_json_output(self, tmp_path, factory, store, capsys):
        db_path = _make_ingested_db(tmp_path, factory, store)
        args = _make_args(
            db=str(db_path), query="What functions exist?",
            json_output=True,
        )
        ret = cmd_query(args)
        assert ret == 0
        captured = capsys.readouterr()
        # JSON should parse without error
        data = json.loads(captured.out)
        assert "timing" in data
        assert "artifacts" in data

    def test_query_verbose_output(self, tmp_path, factory, store, capsys):
        db_path = _make_ingested_db(tmp_path, factory, store)
        args = _make_args(
            db=str(db_path), query="What functions exist?",
            verbose=True,
        )
        ret = cmd_query(args)
        assert ret == 0
        captured = capsys.readouterr()
        # Verbose output goes to stderr
        assert "Pipeline Summary" in captured.err
        assert "Timing" in captured.err or "timing" in captured.err.lower()


# ---------------------------------------------------------------------------
# TestOutputFormatting
# ---------------------------------------------------------------------------

class TestOutputFormatting:
    """Test output formatting functions."""

    def _make_result(self, **kwargs) -> PipelineResult:
        """Build a PipelineResult with test data."""
        defaults = dict(
            answer_text="This is the answer.",
            structural_scores={NodeId("n1"): 0.8, NodeId("n2"): 0.3},
            semantic_scores={NodeId("n1"): 0.6, NodeId("n2"): 0.4},
            gravity_scores={NodeId("n1"): 0.72, NodeId("n2"): 0.34},
            degraded=False,
            skipped_stages=[],
            timing={"projection": 0.01, "fusion": 0.02, "scoring": 0.03, "total": 0.06},
            stage_count=4,
        )
        defaults.update(kwargs)
        return PipelineResult(**defaults)

    def test_format_plain_with_answer(self):
        result = self._make_result(answer_text="The answer is 42.")
        text = format_result_plain(result, skip_synthesis=False)
        assert "The answer is 42." in text

    def test_format_plain_skip_synthesis(self):
        result = self._make_result()
        text = format_result_plain(result, skip_synthesis=True)
        assert "synthesis skipped" in text
        assert "gravity" in text.lower()

    def test_format_json_structure(self):
        result = self._make_result()
        text = format_result_json(result)
        data = json.loads(text)
        assert "timing" in data
        assert "artifacts" in data
        assert "scoring_summary" in data
        assert "answer_text" in data

    def test_format_json_valid(self):
        result = self._make_result()
        text = format_result_json(result)
        # Should not raise
        data = json.loads(text)
        assert isinstance(data, dict)

    def test_format_verbose_includes_timing(self):
        result = self._make_result()
        text = format_verbose(result)
        assert "projection" in text
        assert "fusion" in text
        assert "scoring" in text

    def test_format_verbose_includes_scoring(self):
        result = self._make_result()
        text = format_verbose(result)
        assert "Structural nodes" in text
        assert "Gravity" in text


# ---------------------------------------------------------------------------
# TestErrorHandling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Test error formatting."""

    def test_pipeline_error_formatted(self, capsys):
        exc = PipelineError("scoring", "something broke")
        ret = handle_error(exc)
        assert ret == 1
        captured = capsys.readouterr()
        assert "scoring" in captured.err
        assert "something broke" in captured.err

    def test_connection_error_formatted(self, capsys):
        exc = ModelConnectionError("Connection refused")
        ret = handle_error(exc)
        assert ret == 1
        captured = capsys.readouterr()
        assert "model server" in captured.err.lower() or "connection" in captured.err.lower()

    def test_file_not_found_formatted(self, capsys):
        exc = FileNotFoundError("missing.db")
        ret = handle_error(exc)
        assert ret == 1
        captured = capsys.readouterr()
        assert "missing.db" in captured.err

    def test_generic_error_formatted(self, capsys):
        exc = RuntimeError("something unexpected")
        ret = handle_error(exc)
        assert ret == 1
        captured = capsys.readouterr()
        assert "something unexpected" in captured.err

    def test_verbose_shows_traceback(self, capsys):
        try:
            raise ValueError("traceback test")
        except ValueError as exc:
            handle_error(exc, verbose=True)
        captured = capsys.readouterr()
        assert "traceback test" in captured.err


# ---------------------------------------------------------------------------
# TestEndToEnd
# ---------------------------------------------------------------------------

class TestEndToEnd:
    """Full ingest-then-query workflows."""

    def test_ingest_then_query_e2e(self, tmp_path, factory, store, capsys):
        """Full end-to-end: ingest a project, then query it."""
        proj = _make_test_project(tmp_path)
        db_path = tmp_path / "e2e.db"

        # Ingest
        ingest_args = _make_args(
            command="ingest",
            source=str(proj),
            db=str(db_path),
            manifold_id="e2e-test",
            embed_backend="deterministic",
            tokenizer_path="",
            embeddings_path="",
            skip_embeddings=True,
            max_chunk_tokens=512,
            ollama_url="http://localhost:11434",
        )
        ret_ingest = cmd_ingest(ingest_args)
        assert ret_ingest == 0
        assert db_path.exists()

        # Verify data in DB
        manifold = factory.open_manifold(str(db_path))
        mid = manifold.get_metadata().manifold_id
        nodes = store.list_nodes(manifold.connection, mid)
        assert len(nodes) > 0, "Should have nodes after ingestion"

        # Query
        query_args = _make_args(
            db=str(db_path),
            query="What functions are defined in the project?",
        )
        ret_query = cmd_query(query_args)
        assert ret_query == 0

        # Check stdout has output
        captured = capsys.readouterr()
        assert len(captured.out) > 0, "Should produce output"

    def test_ingest_then_query_json(self, tmp_path, factory, store, capsys):
        """End-to-end with JSON output."""
        proj = _make_test_project(tmp_path)
        db_path = tmp_path / "e2e_json.db"

        # Ingest
        ingest_args = _make_args(
            command="ingest",
            source=str(proj),
            db=str(db_path),
            manifold_id="e2e-json",
            embed_backend="deterministic",
            tokenizer_path="",
            embeddings_path="",
            skip_embeddings=True,
            max_chunk_tokens=512,
            ollama_url="http://localhost:11434",
        )
        cmd_ingest(ingest_args)

        # Query with JSON output
        query_args = _make_args(
            db=str(db_path),
            query="How does greeting work?",
            json_output=True,
        )
        ret = cmd_query(query_args)
        assert ret == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "timing" in data
        assert "artifacts" in data
        assert "scoring_summary" in data
        # Should have produced artifacts
        assert data["stage_count"] > 0

    def test_ingest_then_query_verbose(self, tmp_path, factory, store, capsys):
        """End-to-end with verbose output."""
        proj = _make_test_project(tmp_path)
        db_path = tmp_path / "e2e_verbose.db"

        # Ingest
        ingest_args = _make_args(
            command="ingest",
            source=str(proj),
            db=str(db_path),
            manifold_id="e2e-verbose",
            embed_backend="deterministic",
            tokenizer_path="",
            embeddings_path="",
            skip_embeddings=True,
            max_chunk_tokens=512,
            ollama_url="http://localhost:11434",
        )
        cmd_ingest(ingest_args)

        # Query with verbose
        query_args = _make_args(
            db=str(db_path),
            query="What does sanitize do?",
            verbose=True,
        )
        ret = cmd_query(query_args)
        assert ret == 0

        captured = capsys.readouterr()
        assert "Pipeline Summary" in captured.err
        assert "Stages completed" in captured.err

    def test_ingest_with_embeddings_then_query(self, tmp_path, factory, store, capsys):
        """End-to-end with mock embeddings during ingestion."""
        proj = _make_test_project(tmp_path)
        db_path = tmp_path / "e2e_embed.db"

        # Ingest with embeddings (using direct API since CLI embed setup needs real artifacts)
        manifold = factory.create_disk_manifold(
            ManifoldId("e2e-embed"), ManifoldRole.EXTERNAL, str(db_path),
        )
        ingest_directory(proj, manifold, store, embed_fn=_mock_embed_fn)

        # Verify embeddings exist
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        embed_count = conn.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
        conn.close()
        assert embed_count > 0, "Should have embeddings"

        # Query
        query_args = _make_args(
            db=str(db_path),
            query="What functions exist?",
            json_output=True,
        )
        ret = cmd_query(query_args)
        assert ret == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["stage_count"] > 0

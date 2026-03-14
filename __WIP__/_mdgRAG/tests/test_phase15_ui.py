"""
Phase 15 — Web UI Tests

Tests for the FastAPI-based web UI layer, covering:
    - CLI parser (serve subcommand)
    - REST API endpoints (health, query, ingest, manifold info, graph)
    - Response format and structure
    - Graph serialization to Cytoscape.js format
    - Error handling
    - End-to-end (ingest → query via API)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Sequence

import pytest
from fastapi.testclient import TestClient

from src.app import build_parser, cmd_serve, _check_ui_deps
from src.ui.server import create_app, serialize_graph, _build_query_response
from src.core.factory.manifold_factory import ManifoldFactory
from src.core.store.manifold_store import ManifoldStore
from src.core.types.ids import ManifoldId, NodeId
from src.core.types.enums import ManifoldRole
from src.core.ingestion import (
    IngestionConfig,
    ingest_file,
    ingest_directory,
)


# ---------------------------------------------------------------------------
# Fixtures & helpers
# ---------------------------------------------------------------------------

def _make_test_project(tmp_path: Path) -> Path:
    """Create a small test project with Python and markdown files."""
    project = tmp_path / "test_project"
    project.mkdir()
    (project / "main.py").write_text(
        "def hello():\n    print('hello world')\n\nhello()\n"
    )
    (project / "README.md").write_text(
        "# Test Project\n\nA simple test project for ingestion.\n"
    )
    utils = project / "utils"
    utils.mkdir()
    (utils / "helpers.py").write_text(
        "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n"
    )
    return project


def _make_ingested_db(tmp_path: Path) -> Path:
    """Create and return path to a pre-ingested manifold DB."""
    project = _make_test_project(tmp_path)
    db_path = tmp_path / "test.db"

    factory = ManifoldFactory()
    store = ManifoldStore()
    mid = ManifoldId("test-project")
    manifold = factory.create_disk_manifold(
        mid, ManifoldRole.EXTERNAL, str(db_path),
        description="Test project",
    )
    config = IngestionConfig(enable_embeddings=False)
    ingest_directory(project, manifold, store, config=config)
    return db_path


def _get_test_client(default_db: str = None) -> TestClient:
    """Create a FastAPI TestClient for testing."""
    app = create_app(default_db=default_db)
    return TestClient(app)


# ===========================================================================
# TestServeParser
# ===========================================================================

class TestServeParser:
    """Tests for the 'serve' subcommand parser."""

    def test_parser_has_serve_subcommand(self) -> None:
        """build_parser() should include a 'serve' subcommand."""
        parser = build_parser()
        args = parser.parse_args(["serve"])
        assert args.command == "serve"

    def test_serve_default_port(self) -> None:
        """serve subcommand should default to port 8080."""
        parser = build_parser()
        args = parser.parse_args(["serve"])
        assert args.port == 8080

    def test_serve_default_host(self) -> None:
        """serve subcommand should default to localhost."""
        parser = build_parser()
        args = parser.parse_args(["serve"])
        assert args.host == "localhost"

    def test_serve_custom_port(self) -> None:
        """serve subcommand should accept custom port."""
        parser = build_parser()
        args = parser.parse_args(["serve", "--port", "9090"])
        assert args.port == 9090

    def test_serve_db_argument(self) -> None:
        """serve subcommand should accept optional --db."""
        parser = build_parser()
        args = parser.parse_args(["serve", "--db", "/tmp/test.db"])
        assert args.db == "/tmp/test.db"

    def test_check_ui_deps_returns_true(self) -> None:
        """_check_ui_deps should return True when fastapi/uvicorn are installed."""
        assert _check_ui_deps() is True


# ===========================================================================
# TestHealthEndpoint
# ===========================================================================

class TestHealthEndpoint:
    """Tests for the /api/health endpoint."""

    def test_health_returns_ok(self) -> None:
        """GET /api/health should return status ok."""
        client = _get_test_client()
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    def test_index_returns_html(self) -> None:
        """GET / should return HTML content."""
        client = _get_test_client()
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "Graph Manifold" in response.text


# ===========================================================================
# TestQueryEndpoint
# ===========================================================================

class TestQueryEndpoint:
    """Tests for the POST /api/query endpoint."""

    def test_query_missing_query_returns_400(self) -> None:
        """POST /api/query with no query should return 400."""
        client = _get_test_client()
        response = client.post("/api/query", json={"db_path": "/tmp/test.db"})
        assert response.status_code == 400
        assert "required" in response.json()["error"].lower()

    def test_query_missing_db_returns_400(self) -> None:
        """POST /api/query with no db_path should return 400."""
        client = _get_test_client()
        response = client.post("/api/query", json={"query": "test"})
        assert response.status_code == 400
        assert "required" in response.json()["error"].lower()

    def test_query_nonexistent_db_returns_404(self) -> None:
        """POST /api/query with nonexistent DB should return 404."""
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "test",
            "db_path": "/nonexistent/db.sqlite",
        })
        assert response.status_code == 404

    def test_query_empty_query_returns_400(self) -> None:
        """POST /api/query with empty query string should return 400."""
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "   ",
            "db_path": "/tmp/test.db",
        })
        assert response.status_code == 400

    def test_query_invalid_json_returns_400(self) -> None:
        """POST /api/query with invalid JSON should return 400."""
        client = _get_test_client()
        response = client.post(
            "/api/query",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400

    def test_query_with_valid_db_returns_200(self, tmp_path: Path) -> None:
        """POST /api/query with valid DB should return 200 with results."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "How does hello work?",
            "db_path": str(db_path),
            "skip_synthesis": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert "overview" in data
        assert "scores" in data
        assert "graph" in data

    def test_query_response_has_expected_keys(self, tmp_path: Path) -> None:
        """Query response should have all expected top-level keys."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "What functions exist?",
            "db_path": str(db_path),
        })
        data = response.json()
        expected_keys = {"answer_text", "overview", "timing", "total_time",
                         "evidence", "graph", "scores", "hydrated",
                         "degraded", "skipped_stages"}
        assert expected_keys.issubset(set(data.keys()))


# ===========================================================================
# TestIngestEndpoint
# ===========================================================================

class TestIngestEndpoint:
    """Tests for the POST /api/ingest endpoint."""

    def test_ingest_missing_source_returns_400(self) -> None:
        """POST /api/ingest with no source should return 400."""
        client = _get_test_client()
        response = client.post("/api/ingest", json={"db_path": "/tmp/test.db"})
        assert response.status_code == 400
        assert "required" in response.json()["error"].lower()

    def test_ingest_missing_db_returns_400(self) -> None:
        """POST /api/ingest with no db_path should return 400."""
        client = _get_test_client()
        response = client.post("/api/ingest", json={"source": "/tmp/src"})
        assert response.status_code == 400

    def test_ingest_nonexistent_source_returns_404(self) -> None:
        """POST /api/ingest with nonexistent source should return 404."""
        client = _get_test_client()
        response = client.post("/api/ingest", json={
            "source": "/nonexistent/project",
            "db_path": "/tmp/test.db",
        })
        assert response.status_code == 404

    def test_ingest_valid_source_returns_200(self, tmp_path: Path) -> None:
        """POST /api/ingest with valid source should return 200."""
        project = _make_test_project(tmp_path)
        db_path = tmp_path / "ingest_test.db"
        client = _get_test_client()
        response = client.post("/api/ingest", json={
            "source": str(project),
            "db_path": str(db_path),
            "skip_embeddings": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["files_processed"] > 0
        assert data["nodes_created"] > 0
        assert data["edges_created"] > 0

    def test_ingest_response_has_expected_keys(self, tmp_path: Path) -> None:
        """Ingest response should have all expected keys."""
        project = _make_test_project(tmp_path)
        db_path = tmp_path / "ingest_keys.db"
        client = _get_test_client()
        response = client.post("/api/ingest", json={
            "source": str(project),
            "db_path": str(db_path),
            "skip_embeddings": True,
        })
        data = response.json()
        expected_keys = {"status", "source", "db_path", "files_processed",
                         "files_skipped", "chunks_created", "nodes_created",
                         "edges_created", "embeddings_created", "warnings",
                         "elapsed_seconds"}
        assert expected_keys.issubset(set(data.keys()))


# ===========================================================================
# TestManifoldEndpoint
# ===========================================================================

class TestManifoldEndpoint:
    """Tests for the GET /api/manifold and /api/manifold/graph endpoints."""

    def test_manifold_info_missing_path_returns_400(self) -> None:
        """GET /api/manifold with no db_path should return 400."""
        client = _get_test_client()
        response = client.get("/api/manifold")
        assert response.status_code == 400

    def test_manifold_info_nonexistent_returns_404(self) -> None:
        """GET /api/manifold with nonexistent path should return 404."""
        client = _get_test_client()
        response = client.get("/api/manifold?db_path=/nonexistent/db.sqlite")
        assert response.status_code == 404

    def test_manifold_info_valid_returns_200(self, tmp_path: Path) -> None:
        """GET /api/manifold with valid path should return manifold info."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.get(f"/api/manifold?db_path={db_path}")
        assert response.status_code == 200
        data = response.json()
        assert "manifold_id" in data
        assert "node_count" in data
        assert "edge_count" in data
        assert data["node_count"] > 0

    def test_manifold_graph_returns_cytoscape_format(self, tmp_path: Path) -> None:
        """GET /api/manifold/graph should return nodes and edges arrays."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.get(f"/api/manifold/graph?db_path={db_path}")
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert isinstance(data["nodes"], list)
        assert isinstance(data["edges"], list)
        assert len(data["nodes"]) > 0

    def test_manifold_graph_node_format(self, tmp_path: Path) -> None:
        """Graph nodes should have Cytoscape.js data fields."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.get(f"/api/manifold/graph?db_path={db_path}")
        data = response.json()
        node = data["nodes"][0]
        assert "data" in node
        assert "id" in node["data"]
        assert "label" in node["data"]
        assert "type" in node["data"]


# ===========================================================================
# TestGraphSerialization
# ===========================================================================

class TestGraphSerialization:
    """Tests for serialize_graph() function."""

    def test_serialize_empty_manifold(self, tmp_path: Path) -> None:
        """serialize_graph with empty manifold produces empty arrays."""
        factory = ManifoldFactory()
        manifold = factory.create_memory_manifold(
            ManifoldId("empty"), ManifoldRole.EXTERNAL,
        )
        result = serialize_graph(manifold)
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_serialize_populated_manifold(self, tmp_path: Path) -> None:
        """serialize_graph with populated manifold returns nodes and edges."""
        db_path = _make_ingested_db(tmp_path)
        factory = ManifoldFactory()
        store = ManifoldStore()
        manifold = factory.open_manifold(str(db_path))
        result = serialize_graph(manifold, store=store)
        assert len(result["nodes"]) > 0
        assert len(result["edges"]) > 0

    def test_serialize_node_has_required_fields(self, tmp_path: Path) -> None:
        """Serialized nodes have id, label, type, gravity fields."""
        db_path = _make_ingested_db(tmp_path)
        factory = ManifoldFactory()
        store = ManifoldStore()
        manifold = factory.open_manifold(str(db_path))
        result = serialize_graph(manifold, store=store)
        node = result["nodes"][0]
        assert "id" in node["data"]
        assert "label" in node["data"]
        assert "type" in node["data"]
        assert "gravity" in node["data"]

    def test_serialize_edge_has_required_fields(self, tmp_path: Path) -> None:
        """Serialized edges have source, target, type, weight fields."""
        db_path = _make_ingested_db(tmp_path)
        factory = ManifoldFactory()
        store = ManifoldStore()
        manifold = factory.open_manifold(str(db_path))
        result = serialize_graph(manifold, store=store)
        edge = result["edges"][0]
        assert "source" in edge["data"]
        assert "target" in edge["data"]
        assert "type" in edge["data"]
        assert "weight" in edge["data"]

    def test_serialize_with_gravity_scores(self, tmp_path: Path) -> None:
        """serialize_graph should include gravity scores when provided."""
        db_path = _make_ingested_db(tmp_path)
        factory = ManifoldFactory()
        store = ManifoldStore()
        manifold = factory.open_manifold(str(db_path))
        # Load nodes via store since disk manifold has empty in-memory dict
        conn = manifold.connection
        mid = manifold.get_metadata().manifold_id
        node_list = store.list_nodes(conn, mid)
        assert len(node_list) > 0, "Ingested DB should have nodes"
        first_nid = node_list[0].node_id
        scores = {first_nid: 0.95}
        result = serialize_graph(manifold, gravity_scores=scores, store=store)
        # Find the node with the score
        scored_node = next(
            n for n in result["nodes"]
            if n["data"]["id"] == str(first_nid)
        )
        assert scored_node["data"]["gravity"] == 0.95


# ===========================================================================
# TestResponseFormat
# ===========================================================================

class TestResponseFormat:
    """Tests for query response structure and format."""

    def test_query_response_overview_has_stage_count(self, tmp_path: Path) -> None:
        """Pipeline overview should have stage_count field."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "test query",
            "db_path": str(db_path),
        })
        data = response.json()
        assert "stage_count" in data["overview"]

    def test_query_response_overview_has_timing(self, tmp_path: Path) -> None:
        """Pipeline overview should have timing dict."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "test query",
            "db_path": str(db_path),
        })
        data = response.json()
        assert "timing" in data["overview"]

    def test_query_response_evidence_has_node_count(self, tmp_path: Path) -> None:
        """Evidence section should have node_count when evidence exists."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "What does hello do?",
            "db_path": str(db_path),
        })
        data = response.json()
        if data["evidence"]:
            assert "node_count" in data["evidence"]

    def test_query_response_scores_is_list(self, tmp_path: Path) -> None:
        """Scores should be a list sorted by gravity."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "functions",
            "db_path": str(db_path),
        })
        data = response.json()
        assert isinstance(data["scores"], list)
        if len(data["scores"]) >= 2:
            # Should be sorted descending by gravity
            assert data["scores"][0]["gravity"] >= data["scores"][1]["gravity"]

    def test_query_response_graph_has_nodes_edges(self, tmp_path: Path) -> None:
        """Graph section should have nodes and edges arrays."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "test",
            "db_path": str(db_path),
        })
        data = response.json()
        assert "nodes" in data["graph"]
        assert "edges" in data["graph"]

    def test_query_response_has_total_time(self, tmp_path: Path) -> None:
        """Response should include total execution time."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "test",
            "db_path": str(db_path),
        })
        data = response.json()
        assert "total_time" in data
        assert isinstance(data["total_time"], (int, float))
        assert data["total_time"] > 0


# ===========================================================================
# TestErrorHandling
# ===========================================================================

class TestErrorHandling:
    """Tests for API error handling."""

    def test_query_pipeline_completes_without_synthesis(self, tmp_path: Path) -> None:
        """Query with skip_synthesis should complete without error."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "How does the project work?",
            "db_path": str(db_path),
            "skip_synthesis": True,
        })
        assert response.status_code == 200
        data = response.json()
        # Should not have answer text (synthesis skipped)
        assert data["answer_text"] == ""

    def test_manifold_info_default_db(self, tmp_path: Path) -> None:
        """Should use default_db when no db_path provided."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client(default_db=str(db_path))
        response = client.get("/api/manifold")
        assert response.status_code == 200
        data = response.json()
        assert data["node_count"] > 0

    def test_query_custom_alpha_beta(self, tmp_path: Path) -> None:
        """Custom alpha/beta values should be accepted."""
        db_path = _make_ingested_db(tmp_path)
        client = _get_test_client()
        response = client.post("/api/query", json={
            "query": "test",
            "db_path": str(db_path),
            "alpha": 0.8,
            "beta": 0.2,
        })
        assert response.status_code == 200


# ===========================================================================
# TestEndToEnd
# ===========================================================================

class TestEndToEnd:
    """End-to-end tests: ingest via API then query via API."""

    def test_ingest_then_query(self, tmp_path: Path) -> None:
        """Full flow: ingest via API, then query, verify results."""
        project = _make_test_project(tmp_path)
        db_path = tmp_path / "e2e.db"
        client = _get_test_client()

        # Ingest
        ingest_resp = client.post("/api/ingest", json={
            "source": str(project),
            "db_path": str(db_path),
            "skip_embeddings": True,
        })
        assert ingest_resp.status_code == 200
        assert ingest_resp.json()["nodes_created"] > 0

        # Query
        query_resp = client.post("/api/query", json={
            "query": "What does the hello function do?",
            "db_path": str(db_path),
        })
        assert query_resp.status_code == 200
        data = query_resp.json()
        assert len(data["scores"]) > 0
        assert data["graph"]["nodes"]

    def test_ingest_then_manifold_info(self, tmp_path: Path) -> None:
        """After ingesting, manifold info should show correct counts."""
        project = _make_test_project(tmp_path)
        db_path = tmp_path / "e2e_info.db"
        client = _get_test_client()

        # Ingest
        client.post("/api/ingest", json={
            "source": str(project),
            "db_path": str(db_path),
            "skip_embeddings": True,
        })

        # Check manifold info
        info_resp = client.get(f"/api/manifold?db_path={db_path}")
        assert info_resp.status_code == 200
        data = info_resp.json()
        assert data["node_count"] > 0
        assert data["edge_count"] > 0

    def test_ingest_then_graph(self, tmp_path: Path) -> None:
        """After ingesting, graph endpoint returns nodes from ingested files."""
        project = _make_test_project(tmp_path)
        db_path = tmp_path / "e2e_graph.db"
        client = _get_test_client()

        # Ingest
        client.post("/api/ingest", json={
            "source": str(project),
            "db_path": str(db_path),
            "skip_embeddings": True,
        })

        # Check graph
        graph_resp = client.get(f"/api/manifold/graph?db_path={db_path}")
        assert graph_resp.status_code == 200
        data = graph_resp.json()
        assert len(data["nodes"]) > 0
        # Should have source nodes for the ingested files
        node_labels = [n["data"]["label"] for n in data["nodes"]]
        assert any("main" in label.lower() for label in node_labels)


# ===========================================================================
# TestBrowseEndpoint
# ===========================================================================

class TestBrowseEndpoint:
    """Tests for the filesystem browse API used by the file picker."""

    def test_browse_cwd_returns_entries(self) -> None:
        """GET /api/browse with no path returns current directory listing."""
        client = _get_test_client()
        response = client.get("/api/browse")
        assert response.status_code == 200
        data = response.json()
        assert "current" in data
        assert "entries" in data
        assert isinstance(data["entries"], list)

    def test_browse_specific_path(self, tmp_path: Path) -> None:
        """GET /api/browse with valid path returns its contents."""
        (tmp_path / "fileA.txt").write_text("hello")
        sub = tmp_path / "subdir"
        sub.mkdir()

        client = _get_test_client()
        response = client.get(f"/api/browse?path={tmp_path}")
        assert response.status_code == 200
        data = response.json()
        assert data["current"] == str(tmp_path)
        names = [e["name"] for e in data["entries"]]
        assert "fileA.txt" in names
        assert "subdir" in names

    def test_browse_dirs_sorted_first(self, tmp_path: Path) -> None:
        """Directories should appear before files in the listing."""
        (tmp_path / "zz_file.txt").write_text("x")
        (tmp_path / "aa_dir").mkdir()

        client = _get_test_client()
        response = client.get(f"/api/browse?path={tmp_path}")
        data = response.json()
        # First entry should be the directory
        assert data["entries"][0]["is_dir"] is True
        assert data["entries"][0]["name"] == "aa_dir"

    def test_browse_nonexistent_returns_404(self) -> None:
        """GET /api/browse with nonexistent path returns 404."""
        client = _get_test_client()
        response = client.get("/api/browse?path=/no/such/path/ever")
        assert response.status_code == 404

    def test_browse_has_parent(self, tmp_path: Path) -> None:
        """Response should include parent directory path."""
        client = _get_test_client()
        response = client.get(f"/api/browse?path={tmp_path}")
        data = response.json()
        assert data["parent"] == str(tmp_path.parent)

    def test_browse_show_files_false(self, tmp_path: Path) -> None:
        """show_files=false should omit files from listing."""
        (tmp_path / "visible_dir").mkdir()
        (tmp_path / "hidden_file.txt").write_text("x")

        client = _get_test_client()
        response = client.get(f"/api/browse?path={tmp_path}&show_files=false")
        data = response.json()
        names = [e["name"] for e in data["entries"]]
        assert "visible_dir" in names
        assert "hidden_file.txt" not in names

    def test_browse_hidden_files_excluded(self, tmp_path: Path) -> None:
        """Dot-prefixed items and __pycache__ should be excluded."""
        (tmp_path / ".hidden").write_text("x")
        (tmp_path / "__pycache__").mkdir()
        (tmp_path / "normal.txt").write_text("x")

        client = _get_test_client()
        response = client.get(f"/api/browse?path={tmp_path}")
        data = response.json()
        names = [e["name"] for e in data["entries"]]
        assert ".hidden" not in names
        assert "__pycache__" not in names
        assert "normal.txt" in names

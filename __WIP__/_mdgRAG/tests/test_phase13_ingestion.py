"""
Phase 13 Tests — Ingestion Pipeline.

Tests for:
    - IngestionConfig defaults and overrides
    - Source file detection and directory walking
    - Prose chunking (heading split, paragraph split, sliding window, summary)
    - Tree-sitter chunker routing and fallback
    - Graph object construction (nodes, edges, chunks, hierarchy, bindings, provenance)
    - ingest_file() full pipeline
    - ingest_directory() with directory/project nodes
    - Idempotency (content-addressed dedup)
    - Embedding integration

All tree-sitter tests mock the tree-sitter library.
All embedding tests mock the embed function.
Tests use tmp_path fixture for real file I/O and SQLite-backed manifolds.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import List, Sequence
from unittest.mock import patch

import pytest

from src.core.ingestion.config import (
    CODE_EXTENSIONS,
    DEFAULT_MAX_CHUNK_TOKENS,
    DEFAULT_OVERLAP_LINES,
    EXT_TO_LANGUAGE,
    IngestionConfig,
    LANGUAGE_TIERS,
    PROSE_EXTENSIONS,
    SKIP_DIRS,
    SKIP_EXTENSIONS,
    get_language_tier,
)
from src.core.ingestion.detection import (
    SourceFile,
    detect_file,
    estimate_tokens,
    walk_sources,
)
from src.core.ingestion.chunking import (
    RawChunk,
    chunk_prose,
)
from src.core.ingestion.graph_builder import (
    IngestionArtifacts,
    build_graph_objects,
)
from src.core.ingestion.ingest import (
    IngestionResult,
    ingest_directory,
    ingest_file,
)
from src.core.factory.manifold_factory import ManifoldFactory
from src.core.store.manifold_store import ManifoldStore
from src.core.types.enums import EdgeType, ManifoldRole, NodeType
from src.core.types.ids import ManifoldId


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def factory() -> ManifoldFactory:
    return ManifoldFactory()


@pytest.fixture
def store() -> ManifoldStore:
    return ManifoldStore()


def _make_manifold(factory: ManifoldFactory, manifold_id: str = "test-ext-1"):
    """Create an in-memory EXTERNAL manifold for testing."""
    return factory.create_memory_manifold(
        ManifoldId(manifold_id), ManifoldRole.EXTERNAL
    )


def _write_test_file(tmp_path: Path, name: str, content: str) -> Path:
    """Write a test file and return its path."""
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


def _mock_embed_fn(text: str) -> Sequence[float]:
    """Mock embedding function that returns a fixed-size vector."""
    return [0.1, 0.2, 0.3, 0.4, 0.5]


# ══════════════════════════════════════════════════════════════════════════════
# Config Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestIngestionConfig:
    """Tests for IngestionConfig defaults and overrides."""

    def test_default_values(self) -> None:
        config = IngestionConfig()
        assert config.max_chunk_tokens == DEFAULT_MAX_CHUNK_TOKENS
        assert config.overlap_lines == DEFAULT_OVERLAP_LINES
        assert config.enable_embeddings is True
        assert config.enable_summary_chunks is True

    def test_custom_values(self) -> None:
        config = IngestionConfig(max_chunk_tokens=256, overlap_lines=5)
        assert config.max_chunk_tokens == 256
        assert config.overlap_lines == 5

    def test_skip_dirs_populated(self) -> None:
        config = IngestionConfig()
        assert ".git" in config.skip_dirs
        assert "__pycache__" in config.skip_dirs
        assert "node_modules" in config.skip_dirs

    def test_skip_extensions_populated(self) -> None:
        config = IngestionConfig()
        assert ".pyc" in config.skip_extensions
        assert ".jpg" in config.skip_extensions
        assert ".pdf" in config.skip_extensions


class TestLanguageTiers:
    """Tests for language tier classification."""

    def test_python_is_deep_semantic(self) -> None:
        tier = get_language_tier("python")
        assert tier["tier"] == "deep_semantic"
        assert tier["chunk_strategy"] == "hierarchical"

    def test_bash_is_shallow_semantic(self) -> None:
        tier = get_language_tier("bash")
        assert tier["tier"] == "shallow_semantic"

    def test_json_is_structural(self) -> None:
        tier = get_language_tier("json")
        assert tier["tier"] == "structural"

    def test_html_is_hybrid(self) -> None:
        tier = get_language_tier("html")
        assert tier["tier"] == "hybrid"

    def test_unknown_defaults_to_shallow(self) -> None:
        tier = get_language_tier("brainfuck")
        assert tier["tier"] == "shallow_semantic"

    def test_ext_to_language_coverage(self) -> None:
        assert EXT_TO_LANGUAGE[".py"] == "python"
        assert EXT_TO_LANGUAGE[".js"] == "javascript"
        assert EXT_TO_LANGUAGE[".md"] == "markdown"
        assert EXT_TO_LANGUAGE[".json"] == "json"


# ══════════════════════════════════════════════════════════════════════════════
# Detection Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestDetection:
    """Tests for source file detection."""

    def test_detect_python_file(self, tmp_path: Path) -> None:
        p = _write_test_file(tmp_path, "hello.py", "def hello():\n    pass\n")
        sf = detect_file(p)
        assert sf is not None
        assert sf.source_type == "code"
        assert sf.language == "python"
        assert sf.encoding == "utf-8"
        assert len(sf.lines) == 2

    def test_detect_markdown_file(self, tmp_path: Path) -> None:
        p = _write_test_file(tmp_path, "readme.md", "# Hello\nWorld\n")
        sf = detect_file(p)
        assert sf is not None
        assert sf.source_type == "prose"
        assert sf.language == "markdown"

    def test_detect_plain_text(self, tmp_path: Path) -> None:
        p = _write_test_file(tmp_path, "notes.txt", "Some notes here.\n")
        sf = detect_file(p)
        assert sf is not None
        assert sf.source_type == "prose"
        assert sf.language == "text"

    def test_detect_json_file(self, tmp_path: Path) -> None:
        p = _write_test_file(tmp_path, "config.json", '{"key": "value"}\n')
        sf = detect_file(p)
        assert sf is not None
        assert sf.source_type == "structured"
        assert sf.language == "json"

    def test_detect_empty_file_returns_none(self, tmp_path: Path) -> None:
        p = _write_test_file(tmp_path, "empty.txt", "")
        sf = detect_file(p)
        assert sf is None

    def test_detect_nonexistent_returns_none(self, tmp_path: Path) -> None:
        sf = detect_file(tmp_path / "nonexistent.py")
        assert sf is None

    def test_file_hash_is_deterministic(self, tmp_path: Path) -> None:
        p = _write_test_file(tmp_path, "test.py", "x = 1\n")
        sf1 = detect_file(p)
        sf2 = detect_file(p)
        assert sf1 is not None and sf2 is not None
        assert sf1.file_hash == sf2.file_hash

    def test_bom_stripped(self, tmp_path: Path) -> None:
        p = tmp_path / "bom.txt"
        p.write_bytes(b"\xef\xbb\xbfHello BOM\n")
        sf = detect_file(p)
        assert sf is not None
        assert not sf.text.startswith("\ufeff")


class TestWalkSources:
    """Tests for directory walking."""

    def test_walk_single_file(self, tmp_path: Path) -> None:
        p = _write_test_file(tmp_path, "main.py", "x = 1\n")
        sources = list(walk_sources(p))
        assert len(sources) == 1
        assert sources[0].language == "python"

    def test_walk_directory(self, tmp_path: Path) -> None:
        _write_test_file(tmp_path, "a.py", "a = 1\n")
        _write_test_file(tmp_path, "b.md", "# B\n")
        sources = list(walk_sources(tmp_path))
        assert len(sources) == 2

    def test_skip_hidden_dirs(self, tmp_path: Path) -> None:
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        _write_test_file(hidden, "secret.py", "s = 1\n")
        _write_test_file(tmp_path, "visible.py", "v = 1\n")
        sources = list(walk_sources(tmp_path))
        assert len(sources) == 1
        assert sources[0].path.name == "visible.py"

    def test_skip_git_dir(self, tmp_path: Path) -> None:
        git_dir = tmp_path / ".git"
        git_dir.mkdir()
        _write_test_file(git_dir, "HEAD", "ref: refs/heads/main\n")
        _write_test_file(tmp_path, "main.py", "x = 1\n")
        sources = list(walk_sources(tmp_path))
        assert len(sources) == 1

    def test_skip_binary_extensions(self, tmp_path: Path) -> None:
        _write_test_file(tmp_path, "data.pyc", "binary stuff\n")
        _write_test_file(tmp_path, "code.py", "x = 1\n")
        sources = list(walk_sources(tmp_path))
        assert len(sources) == 1
        assert sources[0].path.name == "code.py"


class TestEstimateTokens:
    """Tests for token estimation."""

    def test_estimate_nonempty(self) -> None:
        assert estimate_tokens("hello world") > 0

    def test_estimate_empty(self) -> None:
        # int(0 * 1.3 + 1) = 1
        assert estimate_tokens("") == 1

    def test_estimate_matches_chunk_heuristic(self) -> None:
        text = "the quick brown fox jumps over the lazy dog"
        expected = int(len(text.split()) * 1.3 + 1)
        assert estimate_tokens(text) == expected


# ══════════════════════════════════════════════════════════════════════════════
# Prose Chunking Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestProseChunking:
    """Tests for prose chunker."""

    def _make_source(self, tmp_path: Path, name: str, content: str) -> SourceFile:
        p = _write_test_file(tmp_path, name, content)
        sf = detect_file(p)
        assert sf is not None
        return sf

    def test_markdown_heading_split(self, tmp_path: Path) -> None:
        content = "# Section A\nParagraph A.\n\n# Section B\nParagraph B.\n"
        source = self._make_source(tmp_path, "doc.md", content)
        chunks = chunk_prose(source)
        # Should have: summary + 2 sections
        assert len(chunks) >= 2
        chunk_names = [c.name for c in chunks]
        assert any("Section A" in n for n in chunk_names)
        assert any("Section B" in n for n in chunk_names)

    def test_plain_text_paragraph_split(self, tmp_path: Path) -> None:
        content = "First paragraph.\n\n\nSecond paragraph.\n"
        source = self._make_source(tmp_path, "notes.txt", content)
        chunks = chunk_prose(source)
        assert len(chunks) >= 2

    def test_summary_chunk_generated(self, tmp_path: Path) -> None:
        content = "# Title\nSome content here.\n"
        source = self._make_source(tmp_path, "doc.md", content)
        config = IngestionConfig(enable_summary_chunks=True)
        chunks = chunk_prose(source, config)
        summary = [c for c in chunks if c.chunk_type == "document_summary"]
        assert len(summary) == 1

    def test_summary_disabled(self, tmp_path: Path) -> None:
        content = "# Title\nSome content here.\n"
        source = self._make_source(tmp_path, "doc.md", content)
        config = IngestionConfig(enable_summary_chunks=False)
        chunks = chunk_prose(source, config)
        summary = [c for c in chunks if c.chunk_type == "document_summary"]
        assert len(summary) == 0

    def test_large_section_uses_sliding_window(self, tmp_path: Path) -> None:
        # Create a section that exceeds token budget
        lines = [f"Line {i} with some text content." for i in range(200)]
        content = "# Big Section\n" + "\n".join(lines)
        source = self._make_source(tmp_path, "big.md", content)
        config = IngestionConfig(max_chunk_tokens=50)
        chunks = chunk_prose(source, config)
        # Should produce multiple chunks from sliding window
        assert len(chunks) > 2

    def test_empty_file_fallback(self, tmp_path: Path) -> None:
        content = "   \n  \n"
        p = _write_test_file(tmp_path, "empty.md", content)
        sf = detect_file(p)
        # Very sparse file may be detected as None or produce fallback
        if sf is not None:
            chunks = chunk_prose(sf)
            assert len(chunks) >= 1

    def test_heading_path_populated(self, tmp_path: Path) -> None:
        content = "# Top\n## Sub\nContent.\n"
        source = self._make_source(tmp_path, "nested.md", content)
        chunks = chunk_prose(source)
        non_summary = [c for c in chunks if c.chunk_type != "document_summary"]
        for c in non_summary:
            assert len(c.heading_path) > 0

    def test_chunk_line_ranges_valid(self, tmp_path: Path) -> None:
        content = "# A\nLine 1\nLine 2\n# B\nLine 3\n"
        source = self._make_source(tmp_path, "ranges.md", content)
        chunks = chunk_prose(source)
        for c in chunks:
            assert c.line_start >= 0
            assert c.line_end >= c.line_start
            assert c.line_end < len(source.lines)


# ══════════════════════════════════════════════════════════════════════════════
# Tree-Sitter Chunker Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestTreeSitterChunker:
    """Tests for tree-sitter chunker routing and fallback."""

    def test_returns_none_when_unavailable(self, tmp_path: Path) -> None:
        from src.core.ingestion.tree_sitter_chunker import chunk_tree_sitter
        p = _write_test_file(tmp_path, "test.py", "x = 1\n")
        sf = detect_file(p)
        assert sf is not None

        with patch(
            "src.core.ingestion.tree_sitter_chunker._tree_sitter_available",
            return_value=False,
        ):
            result = chunk_tree_sitter(sf)
        assert result is None

    def test_returns_none_for_prose_language(self, tmp_path: Path) -> None:
        from src.core.ingestion.tree_sitter_chunker import chunk_tree_sitter
        p = _write_test_file(tmp_path, "doc.md", "# Hello\n")
        sf = detect_file(p)
        assert sf is not None
        # markdown has no tree-sitter query patterns, language is "markdown"
        # not in any tier so returns None (no parser)
        with patch(
            "src.core.ingestion.tree_sitter_chunker._tree_sitter_available",
            return_value=True,
        ), patch(
            "src.core.ingestion.tree_sitter_chunker._get_parser",
            return_value=None,
        ):
            result = chunk_tree_sitter(sf)
        assert result is None

    def test_none_language_returns_none(self, tmp_path: Path) -> None:
        from src.core.ingestion.tree_sitter_chunker import chunk_tree_sitter
        p = _write_test_file(tmp_path, "data.xyz", "stuff\n")
        sf = detect_file(p)
        if sf is not None:
            sf.language = None
            result = chunk_tree_sitter(sf)
            assert result is None

    def test_fallback_chunker_produces_chunks(self, tmp_path: Path) -> None:
        from src.core.ingestion.tree_sitter_chunker import _fallback_line_chunker
        p = _write_test_file(tmp_path, "code.py", "\n".join(
            [f"line_{i} = {i}" for i in range(50)]
        ))
        sf = detect_file(p)
        assert sf is not None
        chunks = _fallback_line_chunker(sf, max_tokens=30)
        assert len(chunks) > 1
        for c in chunks:
            assert c.chunk_type == "code_block"
            assert c.language_tier == "unknown"


# ══════════════════════════════════════════════════════════════════════════════
# Graph Builder Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestGraphBuilder:
    """Tests for graph object construction from chunks."""

    def _make_raw_chunks(self) -> List[RawChunk]:
        return [
            RawChunk(
                text="# Module docstring",
                chunk_type="document_summary",
                name="test.py (summary)",
                heading_path=["test.py", "(summary)"],
                line_start=0, line_end=0,
            ),
            RawChunk(
                text="import os\nimport sys",
                chunk_type="import_block",
                name="imports",
                heading_path=["test.py", "imports"],
                line_start=1, line_end=2,
                semantic_depth=1, structural_depth=1,
                language_tier="deep_semantic",
            ),
            RawChunk(
                text="def hello():\n    print('hello')",
                chunk_type="function_def",
                name="hello",
                heading_path=["test.py", "hello()"],
                line_start=4, line_end=5,
                semantic_depth=1, structural_depth=1,
                language_tier="deep_semantic",
            ),
        ]

    def _make_source(self, tmp_path: Path) -> SourceFile:
        content = "# Module docstring\nimport os\nimport sys\n\ndef hello():\n    print('hello')\n"
        p = _write_test_file(tmp_path, "test.py", content)
        sf = detect_file(p)
        assert sf is not None
        return sf

    def test_source_node_created(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        artifacts = build_graph_objects(chunks, source, "test-manifold")
        assert artifacts.source_node is not None
        assert artifacts.source_node.node_type == NodeType.SOURCE
        assert artifacts.source_node.label == "test.py"

    def test_chunk_nodes_created(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        artifacts = build_graph_objects(chunks, source, "test-manifold")
        assert len(artifacts.chunk_nodes) == 3

    def test_chunk_objects_content_addressed(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        artifacts = build_graph_objects(chunks, source, "test-manifold")
        for chunk in artifacts.chunks:
            assert chunk.chunk_hash != ""
            assert chunk.chunk_text != ""
            assert chunk.byte_length > 0

    def test_contains_edges_created(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        artifacts = build_graph_objects(chunks, source, "test-manifold")
        contains = [e for e in artifacts.edges if e.edge_type == EdgeType.CONTAINS]
        assert len(contains) >= 3  # At least one per chunk

    def test_next_edges_created(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        artifacts = build_graph_objects(chunks, source, "test-manifold")
        next_edges = [e for e in artifacts.edges if e.edge_type == EdgeType.NEXT]
        assert len(next_edges) == 2  # 3 chunks = 2 NEXT edges

    def test_hierarchy_entries_created(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        artifacts = build_graph_objects(chunks, source, "test-manifold")
        assert len(artifacts.hierarchy_entries) == 3

    def test_node_chunk_bindings_created(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        artifacts = build_graph_objects(chunks, source, "test-manifold")
        assert len(artifacts.node_chunk_bindings) == 3

    def test_provenance_records_created(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        artifacts = build_graph_objects(chunks, source, "test-manifold")
        assert len(artifacts.provenance) > 0
        for prov in artifacts.provenance:
            assert prov.stage.name == "INGESTION"

    def test_all_nodes_includes_source(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        artifacts = build_graph_objects(chunks, source, "test-manifold")
        all_nodes = artifacts.all_nodes
        node_types = [n.node_type for n in all_nodes]
        assert NodeType.SOURCE in node_types
        assert NodeType.CHUNK in node_types

    def test_chunk_occurrence_has_location(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        artifacts = build_graph_objects(chunks, source, "test-manifold")
        for occ in artifacts.chunk_occurrences:
            assert occ.source_path != ""
            assert occ.start_line >= 0

    def test_deterministic_ids(self, tmp_path: Path) -> None:
        source = self._make_source(tmp_path)
        chunks = self._make_raw_chunks()
        a1 = build_graph_objects(chunks, source, "test-manifold")
        a2 = build_graph_objects(chunks, source, "test-manifold")
        assert a1.source_node.node_id == a2.source_node.node_id
        for n1, n2 in zip(a1.chunk_nodes, a2.chunk_nodes):
            assert n1.node_id == n2.node_id


# ══════════════════════════════════════════════════════════════════════════════
# Full Pipeline Tests (ingest_file)
# ══════════════════════════════════════════════════════════════════════════════

class TestIngestFile:
    """Tests for ingest_file() full pipeline."""

    def test_ingest_markdown_file(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "doc.md", "# Hello\nWorld.\n\n# Second\nMore text.\n")

        result = ingest_file(p, manifold, store)

        assert result.files_processed == 1
        assert result.files_skipped == 0
        assert result.chunks_created > 0
        assert result.nodes_created > 0
        assert result.edges_created > 0

    def test_ingest_python_file(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        content = "def greet(name):\n    return f'Hello {name}'\n\ndef add(a, b):\n    return a + b\n"
        p = _write_test_file(tmp_path, "funcs.py", content)

        result = ingest_file(p, manifold, store)

        assert result.files_processed == 1
        assert result.chunks_created > 0
        assert result.nodes_created > 0

    def test_ingest_nonexistent_file(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        result = ingest_file(tmp_path / "nope.txt", manifold, store)
        assert result.files_skipped == 1
        assert result.files_processed == 0

    def test_ingest_with_embeddings(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "embed.md", "# Test\nContent to embed.\n")

        result = ingest_file(p, manifold, store, embed_fn=_mock_embed_fn)

        assert result.embeddings_created > 0

    def test_ingest_without_embeddings(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "no_embed.md", "# Test\nNo embeddings.\n")

        result = ingest_file(p, manifold, store)

        assert result.embeddings_created == 0

    def test_nodes_readable_from_store(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        mid = ManifoldId("test-ext-1")
        p = _write_test_file(tmp_path, "stored.md", "# Hello\nStored content.\n")

        ingest_file(p, manifold, store)

        conn = manifold.connection
        nodes = store.list_nodes(conn, mid)
        assert len(nodes) > 0
        node_types = {n.node_type for n in nodes}
        assert NodeType.SOURCE in node_types

    def test_chunks_readable_from_store(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "stored.md", "# Hello\nStored content.\n")

        ingest_file(p, manifold, store)

        # Read chunks via raw SQL (no list_chunks in ManifoldStore)
        conn = manifold.connection
        rows = conn.execute("SELECT chunk_hash, chunk_text FROM chunks").fetchall()
        assert len(rows) > 0
        for row in rows:
            assert row["chunk_text"] != ""

    def test_edges_readable_from_store(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        mid = ManifoldId("test-ext-1")
        p = _write_test_file(tmp_path, "stored.md", "# A\nPart A.\n# B\nPart B.\n")

        ingest_file(p, manifold, store)

        conn = manifold.connection
        edges = store.list_edges(conn, mid)
        assert len(edges) > 0
        edge_types = {e.edge_type for e in edges}
        assert EdgeType.CONTAINS in edge_types

    def test_timing_recorded(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "timed.md", "Content.\n")

        result = ingest_file(p, manifold, store)

        assert result.timing_seconds > 0


# ══════════════════════════════════════════════════════════════════════════════
# Directory Ingestion Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestIngestDirectory:
    """Tests for ingest_directory() with directory/project nodes."""

    def test_ingest_flat_directory(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        mid = ManifoldId("test-ext-1")
        _write_test_file(tmp_path, "a.py", "a = 1\n")
        _write_test_file(tmp_path, "b.md", "# B\nContent.\n")

        result = ingest_directory(tmp_path, manifold, store)

        assert result.files_processed == 2
        assert result.nodes_created > 0

        # Verify PROJECT node exists
        conn = manifold.connection
        nodes = store.list_nodes(conn, mid)
        project_nodes = [n for n in nodes if n.node_type == NodeType.PROJECT]
        assert len(project_nodes) == 1

    def test_ingest_nested_directory(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        mid = ManifoldId("test-ext-1")
        sub = tmp_path / "src"
        sub.mkdir()
        _write_test_file(sub, "main.py", "x = 1\n")
        _write_test_file(tmp_path, "readme.md", "# Readme\n")

        result = ingest_directory(tmp_path, manifold, store)

        assert result.files_processed == 2

        # Verify DIRECTORY nodes exist
        conn = manifold.connection
        nodes = store.list_nodes(conn, mid)
        dir_nodes = [n for n in nodes if n.node_type == NodeType.DIRECTORY]
        assert len(dir_nodes) >= 1

    def test_skip_hidden_subdirs(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        _write_test_file(hidden, "secret.py", "s = 1\n")
        _write_test_file(tmp_path, "visible.py", "v = 1\n")

        result = ingest_directory(tmp_path, manifold, store)

        assert result.files_processed == 1

    def test_not_a_directory(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "file.txt", "content\n")

        result = ingest_directory(p, manifold, store)

        assert result.files_processed == 0
        assert len(result.warnings) > 0

    def test_contains_edges_for_directory_tree(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        mid = ManifoldId("test-ext-1")
        sub = tmp_path / "pkg"
        sub.mkdir()
        _write_test_file(sub, "mod.py", "y = 2\n")

        ingest_directory(tmp_path, manifold, store)

        conn = manifold.connection
        edges = store.list_edges(conn, mid)
        contains = [e for e in edges if e.edge_type == EdgeType.CONTAINS]
        # PROJECT → DIRECTORY, DIRECTORY → SOURCE, SOURCE → CHUNK...
        assert len(contains) >= 2


# ══════════════════════════════════════════════════════════════════════════════
# Idempotency Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestIdempotency:
    """Tests for content-addressed dedup on re-ingestion."""

    def test_same_file_twice_no_crash(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "repeat.md", "# Hello\nSame content.\n")

        r1 = ingest_file(p, manifold, store)
        r2 = ingest_file(p, manifold, store)

        assert r1.files_processed == 1
        assert r2.files_processed == 1
        # Both should succeed without errors

    def test_content_addressed_chunks_dedup(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        # Two files with identical chunk text
        _write_test_file(tmp_path, "a.txt", "Same content.\n")
        _write_test_file(tmp_path, "b.txt", "Same content.\n")

        ingest_file(tmp_path / "a.txt", manifold, store)
        ingest_file(tmp_path / "b.txt", manifold, store)

        # Chunks should be deduplicated (same content → same hash)
        conn = manifold.connection
        rows = conn.execute("SELECT chunk_text FROM chunks").fetchall()
        chunk_texts = [r["chunk_text"] for r in rows]
        # The chunk "Same content." should appear only once
        assert chunk_texts.count("Same content.") == 1


# ══════════════════════════════════════════════════════════════════════════════
# Embedding Integration Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestEmbeddingIntegration:
    """Tests for embedding generation during ingestion."""

    def test_embed_fn_called_per_chunk(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "embed.md", "# A\nChunk A.\n# B\nChunk B.\n")
        call_count = 0

        def counting_embed(text: str) -> Sequence[float]:
            nonlocal call_count
            call_count += 1
            return [0.1] * 5

        result = ingest_file(p, manifold, store, embed_fn=counting_embed)

        assert call_count > 0
        assert result.embeddings_created == call_count

    def test_embed_failure_graceful(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "fail.md", "# Test\nContent.\n")

        def failing_embed(text: str) -> Sequence[float]:
            raise RuntimeError("Embed failed")

        result = ingest_file(p, manifold, store, embed_fn=failing_embed)

        # Should not crash — graceful degradation
        assert result.files_processed == 1
        assert result.embeddings_created == 0

    def test_embeddings_in_store(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "stored_embed.md", "# Test\nContent.\n")

        ingest_file(p, manifold, store, embed_fn=_mock_embed_fn)

        # Read embeddings via raw SQL (no list_embeddings in ManifoldStore)
        conn = manifold.connection
        rows = conn.execute("SELECT embedding_id FROM embeddings").fetchall()
        assert len(rows) > 0

    def test_embeddings_disabled_via_config(self, tmp_path: Path, factory: ManifoldFactory, store: ManifoldStore) -> None:
        manifold = _make_manifold(factory)
        p = _write_test_file(tmp_path, "no_embed.md", "# Test\nContent.\n")
        config = IngestionConfig(enable_embeddings=False)

        result = ingest_file(p, manifold, store, config=config, embed_fn=_mock_embed_fn)

        assert result.embeddings_created == 0


# ══════════════════════════════════════════════════════════════════════════════
# Result Merge Tests
# ══════════════════════════════════════════════════════════════════════════════

class TestIngestionResult:
    """Tests for IngestionResult."""

    def test_merge(self) -> None:
        r1 = IngestionResult(files_processed=1, chunks_created=5, nodes_created=3)
        r2 = IngestionResult(files_processed=2, chunks_created=10, nodes_created=7)
        r1.merge(r2)
        assert r1.files_processed == 3
        assert r1.chunks_created == 15
        assert r1.nodes_created == 10

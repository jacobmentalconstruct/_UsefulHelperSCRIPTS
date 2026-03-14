"""
Ingestion configuration — tuneable constants, file type mappings, and language tiers.

Extracted from: TripartiteDataSTORE/src/config.py :: extension sets, skip lists
Extracted from: TripartiteDataSTORE/src/chunkers/treesitter.py :: LANGUAGE_TIERS
Rewritten for Graph Manifold ingestion pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Set


# ── Chunking budgets ──────────────────────────────────────────────────────────

DEFAULT_MAX_CHUNK_TOKENS: int = 512
DEFAULT_OVERLAP_LINES: int = 3
DEFAULT_SUMMARY_CHUNK_TOKENS: int = 256


# ── Extension → language mapping ──────────────────────────────────────────────

EXT_TO_LANGUAGE: Dict[str, str] = {
    # Code — deep semantic
    ".py": "python", ".js": "javascript", ".jsx": "javascript",
    ".ts": "typescript", ".tsx": "typescript", ".java": "java",
    ".go": "go", ".rs": "rust", ".c": "c", ".cpp": "cpp",
    ".cxx": "cpp", ".cc": "cpp", ".h": "c", ".hpp": "cpp",
    ".hxx": "cpp", ".cs": "c_sharp", ".kt": "kotlin", ".kts": "kotlin",
    ".scala": "scala", ".swift": "swift",
    # Code — shallow semantic
    ".rb": "ruby", ".php": "php", ".r": "r", ".R": "r",
    ".sh": "bash", ".bash": "bash", ".zsh": "bash",
    # Markup / hybrid
    ".html": "html", ".htm": "html", ".css": "css", ".xml": "xml",
    # Structured data
    ".json": "json", ".yaml": "yaml", ".yml": "yaml", ".toml": "toml",
    # Prose
    ".md": "markdown", ".markdown": "markdown", ".rst": "rst",
    ".txt": "text", ".text": "text", ".adoc": "adoc", ".org": "org",
    ".tex": "tex",
}

# ── Source type sets ──────────────────────────────────────────────────────────

CODE_EXTENSIONS: Set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs",
    ".c", ".cpp", ".cxx", ".cc", ".h", ".hpp", ".hxx", ".cs",
    ".rb", ".php", ".swift", ".kt", ".kts", ".scala", ".r", ".R",
    ".sh", ".bash", ".zsh",
}

PROSE_EXTENSIONS: Set[str] = {
    ".md", ".markdown", ".txt", ".text", ".rst", ".adoc", ".org", ".tex",
}

STRUCTURED_EXTENSIONS: Set[str] = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".tsv",
}

MARKUP_EXTENSIONS: Set[str] = {
    ".html", ".htm", ".css", ".xml",
}

SKIP_EXTENSIONS: Set[str] = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".bin", ".obj", ".o",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".zip", ".gz", ".tar", ".rar", ".7z", ".bz2", ".xz",
    ".mp3", ".mp4", ".mov", ".avi", ".mkv", ".wav", ".flac",
    ".woff", ".woff2", ".ttf", ".eot",
    ".db", ".sqlite", ".sqlite3",
    ".npy", ".npz", ".pkl", ".pickle",
    ".lock",
}

SKIP_DIRS: Set[str] = {
    ".git", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules", ".venv", "venv", "env", ".env",
    "dist", "build", ".tox", ".eggs", ".egg-info",
    ".idea", ".vscode", ".vs",
    "_logs", "_showcase",
}


# ── Language tier classification ──────────────────────────────────────────────
# Extracted from: TripartiteDataSTORE/src/chunkers/treesitter.py :: LANGUAGE_TIERS

LANGUAGE_TIERS: Dict[str, Dict] = {
    "deep_semantic": {
        "languages": [
            "python", "javascript", "typescript", "java", "go",
            "rust", "cpp", "c_sharp", "kotlin", "scala", "swift",
        ],
        "max_depth": 4,
        "chunk_strategy": "hierarchical",
        "meaningful_depth": True,
    },
    "shallow_semantic": {
        "languages": ["bash", "r", "ruby", "php", "c"],
        "max_depth": 2,
        "chunk_strategy": "flat",
        "meaningful_depth": True,
    },
    "structural": {
        "languages": ["json", "yaml", "toml"],
        "max_depth": None,
        "chunk_strategy": "structural",
        "meaningful_depth": False,
    },
    "hybrid": {
        "languages": ["html", "css", "xml"],
        "max_depth": 3,
        "chunk_strategy": "markup",
        "meaningful_depth": False,
    },
}


def get_language_tier(language: str) -> Dict:
    """
    Get the tier configuration for a language.

    Returns a dict with keys: tier, languages, max_depth, chunk_strategy,
    meaningful_depth.  Unknown languages default to shallow_semantic.
    """
    for tier_name, config in LANGUAGE_TIERS.items():
        if language in config["languages"]:
            return {**config, "tier": tier_name}
    return {
        "tier": "shallow_semantic",
        "languages": [],
        "max_depth": 2,
        "chunk_strategy": "flat",
        "meaningful_depth": True,
    }


# ── Ingestion config dataclass ────────────────────────────────────────────────

@dataclass
class IngestionConfig:
    """
    Configuration for the ingestion pipeline.

    Controls chunking budgets, file filtering, and embedding behavior.
    All fields have sensible defaults matching the TripartiteDataSTORE conventions.
    """
    # Chunking budgets
    max_chunk_tokens: int = DEFAULT_MAX_CHUNK_TOKENS
    overlap_lines: int = DEFAULT_OVERLAP_LINES
    summary_chunk_tokens: int = DEFAULT_SUMMARY_CHUNK_TOKENS

    # File filtering
    skip_dirs: Set[str] = field(default_factory=lambda: set(SKIP_DIRS))
    skip_extensions: Set[str] = field(default_factory=lambda: set(SKIP_EXTENSIONS))

    # Embedding behavior
    enable_embeddings: bool = True
    enable_summary_chunks: bool = True

    # Parser name for provenance records
    parser_name: str = "mdgRAG-ingestion"
    parser_version: str = "0.1.0"

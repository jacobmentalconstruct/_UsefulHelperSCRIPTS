"""
File detection and directory walking for the ingestion pipeline.

Identifies source type, language, and encoding for each candidate file.
Filters out binary files, hidden files, and skip-listed directories.

Extracted from: TripartiteDataSTORE/src/pipeline/detect.py :: SourceFile, detect, walk_source
Rewritten for Graph Manifold ingestion pipeline.
"""

from __future__ import annotations

import hashlib
import logging
import os
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, List, Optional

from .config import (
    CODE_EXTENSIONS,
    EXT_TO_LANGUAGE,
    MARKUP_EXTENSIONS,
    PROSE_EXTENSIONS,
    STRUCTURED_EXTENSIONS,
    IngestionConfig,
)

logger = logging.getLogger(__name__)


# ── Data types ────────────────────────────────────────────────────────────────

@dataclass
class SourceFile:
    """
    All information about a detected source file, ready for chunking.

    Fields:
        path: Resolved absolute path.
        file_hash: SHA256 hex digest of raw file bytes (for change detection).
        source_type: One of 'code', 'prose', 'structured', 'markup', 'generic'.
        language: Tree-sitter language name or None for unknown.
        encoding: Encoding used to decode the file.
        text: Full decoded text content (CRLF normalised to LF, BOM stripped).
        lines: text.splitlines() result — no trailing newlines per line.
        byte_size: Raw file size in bytes.
    """
    path: Path
    file_hash: str
    source_type: str
    language: Optional[str]
    encoding: str
    text: str
    lines: List[str]
    byte_size: int


# ── Token estimation ──────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """
    Estimate token count using the canonical split heuristic.

    Matches Chunk.__post_init__ in graph.py: int(len(text.split()) * 1.3 + 1).
    """
    return int(len(text.split()) * 1.3 + 1)


# ── Text normalisation ────────────────────────────────────────────────────────

def _normalise_text(text: str) -> str:
    """Strip BOM, NFC normalise, CRLF→LF."""
    if text.startswith("\ufeff"):
        text = text[1:]
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text


def _split_lines(text: str) -> List[str]:
    """Split text into lines without trailing newlines."""
    return text.splitlines()


# ── Hashing ───────────────────────────────────────────────────────────────────

def _file_hash(path: Path) -> str:
    """SHA256 hex digest of raw file bytes."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Detection helpers ─────────────────────────────────────────────────────────

def _detect_language(path: Path) -> Optional[str]:
    """Map file extension to tree-sitter language name."""
    return EXT_TO_LANGUAGE.get(path.suffix.lower())


def _detect_source_type(path: Path) -> str:
    """Classify file by extension into source type category."""
    ext = path.suffix.lower()
    if ext in CODE_EXTENSIONS:
        return "code"
    if ext in PROSE_EXTENSIONS:
        return "prose"
    if ext in STRUCTURED_EXTENSIONS:
        return "structured"
    if ext in MARKUP_EXTENSIONS:
        return "markup"
    return "generic"


def _is_text_file(path: Path, sample_size: int = 8192) -> bool:
    """
    Heuristic check: read the first sample_size bytes and reject if
    more than 10% are non-text (control chars excluding \\t\\n\\r).
    """
    try:
        with open(path, "rb") as f:
            sample = f.read(sample_size)
    except OSError:
        return False

    if not sample:
        return False

    # Count bytes that aren't printable ASCII, whitespace, or high UTF-8
    non_text = sum(
        1 for b in sample
        if b < 0x08 or (0x0E <= b <= 0x1F and b != 0x1B)  # allow ESC
    )
    return non_text / len(sample) < 0.10


def _should_skip_dir(name: str, config: IngestionConfig) -> bool:
    """Check if directory should be skipped during walk."""
    if name.startswith("."):
        return True
    return name in config.skip_dirs


def _should_skip_file(path: Path, config: IngestionConfig) -> bool:
    """Check if file should be skipped during walk."""
    if path.name.startswith("."):
        return True
    if path.suffix.lower() in config.skip_extensions:
        return True
    try:
        if path.stat().st_size == 0:
            return True
    except OSError:
        return True
    return False


# ── Public API ────────────────────────────────────────────────────────────────

def detect_file(path: Path) -> Optional[SourceFile]:
    """
    Detect and normalise a single file.

    Returns None if the file is binary, unreadable, empty, or otherwise
    unsuitable for ingestion.
    """
    path = Path(path)

    try:
        stat = path.stat()
    except OSError:
        return None

    if stat.st_size == 0:
        return None

    if not _is_text_file(path):
        return None

    # Try UTF-8 first, fall back to Latin-1
    encoding = "utf-8"
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            raw = path.read_text(encoding="latin-1")
            encoding = "latin-1"
        except (OSError, UnicodeDecodeError):
            return None
    except OSError:
        return None

    text = _normalise_text(raw)
    if not text.strip():
        return None

    lines = _split_lines(text)
    if not lines:
        return None

    return SourceFile(
        path=path.resolve(),
        file_hash=_file_hash(path),
        source_type=_detect_source_type(path),
        language=_detect_language(path),
        encoding=encoding,
        text=text,
        lines=lines,
        byte_size=stat.st_size,
    )


def walk_sources(
    root: Path,
    config: Optional[IngestionConfig] = None,
) -> Iterator[SourceFile]:
    """
    Recursively walk *root*, yielding SourceFile objects for eligible files.

    Skips hidden directories, skip-listed dirs, binary files, and empty files.
    If root is a single file, yields it if eligible.
    """
    if config is None:
        config = IngestionConfig()

    root = Path(root)

    if root.is_file():
        if not _should_skip_file(root, config) and _is_text_file(root):
            sf = detect_file(root)
            if sf is not None:
                yield sf
        return

    if not root.is_dir():
        logger.warning("walk_sources: %s is not a file or directory", root)
        return

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place so os.walk doesn't descend
        dirnames[:] = sorted(
            d for d in dirnames if not _should_skip_dir(d, config)
        )

        for fname in sorted(filenames):
            fpath = Path(dirpath) / fname
            try:
                if _should_skip_file(fpath, config):
                    continue
                if not _is_text_file(fpath):
                    continue
                sf = detect_file(fpath)
                if sf is not None:
                    yield sf
            except OSError:
                continue

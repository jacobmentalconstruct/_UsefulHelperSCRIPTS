"""
Prose chunker and shared chunking data types for the ingestion pipeline.

Two-pass strategy:
  Pass 1 — Split on structural signals (ATX headings for Markdown,
            blank-line paragraph breaks for plain text).
  Pass 2 — Apply a sliding token window within sections that exceed
            max_chunk_tokens, preserving overlap_lines of context.

A document-level summary chunk is always generated as the first item
(when enabled).

Extracted from: TripartiteDataSTORE/src/chunkers/prose.py
Rewritten for Graph Manifold ingestion pipeline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .config import (
    DEFAULT_MAX_CHUNK_TOKENS,
    DEFAULT_OVERLAP_LINES,
    DEFAULT_SUMMARY_CHUNK_TOKENS,
    IngestionConfig,
)
from .detection import SourceFile, estimate_tokens


# ── Raw chunk dataclass (internal pipeline type) ─────────────────────────────

@dataclass
class RawChunk:
    """
    Output of the chunking step — a logical text segment with metadata.

    This is an intermediate type consumed by graph_builder.py to produce
    graph-native Node/Chunk/Edge/Hierarchy objects.
    """
    text: str
    chunk_type: str              # function_def, class_def, section, paragraph, ...
    name: str                    # Human-readable label
    heading_path: List[str]      # Breadcrumb trail from file root
    line_start: int              # 0-indexed inclusive
    line_end: int                # 0-indexed inclusive
    semantic_depth: int = 0      # Meaningful code hierarchy depth
    structural_depth: int = 0    # Raw nesting depth
    language_tier: str = "prose" # deep_semantic, shallow_semantic, structural, hybrid, prose


# ── ATX heading pattern ──────────────────────────────────────────────────────

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")


# ── Heading / paragraph splitters ─────────────────────────────────────────────

def _split_on_headings(
    lines: List[str],
) -> List[tuple]:
    """
    Split lines on ATX headings.

    Returns list of (line_start, line_end, heading_path) tuples.
    heading_path is the breadcrumb from root to current heading.
    """
    sections: List[tuple] = []
    heading_stack: List[tuple] = []
    current_start: Optional[int] = None
    current_path: List[str] = []

    def flush(end: int) -> None:
        nonlocal current_start
        if current_start is not None and end >= current_start:
            sections.append((current_start, end, list(current_path)))

    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            flush(i - 1)
            heading_stack = [(lv, t) for lv, t in heading_stack if lv < level]
            heading_stack.append((level, text))
            current_path = [t for _, t in heading_stack]
            current_start = i

    flush(len(lines) - 1)

    # If no headings found, treat whole file as one section
    if not sections and lines:
        sections.append((0, len(lines) - 1, []))

    return sections


def _split_on_paragraphs(
    lines: List[str],
) -> List[tuple]:
    """
    Split plain text on blank-line paragraph boundaries.

    Returns (start, end, []) — no heading path for plain text.
    """
    sections: List[tuple] = []
    start: Optional[int] = None

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped:
            if start is None:
                start = i
        else:
            if start is not None:
                sections.append((start, i - 1, []))
                start = None

    if start is not None:
        sections.append((start, len(lines) - 1, []))

    return sections


# ── Sliding window ────────────────────────────────────────────────────────────

def _sliding_window(
    lines: List[str],
    lo: int,
    hi: int,
    heading_path: List[str],
    max_tokens: int,
    overlap: int,
) -> List[RawChunk]:
    """
    Break a large section into overlapping token-budget chunks.
    """
    chunks: List[RawChunk] = []
    cursor = lo
    window_idx = 0

    while cursor <= hi:
        end = cursor
        tokens = 0
        while end <= hi:
            tokens += estimate_tokens(lines[end])
            if tokens > max_tokens and end > cursor:
                break
            end += 1

        chunk_end = min(end - 1, hi)
        chunk_text = "\n".join(lines[cursor : chunk_end + 1])
        label = heading_path[-1] if heading_path else "section"

        chunks.append(RawChunk(
            text=chunk_text,
            chunk_type="paragraph",
            name=f"{label} (part {window_idx + 1})",
            heading_path=heading_path,
            line_start=cursor,
            line_end=chunk_end,
            language_tier="prose",
        ))

        next_cursor = chunk_end + 1 - overlap
        if next_cursor <= cursor:
            next_cursor = cursor + 1  # always make forward progress
        cursor = next_cursor
        window_idx += 1

    return chunks


# ── Summary chunk ─────────────────────────────────────────────────────────────

def _make_summary_chunk(
    source: SourceFile,
    file_name: str,
    target_tokens: int,
) -> Optional[RawChunk]:
    """
    Generate a document-level summary chunk from the first N tokens of the file.
    High-recall entry point for vector search.
    """
    lines = source.lines
    tokens = 0
    end = 0

    for i, line in enumerate(lines):
        tokens += estimate_tokens(line)
        if tokens > target_tokens:
            break
        end = i

    if not lines:
        return None

    chunk_text = "\n".join(lines[: end + 1])
    return RawChunk(
        text=chunk_text,
        chunk_type="document_summary",
        name=f"{file_name} (summary)",
        heading_path=[file_name, "(summary)"],
        line_start=0,
        line_end=end,
        language_tier="prose",
    )


# ── Heading depth → chunk type mapping ────────────────────────────────────────

def _heading_depth_to_type(depth: int) -> str:
    mapping = {0: "document", 1: "section", 2: "subsection", 3: "paragraph"}
    return mapping.get(depth, "paragraph")


# ── Public API ────────────────────────────────────────────────────────────────

def chunk_prose(
    source: SourceFile,
    config: Optional[IngestionConfig] = None,
) -> List[RawChunk]:
    """
    Chunk a prose file (Markdown or plain text) into RawChunk objects.

    Two-pass strategy:
      1. Split on structural signals (headings or paragraph breaks).
      2. Apply sliding window to oversized sections.
      3. Prepend a document summary chunk.
    """
    if config is None:
        config = IngestionConfig()

    lines = source.lines
    file_name = source.path.name
    max_tokens = config.max_chunk_tokens
    overlap = config.overlap_lines

    is_markdown = source.language in ("markdown",) or source.path.suffix.lower() in (
        ".md", ".markdown",
    )

    if is_markdown:
        sections = _split_on_headings(lines)
    else:
        sections = _split_on_paragraphs(lines)

    chunks: List[RawChunk] = []

    # Document summary chunk
    if config.enable_summary_chunks:
        summary = _make_summary_chunk(source, file_name, config.summary_chunk_tokens)
        if summary:
            chunks.append(summary)

    for lo, hi, heading_path in sections:
        section_text = "\n".join(lines[lo : hi + 1])
        token_count = estimate_tokens(section_text)
        full_path = [file_name] + heading_path

        if token_count <= max_tokens:
            chunk_type = _heading_depth_to_type(len(heading_path))
            chunks.append(RawChunk(
                text=section_text,
                chunk_type=chunk_type,
                name=heading_path[-1] if heading_path else file_name,
                heading_path=full_path,
                line_start=lo,
                line_end=hi,
                language_tier="prose",
            ))
        else:
            sub_chunks = _sliding_window(
                lines=lines, lo=lo, hi=hi,
                heading_path=full_path,
                max_tokens=max_tokens, overlap=overlap,
            )
            chunks.extend(sub_chunks)

    # Absolute fallback: whole file as one chunk
    if not chunks:
        chunks.append(RawChunk(
            text=source.text,
            chunk_type="document",
            name=file_name,
            heading_path=[file_name],
            line_start=0,
            line_end=max(0, len(lines) - 1),
            language_tier="prose",
        ))

    return chunks

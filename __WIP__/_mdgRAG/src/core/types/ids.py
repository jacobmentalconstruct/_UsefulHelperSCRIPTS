"""
Typed ID aliases — standardized identifiers for all graph elements.

Ownership: src/core/types/ids.py
    This file is the single source of truth for all typed identifiers
    in the manifold system. Every subsystem references these types.

Using NewType ensures type safety at the annotation level while keeping
runtime overhead at zero. All IDs are strings to maintain serialization
compatibility and human readability.

Also provides deterministic hashing helpers:
    - deterministic_hash(): general-purpose SHA256 for any canonical text
    - make_chunk_hash(): content-addressed chunk identity — SHA256(chunk_text)
    - make_legacy_chunk_hash(): location-based legacy convention (migration only)

Chunk identity model:
    Chunks are content-addressed. Two chunks with identical text produce the
    same ChunkHash regardless of where they appear. Location information
    (source_path, chunk_index, line numbers) belongs in ChunkOccurrence,
    which is a separate entity referencing the chunk by its content hash.

Legacy context:
    - Legacy used SHA256(source_path + ":" + chunk_index) for chunk IDs,
      conflating identity with location. The new model separates these.
    - NodeId/EdgeId map to NetworkX node/edge identifiers
    - EmbeddingId maps to FAISS id_map entries
"""

from __future__ import annotations

import hashlib
from typing import NewType


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HASH_TRUNCATION_LENGTH: int = 16
"""
Default hex-character truncation length for deterministic hash IDs.

16 hex chars = 64 bits of collision space.  Appropriate for per-session
working graphs and moderate-scale persistent collections.  For very
large persistent collections, consider increasing this value.
"""


# ---------------------------------------------------------------------------
# Graph-manifold entity IDs
# ---------------------------------------------------------------------------

ManifoldId = NewType("ManifoldId", str)
NodeId = NewType("NodeId", str)
EdgeId = NewType("EdgeId", str)
ChunkHash = NewType("ChunkHash", str)
EmbeddingId = NewType("EmbeddingId", str)
HierarchyId = NewType("HierarchyId", str)
EvidenceBagId = NewType("EvidenceBagId", str)

# ---------------------------------------------------------------------------
# Manifest and composition IDs
# ---------------------------------------------------------------------------

FileManifestHash = NewType("FileManifestHash", str)
ProjectRootHash = NewType("ProjectRootHash", str)


# ---------------------------------------------------------------------------
# Deterministic hashing helper
# ---------------------------------------------------------------------------

def deterministic_hash(canonical_text: str) -> str:
    """
    Produce a deterministic SHA256 hex digest from a canonical text payload.

    This is the system's standard way to derive content-addressed identifiers.
    The input is UTF-8 encoded before hashing.

    Args:
        canonical_text: The text to hash. Must be a stable, canonical
            representation — caller is responsible for normalisation.

    Returns:
        64-character lowercase hex string (SHA256 digest).
    """
    return hashlib.sha256(canonical_text.encode("utf-8")).hexdigest()


def make_chunk_hash(content: str) -> ChunkHash:
    """
    Create a content-addressed chunk hash from the chunk's text.

    Formula: SHA256(content)

    Chunks are identified by their content, not their location. Two chunks
    with the same text always produce the same ChunkHash. Location data
    (source path, chunk index, line numbers) belongs in ChunkOccurrence.

    Args:
        content: The chunk's full text content.

    Returns:
        ChunkHash wrapping the hex digest.
    """
    return ChunkHash(deterministic_hash(content))


def make_legacy_chunk_hash(source_path: str, chunk_index: int) -> ChunkHash:
    """
    Create a location-based chunk hash matching the legacy convention.

    Formula: SHA256(source_path + ":" + str(chunk_index))

    .. deprecated::
        Legacy used location-based chunk IDs. The canonical model is now
        content-addressed via make_chunk_hash(). This helper exists solely
        for migration compatibility with legacy DeterministicGraphRAG data.

    Args:
        source_path: Canonical path of the source file.
        chunk_index: Zero-based index of the chunk within the file.

    Returns:
        ChunkHash wrapping the hex digest.
    """
    return ChunkHash(deterministic_hash(f"{source_path}:{chunk_index}"))

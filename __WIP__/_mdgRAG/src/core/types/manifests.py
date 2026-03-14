"""
Manifest Types — deterministic composition descriptors.

Ownership: src/core/types/manifests.py
    Typed structures for file and project manifests. Manifests provide
    stable, content-addressed metadata enabling deterministic
    identification and reproducible composition of manifold content.

Legacy context:
    - FileManifest entries correspond to legacy cartridge VFS entries
    - ProjectManifest corresponds to legacy UNCF cartridge.json metadata
    - Content hashes use the same SHA256 convention as chunk hashing
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.types.ids import FileManifestHash, ProjectRootHash


# ---------------------------------------------------------------------------
# File-level manifests
# ---------------------------------------------------------------------------

@dataclass
class FileManifestEntry:
    """
    A single file's manifest entry within a project manifest.

    Captures the identity, content hash, and chunking metadata for
    one source file. Content-addressed via file_hash.
    """

    file_hash: FileManifestHash
    path: str
    content_hash: str = ""          # SHA256 of raw file content
    size_bytes: int = 0
    mime_type: str = ""
    encoding: str = "utf-8"
    chunk_count: int = 0
    line_count: int = 0
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FileManifest:
    """
    Collection of file manifest entries forming a corpus snapshot.

    A FileManifest captures the state of a set of files at a point
    in time. It is deterministic: the same files with the same content
    always produce the same manifest.
    """

    manifest_hash: FileManifestHash
    entries: List[FileManifestEntry] = field(default_factory=list)
    total_files: int = 0
    total_bytes: int = 0
    total_chunks: int = 0
    created_at: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Project-level manifests
# ---------------------------------------------------------------------------

@dataclass
class ProjectManifestEntry:
    """
    A single item within a project manifest (file, directory, or resource).

    Extends the file manifest concept with project-specific metadata
    like VFS path mapping and origin tracking.
    """

    entry_id: str
    vfs_path: str                   # Virtual filesystem path within project
    real_path: str = ""             # Actual filesystem path (if applicable)
    origin_type: str = ""           # "local_file", "url", "generated", etc.
    content_hash: str = ""
    file_manifest_hash: Optional[FileManifestHash] = None
    properties: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectManifest:
    """
    Top-level manifest for a project or corpus.

    A ProjectManifest describes the full scope of a knowledge source:
    its identity, schema version, file inventory, and composition metadata.

    Legacy context:
        Corresponds to UNCF cartridge.json with manifest keys like
        schema_name, cartridge_id, embedding_spec, chunking_spec, etc.
    """

    project_root_hash: ProjectRootHash
    project_id: str
    name: str = ""
    description: str = ""
    schema_version: str = "0.1.0"
    entries: List[ProjectManifestEntry] = field(default_factory=list)
    file_manifest: Optional[FileManifest] = None
    embedding_spec: Dict[str, Any] = field(default_factory=dict)
    chunking_spec: Dict[str, Any] = field(default_factory=dict)
    capabilities: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    properties: Dict[str, Any] = field(default_factory=dict)

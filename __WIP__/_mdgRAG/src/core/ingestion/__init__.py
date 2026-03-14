"""
Ingestion pipeline — Phase 13.

Public API:
    ingest_file(file_path, manifold, store, config, embed_fn) → IngestionResult
    ingest_directory(directory_path, manifold, store, config, embed_fn) → IngestionResult

Configuration:
    IngestionConfig — chunking budgets, file filtering, embedding behavior

Types:
    IngestionResult — summary of an ingestion run
    SourceFile — detected source file metadata
    RawChunk — intermediate chunking output
"""

from .config import IngestionConfig
from .ingest import IngestionResult, ingest_directory, ingest_file

__all__ = [
    "IngestionConfig",
    "IngestionResult",
    "ingest_file",
    "ingest_directory",
]

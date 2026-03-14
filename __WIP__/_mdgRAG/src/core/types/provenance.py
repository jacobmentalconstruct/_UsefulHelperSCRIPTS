"""
Provenance — typed lineage and origin tracking for manifold elements.

Ownership: src/core/types/provenance.py
    Single source of truth for provenance records. Every element in a
    manifold can carry provenance tracing its origin, transformations,
    and derivation history.

Provenance answers: where did this element come from, what created it,
and through which processing stages did it pass?

Legacy context:
    - Legacy lineage DAG (NetworkX directed graph) tracked
      source → chunk derivation
    - Legacy UNCF cartridge stored ingest/parser metadata
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.core.types.ids import ManifoldId
from src.core.types.enums import ProvenanceStage, ProvenanceRelationOrigin


@dataclass
class Provenance:
    """
    Full provenance record for a manifold element.

    Tracks the origin, transformation history, and relationship context
    of any node, edge, chunk, or binding in the system.
    """

    # What this provenance record describes
    owner_kind: str             # "node", "edge", "chunk", "embedding", etc.
    owner_id: str               # The ID of the element this provenance belongs to

    # Where it came from
    source_manifold_id: Optional[ManifoldId] = None
    source_document: Optional[str] = None       # File path, URL, or identifier
    source_snapshot: Optional[str] = None        # Snapshot/version identifier

    # How it was created
    stage: ProvenanceStage = ProvenanceStage.INGESTION
    relation_origin: ProvenanceRelationOrigin = ProvenanceRelationOrigin.PARSED
    parser_name: Optional[str] = None           # e.g. "python_ast", "text_chunker"
    parser_version: Optional[str] = None

    # Evidence and tracing
    evidence_ref: Optional[str] = None          # Reference to supporting evidence
    upstream_ids: List[str] = field(default_factory=list)  # IDs of parent elements

    # Extensible details
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[str] = None

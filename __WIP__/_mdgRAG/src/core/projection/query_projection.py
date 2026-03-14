"""
Query Projection — transform query into a structured working object.

Ownership: src/core/projection/query_projection.py
    The query is NOT just a detached string used as retrieval input.
    It becomes a structured, live working object that carries:
        - A first-class graph node (NodeType.QUERY)
        - Parsed intent
        - Scope constraints
        - Query embedding vector (when embed_fn is provided)
        - Deterministic stable ID derived from query text

    This projection gives the query first-class citizenship in the
    manifold pipeline rather than treating it as a flat search string.

    When an embedding callback (embed_fn) is provided, the query
    text is embedded and the resulting vector is stored in
    QueryProjectionArtifact.properties["query_embedding"].
    This enables downstream semantic scoring.

    QueryProjection does NOT instantiate or discover ModelBridge
    itself. It receives an embedding capability via callback.
    The RuntimeController owns the wiring.

Future extraction targets (from legacy):
    - Query parsing and structuring logic
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.core.contracts.projection_contract import (
    ProjectedSlice,
    ProjectionContract,
    ProjectionMetadata,
    QueryProjectionArtifact,
)
from src.core.types.ids import HASH_TRUNCATION_LENGTH, ManifoldId, NodeId, deterministic_hash
from src.core.types.enums import NodeType, ProjectionSourceKind
from src.core.types.graph import Node
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


# Type alias for the embedding callback.
# Accepts a query string, returns a sequence of floats (the embedding vector).
EmbedFn = Callable[[str], Sequence[float]]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class QueryProjection(ProjectionContract):
    """
    Project a query into a structured working object.

    The query becomes a live participant in the manifold pipeline,
    not just a detached string for retrieval. Creates a QUERY-typed
    Node and wraps it in a QueryProjectionArtifact.

    When an embed_fn is provided, the raw query is embedded and the
    resulting vector is stored in the artifact's properties for
    downstream semantic scoring.
    """

    def project(
        self,
        manifold: Any,
        criteria: Dict[str, Any],
        *,
        embed_fn: Optional[EmbedFn] = None,
    ) -> ProjectedSlice:
        """
        Project query into structured form.

        Supported criteria keys:
            - "raw_query": str -- the query text (REQUIRED)
            - "parsed_intent": Dict -- optional parsed intent
            - "scope_constraints": Dict -- optional scope constraints
            - "embedding_ref": str -- optional reference to query embedding

        Args:
            manifold: Not used for query projection (may be None).
            criteria: Must contain "raw_query".
            embed_fn: Optional callback that accepts a query string and
                returns an embedding vector (Sequence[float]). When
                provided, the query embedding is stored in the artifact's
                properties["query_embedding"]. QueryProjection does not
                own the embedding backend — the caller provides this.

        Returns:
            ProjectedSlice with a single QUERY-typed node and a
            QueryProjectionArtifact in projected_data["query_artifact"].

        Raises:
            ValueError: If "raw_query" is missing or empty.
        """
        raw_query = criteria.get("raw_query", "")
        if not raw_query:
            raise ValueError("QueryProjection requires 'raw_query' in criteria")

        # Deterministic node ID from query text
        query_node_id = NodeId(
            f"query-{deterministic_hash(raw_query)[:HASH_TRUNCATION_LENGTH]}"
        )

        now = _utcnow_iso()

        # Create the query node
        query_node = Node(
            node_id=query_node_id,
            manifold_id=ManifoldId("query"),
            node_type=NodeType.QUERY,
            canonical_key=raw_query,
            label=raw_query[:100],
            properties={
                "full_query": raw_query,
                "origin": "query",
                "ephemeral": True,
            },
            created_at=now,
            updated_at=now,
        )

        # Build the artifact
        artifact = QueryProjectionArtifact(
            raw_query=raw_query,
            embedding_ref=criteria.get("embedding_ref"),
            parsed_intent=criteria.get("parsed_intent", {}),
            scope_constraints=criteria.get("scope_constraints", {}),
            query_node_id=query_node_id,
            query_node=query_node,
        )

        # Generate query embedding if callback provided
        if embed_fn is not None:
            try:
                embedding_vector = embed_fn(raw_query)
                # Store as a list of floats for downstream scoring
                artifact.properties["query_embedding"] = list(embedding_vector)
                artifact.properties["query_embedding_dimensions"] = len(
                    artifact.properties["query_embedding"]
                )
                logger.info(
                    "QueryProjection: query embedded (dims=%d)",
                    artifact.properties["query_embedding_dimensions"],
                )
            except Exception as exc:
                # Embedding failure is non-fatal — log and continue
                # without embedding. Scoring will fall back to
                # structural-only gravity.
                logger.warning(
                    "QueryProjection: embed_fn failed, continuing without "
                    "query embedding: %s",
                    exc,
                )
                artifact.properties["query_embedding_error"] = str(exc)
        else:
            logger.info(
                "QueryProjection: no embed_fn provided — query embedding skipped",
            )

        # Build the slice
        return ProjectedSlice(
            metadata=ProjectionMetadata(
                source_manifold_id=ManifoldId("query"),
                source_kind=ProjectionSourceKind.QUERY,
                criteria=criteria,
                timestamp=now,
                description="Query projection",
            ),
            node_ids=[query_node_id],
            nodes=[query_node],
            projected_data={"query_artifact": artifact},
        )

    def project_by_ids(
        self,
        manifold: Any,
        node_ids: List[NodeId],
    ) -> ProjectedSlice:
        """Not applicable for query projection. Use project() with raw_query."""
        raise NotImplementedError(
            "QueryProjection does not support project_by_ids. "
            "Use project(manifold, {'raw_query': ...}) instead."
        )

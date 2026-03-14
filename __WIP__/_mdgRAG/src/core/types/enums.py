"""
Enumerations — typed constants defining the manifold system vocabulary.

Ownership: src/core/types/enums.py
    Single source of truth for all domain enumerations. Using enums
    instead of string literals prevents typo-driven bugs and makes the
    domain language explicit and discoverable.

Legacy context:
    - ManifoldRole maps to Mind 1 (EXTERNAL), Mind 2 (IDENTITY/session),
      Mind 3 (VIRTUAL)
    - EdgeType placeholders correspond to legacy KG edge types
      (ADJACENT, CONTAINS, CALLS, IMPORTS, INHERITS)
    - StorageMode replaces the implicit legacy mix of SQLite, FAISS files,
      and in-memory NetworkX graphs
"""

from enum import Enum, auto


# ---------------------------------------------------------------------------
# Manifold identity
# ---------------------------------------------------------------------------

class ManifoldRole(Enum):
    """The role a manifold plays in the three-manifold model."""

    IDENTITY = auto()   # Session memory, user/agent/role graph
    EXTERNAL = auto()   # Persistent corpus, source evidence, domain knowledge
    VIRTUAL = auto()    # Ephemeral fused workspace, runtime-only scores


class StorageMode(Enum):
    """How a manifold's data is persisted or held at runtime."""

    SQLITE_DISK = auto()     # Durable SQLite database on disk
    SQLITE_MEMORY = auto()   # SQLite in-memory (fast, session-scoped)
    PYTHON_RAM = auto()      # Pure-Python dicts/lists in process memory


# ---------------------------------------------------------------------------
# Node vocabulary
# ---------------------------------------------------------------------------

class NodeType(Enum):
    """Types of nodes in a manifold's knowledge graph."""

    # Content nodes
    CHUNK = auto()          # Content segment with deterministic hash
    SOURCE = auto()         # Source document or file
    SECTION = auto()        # Structural section within a source

    # Semantic nodes
    CONCEPT = auto()        # Abstract concept or named entity
    TOPIC = auto()          # Topic cluster anchor

    # Identity nodes
    SESSION = auto()        # Session-scoped context node
    AGENT = auto()          # Agent or role identity node
    USER = auto()           # User identity node

    # Query nodes
    QUERY = auto()          # Query-derived working node

    # Structural nodes
    DIRECTORY = auto()      # Filesystem directory
    PROJECT = auto()        # Project root


class NodeCategory(Enum):
    """Broad category grouping for node types."""

    CONTENT = auto()        # Nodes that carry textual content
    SEMANTIC = auto()       # Nodes representing meaning/concepts
    IDENTITY = auto()       # Nodes representing actors/roles
    STRUCTURAL = auto()     # Nodes representing containment/layout


# ---------------------------------------------------------------------------
# Edge vocabulary
# ---------------------------------------------------------------------------

class EdgeType(Enum):
    """Types of edges in a manifold's knowledge graph."""

    # Structural edges
    ADJACENT = auto()       # Sequential/positional adjacency
    CONTAINS = auto()       # Structural containment (parent → child)
    NEXT = auto()           # Ordered sequence (chunk n → chunk n+1)

    # Code-structural edges
    CALLS = auto()          # Function/method invocation
    IMPORTS = auto()        # Module/package import
    INHERITS = auto()       # Class inheritance
    DEFINES = auto()        # Scope defines symbol

    # Semantic edges
    SEMANTIC = auto()       # Semantic similarity relation
    REFERENCES = auto()     # Cross-reference or citation

    # Cross-manifold edges
    BRIDGE = auto()         # Fusion-created cross-manifold edge

    # Provenance edges
    DERIVES = auto()        # Derivation/lineage (source → derived)
    INGESTED_FROM = auto()  # Ingestion provenance


class EdgeCategory(Enum):
    """Broad category grouping for edge types."""

    STRUCTURAL = auto()     # Positional/containment relationships
    CODE = auto()           # Code-level relationships
    SEMANTIC = auto()       # Meaning-based relationships
    CROSS_MANIFOLD = auto() # Fusion bridge relationships
    PROVENANCE = auto()     # Lineage/derivation relationships


# ---------------------------------------------------------------------------
# Projection
# ---------------------------------------------------------------------------

class ProjectionSourceKind(Enum):
    """The kind of source a projection draws from."""

    IDENTITY = auto()       # Projection from identity manifold
    EXTERNAL = auto()       # Projection from external manifold
    QUERY = auto()          # Projection from query structure


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class ProvenanceStage(Enum):
    """The stage in the pipeline where a provenance record was created."""

    INGESTION = auto()      # During initial content ingestion
    CHUNKING = auto()       # During text chunking
    EMBEDDING = auto()      # During vector embedding
    GRAPH_BUILD = auto()    # During knowledge graph construction
    PROJECTION = auto()     # During manifold projection
    FUSION = auto()         # During manifold fusion
    EXTRACTION = auto()     # During evidence bag extraction
    HYDRATION = auto()      # During evidence hydration
    SYNTHESIS = auto()      # During model synthesis


class ProvenanceRelationOrigin(Enum):
    """How a relationship (edge) was originally created."""

    PARSED = auto()         # Extracted by a parser (AST, NLP, etc.)
    COMPUTED = auto()       # Computed by an algorithm (similarity, etc.)
    DECLARED = auto()       # Declared by a human or external source
    FUSED = auto()          # Created by the fusion engine


# ---------------------------------------------------------------------------
# Hydration
# ---------------------------------------------------------------------------

class HydrationMode(Enum):
    """How evidence bag content should be hydrated for synthesis."""

    FULL = auto()           # Hydrate all node payloads completely
    SUMMARY = auto()        # Hydrate with summarised payloads
    REFERENCE = auto()      # Hydrate with references only (IDs + metadata)


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------

class EmbeddingMetricType(Enum):
    """Distance/similarity metric used by the embedding space."""

    COSINE = auto()         # Cosine similarity (via L2-normalised inner product)
    EUCLIDEAN = auto()      # L2 distance
    INNER_PRODUCT = auto()  # Raw inner product (unnormalised)


class EmbeddingTargetKind(Enum):
    """What kind of entity an embedding vector represents."""

    CHUNK = auto()          # Embedding of a chunk's text content
    NODE = auto()           # Embedding of a node's aggregated content
    QUERY = auto()          # Embedding of a user query

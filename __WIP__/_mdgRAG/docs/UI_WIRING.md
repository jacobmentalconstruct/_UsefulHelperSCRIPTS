# UI Wiring Guide

Comprehensive reference for building a user interface on top of Graph Manifold.
Covers every public API, data flow, type shapes, and integration patterns.

Updated: Phase 11 (445 tests passing)

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Current State](#current-state)
3. [Primary Entry Point — RuntimeController.run()](#primary-entry-point)
4. [Pipeline Data Flow](#pipeline-data-flow)
5. [Manifold Lifecycle](#manifold-lifecycle)
6. [Configuration Surface](#configuration-surface)
7. [Type Reference](#type-reference)
8. [Debug & Inspection API](#debug--inspection-api)
9. [Scoring & Math API](#scoring--math-api)
10. [Model Bridge API](#model-bridge-api)
11. [Store CRUD API](#store-crud-api)
12. [UI Panel Layout Suggestions](#ui-panel-layout-suggestions)
13. [Wiring Patterns](#wiring-patterns)
14. [Error Handling](#error-handling)
15. [Import Map](#import-map)

---

## System Overview

Graph Manifold is a deterministic, graph-native retrieval system. It processes
queries through a fixed pipeline:

```
Query  -->  Projection  -->  Fusion  -->  Scoring  -->  Extraction  -->  Hydration  -->  Synthesis
             (stages 1-3)    (stage 4)   (stage 5)     (stage 6)       (stage 7)       (stage 8)
```

The system uses a **three-manifold model**:

| Manifold | Role | Lifecycle | Storage |
|----------|------|-----------|---------|
| **Identity** | Session memory, user/agent graph | Persistent or session-scoped | Disk or RAM |
| **External** | Corpus, source evidence, domain knowledge | Persistent | Disk (SQLite) |
| **Virtual** | Fused workspace with runtime scores | Ephemeral (per-query) | RAM only |

All three share the **same-schema contract** — identical typed collections
(nodes, edges, chunks, embeddings, hierarchy, bindings, provenance).

---

## Current State

- **CLI only** — `app.py` is bootstrap-only (confirms components instantiate, no query path)
- **No ingestion pipeline** — manifolds must be populated programmatically via `ManifoldStore` or by directly setting collections on `BaseManifold`
- **No CLI query command** — `RuntimeController.run()` is the programmatic API
- **Ollama required** for embedding and synthesis — `ModelBridge` calls `http://localhost:11434`
- **Structural-only fallback** — pipeline works without Ollama (gravity uses PageRank only)

---

## Primary Entry Point

### `RuntimeController.run()`

This is the single function a UI calls to execute a query against loaded manifolds.

```python
from src.core.runtime import RuntimeController, PipelineConfig, PipelineResult

controller = RuntimeController()

result: PipelineResult = controller.run(
    query="How does authentication work?",
    identity_manifold=identity_m,       # BaseManifold or None
    external_manifold=external_m,       # BaseManifold or None
    identity_node_ids=None,             # Optional[List[NodeId]] — subset filter
    external_node_ids=None,             # Optional[List[NodeId]] — subset filter
    config=PipelineConfig(),            # Optional — uses defaults if None
)
```

**Returns**: `PipelineResult` containing every intermediate artifact plus the final answer.

**Raises**:
- `ValueError` — empty query string
- `PipelineError` — any stage failure (carries `.stage` and `.cause` attributes)

**Minimum viable call** (no manifolds, no model):
```python
result = controller.run("test query")
# result.degraded == True, result.answer_text == ""
# Still produces query_artifact with parsed query node
```

---

## Pipeline Data Flow

Each stage produces a typed artifact that flows to the next stage. The UI can
inspect any intermediate artifact from `PipelineResult`.

```
INPUT                              ARTIFACT                          RESULT FIELD
-----                              --------                          ------------

query (str)              -->  QueryProjectionArtifact           -->  result.query_artifact
identity_manifold        -->  ProjectedSlice (identity)         -->  result.identity_slice
external_manifold        -->  ProjectedSlice (external)         -->  result.external_slice
                                      |
                                      v
                              FusionResult                      -->  result.fusion_result
                              (contains VirtualManifold)
                                      |
                                      v
                              Dict[NodeId, float] x 3           -->  result.structural_scores
                              (structural, semantic, gravity)        result.semantic_scores
                                                                    result.gravity_scores
                                      |
                                      v
                              EvidenceBag                        -->  result.evidence_bag
                                      |
                                      v
                              HydratedBundle                    -->  result.hydrated_bundle
                              str (formatted context)           -->  result.evidence_context
                                      |
                                      v
                              SynthesisResponse                 -->  result.synthesis_response
                              str (answer)                      -->  result.answer_text
```

### Timing metadata

`result.timing` is a `Dict[str, float]` with keys:
`"projection"`, `"fusion"`, `"scoring"`, `"extraction"`, `"hydration"`, `"synthesis"`, `"total"`

Values are seconds (from `time.perf_counter()`).

### Degradation signals

- `result.degraded` — `True` when semantic scoring was skipped (no model) or synthesis failed
- `result.skipped_stages` — list of stage names that were bypassed
- `result.stage_count` — number of stages that executed

---

## Manifold Lifecycle

### Creating manifolds

```python
from src.core.factory.manifold_factory import ManifoldFactory
from src.core.types.ids import ManifoldId
from src.core.types.enums import ManifoldRole, StorageMode

factory = ManifoldFactory()

# Disk-backed (persistent, WAL mode SQLite)
ext_manifold = factory.create_disk_manifold(
    manifold_id=ManifoldId("corpus-v1"),
    role=ManifoldRole.EXTERNAL,
    db_path="data/corpus.db",
    description="Primary knowledge corpus",
)

# In-memory SQLite (session-scoped, fast, supports SQL queries)
id_manifold = factory.create_memory_manifold(
    manifold_id=ManifoldId("session-001"),
    role=ManifoldRole.IDENTITY,
    description="Current session context",
)

# Unified creator (dispatches by storage_mode)
manifold = factory.create_manifold(
    manifold_id=ManifoldId("my-manifold"),
    role=ManifoldRole.EXTERNAL,
    storage_mode=StorageMode.SQLITE_DISK,
    db_path="data/my.db",
)

# Open existing disk manifold
existing = factory.open_manifold("data/corpus.db")
```

### Reading manifold contents (RAM path)

All manifolds expose identical getters (same-schema rule):

```python
nodes: Dict[NodeId, Node]               = manifold.get_nodes()
edges: Dict[EdgeId, Edge]               = manifold.get_edges()
chunks: Dict[ChunkHash, Chunk]          = manifold.get_chunks()
embeddings: Dict[EmbeddingId, Embedding] = manifold.get_embeddings()
hierarchy: Dict[HierarchyId, HierarchyEntry] = manifold.get_hierarchy()
metadata: ManifoldMetadata               = manifold.get_metadata()

# Cross-layer bindings
nc_bindings: List[NodeChunkBinding]      = manifold.get_node_chunk_bindings()
ne_bindings: List[NodeEmbeddingBinding]  = manifold.get_node_embedding_bindings()
nh_bindings: List[NodeHierarchyBinding]  = manifold.get_node_hierarchy_bindings()

# Provenance
provenance: List[Provenance]             = manifold.get_provenance_entries()

# SQLite connection (for disk/memory manifolds)
conn: Optional[sqlite3.Connection]       = manifold.connection
```

### Populating manifolds (RAM path — direct dict mutation)

```python
from src.core.types.graph import Node, Edge, Chunk
from src.core.types.ids import NodeId, EdgeId, ChunkHash, ManifoldId
from src.core.types.enums import NodeType, EdgeType

# Add a node directly
node = Node(
    node_id=NodeId("n1"),
    manifold_id=ManifoldId("corpus-v1"),
    node_type=NodeType.CONCEPT,
    canonical_key="authentication",
    label="Authentication",
    properties={"domain": "security"},
)
manifold.get_nodes()[node.node_id] = node

# Add an edge directly
edge = Edge(
    edge_id=EdgeId("e1"),
    manifold_id=ManifoldId("corpus-v1"),
    from_node_id=NodeId("n1"),
    to_node_id=NodeId("n2"),
    edge_type=EdgeType.REFERENCES,
    weight=1.0,
)
manifold.get_edges()[edge.edge_id] = edge

# Add a chunk directly
chunk = Chunk(chunk_hash=ChunkHash("abc123"), chunk_text="Authentication uses JWT tokens...")
manifold.get_chunks()[chunk.chunk_hash] = chunk
```

### Populating manifolds (SQLite path — via ManifoldStore)

```python
from src.core.store.manifold_store import ManifoldStore

store = ManifoldStore()
conn = manifold.connection  # sqlite3.Connection

store.add_node(conn, node)
store.add_edge(conn, edge)
store.add_chunk(conn, chunk)
store.link_node_chunk(conn, NodeChunkBinding(
    node_id=NodeId("n1"),
    chunk_hash=ChunkHash("abc123"),
    manifold_id=ManifoldId("corpus-v1"),
))
```

---

## Configuration Surface

### PipelineConfig — all tunable parameters in one place

```python
@dataclass
class PipelineConfig:
    # --- Scoring weights ---
    alpha: float = 0.6              # Structural weight in gravity formula
    beta: float = 0.4               # Semantic weight in gravity formula

    # --- PageRank parameters ---
    damping: float = 0.85           # PageRank damping factor
    max_iterations: int = 100       # Convergence limit
    tolerance: float = 1e-8         # Convergence threshold

    # --- Sub-configurations ---
    fusion_config: Optional[FusionConfig] = None
    extraction_config: Optional[ExtractionConfig] = None
    hydration_config: Optional[HydrationConfig] = None
    model_bridge_config: Optional[ModelBridgeConfig] = None

    # --- Synthesis parameters ---
    synthesis_model: str = ""       # Ollama model name (e.g. "llama3.2")
    system_prompt: Optional[str] = None
    temperature: float = 0.0
    max_synthesis_tokens: int = 4096

    # --- Pipeline behavior ---
    skip_synthesis: bool = False    # Stop after hydration (no model call)
```

### Sub-configurations

**FusionConfig** — bridge behavior:
```python
@dataclass
class FusionConfig:
    enable_label_fallback: bool = True    # Case-insensitive label matching
    label_fallback_weight: float = 0.7    # Weight for label-matched bridges
    canonical_key_weight: float = 1.0     # Weight for canonical key bridges
```

**ExtractionConfig** — evidence bag limits:
```python
@dataclass
class ExtractionConfig:
    max_seed_nodes: int = 3         # Top gravity nodes used as BFS seeds
    max_hops: int = 1               # BFS expansion depth
    token_budget: int = 2048        # Token limit for evidence bag
    max_nodes: int = 25             # Hard cap on nodes
    max_edges: int = 40             # Hard cap on edges
    max_chunks: int = 12            # Hard cap on chunks
```

**HydrationConfig** — content resolution behavior:
```python
@dataclass
class HydrationConfig:
    mode: HydrationMode = HydrationMode.FULL   # FULL, SUMMARY, REFERENCE
    budget_target: Optional[int] = None         # Token truncation target
    include_scores: bool = True                 # Attach score annotations
    include_hierarchy: bool = True              # Attach hierarchy context
    include_provenance: bool = True             # Attach provenance data
```

**ModelBridgeConfig** — Ollama connection:
```python
@dataclass
class ModelBridgeConfig:
    base_url: str = "http://localhost:11434"
    embed_model: str = "mxbai-embed-large"
    synthesis_model: str = ""
    timeout_seconds: float = 60.0
    context_window: int = 0
    embedding_dimensions: int = 0
    estimator: str = "split_heuristic"
```

---

## Type Reference

### ID Types (all `NewType("...", str)`)

| Type | Used For | Example |
|------|----------|---------|
| `ManifoldId` | Manifold identity | `"corpus-v1"` |
| `NodeId` | Graph node identity | `"n-auth-001"` |
| `EdgeId` | Graph edge identity | `"e-001"` |
| `ChunkHash` | Content-addressed chunk | `"a1b2c3..."` (SHA256) |
| `EmbeddingId` | Embedding vector identity | `"emb-001"` |
| `HierarchyId` | Hierarchy entry identity | `"h-001"` |
| `EvidenceBagId` | Evidence bag identity | `"bag-..."` (deterministic hash) |

### Node Types

```
CHUNK, SOURCE, SECTION          — content nodes
CONCEPT, TOPIC                  — semantic nodes
SESSION, AGENT, USER            — identity nodes
QUERY                           — query nodes (created by QueryProjection)
DIRECTORY, PROJECT              — structural nodes
```

### Edge Types

```
ADJACENT, CONTAINS, NEXT        — structural edges
CALLS, IMPORTS, INHERITS, DEFINES — code-structural edges
SEMANTIC, REFERENCES            — semantic edges
BRIDGE                          — cross-manifold bridges (created by fusion)
DERIVES, INGESTED_FROM          — provenance edges
```

### Key Dataclass Shapes

**Node**:
```
node_id, manifold_id, node_type, canonical_key, label, properties,
source_refs, created_at, updated_at
```

**Edge**:
```
edge_id, manifold_id, from_node_id, to_node_id, edge_type, weight,
properties, created_at, updated_at
```

**Chunk**:
```
chunk_hash, chunk_text, byte_length, char_length, token_estimate,
hash_algorithm, created_at
```
Note: `byte_length`, `char_length`, `token_estimate` auto-fill in `__post_init__`.

**Embedding**:
```
embedding_id, target_kind (NODE/CHUNK/QUERY), target_id, model_name,
model_version, dimensions, metric_type, is_normalized, vector_ref,
vector_blob (packed float32), created_at
```

**ScoreAnnotation** (attached to nodes in runtime_annotations):
```
structural: float, semantic: float, gravity: float,
raw_scores: Dict[str, float]
```

**HydratedNode** (in HydratedBundle.nodes):
```
node_id, content (resolved chunk text), token_estimate,
chunk_hashes, label, node_type, metadata
    metadata["score"] = {structural, semantic, gravity, raw_scores}
    metadata["hierarchy"] = [{hierarchy_id, depth, sort_order, path_label, parent_id}]
    metadata["properties"] = node.properties
```

**HydratedEdge** (in HydratedBundle.edges):
```
edge_id, source_id, target_id, relation (EdgeType.name string),
weight, metadata
```

---

## Debug & Inspection API

All inspection functions return plain dicts — perfect for JSON serialization to a UI.

```python
from src.core.debug import (
    dump_virtual_scores,
    dump_projection_summary,
    dump_fusion_result,
    dump_evidence_bag,
    dump_hydrated_bundle,
    inspect_pipeline_result,
)
```

### `dump_projection_summary(projected_slice) -> dict`
```
{
    "source_manifold_id": str,
    "source_kind": str,
    "timestamp": str,
    "description": str,
    "node_count": int,
    "edge_count": int,
    "chunk_count": int,
    "embedding_count": int,
    "hierarchy_count": int,
    "nc_bindings": int,
    "ne_bindings": int,
    "nh_bindings": int,
    "provenance_count": int,
    "node_ids": [str, ...]
}
```

### `dump_fusion_result(fusion_result) -> dict`
```
{
    "vm_id": str,
    "vm_node_count": int,
    "vm_edge_count": int,
    "bridge_count": int,
    "bridge_types": {"explicit": int, "canonical_key": int, "label": int},
    "source_manifold_ids": [str, ...],
    "projection_count": int,
    "strategy": str,
    "provenance_count": int
}
```

### `dump_evidence_bag(evidence_bag) -> dict`
```
{
    "bag_id": str,
    "source_virtual_manifold_id": str,
    "node_count": int,
    "edge_count": int,
    "chunk_ref_count": int,
    "hierarchy_ref_count": int,
    "token_budget": {
        "used": int,
        "max": int,
        "utilization": float   # 0.0-1.0
    },
    "top_gravity": [
        {"node_id": str, "gravity": float, "structural": float, "semantic": float},
        ...  # top 10
    ]
}
```

### `dump_hydrated_bundle(hydrated_bundle) -> dict`
```
{
    "node_count": int,
    "edge_count": int,
    "total_tokens": int,
    "mode": str,
    "topology_preserved": bool,
    "content_lengths": [
        {"node_id": str, "label": str, "content_length": int},
        ...
    ]
}
```

### `dump_virtual_scores(vm) -> dict`
```
{
    "node_count": int,
    "annotated_count": int,
    "scores": {
        node_id: {"structural": float, "semantic": float, "gravity": float},
        ...
    },
    "top_gravity": [(node_id, gravity_score), ...]  # top 10 descending
}
```

### `inspect_pipeline_result(pipeline_result) -> dict`
```
{
    "answer_length": int,
    "has_synthesis": bool,
    "degraded": bool,
    "skipped_stages": [str, ...],
    "stage_count": int,
    "timing": {"projection": float, "fusion": float, ...},
    "artifacts": {
        "query_artifact": bool,   # present?
        "identity_slice": bool,
        "external_slice": bool,
        "fusion_result": bool,
        "evidence_bag": bool,
        "hydrated_bundle": bool
    },
    "scoring_summary": {
        "structural_nodes": int,
        "semantic_nodes": int,
        "gravity_nodes": int
    }
}
```

---

## Scoring & Math API

These are the pure-Python scoring functions used internally by the pipeline.
A UI can also call them directly for visualization or parameter tuning.

```python
from src.core.math.scoring import (
    structural_score,
    semantic_score,
    gravity_score,
    spreading_activation,
    normalize_min_max,
)
```

### `structural_score(graph, *, damping=0.85, max_iterations=100, tolerance=1e-8) -> Dict[NodeId, float]`

PageRank via power iteration. Input: any object with `get_nodes()` and `get_edges()`.
Returns raw scores (sum ~ 1.0). Dangling nodes redistribute uniformly.

### `semantic_score(node_embeddings, query_embedding) -> Dict[NodeId, float]`

Cosine similarity per node vs. query embedding. Returns scores in [0, 1].
- `node_embeddings`: `Dict[NodeId, List[float]]`
- `query_embedding`: `List[float]`

### `gravity_score(structural_scores, semantic_scores, alpha=0.6, beta=0.4) -> Dict[NodeId, float]`

Fused score: `G(v) = alpha * S_norm(v) + beta * T_norm(v)`.
Both inputs min-max normalized internally. Missing nodes get 0.0 for that component.

### `spreading_activation(graph, seed_nodes, iterations=3, decay=0.5) -> Dict[NodeId, float]`

BFS spreading from seeds with exponential decay. Seeds keep 1.0.

### `normalize_min_max(scores) -> Dict[NodeId, float]`

Min-max normalize to [0, 1]. Single/all-equal values get 0.5.

### Friction detection

```python
from src.core.math.friction import (
    detect_island_effect,       # graph has disconnected components?
    detect_gravity_collapse,    # score spread too narrow?
    detect_normalization_extrema,  # all scores near zero?
    detect_all_friction,        # run all detectors, return summary dict
)
```

`detect_all_friction(graph, gravity_scores) -> Dict[str, bool]`:
```
{"island_effect": bool, "gravity_collapse": bool, "normalization_extrema": bool}
```

### Score annotator

```python
from src.core.math.annotator import annotate_scores, read_score_annotation

# Write scores into VM runtime_annotations
annotate_scores(vm, structural, semantic, gravity)

# Read back
annotation: Optional[ScoreAnnotation] = read_score_annotation(vm, node_id)
```

---

## Model Bridge API

Ollama HTTP backend for embedding and synthesis.

```python
from src.core.model_bridge.model_bridge import (
    ModelBridge, ModelBridgeConfig,
    ModelConnectionError, ModelResponseError, ModelBridgeError,
)
from src.core.contracts.model_bridge_contract import (
    EmbedRequest, EmbedResponse,
    SynthesisRequest, SynthesisResponse,
    ModelIdentity,
)
```

### Construction

```python
bridge = ModelBridge(ModelBridgeConfig(
    base_url="http://localhost:11434",
    embed_model="mxbai-embed-large",
    synthesis_model="llama3.2",
    timeout_seconds=60.0,
))
```

### Embedding

```python
response: EmbedResponse = bridge.embed(EmbedRequest(
    texts=["How does authentication work?"],
    model="",  # uses config.embed_model if empty
))
vector: List[float] = response.vectors[0]    # L2-normalized
dims: int = response.dimensions
```

### Synthesis

```python
response: SynthesisResponse = bridge.synthesize(SynthesisRequest(
    evidence_context="=== EVIDENCE BUNDLE ===\n...",
    query="How does authentication work?",
    model="llama3.2",
    system_prompt="You are a helpful assistant.",
    temperature=0.0,
    max_tokens=4096,
))
answer: str = response.text
tokens: int = response.tokens_used
```

### Token estimation (offline, no HTTP)

```python
estimate: int = bridge.estimate_tokens("some text here")
# Formula: int(len(text.split()) * 1.3 + 1)
```

### Model identity

```python
identity: Optional[ModelIdentity] = bridge.get_model_identity()
# Returns None if no model configured
```

### Error hierarchy

```
ModelBridgeError          — base class
  ModelConnectionError    — network/timeout failure (caught gracefully by pipeline)
  ModelResponseError      — unexpected response shape from Ollama
```

---

## Store CRUD API

`ManifoldStore` provides stateless typed CRUD against a SQLite connection.
Used for disk-backed and memory-backed manifolds.

```python
from src.core.store.manifold_store import ManifoldStore

store = ManifoldStore()
conn = manifold.connection  # sqlite3.Connection
```

### Write operations

```python
store.add_node(conn, node: Node)
store.add_edge(conn, edge: Edge)
store.add_chunk(conn, chunk: Chunk)
store.add_chunk_occurrence(conn, occ: ChunkOccurrence)
store.add_embedding(conn, emb: Embedding)
store.add_hierarchy(conn, entry: HierarchyEntry)
store.add_metadata(conn, entry: MetadataEntry)
store.add_provenance(conn, prov: Provenance)

# Cross-layer links
store.link_node_chunk(conn, binding: NodeChunkBinding)
store.link_node_embedding(conn, binding: NodeEmbeddingBinding)
store.link_node_hierarchy(conn, binding: NodeHierarchyBinding)
```

All write methods validate non-empty required fields (raise `ValueError`).
Self-loop edges emit warnings.

### Read operations

```python
store.get_node(conn, node_id: NodeId) -> Optional[Node]
store.list_nodes(conn, manifold_id: ManifoldId) -> List[Node]

store.get_edge(conn, edge_id: EdgeId) -> Optional[Edge]
store.list_edges(conn, manifold_id: ManifoldId) -> List[Edge]

store.get_chunk(conn, chunk_hash: ChunkHash) -> Optional[Chunk]

store.get_embedding(conn, embedding_id: EmbeddingId) -> Optional[Embedding]

store.get_hierarchy(conn, hierarchy_id: HierarchyId) -> Optional[HierarchyEntry]

store.get_metadata_for_owner(conn, owner_kind: str, owner_id: str, manifold_id: ManifoldId) -> List[MetadataEntry]

store.get_provenance_for_owner(conn, owner_kind: str, owner_id: str) -> List[Provenance]

# Cross-layer link readers
store.get_node_chunk_links(conn, node_id: NodeId) -> List[NodeChunkBinding]
store.get_node_embedding_links(conn, node_id: NodeId) -> List[NodeEmbeddingBinding]
store.get_node_hierarchy_links(conn, node_id: NodeId) -> List[NodeHierarchyBinding]
```

---

## UI Panel Layout Suggestions

Based on the data available from the pipeline, here are logical UI panels:

### Panel 1 — Query Input & Config

- Text input for query
- Accordion/sidebar for PipelineConfig overrides:
  - Alpha/beta sliders (0.0-1.0, sum to 1.0)
  - Extraction limits (max_seed_nodes, max_hops, token_budget)
  - Hydration mode selector (FULL / SUMMARY / REFERENCE)
  - Skip synthesis toggle
  - Model selector (embed_model, synthesis_model)
- "Run" button that calls `controller.run()`

### Panel 2 — Pipeline Status & Timing

- Stage progress indicator (projection > fusion > scoring > extraction > hydration > synthesis)
- Per-stage timing bars from `result.timing`
- Degraded/skipped stage warnings from `result.degraded`, `result.skipped_stages`

### Panel 3 — Graph Visualization

Data source: `result.fusion_result.virtual_manifold`
- Node/edge graph view from `vm.get_nodes()` and `vm.get_edges()`
- Color nodes by gravity score from `result.gravity_scores`
- Highlight bridge edges (edge_type == BRIDGE)
- Show node labels, types, canonical keys on hover
- Highlight seed nodes from evidence bag extraction

### Panel 4 — Score Explorer

Data source: `result.structural_scores`, `result.semantic_scores`, `result.gravity_scores`
- Sortable table: node_id | label | structural | semantic | gravity
- Bar chart of top-N gravity scores
- Friction warnings from `detect_all_friction(vm, gravity_scores)`
- Alpha/beta weight visualization showing formula contribution

### Panel 5 — Evidence Bag Inspector

Data source: `result.evidence_bag`, `dump_evidence_bag(result.evidence_bag)`
- Node list with gravity-rank ordering
- Token budget usage bar (used / max, utilization %)
- Chunk references per node
- Trace metadata: extraction strategy, hop depth, seed count

### Panel 6 — Hydrated Content

Data source: `result.hydrated_bundle`, `dump_hydrated_bundle(result.hydrated_bundle)`
- Per-node content panels with resolved chunk text
- Score annotations per node
- Edge list with relation types and weights
- Total token count
- Mode indicator (FULL / SUMMARY / REFERENCE)

### Panel 7 — Synthesis Output

Data source: `result.answer_text`, `result.synthesis_response`
- Final answer text (markdown rendering)
- Token usage (prompt_tokens, completion_tokens)
- Model identity
- Evidence context view (raw formatted bundle sent to model)

### Panel 8 — Manifold Manager

- List loaded manifolds (identity, external)
- Per-manifold stats: node count, edge count, chunk count
- Create new manifold form
- Open existing manifold (file picker for .db)
- Browse manifold contents (node list, edge list, chunk list)

---

## Wiring Patterns

### Pattern 1 — Full pipeline (simplest)

```python
from src.core.runtime import RuntimeController, PipelineConfig
from src.core.factory.manifold_factory import ManifoldFactory
from src.core.types.ids import ManifoldId
from src.core.types.enums import ManifoldRole

factory = ManifoldFactory()
controller = RuntimeController()

# Load manifolds
ext = factory.open_manifold("data/corpus.db")

# Run query
result = controller.run(
    query="How does authentication work?",
    external_manifold=ext,
    config=PipelineConfig(
        model_bridge_config=ModelBridgeConfig(
            embed_model="mxbai-embed-large",
            synthesis_model="llama3.2",
        ),
    ),
)

print(result.answer_text)
```

### Pattern 2 — Structural-only (no model server)

```python
result = controller.run(
    query="How does authentication work?",
    external_manifold=ext,
    config=PipelineConfig(skip_synthesis=True),
)

# result.degraded == True (no semantic scoring)
# result.gravity_scores uses structural (PageRank) only
# result.hydrated_bundle has full content
# result.evidence_context has formatted text
```

### Pattern 3 — Inspect intermediate artifacts

```python
from src.core.debug import (
    inspect_pipeline_result,
    dump_fusion_result,
    dump_evidence_bag,
    dump_hydrated_bundle,
    dump_virtual_scores,
)

result = controller.run(query, external_manifold=ext)

# Full pipeline summary (JSON-serializable)
summary = inspect_pipeline_result(result)

# Individual artifact inspection
fusion_info = dump_fusion_result(result.fusion_result)
bag_info = dump_evidence_bag(result.evidence_bag)
bundle_info = dump_hydrated_bundle(result.hydrated_bundle)

# Score details from VirtualManifold
vm = result.fusion_result.virtual_manifold
scores = dump_virtual_scores(vm)
```

### Pattern 4 — Custom scoring parameters

```python
result = controller.run(
    query="...",
    external_manifold=ext,
    config=PipelineConfig(
        alpha=0.8,            # Heavy structural bias
        beta=0.2,             # Light semantic
        damping=0.90,         # Higher PageRank damping
        extraction_config=ExtractionConfig(
            max_seed_nodes=5,
            max_hops=2,
            token_budget=4096,
        ),
    ),
)
```

### Pattern 5 — Query embedding without synthesis

```python
from src.core.model_bridge.model_bridge import ModelBridge, ModelBridgeConfig

result = controller.run(
    query="...",
    external_manifold=ext,
    config=PipelineConfig(
        skip_synthesis=True,  # No generation
        model_bridge_config=ModelBridgeConfig(
            embed_model="mxbai-embed-large",
            # synthesis_model left empty
        ),
    ),
)

# Semantic scoring IS active (embed_model available)
# result.semantic_scores populated
# result.degraded may be False (semantic scoring active)
# No synthesis call
```

### Pattern 6 — Direct manifold population (for ingestion UI)

```python
from src.core.types.graph import Node, Edge, Chunk
from src.core.types.ids import NodeId, EdgeId, ChunkHash, ManifoldId
from src.core.types.enums import NodeType, EdgeType
from src.core.types.bindings import NodeChunkBinding

factory = ManifoldFactory()
m = factory.create_memory_manifold(
    ManifoldId("test"), ManifoldRole.EXTERNAL,
)

# Add nodes
n1 = Node(
    node_id=NodeId("n1"), manifold_id=ManifoldId("test"),
    node_type=NodeType.CONCEPT, canonical_key="auth",
    label="Authentication",
)
m.get_nodes()[n1.node_id] = n1

# Add chunks
c1 = Chunk(chunk_hash=ChunkHash("hash1"), chunk_text="JWT tokens are...")
m.get_chunks()[c1.chunk_hash] = c1

# Link node to chunk
m.get_node_chunk_bindings().append(NodeChunkBinding(
    node_id=NodeId("n1"),
    chunk_hash=ChunkHash("hash1"),
    manifold_id=ManifoldId("test"),
))

# Add edges
e1 = Edge(
    edge_id=EdgeId("e1"), manifold_id=ManifoldId("test"),
    from_node_id=NodeId("n1"), to_node_id=NodeId("n2"),
    edge_type=EdgeType.REFERENCES,
)
m.get_edges()[e1.edge_id] = e1
```

### Pattern 7 — Using ManifoldStore for disk persistence

```python
from src.core.store.manifold_store import ManifoldStore

store = ManifoldStore()
m = factory.create_disk_manifold(
    ManifoldId("corpus"), ManifoldRole.EXTERNAL, "data/corpus.db",
)

conn = m.connection
store.add_node(conn, n1)
store.add_chunk(conn, c1)
store.link_node_chunk(conn, NodeChunkBinding(
    node_id=NodeId("n1"), chunk_hash=ChunkHash("hash1"),
    manifold_id=ManifoldId("corpus"),
))

# Read back
node = store.get_node(conn, NodeId("n1"))
all_nodes = store.list_nodes(conn, ManifoldId("corpus"))
links = store.get_node_chunk_links(conn, NodeId("n1"))
```

---

## Error Handling

### PipelineError — stage-attributed failures

```python
from src.core.runtime import PipelineError

try:
    result = controller.run(query, external_manifold=ext)
except PipelineError as e:
    print(f"Failed at stage: {e.stage}")   # "projection", "fusion", etc.
    print(f"Message: {e}")
    if e.cause:
        print(f"Root cause: {e.cause}")
except ValueError as e:
    print(f"Invalid input: {e}")           # empty query
```

### Graceful degradation

The pipeline does NOT crash when the model is unavailable:
- Missing model bridge config -> synthesis skipped, `result.degraded = True`
- `ModelConnectionError` during synthesis -> synthesis skipped gracefully
- Missing query embedding -> semantic scoring skipped, gravity uses alpha=1.0, beta=0.0
- No identity manifold -> identity projection skipped
- No external manifold -> external projection skipped

Check `result.degraded` and `result.skipped_stages` for UI warnings.

### RuntimeState inspection

The controller tracks state internally:
```python
state: RuntimeState = controller._state  # Direct access (not public API yet)
state.current_query           # Current query being processed
state.identity_manifold_id    # Active identity manifold ID
state.external_manifold_id    # Active external manifold ID
state.virtual_manifold_id     # Current VM ID
state.current_evidence_bag_id # Current bag ID
state.session_metadata        # Dict with keys:
    # "bootstrap_complete": bool
    # "current_stage": str
    # "last_successful_stage": str
    # "last_error": str (if any)
```

---

## Import Map

Quick reference for all public imports a UI needs:

```python
# Runtime (primary entry point)
from src.core.runtime import (
    RuntimeController, PipelineConfig, PipelineResult, PipelineError,
)

# Factory (manifold creation)
from src.core.factory.manifold_factory import ManifoldFactory

# Store (CRUD for disk manifolds)
from src.core.store.manifold_store import ManifoldStore

# Debug (JSON-serializable inspection)
from src.core.debug import (
    dump_virtual_scores,
    dump_projection_summary,
    dump_fusion_result,
    dump_evidence_bag,
    dump_hydrated_bundle,
    inspect_pipeline_result,
)

# Configuration dataclasses
from src.core.contracts.fusion_contract import FusionConfig
from src.core.extraction.extractor import ExtractionConfig
from src.core.hydration.hydrator import HydrationConfig
from src.core.model_bridge.model_bridge import ModelBridgeConfig

# IDs
from src.core.types.ids import (
    ManifoldId, NodeId, EdgeId, ChunkHash,
    EmbeddingId, HierarchyId, EvidenceBagId,
)

# Enums
from src.core.types.enums import (
    ManifoldRole, StorageMode, NodeType, EdgeType,
    HydrationMode, EmbeddingTargetKind,
)

# Graph entities
from src.core.types.graph import Node, Edge, Chunk, Embedding, HierarchyEntry
from src.core.types.bindings import (
    NodeChunkBinding, NodeEmbeddingBinding, NodeHierarchyBinding,
)
from src.core.types.provenance import Provenance

# Contracts (artifact types from pipeline)
from src.core.contracts.projection_contract import (
    ProjectedSlice, QueryProjectionArtifact, ProjectionMetadata,
)
from src.core.contracts.fusion_contract import FusionResult, BridgeRequest
from src.core.contracts.evidence_bag_contract import (
    EvidenceBag, EvidenceBagTrace, ScoreAnnotation, TokenBudget,
)
from src.core.contracts.hydration_contract import (
    HydratedBundle, HydratedNode, HydratedEdge,
)
from src.core.contracts.model_bridge_contract import (
    SynthesisRequest, SynthesisResponse,
    EmbedRequest, EmbedResponse, ModelIdentity,
)

# Model Bridge
from src.core.model_bridge.model_bridge import (
    ModelBridge, ModelConnectionError, ModelResponseError,
)

# Scoring (for direct use or visualization)
from src.core.math.scoring import (
    structural_score, semantic_score, gravity_score,
    spreading_activation, normalize_min_max,
)
from src.core.math.friction import detect_all_friction
from src.core.math.annotator import annotate_scores, read_score_annotation

# Runtime state (internal but inspectable)
from src.core.types.runtime_state import RuntimeState, ModelBridgeState
```

---

## Appendix: Gravity Formula

The core ranking formula:

```
G(v) = alpha * S_norm(v) + beta * T_norm(v)
```

Where:
- `S_norm(v)` = min-max normalized PageRank (structural centrality)
- `T_norm(v)` = min-max normalized cosine similarity vs. query embedding (semantic relevance)
- `alpha` = structural weight (default 0.6)
- `beta` = semantic weight (default 0.4)

When no query embedding is available:
```
G(v) = 1.0 * S_norm(v) + 0.0 * T_norm(v) = S_norm(v)
```

The gravity scores determine:
1. **Extraction seed selection** — top-N gravity nodes become BFS seeds
2. **Budget enforcement** — nodes packed in gravity-descending order
3. **Evidence bag ordering** — highest gravity nodes appear first

# System Map

Living map of the application. Documents what each system is, what it owns, what it
depends on, what depends on it, and where it is intended to expand.

**Rule**: This document is descriptive, not speculative. It records what exists now,
what each system owns now, and where it is intended to expand next — without inventing
future architecture beyond already-approved direction.

Updated each phase.

---

## Manifold Factory

**Purpose**: Create manifold instances (disk, memory, RAM) and initialise their SQLite
schema. The single entry point for manifold lifecycle creation.

**Owned files**:
- `src/core/factory/__init__.py`
- `src/core/factory/manifold_factory.py`

**Allowed to own**: Manifold creation, schema bootstrapping, connection assignment,
manifold metadata row insertion.

**Must not own**: CRUD on graph objects (that's Store), projection or fusion logic,
runtime orchestration.

**Inputs**: ManifoldId, ManifoldRole, StorageMode, optional db_path.

**Outputs**: Fully constructed BaseManifold subclass with connection handle set.

**Upstream dependencies**: BaseManifold, IdentityManifold, ExternalManifold,
VirtualManifold, ManifoldMetadata, `_schema.initialize_schema`, enums, ids.

**Downstream consumers**: RuntimeController.

**Legacy source replaced**: Manual manifold construction scattered across legacy
orchestrators. No single legacy equivalent — this consolidates creation patterns.

**Expansion notes**: May grow `delete_manifold()`, `list_manifolds()`, or
connection pool management as persistence hardens.

---

## Manifold Store

**Purpose**: Stateless typed CRUD for all graph objects in SQLite-backed manifolds.
Takes a connection and typed objects per call — owns no state itself. Validates
inputs at write boundaries and logs operations at DEBUG level.

**Owned files**:
- `src/core/store/__init__.py`
- `src/core/store/_schema.py`
- `src/core/store/manifold_store.py`

**Allowed to own**: All SQL read/write operations for nodes, edges, chunks, occurrences,
embeddings, hierarchy, metadata, provenance, and cross-layer bindings. Schema DDL.

**Must not own**: Manifold creation (that's Factory), in-memory collection management
(that's BaseManifold), projection or fusion logic.

**Inputs**: `sqlite3.Connection` + typed graph objects (Node, Edge, Chunk, etc.).

**Outputs**: Typed graph objects on reads, None on missing.

**Upstream dependencies**: All types (ids, enums, graph, provenance, bindings).

**Downstream consumers**: Projection Core, Identity Projection, External Projection,
RuntimeController.

**Legacy source replaced**: Raw SQL scattered across ContentStoreMS, CartridgeServiceMS,
and FaissIndexMS. Store centralises all SQLite interaction.

**Expansion notes**: Bulk insert methods, query-by-criteria (not just by ID),
pagination for list methods.

---

## Projection Core

**Purpose**: Shared gathering logic for identity and external projectors. Handles the
dual code path (SQLite-backed via Store, RAM via in-memory collections) in one place.

**Owned files**:
- `src/core/projection/_projection_core.py`

**Allowed to own**: Node resolution, edge filtering (closed subgraph), binding traversal,
linked object gathering, PROJECTION provenance stamping.

**Must not own**: Criteria interpretation (that's the projector wrappers), fusion,
scoring, extraction.

**Inputs**: ManifoldContract, List[NodeId], ProjectionSourceKind, optional Store + conn.

**Outputs**: Fully populated ProjectedSlice with materialised objects.

**Upstream dependencies**: ManifoldContract, ProjectedSlice, ProjectionMetadata,
ManifoldStore, all type modules, Provenance.

**Downstream consumers**: IdentityProjection, ExternalProjection.

**Legacy source replaced**: Ad-hoc subgraph selection in SeamBuilderMS and
AnchorDiscoveryMS.

**Expansion notes**: Pre-indexed binding lookups implemented (O-011 resolved). Found-vs-
requested count warning implemented. Full requested-vs-found count in
ProjectionMetadata (O-017) still open.

---

## Identity Projection

**Purpose**: Project selected slices from the identity manifold (session state, user
context, agent memory). The prompt enters identity first — this is the ordering rule.

**Owned files**:
- `src/core/projection/identity_projection.py`

**Allowed to own**: Identity-specific criteria interpretation, identity-scoped
projection policies.

**Must not own**: External corpus content, query construction, fusion, shared gathering
logic (that's Projection Core).

**Inputs**: Identity manifold + criteria dict (`node_ids` key, future: `session_id`,
`user_id`, `role`).

**Outputs**: ProjectedSlice with source_kind=IDENTITY.

**Upstream dependencies**: ProjectionContract, Projection Core, ManifoldStore, ids, enums.

**Downstream consumers**: FusionEngine (receives identity slice).

**Legacy source replaced**: Session context selection from Mind 2 session seam, chat
history windowing from Backend orchestrator.

**Expansion notes**: Session-scoped projection, user-scoped projection, role filtering.

---

## External Projection

**Purpose**: Project selected slices from the external manifold (corpus, domain
knowledge, source evidence). Operates solely on external data — isolated from identity.

**Owned files**:
- `src/core/projection/external_projection.py`

**Allowed to own**: External-specific criteria interpretation, external-scoped projection
policies (topic, embedding similarity, anchor neighborhoods).

**Must not own**: Identity/session content, query construction, fusion, shared gathering
logic (that's Projection Core).

**Inputs**: External manifold + criteria dict (`node_ids` key, future: `topic`,
`embedding_query`, `anchor_ids`).

**Outputs**: ProjectedSlice with source_kind=EXTERNAL.

**Upstream dependencies**: ProjectionContract, Projection Core, ManifoldStore, ids, enums.

**Downstream consumers**: FusionEngine (receives external slice).

**Legacy source replaced**: Anchor discovery from AnchorDiscoveryMS (FAISS top-K),
ego-graph extraction from SeamBuilderMS.

**Expansion notes**: FAISS-based anchor projection, topic cluster projection,
embedding similarity projection.

---

## Query Projection

**Purpose**: Transform a raw query string into a first-class graph participant. The query
is not a detached search string — it becomes a QUERY-typed Node with deterministic ID,
parsed intent, scope constraints, and embedding references.

**Owned files**:
- `src/core/projection/query_projection.py`

**Allowed to own**: Query node creation, query artifact construction, intent parsing,
scope constraint extraction.

**Must not own**: Manifold data projection (that's Identity/External Projection),
embedding backend/provider logic (that's Model Bridge), fusion.

**Inputs**: Criteria dict with `raw_query` (required), optional `parsed_intent`,
`scope_constraints`, `embedding_ref`. Optional `embed_fn` callback for query
embedding generation (provided by RuntimeController from ModelBridge).

**Outputs**: ProjectedSlice with a single QUERY node and QueryProjectionArtifact in
`projected_data["query_artifact"]`. When embed_fn is provided and succeeds, the
artifact carries `properties["query_embedding"]` (vector) and
`properties["query_embedding_dimensions"]` (int) for downstream semantic scoring.

**Upstream dependencies**: ProjectionContract, ProjectedSlice, QueryProjectionArtifact,
Node, NodeType.QUERY, deterministic_hash.

**Downstream consumers**: FusionEngine (receives query artifact, adds query node to VM).

**Legacy source replaced**: Query embedding generation patterns, query parsing and
structuring logic from legacy pipeline.

**Expansion notes**: Structured intent parsing, scope constraint enforcement.
Query embedding hookup is now implemented via embed_fn callback (Phase 11, O-028 resolved).

---

## Fusion Engine

**Purpose**: Combine projected manifold slices into a VirtualManifold. Creates bridge
edges between identity and external nodes, stamps FUSION provenance. This is the
assembly point — not yet reasoning, scoring, or extraction.

**Owned files**:
- `src/core/fusion/__init__.py`
- `src/core/fusion/fusion_engine.py`

**Allowed to own**: VirtualManifold population, bridge edge creation (explicit + auto),
bridge provenance, fusion result construction, auto-bridging policies.

**Must not own**: Projection (that's upstream), scoring (that's Math), extraction,
hydration, VirtualManifold class definition (that's Manifolds).

**Inputs**: Optional identity_slice, external_slice, query_artifact, bridge_requests.

**Outputs**: FusionResult containing VirtualManifold, bridge edges, ancestry, provenance.

**Upstream dependencies**: FusionContract, BridgeEdge, BridgeRequest, FusionResult,
ProjectedSlice, QueryProjectionArtifact, VirtualManifold, Edge, Node, Provenance,
deterministic_hash, EdgeType.BRIDGE.

**Downstream consumers**: Math/Scoring (scores VM nodes), Evidence Extraction (extracts
evidence bags from scored VM).

**Legacy source replaced**: Seam composition logic from Mind2Manager, gravity-driven
fusion from Mind3Manager, bridge edge creation patterns.

**Expansion notes**: Bridge request failure reporting in FusionResult (O-008 remaining).
FusionConfig bridge policy control is now implemented (W-002 resolved). VM ID is
accepted-by-design as ephemeral (W-001 resolved).

---

## Manifolds (Base + Identity + External + Virtual)

**Purpose**: The same-schema graph containers. All manifolds share identical typed
collections (nodes, edges, chunks, embeddings, hierarchy, metadata, provenance,
bindings, manifests). They differ only in role, content, and lifecycle.

**Owned files**:
- `src/core/manifolds/__init__.py`
- `src/core/manifolds/base_manifold.py`
- `src/core/manifolds/identity_manifold.py`
- `src/core/manifolds/external_manifold.py`
- `src/core/manifolds/virtual_manifold.py`

**Allowed to own**: In-memory collection storage, ManifoldMetadata, connection handle,
role enforcement, VirtualManifold's source_manifold_ids and runtime_annotations.

**Must not own**: CRUD against SQLite (that's Store), creation logic (that's Factory),
projection or fusion logic, scoring.

**Inputs**: ManifoldId, ManifoldRole, StorageMode (at construction).

**Outputs**: Typed collection accessors (get_nodes, get_edges, get_chunks, etc.).

**Upstream dependencies**: ManifoldContract, all type modules.

**Downstream consumers**: Factory (creates them), Store (reads/writes their connections),
Projection Core (reads their collections), Fusion Engine (creates VirtualManifold and
populates its collections).

**Legacy source replaced**:
- Identity: Mind 2 session seam, Backend orchestrator chat history.
- External: ContentStoreMS, NetworkX KG, FaissIndexMS, CartridgeServiceMS.
- Virtual: GravityScorerMS, SeamBuilderMS, TokenPackerMS working graphs.

**Expansion notes**: Connection lifecycle management (O-015), compact __repr__ (O-018).

---

## Math / Scoring Layer

**Purpose**: Graph scoring algorithms — structural centrality (PageRank), semantic
similarity (cosine), gravity composition (fused α·S + β·T), normalisation (min-max),
spreading activation (BFS decay), and friction detection (scoring pathology diagnosis).
Score annotations are written to VirtualManifold runtime_annotations via the annotator
bridge.

**Owned files**:
- `src/core/math/__init__.py`
- `src/core/math/scoring.py`
- `src/core/math/scoring_placeholders.py` (backward-compatible re-export shim)
- `src/core/math/friction.py`
- `src/core/math/annotator.py`

**Allowed to own**: All score computation, normalisation, graph traversal algorithms,
friction detection, score annotation writing. Pure math over graph structures — no I/O,
no persistence, no model calls.

**Must not own**: Embedding generation (that's Model Bridge), graph storage, projection,
fusion, extraction.

**Inputs**: Graph structures (duck-typed: `get_nodes()`, `get_edges()`), node embeddings,
query embeddings, score dicts.

**Outputs**: `Dict[NodeId, float]` score maps, `Dict[str, bool]` friction signals,
ScoreAnnotation objects written to VM runtime_annotations.

**Upstream dependencies**: ids (NodeId), ScoreAnnotation from evidence_bag_contract.

**Downstream consumers**: Extraction (will read ScoreAnnotation from VM). Debug
(score_dump reads annotations).

**Legacy source replaced**: PageRank on seam subgraph from GravityScorerMS, dot product
scoring on L2-normalised embeddings, gravity formula G(v) = α·S_norm(v) + β·T_norm(v),
friction detection from FrictionDetectorMS.

**Expansion notes**: Weighted PageRank using edge weights (currently unweighted).
Configurable scoring parameters via ScoringConfig dataclass. Batch scoring for multiple
query embeddings.

---

## Evidence Extraction

**Purpose**: Extract deterministic, graph-native evidence bags from a scored
VirtualManifold. Gravity-greedy seed selection, BFS expansion, token-budgeted
chunk collection, and hard-limit enforcement. The evidence bag remains a graph
structure (nodes, edges, chunk refs, hierarchy refs, score annotations) — not
yet flattened for model consumption.

**Owned files**:
- `src/core/extraction/__init__.py`
- `src/core/extraction/extractor.py`
- `src/core/extraction/extractor_placeholder.py` (backward-compatible re-export shim)

**Allowed to own**: Node ranking by gravity, seed selection, BFS expansion,
connecting edge collection, chunk and hierarchy binding collection, greedy
token-budget enforcement, hard-limit enforcement (max_nodes, max_edges, max_chunks),
EvidenceBag construction, extraction provenance, bag ID generation.

**Must not own**: Scoring (that's Math), hydration (that's Hydration), model calls
(that's Model Bridge), fusion (that's Fusion Engine), graph storage.

**Inputs**: Scored VirtualManifold (duck-typed: `get_nodes()`, `get_edges()`,
`get_chunks()`, `get_node_chunk_bindings()`, `get_node_hierarchy_bindings()`,
`get_metadata()`, `runtime_annotations`), optional ExtractionConfig.

**Outputs**: EvidenceBag with selected node IDs, edge IDs, chunk refs, hierarchy refs,
score annotations, provenance, token budget metadata, and construction trace.

**Upstream dependencies**: ids (NodeId, EdgeId, ChunkHash, HierarchyId, EvidenceBagId,
ManifoldId, deterministic_hash), enums (ProvenanceStage, ProvenanceRelationOrigin),
Provenance, EvidenceBag/EvidenceBagTrace/TokenBudget/ScoreAnnotation from
evidence_bag_contract, read_score_annotation from annotator.

**Downstream consumers**: Hydration (consumes EvidenceBag to materialise content into
HydratedBundle).

**Legacy source replaced**: Ego-graph extraction from SeamBuilderMS (radius=2 around
anchors), token-budgeted packing from TokenPackerMS (greedy max-heap, 8000 tokens),
friction detection from FrictionDetectorMS.

**Expansion notes**: Alternative extraction strategies (neighborhood_cluster, path_trace,
query_focus). Propagation-based graph activation. Advanced token packing (knapsack).
Structural graph metrics for extraction quality.

---

## Hydration

**Purpose**: Materialise evidence bag references into structured, model-readable
content. Resolve chunk text, translate edge relationships, assemble hierarchy
context, and produce deterministic HydratedBundles using the existing contract
types. Supports three modes (FULL, SUMMARY, REFERENCE) and optional budget
enforcement for the receiving model slot.

**Owned files**:
- `src/core/hydration/__init__.py`
- `src/core/hydration/hydrator.py`
- `src/core/hydration/hydrator_placeholder.py` (backward-compatible re-export shim)

**Allowed to own**: Chunk text resolution, hierarchy context resolution, edge
translation, score annotation packaging, hydration provenance, budget enforcement
(truncation), HydratedBundle construction, backward-compatible formatting helpers.

**Must not own**: Extraction (that's Extraction), scoring (that's Math), model calls
(that's Model Bridge), graph storage, fusion.

**Inputs**: EvidenceBag (from extraction), VirtualManifold (duck-typed: `get_nodes()`,
`get_edges()`, `get_chunks()`, `get_hierarchy()`), optional HydrationConfig.

**Outputs**: HydratedBundle with hydrated nodes (content, labels, types, scores,
hierarchy), translated edges (relations, weights), token totals, provenance,
budget metadata, and mode indicator.

**Upstream dependencies**: ids (NodeId, EdgeId, ChunkHash, HierarchyId, ManifoldId),
enums (HydrationMode, ProvenanceStage, ProvenanceRelationOrigin), Provenance,
HydratedBundle/HydratedNode/HydratedEdge from hydration_contract,
EvidenceBag/ScoreAnnotation from evidence_bag_contract.

**Downstream consumers**: Model Bridge (consumes HydratedBundle for synthesis via
SynthesisRequest).

**Legacy source replaced**: Content retrieval from ContentStoreMS, context string
assembly from TokenPackerMS.

**Expansion notes**: Real SUMMARY mode with model-assisted truncation (requires
Model Bridge). Hydration-level token estimation with real tokenizer. Configurable
content formatting strategies.

---

## Model Bridge

**Purpose**: Single controlled boundary for all model interaction. Mediates
embedding requests (text → vector), synthesis requests (evidence → generated
output), and token estimation. Concrete backend: Ollama HTTP. No other
subsystem talks directly to embedding or language models.

**Owned files**:
- `src/core/model_bridge/__init__.py`
- `src/core/model_bridge/model_bridge.py`

**Allowed to own**: Ollama HTTP transport, request/response transformation
(EmbedRequest → Ollama payload → EmbedResponse, SynthesisRequest → Ollama
payload → SynthesisResponse), canonical token estimation, model identity
reporting, model resolution (request.model → config model → error), error
classification (connection vs. response failures).

**Must not own**: Graph storage, projection, fusion, scoring, extraction,
hydration, prompt construction (SynthesisRequest arrives pre-built), pipeline
orchestration.

**Inputs**: EmbedRequest (texts, model, normalize, metric_type),
SynthesisRequest (evidence_context, query, system_prompt, temperature,
max_tokens), raw text (for estimate_tokens), ModelBridgeConfig.

**Outputs**: EmbedResponse (vectors, dimensions, token_counts),
SynthesisResponse (text, token counts, finish_reason), int (token estimate),
ModelIdentity (from config).

**Upstream dependencies**: ModelBridgeContract, EmbedRequest, EmbedResponse,
SynthesisRequest, SynthesisResponse, ModelIdentity from model_bridge_contract.
EmbeddingMetricType from enums. stdlib urllib.request for HTTP.

**Downstream consumers**: Query Projection (will call embed for query
embeddings), Runtime Controller (will wire synthesis into pipeline).

**Legacy source replaced**: OllamaClientMS for HTTP-based model interaction,
ReferenceEmbedPipelineMS for batch embedding, token estimation heuristic from
TokenPackerMS.

**Expansion notes**: Multi-provider abstraction (OpenAI-compatible, etc.).
Real tokenizer backend for estimate_tokens(). Streaming responses. Retry/
fallback chains. Embedding cache layer. Model auto-discovery.

---

## Runtime Controller

**Purpose**: Pipeline orchestration coordinator. Thin controller that wires all
subsystems into an executable pipeline: projection → fusion → scoring → extraction →
hydration → synthesis. Coordinates stage execution, passes typed artifacts between
stages, handles degraded mode (structural-only scoring), and provides stage-attributed
error handling.

**Owned files**:
- `src/core/runtime/__init__.py`
- `src/core/runtime/runtime_controller.py`

**Allowed to own**: Pipeline orchestration, system lifecycle, component wiring,
top-level error handling, stage-boundary logging, PipelineConfig/PipelineResult/
PipelineError types, RuntimeState lifecycle updates during execution.

**Must not own**: Any subsystem's internal logic. Controller calls subsystems but
does not implement their algorithms. Does not own projection, fusion, scoring,
extraction, hydration, formatting, or model interaction logic.

**Inputs**: Query string, optional pre-loaded manifolds with node IDs, PipelineConfig.

**Outputs**: PipelineResult with SynthesisResponse, all intermediate artifacts
(ProjectedSlice, FusionResult, EvidenceBag, HydratedBundle), scoring maps,
timing metadata, and degraded/skipped stage indicators.

**Upstream dependencies**: ManifoldFactory, ManifoldStore, RuntimeState,
QueryProjection, IdentityProjection, ExternalProjection, FusionEngine,
structural_score, semantic_score, gravity_score, annotate_scores,
extract_evidence_bag, hydrate_evidence_bag, format_evidence_bundle,
ModelBridge, SynthesisRequest, SynthesisResponse, all contract types.

**Downstream consumers**: `src/app.py` (entry point), programmatic callers.

**Legacy source replaced**: Pipeline coordination scattered across Mind2Manager,
Mind3Manager, and Backend orchestrator.

**Expansion notes**: Multi-query orchestration, streaming pipeline results,
pipeline-level caching, session management. QueryProjection embed integration
is now implemented (O-028 resolved, Phase 11) — controller wires ModelBridge.embed
as embed_fn callback into QueryProjection.

---

## Ingestion Pipeline

**Purpose**: Get data INTO manifolds. Detects file types, chunks content using tree-sitter
(code, 20+ languages) or prose splitting (text/markdown), builds graph-native objects
(nodes, edges, chunks, hierarchy, bindings, provenance), persists via ManifoldStore,
and optionally generates embeddings. The "fuel pump" — without ingestion, the system
has no content to query.

**Owned files**:
- `src/core/ingestion/__init__.py`
- `src/core/ingestion/config.py`
- `src/core/ingestion/detection.py`
- `src/core/ingestion/chunking.py`
- `src/core/ingestion/tree_sitter_chunker.py`
- `src/core/ingestion/graph_builder.py`
- `src/core/ingestion/ingest.py`

**Allowed to own**: File detection, language classification, directory walking, skip
rules, text chunking (prose + tree-sitter), RawChunk construction, graph object
creation (SOURCE/SECTION/CHUNK nodes, CONTAINS/NEXT edges, hierarchy, bindings),
ingestion-stage provenance stamping, embedding generation during ingestion, ingestion
result aggregation.

**Must not own**: ManifoldStore CRUD implementation (that's Store), manifold creation
(that's Factory), projection, fusion, scoring, extraction, hydration, model bridge
internals, prompt construction. Ingestion calls Store.add_node/add_edge/etc. but
doesn't own the SQL.

**Inputs**: File or directory path, target BaseManifold (EXTERNAL role), ManifoldStore,
optional IngestionConfig, optional embed_fn callback.

**Outputs**: IngestionResult (files_processed, files_skipped, chunks_created,
nodes_created, edges_created, embeddings_created, warnings, timing_seconds).

**Upstream dependencies**: ManifoldStore (for persistence), BaseManifold (target
manifold), all type modules (Node, Edge, Chunk, ChunkOccurrence, Embedding,
HierarchyEntry, bindings, provenance, ids, enums). tree-sitter (lazy import,
optional — falls back to prose chunker without it).

**Downstream consumers**: RuntimeController (future: auto-ingest before query),
programmatic callers, CLI tools.

**Legacy source replaced**: Chunking logic from `_TripartiteDataSTORE` — ProseChunker
(heading split + sliding window), TreeSitterChunker (4-tier language-aware parsing),
file detection (SourceFile, walk_source). All rewritten per EXTRACTION_RULES.md.
Class-based architecture converted to functional API.

**Functions provided**:
- `ingest_file(file_path, manifold, store, config, embed_fn)` — single file ingestion
- `ingest_directory(directory_path, manifold, store, config, embed_fn)` — recursive directory ingestion
- `detect_file(path)` — file detection and classification
- `walk_sources(root, config)` — recursive file walker with skip rules
- `chunk_prose(source, config)` — prose chunking (headings + sliding window)
- `chunk_tree_sitter(source, config)` — tree-sitter chunking (4 tier strategies)
- `build_graph_objects(raw_chunks, source, manifold_id, config)` — graph object creation

**Expansion notes**: Batch embedding (O-031), incremental re-ingestion with change
detection (O-032), compound document detection (O-033), directory-level hierarchy
nodes (O-034). Tree-sitter `query()` deprecation tracked in W-004.

---

## Debug / Inspection Helpers

**Purpose**: Development-time diagnostic tools for inspecting manifold state, scoring
output, pipeline artifacts, and pipeline health. Not part of the production pipeline —
purely for developer visibility.

**Owned files**:
- `src/core/debug/__init__.py`
- `src/core/debug/score_dump.py`
- `src/core/debug/inspection.py`

**Allowed to own**: Read-only inspection of manifold state, score annotations, and
pipeline artifacts. Formatting for human consumption. Structured dump functions for
all major pipeline artifacts.

**Must not own**: Score computation, annotation writing, manifold mutation, pipeline
orchestration.

**Inputs**: VirtualManifold, ProjectedSlice, FusionResult, EvidenceBag, HydratedBundle,
PipelineResult (all duck-typed via `Any` parameters).

**Outputs**: Structured summary dicts suitable for logging or REPL inspection.

**Upstream dependencies**: SCORE_ANNOTATION_KEY from annotator, ids (NodeId).

**Downstream consumers**: Developer tooling, REPL sessions, future CLI diagnostics.

**Legacy source replaced**: Ad-hoc print statements and manual inspection.

**Functions provided**:
- `dump_virtual_scores(vm)` — score annotation summary with top-10 gravity ranking
- `dump_projection_summary(projected_slice)` — source, counts, node IDs
- `dump_fusion_result(fusion_result)` — VM identity, bridge breakdown, ancestry
- `dump_evidence_bag(evidence_bag)` — bag ID, counts, token budget, top gravity nodes
- `dump_hydrated_bundle(hydrated_bundle)` — node/edge counts, tokens, content lengths
- `inspect_pipeline_result(pipeline_result)` — status, timing, artifact presence flags

**Expansion notes**: May grow a unified `inspect_manifold()` or CLI diagnostic commands.

---

## Shared Contracts Layer

Not a system — a shared interface layer that multiple systems depend on. Included here
because boundary violations often happen at the contract level.

**Owned files**:
- `src/core/contracts/__init__.py`
- `src/core/contracts/manifold_contract.py`
- `src/core/contracts/projection_contract.py`
- `src/core/contracts/fusion_contract.py`
- `src/core/contracts/evidence_bag_contract.py`
- `src/core/contracts/hydration_contract.py`
- `src/core/contracts/model_bridge_contract.py`

**Rule**: Contracts define interfaces and data shapes. They must not contain
implementation logic. Every contract type is owned by this layer, consumed by
the systems above.

---

## Shared Types Layer

Not a system — the canonical typed vocabulary used by all systems.

**Owned files**:
- `src/core/types/__init__.py`
- `src/core/types/ids.py`
- `src/core/types/enums.py`
- `src/core/types/graph.py`
- `src/core/types/provenance.py`
- `src/core/types/bindings.py`
- `src/core/types/manifests.py`
- `src/core/types/runtime_state.py`

**Rule**: Pure data containers and type definitions. No behaviour, no I/O, no storage.
Every system imports from this layer; this layer imports from nothing except stdlib.

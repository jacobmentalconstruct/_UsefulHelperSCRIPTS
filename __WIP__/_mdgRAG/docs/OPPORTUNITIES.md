# Opportunities

Enhancements, fortifications, and monitoring/logging improvements spotted during implementation.
Not bugs or debt — these are forward-looking improvements to pursue as the system matures.

Updated as new opportunities are identified. Each item tagged with priority
(**high** / **medium** / **low**) and the phase where it was spotted.

---

## Logging & Observability

### ~~O-001 · Projection pipeline has no logging~~ → ADDRESSED (Phase 10)
- **Priority**: high
- **Spotted**: Phase 4
- **Resolution**: `_projection_core.py` now has structured logging — empty node_ids warning, found-vs-requested node count warning, timing summary with node/edge/chunk/embedding counts. Logger: `src.core.projection._projection_core`.

### ~~O-002 · Fusion engine has no logging~~ → ADDRESSED (Phase 10)
- **Priority**: high
- **Spotted**: Phase 4
- **Resolution**: `fusion_engine.py` now logs all-None input warnings, skipped bridge requests (missing nodes), bridge type breakdown (explicit/canonical/label/skipped), and summary line with total bridge count. Logger: `src.core.fusion.fusion_engine`.

### ~~O-003 · ManifoldStore CRUD has no logging~~ → ADDRESSED (Phase 10)
- **Priority**: medium
- **Spotted**: Phase 3
- **Resolution**: `manifold_store.py` now has DEBUG-level logging for write operations (`add_node`, `add_edge`, `add_chunk`). Logger: `src.core.store.manifold_store`.

### ~~O-004 · JSON deserialization failures are silent~~ → ADDRESSED (Phase 10)
- **Priority**: medium
- **Spotted**: Phase 3
- **Resolution**: `_json_loads()` and `_json_loads_list()` now catch `json.JSONDecodeError`/`TypeError` and log warnings with the raw value that failed to parse. Silent data loss eliminated.

### ~~O-005 · Metrics hooks for projection/fusion timing~~ → PARTIALLY ADDRESSED (Phase 10)
- **Priority**: medium
- **Spotted**: Phase 4
- **Addressed**: `_projection_core.py` now instruments `gather_slice_by_node_ids()` with `time.perf_counter()` and logs duration in summary line.
- **Remaining**: `fusion_engine.py` and `query_projection.py` not yet timed.

---

## Input Validation & Defensive Programming

### ~~O-006 · Projection accepts empty node_ids without warning~~ → ADDRESSED (Phase 10)
- **Priority**: medium
- **Spotted**: Phase 4
- **Resolution**: `_projection_core.py` now logs a warning when `node_ids` is empty. Also warns when found count < requested count.

### ~~O-007 · Fusion accepts all-None slices~~ → ADDRESSED (Phase 10)
- **Priority**: low
- **Spotted**: Phase 4
- **Resolution**: `fusion_engine.py` now logs a warning when all inputs (identity_slice, external_slice, query_artifact) are None.

### ~~O-008 · Bridge requests not validated against VM contents~~ → PARTIALLY ADDRESSED (Phase 10)
- **Priority**: medium
- **Spotted**: Phase 4
- **Addressed**: Skipped bridge requests now emit a warning log with the missing node IDs and the skip count is tracked in the bridge summary.
- **Remaining**: Failed bridge requests not yet returned in FusionResult for programmatic access.

### ~~O-009 · Store add methods don't validate inputs~~ → ADDRESSED (Phase 10)
- **Priority**: medium
- **Spotted**: Phase 3
- **Resolution**: `add_node()`, `add_edge()`, `add_chunk()` now validate non-empty required fields with clear `ValueError` messages. Self-loop edges emit warnings. Validation occurs before SQL execution.

### O-010 · NewType IDs have no runtime validation
- **Priority**: low
- **Spotted**: Phase 4
- **Location**: `ids.py` — all NewType definitions
- **Gap**: `NodeId("")` and `NodeId(None)` are both legal at runtime. NewType is purely a type-checker hint.
- **Enhancement**: Consider optional validation wrapper functions (e.g., `validate_node_id(nid)`) for use at system boundaries. Not needed in inner loops.

---

## Performance

### ~~O-011 · Projection binding scan is O(nodes × bindings)~~ → ADDRESSED (Phase 10)
- **Priority**: high
- **Spotted**: Phase 4
- **Resolution**: `_projection_core.py` now pre-indexes bindings via `_build_binding_index()` using `defaultdict`. O(1) per-node lookup on the RAM code path. SQLite path was already indexed.

### O-012 · Auto-bridging is O(identity × external) per shared key
- **Priority**: medium
- **Spotted**: Phase 4
- **Location**: `fusion_engine.py` — `_auto_bridge_by_key()` nested loops
- **Gap**: For each shared canonical_key, creates bridges for every (identity_node, external_node) pair. If many nodes share a key, this is quadratic.
- **Enhancement**: Acceptable for now (typical key sharing is 1:1 or 1:few). If key cardinality grows, consider limiting bridges per key or scoring candidates.

### ~~O-013 · Hash truncation collision space~~ → ADDRESSED (Phase 10)
- **Priority**: low
- **Spotted**: Phase 4
- **Resolution**: `HASH_TRUNCATION_LENGTH = 16` constant added to `ids.py` with docstring documenting 64-bit collision space. All `[:16]` usages in `fusion_engine.py` and `query_projection.py` replaced with the named constant.

---

## Configuration & Constants

### ~~O-014 · Magic numbers scattered across modules~~ → PARTIALLY ADDRESSED (Phase 10)
- **Priority**: medium
- **Spotted**: Phase 4
- **Addressed**: `0.7` label fallback weight → configurable via `FusionConfig.label_fallback_weight`. `[:16]` hash truncation → `HASH_TRUNCATION_LENGTH` constant.
- **Remaining**: `[:100]` query label truncation, `1.3`/`+1` token estimation heuristic still inline.

---

## Connection & Resource Management

### O-015 · BaseManifold has no connection lifecycle management
- **Priority**: medium
- **Spotted**: Phase 3
- **Location**: `base_manifold.py` — `_connection` attribute
- **Gap**: Connection is set by factory but never formally closed. No context manager (`__enter__`/`__exit__`). Tests have to manually call `m.connection.close()`.
- **Enhancement**: Add `close()` method and `__enter__`/`__exit__` for `with` statement support. Particularly important for disk manifolds.

---

## Provenance & Traceability

### O-016 · Fusion provenance has no upstream chain
- **Priority**: medium
- **Spotted**: Phase 4
- **Location**: `fusion_engine.py` — `_make_fusion_provenance()`
- **Gap**: FUSION-stage provenance records have `upstream_ids=[]`. No link back to the BridgeRequest or auto-bridge rule that created them. Provenance chain breaks at fusion.
- **Enhancement**: Populate `upstream_ids` with the projection provenance IDs of the two bridged nodes, or with a reference to the bridge request.

### O-017 · Projection doesn't track requested-vs-found counts
- **Priority**: medium
- **Spotted**: Phase 4
- **Location**: `_projection_core.py`
- **Gap**: If 5 node IDs are requested but only 3 exist, the caller gets a slice with 3 nodes and no indication that 2 were missing. This is a silent data loss signal.
- **Enhancement**: Add `requested_count` and `found_count` to ProjectionMetadata, or a `warnings` list.

---

## Representation & Debugging

### O-018 · Dataclass repr is verbose for large objects
- **Priority**: low
- **Spotted**: Phase 4
- **Location**: All dataclasses in `types/graph.py`, `contracts/fusion_contract.py`, `contracts/projection_contract.py`
- **Gap**: Default dataclass repr shows all fields. A ProjectedSlice with 50 nodes, 200 chunks, and 300 provenance entries produces an unreadable multi-KB repr string.
- **Enhancement**: Add compact `__repr__` to key operational classes (ProjectedSlice, FusionResult, VirtualManifold) showing counts instead of contents. Leave type primitives (Node, Edge, Chunk) with full repr for debugging.

---

## Scoring & Math

### O-019 · PageRank ignores edge weights
- **Priority**: medium
- **Spotted**: Phase 5
- **Location**: `src/core/math/scoring.py` — `structural_score()`
- **Gap**: All edges contribute equally regardless of their `weight` field. Bridge edges (weight 0.7 from label fallback) should contribute less structural influence than canonical matches (weight 1.0).
- **Enhancement**: Use `edge.weight` as transition probability modifier in PageRank. Normalise outgoing weights per node.

### ~~O-020 · Scoring has no logging~~ → PARTIALLY ADDRESSED (Phase 10)
- **Priority**: high
- **Spotted**: Phase 5
- **Addressed**: `scoring.py` PageRank now logs convergence stats (iterations, node/edge counts, damping). Logger: `src.core.math.scoring`.
- **Remaining**: `friction.py` and `annotator.py` still run silently.

### O-021 · ScoringConfig dataclass for tunable parameters
- **Priority**: medium
- **Spotted**: Phase 5
- **Location**: `src/core/math/scoring.py` — function-level defaults
- **Items**:
  - `damping=0.85` — PageRank damping factor
  - `max_iterations=100` — convergence limit
  - `tolerance=1e-8` — convergence threshold
  - `alpha=0.6, beta=0.4` — gravity fusion weights
  - `decay=0.5` — spreading activation decay
- **Enhancement**: Extract to a `ScoringConfig` dataclass. Makes parameter tuning visible, grep-able, and serialisable.

### O-022 · Spreading activation has no max-activation cap
- **Priority**: low
- **Spotted**: Phase 5
- **Location**: `src/core/math/scoring.py` — `spreading_activation()`
- **Gap**: On dense graphs with many seeds, activation values could stack near 1.0 for most reachable nodes, reducing discrimination.
- **Enhancement**: Consider normalising final activation values or adding a cap/damping option for dense graphs.

---

## Extraction & Evidence Bags

### O-023 · Propagation-based graph activation for extraction
- **Priority**: medium
- **Spotted**: Phase 6
- **Location**: `src/core/extraction/extractor.py` — seed selection and expansion
- **Gap**: Current extraction uses BFS expansion from gravity-ranked seeds. An alternative approach would use spreading activation scores to select the extraction boundary, producing more semantically coherent subgraphs that follow influence paths rather than hop distance.
- **Enhancement**: Add an `activation_threshold` extraction strategy that selects nodes whose spreading activation exceeds a threshold, as an alternative to BFS hops.

### O-024 · Alias and canonicalization layer
- **Priority**: medium
- **Spotted**: Phase 6
- **Location**: Cross-cutting — affects fusion bridging, extraction, and future query resolution
- **Gap**: Label-fallback bridging (W-002) produces low-confidence bridges because there's no canonicalization layer. Extraction inherits these weak bridges. An alias registry mapping variant labels to canonical concepts would improve bridge quality and extraction precision.
- **Enhancement**: Build a `CanonicalAliasRegistry` that maps variant labels to canonical keys. Wire into fusion auto-bridging and extraction seed selection.

### O-025 · Advanced token packing (knapsack)
- **Priority**: low
- **Spotted**: Phase 6
- **Location**: `src/core/extraction/extractor.py` — `_enforce_budget()`
- **Gap**: Current greedy budget enforcement iterates nodes in gravity order and skips expensive nodes. This is O(n) and deterministic but not optimal — a knapsack approach could fit more total evidence within the same budget.
- **Enhancement**: Add an optional `knapsack` budget strategy that maximises total gravity within token budget. Keep greedy as default for speed and determinism.

### O-026 · Alternative extraction strategies
- **Priority**: medium
- **Spotted**: Phase 6
- **Location**: `src/core/extraction/extractor.py` — currently only `gravity_greedy`
- **Gap**: Different query types benefit from different extraction shapes. Factual queries need tight ego-graphs, exploratory queries need broader neighborhood clusters, reasoning queries need path traces between concepts.
- **Enhancement**: Add strategy variants: `neighborhood_cluster` (community detection), `path_trace` (shortest paths between high-gravity nodes), `query_focus` (weigh expansion toward query-adjacent nodes). Select via ExtractionConfig.

### O-027 · Structural graph metrics for extraction quality
- **Priority**: low
- **Spotted**: Phase 6
- **Location**: `src/core/extraction/extractor.py` — post-extraction
- **Gap**: No quality signal on the extracted evidence bag. Is the subgraph connected? What's its density? How much gravity was captured vs. total available?
- **Enhancement**: Add optional `ExtractionQualityMetrics` (connectivity, density, gravity coverage ratio, avg gravity of selected vs. excluded nodes). Attach to EvidenceBagTrace or return alongside the bag.

---

## Runtime & Pipeline

### ~~O-028 · QueryProjection embed integration~~ → RESOLVED (Phase 11)
- **Priority**: high
- **Spotted**: Phase 9
- **Resolution**: `QueryProjection.project()` now accepts an optional `embed_fn` callback. RuntimeController wires `ModelBridge.embed()` as the callback. Query embedding stored in `QueryProjectionArtifact.properties["query_embedding"]`. Scoring stage activates semantic path when embedding is present. Graceful fallback to structural-only gravity when embedding unavailable.

### O-029 · Pipeline-level caching
- **Priority**: medium
- **Spotted**: Phase 9
- **Location**: `src/core/runtime/runtime_controller.py` — `run()`
- **Gap**: Every `run()` call recomputes the entire pipeline from scratch. If the same manifolds and query are used, projection, fusion, and scoring could be cached.
- **Enhancement**: Add optional caching layer that detects when VM inputs are unchanged and reuses scored VM, evidence bag, or hydrated bundle from a previous run.

### O-030 · Streaming pipeline results
- **Priority**: low
- **Spotted**: Phase 9
- **Location**: `src/core/runtime/runtime_controller.py` — `run()`
- **Gap**: `run()` returns a complete PipelineResult only after all stages finish. No way to observe intermediate artifacts or stream partial results to a caller.
- **Enhancement**: Add a callback or generator-based interface that yields intermediate artifacts as each stage completes, enabling progressive UI rendering or early-stop decisions.

---

## Ingestion & Data Loading

### O-031 · Batch embedding during ingestion
- **Priority**: medium
- **Spotted**: Phase 13
- **Location**: `src/core/ingestion/ingest.py` — `_embed_chunks()`
- **Gap**: Embeddings are generated one chunk at a time via `embed_fn(text)`. For large corpora, batching multiple chunks per embed call would significantly reduce overhead (fewer HTTP round-trips for Ollama, fewer numpy operations for deterministic).
- **Enhancement**: Accept `batch_embed_fn: Callable[[List[str]], List[Sequence[float]]]` alongside or instead of single-text `embed_fn`. Accumulate chunks, embed in batches of N, create bindings from batched results.

### O-032 · Incremental re-ingestion (change detection)
- **Priority**: high
- **Spotted**: Phase 13
- **Location**: `src/core/ingestion/ingest.py` — `ingest_file()`
- **Gap**: Currently, re-ingesting a file creates duplicate nodes/edges (chunks are deduped via content-addressing, but nodes and edges are not). No mechanism to detect unchanged files and skip them, or to update the graph when a file changes (remove old nodes, add new ones).
- **Enhancement**: Before ingestion, query the manifold for a SOURCE node matching the file path. If file_hash matches, skip. If file_hash differs, remove old graph objects for that file, then re-ingest. Requires `store.delete_nodes_by_source()` or similar.

### O-033 · Compound document detection
- **Priority**: low
- **Spotted**: Phase 13
- **Location**: `src/core/ingestion/detection.py` — `detect_file()`
- **Gap**: Files like Jupyter notebooks (.ipynb), literate programming files (.Rmd, .nw), or polyglot configs contain multiple content types in one file. Currently treated as a single source_type based on extension.
- **Enhancement**: Detect compound documents and split into virtual sub-sources, each chunked with the appropriate strategy (code chunks via tree-sitter, prose chunks via heading splitter).

### O-034 · Directory-level hierarchy nodes
- **Priority**: medium
- **Spotted**: Phase 13
- **Location**: `src/core/ingestion/ingest.py` — `ingest_directory()`
- **Gap**: `ingest_directory()` ingests files individually but doesn't create DIRECTORY or PROJECT nodes to represent the folder structure. No CONTAINS edges from directory to file SOURCE nodes.
- **Enhancement**: Create NodeType.DIRECTORY nodes for each traversed directory, with CONTAINS edges forming the directory tree. Add a PROJECT root node for the top-level directory. Enables structural queries like "what files are in src/core/?".

# Development Log

Chronological record of each implementation phase, what was built, and key decisions made.

---

## Phase 1 — Graph Manifold Scaffold

**Goal**: Create the receiving scaffold for strangler-fig migration from the legacy DeterministicGraphRAG project. Module layout, contracts, base types, placeholders, and a bootable `src/app.py`.

**What was built**:
- Root project files: README.md, pyproject.toml, requirements.txt, .gitignore
- Documentation anchors: ARCHITECTURE.md, PHASE_1_SCOPE.md, EXTRACTION_RULES.md
- Entry point: src/app.py with RuntimeController bootstrap
- Contracts layer: 6 ABC/dataclass contracts (manifold, evidence_bag, hydration, projection, fusion, model_bridge)
- Shared types: ids.py (NewType wrappers), enums.py, manifests.py, runtime_state.py
- Manifold classes: BaseManifold, IdentityManifold, ExternalManifold, VirtualManifold
- Factory & Store: placeholder stubs
- Projection & Fusion: placeholder stubs
- Math / Extraction / Hydration / Model Bridge: placeholder stubs
- Runtime controller: thin bootstrap coordinator
- Adapters: empty layer with extraction tracking template
- Utils: logging_utils.py, file_utils.py
- Tests: test_imports.py (46 modules), test_scaffold_smoke.py

**Key decisions**:
- Strangler-fig pattern: extract narrow functions only, never whole scripts
- Same-schema rule: all manifolds share identical typed collections
- sys.path fix in app.py for direct script execution

**Result**: 61 files, 46/46 tests passing

---

## Phase 2 — Contracts and Core Types

**Goal**: Make the architecture's objects real with typed dataclasses, enums, and concrete contracts. Replace placeholder shapes with production-ready typed structures.

**What was built**:
- ids.py expanded: 9 NewType IDs + deterministic_hash() + make_chunk_hash()
- enums.py expanded: 12 enums (ManifoldRole, StorageMode, NodeType, EdgeType, ProvenanceStage, etc.)
- New type files: graph.py (Node, Edge, Chunk, ChunkOccurrence, Embedding, HierarchyEntry, MetadataEntry), provenance.py (Provenance), bindings.py (NodeChunkBinding, NodeEmbeddingBinding, NodeHierarchyBinding)
- manifests.py: FileManifest/Entry, ProjectManifest/Entry
- runtime_state.py: RuntimeState + ModelBridgeState
- All 6 contracts rewritten with real typed structures and ABCs
- All 4 manifold classes updated with typed collections
- test_phase2_types.py: 51 tests

**Key decisions**:
- Chunk auto-computes byte_length, char_length, token_estimate via __post_init__
- Explicit cross-layer bindings as first-class typed objects (not collapsed into dicts)
- Provenance carries stage enum and relation_origin enum for pipeline traceability

**Result**: 98/98 tests passing

---

## Phase 3 — Persistent Manifold Storage and Factory Basics

**Goal**: Make manifolds persistable via SQLite. Factory creates, store reads/writes, manifold carries connection handle.

**What was built**:
- _schema.py (NEW): Full SQLite DDL with 16 tables, WAL mode, FK enforcement, initialize_schema(), verify_schema()
- manifold_store.py (REWRITTEN): 11 write methods + 11 read methods, all typed, role-agnostic
- manifold_factory.py (REWRITTEN): create_disk_manifold(), create_memory_manifold(), create_manifold() unified dispatcher, open_manifold()
- base_manifold.py updated: _connection attribute + connection property
- test_phase3_storage.py: 42 tests across 11 test classes

**Key decisions**:
- Store is stateless: takes connection + typed objects per call
- Factory sets m._connection = conn on created manifolds
- Schema uses TEXT for all IDs (human-readable when inspecting DB)
- WAL mode for concurrent read performance
- INSERT OR REPLACE for upsert semantics, INSERT OR IGNORE for content-addressed chunks

**Result**: 140/140 tests passing

---

## Phase 4 — Projection and Fusion

**Goal**: Make the Virtual Manifold real as a fused working graph built from persistent manifolds. Implement projection (selecting records from manifolds), query projection (query becomes graph-native), and fusion (combining slices into VirtualManifold with bridge edges).

**What was built**:
- enums.py: Added NodeType.QUERY
- projection_contract.py (REWRITTEN): ProjectedSlice expanded with materialized typed objects (nodes, edges, chunks, embeddings, hierarchy, metadata, provenance, all 3 binding types); QueryProjectionArtifact expanded with query_node_id and query_node; project_by_ids() convenience method on ABC
- fusion_contract.py (REWRITTEN): BridgeRequest dataclass; FusionContract.fuse() retyped from List[Any] to explicit identity_slice/external_slice/query_artifact/bridge_requests parameters
- _projection_core.py (NEW): Shared gather_slice_by_node_ids() with dual SQLite/RAM code path — resolves nodes, finds closed-subgraph edges, gathers linked chunks/embeddings/hierarchy via bindings, stamps PROJECTION provenance
- identity_projection.py (REWRITTEN): Real projector delegating to _projection_core with IDENTITY source_kind
- external_projection.py (REWRITTEN): Real projector delegating to _projection_core with EXTERNAL source_kind
- query_projection.py (REWRITTEN): Creates QUERY-typed Node with deterministic ID, wraps in QueryProjectionArtifact
- fusion_engine.py (REWRITTEN): Mechanical fusion — ingests slices into VirtualManifold, adds query node, processes explicit BridgeRequests, auto-bridges by canonical_key match then label fallback (weight=0.7), stamps FUSION provenance
- test_phase4_projection_fusion.py: 27 tests across 13 test classes

**Bug fixed during testing**: `isinstance(nid, NodeId)` fails because NodeId is a NewType (not a real class). Simplified to always call `NodeId(nid)` since NewType callables are identity functions on strings.

**Key decisions**:
- ProjectedSlice carries actual objects so fusion doesn't need source connections
- Shared projection core handles both SQLite-backed and RAM manifolds
- Bridge creation: explicit requests + auto canonical_key match + label fallback
- Every projected object gets PROJECTION-stage provenance
- Every bridge edge gets FUSION-stage provenance with FUSED origin
- Deterministic IDs for query nodes (query-{hash[:16]}) and bridge edges (bridge-{hash[:16]})

**Result**: 168/168 tests passing (Phases 1-4)

---

## Phase 4.1 — Chunk Identity Correction

**Goal**: Fix an architectural mismatch between the chunk identity model and the hashing helper. The data model (Chunk + ChunkOccurrence in graph.py) is explicitly content-addressed, but the `make_chunk_hash()` helper was computing location-based hashes from the legacy convention.

**The mismatch**:
- graph.py Chunk docstring: "content-addressed: two chunks with the same text produce the same ChunkHash"
- ChunkOccurrence exists specifically to hold location info (source_path, chunk_index)
- But `make_chunk_hash(source_path, chunk_index)` computed `SHA256(source_path:chunk_index)` — location-based, not content-based
- This was inherited from legacy DeterministicGraphRAG which conflated chunk identity with file position

**What was changed**:
- ids.py: `make_chunk_hash(content: str) -> ChunkHash` now hashes chunk text (content-addressed)
- ids.py: `make_legacy_chunk_hash(source_path, chunk_index)` preserved for migration compatibility, marked deprecated
- ids.py: Module docstring updated to document the content-addressed chunk identity model
- ids.py: Removed misleading "Legacy context" comment from deterministic_hash()
- Phase 2 devlog entry: Removed "Deterministic IDs: SHA256 of source_path:chunk_index" which was incorrect
- test_phase2_types.py: Chunk hash tests updated to verify content-addressing; legacy helper tested separately
- test_phase3_storage.py: Updated to use content-based make_chunk_hash()

**Key decisions**:
- Content identity is the canonical model: same text = same ChunkHash, regardless of file origin
- Location tracking is ChunkOccurrence's job, not ChunkHash's
- Legacy helper preserved (not deleted) for future migration from old DeterministicGraphRAG data
- No schema changes needed — the schema already uses `chunk_hash TEXT PRIMARY KEY` which is agnostic to how the hash is computed

**Result**: 171/171 tests passing (3 new tests added for content-addressing + legacy helper)

---

## Phase 5 — Scoring and Graph Math

**Goal**: Make the VirtualManifold think. Replace placeholder scoring stubs with real algorithms: PageRank for structural importance, cosine similarity for semantic relevance, and gravity fusion to combine both into a single ranking signal. Add friction detection for scoring pathology diagnosis and an annotation bridge to write scores into VirtualManifold runtime_annotations.

**Pre-flight checks passed**:
- `VirtualManifold.runtime_annotations: Dict[NodeId, Dict[str, Any]]` exists — scores stored here
- `NodeEmbeddingBinding` provides direct node→embedding access for semantic scoring
- `ScoreAnnotation` dataclass already defined in `evidence_bag_contract.py`

**What was built**:
- scoring.py (NEW): 5 real algorithms — `normalize_min_max`, `structural_score` (PageRank power iteration), `semantic_score` (cosine similarity), `gravity_score` (fused α·S + β·T), `spreading_activation` (BFS decay propagation)
- friction.py (NEW): 3 friction detectors — `detect_island_effect` (disconnected components), `detect_gravity_collapse` (narrow spread), `detect_normalization_extrema` (all-zero scores), plus `detect_all_friction` summary
- annotator.py (NEW): Score→VM annotation bridge — `annotate_scores()` writes ScoreAnnotation to `vm.runtime_annotations[nid]["score"]`, `read_score_annotation()` reads back
- scoring_placeholders.py (REWRITTEN): Re-export shim for backward compatibility — no more NotImplementedError
- math/__init__.py (UPDATED): Public re-exports from scoring, friction, and annotator modules
- debug/__init__.py (NEW): Debug package for development-time inspection
- debug/score_dump.py (NEW): `dump_virtual_scores(vm)` extracts readable scoring summary with per-node scores and top-10 gravity ranking
- test_phase5_scoring.py (NEW): 49 tests across 9 test classes
- test_imports.py (UPDATED): Added 5 new module import checks

**Key decisions**:
- Pure Python — no numpy, no NetworkX. PageRank is power iteration, cosine is dot product. Works for sub-10K node graphs.
- Graph parameters typed as `Any` (duck typing: `get_nodes()`, `get_edges()`). Math layer depends only on `ids.NodeId` from types — no manifold imports.
- Determinism via `sorted()` iteration throughout. Same inputs → identical outputs.
- Spreading activation uses undirected adjacency — activation propagates both ways through edges.
- Annotator uses canonical key `"score"` — `vm.runtime_annotations[nid]["score"] = ScoreAnnotation(...)`. Downstream consumers know exactly where to find scores.
- scoring_placeholders.py preserved as re-export shim so old import paths still work.

**Result**: 220/220 tests passing (Phases 1-5)

---

## Phase 6 — Evidence Bag Extraction

**Goal**: Extract deterministic, graph-native evidence bags from scored VirtualManifolds. An evidence bag is a bounded contextual subgraph — the minimal set of evidence required to answer a query. It preserves graph topology (nodes, edges, chunk refs, hierarchy refs, score annotations) until hydration in Phase 7.

**What was built**:
- extractor.py (NEW): `ExtractionConfig` dataclass (6 configurable limits) and `extract_evidence_bag(vm, config)` entry point with gravity-greedy algorithm — rank nodes by gravity, select seeds, BFS expand, collect chunk/hierarchy bindings, enforce token budget with hard caps
- extractor_placeholder.py (REWRITTEN): Re-export shim for backward compatibility — no more NotImplementedError
- extraction/__init__.py (UPDATED): Public re-exports for ExtractionConfig and extract_evidence_bag
- test_phase6_extraction.py (NEW): 40 tests across 13 test classes
- test_imports.py (UPDATED): Added extraction.extractor module check

**Key decisions**:
- Single extraction module — all logic in `extractor.py` with small internal helpers. No need for separate ranker/budget/traversal files at this scale.
- VM parameter duck-typed as `Any` — same pattern as scoring.py. Avoids coupling extraction to manifold imports.
- Skip-not-break on budget overflow — when a node's chunks exceed remaining budget, skip it and try smaller nodes later in gravity order. Maximizes evidence within budget.
- Edge limit is secondary — nodes selected first, edges filtered to connecting selected nodes only, then truncated to `max_edges`. Edges cannot cause node removal.
- Chunk truncation per node — if a node's full chunk list would bust `max_chunks`, include the node with truncated chunks. Preserves graph topology even without full text.
- Deterministic bag ID — `deterministic_hash(sorted_node_ids + manifold_id)`. Same VM + same config = same bag.
- Read-only extraction — VM is never modified. Same VM can be extracted multiple times with different configs.
- Reuses existing contracts — EvidenceBag, TokenBudget, EvidenceBagTrace, ScoreAnnotation all already defined in evidence_bag_contract.py. No new contract types needed.

**Result**: 260/260 tests passing (Phases 1-6)

---

## Phase 7 — Evidence Hydration

**Goal**: Materialise evidence bag references into structured, model-readable content. Resolve chunk text, hierarchy context, and edge relationships from the VirtualManifold. Produce HydratedBundle using existing contract types with deterministic output ordering and optional budget enforcement.

**What was built**:
- hydrator.py (NEW): `HydrationConfig` dataclass and `hydrate_evidence_bag(bag, vm, config)` entry point with content resolution, hierarchy resolution, edge translation, budget enforcement, and three hydration modes (FULL, SUMMARY, REFERENCE)
- hydrator_placeholder.py (REWRITTEN): Re-export shim for backward compatibility — no more NotImplementedError
- hydration/__init__.py (UPDATED): Public re-exports for HydrationConfig, hydrate_evidence_bag, and backward-compatible helpers
- test_phase7_hydration.py (NEW): 38 tests across 13 test classes
- test_imports.py (UPDATED): Added hydration.hydrator module check

**Key decisions**:
- Single hydration module — all logic in `hydrator.py` with small internal helpers. Same pattern as scoring.py and extractor.py.
- VM parameter duck-typed as `Any` — accesses get_nodes(), get_edges(), get_chunks(), get_hierarchy(). Same pattern as extraction.
- Reuses existing contract types — HydratedBundle, HydratedNode, HydratedEdge from hydration_contract.py. Score annotations stored in HydratedNode.metadata["score"], hierarchy context in metadata["hierarchy"], provenance and budget metadata in HydratedBundle.properties.
- Node order preserved from EvidenceBag (gravity-descending from extraction). Edge sort by (source_id, target_id, edge_id) for stable secondary ordering.
- Budget enforcement truncates from end — lowest gravity nodes removed first. At least one node always kept. topology_preserved flag set to False when truncation occurs. Edges to dropped nodes are filtered out.
- Three modes: FULL resolves all chunk text, REFERENCE returns empty content with chunk hashes for traceability, SUMMARY behaves as FULL for now (real summarization requires model calls in Phase 8+).
- Defensive resolution — missing chunks, edges, or nodes in VM are silently skipped. Hydration does not crash on partial VMs.
- Read-only — neither VM nor EvidenceBag is modified. Same bag can be hydrated multiple times with different configs.
- Backward-compatible helpers: hydrate_node_payloads(), translate_edges(), format_evidence_bundle() match Phase 1 placeholder signatures and are re-exported by the shim.

**Result**: 299/299 tests passing (Phases 1-7)

---

## Phase 8 — Model Bridge

**Goal**: Replace the three `NotImplementedError` stubs in `ModelBridge` with a real Ollama HTTP backend. Make the system capable of embedding text, synthesizing answers, and estimating tokens through one controlled boundary.

**What was built**:
- model_bridge.py (REWRITTEN): `ModelBridgeConfig` dataclass, `ModelBridgeError` hierarchy (ModelBridgeError → ModelConnectionError / ModelResponseError), and `ModelBridge` class with Ollama HTTP backend — `embed()` via `/api/embed`, `synthesize()` via `/api/generate`, `estimate_tokens()` with canonical split heuristic, `get_model_identity()` from config
- model_bridge/__init__.py (UPDATED): Public re-exports for ModelBridge, ModelBridgeConfig, error classes
- test_phase8_model_bridge.py (NEW): 37 tests across 12 test classes (all mocked, no live Ollama server required)

**Key decisions**:
- Ollama HTTP as the sole Phase 8 backend. No multi-provider abstraction. Code structured so a provider layer can be extracted later but not built now.
- stdlib `urllib.request` for HTTP — no external dependencies. Pure Python constraint maintained.
- `estimate_tokens()` is bridge-canonical: uses `int(len(text.split()) * 1.3 + 1)` heuristic matching Chunk.__post_init__. Works offline, no running server needed. Future upgrade path: swap for real tokenizer.
- `get_model_identity()` is config-driven — no HTTP call to discover model metadata.
- Bridge does NOT own prompt construction. `SynthesisRequest.evidence_context` and `.query` arrive pre-built. Bridge translates to Ollama format and sends.
- Model resolution order: request.model → config model → raise ModelBridgeError. Each method resolves independently.
- Explicit error hierarchy: `ModelConnectionError` for network failures, `ModelResponseError` for data failures. Both extend `ModelBridgeError`.
- All tests mock `_http_post` via `unittest.mock.patch.object`. No live Ollama server required to pass the phase.
- Not built: streaming, multi-provider routing, retry chains, embedding caching, batch orchestration, prompt templating, structured output parsing, tokenizer plugins.

**Result**: 336/336 tests passing (Phases 1-8)

---

## Phase 9 — Runtime Pipeline Orchestration

**Goal**: Replace the no-op `RuntimeController.run()` with a real orchestration path that coordinates all completed subsystems in sequence: projection → fusion → scoring → extraction → hydration → synthesis. The controller remains a thin coordination seam — it calls subsystems but does not reimplement their algorithms.

**What was built**:
- runtime_controller.py (REWRITTEN): `PipelineConfig` dataclass (scoring weights, sub-configs, synthesis params), `PipelineResult` dataclass (all intermediate artifacts, timing, degraded flag), `PipelineError` exception with stage attribution, and `RuntimeController.run()` with 6 private stage methods (`_run_projection`, `_run_fusion`, `_run_scoring`, `_run_extraction`, `_run_hydration`, `_run_synthesis`) plus `_gather_node_embeddings` helper
- runtime/__init__.py (UPDATED): Public re-exports for PipelineConfig, PipelineResult, PipelineError
- test_phase9_pipeline.py (NEW): 37 tests across 11 test classes (all mocked, no live server)

**Key decisions**:
- Controller stays thin — each stage method is a ~10–20 line wrapper calling a subsystem API. No computation, no formatting, no scoring in the controller.
- Typed artifacts as handoffs: ProjectedSlice → FusionResult → scored VM → EvidenceBag → HydratedBundle → SynthesisResponse. No loose dicts at any boundary.
- Controller does NOT embed the query — per the system map, that responsibility belongs to QueryProjection (future O-028). Semantic scoring falls back to structural-only gravity when no embeddings are available.
- RuntimeState lifecycle tracking: existing fields (manifold IDs, evidence_bag_id, current_query) updated during execution, plus stage tracking via session_metadata (bootstrap_complete, current_stage, last_successful_stage, last_error).
- Stage-aware error handling: `PipelineError(stage, message, cause)` gives stage attribution. ModelConnectionError during synthesis → graceful degradation, not crash. All other stage failures → PipelineError with failing stage name.
- Provenance preserved, not generated — controller passes provenance-bearing artifacts through intact. Subsystems own their own provenance creation.
- Context formatting delegated to `format_evidence_bundle()` from hydrator.py — controller does not own formatting logic.
- app.py unchanged — stays as thin bootstrap entry point.
- Not built: streaming, multi-query orchestration, retry chains, caching, agent loops, query embedding generation (O-028).

**Result**: 373/373 tests passing (Phases 1-9)

---

## Phase 10 — Hardening / Stabilization / Policy Tightening

**Goal**: Fortify existing architecture without adding new features. Resolve tracked watch items, address logged opportunities, harden boundaries, add observability, and expand debug tooling.

**What was built**:
- **Packaging cleanup**: Removed `sys.path.insert` hack from `app.py`. Entry point now relies on editable install (`pip install -e .`) or module invocation (`python -m src.app`).
- **Fusion policy hardening**: Added `FusionConfig` dataclass to `fusion_contract.py` — `enable_label_fallback`, `label_fallback_weight`, `canonical_key_weight`. FusionEngine respects config throughout bridge creation. Wired through `PipelineConfig.fusion_config` into the runtime pipeline.
- **VM ID ephemeral policy**: Documented W-001 as accepted-by-design. Added `HASH_TRUNCATION_LENGTH = 16` named constant in `ids.py`, replacing magic `[:16]` across fusion_engine.py and query_projection.py.
- **Observability pass**: Added structured logging to `_projection_core.py` (node resolution counts, timing summary), `fusion_engine.py` (bridge type breakdown, auto-bridge policy decisions, ancestry parameters), `scoring.py` (PageRank convergence stats), `manifold_store.py` (DEBUG-level write logging).
- **Validation pass**: `manifold_store.py` now validates non-empty IDs before SQL execution — `add_node()`, `add_edge()`, `add_chunk()` raise `ValueError` on empty required fields. Self-loop edges emit warnings. JSON deserialization failures (`_json_loads`, `_json_loads_list`) now log warnings instead of failing silently.
- **Debug tooling expansion**: New `src/core/debug/inspection.py` with 5 structured dump functions — `dump_projection_summary()`, `dump_fusion_result()`, `dump_evidence_bag()`, `dump_hydrated_bundle()`, `inspect_pipeline_result()`. All exported from `debug/__init__.py`.
- **Performance fix**: `_projection_core.py` now pre-indexes bindings via `_build_binding_index()` for O(1) per-node lookup, replacing the O(nodes × bindings) scan on the RAM code path (O-011).
- **Timing instrumentation**: Projection core times entire `gather_slice_by_node_ids()` operation and logs duration in summary line.

**Key decisions**:
- FusionConfig is a policy object, not a feature. Makes previously-hidden defaults explicit and configurable without adding new capabilities.
- Label fallback stays enabled by default for backward compatibility. Can be disabled via `FusionConfig(enable_label_fallback=False)`.
- VM ID non-determinism (W-001) accepted-by-design: VMs are ephemeral working graphs, not persistent or cached entities.
- Debug inspection helpers are duck-typed (`Any` parameters) to avoid coupling debug tooling to specific class imports.
- No new subsystems, no architecture changes, no new contract types (FusionConfig added to existing fusion_contract.py).

**Result**: 416/416 tests passing (373 existing + 43 new Phase 10 tests)

---

## Phase 11 — Query Embedding Integration / Semantic Scoring Activation

**Goal**: Activate the semantic half of the scoring system by making QueryProjection produce a query embedding, so scoring can use both structural centrality and semantic similarity to the query. Closes O-028 — the single high-severity gap identified in the Phase 10 audit.

**What was built**:
- **QueryProjection embed_fn callback**: `QueryProjection.project()` now accepts an optional `embed_fn: Callable[[str], Sequence[float]]` keyword argument. When provided, the raw query is embedded and the vector is stored in `QueryProjectionArtifact.properties["query_embedding"]`. Embedding failure is non-fatal — logged as warning, pipeline falls back to structural-only scoring.
- **RuntimeController embed wiring**: `_run_projection()` builds an embed callback from `ModelBridge.embed()` when a bridge is available. The callback wraps `EmbedRequest(texts=[text])` → extracts first vector from `EmbedResponse.vectors`. Keeps QueryProjection decoupled from ModelBridge — it receives a capability, not a backend object.
- **Semantic scoring activation**: The existing scoring stage code in `_run_scoring()` already checked for `query_artifact.properties["query_embedding"]` — it now receives actual embeddings when a model bridge is available. Semantic scoring fires, gravity formula uses both `alpha*S + beta*T`, and score annotations include non-zero semantic components.
- **Logging and visibility**: QueryProjection logs embedding success (with dimensions), failure (with error), or skip (no embed_fn). RuntimeController logs embedding presence in projection summary. Scoring logs whether semantic path was activated or skipped.
- **EmbedFn type alias**: Exported from `query_projection.py` as `EmbedFn = Callable[[str], Sequence[float]]` for external consumers.

**Key decisions**:
- **Callback injection (Option A)**: QueryProjection receives `embed_fn`, not a full ModelBridge object. This preserves ownership boundaries — Projection doesn't know about backend/provider details, RuntimeController owns the wiring, ModelBridge remains the only embedding provider.
- **Non-fatal embed failure**: Embedding errors are caught, logged, and recorded in `artifact.properties["query_embedding_error"]`. The pipeline continues with structural-only gravity. This maintains the existing graceful degradation behavior.
- **No new contract types**: Query embedding stored in the existing `properties: Dict[str, Any]` on QueryProjectionArtifact. No new dataclass fields needed.
- **Scoring code unchanged**: The `_run_scoring()` code that reads `query_embedding` from the artifact was already written in Phase 9 — it just never received non-None input until now. Phase 11 didn't touch scoring.py at all.
- **Not bundled**: No ScoringConfig, no weighted PageRank, no alias registry, no extraction strategies, no app.py CLI. Scope stayed narrow.

**Files changed**:
- `src/core/projection/query_projection.py` (MODIFIED) — embed_fn parameter, logging, EmbedFn type alias
- `src/core/runtime/runtime_controller.py` (MODIFIED) — embed callback wiring, updated docstring, EmbedRequest import
- `tests/test_phase11_query_embedding.py` (NEW) — 29 tests across 7 test classes

**Result**: 445/445 tests passing (416 existing + 29 new Phase 11 tests)

---

## Phase 12 — Deterministic Embedding Backend

**Goal**: Wire a local deterministic BPE-SVD embedding provider behind `ModelBridge` as the default embedding backend. Users can choose between deterministic (offline, local vector lookup from pre-trained artifacts) and Ollama (HTTP, neural). Deterministic is preferred when artifacts exist; Ollama is the fallback. The training pipeline (tokenizer, co-occurrence, PMI, SVD) that produces the artifacts is NOT part of this deliverable — inference only.

**Source material**: `_STUFF-TO-INTEGRATE/deterministic_embedder/inference_engine.py :: DeterministicEmbedder`. Extracted per EXTRACTION_RULES.md — rewritten, not verbatim.

**What was built**:
- **deterministic_provider.py** (NEW): `DeterministicEmbedProvider` class — loads BPE tokenizer (JSON) and pre-trained embedding matrix (.npy), encodes text via BPE into token IDs, looks up corresponding rows in the embedding matrix, mean-pools token vectors into a single pooled vector per text. Returns `DeterministicEmbedResult` with pooled vectors, dimensions, token counts, and per-text token-level artifacts (token_ids for verbatim grounding).
- **model_bridge.py** (MODIFIED): `ModelBridgeConfig` extended with `embed_backend`, `deterministic_tokenizer_path`, `deterministic_embeddings_path`. `ModelBridge` gained backend routing (`_resolve_embed_backend`), lazy provider construction (`_get_deterministic_provider`), and deterministic embed path (`_embed_deterministic`). `embed()` routes to deterministic first, falls back to Ollama on failure. `get_model_identity()` reports embed_backend in properties.
- **test_phase12_deterministic_embed.py** (NEW): Tests across 10 test classes covering provider isolation, config fields, backend routing, deterministic embed path, Ollama embed path, fallback chain, lazy import, model identity, and end-to-end integration through QueryProjection.

**Key decisions**:
- **Provider-behind-bridge pattern**: `DeterministicEmbedProvider` is an internal implementation detail of `ModelBridge`. No new contract types, no new ABC methods. The existing `ModelBridgeContract.embed()` signature is unchanged.
- **Lazy numpy import**: numpy is imported only inside `_load_embeddings()` and `_embed_single()` in the provider, never at module level. `model_bridge.py` has zero numpy dependency. Environments without numpy can still import and use the Ollama path.
- **Empty string defaults for artifact paths**: Deterministic backend activates only when `embed_backend == "deterministic"` AND both paths are non-empty AND both files exist on disk. Otherwise falls back to Ollama. No convention paths, no auto-discovery — corpus-specific artifacts are configured explicitly.
- **Fallback chain**: deterministic -> Ollama -> error. If deterministic provider fails (missing artifacts, corrupted files, import error), the bridge logs a warning and transparently falls back to Ollama. If both fail, the error propagates to the caller (caught by QueryProjection's embed_fn error handler for graceful degradation to structural-only gravity).
- **No numpy types leak**: All numpy arrays converted to plain Python lists via `.tolist()` before leaving the provider. `EmbedResponse` contains only stdlib types.
- **model field**: Deterministic embed responses report `model="deterministic-bpe-svd"` to distinguish from Ollama responses.
- **Token artifacts**: Carried in `EmbedResponse.properties["token_artifacts"]` — list of per-text `{"token_ids": List[int]}` for verbatim grounding and traceability.

**Files changed**:
- `src/core/model_bridge/deterministic_provider.py` (NEW)
- `src/core/model_bridge/model_bridge.py` (MODIFIED)
- `tests/test_phase12_deterministic_embed.py` (NEW)
- `tests/test_imports.py` (MODIFIED — added deterministic_provider import check)
- `src/adapters/legacy_source_notes.md` (MODIFIED — extraction record)
- `requirements.txt` (MODIFIED — added numpy>=1.24.0)

---

## Phase 12.2 — Training Pipeline (BPE, Co-occurrence, NPMI, SVD)

**Goal**: Build the offline training pipeline that produces the deterministic embedding artifacts consumed by Phase 12's inference-side `DeterministicEmbedProvider`. Four stages: BPE tokenizer training → co-occurrence statistics → NPMI matrix construction → spectral compression (SVD). Extracted from legacy `_STUFF-TO-INTEGRATE/deterministic_embedder/` per EXTRACTION_RULES.md.

**What was built**:
- **bpe_trainer.py** (NEW): `BPETrainer` class — trains BPE tokenizer from corpus text. API split: `train(texts)` for training, `save(path)` for persistence, `load(path)` for reload. Configurable vocab_size and min_frequency.
- **cooccurrence.py** (NEW): `sliding_window_cooccurrence(token_streams, window_size)` and `compute_counts(sources, window_size)` — sliding window co-occurrence statistics over pre-tokenised streams. `BPETokenizer` class dropped (single-ownership violation); callers pass pre-tokenised streams.
- **npmi_matrix.py** (NEW): `build_npmi_matrix(cooccurrence_counts, token_counts, total_pairs)` — NPMI normalisation + friction transformation + sparse CSR matrix output.
- **spectral.py** (NEW): `compute_embeddings(npmi_matrix, dimensions)` — truncated SVD via `scipy.sparse.linalg.svds`. Zero-padding guard for k > effective dims (handles tiny test matrices).

**Key decisions**:
- All four modules are pure functional — no side effects, no I/O except explicit save/load.
- Lazy scipy import in spectral.py (same pattern as numpy in deterministic_provider.py).
- BPETokenizer class from legacy code was NOT extracted — it violates single-ownership (tokenization is also owned by inference-side provider). Callers pass pre-tokenised token ID streams.
- Training pipeline and inference pipeline share only the artifact format (tokenizer.json + embeddings.npy), not code.

**Files changed**:
- `src/core/training/bpe_trainer.py` (NEW)
- `src/core/training/cooccurrence.py` (NEW)
- `src/core/training/npmi_matrix.py` (NEW)
- `src/core/training/spectral.py` (NEW)
- `src/core/training/__init__.py` (NEW)
- `tests/test_imports.py` (MODIFIED — added 4 training module import checks)
- `src/adapters/legacy_source_notes.md` (MODIFIED — 4 extraction records)

**Result**: 504/504 tests passing (Phases 1-12.2)

---

## Phase 13 — Ingestion Pipeline

**Goal**: Build the ingestion pipeline — the "fuel pump" that gets data INTO manifolds. Without ingestion, the system is an engine with no way to load content. This is the critical-path blocker for the North Star (agent-driven project interface). Tree-sitter based parsing covers 20+ languages; prose fallback handles text/markdown.

**Source material**: Chunking logic extracted from `_UsefulDataCurationTools/_TripartiteDataSTORE` per EXTRACTION_RULES.md — rewritten, not verbatim. Class-based architecture converted to functional API.

**What was built**:
- **config.py** (NEW): `IngestionConfig` dataclass with chunking/skip/embedding settings. `LANGUAGE_TIERS` dict (4-tier tree-sitter classification: deep_semantic, shallow_semantic, structural, hybrid). `EXT_TO_LANGUAGE` mapping (30+ extensions). Extension sets (`CODE_EXTENSIONS`, `PROSE_EXTENSIONS`, `STRUCTURED_EXTENSIONS`, `MARKUP_EXTENSIONS`). Skip lists (`SKIP_DIRS`, `SKIP_EXTENSIONS`).
- **detection.py** (NEW): `SourceFile` dataclass (path, file_hash, source_type, language, encoding, text, lines, byte_size). `detect_file()` — reads file, detects language/type/encoding, computes SHA256 hash. `walk_sources()` — recursive directory walk with skip rules. `estimate_tokens()` — canonical token estimation.
- **chunking.py** (NEW): `RawChunk` dataclass (intermediate pipeline type). `chunk_prose()` — two-pass strategy: heading split → paragraph/sliding window within each section. Generates summary chunks when enabled. Handles empty files, no-heading files, and mixed heading structures.
- **tree_sitter_chunker.py** (NEW): `chunk_tree_sitter()` — 4-tier tree-sitter chunking. Routes to `_chunk_hierarchical` (deep_semantic), `_chunk_flat` (shallow_semantic), `_chunk_structural` (structural), `_chunk_markup` (hybrid). `FUNCTION_QUERIES`, `CLASS_QUERIES`, `IMPORT_QUERIES` for 14 languages. Lazy tree-sitter import — environments without tree-sitter fall back to prose chunker. `_fallback_line_chunker()` for parse failures.
- **graph_builder.py** (NEW): `IngestionArtifacts` dataclass. `build_graph_objects()` — translates RawChunks into graph-native objects: 1 SOURCE node per file, N SECTION nodes from heading paths, M CHUNK nodes, M Chunk objects (content-addressed via make_chunk_hash), M ChunkOccurrences, CONTAINS edges (SOURCE→SECTION→CHUNK), NEXT edges (chunk ordering), HierarchyEntry records, all bindings (NodeChunkBinding, NodeHierarchyBinding), all provenance records (stage=INGESTION).
- **ingest.py** (NEW): `IngestionResult` dataclass with `merge()` for directory aggregation. `ingest_file()` — orchestrates detection → chunking → graph build → storage → embedding. `ingest_directory()` — walks directory, calls `ingest_file()` per file, aggregates results. Chunker routing: tree-sitter for code/structured → prose for text/md → fallback line chunker. Embedding step: optional `embed_fn` callback (same pattern as QueryProjection), creates Embedding + NodeEmbeddingBinding per chunk.
- **__init__.py** (NEW): Public exports — `IngestionConfig`, `IngestionResult`, `ingest_file`, `ingest_directory`.
- **test_phase13_ingestion.py** (NEW): 70 tests across 12 test classes — TestIngestionConfig, TestLanguageTiers, TestDetection, TestWalkSources, TestEstimateTokens, TestProseChunking, TestTreeSitterChunker, TestGraphBuilder, TestIngestFile, TestIngestDirectory, TestIdempotency, TestEmbeddingIntegration.

**Key decisions**:
- Functional API pattern — free functions (`ingest_file`, `ingest_directory`) matching scoring, extraction, hydration patterns. No class hierarchy.
- `embed_fn` callback injection — same pattern as QueryProjection. Ingestion receives a capability, not a backend object. Graceful skip when no embed_fn provided.
- Lazy tree-sitter import — `tree_sitter` imported only inside functions, never at module level. Same pattern as numpy in deterministic_provider.py. Environments without tree-sitter fall back to prose chunking.
- Content-addressed chunk dedup — `make_chunk_hash(text)` produces `ChunkHash`, storage uses `INSERT OR IGNORE` for natural deduplication across files.
- RawChunk as intermediate type — sits between chunking and graph building. Not stored, not exported. Carries heading_path, semantic_depth, structural_depth, language_tier for graph construction.
- TripartiteDataSTORE extraction — class-based architecture (BaseChunker/ProseChunker/TreeSitterChunker) converted to functional. SpanRef/Chunk model replaced with RawChunk dataclass. All extractions rewritten per EXTRACTION_RULES.md.

**Files changed**:
- `src/core/ingestion/__init__.py` (NEW)
- `src/core/ingestion/config.py` (NEW)
- `src/core/ingestion/detection.py` (NEW)
- `src/core/ingestion/chunking.py` (NEW)
- `src/core/ingestion/tree_sitter_chunker.py` (NEW)
- `src/core/ingestion/graph_builder.py` (NEW)
- `src/core/ingestion/ingest.py` (NEW)
- `tests/test_phase13_ingestion.py` (NEW — 70 tests)
- `tests/test_imports.py` (MODIFIED — added 6 ingestion module import checks)
- `src/adapters/legacy_source_notes.md` (MODIFIED — 4 extraction records)
- `TODO.md` (MODIFIED — state line updated, Phase 13 items checked off)

**Result**: 574/574 tests passing (504 existing + 70 new)

---

## Phase 14 — CLI Query Path

**Goal**: Make the system usable from the command line. Replace the bootstrap-only `app.py` with a real CLI entry point with two subcommands: `ingest` (get data into manifolds) and `query` (run the full pipeline against an existing manifold). End-to-end testable without Ollama.

**What was built**:
- **app.py** (REWRITTEN): Full CLI with argparse, two subcommands, output formatting, and error handling.
  - `build_parser()` — argparse with `ingest` and `query` subparsers.
  - `cmd_ingest(args)` — creates/opens manifold DB, builds embed_fn from ModelBridge if embeddings enabled, calls `ingest_file()` or `ingest_directory()`, prints summary to stderr.
  - `cmd_query(args)` — opens manifold, loads ALL node IDs via `store.list_nodes()`, builds PipelineConfig/ModelBridgeConfig from args, runs `RuntimeController.run()`, formats output (plain/JSON/verbose).
  - `format_result_plain()` — answer text or evidence summary when synthesis skipped.
  - `format_result_json()` — `inspect_pipeline_result()` + `dump_evidence_bag()` as JSON.
  - `format_verbose()` — stage timing, scoring summary, top-5 gravity, evidence bag stats.
  - `handle_error()` — stage-attributed PipelineError messages, ModelConnectionError, FileNotFoundError.
  - Helper functions: `_build_embed_fn()`, `_load_all_node_ids()`, `_build_model_bridge_config()`, `_sanitize_manifold_id()`.

**Key decisions**:
- **argparse only** — pure Python constraint, no click/typer. Subcommand pattern with `set_defaults(func=...)`.
- **Default skip_synthesis=True** — CLI works out of the box without Ollama. Synthesis opt-in via `--synthesis-model MODEL`.
- **Load ALL node IDs for projection** — `RuntimeController.run()` requires explicit `external_node_ids`. CLI reads all nodes from the manifold. Simple and correct for the common case.
- **stdout for results, stderr for logs** — Unix convention. `python -m src.app query ... > result.json` works.
- **Rewrite app.py** — it was 35 lines of bootstrap. Making it the CLI entry point is the natural evolution.
- **No REPL mode** — one query per invocation. Keep it simple.
- **Two existing tests updated**: `test_scaffold_smoke.py::test_app_main_returns_zero` → `test_app_main_no_subcommand_returns_one` (main now returns 1 with no args). `test_phase10_hardening.py::test_app_no_sys_import` → `test_app_no_sys_path_manipulation` (sys import is now valid for stderr).

**Files changed**:
- `src/app.py` (REWRITTEN — CLI entry point with ingest/query subcommands)
- `tests/test_phase14_cli.py` (NEW — 41 tests across 7 test classes)
- `tests/test_scaffold_smoke.py` (MODIFIED — updated main() test for new CLI behavior)
- `tests/test_phase10_hardening.py` (MODIFIED — updated sys import test to sys.path test)
- `TODO.md` (MODIFIED — state line updated, Phase 14 items checked off)

**Result**: 622/622 tests passing (574 existing + 41 new + 7 existing updated)

---

## Phase 15 — Web UI (2026-03-11)

**Goal**: Build an interactive web UI for exploring pipeline results, visualizing the graph, and inspecting all intermediate artifacts. Replace CLI-only workflow with a browser-based interface.

**What was built**:
- **Technology**: FastAPI + single-page HTML + Cytoscape.js (CDN). No build step, no npm.
- **`src/ui/server.py`** (NEW): FastAPI application with REST endpoints.
  - `create_app(default_db)` — factory function returning configured FastAPI app.
  - `POST /api/query` — runs full pipeline, returns JSON with overview, evidence, graph, scores, hydrated bundle, timing.
  - `POST /api/ingest` — ingests files/directories into a manifold DB.
  - `GET /api/manifold` — returns manifold metadata and node/edge counts.
  - `GET /api/manifold/graph` — returns Cytoscape.js-compatible graph JSON.
  - `GET /api/health` — health check.
  - `serialize_graph()` — converts manifold nodes/edges to Cytoscape.js format with gravity coloring. Handles both RAM and disk manifolds via optional ManifoldStore fallback.
  - `_build_query_response()` — assembles full response using `inspect_pipeline_result()`, `dump_evidence_bag()`, `dump_hydrated_bundle()`, and `serialize_graph()`.
  - Exception handlers for PipelineError (500 with stage), FileNotFoundError (404), ValueError (400).
  - `start(host, port, default_db)` — launches uvicorn server.
- **`src/ui/static/index.html`** (NEW): Single-page dark-theme UI.
  - Header bar: DB path input, Load button, Ingest button, manifold status.
  - Query panel: text input, Run button, alpha/beta controls, skip synthesis checkbox.
  - Results area: answer text or evidence summary, expandable timing/scores/evidence sections.
  - Graph panel: Cytoscape.js force-directed layout, nodes sized/colored by gravity, bridge edges dashed/orange, click-to-inspect node detail popup.
  - Score table: sortable by gravity/structural/semantic columns.
  - Pipeline status bar: stage pill indicators (done/skipped), total time, degraded warnings.
  - Ingest modal: source path, DB path, skip embeddings toggle.
- **`src/app.py`** (MODIFIED): Added `serve` subcommand.
  - `_add_serve_parser()` — argparse for `--port`, `--host`, `--db`.
  - `cmd_serve(args)` — checks UI deps, lazy-imports server, starts it.
  - `_check_ui_deps()` — verifies fastapi/uvicorn are installed.

**Key decisions**:
- **FastAPI + Cytoscape.js** — graph visualization is critical for a Graph RAG system. Single HTML file with CDN = no frontend toolchain. FastAPI provides built-in TestClient for testing.
- **Lazy-imported dependencies** — fastapi/uvicorn only imported when `serve` subcommand runs. Matches tree-sitter pattern. Project stays "pure Python" for non-UI usage.
- **ManifoldStore fallback in serialize_graph()** — disk manifolds have empty in-memory collections when reopened. Function detects this and reads via store. RAM manifolds (VirtualManifold from pipeline) use get_nodes()/get_edges() directly.
- **serve subcommand** — natural evolution from CLI. `python -m src.app serve --db ./manifold.db` starts the UI.
- **All debug dump functions reused** — `inspect_pipeline_result()`, `dump_evidence_bag()`, `dump_hydrated_bundle()` produce JSON-serializable dicts. No new serialization code needed.

**Files changed**:
- `src/ui/__init__.py` (NEW — package marker)
- `src/ui/server.py` (NEW — FastAPI application, ~340 lines)
- `src/ui/static/index.html` (NEW — single-page UI, ~490 lines)
- `src/app.py` (MODIFIED — added serve subcommand, ~30 lines added)
- `tests/test_phase15_ui.py` (NEW — 42 tests across 8 test classes)
- `tests/test_imports.py` (MODIFIED — added src.ui, src.ui.server, src.core.debug.inspection)
- `TODO.md` (MODIFIED — state line updated, Phase 15 items checked off)

**Result**: 667/667 tests passing (622 existing + 42 new Phase 15 + 3 new import tests)

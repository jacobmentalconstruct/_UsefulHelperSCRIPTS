# Graph Manifold — Master TODO

Everything that remains to be done, in verbose detail.
Iterate through these with the builder when ready.

**Current state**: Phase 15 complete, 674 tests passing, 0 test failures.
Pipeline fully wired from projection through synthesis. Semantic scoring active.
Deterministic BPE-SVD embedder wired behind ModelBridge with diagnostic UI and
standalone showcase demo (BDVE). Training pipeline functional with file picker.
Ingestion pipeline complete (tree-sitter + prose chunking, graph construction, embedding).
CLI query path complete (ingest + query + serve subcommands with argparse).
Web UI complete (FastAPI + Cytoscape.js single-page app with file browser).

**Next up — PAUSED**: Phase 16 "Hardening II" (bundled Phases 16+17+19). Full plan saved at
`.claude/plans/delightful-noodling-engelbart.md`. Ready to resume implementation.

---

## Status Key

- [ ] Not started
- [~] Partially done / known foundation exists
- [x] Complete

---

## PHASE 13 — Ingestion Pipeline

**Why**: There is currently no way to get data INTO manifolds except by manually constructing Node/Edge/Chunk objects in Python. Without ingestion, the system is an engine with no fuel pump.

**What needs to happen**:

- [x] **13.1 · Text file ingestion** — `ingest_file()` reads any text file, chunks it, creates CHUNK nodes with content-addressed ChunkHash, wires NodeChunkBindings. Stores into External manifold via ManifoldStore.

- [x] **13.2 · Chunking strategy** — Tree-sitter 4-tier language-aware chunking (20+ languages) + prose chunker (ATX heading split + sliding window). Configurable via `IngestionConfig` dataclass.

- [x] **13.3 · Source file node creation** — SOURCE nodes per file, SECTION nodes from heading paths, CONTAINS edges SOURCE → SECTION → CHUNK.

- [x] **13.4 · Hierarchy entry creation** — HierarchyEntry records with semantic/structural depth, NodeHierarchyBindings, path_label breadcrumbs.

- [x] **13.5 · Embedding generation during ingestion** — Optional `embed_fn` callback per chunk with context prefix. Creates Embedding + NodeEmbeddingBinding. Graceful skip on failure.

- [x] **13.6 · Provenance stamping** — All objects get Provenance with stage=INGESTION, source_document, parser_name, timestamp.

- [x] **13.7 · Directory / project ingestion** — `ingest_directory()` walks trees, creates PROJECT and DIRECTORY nodes, CONTAINS edges for directory structure.

- [x] **13.8 · Ingestion idempotency** — Content-addressed chunks dedup via INSERT OR IGNORE. Re-ingestion of same file succeeds without crashes or duplicates.

**Resolved**: Functional API (`ingest_file`, `ingest_directory`). Lives in `src/core/ingestion/`. Tree-sitter for code + prose chunker for text/markdown.

---

## PHASE 14 — CLI Query Path

**Why**: `app.py` is currently bootstrap-only — it instantiates RuntimeController, calls `bootstrap()`, and exits. There is no way to actually run a query from the command line. The RuntimeController.run() API exists but has no CLI caller.

**What needs to happen**:

- [x] **14.1 · CLI argument parsing** — argparse with `ingest` and `query` subcommands. `--source`, `--db`, `--query`, `--alpha`, `--beta`, `--skip-synthesis`, `--synthesis-model`, `--json`, `--verbose`, `--embed-backend`, `--tokenizer-path`, `--embeddings-path`, `--skip-embeddings`, `--max-chunk-tokens`.

- [x] **14.2 · Manifold loading** — `ManifoldFactory.open_manifold(db_path)` for existing DBs, `create_disk_manifold()` for new ones. Loads all node IDs via `store.list_nodes()` for projection.

- [x] **14.3 · Config loading** — CLI args override PipelineConfig defaults directly (--alpha, --beta, --skip-synthesis). ModelBridgeConfig built from --embed-backend, --ollama-url, --synthesis-model.

- [x] **14.4 · Pipeline execution** — `RuntimeController.run()` called with loaded manifold and all node IDs. Synthesis skipped by default, enabled via `--synthesis-model`.

- [x] **14.5 · Output formatting** — Plain text (answer or evidence summary), `--json` (inspect_pipeline_result + dump_evidence_bag), `--verbose` (stage timing, scoring summary, evidence bag stats to stderr).

- [x] **14.6 · Error handling** — PipelineError (stage attribution), ModelConnectionError, FileNotFoundError, ValueError all caught with human-readable messages. `--verbose` adds traceback.

**Resolved**: argparse only (no external deps). Two subcommands: `ingest` and `query`. No REPL mode. Default skip_synthesis=True. stdout for results, stderr for logs.

---

## PHASE 15 — UI Interface

**Why**: The user explicitly requested a UI. Currently CLI-only. The `docs/UI_WIRING.md` document describes all API surfaces, data flows, and suggested panel layouts for a UI.

**What needs to happen**:

- [x] **15.1 · Technology selection** — Web-based: FastAPI + single-page HTML + Cytoscape.js (CDN). Dependencies lazy-imported like tree-sitter.

- [x] **15.2 · Query panel** — Text input, Run button, alpha/beta number inputs, skip synthesis checkbox.

- [x] **15.3 · Pipeline status panel** — Stage pill indicators (done/skipped), total time, degraded warnings.

- [x] **15.4 · Graph visualization panel** — Cytoscape.js force-directed graph. Nodes sized and colored by gravity. Bridge edges dashed/orange. Click node for detail popup.

- [x] **15.5 · Score explorer panel** — Sortable table (gravity, structural, semantic). Click column headers to sort.

- [x] **15.6 · Evidence bag inspector panel** — Expandable section with bag ID, node/edge/chunk counts, token budget, top gravity nodes.

- [x] **15.7 · Hydrated content panel** — Hydration summary included in query response JSON (dump_hydrated_bundle).

- [x] **15.8 · Synthesis output panel** — Answer text displayed when synthesis runs; evidence summary when skipped.

- [x] **15.9 · Manifold manager panel** — Header bar with DB path input, Load button, Ingest modal with source/db path controls.

- [x] **15.10 · API layer** — FastAPI REST: GET /, GET /api/health, POST /api/query, POST /api/ingest, GET /api/manifold, GET /api/manifold/graph.

---

## PHASE 16 — Hardening II (Weighted PageRank + ScoringConfig + Connection Lifecycle)

**Status**: ⏸ PLANNED — full implementation plan saved, ready to resume.

**Bundles**: Phases 16 (O-019), 17 (O-021), 19 (O-015) into one hardening pass.

**What needs to happen**:

### 16A · Weighted PageRank (was Phase 16)

- [ ] **16.1 · Modify `structural_score()` in `scoring.py`** — Use `edge.weight` as transition probability modifier. Normalize outgoing weights per node so they sum to 1.0. Preserve all existing edge cases (empty graph, single node, dangling nodes, disconnected components).

- [ ] **16.2 · Backward compatibility** — Default behavior should be identical when all edges have weight=1.0 (current default). Only diverges when edges have non-uniform weights.

- [ ] **16.3 · Test coverage** — Add tests proving that weight=0.5 edges carry half the structural influence. Verify bridge edges (weight 0.7 from label fallback) produce lower structural influence than canonical matches (weight 1.0).

### 16B · ScoringConfig Dataclass (was Phase 17)

- [ ] **16.4 · Create ScoringConfig dataclass** — Fields: `damping` (0.85), `max_iterations` (100), `tolerance` (1e-8), `alpha` (0.6), `beta` (0.4), `decay` (0.5 for spreading activation).

- [ ] **16.5 · Wire into scoring functions** — Each function accepts optional ScoringConfig and falls back to field defaults. No behavioral change when ScoringConfig is not provided.

- [ ] **16.6 · Wire into PipelineConfig** — Add `scoring_config: Optional[ScoringConfig] = None` to PipelineConfig. RuntimeController reads it in `_run_scoring()`. Existing direct fields kept as legacy aliases.

### 16C · Connection Lifecycle (was Phase 19)

- [ ] **16.7 · Add `close()` method to BaseManifold** — Closes the SQLite connection if present. No-op for RAM manifolds. Safe to call multiple times.

- [ ] **16.8 · Add `__enter__` / `__exit__`** — Support `with ManifoldFactory.open_manifold("db") as m:` pattern.

- [ ] **16.9 · Update callers** — app.py CLI commands and server.py endpoints use try/finally to close manifolds.

**Location**: `scoring.py`, `runtime_controller.py`, `base_manifold.py`, `app.py`, `server.py`.

---

## PHASE 18 — Real SUMMARY Hydration Mode

**Why**: `HydrationMode.SUMMARY` currently behaves identically to FULL — it was stubbed in Phase 7 with a comment that real summarization requires model calls. Now that ModelBridge exists, SUMMARY can produce compressed evidence.

**What needs to happen**:

- [ ] **18.1 · SUMMARY mode implementation** — When `HydrationConfig.mode == SUMMARY`, call `ModelBridge.synthesize()` per-node (or batched) to produce condensed summaries of chunk text. Store summaries as `HydratedNode.content` instead of raw chunk text.

- [ ] **18.2 · Token savings tracking** — Record original vs. summarized token counts in HydratedBundle.properties so the UI can show compression ratio.

- [ ] **18.3 · Fallback** — If ModelBridge is unavailable, fall back to FULL mode with a warning (same graceful degradation pattern as synthesis).

**Dependencies**: ModelBridge.synthesize() (done). May want a dedicated summary prompt template.

---

## PHASE 19 — *(Merged into Phase 16 Hardening II)*

---

## PHASE 20 — Multi-Provider Model Bridge

**Why**: Currently locked to Ollama. Future needs: OpenAI API, Anthropic Claude, local HuggingFace models, etc.

**What needs to happen**:

- [ ] **20.1 · Provider abstraction** — Extract an interface/ABC that ModelBridge implements. New providers implement the same interface.

- [ ] **20.2 · Provider registry** — Select provider by config string (e.g., `provider: "ollama"`, `provider: "openai"`).

- [ ] **20.3 · At least one additional provider** — OpenAI-compatible API is the most useful second target.

- [ ] **20.4 · Provider-specific config** — Each provider has its own config shape (API keys, base URLs, model names, etc.).

**Dependencies**: ModelBridge (done), ModelBridgeConfig (done), ModelBridgeContract ABC (done).

---

## PHASE 21 — Advanced Extraction Strategies (O-026)

**Why**: Currently only `gravity_greedy` (BFS from top-gravity seeds). Different query types benefit from different extraction shapes.

**What needs to happen**:

- [ ] **21.1 · `neighborhood_cluster` strategy** — Community detection to extract dense subgraph neighborhoods rather than ego-graphs.

- [ ] **21.2 · `path_trace` strategy** — Find shortest paths between high-gravity nodes. Good for reasoning queries that need logical chains.

- [ ] **21.3 · `query_focus` strategy** — Bias expansion toward query-adjacent nodes using spreading activation scores.

- [ ] **21.4 · Strategy selection via ExtractionConfig** — Add `strategy: str = "gravity_greedy"` field to ExtractionConfig.

**Location**: `src/core/extraction/extractor.py`

---

## PHASE 22 — Pipeline Caching (O-029)

**Why**: Every `run()` call recomputes everything from scratch. If the same manifolds and query repeat, projection/fusion/scoring could be cached.

**What needs to happen**:

- [ ] **22.1 · Cache key computation** — Hash of manifold contents + query + config = cache key.

- [ ] **22.2 · Cache layer** — LRU or TTL cache for scored VirtualManifold, EvidenceBag, HydratedBundle.

- [ ] **22.3 · Cache invalidation** — When manifold contents change, cached results for that manifold are invalidated.

- [ ] **22.4 · Optional** — Cache should be opt-in via PipelineConfig flag.

---

## PHASE 23 — Streaming Pipeline Results (O-030)

**Why**: `run()` returns only after all stages complete. No way to observe intermediate artifacts progressively. Important for UI responsiveness.

**What needs to happen**:

- [ ] **23.1 · Callback interface** — `run()` accepts optional `on_stage_complete(stage_name, artifact)` callback.

- [ ] **23.2 · Generator variant** — `run_stream()` that yields `(stage_name, artifact)` tuples as each stage completes.

- [ ] **23.3 · Early-stop** — Caller can signal stop after any stage (e.g., stop after scoring to inspect scores without running extraction).

---

## Open Opportunities (not phased yet)

These are tracked in `docs/OPPORTUNITIES.md` and may be rolled into phases above or addressed ad-hoc:

- [~] **O-005** · Fusion/query projection timing instrumentation (projection core done, fusion/query not yet)
- [~] **O-008** · Failed bridge requests not returned in FusionResult for programmatic access
- [ ] **O-010** · NewType IDs have no runtime validation (consider boundary validators)
- [ ] **O-012** · Auto-bridging is O(identity × external) per shared key (quadratic risk)
- [~] **O-014** · Magic numbers: `[:100]` query label truncation, `1.3`/`+1` token heuristic still inline
- [ ] **O-016** · Fusion provenance has no upstream chain (upstream_ids empty)
- [ ] **O-017** · Projection doesn't track requested-vs-found counts
- [ ] **O-018** · Dataclass repr is verbose for large objects (compact __repr__ needed)
- [~] **O-020** · friction.py and annotator.py still run silently (scoring.py logging done)
- [ ] **O-022** · Spreading activation has no max-activation cap
- [ ] **O-023** · Propagation-based graph activation for extraction
- [ ] **O-024** · Alias and canonicalization layer
- [ ] **O-025** · Advanced token packing (knapsack)
- [ ] **O-027** · Structural graph metrics for extraction quality

---

## Orphaned / Housekeeping Items

These are cleanup items identified during the Phase 10 audit:

- [ ] **Orphaned ABCs** — `EvidenceBagContract` and `HydrationContract` have no implementations. Both subsystems went functional (free functions) instead of OOP. Options: remove the ABCs, or wrap the functions in classes that implement them.
- [ ] **16 unused imports** — Cosmetic. Identified in Phase 10 audit. Low priority.
- [ ] **app.py is bootstrap-only** — No query path. Addressed by Phase 14 above.
- [ ] **Placeholder re-export shims** — `scoring_placeholders.py`, `extractor_placeholder.py`, `hydrator_placeholder.py` exist only for backward-compat import paths. Can be removed when confident no legacy imports remain.

---

## Priority Order (suggested)

| Priority | Phase | Why |
|----------|-------|-----|
| ~~**1 (critical)**~~ | ~~Phase 13 — Ingestion~~ | ~~Done~~ |
| ~~**2 (critical)**~~ | ~~Phase 14 — CLI Query~~ | ~~Done~~ |
| ~~**3 (high)**~~ | ~~Phase 15 — UI Interface~~ | ~~Done~~ |
| **4 (medium) ⏸** | Phase 16 — Hardening II (16+17+19 bundled) | Planned, paused — ready to resume |
| **5 (medium)** | Phase 18 — SUMMARY Hydration | Feature completeness |
| **6 (low)** | Phase 20 — Multi-Provider Bridge | Flexibility |
| **7 (low)** | Phase 21 — Extraction Strategies | Advanced feature |
| **8 (low)** | Phase 22 — Pipeline Caching | Performance optimization |
| **9 (low)** | Phase 23 — Streaming Pipeline | UX enhancement |

---

## North Star — Agent-Driven Project Interface

The long-term target for Graph Manifold is a **general-purpose agent interface for working on any software project**. Not a self-aware system — a project-aware tool where the project under development is loaded into the manifold and an AI agent reasons over it, proposes changes, and executes them in a controlled loop.

**The model**:

- **External manifold** = the target project (code, docs, configs, tests — any repo)
- **Identity manifold** = the agent's working context (session state, prior queries, accumulated understanding)
- **Query pipeline** = the agent asks questions about the project and gets gravity-ranked, topology-preserving evidence bags grounded back to source
- **Sandbox execution** = the agent proposes changes against a **sandboxed copy** of the project, never touching live state
- **Version-tagged diffs** = changes are captured as graph deltas against a tagged manifold version. Each delta carries provenance linking it to the version it branched from
- **Approval gate** = human reviews the diff. If accepted, the delta applies as a new versioned state in the project's manifold history. If rejected, the sandbox VM is destroyed

**Key architectural properties**:

- The manifold versions itself using its own primitives — content-addressed chunks + provenance chains give Merkle-like history without needing git
- The sandbox is just another Virtual manifold — ephemeral, derived, disposable
- The agent is not special-cased. It uses the same `RuntimeController.run()` pipeline as any other consumer. The "self-diagnosis" case (agent working on Graph Manifold's own code) is an emergent property of pointing the tool at its own repo

**Context isolation principle**:

Every manifold load is a deliberate, bounded act. The agent has no ambient self-awareness, no residual context bleeding between projects, and no implicit cross-referencing between separate loads. When the agent works on project X, it knows project X — nothing else.

- Loading the agent's own repo is not "self-awareness." It is the same retrieval pipeline processing data that happens to be its own source code. The agent does not get special access, special treatment, or special framing because the target is itself.
- Cross-project context (e.g., comparing two repos, or letting the agent reference its own architecture while working on another project) is only permitted through **explicit, intentional fusion** — never through leakage, ambient state, or accumulated memory across sessions.
- Automated self-curation cycles (learning, cleanup, optimization of its own manifolds) are valid use cases, but must always be **intentional acts** — triggered deliberately, scoped clearly, and never running as invisible background processes that the user hasn't chosen to enable.
- The system is honest about what it is at every level. The agent is a tool. The manifold is a data structure. The graph is a representation. None of these pretend to be more than what they are.

**Theoretical grounding**: See `docs/TRANSLATION_THEORY.md` — ingestion as translation between representational bases, the round-trip guarantee (source → relational space → grounded reconstruction), and the manifold as a "translation lattice of meaning spaces" rather than a database.

**Prerequisites**: Phase 13 (Ingestion), Phase 14 (CLI), Phase 15 (UI), manifold versioning/diff system (not yet phased).

---

*Last updated: Phase 15 complete, Phase 16 planned/paused (674 tests passing)*

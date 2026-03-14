# Architecture

## Three-Manifold Model

The system operates on three manifolds that share **the same graph-native schema**.
The schema is identical across all three — they differ only in role, content
ownership, and lifecycle.

### Same-Schema Rule

Every manifold stores the same structural collections:
- **Nodes** — typed vertices in the knowledge graph (11 types across 4 categories)
- **Edges** — typed directed relations between nodes (11 types across 5 categories)
- **Chunks** — content-addressed text segments with deterministic IDs (SHA256 of content)
- **Embeddings** — vector representations bound to nodes or chunks
- **Hierarchy** — structural containment (file → section → chunk)
- **Cross-layer bindings** — explicit typed links: node↔chunk, node↔embedding, node↔hierarchy
- **Metadata** — owner-bound key/value pairs on any element
- **Provenance** — lineage records tracing every element to its origin, transformation stage, and upstream dependencies

No manifold has a special schema. No manifold gets extra fields. The
architectural invariant is: traversal logic written for one manifold works
identically against any other manifold.

### Manifold Roles

**Identity Manifold**
- Owns session memory, user context, agent/role graphs
- Population is identity-side only
- Persists across sessions (disk-backed or session-scoped)

**External Manifold**
- Owns the external corpus: source documents, domain knowledge
- Content is ingested from outside sources
- Persists independently of sessions (SQLite disk-backed)

**Virtual Manifold**
- Ephemeral, created at query time by fusing identity and external projections
- Runtime-only score annotations are permitted here (structural, semantic, gravity)
- Destroyed after synthesis is complete
- Clearly marked as temporary/derived
- VM IDs are non-deterministic by design (timestamp-seeded, ephemeral)

## Evidence Bag

An evidence bag is a **contextual subgraph** — not a flat text bundle. It
contains:
- Node IDs from the virtual manifold (gravity-ranked)
- Edge IDs preserving topological relationships (closed subgraph)
- Chunk references with content payloads per node
- Hierarchy references per node
- Score annotations (gravity, semantic, structural) per node
- Provenance references tracing each element to its source manifold
- Token budget metadata (used, max, utilization)
- Construction trace (strategy, seed count, hop depth, selected/candidate counts)

## Processing Flow

The full pipeline executes six stages in sequence. Each stage produces typed
artifacts consumed by the next:

```
Query + Manifolds
    │
    ▼
1. PROJECTION  ─── query → QueryProjectionArtifact (with optional query embedding)
    │               identity manifold → ProjectedSlice (IDENTITY)
    │               external manifold → ProjectedSlice (EXTERNAL)
    ▼
2. FUSION  ─────── slices + query artifact → FusionResult
    │               Creates VirtualManifold, ingests all objects,
    │               builds bridge edges (explicit, canonical_key, label-fallback)
    ▼
3. SCORING  ────── VirtualManifold → scored VM
    │               structural_score() — PageRank via power iteration
    │               semantic_score()  — cosine similarity vs query embedding
    │               gravity_score()   — G(v) = α·S_norm(v) + β·T_norm(v)
    │               Scores written to VM.runtime_annotations
    ▼
4. EXTRACTION  ─── scored VM → EvidenceBag
    │               Gravity-greedy seed selection → BFS expansion →
    │               token-budgeted chunk collection → hard-limit enforcement
    ▼
5. HYDRATION  ──── EvidenceBag + VM → HydratedBundle → formatted context string
    │               Resolves chunk text, edge relations, hierarchy context,
    │               score annotations. Three modes: FULL, SUMMARY, REFERENCE
    ▼
6. SYNTHESIS  ──── evidence context + query → SynthesisResponse
                    Formatted bundle passed to ModelBridge.synthesize()
                    Returns generated answer text
```

### Gravity Formula

The core ranking signal that drives extraction:

```
G(v) = α · S_norm(v) + β · T_norm(v)
```

Where:
- `S_norm(v)` = min-max normalized PageRank (structural centrality)
- `T_norm(v)` = min-max normalized cosine similarity vs query embedding (semantic relevance)
- `α` = structural weight (default 0.6)
- `β` = semantic weight (default 0.4)

When no query embedding is available (no model bridge), gravity falls back to
structural-only: `G(v) = S_norm(v)`.

### Graceful Degradation

The pipeline degrades gracefully at multiple levels:
- **No model bridge** → semantic scoring skipped, synthesis skipped
- **Embed failure** → semantic scoring skipped, structural-only gravity
- **No identity manifold** → identity projection skipped, external-only fusion
- **No external manifold** → external projection skipped, identity-only fusion
- **Synthesis failure** → answer_text empty, all intermediate artifacts preserved

`PipelineResult.degraded` and `PipelineResult.skipped_stages` signal what was bypassed.

## Module Architecture

```
src/
├── app.py                        Bootstrap entry point
├── core/
│   ├── types/                    Shared typed vocabulary (ids, enums, graph, provenance, bindings)
│   ├── contracts/                Interface ABCs and data shapes (6 contracts)
│   ├── manifolds/                Same-schema graph containers (base, identity, external, virtual)
│   ├── factory/                  Manifold creation (disk, memory, RAM)
│   ├── store/                    SQLite CRUD (16 tables, WAL mode)
│   ├── projection/               Manifold slicing (identity, external, query, shared core)
│   ├── fusion/                   Slice combination into VirtualManifold with bridges
│   ├── math/                     Scoring (PageRank, cosine, gravity, friction, annotator)
│   ├── extraction/               Evidence bag extraction (gravity-greedy, BFS, budget)
│   ├── hydration/                Content resolution (chunk text, hierarchy, edge translation)
│   ├── model_bridge/             Ollama HTTP backend (embed, synthesize, estimate tokens)
│   ├── runtime/                  Pipeline orchestration (controller, config, result, error)
│   └── debug/                    Inspection helpers (score dump, artifact inspection)
└── adapters/                     Migration compatibility shims
```

### Dependency Direction

```
types ← contracts ← manifolds ← factory
                                ← store
                   ← projection (reads manifolds via store or RAM)
                   ← fusion (creates VirtualManifold from projected slices)
                   ← math/scoring (scores VM, writes annotations)
                   ← extraction (reads scored VM, produces EvidenceBag)
                   ← hydration (reads VM + EvidenceBag, produces HydratedBundle)
                   ← model_bridge (HTTP to Ollama, no graph deps)
                   ← runtime (orchestrates all of the above)
                   ← debug (reads everything, writes nothing)
```

Synthesis is **downstream only**. The model bridge is the single boundary for
all model interaction. No subsystem other than model_bridge makes HTTP calls.

## Migration Discipline

This project uses a **strangler-fig pattern** to extract logic from a legacy
codebase. See `docs/EXTRACTION_RULES.md` for the full protocol. Key rules:
- Never copy entire legacy scripts
- Extract only narrow, well-bounded functions
- Every extraction tracked in `src/adapters/legacy_source_notes.md`

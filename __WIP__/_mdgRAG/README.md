# Graph Manifold

**Deterministic, graph-native knowledge retrieval — no GPU, no API, no guesswork.**

Graph Manifold is a structured knowledge retrieval system that turns your documents
into traversable graph manifolds — then retrieves, scores, and synthesizes answers
from them. It includes a **fully deterministic embedding engine** that produces
semantic vectors using pure math instead of neural networks.

```
Your corpus ──→ Graph Manifold ──→ Query ──→ Scored Evidence ──→ Answer
                                     │
                    No GPU. No API calls. Same input = same output. Always.
```

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)]()
[![Tests](https://img.shields.io/badge/tests-504%20passing-brightgreen.svg)]()
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE.md)
[![Phase](https://img.shields.io/badge/phase-12%20of%2023-orange.svg)]()

---

## Why This Exists

Every RAG system today follows the same pattern: chunk your documents, call an
embedding API, store vectors in a database, retrieve by cosine similarity, feed
to an LLM. That pipeline has three problems:

1. **Non-deterministic** — the same query can return different results depending
   on model version, quantization, hardware, and API weather.
2. **Opaque** — you cannot explain *why* two chunks scored similarly. The embedding
   is a black box.
3. **Infrastructure-dependent** — you need a running model server (or pay per API call)
   just to turn text into vectors.

Graph Manifold solves all three by replacing the neural embedding step with a
**deterministic mathematical pipeline** (BPE tokenization → co-occurrence statistics →
NPMI normalization → SVD compression), and by storing knowledge in graph manifolds
instead of flat vector databases.

The result: **same input always produces the same output**, on any machine, with
no server running, and you can trace exactly why any two texts are considered similar.

---

## The Embedding Engine — What Makes This Different

Most embedding systems look like this:

```
text ──→ [ Neural Network ] ──→ vector
              (black box)
```

Graph Manifold's deterministic embedder looks like this:

```
text ──→ BPE tokenize ──→ token IDs ──→ vector lookup ──→ mean pool ──→ vector
              │                              │                             │
         Split into          Look up each token's        Average all token
        learned subword       pre-computed vector        vectors into one
          units               from the SVD matrix        pooled embedding
```

**Every step is inspectable.** You can see which tokens were produced, what their
individual vectors look like, how they combined, and which vocabulary entries are
nearest to the result.

### Key Properties

| Property | Neural Embeddings | Graph Manifold |
|----------|------------------|----------------|
| **Deterministic** | No — varies by hardware, quantization, batch size | Yes — identical output every time |
| **Offline** | Needs running server or API | Just numpy array lookups |
| **Transparent** | Black box | Every step traceable |
| **Reversible** | No | Yes — vector → nearest tokens |
| **Corpus-specific** | Trained on web crawl | Trained on *your* data |
| **Dependencies** | PyTorch, transformers, GPU drivers | numpy |

### The Intuition (No Math Required)

Imagine you read a thousand-page book and noticed that "sword" and "blade" always
appear near each other, but "sword" and "accounting" never do. You'd naturally
conclude that "sword" and "blade" are related.

That's what this system does, mechanically:

1. **Tokenize** — Break text into reusable subword pieces (like `pre`, `tend`, `ing`)
   using the same BPE algorithm that powers GPT and friends.

2. **Count co-occurrences** — Slide a window across all your text. Every time two
   tokens appear near each other, record it.

3. **Normalize** — Raw counts are misleading because common tokens like `the` and
   `ing` appear near *everything*. NPMI (Normalized Pointwise Mutual Information)
   fixes this by asking: "Do these tokens appear together *more than chance predicts*?"
   Common-with-everything tokens get crushed. Rare-but-specific pairings get boosted.

4. **Compress** — The normalized co-occurrence matrix is huge and sparse (most tokens
   never meet most other tokens). SVD (Singular Value Decomposition) compresses it
   into dense, compact vectors that preserve the important relationships while
   discarding the noise.

5. **Look up and pool** — At query time, tokenize the input, look up each token's
   pre-computed vector, and average them together. Done. No neural network. No GPU.
   No API call. Just array indexing and arithmetic.

> **Want the formal math?** See [`docs/BPE_SVD_WHITEPAPER.md`](docs/BPE_SVD_WHITEPAPER.md)
> for the complete mathematical derivation with proper notation.

---

## System Architecture

Graph Manifold uses a **three-manifold model**. Every manifold shares the same
graph-native schema — they differ only in what they store and when they exist.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        QUERY + MANIFOLDS                            │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────┐   │
│  │   Identity    │    │   External   │    │ Deterministic Embed  │   │
│  │   Manifold    │    │   Manifold   │    │    Provider          │   │
│  │              │    │              │    │                      │   │
│  │ Session state │    │ Your corpus  │    │ BPE + SVD vectors    │   │
│  │ User context  │    │ Documents    │    │ No GPU required      │   │
│  │ Agent roles   │    │ Knowledge    │    │ (fallback: Ollama)   │   │
│  └──────┬───────┘    └──────┬───────┘    └──────────┬───────────┘   │
│         │                   │                       │               │
│         └─────────┬─────────┘                       │               │
│                   ▼                                 │               │
│           ┌───────────────┐                         │               │
│           │  PROJECTION   │◄────────────────────────┘               │
│           │ Slice + embed │                                         │
│           └───────┬───────┘                                         │
│                   ▼                                                 │
│           ┌───────────────┐                                         │
│           │    FUSION     │  Combine slices → Virtual Manifold      │
│           └───────┬───────┘  with bridge edges                      │
│                   ▼                                                 │
│           ┌───────────────┐                                         │
│           │   SCORING     │  G(v) = α·PageRank + β·CosineSim       │
│           └───────┬───────┘                                         │
│                   ▼                                                 │
│           ┌───────────────┐                                         │
│           │  EXTRACTION   │  Gravity-greedy → Evidence Bag          │
│           └───────┬───────┘                                         │
│                   ▼                                                 │
│           ┌───────────────┐                                         │
│           │  HYDRATION    │  Resolve chunks, hierarchy, edges       │
│           └───────┬───────┘                                         │
│                   ▼                                                 │
│           ┌───────────────┐                                         │
│           │  SYNTHESIS    │  Evidence → Answer (via Ollama)         │
│           └───────────────┘                                         │
└─────────────────────────────────────────────────────────────────────┘
```

### The Gravity Formula

The core ranking signal combines structural importance (how connected a node is)
with semantic relevance (how similar it is to the query):

```
G(v) = α · structural_score(v) + β · semantic_score(v)
```

- **Structural score**: PageRank — nodes that many other nodes point to are important
- **Semantic score**: Cosine similarity between the node's embedding and the query embedding
- **α = 0.6, β = 0.4** by default (structure matters slightly more than semantics)

When no embedding backend is available, the system degrades gracefully to
structure-only scoring. Nothing crashes. Nothing hangs.

---

## Quick Start

### Prerequisites

- Python 3.11+
- numpy (the only required dependency)

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd _mdgRAG

# Option A: Use the setup script (Windows)
setup_env.bat

# Option B: Manual setup
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e .
```

### Run the System

```bash
python -m src.app              # Bootstrap the pipeline
```

### Run Tests

```bash
pytest tests/                  # Full suite (499 tests, ~10 seconds)
pytest tests/ -v               # Verbose output
pytest tests/test_phase12_deterministic_embed.py -v   # Embedder tests only
```

### Launch the Diagnostic UI

```bash
python tools/diagnostic_ui.py
```

The diagnostic UI has three auto-discovering tabs:

| Tab | What It Does |
|-----|-------------|
| **Test Runner** | Discover and run any test file, see pass/fail results live |
| **API Explorer** | Browse every public module, class, and method with signatures and docstrings |
| **Embedder** | Interactive embedding playground — tokenize text, see vectors, reverse-lookup nearest tokens |

The Embedder tab includes a **"Generate Demo"** button that creates tiny test
artifacts so you can explore the embedding pipeline immediately without training
on a real corpus.

---

## Using the Deterministic Embedder

### Standalone Usage

```python
from src.core.model_bridge.deterministic_provider import (
    DeterministicEmbedProvider,
)

# Load pre-trained artifacts
provider = DeterministicEmbedProvider(
    tokenizer_path="path/to/tokenizer.json",
    embeddings_path="path/to/embeddings.npy",
)

# Embed text
result = provider.embed_texts(["hello world", "graph manifold"])

print(result.vectors)       # [[0.23, -0.56, ...], [0.41, 0.12, ...]]
print(result.dimensions)    # 300 (or whatever your SVD k was)
print(result.token_counts)  # [5, 7]
```

### Forward Path — Tokenization and Embedding

```python
# See exactly what BPE does to your text
token_ids = provider._encode("hello world")
symbols = provider.decode_token_ids(token_ids)
print(symbols)  # ['he', 'll', 'o', '</w>', 'w', 'or', 'ld', '</w>']

# Embed and inspect
result = provider.embed_texts(["hello world"])
print(f"Dimensions: {result.dimensions}")
print(f"Token count: {result.token_counts[0]}")
print(f"Vector (first 5): {result.vectors[0][:5]}")
```

### Reverse Path — What Does a Vector "Mean"?

```python
# Find which tokens are closest to a pooled vector
nearest = provider.nearest_tokens(result.vectors[0], k=5)

for symbol, similarity, token_vec in nearest:
    print(f"  {symbol:12s}  cos={similarity:+.4f}")
# Output:
#   he            cos=+0.8934
#   ll            cos=+0.8521
#   or            cos=+0.7832
#   ...
```

This is **not possible with neural embeddings**. You can literally read back what
a vector encodes.

### Through ModelBridge (Integrated Pipeline)

```python
from src.core.model_bridge.model_bridge import ModelBridge, ModelBridgeConfig

config = ModelBridgeConfig(
    embed_backend="deterministic",
    deterministic_tokenizer_path="path/to/tokenizer.json",
    deterministic_embeddings_path="path/to/embeddings.npy",
)

bridge = ModelBridge(config)

# This uses deterministic embeddings automatically
response = bridge.embed(EmbedRequest(texts=["your query here"]))
print(response.model)  # "deterministic-bpe-svd"
```

If the deterministic backend fails for any reason, ModelBridge automatically
falls back to Ollama. If Ollama is also unavailable, the pipeline continues
with structure-only scoring. **Nothing crashes.**

---

## Training Your Own Embeddings

The training pipeline produces two artifact files from your text corpus:

```
your_corpus/           training pipeline        artifacts/
├── doc1.txt    ──→    BPE → Co-occ →     ──→   ├── tokenizer.json
├── doc2.txt           NPMI → SVD                └── embeddings.npy
└── ...
```

### Training Pipeline (in `src/core/training/`)

```python
import numpy as np
from src.core.training import BPETrainer, compute_counts, build_npmi_matrix, compute_embeddings

# Stage 1: Train BPE tokenizer
trainer = BPETrainer(vocab_size=5000)
trainer.train("path/to/your/texts")
trainer.save("artifacts/tokenizer.json")

# Stage 2: Encode corpus + count co-occurrences
# (encode each line with the trained tokenizer, pass token ID streams here)
pair_counts, token_counts = compute_counts(token_streams, window_size=5)

# Stage 3: Build NPMI friction matrix
friction_matrix = build_npmi_matrix(pair_counts, token_counts, vocab_size=5000)

# Stage 4: SVD compression → final embeddings
embeddings = compute_embeddings(friction_matrix, k=300)
np.save("artifacts/embeddings.npy", embeddings)
```

### Artifact Formats

**`tokenizer.json`** — BPE vocabulary and merge rules:
```json
{
  "vocab": {"h": 0, "e": 1, "l": 2, "o": 3, "</w>": 4, "he": 8, "ll": 9},
  "merges": [["h", "e"], ["l", "l"], ["l", "o"]],
  "end_of_word": "</w>"
}
```

**`embeddings.npy`** — Dense matrix, shape `(vocab_size, k)`:
- Row `i` is the embedding vector for the token with vocab ID `i`
- `k` is the SVD dimensionality (default 300)
- Standard numpy `.npy` format — load with `np.load()`

---

## Project Status

### Current Phase: 12 of 23

| Phase | Status | Description |
|-------|--------|-------------|
| 2 | ✅ Complete | Type system — 9 typed IDs, 12 enums, full graph types |
| 3 | ✅ Complete | SQLite persistence — 16 tables, WAL mode |
| 4 | ✅ Complete | Projection and fusion — manifold slicing and combination |
| 5 | ✅ Complete | Scoring — PageRank, cosine similarity, gravity formula |
| 6 | ✅ Complete | Extraction — gravity-greedy evidence bags with token budgets |
| 7 | ✅ Complete | Hydration — content resolution (FULL, SUMMARY, REFERENCE modes) |
| 8 | ✅ Complete | Model bridge — Ollama HTTP backend for embedding and synthesis |
| 9 | ✅ Complete | Runtime pipeline — end-to-end orchestration with graceful degradation |
| 10 | ✅ Complete | Hardening — input validation, structured logging, timing instrumentation |
| 11 | ✅ Complete | Query embedding — semantic scoring activation |
| 12 | ✅ Complete | Deterministic embedder — BPE-SVD pipeline, reverse lookup, diagnostic UI |
| 13 | 🔲 Planned | Ingestion pipeline — text files → manifolds |
| 14 | 🔲 Planned | CLI query path |
| 15 | 🔲 Planned | UI interface |
| 16 | 🔲 Planned | Weighted PageRank |
| 17 | 🔲 Planned | ScoringConfig dataclass |
| 18 | 🔲 Planned | Real SUMMARY hydration mode |
| 19 | 🔲 Planned | Connection lifecycle management |
| 20 | 🔲 Planned | Multi-provider model bridge |
| 21 | 🔲 Planned | Advanced extraction strategies |
| 22 | 🔲 Planned | Pipeline caching |
| 23 | 🔲 Planned | Streaming pipeline results |

### Test Coverage

504 tests across 13 test files. Zero failures. ~10 second runtime.

```
tests/
├── test_imports.py                     # Module import validation
├── test_phase2_types.py                # Type system
├── test_phase3_storage.py              # SQLite persistence
├── test_phase4_projection_fusion.py    # Projection + fusion
├── test_phase5_scoring.py              # PageRank, cosine, gravity
├── test_phase6_extraction.py           # Evidence bag extraction
├── test_phase7_hydration.py            # Content resolution
├── test_phase8_model_bridge.py         # Model bridge (Ollama)
├── test_phase9_pipeline.py             # End-to-end pipeline
├── test_phase10_hardening.py           # Input validation, logging
├── test_phase11_query_embedding.py     # Semantic scoring
├── test_phase12_deterministic_embed.py # Deterministic embedder (53 tests)
└── test_scaffold_smoke.py              # Bootstrap smoke tests
```

---

## Design Principles

### Determinism First
Same input produces identical output. No randomness, no temperature, no stochastic
dropout. Every result is reproducible across machines and time.

### Graceful Degradation
The pipeline never crashes due to a missing component. No embedding backend?
Structure-only scoring. No Ollama? Synthesis skipped. No identity manifold?
External-only fusion. Every degradation is logged and reported.

### No Numpy Leakage
All numpy arrays are converted to plain Python lists before leaving the embedding
provider. No downstream code needs numpy. No serialization surprises.

### Lazy Imports
numpy is imported only when the deterministic backend is actually used. The entire
`model_bridge` module is importable in environments without numpy installed — it
just falls back to Ollama.

### Single Boundary for External Calls
ModelBridge is the only module that makes HTTP calls. No other subsystem contacts
external services. Everything else is local computation over local data structures.

---

## Documentation

| Document | Description |
|----------|-------------|
| [`docs/BPE_SVD_WHITEPAPER.md`](docs/BPE_SVD_WHITEPAPER.md) | **Formal mathematical blueprint** — complete derivation of the BPE-SVD embedding pipeline with proper notation |
| [`docs/MATH_PROBLEMS_RELATING_TO_EMBEDDING.md`](docs/MATH_PROBLEMS_RELATING_TO_EMBEDDING.md) | Prior art survey, comparative analysis, and engineering best practices for the embedding pipeline |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | System design, processing flow, module layout, dependency map |
| [`docs/DEVLOG.md`](docs/DEVLOG.md) | Chronological record of each implementation phase |
| [`docs/SYSTEM_MAP.md`](docs/SYSTEM_MAP.md) | Living map of system ownership and module boundaries |
| [`docs/TRANSLATION_THEORY.md`](docs/TRANSLATION_THEORY.md) | Theoretical foundation — ingestion as dimensional translation |
| [`docs/UI_WIRING.md`](docs/UI_WIRING.md) | UI integration guide with API surfaces and wiring patterns |
| [`docs/WATCHLIST.md`](docs/WATCHLIST.md) | Tracked architectural concerns and technical debt |
| [`docs/OPPORTUNITIES.md`](docs/OPPORTUNITIES.md) | Forward-looking enhancements |
| [`docs/EXTRACTION_RULES.md`](docs/EXTRACTION_RULES.md) | Strangler-fig migration protocol |
| `TODO.md` | Master task list for all remaining phases |

---

## Dependencies

**Required:**
- Python ≥ 3.11
- numpy ≥ 1.24.0

**Optional (for full pipeline):**
- [Ollama](https://ollama.com) — local LLM server for neural embeddings and text synthesis
- scipy — only needed for the training pipeline (SVD computation)

That's it. No PyTorch. No transformers. No CUDA. No API keys.

---

## Migration Discipline

This project uses a **strangler-fig pattern** to selectively extract logic from
a legacy codebase. The rules are strict:

- Never copy an entire legacy script
- Extract only narrow, well-bounded functions or classes
- Every extracted unit is assigned to exactly one owner module
- If ownership is unclear, the function stays in the legacy project
- All extractions are tracked in `src/adapters/legacy_source_notes.md`

See [`docs/EXTRACTION_RULES.md`](docs/EXTRACTION_RULES.md) for the full protocol.

---

## License

MIT — see [`LICENSE.md`](LICENSE.md)

# BPE-SVD Deterministic Embedding: Mathematical Foundations

**A corpus-specific, fully deterministic text embedding pipeline using
subword tokenization, co-occurrence statistics, and spectral decomposition.**

*Graph Manifold Project — Deterministic Embedding Subsystem*

---

## Abstract

This document formally defines a text embedding pipeline that replaces neural
network inference with a deterministic mathematical construction. The pipeline
operates in two phases: an offline **training phase** that builds artifacts from
a text corpus, and an online **inference phase** that produces embedding vectors
from those artifacts with no model server, no GPU, and no network calls.

The key insight is that the semantic relationships captured by neural embedding
models can be approximated by a classical statistical pipeline: Byte-Pair
Encoding (BPE) for tokenization, sliding-window co-occurrence counting,
Normalized Pointwise Mutual Information (NPMI) for statistical normalization,
and truncated Singular Value Decomposition (SVD) for dimensionality reduction.

The resulting embeddings are **fully deterministic** (same input always produces
identical output), **fully transparent** (every step is inspectable), **fully
reversible** (a pooled vector can be mapped back to its nearest tokens), and
**corpus-specific** (trained on the target corpus, not a general web crawl).

---

## Table of Contents

1. [Pipeline Overview](#1-pipeline-overview)
2. [Stage 1: BPE Tokenization](#2-stage-1-bpe-tokenization)
3. [Stage 2: Co-occurrence Counting](#3-stage-2-co-occurrence-counting)
4. [Stage 3: NPMI Normalization](#4-stage-3-npmi-normalization)
5. [Stage 4: The Friction Interpretation](#5-stage-4-the-friction-interpretation)
6. [Stage 5: SVD Spectral Compression](#6-stage-5-svd-spectral-compression)
7. [Stage 6: Inference — Encoding and Pooling](#7-stage-6-inference--encoding-and-pooling)
8. [Stage 7: Reverse Lookup](#8-stage-7-reverse-lookup)
9. [Properties and Guarantees](#9-properties-and-guarantees)
10. [Relationship to Prior Work](#10-relationship-to-prior-work)
11. [Artifact Specification](#11-artifact-specification)
12. [Integration with the Gravity Scoring Pipeline](#12-integration-with-the-gravity-scoring-pipeline)

---

## 1. Pipeline Overview

The full system consists of a training pipeline (offline, runs once per corpus)
and an inference engine (online, runs per query):

```
TRAINING (offline, per corpus)                    INFERENCE (online, per query)
═══════════════════════════════                   ════════════════════════════

  Corpus texts                                      Input text
      │                                                 │
      ▼                                                 ▼
  ┌──────────────┐                                ┌──────────────┐
  │ BPE Training │ ──→ tokenizer.json             │ BPE Encoding │
  └──────┬───────┘     (vocab + merges)           └──────┬───────┘
         │                    │                          │
         ▼                    │                     token IDs
  ┌──────────────┐            │                          │
  │ Co-occurrence│            │                          ▼
  │   Counting   │            │                   ┌──────────────┐
  └──────┬───────┘            │                   │Vector Lookup │
         │                    │                   │(matrix rows) │
         ▼                    │                   └──────┬───────┘
  ┌──────────────┐            │                          │
  │     NPMI     │            │                     token vectors
  │   Matrix     │            │                          │
  └──────┬───────┘            │                          ▼
         │                    │                   ┌──────────────┐
         ▼                    │                   │  Mean Pool   │
  ┌──────────────┐            │                   └──────┬───────┘
  │  Truncated   │            │                          │
  │     SVD      │ ──→ embeddings.npy                    ▼
  └──────────────┘     (V × k matrix)             pooled vector
                                                  (1 × k)
```

Two artifact files bridge the gap:
- **`tokenizer.json`** — vocabulary mapping and ordered merge rules
- **`embeddings.npy`** — dense matrix of shape (V, k) where V is vocabulary
  size and k is embedding dimensionality

---

## 2. Stage 1: BPE Tokenization

### Definition

Byte-Pair Encoding (BPE) is a subword tokenization algorithm that iteratively
merges the most frequent adjacent symbol pairs in a corpus.

### Algorithm

**Input:** Corpus C as a sequence of words; target vocabulary size V_target.

**Initialization:**
- Split every word w into its character sequence plus an end-of-word marker:
  `w = "hello"` becomes `['h', 'e', 'l', 'l', 'o', '</w>']`
- Initialize vocabulary V_0 as the set of all unique characters plus `</w>`
- Initialize merge list M = []

**Iteration (repeat until |V| = V_target or no pairs remain):**

At step t:

1. Count all adjacent symbol pairs across the corpus:

   ```
   counts(a, b) = number of times symbol a is immediately followed by symbol b
                  across all words in the corpus
   ```

2. Select the most frequent pair:

   ```
   (a*, b*) = argmax_{(a,b)} counts(a, b)
   ```

3. Merge: replace every adjacent occurrence of (a*, b*) with the concatenated
   symbol `a*b*` throughout the corpus.

4. Update: V_{t+1} = V_t ∪ {a*b*}, append (a*, b*) to M.

**Output:** Vocabulary V (symbol → integer ID) and ordered merge list M.

### Properties

- **Lossless:** The original text can be reconstructed from the token sequence
  plus the vocabulary.
- **Frequency-adaptive:** Common subwords get dedicated tokens; rare words are
  composed from smaller pieces.
- **Deterministic:** Given the same corpus, the same merges are learned in the
  same order.

### Example

Given corpus containing "hello" and "help":

```
Step 0: h e l l o </w>  |  h e l p </w>
Step 1: merge (h, e) → he
        he l l o </w>   |  he l p </w>
Step 2: merge (l, l) → ll
        he ll o </w>    |  he l p </w>
```

---

## 3. Stage 2: Co-occurrence Counting

### Definition

Given the trained BPE tokenizer from Stage 1, encode the entire corpus into
token ID streams, then count how often each pair of distinct tokens appears
within a fixed-width sliding window.

### Formalism

Let T = [t_1, t_2, ..., t_N] be the full token stream produced by encoding
the corpus. Let w be the window half-width (default w = 5).

**Pair counts:**

```
count(a, b) = |{(i, j) : t_i = a, t_j = b, i ≠ j, |i - j| ≤ w}|
```

Pairs are stored canonically as (min(a, b), max(a, b)) to enforce symmetry:
count(a, b) = count(b, a).

**Token counts:**

```
count(a) = |{i : t_i = a}|
```

**Total pairs:**

```
N_pairs = Σ_{(a,b)} count(a, b)
```

### Why a Window?

Without a window, every token in a document co-occurs with every other token,
drowning local semantic signal in document-level noise. The window constrains
co-occurrence to tokens that are actually near each other in the text —
capturing the same distributional signal that Word2Vec's skip-gram window
captures, but without any neural network.

---

## 4. Stage 3: NPMI Normalization

### The Problem with Raw Counts

Raw co-occurrence counts are dominated by high-frequency tokens. The token
`the` co-occurs with nearly everything, not because it's semantically related
to everything, but because it's ubiquitous. A better measure asks:
"Do these two tokens co-occur **more than chance predicts**?"

### Pointwise Mutual Information (PMI)

PMI measures the ratio between a pair's observed co-occurrence probability
and what would be expected if the tokens were independent:

```
PMI(a, b) = log₂( P(a,b) / (P(a) · P(b)) )
```

Where:
- P(a, b) = count(a, b) / N_pairs
- P(a) = count(a) / N_tokens
- P(b) = count(b) / N_tokens

**Interpretation:**
- PMI > 0: tokens co-occur more than chance → positively associated
- PMI = 0: tokens co-occur exactly at chance rate → independent
- PMI < 0: tokens co-occur less than chance → negatively associated

### The Problem with Raw PMI

PMI is unbounded. For very rare pairs that happen to co-occur, PMI can be
extremely large (because P(a,b) is tiny relative to P(a)·P(b), but the
log ratio explodes when the denominator is also tiny). This makes PMI
incomparable across pairs with different base rates.

### Normalized PMI (NPMI)

NPMI normalizes PMI to the range [-1, +1] by dividing by the self-information
of the pair:

```
NPMI(a, b) = PMI(a, b) / (-log₂(P(a, b)))
           = log₂(P(a,b) / (P(a)·P(b))) / (-log₂(P(a,b)))
```

**Interpretation:**
- NPMI = +1: perfect co-occurrence (a and b always appear together)
- NPMI = 0: independence (co-occur at exactly the chance rate)
- NPMI = -1: never co-occur (complete avoidance)

**Why NPMI over PMI?**

The normalization by -log₂(P(a,b)) has a crucial effect: it makes the measure
comparable across pairs with wildly different base rates. A rare pair and a
common pair can both score NPMI = 0.7, and that 0.7 means the same thing
in both cases: "these tokens co-occur substantially more than chance predicts."

---

## 5. Stage 4: The Friction Interpretation

### From Association to Distance

NPMI gives us a measure of association strength. But for graph traversal and
embedding purposes, a measure of **distance** is needed — how far apart are
two tokens in semantic space?

The friction transformation inverts the semantic signal:

```
friction(a, b) = 1 - NPMI(a, b)
```

**Interpretation:**
- friction ≈ 0: strong association → semantically close → low traversal cost
- friction = 1: independence → neutral distance
- friction ≈ 2: anti-association → semantically distant → high traversal cost

### The Friction Matrix

The result is a symmetric sparse matrix F of shape (V, V):

```
F[i, j] = friction(token_i, token_j)    if tokens i and j co-occurred
F[i, j] = 0                             if never observed
```

### Why "Friction"?

This term comes from the original design insight that motivated the system.
The original design insight: if a graph of token relationships treats
high-frequency connections as **resistance** (friction), then pathfinding
through the graph naturally routes around generic connectors (like `the`, `ing`)
toward semantically meaningful connections.

This intuition maps precisely onto the NPMI construction:

- **High NPMI** (strong association) → **low friction** → traversal prefers
  these edges → semantically meaningful connections are favored
- **Low/zero NPMI** (independence) → **high friction** → traversal avoids
  these edges → generic connectors are naturally penalized

The graph view and the vector view are two representations of the same
underlying relational structure. The friction matrix IS the graph's weighted
adjacency matrix, and SVD compresses it into navigable vector coordinates.

---

## 6. Stage 5: SVD Spectral Compression

### The Problem: Dimensionality

The friction matrix F is (V × V) — potentially 5,000 × 5,000 or larger.
It's also extremely sparse: most token pairs never co-occur. This matrix
is too large and too sparse to use directly as an embedding.

### Singular Value Decomposition

SVD factorizes any matrix M into three matrices:

```
M = U · Σ · V^T
```

Where:
- U is (V × V) — left singular vectors (one per token)
- Σ is diagonal (V × V) — singular values in descending magnitude
- V^T is (V × V) — right singular vectors

### Truncated SVD

Only the top k singular values and their corresponding vectors are retained:

```
M ≈ U_k · Σ_k · V_k^T
```

Where U_k is (V × k). Each row of U_k is a k-dimensional embedding for one
token. The truncation discards the dimensions that capture the least variance
in the friction matrix — effectively compressing the relational structure
into its most important axes.

### What the Dimensions Mean

Each column of U_k corresponds to one axis of variation in the friction space.
The first dimension captures the most significant pattern of co-occurrence
variation across the vocabulary. The second captures the next most significant
pattern, orthogonal to the first. And so on.

Tokens with similar friction profiles (similar patterns of what they co-occur
with and what they avoid) end up with similar k-dimensional coordinates.
This is precisely the distributional hypothesis: tokens that appear in similar
contexts have similar meanings.

### Implementation Detail

The implementation uses `scipy.sparse.linalg.svds()` which computes truncated
SVD directly on the sparse friction matrix without ever constructing the full
dense factorization. The singular values are returned in ascending order and
reversed to descending order so that the most significant dimensions come first.

Only U_k (the left singular vectors) is retained as the embedding matrix.
The singular values Σ_k are not applied as scaling factors — the embedding
coordinates are the raw singular vector components.

**Output:** A dense numpy array of shape (V, k), saved as `embeddings.npy`.

---

## 7. Stage 6: Inference — Encoding and Pooling

### BPE Encoding (Online)

Given a new text string at query time:

1. Split on whitespace into words
2. For each word, decompose into characters plus `</w>`:
   `"hello"` → `['h', 'e', 'l', 'l', 'o', '</w>']`
3. Apply merge rules in order: scan left-to-right, merge matching adjacent
   pairs into their combined symbol
4. Map each resulting symbol to its vocabulary ID (unknown symbols → -1)

This reproduces the same tokenization that the training phase used, ensuring
that the same tokens map to the same embedding rows.

### Vector Lookup

For each token ID produced by BPE encoding:

```
v_i = E[token_id_i]     if 0 ≤ token_id_i < V
v_i = 0_k               if token_id_i is unknown (-1 or out of range)
```

Where E is the (V × k) embedding matrix and 0_k is the k-dimensional zero vector.

Unknown tokens map to zero vectors rather than being excluded. This means they
dilute the pooled result proportionally to how many unknown tokens appear —
a deliberate design choice that makes the degradation continuous rather than
discontinuous.

### Mean Pooling

Given token vectors v_1, v_2, ..., v_n for a text with n tokens:

```
pooled = (1/n) · Σ_{i=1}^{n} v_i
```

This is the same aggregation strategy used by many neural embedding models
(e.g., averaging the last hidden states of a transformer). It produces a
single k-dimensional vector that represents the entire input text.

### Optional L2 Normalization

When enabled (controlled by the caller), the pooled vector is normalized
to unit length:

```
v_normalized = v / ||v||₂
```

After normalization, dot product equals cosine similarity:

```
cos(a, b) = a · b / (||a|| · ||b||) = a_norm · b_norm
```

This simplifies downstream scoring to a single dot product.

---

## 8. Stage 7: Reverse Lookup

### Motivation

A unique property of this embedding system is that the vector space is
**interpretable**. Because each row of the embedding matrix corresponds to a
known token, the nearest tokens to any point in the space can be determined.

Neural embedding models cannot do this — their vector spaces are entangled
by billions of learned parameters with no clean mapping back to vocabulary items.

### Nearest Token Search

Given a query vector q (either a pooled text embedding or any k-dimensional
vector):

1. Normalize the query: q_unit = q / ||q||₂
2. Normalize each embedding row: e_i_unit = E[i] / ||E[i]||₂
   (rows with zero norm are assigned zero similarity)
3. Compute cosine similarities: sim_i = e_i_unit · q_unit
4. Return the top-k tokens by descending similarity

Each result is a tuple of (symbol, cosine_similarity, token_vector).

### Decode Token IDs

The inverse vocabulary mapping (ID → symbol) is built lazily from the forward
vocabulary (symbol → ID). Any ID not in the vocabulary maps to the placeholder
`<unk:{id}>`.

### What This Enables

- **Debugging:** "What does this embedding actually capture?" → look at its
  nearest tokens
- **Validation:** After embedding a text, verify that the nearest tokens
  are semantically related to the input
- **Transparency:** External auditors can inspect exactly what the system
  considers "similar"

---

## 9. Properties and Guarantees

### Determinism

**Guarantee:** For any fixed pair of artifact files (tokenizer.json,
embeddings.npy), the same input text always produces the identical output vector.

**Why:** Every operation is deterministic:
- BPE encoding: ordered merge rules applied left-to-right
- Vocabulary lookup: dictionary mapping
- Matrix indexing: numpy array row access
- Mean pooling: arithmetic average
- No randomness, no temperature, no dropout, no GPU non-determinism

### No Numpy Type Leakage

**Guarantee:** All vectors returned by the provider are plain Python
`List[float]`. No numpy scalars, no numpy arrays, no numpy dtypes cross
the provider boundary.

**Why:** All numpy results are converted via `.tolist()` before being
returned in `DeterministicEmbedResult`. This prevents serialization
surprises and decouples downstream code from numpy.

### Graceful Degradation

**Guarantee:** If the deterministic backend fails for any reason, the system
falls back to Ollama. If Ollama also fails, the pipeline continues with
structure-only scoring.

**Chain:** deterministic → Ollama → structural-only → error propagation

### Empty Input Handling

- Empty string → zero vector of correct dimensionality, token count = 0
- Empty text list → empty result (no vectors, no artifacts)
- Unknown tokens → zero vectors included in mean pool

---

## 10. Relationship to Prior Work

### Latent Semantic Analysis (LSA/LSI)

**Deerwester et al., 1990**

LSA applies SVD to a term-document matrix (typically TF-IDF weighted).
This pipeline differs from LSA in three ways:

1. **Tokenization:** LSA uses whole words or stems. BPE subwords are used
   here, which handles novel words gracefully by composing them from known
   pieces.

2. **Co-occurrence matrix:** LSA builds a term-document matrix (rows = words,
   columns = documents). This pipeline builds a token-token co-occurrence
   matrix with windowed counts, capturing local context rather than
   document-level co-presence.

3. **Normalization:** LSA typically uses TF-IDF. NPMI is used here, which
   provides a bounded [-1, +1] measure that properly accounts for base rates
   of both tokens in a pair.

### Word2Vec (Skip-gram with Negative Sampling)

**Mikolov et al., 2013**

Word2Vec trains a shallow neural network to predict context words from a
target word (or vice versa). Levy & Goldberg (2014) showed that skip-gram
with negative sampling implicitly factorizes a PMI matrix shifted by
log(k), where k is the number of negative samples.

This pipeline makes the factorization **explicit**: NPMI is computed directly
and decomposed via SVD. The result is mathematically related to what Word2Vec
learns, but without any stochastic gradient descent, random initialization,
or training hyperparameter sensitivity.

### GloVe

**Pennington et al., 2014**

GloVe explicitly constructs a co-occurrence matrix and learns embeddings
by factorizing it. The key differences from this pipeline:

1. GloVe uses a weighted least squares objective with a custom weighting
   function. This pipeline uses NPMI normalization + truncated SVD — a
   closed-form solution with no iterative optimization.

2. GloVe learns both word vectors and context vectors. Only the left
   singular vectors (U_k) are used here.

### The Novel Contribution

The specific combination in this pipeline — **BPE subword tokenization +
windowed co-occurrence + NPMI normalization + friction interpretation +
truncated SVD** — is not described as an integrated system in the existing
literature, to the authors' knowledge. Each component is well-understood
individually, but their composition produces a system with unique properties:

- **Subword granularity** with **statistical normalization** (most SVD-based
  approaches use whole-word vocabularies)
- **Corpus-specific training** that produces a **closed-form embedding**
  (no iterative optimization, no convergence concerns)
- **Full reversibility** (pooled vector → nearest BPE tokens) enabled by
  the clean mapping between matrix rows and vocabulary entries
- **Friction interpretation** that provides a principled bridge between
  the graph-traversal view and the vector-space view of semantic similarity

---

## 11. Artifact Specification

### tokenizer.json

```json
{
  "vocab": {
    "<symbol>": <integer_id>,
    ...
  },
  "merges": [
    ["<left>", "<right>"],
    ...
  ],
  "end_of_word": "</w>"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `vocab` | Dict[str, int] | Symbol string → integer ID. IDs are sequential from 0. |
| `merges` | List[List[str, str]] | Ordered merge pairs. Order is critical — merges are applied sequentially during encoding. |
| `end_of_word` | str | Marker appended to each word before BPE (default `</w>`). |

### embeddings.npy

| Property | Value |
|----------|-------|
| Format | numpy `.npy` (v1.0+) |
| Shape | (V, k) where V = vocab size, k = embedding dim |
| Dtype | float32 or float64 |
| Row semantics | Row i = embedding vector for token with vocab ID i |
| Loading | `numpy.load("embeddings.npy")` |

---

## 12. Integration with the Gravity Scoring Pipeline

The deterministic embedder plugs into the Graph Manifold retrieval pipeline
at the **Projection** stage. Here is how the embedding flows through the
full system:

### At Query Time

1. **Query Projection** receives the user's query text
2. **ModelBridge.embed()** routes to the deterministic backend (if artifacts
   are configured) or falls back to Ollama
3. The deterministic backend:
   - BPE-encodes the query
   - Looks up token vectors
   - Mean-pools into a single query vector
   - Optionally L2-normalizes
4. The query vector is stored in the **QueryProjectionArtifact**

### At Scoring Time

5. **Semantic scoring** computes cosine similarity between the query vector
   and every node's embedding in the Virtual Manifold
6. **Gravity scoring** combines semantic similarity with structural centrality:

   ```
   G(v) = α · S_norm(v) + β · T_norm(v)
   ```

   Where:
   - S_norm(v) = min-max normalized PageRank score
   - T_norm(v) = min-max normalized cosine similarity vs query embedding
   - α = 0.6 (structural weight)
   - β = 0.4 (semantic weight)

7. **Extraction** uses gravity scores to greedily select the most relevant
   evidence nodes

### The Two-View Equivalence

The friction matrix and the embedding matrix represent the same information
in two different forms:

- **Graph view:** Tokens are nodes. Friction values are edge weights.
  Semantic similarity is inverse path cost. Retrieval is pathfinding.

- **Vector view:** Tokens are points in k-dimensional space. Semantic
  similarity is cosine of the angle between points. Retrieval is nearest
  neighbor search.

SVD is the bridge between these views. It compresses the graph's weighted
adjacency matrix into dense coordinates that preserve the most significant
relational structure. The graph IS the matrix IS the vector space — three
views of one reality.

---

*This document establishes the mathematical foundations of the BPE-SVD
deterministic embedding system as implemented in Graph Manifold. For
implementation details, see the source at
`src/core/model_bridge/deterministic_provider.py`. For the training
pipeline, see `src/core/training/`. The standalone distributable package
is at `packages/bpe_svd/`.*

# Deterministic Embedder: Literature Context and Engineering Best Practices

> **Companion document** — mathematical derivation and formal notation are in
> [`docs/BPE_SVD_WHITEPAPER.md`](BPE_SVD_WHITEPAPER.md). This document covers
> prior art, comparative analysis, and practical engineering recommendations.

---

## Executive Summary

The “Deterministic Embedder” design (BPE subwords → windowed co‑occurrence → NPMI → PNPMI sparse association matrix → truncated SVD with singular‑value scaling → optional friction graph for traversal) is best understood as a modernized, corpus‑specific instance of count‑based distributional semantics and spectral embedding. This family includes Latent Semantic Analysis/Indexing (LSA/LSI) via SVD on term–document matrices , PPMI/SPPMI + SVD pipelines that explicitly factorize PMI‑derived matrices (and are theoretically tied to word2vec SGNS via shifted PMI factorization) , and graph spectral embeddings such as Laplacian Eigenmaps as well as graph–embedding unifications like NetMF that show DeepWalk/node2vec are also matrix‑factorization views of graph neighborhoods .

Two “industry‑grade” lessons from prior art apply directly to this pipeline:

    Sparse‑matrix semantics must match implicit zeros. This is why factorizing PNPMI/PPMI/SPPMI (where “no positive evidence” is truly zero) is canonical for sparse SVD pipelines .
    SVD outputs require variance‑aware scaling and sign canonicalization. Classical LSA uses Σ‑weighted coordinates for meaningful geometry , and modern libraries explicitly handle sign ambiguity (e.g., svd_flip / flip_sign) to ensure deterministic components .

Recommended defaults that align with the strongest practices in the literature: (a) PNPMI or SPPMI as the factorized matrix; (b) distance‑weighted windows (deterministic analog of word2vec’s dynamic windowing) ; (c) Σ scaling exponent α ≈ 0.5 (LSA‑style) with optional row L2 normalization ; (d) sign canonicalization (svd_flip equivalent) ; (e) SIF‑style pooling upgrades when sentence/query embeddings are needed .
Prior art and recurring patterns
PMI/NPMI as association backbones

PMI and its variants are longstanding tools for measuring how strongly two events co‑occur relative to independence. NPMI (Bouma) is a normalized variant intended to be more interpretable and less frequency‑sensitive by bounding scores to ([-1,1]). This normalization is widely adopted outside embeddings too—most visibly in topic coherence evaluation, where NPMI correlates well with human judgments compared to many alternatives.

Positive PMI transforms are a canonical practical step in distributional semantics. Bullinaria & Levy’s systematic studies (and follow‑ups) repeatedly find PPMI (negative PMI values clamped to zero) and small context windows to be strong defaults for semantic tasks, because negative PMI often behaves more like noise than useful signal in sparse data regimes.

A key bridge to “predictive” embeddings is Levy & Goldberg’s result: word2vec SGNS is (approximately) learning a shifted PMI factorization, motivating SPPMI = max(PMI − log k, 0) as an explicit count‑based surrogate for SGNS.
PPMI/SPPMI + SVD and LSA/LSI as canonical spectral compressions

LSA/LSI applies SVD to a (typically TF‑IDF weighted) term–document matrix and uses low‑rank representations for retrieval and similarity. The same logic appears in word–context pipelines: build a large sparse matrix of co‑occurrence signal (often PPMI/SPPMI), then reduce with truncated SVD to get dense embeddings. This is the classic “count → factorize” family that predates neural embeddings and remains competitive in many regimes.

Beyond “plain SVD,” Lebret & Collobert show a closely related spectral approach: embeddings via Hellinger PCA on co‑occurrence probabilities (square‑root transform), achieving competitive results while keeping the pipeline simple and mostly closed‑form.
Predictive embeddings and their explicit‑statistics interpretations

    word2vec (SGNS/CBOW) learns embeddings by predicting context via stochastic training; its “magic” is partly explained by implicit matrix factorization of PMI‑like quantities.
    GloVe explicitly uses global co‑occurrence statistics and optimizes a weighted regression objective (rather than pure SVD), achieving strong performance and introducing a well‑studied weighting function for rare vs frequent co‑occurrences.
    fastText adds subword character n‑grams so that embeddings can be composed for unseen words, substantially improving OOV handling.

Baroni et al.’s “Don’t count, predict!” provides a widely cited systematic comparison showing that predictive models often win on benchmarks, but count‑based models can remain highly competitive depending on hyperparameters and tasks.
Spectral and graph embedding views of co‑occurrence structures

There are two adjacent graph‑based traditions relevant to the friction graph concept:

    Spectral graph embeddings (e.g., Laplacian Eigenmaps) embed nodes so that connected/weighted neighbors stay close, using eigenvectors of Laplacian‑derived matrices.
    Random‑walk/skip‑gram graph embeddings (DeepWalk/node2vec/LINE) treat walks as sentences and learn embeddings via SGNS‑like objectives.

Crucially, NetMF shows these graph‑walk embeddings can be reframed as explicit matrix factorization problems, unifying DeepWalk/LINE/node2vec and connecting them to normalized Laplacian operators. This is directly thematically aligned with the “closed‑form factorization + graph traversal” split in this design: one representation is “factorize for vectors,” another is “use weights for paths.”

Graph‑of‑words approaches (like TextRank) also build co‑occurrence graphs, though typically for ranking rather than embeddings. Recent work on term co‑occurrence networks explicitly converts edge weights to NPMI and then thresholds, reinforcing that NPMI‑weighted co‑occurrence graphs are an established motif.
Friction/distance‑as‑cost usage patterns

Treating “semantic strength” as a graph weight and then converting it into a path cost is a standard maneuver in weighted graph algorithms: shortest paths minimize the sum of edge costs, so stronger links must correspond to smaller costs. NetworkX’s weighted shortest‑path interfaces encode exactly this model (edge attribute → weight function).

More domain‑specific evidence that this exact approach is plausible: a computational linguistics study on semantic relatedness (in the context of a word‑association game) compares NPMI‑based and graph‑path‑based relatedness measures, explicitly noting the convention that “stronger connections belong to smaller path weights.”
Comparative analysis against established approaches
Comparison table

The table below covers four key dimensions. “Determinism” is separated into (a) determinism given fixed artifacts and (b) determinism of training without extra controls (random seeds, single‑threading, sign flips). “Reversibility” here means the system naturally yields a stable token trace and a direct mapping from vectors back to discrete units.
Approach / pattern	Determinism (inference)	Determinism (training)	Offline training & inference	Sparsity handling	Memory / compute profile	Interpretability	Reversibility / token trace	Unseen tokens	Corpus specificity	Integration complexity
This design: PNPMI + truncated SVD + friction graph	High (artifact lookup)	High if sign‑canon + fixed solver	Yes	Excellent (sparse matrix)	SVD dominates; scales with nnz·k	High (nearest tokens, inspectable pipeline)	Strong (token_ids + per‑token vectors)	Moderate→High with byte‑level BPE	Very high	Moderate
LSA/LSI (TF‑IDF term–doc + SVD)	High	High with sign‑canon	Yes	Excellent	Sparse term–doc; SVD dominates	Medium‑high (“topics”)	Medium (term/doc mapping; no token trace)	Low unless subword	High	Moderate
PPMI/SPPMI + SVD (word–context)	High	High with sign‑canon	Yes	Excellent	Sparse PMI matrix; SVD dominates	Medium‑high	Medium (word ids; no subword trace)	Low unless subword	High	Moderate
Hellinger PCA / spectral on probabilities	High	High with sign‑canon	Yes	Moderate (often needs dense-ish ops or careful sparse linear algebra)	PCA/eigs; can be heavy at scale	Medium	Medium	Low unless subword	High	Moderate
word2vec SGNS (predictive)	High (lookup)	Lower (SGD stochasticity, multi‑threading)	Yes	N/A (doesn’t build giant matrix)	Very scalable streaming SGD	Lower (implicit)	Medium (word ids; no trace)	Low unless augmented	Medium (often trained on huge corpora)	Low (mature libs)
GloVe (co‑occurrence regression)	High (lookup)	Lower‑moderate (iterative optimization)	Yes	Good (sparse cooccur counts)	Cooccur building + iterative training	Medium	Medium	Low unless augmented	Medium	Low
fastText (subword n‑grams + SGNS)	High (lookup/composition)	Lower (SGD)	Yes	N/A	Very scalable; extra n‑gram storage	Low‑medium	Medium‑high (subword compositionality)	High (OOV via n‑grams)	Medium	Low
Graph spectral (Laplacian Eigenmaps)	High	High with sign‑canon	Yes	Good	Eigs of Laplacian; depends on k, nnz	Medium	Medium (node ids)	Depends on tokenizer	High	Moderate
Graph walk embeddings (DeepWalk/node2vec/LINE)	High (lookup)	Low (sampling + SGD)	Yes	Good	Sampling + SGNS‑like training	Low‑medium	Medium	Depends	High	Moderate
Transformer embeddings (BERT/modern encoders)	High for fixed weights	N/A if using pretrained; training is stochastic	Inference needs model runtime	Dense compute	Heavy inference; GPU/CPU cost	Low	Low (subword ids exist but model obscures)	High (subwords)	Lower unless fine‑tuned	Higher

Sources underpinning the families above: LSA/LSI ; PPMI empirical best‑practice ; SGNS↔shifted PMI theory ; GloVe ; fastText ; Laplacian Eigenmaps ; DeepWalk/node2vec ; NetMF unification .
Visual comparison chart

Below is a qualitative (non‑benchmarked) chart that summarizes the structural tradeoffs most people see in practice: determinism, complexity, and general semantic accuracy across major families.

Download the chart

(The scoring is an analytical heuristic, not an empirical benchmark; it is meant to support design decisions, not to “prove” a winner.) Supporting context for the axes: determinism and sign ambiguity in SVD outputs ; predictive model training being SGD‑based ; count‑based vs predictive comparisons .
Algorithmic variants and engineering best practices

This section distills “what to adopt” from the strongest recurring patterns and from how mature libraries do it.
Matrix construction choices

Positive association matrix for factorization. For a sparse matrix where implicit zero means “no positive evidence,” the canonical construction is one of:

    PPMI: ( \max(0, \mathrm{PMI}) )
    SPPMI: ( \max(0, \mathrm{PMI} - \log k) ) (explicit SGNS surrogate)
    PNPMI: ( \max(0, \mathrm{NPMI}) ) (the bounded variant; well-motivated by NPMI properties)

Default recommendation: start with PNPMI for bounded scores and interpretability; keep SPPMI as an optional “SGNS‑like” mode if analogy performance or SGNS parity matters. The literature most directly validates SPPMI as an SGNS equivalent ; the literature most directly validates NPMI for bounded association stability is in collocations and coherence measurement .

Minimum count thresholds. Bullinaria & Levy’s empirical work (and many follow‑ons) implicitly support the idea that small windows + positive PMI work best when unstable low‑count events are removed.
Defaults that tend to behave well:

    token min frequency: min_token_count ∈ [5, 50] depending on corpus scale
    pair min frequency: c_min ∈ [2, 10] depending on window size and corpus scale

Distance‑weighted windows. word2vec’s training uses windowing strategies that effectively bias closer words more than distant ones (dynamic windows and subsampling are core to the original improvements).
A deterministic analogue is to weight pair increments by distance:

[ \Delta \mathrm{count}(i,j) \mathrel{+}= \frac{1}{|i-j|} \quad\text{or}\quad \Delta \mathrm{count}(i,j) \mathrel{+}= (w+1-|i-j|) ]

This typically reduces “baggy” noise and strengthens syntagmatic relations.
SVD solver, scaling, and determinism controls

Sparse SVD choices. For sparse matrices, two mature paths dominate:

    SciPy svds (ARPACK/Lobpcg/PROPACK solvers). SciPy explicitly notes singular value order is not guaranteed, so results must be sorted.
    scikit‑learn TruncatedSVD / randomized_svd for scalable randomized methods; flip_sign exists specifically to resolve sign ambiguity deterministically.

Recommendation by corpus scale

    (V \lesssim 50k), nnz moderate: svds with careful sorting is fine.
    Very large nnz: consider randomized SVD with fixed random_state and flip_sign=True.

Singular value scaling. Classical LSA/LSI places items in Σ‑weighted latent space (variance‑aware coordinates).
General family:

[ E = U_k \Sigma_k^\alpha ]

Recommended default:

    ( \alpha = 0.5 ) (balanced; common in “LSA‑style” embeddings)
    ( \alpha = 1.0 ) (max variance emphasis; sometimes better for retrieval but can over‑focus dominant factors)

Sign canonicalization. SVD is only unique up to sign flips of singular vectors; scikit‑learn documents this explicitly and provides svd_flip.
Adopt either:

    sklearn.utils.extmath.svd_flip(u, v)
    or a custom canonical rule: “make the largest‑magnitude entry in each component positive.”

Pooling, weighting, and sentence/query embeddings

Mean pooling is a reasonable v0. But the strongest known low‑complexity upgrade is SIF weighting (Smooth Inverse Frequency): reweight token vectors by (a/(a+p(w))), then remove the top principal component of sentence embeddings. This is explicitly proposed as a tough baseline for sentence embeddings.

Practical default for SIF:

    (a \in [10^{-4}, 10^{-3}]) (tune lightly)
    remove 1–2 PCs (usually 1)

Storage formats and artifact hygiene

Sparse matrix storage. SciPy’s save_npz/load_npz are the simplest durable format for sparse matrices.
Use CSR or CSC for efficient multiplication; build in COO then convert to CSR.

Embedding storage. Store embeddings.npy as float32 for inference speed; keep float64 in training for greater numerical stability.

Metadata. Persist a small metadata.json containing:

    corpus identifier/hash
    tokenizer hash
    window parameters
    thresholds and smoothing constants
    SVD solver name + version string (SciPy/sklearn versions)
    (k) and (\alpha)

This is the difference between “deterministic in theory” and “auditable determinism in practice.”
Tokenization and unseen token strategy

The BPE tokenization choice is well aligned with modern subword practices (BPE in NLP popularized by Sennrich et al.; SentencePiece provides BPE/unigram tooling).

To virtually eliminate unknown tokens, byte‑level BPE can be adopted (base vocabulary covers 256 byte values), as widely used in modern LLM tokenizers; educational minimal implementations exist.
If switching tokenizers is not desired, the current BPE with a deterministic `<unk>` handling strategy is sufficient. FastText’s approach demonstrates why subword composition materially improves OOV behavior.
Reusable implementations and primary references
Open-source implementations worth reusing or cribbing from

The following are directly relevant to PNPMI/PPMI/SPPMI computation, sparse SVD, sign canonicalization, tokenization, and graph cost usage.

text

Matrix factorization / PMI pipelines
- hyperwords (updated fork): https://github.com/jfilter/hyperwords
- create_sppmi.py (SPPMI builder script): https://github.com/clips/dutchembeddings/blob/master/create_sppmi.py
- small SPPMI-SVD repo: https://github.com/a1da4/sppmi-svd

Sparse SVD + sign handling
- SciPy svds docs: https://docs.scipy.org/doc/scipy/reference/generated/scipy.sparse.linalg.svds.html
- scikit-learn TruncatedSVD: https://scikit-learn.org/stable/modules/generated/sklearn.decomposition.TruncatedSVD.html
- scikit-learn randomized_svd + flip_sign: https://scikit-learn.org/stable/modules/generated/sklearn.utils.extmath.randomized_svd.html
- scikit-learn svd_flip source: https://github.com/scikit-learn/scikit-learn/blob/main/sklearn/utils/extmath.py

Tokenization (BPE / subword)
- SentencePiece: https://github.com/google/sentencepiece
- minimal byte-level BPE reference: https://github.com/karpathy/minbpe

Reference embedding baselines
- SIF code: https://github.com/PrincetonML/SIF
- SIF mini demo: https://github.com/PrincetonML/SIF_mini_demo

Graph friction / shortest paths
- NetworkX shortest path docs: https://networkx.org/documentation/stable/reference/algorithms/shortest_paths.html

Predictive baselines (for comparison)
- GloVe code: https://github.com/stanfordnlp/GloVe
- word2vec code: https://github.com/tmikolov/word2vec
- fastText code: https://github.com/facebookresearch/fastText

Why these are the right targets: hyperwords and the SPPMI scripts are explicitly aligned with Levy & Goldberg’s SGNS↔SPPMI theory ; scikit‑learn’s flip_sign exists precisely to fix sign ambiguity deterministically ; SciPy’s sparse SVD and sparse save/load are the standard stack for sparse linear algebra artifacts ; SentencePiece and BPE references cover the practical tokenizer side ; NetworkX’s weighted shortest path APIs match the friction‑as‑cost usage in this pipeline .
Primary sources and canonical surveys

    LSA/LSI origin: Deerwester et al. (1990).
    Count‑based VSM survey: Turney & Pantel (2010).
    NPMI definition and motivation: Bouma (2009).
    PPMI and empirical design studies: Bullinaria & Levy (2007/2012 line).
    SGNS↔shifted PMI factorization: Levy & Goldberg (2014).
    Predictive co‑occurrence regression: GloVe (2014).
    Subword OOV handling: fastText (Bojanowski et al., 2017).
    Graph spectral embedding: Laplacian Eigenmaps (Belkin & Niyogi).
    Graph‑walk embeddings: DeepWalk, node2vec.
    Graph embedding matrix factorization unification: NetMF.
    Sentence pooling best‑practice: SIF.

Proposed pipeline and whitepaper updates

This section provides drop‑in replacements for the core math and the surrounding engineering story (what gets factorized vs what becomes a graph cost), plus pseudocode and a migration/test plan.
Pipeline stage timeline

Training   artifactsBPE   trainingtokenizer.jsonSliding-windowcountingtoken_counts   +pair_countsAssociation   buildPNPMI   (sparse)Spectral   compressionembeddings.npy   +sigma.npyTraversal   viewfriction   edges(optional)Query-time   inferenceEncodetoken_idsLookuptoken_vectorsPoolpooled_vectorNormalizecosine-readyembeddingDeterministic embedder lifecycle

Data object flow

mermaid

flowchart LR
  A[corpus/*.txt] --> B[BPE train]
  B --> C[tokenizer.json]

  A --> D[encode corpus with tokenizer]
  C --> D

  D --> E[pair_counts]
  D --> F[token_counts]

  E --> G[compute NPMI on observed pairs]
  F --> G

  G --> H[PNPMI sparse matrix (A)]
  H --> I[Truncated SVD]
  I --> J[U_k]
  I --> K[Sigma_k]
  J --> L[embeddings.npy]
  K --> M[sigma.npy]

  H --> N[friction graph edges (optional)]
  N --> O[graph traversal / pathfinding]

  C --> P[inference: BPE encode query]
  L --> Q[vector lookup]
  P --> Q
  Q --> R[pool + optional SIF + normalize]
  R --> S[query embedding]

Whitepaper math replacements for the core stages

The cleanest patch is to separate the factorized object from the traversal object, in line with how sparse matrix factorization pipelines are typically constructed (positive association matrix) and how weighted shortest paths are typically configured (cost graph).
Association stage (replace “friction matrix input to SVD”)

Define counts and probabilities as usual:

[ P(i)=\frac{\mathrm{count}(i)}{N_{\text{tokens}}} \qquad P(i,j)=\frac{\mathrm{count}(i,j)}{N_{\text{pairs}}} ]

[ \mathrm{PMI}(i,j)=\log\frac{P(i,j)}{P(i)P(j)} ]

[ \mathrm{NPMI}(i,j)=\frac{\mathrm{PMI}(i,j)}{-\log P(i,j)} ] Bouma’s normalization motivation and boundedness apply here.

Now define the factorization matrix (A) (sparse) as:

[ A_{ij}=\max\left(0, \mathrm{NPMI}(i,j)\right) \quad\text{for observed pairs with } \mathrm{count}(i,j)\ge c_{\min} ] and implicitly (A_{ij}=0) for all unobserved pairs.

This aligns the implicit zeros of sparse storage with “no positive semantic evidence,” matching standard best practice in PPMI‑family pipelines.

Optional alternative mode (SGNS parity):

[ A_{ij}=\max\left(0, \mathrm{PMI}(i,j)-\log k\right) \quad\text{(SPPMI)} ] which is directly motivated by Levy & Goldberg.
Spectral compression stage (replace “retain U only, ignore Σ”)

Compute truncated SVD:

[ A \approx U_k \Sigma_k V_k^\top ]

Then define embeddings:

[ E = U_k \Sigma_k^\alpha ]

Recommended default:

[ E = U_k \Sigma_k^{1/2} ]

This is consistent with variance‑aware representations used in LSA/LSI style embeddings, where Σ scaling preserves the relative importance of latent axes.
Determinism fix (add canonical sign)

Apply sign canonicalization after SVD (either via svd_flip or equivalent), because SVD vectors are only unique up to sign.

A simple canonical rule:

For each component (j), let (r = \arg\max_i |U_{ij}|). If (U_{rj} < 0), multiply column (j) of (U_k) by (-1) (and correspondingly flip the corresponding row of V_k if it is stored).
Friction graph stage (preserving the traversal concept without poisoning SVD)

Define friction only as a graph cost on selected edges:

[ \mathrm{friction}(i,j)=1-A_{ij} \quad\text{for }A_{ij}>0 ]

and treat unobserved pairs as no edge (or (+\infty) cost).

This matches the weighted shortest path convention that stronger relationships must mean smaller path weights.
Pseudocode for Sections 4–6

text

Inputs:
  token_counts[i], pair_counts[(i,j)], N_tokens, N_pairs
  params: c_min, k_dim, alpha, npmi_mode=True, shift_k=None
Outputs:
  embeddings E (V x k_dim), sigma (k_dim), optional friction_edges

1) Build sparse association A (COO lists)
  for (i,j), c_ij in pair_counts:
    if c_ij < c_min: continue
    p_i  = token_counts[i] / N_tokens
    p_j  = token_counts[j] / N_tokens
    p_ij = c_ij / N_pairs

    if npmi_mode:
       pmi  = log(p_ij / (p_i * p_j))
       npmi = pmi / (-log(p_ij))
       val  = max(0, npmi)                # PNPMI
    else:
       pmi  = log(p_ij / (p_i * p_j))
       val  = max(0, pmi - log(shift_k))  # SPPMI surrogate

    if val == 0: continue
    append (i, j, val) and (j, i, val) to COO lists

  A = sparse_matrix_from_coo(rows, cols, data).tocsr()

2) Truncated SVD
  (U, S, Vt) = truncated_svd(A, k=k_dim)   # SciPy svds or sklearn randomized_svd
  sort components so S is descending
  (U, Vt) = svd_flip(U, Vt)                # sign canonicalization

3) Build embeddings
  Sigma_alpha = diag(S ** alpha)
  E = U @ Sigma_alpha

  optionally: row-normalize E for cosine search

4) Build friction edges (optional)
  for each nonzero A[i,j]:
    cost = 1 - A[i,j]
    store edge (i, j, cost)

5) Save artifacts
  save embeddings.npy (float32)
  save sigma.npy
  save A as pnmi_matrix.npz (optional, training/debug)
  save friction_edges (optional)
  save metadata.json

Migration plan and test gates

A short migration plan that keeps the system auditable:

    Unit tests for matrix semantics
        Assert (A_{ij} \ge 0) and sparse implicit zeros are acceptable.
        Assert no “never observed” pair is stored as a nonzero, by construction.
    Determinism tests
        Run training twice with identical inputs and environment configuration; hash tokenizer.json, A.npz (if stored), sigma.npy, embeddings.npy.
        Verify identical outputs after svd_flip-style sign canonicalization.
    Solver behavior tests
        If using SciPy svds, explicitly sort singular values because SciPy documents non-guaranteed ordering.
    Artifact format tests
        Verify sparse save/load round trips with SciPy save_npz/load_npz.
    Retrieval sanity tests
        Nearest neighbor queries on known pairs: verify that strongly co‑occurring tokens move closer after SVD (sample from high PNPMI edges).
    Pooling upgrade optional tests
        If adding SIF: verify weights and PC removal match Arora et al.’s intended behavior.

These steps bring this pipeline into alignment with the strongest “count‑based + spectral” prior art while preserving the distinctive “friction graph as a traversal view” separation, which parallels broader graph embedding dualities (matrix factorization view vs shortest‑path / neighborhood view).

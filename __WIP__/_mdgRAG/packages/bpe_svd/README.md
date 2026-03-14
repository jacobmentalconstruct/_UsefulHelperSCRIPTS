# bpe-svd

**Deterministic text embeddings using BPE tokenization and SVD spectral compression.**

No GPU. No API. No model server. Same input always produces identical output.

```python
from bpe_svd import DeterministicEmbedProvider

provider = DeterministicEmbedProvider(
    tokenizer_path="tokenizer.json",
    embeddings_path="embeddings.npy",
)

result = provider.embed_texts(["hello world", "graph manifold"])
print(result.vectors[0][:5])   # [0.12, -0.34, 0.56, ...]

# Reverse: what tokens are closest to this vector?
nearest = provider.nearest_tokens(result.vectors[0], k=5)
for symbol, sim, _ in nearest:
    print(f"  {symbol:12s}  cos={sim:+.4f}")
```

## Install

```bash
# Inference only (numpy)
pip install bpe-svd

# Training pipeline (numpy + scipy)
pip install bpe-svd[training]
```

## Training Your Own Embeddings

```python
from bpe_svd.training import (
    BPETrainer,
    compute_counts,
    build_npmi_matrix,
    compute_embeddings,
)
import numpy as np

# Stage 1: Train BPE tokenizer
trainer = BPETrainer(vocab_size=5000)
trainer.train("path/to/corpus/")
trainer.save("tokenizer.json")

# Stage 2: Encode corpus and count co-occurrences
#   (encode your corpus into token streams using the trained tokenizer,
#    then pass the streams here)
pair_counts, token_counts = compute_counts(token_streams, window_size=5)

# Stage 3: Build NPMI friction matrix
friction = build_npmi_matrix(pair_counts, token_counts, vocab_size=5000)

# Stage 4: Compress to dense embeddings via SVD
embeddings = compute_embeddings(friction, k=300)
np.save("embeddings.npy", embeddings)
```

## How It Works

| Stage | Operation | Output |
|-------|-----------|--------|
| 1 | BPE tokenizer training | `tokenizer.json` |
| 2 | Sliding-window co-occurrence counting | `pair_counts`, `token_counts` |
| 3 | NPMI normalization → friction matrix | sparse (V × V) matrix |
| 4 | Truncated SVD | `embeddings.npy` (V × k) |
| Query | BPE encode → vector lookup → mean pool | k-dimensional vector |

For the full mathematical derivation see the
[BPE-SVD Whitepaper](../../docs/BPE_SVD_WHITEPAPER.md).

## Part of Graph Manifold

This package is extracted from the
[Graph Manifold](../../README.md) project — a deterministic,
graph-native knowledge retrieval system.

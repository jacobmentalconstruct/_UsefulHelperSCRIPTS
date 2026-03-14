"""
BPE Tokenizer Trainer — deterministic subword vocabulary builder.

Ownership: src/core/training/bpe_trainer.py
    Owns BPE merge training, corpus ingestion, and tokenizer.json
    serialisation. This is training-time only — produces the vocab and
    merge list consumed by the inference provider at query time.

Responsibilities:
    - Read plain-text corpus files
    - Build initial character-level vocabulary (with end-of-word marker)
    - Iteratively merge the most frequent adjacent symbol pair
    - Write tokenizer.json (vocab + merges + end_of_word)
    - Load an existing tokenizer.json back into memory

Design constraints:
    - No side effects at import time
    - Stdlib only (no numpy, no scipy)
    - Deterministic: same corpus always produces the same vocabulary
    - Single ownership: does not own co-occurrence counting or SVD

# Extracted from: _STUFF-TO-INTEGRATE/deterministic_embedder/tokenizer_trainer.py :: BPETokenizerTrainer
# Scope: training loop, corpus ingestion, JSON serialisation
# Rewritten per EXTRACTION_RULES.md — not verbatim copy
# API change: train() and save() are separated; load() added
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Tuple


@dataclass
class BPETrainer:
    """Deterministic Byte-Pair Encoding vocabulary trainer.

    Trains on a directory of .txt files and produces a tokenizer.json
    artifact that the inference provider uses to encode text at query time.

    Parameters
    ----------
    vocab_size : int
        Target maximum vocabulary size (characters + merged tokens).
    end_of_word : str
        Marker appended to every word before BPE encoding.  Must be a
        string that does not appear as a natural character in the corpus.
    """

    vocab_size: int = 5000
    end_of_word: str = "</w>"

    _vocab: Dict[str, int] = field(init=False, default_factory=dict)
    _merges: List[Tuple[str, str]] = field(init=False, default_factory=list)

    # ── Corpus ingestion ─────────────────────────────────────────────

    def _read_corpus(self, corpus_dir: str | Path) -> List[Tuple[str, ...]]:
        """Read all .txt files in corpus_dir into a list of symbol tuples."""
        words: List[Tuple[str, ...]] = []
        for root, _, files in os.walk(str(corpus_dir)):
            for fname in sorted(files):  # sorted for determinism
                if not fname.lower().endswith(".txt"):
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        for line in f:
                            for word in line.strip().split():
                                words.append(tuple(list(word) + [self.end_of_word]))
                except OSError:
                    continue
        return words

    def _init_vocab(self, words: List[Tuple[str, ...]]) -> None:
        """Build initial vocabulary from all unique symbols in the corpus."""
        vocab: Dict[str, int] = {}
        next_id = 0
        for word in words:
            for symbol in word:
                if symbol not in vocab:
                    vocab[symbol] = next_id
                    next_id += 1
        self._vocab = vocab

    # ── BPE merge loop ───────────────────────────────────────────────

    @staticmethod
    def _pair_frequencies(words: List[Tuple[str, ...]]) -> Dict[Tuple[str, str], int]:
        """Count frequency of every adjacent symbol pair across the corpus."""
        pairs: Dict[Tuple[str, str], int] = defaultdict(int)
        for word in words:
            for i in range(len(word) - 1):
                pairs[(word[i], word[i + 1])] += 1
        return pairs

    @staticmethod
    def _merge(pair: Tuple[str, str], words: List[Tuple[str, ...]]) -> List[Tuple[str, ...]]:
        """Replace every occurrence of pair (a, b) with the merged token 'ab'."""
        a, b = pair
        merged = a + b
        result: List[Tuple[str, ...]] = []
        for word in words:
            i = 0
            new_word: List[str] = []
            while i < len(word):
                if i < len(word) - 1 and word[i] == a and word[i + 1] == b:
                    new_word.append(merged)
                    i += 2
                else:
                    new_word.append(word[i])
                    i += 1
            result.append(tuple(new_word))
        return result

    # ── Public API ───────────────────────────────────────────────────

    def train(self, corpus_dir: str | Path) -> None:
        """Train BPE on all .txt files under corpus_dir.

        Builds the vocabulary and merge list in memory.  Call save() to
        write the result to disk.

        Parameters
        ----------
        corpus_dir : str | Path
            Directory containing training .txt files (scanned recursively).
        """
        self._vocab = {}
        self._merges = []
        words = self._read_corpus(corpus_dir)
        self._init_vocab(words)
        while len(self._vocab) < self.vocab_size:
            pair_freq = self._pair_frequencies(words)
            if not pair_freq:
                break
            best = max(pair_freq, key=pair_freq.get)  # type: ignore[arg-type]
            words = self._merge(best, words)
            self._merges.append(best)
            merged_token = best[0] + best[1]
            if merged_token not in self._vocab:
                self._vocab[merged_token] = len(self._vocab)

    def save(self, path: str | Path) -> None:
        """Write vocab + merges to a tokenizer.json file.

        Parameters
        ----------
        path : str | Path
            Destination file path.  Parent directories are created if needed.
        """
        if not self._vocab:
            raise RuntimeError("Nothing to save — call train() first.")
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        spec = {
            "vocab": self._vocab,
            "merges": list(self._merges),
            "end_of_word": self.end_of_word,
        }
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(spec, f, ensure_ascii=False, indent=2)

    def load(self, path: str | Path) -> None:
        """Load a previously saved tokenizer.json into this trainer instance.

        Parameters
        ----------
        path : str | Path
            Path to a tokenizer.json produced by save().
        """
        with open(str(path), "r", encoding="utf-8") as f:
            spec = json.load(f)
        self._vocab = {str(k): int(v) for k, v in spec["vocab"].items()}
        raw_merges = spec.get("merges", [])
        self._merges = [
            (m[0], m[1]) if isinstance(m, (list, tuple)) else (m[: len(m) // 2], m[len(m) // 2 :])
            for m in raw_merges
        ]
        self.end_of_word = spec.get("end_of_word", "</w>")

    @property
    def vocab(self) -> Dict[str, int]:
        """Learned vocabulary mapping (symbol → ID)."""
        return dict(self._vocab)

    @property
    def merges(self) -> List[Tuple[str, str]]:
        """Ordered merge list (applied sequentially during encoding)."""
        return list(self._merges)

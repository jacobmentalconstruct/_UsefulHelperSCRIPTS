# Legacy Source Notes

## Rules for Future Extraction Passes

1. The old project is **source material only** — never paste whole scripts
2. Extract only narrow, well-bounded functions or small dataclasses
3. Every extraction must record:
   - Source file path in legacy project
   - Function/class name extracted
   - Target module in this project
   - Date of extraction
4. If a function touches multiple ownership domains, do NOT extract it
5. Adapters in this directory are **temporary bridges**, not final homes

## Legacy Project Location

```
C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_DeterministicGraphRAG
```

## Extraction Log

| Date | Legacy Source File | Function/Class | Target Module | Notes |
|------|-------------------|----------------|---------------|-------|
| — | — | — | — | No extractions yet (Phase 1 is scaffold only) |
| Phase 12 | `_STUFF-TO-INTEGRATE/deterministic_embedder/inference_engine.py` | `DeterministicEmbedder` (BPE encoding + vector lookup + mean pooling) | `src/core/model_bridge/deterministic_provider.py` | Inference-side only. Rewritten per EXTRACTION_RULES.md. Training pipeline (tokenizer, co-occurrence, PMI, SVD) is separate. |
| Phase 12.2 | `_STUFF-TO-INTEGRATE/deterministic_embedder/tokenizer_trainer.py` | `BPETokenizerTrainer` (BPE merge training loop, corpus ingestion, tokenizer.json I/O) | `src/core/training/bpe_trainer.py` | Renamed to `BPETrainer`. API split: `train()` and `save()` separated; `load()` added. Rewritten per EXTRACTION_RULES.md. |
| Phase 12.2 | `_STUFF-TO-INTEGRATE/deterministic_embedder/cooccurrence_graph.py` | `sliding_window_cooccurrence`, `compute_counts` (sliding window co-occurrence statistics) | `src/core/training/cooccurrence.py` | `BPETokenizer` class dropped — single-ownership violation; callers now pass pre-tokenised streams. `compute_counts()` signature updated accordingly. Rewritten per EXTRACTION_RULES.md. |
| Phase 12.2 | `_STUFF-TO-INTEGRATE/deterministic_embedder/pmi_matrix.py` | `build_npmi_matrix` (NPMI normalisation + friction transformation + sparse CSR matrix) | `src/core/training/npmi_matrix.py` | Renamed module (`pmi_matrix` → `npmi_matrix`) for precision. Algorithm unchanged. Rewritten per EXTRACTION_RULES.md. |
| Phase 12.2 | `_STUFF-TO-INTEGRATE/deterministic_embedder/spectral_compression.py` | `compute_embeddings` (truncated SVD via scipy.sparse.linalg.svds) | `src/core/training/spectral.py` | Added zero-padding guard for k > effective dims (handles tiny test matrices). Rewritten per EXTRACTION_RULES.md. |
| Phase 13 | `_TripartiteDataSTORE/src/config.py` | Extension sets (CODE_EXTENSIONS, PROSE_EXTENSIONS, etc.), skip lists, chunking constants | `src/core/ingestion/config.py` | Extension mappings and skip lists extracted. Model registry and entity extraction config excluded (not applicable). Rewritten per EXTRACTION_RULES.md. |
| Phase 13 | `_TripartiteDataSTORE/src/chunkers/treesitter.py` | LANGUAGE_TIERS dict, FUNCTION_QUERIES/CLASS_QUERIES/IMPORT_QUERIES dicts, 4-tier chunking strategies (hierarchical, flat, structural, markup), fallback line chunker | `src/core/ingestion/tree_sitter_chunker.py` + `src/core/ingestion/config.py` | Class-based architecture converted to functional. SpanRef/Chunk model replaced with RawChunk dataclass. Rewritten per EXTRACTION_RULES.md. |
| Phase 13 | `_TripartiteDataSTORE/src/chunkers/prose.py` | Two-pass heading/paragraph splitter, sliding window, summary chunk | `src/core/ingestion/chunking.py` | Class-based ProseChunker converted to `chunk_prose()` function. SpanRef model replaced with line_start/line_end. Rewritten per EXTRACTION_RULES.md. |
| Phase 13 | `_TripartiteDataSTORE/src/pipeline/detect.py` | SourceFile dataclass, detect(), walk_source() | `src/core/ingestion/detection.py` | External config imports replaced with local config.py. External utils replaced with inline implementations. Rewritten per EXTRACTION_RULES.md. |

"""
wasm_modules_spec.py
Specification and Python reference implementations for each WASM headless module.
Each is pure compute — no I/O, no DB, no network. Perfect WASM candidates.

Build path: compile to .wasm via Emscripten or wasi-sdk, expose via JS/Python bridge.
Each module maps to a microservice endpoint that can delegate to WASM for hot-path perf.
"""

# ---------------------------------------------------------------------------
# 1. blake3_hasher.wasm
#    Maps to: Blake3HashMS.hash_content / hash_bytes
#    Input:  bytes
#    Output: 32-byte hex string
#    Why WASM: pure CPU, no deps, called millions of times during ingest
# ---------------------------------------------------------------------------

def blake3_hasher_reference(data: bytes) -> str:
    """Python reference. WASM version runs same logic in C."""
    import hashlib
    return hashlib.sha3_256(data).hexdigest()


# ---------------------------------------------------------------------------
# 2. merkle_root.wasm
#    Maps to: MerkleRootMS.build_tree / combine_cids
#    Input:  list of hex CID strings
#    Output: single root hex string
#    Why WASM: tree building is pure recursive hashing, no state
# ---------------------------------------------------------------------------

def merkle_root_reference(leaves: list) -> str:
    import hashlib
    level = list(leaves)
    while len(level) > 1:
        if len(level) % 2 == 1:
            level.append(level[-1])
        level = [hashlib.sha3_256((level[i] + level[i+1]).encode()).hexdigest()
                 for i in range(0, len(level), 2)]
    return level[0] if level else ''


# ---------------------------------------------------------------------------
# 3. cosine_similarity.wasm
#    Maps to: SemanticSearchMS / EmbedUtilsMS cosine ops
#    Input:  two float32 arrays of equal length
#    Output: float score 0.0..1.0
#    Why WASM: called for every vector pair in search, hot inner loop
# ---------------------------------------------------------------------------

def cosine_similarity_reference(a: list, b: list) -> float:
    import math
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(y*y for y in b))
    return dot / (na * nb) if na and nb else 0.0


# ---------------------------------------------------------------------------
# 4. interval_query.wasm
#    Maps to: IntervalIndexMS span queries
#    Input:  array of (start, end, id) tuples + query point or range
#    Output: list of matching span IDs
#    Why WASM: pure range math, can sort and binary search in C
# ---------------------------------------------------------------------------

def interval_query_reference(spans: list, query_start: int, query_end: int) -> list:
    """Return span IDs that overlap with [query_start, query_end]."""
    return [s['span_id'] for s in spans
            if s['line_start'] <= query_end and s['line_end'] >= query_start]


# ---------------------------------------------------------------------------
# 5. ast_tier_classifier.wasm
#    Maps to: ReferenceTreeSitterStrategyMS.classify_file
#    Input:  file extension string
#    Output: {language, tier, chunk_strategy} dict
#    Why WASM: pure lookup table, useful in browser-side tooling
# ---------------------------------------------------------------------------

EXTENSION_TIER_MAP = {
    '.py': ('python', 'deep_semantic', 'hierarchical'),
    '.js': ('javascript', 'deep_semantic', 'hierarchical'),
    '.ts': ('typescript', 'deep_semantic', 'hierarchical'),
    '.rs': ('rust', 'deep_semantic', 'hierarchical'),
    '.go': ('go', 'deep_semantic', 'hierarchical'),
    '.java': ('java', 'deep_semantic', 'hierarchical'),
    '.sh': ('bash', 'shallow_semantic', 'flat'),
    '.rb': ('ruby', 'shallow_semantic', 'flat'),
    '.json': ('json', 'structural', 'structural'),
    '.yaml': ('yaml', 'structural', 'structural'),
    '.toml': ('toml', 'structural', 'structural'),
    '.html': ('html', 'hybrid', 'markup'),
    '.css': ('css', 'hybrid', 'markup'),
}

def ast_tier_classifier_reference(extension: str) -> dict:
    entry = EXTENSION_TIER_MAP.get(extension.lower(), ('unknown', 'shallow_semantic', 'flat'))
    return {'language': entry[0], 'tier': entry[1], 'chunk_strategy': entry[2]}


# ---------------------------------------------------------------------------
# 6. trie_lookup.wasm
#    Maps to: LexicalIndexMS.prefix_search
#    Input:  sorted term list + prefix string
#    Output: matching terms
#    Why WASM: binary search over sorted array, zero I/O
# ---------------------------------------------------------------------------

def trie_lookup_reference(sorted_terms: list, prefix: str) -> list:
    prefix = prefix.lower()
    return [t for t in sorted_terms if t.startswith(prefix)]


# ---------------------------------------------------------------------------
# 7. property_graph_schema.wasm
#    Maps to: PropertyGraphMS schema validation before write
#    Input:  node or edge dict
#    Output: {valid: bool, errors: list}
#    Why WASM: runs client-side before hitting DB, pure validation logic
# ---------------------------------------------------------------------------

def property_graph_schema_reference(record: dict, record_type: str = 'node') -> dict:
    errors = []
    if record_type == 'node':
        if not record.get('node_id'):
            errors.append('node_id required')
        if not isinstance(record.get('props', {}), dict):
            errors.append('props must be a dict')
    elif record_type == 'edge':
        if not record.get('src'):
            errors.append('src required')
        if not record.get('dst'):
            errors.append('dst required')
    return {'valid': len(errors) == 0, 'errors': errors}


# ---------------------------------------------------------------------------
# BUILD NOTES
# ---------------------------------------------------------------------------
#
# To compile any of these to WASM:
#
#   1. Rewrite reference function in C or Rust
#   2. Compile:
#      - C via Emscripten:   emcc module.c -o module.wasm -s WASM=1 -O3
#      - Rust via wasm-pack: wasm-pack build --target web
#   3. Expose via JS:
#      const mod = await WebAssembly.instantiateStreaming(fetch('module.wasm'))
#      const result = mod.instance.exports.cosine_similarity(ptr_a, ptr_b, len)
#   4. Or via Python wasmtime:
#      from wasmtime import Store, Module, Instance
#      store = Store(); module = Module.from_file(store.engine, 'module.wasm')
#
# Priority build order (hottest paths first):
#   1. cosine_similarity.wasm    — called every search
#   2. blake3_hasher.wasm        — called every ingest line
#   3. merkle_root.wasm          — called every commit
#   4. interval_query.wasm       — called every positional lookup
#   5. ast_tier_classifier.wasm  — called every file detect
#   6. trie_lookup.wasm          — called every autocomplete
#   7. property_graph_schema.wasm — called every graph write

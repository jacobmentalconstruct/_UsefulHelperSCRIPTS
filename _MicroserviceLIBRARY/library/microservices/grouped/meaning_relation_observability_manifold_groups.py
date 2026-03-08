"""
meaning_relation_observability_manifold_groups.py
Four manager groups in one file:
  - MeaningManager:       SemanticSearchMS, LexicalIndexMS, OntologyMS
  - RelationManager:      PropertyGraphMS, IdentityAnchorMS
  - ObservabilityManager: LayerHealthMS, WalkerTraceMS
  - ManifoldManager:      CrossLayerResolverMS, ManifoldProjectorMS, HypergraphMS
"""

import json
import math
import sqlite3
import struct
import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_metadata, service_endpoint


# ===========================================================================
# MEANING GROUP
# ===========================================================================

@service_metadata(
    name='SemanticSearchMS',
    version='1.0.0',
    description='Cosine similarity search over SQLite-stored chunk embeddings.',
    tags=['meaning', 'semantic', 'vector', 'search'],
    capabilities=['db:read'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class SemanticSearchMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _unpack(self, blob: bytes) -> List[float]:
        if not blob:
            return []
        return list(struct.unpack(f'<{len(blob)//4}f', blob))

    def _cosine(self, a: List[float], b: List[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x*y for x, y in zip(a, b))
        na = math.sqrt(sum(x*x for x in a))
        nb = math.sqrt(sum(y*y for y in b))
        return dot / (na * nb) if na and nb else 0.0

    @service_endpoint(inputs={'db_path': 'str', 'query_vector': 'list', 'limit': 'int'}, outputs={'results': 'list'}, description='Top-k cosine similarity search over chunk embeddings.', tags=['semantic', 'search'])
    def search(self, db_path: str, query_vector: List[float], limit: int = 10) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT chunk_id, embedding FROM chunk_embeddings').fetchall()
            scored = [{'chunk_id': r['chunk_id'], 'score': self._cosine(query_vector, self._unpack(r['embedding']))} for r in rows]
            scored.sort(key=lambda x: x['score'], reverse=True)
            return scored[:max(1, limit)]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'chunk_id_a': 'str', 'chunk_id_b': 'str'}, outputs={'score': 'float'}, description='Compare two stored chunk embeddings directly.', tags=['semantic', 'compare'])
    def compare_chunks(self, db_path: str, chunk_id_a: str, chunk_id_b: str) -> float:
        conn = self._open(db_path)
        try:
            def get_vec(cid):
                row = conn.execute('SELECT embedding FROM chunk_embeddings WHERE chunk_id = ?', (cid,)).fetchone()
                return self._unpack(row['embedding']) if row else []
            return self._cosine(get_vec(chunk_id_a), get_vec(chunk_id_b))
        finally:
            conn.close()

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ---------------------------------------------------------------------------

@service_metadata(
    name='LexicalIndexMS',
    version='1.0.0',
    description='Token-level surface form index. Prefix search and n-gram matching over stored terms.',
    tags=['meaning', 'lexical', 'trie', 'ngram'],
    capabilities=['compute', 'db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class LexicalIndexMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS lexical_terms (
            term      TEXT PRIMARY KEY,
            node_id   TEXT,
            frequency INTEGER DEFAULT 1
        )''')
        conn.commit()
        return conn

    @service_endpoint(inputs={'db_path': 'str', 'terms': 'list', 'node_id': 'str'}, outputs={'indexed': 'int'}, description='Index a list of terms for a node.', tags=['lexical', 'write'], side_effects=['db:write'])
    def index_terms(self, db_path: str, terms: List[str], node_id: str) -> int:
        conn = self._open(db_path)
        try:
            for term in terms:
                conn.execute('INSERT INTO lexical_terms (term, node_id, frequency) VALUES (?, ?, 1) ON CONFLICT(term) DO UPDATE SET frequency = frequency + 1', (term.lower(), node_id))
            conn.commit()
            return len(terms)
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'prefix': 'str', 'limit': 'int'}, outputs={'matches': 'list'}, description='Prefix search over indexed terms.', tags=['lexical', 'search'])
    def prefix_search(self, db_path: str, prefix: str, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT term, node_id, frequency FROM lexical_terms WHERE term LIKE ? ORDER BY frequency DESC LIMIT ?', (prefix.lower() + '%', limit)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'text': 'str', 'n': 'int'}, outputs={'ngrams': 'list'}, description='Generate n-grams from text for fuzzy surface matching.', tags=['lexical', 'ngram'])
    def ngrams(self, text: str, n: int = 3) -> List[str]:
        tokens = text.lower().split()
        return [' '.join(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ---------------------------------------------------------------------------

@service_metadata(
    name='OntologyMS',
    version='1.0.0',
    description='IS-A class/type/kind hierarchy. Register types, resolve inheritance, check membership.',
    tags=['meaning', 'ontology', 'taxonomy', 'isa'],
    capabilities=['compute', 'db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class OntologyMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS ontology_types (
            type_id   TEXT PRIMARY KEY,
            parent_id TEXT,
            label     TEXT
        )''')
        conn.commit()
        return conn

    @service_endpoint(inputs={'db_path': 'str', 'type_id': 'str', 'parent_id': 'str', 'label': 'str'}, outputs={'ok': 'bool'}, description='Register a type with optional parent.', tags=['ontology', 'write'], side_effects=['db:write'])
    def register_type(self, db_path: str, type_id: str, parent_id: str = '', label: str = '') -> bool:
        conn = self._open(db_path)
        try:
            conn.execute('INSERT OR REPLACE INTO ontology_types (type_id, parent_id, label) VALUES (?, ?, ?)', (type_id, parent_id or None, label))
            conn.commit()
            return True
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'type_id': 'str'}, outputs={'ancestors': 'list'}, description='Walk all ancestors of a type in the IS-A hierarchy.', tags=['ontology', 'query'])
    def get_ancestors(self, db_path: str, type_id: str) -> List[str]:
        conn = self._open(db_path)
        visited, current = [], type_id
        try:
            while current:
                row = conn.execute('SELECT parent_id FROM ontology_types WHERE type_id = ?', (current,)).fetchone()
                if not row or not row['parent_id']:
                    break
                visited.append(row['parent_id'])
                current = row['parent_id']
            return visited
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'type_id': 'str', 'candidate_ancestor': 'str'}, outputs={'is_a': 'bool'}, description='Check if type_id IS-A candidate_ancestor.', tags=['ontology', 'query'])
    def is_a(self, db_path: str, type_id: str, candidate_ancestor: str) -> bool:
        return candidate_ancestor in self.get_ancestors(db_path, type_id)

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ===========================================================================
# RELATION GROUP
# ===========================================================================

@service_metadata(
    name='PropertyGraphMS',
    version='1.0.0',
    description='SQLite-backed property graph. Nodes and edges carry named attribute dicts. Foundation for identity anchoring.',
    tags=['relation', 'property-graph', 'identity', 'graph'],
    capabilities=['db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class PropertyGraphMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS pg_nodes (
            node_id    TEXT PRIMARY KEY,
            node_type  TEXT,
            props_json TEXT
        )''')
        conn.execute('''CREATE TABLE IF NOT EXISTS pg_edges (
            edge_id    TEXT PRIMARY KEY,
            src        TEXT NOT NULL,
            dst        TEXT NOT NULL,
            edge_type  TEXT,
            props_json TEXT
        )''')
        conn.commit()
        return conn

    @service_endpoint(inputs={'db_path': 'str', 'node_id': 'str', 'node_type': 'str', 'props': 'dict'}, outputs={'ok': 'bool'}, description='Upsert a node with named properties.', tags=['pg', 'write'], side_effects=['db:write'])
    def upsert_node(self, db_path: str, node_id: str, node_type: str = '', props: Dict = None) -> bool:
        conn = self._open(db_path)
        try:
            conn.execute('INSERT OR REPLACE INTO pg_nodes (node_id, node_type, props_json) VALUES (?, ?, ?)',
                         (node_id, node_type, json.dumps(props or {})))
            conn.commit()
            return True
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'src': 'str', 'dst': 'str', 'edge_type': 'str', 'props': 'dict'}, outputs={'edge_id': 'str'}, description='Upsert a typed edge with properties.', tags=['pg', 'write'], side_effects=['db:write'])
    def upsert_edge(self, db_path: str, src: str, dst: str, edge_type: str = 'RELATES_TO', props: Dict = None) -> str:
        edge_id = f'{edge_type}:{src}:{dst}'
        conn = self._open(db_path)
        try:
            conn.execute('INSERT OR REPLACE INTO pg_edges (edge_id, src, dst, edge_type, props_json) VALUES (?, ?, ?, ?, ?)',
                         (edge_id, src, dst, edge_type, json.dumps(props or {})))
            conn.commit()
            return edge_id
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'node_id': 'str'}, outputs={'node': 'dict'}, description='Fetch a node with its properties.', tags=['pg', 'read'])
    def get_node(self, db_path: str, node_id: str) -> Optional[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            row = conn.execute('SELECT * FROM pg_nodes WHERE node_id = ?', (node_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d['props'] = json.loads(d.pop('props_json', '{}'))
            return d
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'node_id': 'str', 'edge_type': 'str'}, outputs={'neighbors': 'list'}, description='Get neighbors filtered by edge type.', tags=['pg', 'query'])
    def get_neighbors(self, db_path: str, node_id: str, edge_type: str = '') -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            if edge_type:
                rows = conn.execute('SELECT dst, edge_type, props_json FROM pg_edges WHERE src = ? AND edge_type = ?', (node_id, edge_type)).fetchall()
            else:
                rows = conn.execute('SELECT dst, edge_type, props_json FROM pg_edges WHERE src = ?', (node_id,)).fetchall()
            return [{'node_id': r['dst'], 'edge_type': r['edge_type'], 'props': json.loads(r['props_json'] or '{}')} for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'prop_key': 'str', 'prop_value': 'str'}, outputs={'nodes': 'list'}, description='Find nodes where a named property matches a value.', tags=['pg', 'query'])
    def find_by_property(self, db_path: str, prop_key: str, prop_value: str) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT node_id, node_type, props_json FROM pg_nodes').fetchall()
            results = []
            for row in rows:
                props = json.loads(row['props_json'] or '{}')
                if str(props.get(prop_key, '')) == prop_value:
                    results.append({'node_id': row['node_id'], 'node_type': row['node_type'], 'props': props})
            return results
        finally:
            conn.close()

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ---------------------------------------------------------------------------

@service_metadata(
    name='IdentityAnchorMS',
    version='1.0.0',
    description='Computes and assigns stable identity positions to artifacts. Anchors cross-layer identity using property graph.',
    tags=['relation', 'identity', 'anchor', 'property-graph'],
    capabilities=['compute', 'db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib', 'PropertyGraphMS', 'Blake3HashMS'],
    external_dependencies=[],
)
class IdentityAnchorMS:
    def __init__(self):
        self.start_time = time.time()
        self._pg = PropertyGraphMS()

    @service_endpoint(
        inputs={'db_path': 'str', 'artifact_id': 'str', 'layer_refs': 'dict', 'stable_props': 'dict'},
        outputs={'anchor_id': 'str'},
        description='Anchor an artifact by registering its presence across layers as named properties on a pg node.',
        tags=['identity', 'anchor'],
        side_effects=['db:write']
    )
    def anchor(self, db_path: str, artifact_id: str, layer_refs: Dict[str, str], stable_props: Dict[str, Any] = None) -> str:
        props = dict(stable_props or {})
        props.update({f'layer_{k}': v for k, v in layer_refs.items()})
        props['anchor_id'] = artifact_id
        self._pg.upsert_node(db_path, artifact_id, node_type='anchor', props=props)
        return artifact_id

    @service_endpoint(inputs={'db_path': 'str', 'artifact_id': 'str'}, outputs={'anchor': 'dict'}, description='Retrieve the full identity anchor for an artifact.', tags=['identity', 'read'])
    def get_anchor(self, db_path: str, artifact_id: str) -> Optional[Dict[str, Any]]:
        return self._pg.get_node(db_path, artifact_id)

    @service_endpoint(inputs={'db_path': 'str', 'prop_key': 'str', 'prop_value': 'str'}, outputs={'matches': 'list'}, description='Resolve identity by searching anchors for a property match.', tags=['identity', 'resolve'])
    def resolve_by_property(self, db_path: str, prop_key: str, prop_value: str) -> List[Dict[str, Any]]:
        return self._pg.find_by_property(db_path, prop_key, prop_value)

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ===========================================================================
# OBSERVABILITY GROUP
# ===========================================================================

@service_metadata(
    name='LayerHealthMS',
    version='1.0.0',
    description='Polls all registered services via registry, aggregates health status across layers.',
    tags=['observability', 'health', 'monitoring'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class LayerHealthMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'registry': 'object'}, outputs={'report': 'dict'}, description='Poll all services in registry and return aggregated health report.', tags=['health', 'monitor'])
    def poll_all(self, registry) -> Dict[str, Any]:
        results = registry.health_all()
        online = sum(1 for v in results.values() if v.get('status') == 'online')
        return {
            'total': len(results),
            'online': online,
            'degraded': len(results) - online,
            'services': results,
        }

    @service_endpoint(inputs={'registry': 'object', 'tag': 'str'}, outputs={'report': 'dict'}, description='Poll only services matching a tag.', tags=['health', 'monitor'])
    def poll_by_tag(self, registry, tag: str) -> Dict[str, Any]:
        names = registry.list_by_tag(tag)
        report = {}
        for name in names:
            inst = registry.get(name)
            if inst:
                try:
                    report[name] = inst.get_health()
                except Exception as e:
                    report[name] = {'status': 'error', 'error': str(e)}
        return report

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ---------------------------------------------------------------------------

@service_metadata(
    name='WalkerTraceMS',
    version='1.0.0',
    description='Record, store, and replay node walker pilgrimages for debugging and audit.',
    tags=['observability', 'walker', 'trace', 'debug'],
    capabilities=['db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class WalkerTraceMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS walker_traces (
            trace_id   TEXT PRIMARY KEY,
            query_text TEXT,
            steps_json TEXT,
            result_json TEXT,
            created_at REAL
        )''')
        conn.commit()
        return conn

    @service_endpoint(inputs={'db_path': 'str', 'trace_id': 'str', 'query_text': 'str', 'steps': 'list', 'result': 'dict'}, outputs={'ok': 'bool'}, description='Record a completed walker trace.', tags=['trace', 'write'], side_effects=['db:write'])
    def record_trace(self, db_path: str, trace_id: str, query_text: str, steps: List[Any], result: Dict[str, Any]) -> bool:
        conn = self._open(db_path)
        try:
            conn.execute('INSERT OR REPLACE INTO walker_traces (trace_id, query_text, steps_json, result_json, created_at) VALUES (?, ?, ?, ?, ?)',
                         (trace_id, query_text, json.dumps(steps), json.dumps(result), time.time()))
            conn.commit()
            return True
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'trace_id': 'str'}, outputs={'trace': 'dict'}, description='Retrieve a stored trace by ID.', tags=['trace', 'read'])
    def get_trace(self, db_path: str, trace_id: str) -> Optional[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            row = conn.execute('SELECT * FROM walker_traces WHERE trace_id = ?', (trace_id,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d['steps'] = json.loads(d.pop('steps_json', '[]'))
            d['result'] = json.loads(d.pop('result_json', '{}'))
            return d
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'limit': 'int'}, outputs={'traces': 'list'}, description='List recent traces.', tags=['trace', 'read'])
    def list_recent(self, db_path: str, limit: int = 20) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT trace_id, query_text, created_at FROM walker_traces ORDER BY created_at DESC LIMIT ?', (limit,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ===========================================================================
# MANIFOLD GROUP
# ===========================================================================

@service_metadata(
    name='CrossLayerResolverMS',
    version='1.0.0',
    description='Given a CID or node_id, fetch its presence and data across all available layers.',
    tags=['manifold', 'cross-layer', 'resolver'],
    capabilities=['db:read'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class CrossLayerResolverMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'db_path': 'str', 'artifact_id': 'str'}, outputs={'presence': 'dict'}, description='Check and return artifact presence across all layers.', tags=['resolver', 'cross-layer'])
    def resolve(self, db_path: str, artifact_id: str) -> Dict[str, Any]:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        presence = {}
        try:
            for table, id_col in [
                ('verbatim_lines', 'line_cid'),
                ('chunk_manifest', 'chunk_id'),
                ('graph_nodes', 'node_id'),
                ('pg_nodes', 'node_id'),
                ('chunk_embeddings', 'chunk_id'),
            ]:
                try:
                    row = conn.execute(f'SELECT * FROM {table} WHERE {id_col} = ?', (artifact_id,)).fetchone()
                    presence[table] = dict(row) if row else None
                except Exception:
                    presence[table] = None
        finally:
            conn.close()
        return {'artifact_id': artifact_id, 'presence': presence}

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ---------------------------------------------------------------------------

@service_metadata(
    name='ManifoldProjectorMS',
    version='1.0.0',
    description='Transient lens — project a query across all layers in working memory without writing. Returns scored evidence per layer.',
    tags=['manifold', 'projector', 'transient', 'lens'],
    capabilities=['db:read'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib', 'SemanticSearchMS', 'CrossLayerResolverMS'],
    external_dependencies=[],
)
class ManifoldProjectorMS:
    def __init__(self):
        self.start_time = time.time()
        self._semantic = SemanticSearchMS()
        self._resolver = CrossLayerResolverMS()

    @service_endpoint(
        inputs={'db_path': 'str', 'query_vector': 'list', 'query_text': 'str', 'top_k': 'int'},
        outputs={'projection': 'dict'},
        description='Project query into manifold space. Returns top-k semantic hits enriched with cross-layer presence. Nothing is written.',
        tags=['projector', 'lens', 'transient']
    )
    def project(self, db_path: str, query_vector: List[float], query_text: str = '', top_k: int = 10) -> Dict[str, Any]:
        semantic_hits = self._semantic.search(db_path, query_vector, limit=top_k)
        enriched = []
        for hit in semantic_hits:
            presence = self._resolver.resolve(db_path, hit['chunk_id'])
            enriched.append({
                'chunk_id': hit['chunk_id'],
                'semantic_score': hit['score'],
                'layer_presence': presence['presence'],
            })
        return {
            'query_text': query_text,
            'top_k': top_k,
            'hits': enriched,
            'transient': True,
        }

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ---------------------------------------------------------------------------

@service_metadata(
    name='HypergraphMS',
    version='1.0.0',
    description='Hypergraph where one hyperedge connects nodes across multiple layers simultaneously. Encodes superposition — multiple simultaneous truths about one artifact.',
    tags=['manifold', 'hypergraph', 'superposition', 'cross-layer'],
    capabilities=['db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class HypergraphMS:
    """
    A hyperedge is a named set of (layer, node_id) pairs.
    One hyperedge says: these nodes across these layers are all the same artifact.
    This is the connective tissue that makes the four layers one manifold.
    """

    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS hyperedges (
            edge_id    TEXT NOT NULL,
            layer      TEXT NOT NULL,
            node_id    TEXT NOT NULL,
            label      TEXT,
            PRIMARY KEY (edge_id, layer, node_id)
        )''')
        conn.commit()
        return conn

    @service_endpoint(
        inputs={'db_path': 'str', 'edge_id': 'str', 'members': 'list', 'label': 'str'},
        outputs={'ok': 'bool'},
        description='Create or extend a hyperedge. members = list of {layer, node_id} dicts.',
        tags=['hypergraph', 'write'],
        side_effects=['db:write']
    )
    def upsert_hyperedge(self, db_path: str, edge_id: str, members: List[Dict[str, str]], label: str = '') -> bool:
        conn = self._open(db_path)
        try:
            for m in members:
                conn.execute('INSERT OR IGNORE INTO hyperedges (edge_id, layer, node_id, label) VALUES (?, ?, ?, ?)',
                             (edge_id, m['layer'], m['node_id'], label))
            conn.commit()
            return True
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'edge_id': 'str'}, outputs={'members': 'list'}, description='Get all members of a hyperedge across layers.', tags=['hypergraph', 'read'])
    def get_hyperedge(self, db_path: str, edge_id: str) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT layer, node_id, label FROM hyperedges WHERE edge_id = ?', (edge_id,)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'node_id': 'str', 'layer': 'str'}, outputs={'edges': 'list'}, description='Find all hyperedges that include a given node.', tags=['hypergraph', 'query'])
    def edges_for_node(self, db_path: str, node_id: str, layer: str = '') -> List[str]:
        conn = self._open(db_path)
        try:
            if layer:
                rows = conn.execute('SELECT DISTINCT edge_id FROM hyperedges WHERE node_id = ? AND layer = ?', (node_id, layer)).fetchall()
            else:
                rows = conn.execute('SELECT DISTINCT edge_id FROM hyperedges WHERE node_id = ?', (node_id,)).fetchall()
            return [r['edge_id'] for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'node_id_a': 'str', 'node_id_b': 'str'}, outputs={'shared_edges': 'list'}, description='Find hyperedges that contain both nodes — cross-layer co-membership.', tags=['hypergraph', 'query'])
    def co_membership(self, db_path: str, node_id_a: str, node_id_b: str) -> List[str]:
        edges_a = set(self.edges_for_node(db_path, node_id_a))
        edges_b = set(self.edges_for_node(db_path, node_id_b))
        return list(edges_a & edges_b)

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

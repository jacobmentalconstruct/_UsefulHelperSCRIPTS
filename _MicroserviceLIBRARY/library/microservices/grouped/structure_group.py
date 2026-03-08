"""
structure_group.py
StructureManager microservice group.
Covers: DAG ops, Positional/interval index, Directional/flow graph.
AST/tree-sitter services already exist as reference MSes — see
_ReferencePythonAstChunkerMS, _ReferenceTreeSitterStrategyMS, _ReferenceTreeSitterQueryRegistryMS.
"""

import sqlite3
import time
from typing import Any, Dict, List, Optional, Tuple

from microservice_std_lib import service_metadata, service_endpoint


# ---------------------------------------------------------------------------
# DagOpsMS
# ---------------------------------------------------------------------------

@service_metadata(
    name='DagOpsMS',
    version='1.0.0',
    description='Create and operate on a SQLite-backed DAG. Insert nodes/edges, walk, topological sort, subtree extraction.',
    tags=['structure', 'dag', 'graph'],
    capabilities=['db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class DagOpsMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn

    @service_endpoint(inputs={'db_path': 'str'}, outputs={'ok': 'bool'}, description='Ensure DAG tables exist (idempotent).', tags=['dag', 'init'], side_effects=['db:write'])
    def ensure_schema(self, db_path: str) -> bool:
        conn = self._open(db_path)
        try:
            conn.execute('''CREATE TABLE IF NOT EXISTS dag_nodes (
                node_id   TEXT PRIMARY KEY,
                node_type TEXT,
                label     TEXT,
                meta_json TEXT
            )''')
            conn.execute('''CREATE TABLE IF NOT EXISTS dag_edges (
                edge_id   TEXT PRIMARY KEY,
                src       TEXT NOT NULL,
                dst       TEXT NOT NULL,
                edge_type TEXT,
                weight    REAL DEFAULT 1.0
            )''')
            conn.commit()
            return True
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'node_id': 'str', 'node_type': 'str', 'label': 'str', 'meta': 'dict'}, outputs={'ok': 'bool'}, description='Upsert a node into the DAG.', tags=['dag', 'write'], side_effects=['db:write'])
    def upsert_node(self, db_path: str, node_id: str, node_type: str = '', label: str = '', meta: Dict = None) -> bool:
        import json
        conn = self._open(db_path)
        try:
            conn.execute('INSERT OR REPLACE INTO dag_nodes (node_id, node_type, label, meta_json) VALUES (?, ?, ?, ?)',
                         (node_id, node_type, label, json.dumps(meta or {})))
            conn.commit()
            return True
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'src': 'str', 'dst': 'str', 'edge_type': 'str', 'weight': 'float'}, outputs={'edge_id': 'str'}, description='Insert a directed edge between two nodes.', tags=['dag', 'write'], side_effects=['db:write'])
    def insert_edge(self, db_path: str, src: str, dst: str, edge_type: str = 'CONTAINS', weight: float = 1.0) -> str:
        edge_id = f'{edge_type}:{src}:{dst}'
        conn = self._open(db_path)
        try:
            conn.execute('INSERT OR IGNORE INTO dag_edges (edge_id, src, dst, edge_type, weight) VALUES (?, ?, ?, ?, ?)',
                         (edge_id, src, dst, edge_type, weight))
            conn.commit()
            return edge_id
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'node_id': 'str'}, outputs={'children': 'list'}, description='Return direct children of a node.', tags=['dag', 'query'])
    def get_children(self, db_path: str, node_id: str) -> List[str]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT dst FROM dag_edges WHERE src = ?', (node_id,)).fetchall()
            return [r['dst'] for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'node_id': 'str'}, outputs={'ancestors': 'list'}, description='Walk all ancestors of a node.', tags=['dag', 'query'])
    def get_ancestors(self, db_path: str, node_id: str) -> List[str]:
        conn = self._open(db_path)
        visited, queue = set(), [node_id]
        try:
            while queue:
                current = queue.pop()
                rows = conn.execute('SELECT src FROM dag_edges WHERE dst = ?', (current,)).fetchall()
                for r in rows:
                    p = r['src']
                    if p not in visited:
                        visited.add(p)
                        queue.append(p)
            return list(visited)
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str'}, outputs={'order': 'list', 'has_cycle': 'bool'}, description='Topological sort of entire DAG. Reports cycle if detected.', tags=['dag', 'sort'])
    def topological_sort(self, db_path: str) -> Dict[str, Any]:
        conn = self._open(db_path)
        try:
            nodes = [r['node_id'] for r in conn.execute('SELECT node_id FROM dag_nodes').fetchall()]
            edges = [(r['src'], r['dst']) for r in conn.execute('SELECT src, dst FROM dag_edges').fetchall()]
        finally:
            conn.close()

        from collections import defaultdict, deque
        in_degree = defaultdict(int, {n: 0 for n in nodes})
        adj = defaultdict(list)
        for src, dst in edges:
            adj[src].append(dst)
            in_degree[dst] += 1

        queue = deque([n for n in nodes if in_degree[n] == 0])
        order = []
        while queue:
            n = queue.popleft()
            order.append(n)
            for child in adj[n]:
                in_degree[child] -= 1
                if in_degree[child] == 0:
                    queue.append(child)

        return {'order': order, 'has_cycle': len(order) != len(nodes)}

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ---------------------------------------------------------------------------
# IntervalIndexMS
# ---------------------------------------------------------------------------

@service_metadata(
    name='IntervalIndexMS',
    version='1.0.0',
    description='Build and query a positional interval index over line spans. Find overlaps, containment, and point membership.',
    tags=['structure', 'positional', 'interval', 'range'],
    capabilities=['compute', 'db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class IntervalIndexMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS interval_index (
            span_id    TEXT PRIMARY KEY,
            node_id    TEXT,
            line_start INTEGER NOT NULL,
            line_end   INTEGER NOT NULL,
            label      TEXT
        )''')
        conn.commit()
        return conn

    @service_endpoint(inputs={'db_path': 'str', 'span_id': 'str', 'node_id': 'str', 'line_start': 'int', 'line_end': 'int', 'label': 'str'}, outputs={'ok': 'bool'}, description='Insert or replace a span in the interval index.', tags=['interval', 'write'], side_effects=['db:write'])
    def upsert_span(self, db_path: str, span_id: str, node_id: str, line_start: int, line_end: int, label: str = '') -> bool:
        conn = self._open(db_path)
        try:
            conn.execute('INSERT OR REPLACE INTO interval_index (span_id, node_id, line_start, line_end, label) VALUES (?, ?, ?, ?, ?)',
                         (span_id, node_id, line_start, line_end, label))
            conn.commit()
            return True
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'line': 'int'}, outputs={'spans': 'list'}, description='Find all spans that contain a given line number.', tags=['interval', 'query'])
    def spans_at_line(self, db_path: str, line: int) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT * FROM interval_index WHERE line_start <= ? AND line_end >= ?', (line, line)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'line_start': 'int', 'line_end': 'int'}, outputs={'spans': 'list'}, description='Find all spans that overlap with a given range.', tags=['interval', 'query'])
    def spans_overlapping(self, db_path: str, line_start: int, line_end: int) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT * FROM interval_index WHERE line_start <= ? AND line_end >= ?', (line_end, line_start)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'line_start': 'int', 'line_end': 'int'}, outputs={'spans': 'list'}, description='Find all spans fully contained within a range.', tags=['interval', 'query'])
    def spans_contained_by(self, db_path: str, line_start: int, line_end: int) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT * FROM interval_index WHERE line_start >= ? AND line_end <= ?', (line_start, line_end)).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ---------------------------------------------------------------------------
# DirectedFlowMS
# ---------------------------------------------------------------------------

@service_metadata(
    name='DirectedFlowMS',
    version='1.0.0',
    description='Typed directed graph for causality, dependency, and dataflow. Upstream/downstream walk, cycle detection.',
    tags=['structure', 'directional', 'flow', 'dependency'],
    capabilities=['db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class DirectedFlowMS:
    def __init__(self):
        self.start_time = time.time()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('''CREATE TABLE IF NOT EXISTS flow_edges (
            edge_id   TEXT PRIMARY KEY,
            src       TEXT NOT NULL,
            dst       TEXT NOT NULL,
            flow_type TEXT DEFAULT 'DEPENDS_ON',
            weight    REAL DEFAULT 1.0
        )''')
        conn.commit()
        return conn

    @service_endpoint(inputs={'db_path': 'str', 'src': 'str', 'dst': 'str', 'flow_type': 'str', 'weight': 'float'}, outputs={'edge_id': 'str'}, description='Insert a typed flow edge.', tags=['flow', 'write'], side_effects=['db:write'])
    def insert_flow_edge(self, db_path: str, src: str, dst: str, flow_type: str = 'DEPENDS_ON', weight: float = 1.0) -> str:
        edge_id = f'{flow_type}:{src}:{dst}'
        conn = self._open(db_path)
        try:
            conn.execute('INSERT OR IGNORE INTO flow_edges (edge_id, src, dst, flow_type, weight) VALUES (?, ?, ?, ?, ?)',
                         (edge_id, src, dst, flow_type, weight))
            conn.commit()
            return edge_id
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'node_id': 'str'}, outputs={'upstream': 'list'}, description='Walk all upstream nodes (what this node depends on).', tags=['flow', 'query'])
    def upstream(self, db_path: str, node_id: str) -> List[str]:
        conn = self._open(db_path)
        visited, queue = set(), [node_id]
        try:
            while queue:
                current = queue.pop()
                rows = conn.execute('SELECT src FROM flow_edges WHERE dst = ?', (current,)).fetchall()
                for r in rows:
                    if r['src'] not in visited:
                        visited.add(r['src'])
                        queue.append(r['src'])
            return list(visited)
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'node_id': 'str'}, outputs={'downstream': 'list'}, description='Walk all downstream nodes (what depends on this node).', tags=['flow', 'query'])
    def downstream(self, db_path: str, node_id: str) -> List[str]:
        conn = self._open(db_path)
        visited, queue = set(), [node_id]
        try:
            while queue:
                current = queue.pop()
                rows = conn.execute('SELECT dst FROM flow_edges WHERE src = ?', (current,)).fetchall()
                for r in rows:
                    if r['dst'] not in visited:
                        visited.add(r['dst'])
                        queue.append(r['dst'])
            return list(visited)
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'node_id': 'str'}, outputs={'has_cycle': 'bool', 'cycle_path': 'list'}, description='Detect if node participates in a cycle.', tags=['flow', 'cycle'])
    def detect_cycle(self, db_path: str, node_id: str) -> Dict[str, Any]:
        visited_path = []
        downstream = self.downstream(db_path, node_id)
        has_cycle = node_id in downstream
        return {'has_cycle': has_cycle, 'cycle_path': visited_path}

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

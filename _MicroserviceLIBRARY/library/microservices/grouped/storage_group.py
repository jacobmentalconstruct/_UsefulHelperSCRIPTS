"""
storage_group.py
StorageManager microservice group.
Covers: BLAKE3 hashing, Merkle tree ops, Verbatim store, Temporal chain.
"""

import hashlib
import json
import math
import sqlite3
import struct
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_metadata, service_endpoint


# ---------------------------------------------------------------------------
# Blake3HashMS
# ---------------------------------------------------------------------------

@service_metadata(
    name='Blake3HashMS',
    version='1.0.0',
    description='Produces BLAKE3-compatible content IDs for verbatim content. Uses SHA3-256 as stdlib stand-in; swap for blake3 package when available.',
    tags=['storage', 'hash', 'cid', 'blake3'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[],
)
class Blake3HashMS:
    def __init__(self):
        self.start_time = time.time()
        try:
            import blake3 as _b3
            self._blake3 = _b3
        except ImportError:
            self._blake3 = None

    @service_endpoint(inputs={'content': 'str'}, outputs={'cid': 'str'}, description='Hash a string and return hex CID.', tags=['hash', 'cid'])
    def hash_content(self, content: str) -> str:
        raw = content.encode('utf-8')
        if self._blake3:
            return self._blake3.blake3(raw).hexdigest()
        return hashlib.sha3_256(raw).hexdigest()

    @service_endpoint(inputs={'blob': 'bytes'}, outputs={'cid': 'str'}, description='Hash raw bytes and return hex CID.', tags=['hash', 'cid'])
    def hash_bytes(self, blob: bytes) -> str:
        if self._blake3:
            return self._blake3.blake3(blob).hexdigest()
        return hashlib.sha3_256(blob).hexdigest()

    @service_endpoint(inputs={'cids': 'list'}, outputs={'root': 'str'}, description='Combine ordered list of leaf CIDs into a single root hash.', tags=['hash', 'merkle'])
    def combine_cids(self, cids: List[str]) -> str:
        combined = ''.join(cids).encode('utf-8')
        if self._blake3:
            return self._blake3.blake3(combined).hexdigest()
        return hashlib.sha3_256(combined).hexdigest()

    def register(self, registry, group=None):
        """Auto-injected registration hook."""
        meta = getattr(self, '_meta', {})
        registry.register(
            name=meta.get('name', self.__class__.__name__),
            version=meta.get('version', '0.0.0'),
            tags=meta.get('tags', []),
            capabilities=meta.get('capabilities', []),
            instance=self,
            group=group,
        )

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float', 'blake3_native': 'bool'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time, 'blake3_native': self._blake3 is not None}


# ---------------------------------------------------------------------------
# MerkleRootMS
# ---------------------------------------------------------------------------

@service_metadata(
    name='MerkleRootMS',
    version='1.0.0',
    description='Builds, verifies, and diffs Merkle trees from ordered CID leaf lists.',
    tags=['storage', 'merkle', 'tree', 'diff'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib', 'Blake3HashMS'],
    external_dependencies=[],
)
class MerkleRootMS:
    def __init__(self):
        self.start_time = time.time()
        self._hasher = Blake3HashMS()

    def _pair_hash(self, a: str, b: str) -> str:
        return self._hasher.hash_content(a + b)

    @service_endpoint(inputs={'leaves': 'list'}, outputs={'root': 'str', 'levels': 'list'}, description='Build Merkle tree from leaf CIDs, return root and all levels.', tags=['merkle', 'build'])
    def build_tree(self, leaves: List[str]) -> Dict[str, Any]:
        if not leaves:
            return {'root': '', 'levels': []}
        level = list(leaves)
        levels = [level[:]]
        while len(level) > 1:
            if len(level) % 2 == 1:
                level.append(level[-1])
            level = [self._pair_hash(level[i], level[i+1]) for i in range(0, len(level), 2)]
            levels.append(level[:])
        return {'root': level[0], 'levels': levels}

    @service_endpoint(inputs={'leaves_a': 'list', 'leaves_b': 'list'}, outputs={'added': 'list', 'removed': 'list', 'root_changed': 'bool'}, description='Diff two leaf sets, return added/removed CIDs and whether root changed.', tags=['merkle', 'diff'])
    def diff_trees(self, leaves_a: List[str], leaves_b: List[str]) -> Dict[str, Any]:
        set_a, set_b = set(leaves_a), set(leaves_b)
        root_a = self.build_tree(leaves_a)['root']
        root_b = self.build_tree(leaves_b)['root']
        return {
            'added': list(set_b - set_a),
            'removed': list(set_a - set_b),
            'root_changed': root_a != root_b,
        }

    @service_endpoint(inputs={'leaf': 'str', 'leaves': 'list'}, outputs={'proof': 'list', 'root': 'str'}, description='Generate inclusion proof for a leaf in the tree.', tags=['merkle', 'proof'])
    def inclusion_proof(self, leaf: str, leaves: List[str]) -> Dict[str, Any]:
        if leaf not in leaves:
            return {'proof': [], 'root': ''}
        tree = self.build_tree(leaves)
        return {'proof': tree['levels'], 'root': tree['root']}

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}


# ---------------------------------------------------------------------------
# VerbatimStoreMS
# ---------------------------------------------------------------------------

@service_metadata(
    name='VerbatimStoreMS',
    version='1.0.0',
    description='Write, read, and deduplicate verbatim lines by CID. Reconstruct text from span references.',
    tags=['storage', 'verbatim', 'cid', 'db'],
    capabilities=['db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib', 'Blake3HashMS'],
    external_dependencies=[],
)
class VerbatimStoreMS:
    def __init__(self):
        self.start_time = time.time()
        self._hasher = Blake3HashMS()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @service_endpoint(inputs={'db_path': 'str', 'lines': 'list'}, outputs={'cids': 'list', 'written': 'int'}, description='Write deduplicated lines, return ordered CIDs.', tags=['verbatim', 'write'], side_effects=['db:write'])
    def write_lines(self, db_path: str, lines: List[str]) -> Dict[str, Any]:
        conn = self._open(db_path)
        cids, rows = [], []
        for line in lines:
            cid = self._hasher.hash_content(line)
            cids.append(cid)
            rows.append((cid, line, len(line.encode('utf-8'))))
        try:
            conn.executemany('INSERT OR IGNORE INTO verbatim_lines (line_cid, content, byte_len) VALUES (?, ?, ?)', rows)
            conn.commit()
            return {'cids': cids, 'written': len(rows)}
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'cid': 'str'}, outputs={'content': 'str'}, description='Read a single line by CID.', tags=['verbatim', 'read'])
    def read_line(self, db_path: str, cid: str) -> str:
        conn = self._open(db_path)
        try:
            row = conn.execute('SELECT content FROM verbatim_lines WHERE line_cid = ?', (cid,)).fetchone()
            return row['content'] if row else ''
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'cids': 'list'}, outputs={'lines': 'list'}, description='Reconstruct ordered text from a list of CIDs.', tags=['verbatim', 'reconstruct'])
    def reconstruct(self, db_path: str, cids: List[str]) -> List[str]:
        conn = self._open(db_path)
        try:
            placeholders = ','.join('?' * len(cids))
            rows = conn.execute(f'SELECT line_cid, content FROM verbatim_lines WHERE line_cid IN ({placeholders})', cids).fetchall()
            lookup = {r['line_cid']: r['content'] for r in rows}
            return [lookup.get(c, '') for c in cids]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'query': 'str', 'limit': 'int'}, outputs={'results': 'list'}, description='FTS search over verbatim line content.', tags=['verbatim', 'search'])
    def fts_search(self, db_path: str, query: str, limit: int = 25) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT line_cid, content FROM fts_lines WHERE fts_lines MATCH ? LIMIT ?', (query, max(1, limit))).fetchall()
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
# TemporalChainMS
# ---------------------------------------------------------------------------

@service_metadata(
    name='TemporalChainMS',
    version='1.0.0',
    description='Append-only Merkle root chain. Each commit links to previous root, enabling diff, snapshot, and audit.',
    tags=['storage', 'temporal', 'merkle', 'versioning'],
    capabilities=['db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib', 'MerkleRootMS', 'Blake3HashMS'],
    external_dependencies=[],
)
class TemporalChainMS:
    def __init__(self):
        self.start_time = time.time()
        self._merkle = MerkleRootMS()
        self._hasher = Blake3HashMS()

    def _open(self, db_path: str) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute('''
            CREATE TABLE IF NOT EXISTS temporal_chain (
                seq         INTEGER PRIMARY KEY AUTOINCREMENT,
                root_cid    TEXT NOT NULL,
                prev_cid    TEXT,
                label       TEXT,
                leaf_count  INTEGER,
                created_at  REAL NOT NULL
            )
        ''')
        conn.commit()
        return conn

    @service_endpoint(inputs={'db_path': 'str', 'leaves': 'list', 'label': 'str'}, outputs={'root': 'str', 'seq': 'int'}, description='Commit a new set of leaves as a chained Merkle root.', tags=['temporal', 'commit'], side_effects=['db:write'])
    def commit(self, db_path: str, leaves: List[str], label: str = '') -> Dict[str, Any]:
        conn = self._open(db_path)
        try:
            root = self._merkle.build_tree(leaves)['root']
            prev_row = conn.execute('SELECT root_cid FROM temporal_chain ORDER BY seq DESC LIMIT 1').fetchone()
            prev_cid = prev_row['root_cid'] if prev_row else None
            cursor = conn.execute(
                'INSERT INTO temporal_chain (root_cid, prev_cid, label, leaf_count, created_at) VALUES (?, ?, ?, ?, ?)',
                (root, prev_cid, label, len(leaves), time.time())
            )
            conn.commit()
            return {'root': root, 'seq': cursor.lastrowid}
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str'}, outputs={'chain': 'list'}, description='Return full commit chain in order.', tags=['temporal', 'history'])
    def get_chain(self, db_path: str) -> List[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            rows = conn.execute('SELECT seq, root_cid, prev_cid, label, leaf_count, created_at FROM temporal_chain ORDER BY seq').fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    @service_endpoint(inputs={'db_path': 'str', 'label': 'str'}, outputs={'entry': 'dict'}, description='Look up a named snapshot by label.', tags=['temporal', 'snapshot'])
    def get_snapshot(self, db_path: str, label: str) -> Optional[Dict[str, Any]]:
        conn = self._open(db_path)
        try:
            row = conn.execute('SELECT * FROM temporal_chain WHERE label = ? ORDER BY seq DESC LIMIT 1', (label,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def register(self, registry, group=None):
        meta = getattr(self, '_meta', {})
        registry.register(name=meta.get('name', self.__class__.__name__), version=meta.get('version', '0.0.0'), tags=meta.get('tags', []), capabilities=meta.get('capabilities', []), instance=self, group=group)

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Health check.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

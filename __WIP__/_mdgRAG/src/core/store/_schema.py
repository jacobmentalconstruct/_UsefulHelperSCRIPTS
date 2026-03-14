"""
SQLite Schema — DDL and initialization for manifold storage.

Ownership: src/core/store/_schema.py
    Internal helper for schema creation. Not part of the public API.
    Called by ManifoldFactory during manifold creation.

Every manifold role (identity, external, virtual) uses the SAME schema.
There are no role-specific tables. The same-schema invariant is enforced
at the storage level.

Tables:
    manifolds, nodes, edges, chunks, chunk_occurrences, embeddings,
    hierarchy, metadata, provenance, node_chunk_links,
    node_embedding_links, node_hierarchy_links, file_manifests,
    file_manifest_entries, project_manifests, project_manifest_entries
"""

from __future__ import annotations

import sqlite3

SCHEMA_VERSION = "0.1.0"

# All tables use TEXT for IDs to keep serialisation simple and
# maintain human-readability when inspecting the database.

_DDL = """
-- Manifold identity
CREATE TABLE IF NOT EXISTS manifolds (
    manifold_id     TEXT PRIMARY KEY,
    role            TEXT NOT NULL,
    storage_mode    TEXT NOT NULL,
    schema_version  TEXT NOT NULL DEFAULT '0.1.0',
    created_at      TEXT,
    description     TEXT DEFAULT '',
    properties_json TEXT DEFAULT '{}'
);

-- Graph: nodes
CREATE TABLE IF NOT EXISTS nodes (
    node_id         TEXT PRIMARY KEY,
    manifold_id     TEXT NOT NULL,
    node_type       TEXT NOT NULL,
    canonical_key   TEXT DEFAULT '',
    label           TEXT DEFAULT '',
    properties_json TEXT DEFAULT '{}',
    source_refs_json TEXT DEFAULT '[]',
    created_at      TEXT,
    updated_at      TEXT,
    FOREIGN KEY (manifold_id) REFERENCES manifolds(manifold_id)
);

-- Graph: edges
CREATE TABLE IF NOT EXISTS edges (
    edge_id         TEXT PRIMARY KEY,
    manifold_id     TEXT NOT NULL,
    from_node_id    TEXT NOT NULL,
    to_node_id      TEXT NOT NULL,
    edge_type       TEXT NOT NULL,
    weight          REAL DEFAULT 1.0,
    properties_json TEXT DEFAULT '{}',
    created_at      TEXT,
    updated_at      TEXT,
    FOREIGN KEY (manifold_id) REFERENCES manifolds(manifold_id),
    FOREIGN KEY (from_node_id) REFERENCES nodes(node_id),
    FOREIGN KEY (to_node_id) REFERENCES nodes(node_id)
);

-- Content: chunks (content-addressed, deduplicatable)
CREATE TABLE IF NOT EXISTS chunks (
    chunk_hash      TEXT PRIMARY KEY,
    chunk_text      TEXT NOT NULL,
    byte_length     INTEGER DEFAULT 0,
    char_length     INTEGER DEFAULT 0,
    token_estimate  INTEGER DEFAULT 0,
    hash_algorithm  TEXT DEFAULT 'sha256',
    created_at      TEXT
);

-- Content: chunk occurrences (location-based, many per chunk)
CREATE TABLE IF NOT EXISTS chunk_occurrences (
    chunk_hash      TEXT NOT NULL,
    manifold_id     TEXT NOT NULL,
    source_path     TEXT DEFAULT '',
    chunk_index     INTEGER DEFAULT 0,
    start_line      INTEGER,
    end_line        INTEGER,
    start_offset    INTEGER,
    end_offset      INTEGER,
    context_label   TEXT DEFAULT '',
    properties_json TEXT DEFAULT '{}',
    PRIMARY KEY (chunk_hash, manifold_id, source_path, chunk_index),
    FOREIGN KEY (chunk_hash) REFERENCES chunks(chunk_hash),
    FOREIGN KEY (manifold_id) REFERENCES manifolds(manifold_id)
);

-- Vectors: embeddings
CREATE TABLE IF NOT EXISTS embeddings (
    embedding_id    TEXT PRIMARY KEY,
    target_kind     TEXT NOT NULL,
    target_id       TEXT NOT NULL,
    model_name      TEXT DEFAULT '',
    model_version   TEXT DEFAULT '',
    dimensions      INTEGER DEFAULT 0,
    metric_type     TEXT DEFAULT 'COSINE',
    is_normalized   INTEGER DEFAULT 1,
    vector_ref      TEXT,
    vector_blob     BLOB,
    created_at      TEXT
);

-- Structure: hierarchy
CREATE TABLE IF NOT EXISTS hierarchy (
    hierarchy_id    TEXT PRIMARY KEY,
    manifold_id     TEXT NOT NULL,
    node_id         TEXT NOT NULL,
    parent_id       TEXT,
    depth           INTEGER DEFAULT 0,
    sort_order      INTEGER DEFAULT 0,
    path_label      TEXT DEFAULT '',
    properties_json TEXT DEFAULT '{}',
    FOREIGN KEY (manifold_id) REFERENCES manifolds(manifold_id),
    FOREIGN KEY (node_id) REFERENCES nodes(node_id)
);

-- Generic metadata
CREATE TABLE IF NOT EXISTS metadata (
    owner_kind      TEXT NOT NULL,
    owner_id        TEXT NOT NULL,
    manifold_id     TEXT NOT NULL,
    key             TEXT DEFAULT '',
    value_json      TEXT,
    properties_json TEXT DEFAULT '{}',
    created_at      TEXT,
    PRIMARY KEY (owner_kind, owner_id, manifold_id, key),
    FOREIGN KEY (manifold_id) REFERENCES manifolds(manifold_id)
);

-- Provenance / lineage
CREATE TABLE IF NOT EXISTS provenance (
    rowid_          INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_kind      TEXT NOT NULL,
    owner_id        TEXT NOT NULL,
    source_manifold_id TEXT,
    source_document TEXT,
    source_snapshot TEXT,
    stage           TEXT DEFAULT 'INGESTION',
    relation_origin TEXT DEFAULT 'PARSED',
    parser_name     TEXT,
    parser_version  TEXT,
    evidence_ref    TEXT,
    upstream_ids_json TEXT DEFAULT '[]',
    details_json    TEXT DEFAULT '{}',
    timestamp       TEXT
);

-- Cross-layer: node ↔ chunk
CREATE TABLE IF NOT EXISTS node_chunk_links (
    node_id         TEXT NOT NULL,
    chunk_hash      TEXT NOT NULL,
    manifold_id     TEXT NOT NULL,
    binding_role    TEXT DEFAULT 'contains',
    ordinal         INTEGER DEFAULT 0,
    properties_json TEXT DEFAULT '{}',
    PRIMARY KEY (node_id, chunk_hash, manifold_id),
    FOREIGN KEY (node_id) REFERENCES nodes(node_id),
    FOREIGN KEY (chunk_hash) REFERENCES chunks(chunk_hash),
    FOREIGN KEY (manifold_id) REFERENCES manifolds(manifold_id)
);

-- Cross-layer: node ↔ embedding
CREATE TABLE IF NOT EXISTS node_embedding_links (
    node_id         TEXT NOT NULL,
    embedding_id    TEXT NOT NULL,
    manifold_id     TEXT NOT NULL,
    binding_role    TEXT DEFAULT 'primary',
    properties_json TEXT DEFAULT '{}',
    PRIMARY KEY (node_id, embedding_id, manifold_id),
    FOREIGN KEY (node_id) REFERENCES nodes(node_id),
    FOREIGN KEY (embedding_id) REFERENCES embeddings(embedding_id),
    FOREIGN KEY (manifold_id) REFERENCES manifolds(manifold_id)
);

-- Cross-layer: node ↔ hierarchy
CREATE TABLE IF NOT EXISTS node_hierarchy_links (
    node_id         TEXT NOT NULL,
    hierarchy_id    TEXT NOT NULL,
    manifold_id     TEXT NOT NULL,
    binding_role    TEXT DEFAULT 'member',
    properties_json TEXT DEFAULT '{}',
    PRIMARY KEY (node_id, hierarchy_id, manifold_id),
    FOREIGN KEY (node_id) REFERENCES nodes(node_id),
    FOREIGN KEY (hierarchy_id) REFERENCES hierarchy(hierarchy_id),
    FOREIGN KEY (manifold_id) REFERENCES manifolds(manifold_id)
);

-- Manifests: file-level
CREATE TABLE IF NOT EXISTS file_manifests (
    manifest_hash   TEXT PRIMARY KEY,
    total_files     INTEGER DEFAULT 0,
    total_bytes     INTEGER DEFAULT 0,
    total_chunks    INTEGER DEFAULT 0,
    created_at      TEXT,
    properties_json TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS file_manifest_entries (
    file_hash       TEXT PRIMARY KEY,
    manifest_hash   TEXT NOT NULL,
    path            TEXT NOT NULL,
    content_hash    TEXT DEFAULT '',
    size_bytes      INTEGER DEFAULT 0,
    mime_type       TEXT DEFAULT '',
    encoding        TEXT DEFAULT 'utf-8',
    chunk_count     INTEGER DEFAULT 0,
    line_count      INTEGER DEFAULT 0,
    properties_json TEXT DEFAULT '{}',
    FOREIGN KEY (manifest_hash) REFERENCES file_manifests(manifest_hash)
);

-- Manifests: project-level
CREATE TABLE IF NOT EXISTS project_manifests (
    project_root_hash   TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL,
    name                TEXT DEFAULT '',
    description         TEXT DEFAULT '',
    schema_version      TEXT DEFAULT '0.1.0',
    embedding_spec_json TEXT DEFAULT '{}',
    chunking_spec_json  TEXT DEFAULT '{}',
    capabilities_json   TEXT DEFAULT '[]',
    created_at          TEXT,
    properties_json     TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS project_manifest_entries (
    entry_id            TEXT PRIMARY KEY,
    project_root_hash   TEXT NOT NULL,
    vfs_path            TEXT NOT NULL,
    real_path           TEXT DEFAULT '',
    origin_type         TEXT DEFAULT '',
    content_hash        TEXT DEFAULT '',
    file_manifest_hash  TEXT,
    properties_json     TEXT DEFAULT '{}',
    FOREIGN KEY (project_root_hash) REFERENCES project_manifests(project_root_hash)
);
"""

# The expected table names for verification
EXPECTED_TABLES = frozenset({
    "manifolds",
    "nodes",
    "edges",
    "chunks",
    "chunk_occurrences",
    "embeddings",
    "hierarchy",
    "metadata",
    "provenance",
    "node_chunk_links",
    "node_embedding_links",
    "node_hierarchy_links",
    "file_manifests",
    "file_manifest_entries",
    "project_manifests",
    "project_manifest_entries",
})


def initialize_schema(conn: sqlite3.Connection) -> None:
    """
    Create all manifold schema tables in the given connection.

    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS).
    Enables WAL mode and foreign keys for SQLite.
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_DDL)
    conn.commit()


def verify_schema(conn: sqlite3.Connection) -> set[str]:
    """
    Return the set of table names present in the database.

    Useful for testing that schema initialization succeeded.
    """
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return {row[0] for row in cursor.fetchall()}

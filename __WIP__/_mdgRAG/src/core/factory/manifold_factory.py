"""
Manifold Factory — creation and lifecycle management.

Ownership: src/core/factory/manifold_factory.py
    Creates manifold instances backed by SQLite (disk or memory) or
    pure Python RAM. Initialises schema, writes manifold metadata,
    and returns typed manifold objects with live connections.

The factory is separate from the store. The factory creates;
the store reads and writes contents.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.core.manifolds.base_manifold import BaseManifold
from src.core.manifolds.identity_manifold import IdentityManifold
from src.core.manifolds.external_manifold import ExternalManifold
from src.core.manifolds.virtual_manifold import VirtualManifold
from src.core.contracts.manifold_contract import ManifoldMetadata
from src.core.types.ids import ManifoldId
from src.core.types.enums import ManifoldRole, StorageMode
from src.core.store._schema import initialize_schema, SCHEMA_VERSION
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


def _make_connection(db_path: str) -> sqlite3.Connection:
    """Create a SQLite connection with row_factory for named access."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ManifoldFactory:
    """
    Factory for creating and opening manifold instances.

    Supports three creation modes:
        - Disk: SQLite database file on the filesystem
        - Memory: SQLite in-memory database (session-scoped)
        - RAM: Pure Python dicts (no SQLite, for virtual manifolds)
    """

    # =================================================================
    # Primary creation methods
    # =================================================================

    def create_disk_manifold(
        self,
        manifold_id: ManifoldId,
        role: ManifoldRole,
        db_path: str | Path,
        description: str = "",
    ) -> BaseManifold:
        """
        Create a new manifold persisted to a SQLite file on disk.

        Args:
            manifold_id: Unique identifier for this manifold.
            role: IDENTITY, EXTERNAL, or VIRTUAL.
            db_path: Filesystem path for the SQLite database.
            description: Optional description.

        Returns:
            A manifold object with a live connection and initialised schema.
        """
        db_path = str(Path(db_path).resolve())
        conn = _make_connection(db_path)
        initialize_schema(conn)
        manifold = self._build_manifold(
            manifold_id, role, StorageMode.SQLITE_DISK, conn,
        )
        self._write_manifold_row(conn, manifold.get_metadata(), description)
        logger.info(
            "Created disk manifold %s (%s) at %s",
            manifold_id, role.name, db_path,
        )
        return manifold

    def create_memory_manifold(
        self,
        manifold_id: ManifoldId,
        role: ManifoldRole,
        description: str = "",
    ) -> BaseManifold:
        """
        Create a new manifold in an in-memory SQLite database.

        The database lives for the lifetime of the connection. Useful
        for tests and transient manifolds.
        """
        conn = _make_connection(":memory:")
        initialize_schema(conn)
        manifold = self._build_manifold(
            manifold_id, role, StorageMode.SQLITE_MEMORY, conn,
        )
        self._write_manifold_row(conn, manifold.get_metadata(), description)
        logger.info(
            "Created memory manifold %s (%s)", manifold_id, role.name,
        )
        return manifold

    def create_manifold(
        self,
        manifold_id: ManifoldId,
        role: ManifoldRole,
        storage_mode: StorageMode = StorageMode.PYTHON_RAM,
        db_path: Optional[str | Path] = None,
        description: str = "",
    ) -> BaseManifold:
        """
        Unified creation method — dispatches to disk, memory, or RAM.
        """
        if storage_mode == StorageMode.SQLITE_DISK:
            if db_path is None:
                raise ValueError("db_path is required for SQLITE_DISK mode")
            return self.create_disk_manifold(
                manifold_id, role, db_path, description,
            )
        elif storage_mode == StorageMode.SQLITE_MEMORY:
            return self.create_memory_manifold(
                manifold_id, role, description,
            )
        else:
            # PYTHON_RAM — no SQLite, pure in-memory dicts
            return self._build_manifold(
                manifold_id, role, StorageMode.PYTHON_RAM, None,
            )

    # =================================================================
    # Open existing manifold
    # =================================================================

    def open_manifold(self, db_path: str | Path) -> BaseManifold:
        """
        Open an existing manifold from a SQLite database file.

        Reads the manifold metadata row to determine role and build
        the correct manifold type.
        """
        db_path = str(Path(db_path).resolve())
        conn = _make_connection(db_path)

        row = conn.execute(
            "SELECT * FROM manifolds LIMIT 1"
        ).fetchone()
        if row is None:
            raise ValueError(f"No manifold record found in {db_path}")

        role = ManifoldRole[row["role"]]
        manifold_id = ManifoldId(row["manifold_id"])
        manifold = self._build_manifold(
            manifold_id, role, StorageMode.SQLITE_DISK, conn,
        )
        logger.info(
            "Opened manifold %s (%s) from %s",
            manifold_id, role.name, db_path,
        )
        return manifold

    # =================================================================
    # Internal helpers
    # =================================================================

    @staticmethod
    def _build_manifold(
        manifold_id: ManifoldId,
        role: ManifoldRole,
        storage_mode: StorageMode,
        conn: Optional[sqlite3.Connection],
    ) -> BaseManifold:
        """Build the correct manifold subclass for the given role."""
        if role == ManifoldRole.IDENTITY:
            m = IdentityManifold(manifold_id, storage_mode=storage_mode)
        elif role == ManifoldRole.EXTERNAL:
            m = ExternalManifold(manifold_id, storage_mode=storage_mode)
        elif role == ManifoldRole.VIRTUAL:
            m = VirtualManifold(manifold_id)
            # Override storage_mode for virtual if SQLite was requested
            m._metadata = ManifoldMetadata(
                manifold_id=manifold_id,
                role=role,
                storage_mode=storage_mode,
            )
        else:
            raise ValueError(f"Unknown manifold role: {role}")

        m._connection = conn
        return m

    @staticmethod
    def _write_manifold_row(
        conn: sqlite3.Connection,
        meta: ManifoldMetadata,
        description: str = "",
    ) -> None:
        """Write the manifold identity row into the manifolds table."""
        conn.execute(
            """INSERT OR REPLACE INTO manifolds
               (manifold_id, role, storage_mode, schema_version,
                created_at, description, properties_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                meta.manifold_id,
                meta.role.name,
                meta.storage_mode.name,
                meta.schema_version,
                _utcnow_iso(),
                description,
                "{}",
            ),
        )
        conn.commit()

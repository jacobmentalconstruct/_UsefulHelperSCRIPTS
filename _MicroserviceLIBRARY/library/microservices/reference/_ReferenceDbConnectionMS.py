import sqlite3
import time
from pathlib import Path
from typing import Optional

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceDbConnectionMS',
    version='1.0.0',
    description='Pilfered from reference db.connection helpers. Opens/closes SQLite DB and runs WAL checkpoint.',
    tags=['db', 'sqlite', 'connection'],
    capabilities=['db:connect'],
    side_effects=['db:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceDbConnectionMS:
    def __init__(self):
        self.start_time = time.time()
        self._conn: Optional[sqlite3.Connection] = None

    @service_endpoint(inputs={'db_path': 'str', 'check_same_thread': 'bool'}, outputs={'ok': 'bool'}, description='Open SQLite connection and enable foreign key pragma.', tags=['db', 'connect'], side_effects=['db:write'])
    def open_db(self, db_path: str, check_same_thread: bool=False) -> bool:
        self._conn = sqlite3.connect(db_path, check_same_thread=check_same_thread)
        self._conn.execute('PRAGMA foreign_keys = ON')
        return True

    @service_endpoint(inputs={}, outputs={'connected': 'bool'}, description='Return whether a live DB connection is currently open.', tags=['db', 'status'])
    def is_connected(self) -> bool:
        return self._conn is not None

    @service_endpoint(inputs={'truncate_wal': 'bool'}, outputs={'ok': 'bool'}, description='Close DB connection with optional WAL checkpoint truncate.', tags=['db', 'close'], side_effects=['db:write'])
    def close_db(self, truncate_wal: bool=True) -> bool:
        if self._conn is None:
            return True
        try:
            if truncate_wal:
                self._conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        except Exception:
            pass
        finally:
            self._conn.close()
            self._conn = None
        return True

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float', 'connected': 'bool'}, description='Standardized health check for service status and DB connection state.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time, 'connected': self.is_connected()}

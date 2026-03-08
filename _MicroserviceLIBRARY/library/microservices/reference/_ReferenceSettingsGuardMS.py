import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceSettingsGuardMS',
    version='1.0.0',
    description='Pilfered from settings_dialog mismatch guard. Compares selected embedder against DB embed model.',
    tags=['settings', 'db', 'guard'],
    capabilities=['filesystem:read', 'db:read'],
    side_effects=['filesystem:read', 'db:read'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceSettingsGuardMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'settings_path': 'str'}, outputs={'settings': 'dict'}, description='Load settings JSON with safe fallback defaults.', tags=['settings', 'read'], side_effects=['filesystem:read'])
    def load_settings(self, settings_path: str) -> Dict[str, Any]:
        defaults = {'embedder_filename': 'qwen2.5-coder:3b', 'extractor_filename': 'qwen2.5-coder:3b', 'lazy_mode': False}
        path = Path(settings_path)
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding='utf-8'))
                out = dict(defaults)
                out.update({k: v for k, v in data.items() if k in defaults})
                return out
        except Exception:
            pass
        return defaults

    @service_endpoint(inputs={'db_path': 'str'}, outputs={'embed_model': 'str'}, description='Read one existing embed model value from chunk_manifest.', tags=['db', 'read'], side_effects=['db:read'])
    def get_db_embed_model(self, db_path: str) -> str:
        try:
            conn = sqlite3.connect(db_path)
            row = conn.execute('SELECT embed_model FROM chunk_manifest WHERE embed_model IS NOT NULL LIMIT 1').fetchone()
            conn.close()
            return row[0] if row and row[0] else ''
        except Exception:
            return ''

    @service_endpoint(inputs={'db_path': 'str', 'selected_embedder': 'str'}, outputs={'result': 'dict'}, description='Detect embedder mismatch risk between selected model and DB model provenance.', tags=['settings', 'guard', 'validation'])
    def check_model_mismatch(self, db_path: str, selected_embedder: str) -> Dict[str, Any]:
        db_model = self.get_db_embed_model(db_path)
        if not db_model:
            return {'safe': True, 'reason': 'db_has_no_embed_model', 'db_model': '', 'selected': selected_embedder}
        if db_model == selected_embedder:
            return {'safe': True, 'reason': 'models_match', 'db_model': db_model, 'selected': selected_embedder}
        return {
            'safe': False,
            'reason': 'model_mismatch',
            'db_model': db_model,
            'selected': selected_embedder,
            'message': 'Mixing embedding models can produce incompatible vectors and bad semantic search results.'
        }

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

import json
import time
from pathlib import Path
from typing import Any, Dict

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceSettingsStoreMS',
    version='1.0.0',
    description='Pilfered from reference settings_store. JSON-backed settings persistence with model role selection.',
    tags=['settings', 'config', 'persistence'],
    capabilities=['filesystem:read', 'filesystem:write'],
    side_effects=['filesystem:read', 'filesystem:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceSettingsStoreMS:
    def __init__(self, settings_path: str=''):
        self.start_time = time.time()
        self.settings_path = Path(settings_path) if settings_path else (Path.home() / '.tripartite' / 'settings.json')
        self.default_settings = {
            'embedder_filename': 'qwen2.5-coder:3b',
            'extractor_filename': 'qwen2.5-coder:3b',
            'lazy_mode': False,
        }

    @service_endpoint(inputs={}, outputs={'settings_path': 'str'}, description='Return resolved settings file path.', tags=['settings'])
    def get_settings_path(self) -> str:
        return str(self.settings_path)

    @service_endpoint(inputs={}, outputs={'settings': 'dict'}, description='Load settings JSON from disk, falling back to defaults.', tags=['settings', 'read'], side_effects=['filesystem:read'])
    def load(self) -> Dict[str, Any]:
        try:
            if self.settings_path.exists():
                data = json.loads(self.settings_path.read_text(encoding='utf-8'))
                out = dict(self.default_settings)
                out.update({k: v for k, v in data.items() if k in self.default_settings})
                return out
        except Exception:
            pass
        return dict(self.default_settings)

    @service_endpoint(inputs={'settings': 'dict'}, outputs={'ok': 'bool'}, description='Persist settings to disk as JSON, creating parent directory if needed.', tags=['settings', 'write'], side_effects=['filesystem:write'])
    def save(self, settings: Dict[str, Any]) -> bool:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        out = dict(self.default_settings)
        out.update({k: v for k, v in settings.items() if k in self.default_settings})
        self.settings_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
        return True

    @service_endpoint(inputs={'role': 'str'}, outputs={'filename': 'str'}, description='Get selected model filename for role: embedder or extractor.', tags=['settings'])
    def get_model_for_role(self, role: str) -> str:
        s = self.load()
        return s['embedder_filename'] if role == 'embedder' else s['extractor_filename']

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float', 'settings_path': 'str'}, description='Standardized health check for service status and settings path.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time, 'settings_path': str(self.settings_path)}

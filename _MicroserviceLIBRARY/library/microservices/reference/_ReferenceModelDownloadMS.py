import time
import urllib.request
from pathlib import Path
from typing import Any, Dict

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceModelDownloadMS',
    version='1.0.0',
    description='Pilfered from settings_dialog.py download workflow. Provides cache status checks and model download/verification operations.',
    tags=['models', 'download', 'settings'],
    capabilities=['filesystem:read', 'filesystem:write', 'network:http'],
    side_effects=['filesystem:read', 'filesystem:write', 'network:http'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceModelDownloadMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'models_dir': 'str', 'spec': 'dict'}, outputs={'status': 'dict'}, description='Check cached file status against min_size_bytes requirements.', tags=['models', 'cache'], side_effects=['filesystem:read'])
    def cache_status(self, models_dir: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        path = Path(models_dir) / spec['filename']
        min_size = int(spec.get('min_size_bytes', 0))
        if path.exists() and path.stat().st_size >= min_size:
            size_mb = path.stat().st_size / 1_048_576
            return {'cached': True, 'size_mb': round(size_mb, 1), 'path': str(path)}
        return {'cached': False, 'size_mb': 0.0, 'path': str(path)}

    @service_endpoint(inputs={'models_dir': 'str', 'spec': 'dict'}, outputs={'result': 'dict'}, description='Download model file to cache directory and verify minimum size.', tags=['models', 'download'], side_effects=['network:http', 'filesystem:write'])
    def download_model(self, models_dir: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        models = Path(models_dir)
        models.mkdir(parents=True, exist_ok=True)

        dest = models / spec['filename']
        tmp = dest.with_suffix(dest.suffix + '.tmp')
        url = spec['url']
        min_size = int(spec.get('min_size_bytes', 0))

        urllib.request.urlretrieve(url, tmp)
        tmp.rename(dest)

        actual = dest.stat().st_size
        if actual < min_size:
            dest.unlink(missing_ok=True)
            return {'ok': False, 'error': 'download_too_small', 'size_bytes': actual, 'min_size_bytes': min_size}

        return {'ok': True, 'path': str(dest), 'size_bytes': actual}

    @service_endpoint(inputs={'models_dir': 'str', 'spec': 'dict'}, outputs={'ok': 'bool'}, description='Verify that a cached model file satisfies size constraints.', tags=['models', 'verify'], side_effects=['filesystem:read'])
    def verify_model(self, models_dir: str, spec: Dict[str, Any]) -> bool:
        status = self.cache_status(models_dir, spec)
        return bool(status['cached'])

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

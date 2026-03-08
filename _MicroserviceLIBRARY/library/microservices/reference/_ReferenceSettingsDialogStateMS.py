import time
from typing import Any, Dict

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceSettingsDialogStateMS',
    version='1.0.0',
    description='Pilfered from settings_dialog.py workflow logic. Tracks dirty state, apply/cancel snapshots, and status badge text.',
    tags=['settings', 'ui', 'state'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceSettingsDialogStateMS:
    def __init__(self):
        self.start_time = time.time()
        self.state: Dict[str, Any] = {
            'embedder_filename': 'qwen2.5-coder:3b',
            'extractor_filename': 'qwen2.5-coder:3b',
            'lazy_mode': False,
            '_original_embedder': 'qwen2.5-coder:3b',
            '_original_extractor': 'qwen2.5-coder:3b',
            '_original_lazy': False,
            'dirty': False,
            'status_msg': '',
        }

    @service_endpoint(inputs={'settings': 'dict'}, outputs={'state': 'dict'}, description='Load dialog state from settings and snapshot original values.', tags=['settings', 'state'])
    def load_state(self, settings: Dict[str, Any]) -> Dict[str, Any]:
        self.state['embedder_filename'] = settings.get('embedder_filename', self.state['embedder_filename'])
        self.state['extractor_filename'] = settings.get('extractor_filename', self.state['extractor_filename'])
        self.state['lazy_mode'] = bool(settings.get('lazy_mode', self.state['lazy_mode']))
        self.state['_original_embedder'] = self.state['embedder_filename']
        self.state['_original_extractor'] = self.state['extractor_filename']
        self.state['_original_lazy'] = self.state['lazy_mode']
        self.state['dirty'] = False
        self.state['status_msg'] = ''
        return dict(self.state)

    @service_endpoint(inputs={'role': 'str', 'filename': 'str'}, outputs={'state': 'dict'}, description='Set selected model for embedder/extractor and mark state dirty.', tags=['settings', 'state'])
    def set_model(self, role: str, filename: str) -> Dict[str, Any]:
        if role == 'embedder':
            self.state['embedder_filename'] = filename
        elif role == 'extractor':
            self.state['extractor_filename'] = filename
        else:
            raise ValueError('role must be embedder or extractor')
        self.state['dirty'] = True
        self.state['status_msg'] = ''
        return dict(self.state)

    @service_endpoint(inputs={'lazy_mode': 'bool'}, outputs={'state': 'dict'}, description='Toggle lazy mode and mark state dirty.', tags=['settings', 'state'])
    def set_lazy_mode(self, lazy_mode: bool) -> Dict[str, Any]:
        self.state['lazy_mode'] = bool(lazy_mode)
        self.state['dirty'] = True
        self.state['status_msg'] = ''
        return dict(self.state)

    @service_endpoint(inputs={}, outputs={'persist_settings': 'dict'}, description='Apply changes: clear dirty flag, update snapshots, and return persisted settings payload.', tags=['settings', 'apply'])
    def apply(self) -> Dict[str, Any]:
        self.state['_original_embedder'] = self.state['embedder_filename']
        self.state['_original_extractor'] = self.state['extractor_filename']
        self.state['_original_lazy'] = self.state['lazy_mode']
        self.state['dirty'] = False
        self.state['status_msg'] = 'Settings applied'
        return {
            'embedder_filename': self.state['embedder_filename'],
            'extractor_filename': self.state['extractor_filename'],
            'lazy_mode': self.state['lazy_mode'],
        }

    @service_endpoint(inputs={}, outputs={'state': 'dict'}, description='Cancel unsaved changes by restoring original snapshot values.', tags=['settings', 'cancel'])
    def cancel(self) -> Dict[str, Any]:
        self.state['embedder_filename'] = self.state['_original_embedder']
        self.state['extractor_filename'] = self.state['_original_extractor']
        self.state['lazy_mode'] = self.state['_original_lazy']
        self.state['dirty'] = False
        self.state['status_msg'] = ''
        return dict(self.state)

    @service_endpoint(inputs={}, outputs={'status': 'dict'}, description='Return condensed dialog status data for UI binding.', tags=['settings', 'status'])
    def get_dialog_status(self) -> Dict[str, Any]:
        return {
            'dirty': self.state['dirty'],
            'status_msg': self.state['status_msg'],
            'embedder_filename': self.state['embedder_filename'],
            'extractor_filename': self.state['extractor_filename'],
            'lazy_mode': self.state['lazy_mode'],
        }

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

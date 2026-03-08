import difflib
import time
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceViewerContentMS',
    version='1.0.0',
    description='Pilfered from components/viewer.py. Headless content formatting for placeholders, directory listings, and diff previews.',
    tags=['viewer', 'ui', 'formatting'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceViewerContentMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={}, outputs={'text': 'str'}, description='Return default viewer placeholder text.', tags=['viewer', 'placeholder'])
    def placeholder_text(self) -> str:
        return (
            '\n\n\n'
            '              Select a node in the Explorer\n'
            '              to view its content here.\n\n'
            "              Or right-click a node and choose\n"
            "              'View' or 'View in New Panel'."
        )

    @service_endpoint(inputs={'directory_name': 'str', 'rows': 'list', 'icon_map': 'dict'}, outputs={'text': 'str'}, description='Format directory listing content block used by viewer panels.', tags=['viewer', 'directory'])
    def format_directory_listing(self, directory_name: str, rows: List[Dict[str, Any]], icon_map: Dict[str, str]=None) -> str:
        icons = icon_map or {}
        lines = []
        for r in rows:
            ntype = r.get('node_type', 'unknown')
            icon = icons.get(ntype, '▪')
            name = r.get('name', '(unnamed)')
            tier = r.get('language_tier', 'unknown')
            lines.append(f'{icon} {name}  [{tier}]')
        head = f'Directory: {directory_name}\n' + ('-' * 40)
        return head + ('\n' + '\n'.join(lines) if lines else '\n(empty)')

    @service_endpoint(inputs={'before_text': 'str', 'after_text': 'str', 'context_lines': 'int'}, outputs={'diff_lines': 'list'}, description='Generate unified diff lines for viewer diff mode.', tags=['viewer', 'diff'])
    def unified_diff(self, before_text: str, after_text: str, context_lines: int=3) -> List[str]:
        before = before_text.splitlines()
        after = after_text.splitlines()
        return list(difflib.unified_diff(before, after, lineterm='', n=context_lines))

    @service_endpoint(inputs={'text': 'str', 'max_lines': 'int'}, outputs={'preview': 'str'}, description='Create large-file preview snippet with truncation marker.', tags=['viewer', 'preview'])
    def large_file_preview(self, text: str, max_lines: int=1000) -> str:
        lines = text.splitlines()
        if len(lines) <= max_lines:
            return text
        shown = '\n'.join(lines[:max_lines])
        return f"{shown}\n\n... [{len(lines) - max_lines} more lines] ..."

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

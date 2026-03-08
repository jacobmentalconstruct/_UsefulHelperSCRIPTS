import time
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceExplorerModelMS',
    version='1.0.0',
    description='Pilfered from explorer.py. Headless hierarchy modeling, mode detection, and deterministic child sorting.',
    tags=['explorer', 'tree', 'model'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceExplorerModelMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'source_type_counts': 'dict', 'virtual_file_count': 'int', 'total_files': 'int'}, outputs={'mode': 'str'}, description='Auto-detect explorer mode from source-type distribution and virtual-file presence.', tags=['explorer', 'mode'])
    def detect_mode(self, source_type_counts: Dict[str, int], virtual_file_count: int=0, total_files: int=0) -> str:
        total = total_files or sum(source_type_counts.values())
        if virtual_file_count > 0:
            return 'project'
        if total > 1:
            return 'project'
        if not source_type_counts:
            return 'outline'
        dominant = max(source_type_counts.items(), key=lambda x: x[1])[0]
        if dominant in ('prose', 'markdown', 'text'):
            return 'document'
        return 'outline'

    @service_endpoint(inputs={'rows': 'list'}, outputs={'roots': 'list'}, description='Build parent/child tree from flat node rows using node_id/parent_id links.', tags=['explorer', 'tree'])
    def build_tree(self, rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items: Dict[str, Dict[str, Any]] = {}
        for r in rows:
            node = dict(r)
            node.setdefault('children', [])
            items[node['node_id']] = node

        roots: List[Dict[str, Any]] = []
        for node in items.values():
            pid = node.get('parent_id')
            if pid and pid in items:
                items[pid]['children'].append(node)
            else:
                roots.append(node)

        self._sort_children(roots)
        return roots

    def _sort_children(self, nodes: List[Dict[str, Any]]) -> None:
        def key_fn(c: Dict[str, Any]):
            return (
                c.get('node_type') != 'directory',
                c.get('node_type') != 'virtual_file',
                c.get('node_type') != 'file',
                c.get('line_start') if c.get('line_start') is not None else 999999,
                str(c.get('name', '')).lower(),
            )

        nodes.sort(key=key_fn)
        for node in nodes:
            children = node.get('children', [])
            if children:
                self._sort_children(children)

    @service_endpoint(inputs={'roots': 'list'}, outputs={'stats': 'dict'}, description='Summarize tree counts for roots, files, and chunk-like nodes.', tags=['explorer', 'stats'])
    def summarize_tree(self, roots: List[Dict[str, Any]]) -> Dict[str, int]:
        stats = {'roots': len(roots), 'files': 0, 'directories': 0, 'chunks': 0}

        def walk(nodes: List[Dict[str, Any]]):
            for n in nodes:
                ntype = n.get('node_type', '')
                if ntype in ('file', 'virtual_file'):
                    stats['files'] += 1
                elif ntype == 'directory':
                    stats['directories'] += 1
                else:
                    stats['chunks'] += 1
                walk(n.get('children', []))

        walk(roots)
        return stats

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

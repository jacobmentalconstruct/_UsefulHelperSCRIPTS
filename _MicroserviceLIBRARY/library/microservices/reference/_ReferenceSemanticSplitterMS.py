import time
from pathlib import Path
from typing import Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceSemanticSplitterMS',
    version='1.0.0',
    description='Pilfered from file_splitter.py. Splits large source files into semantic hunks by anchor lines.',
    tags=['splitter', 'refactor', 'filesystem'],
    capabilities=['filesystem:read', 'filesystem:write'],
    side_effects=['filesystem:read', 'filesystem:write'],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceSemanticSplitterMS:
    DEFAULT_ANCHORS = [
        'class TreeItem:',
        'class BaseCurationTool(ABC):',
        'class ViewerPanel(tk.Frame):',
        'class ViewerStack(tk.Frame):',
        'class TripartiteDataStore:',
        'def _build_workspace(self):',
        'def _patch_validate(self):',
        'def _run_ingest(self, source_path: str):',
        'def _query_semantic_layer(self, query: str, top_k: int):',
    ]

    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'file_path': 'str', 'anchors': 'list'}, outputs={'indices': 'list'}, description='Find split indices for anchor lines in a source file.', tags=['split', 'analysis'], side_effects=['filesystem:read'])
    def find_split_indices(self, file_path: str, anchors: List[str]=None) -> List[int]:
        path = Path(file_path)
        lines = path.read_text(encoding='utf-8', errors='ignore').splitlines(keepends=True)
        anchors = anchors or self.DEFAULT_ANCHORS

        split_indices = [0]
        for anchor in anchors:
            matches = [i for i, line in enumerate(lines) if line.strip().startswith(anchor)]
            if len(matches) == 1:
                split_indices.append(matches[0])

        split_indices.append(len(lines))
        return sorted(set(split_indices))

    @service_endpoint(inputs={'file_path': 'str', 'output_dir': 'str', 'anchors': 'list'}, outputs={'stats': 'dict'}, description='Split source file into semantic hunk files at anchor boundaries.', tags=['split', 'write'], side_effects=['filesystem:read', 'filesystem:write'])
    def split_file(self, file_path: str, output_dir: str='', anchors: List[str]=None) -> Dict[str, int]:
        path = Path(file_path)
        out_dir = Path(output_dir) if output_dir else path.parent
        out_dir.mkdir(parents=True, exist_ok=True)

        lines = path.read_text(encoding='utf-8', errors='ignore').splitlines(keepends=True)
        splits = self.find_split_indices(file_path, anchors)

        count = 0
        for i in range(len(splits) - 1):
            start, end = splits[i], splits[i + 1]
            chunk_lines = lines[start:end]
            out_name = f'{path.stem}_hunk_{i:02d}{path.suffix}'
            (out_dir / out_name).write_text(''.join(chunk_lines), encoding='utf-8')
            count += 1

        return {'parts_written': count, 'anchors_used': len(anchors or self.DEFAULT_ANCHORS)}

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

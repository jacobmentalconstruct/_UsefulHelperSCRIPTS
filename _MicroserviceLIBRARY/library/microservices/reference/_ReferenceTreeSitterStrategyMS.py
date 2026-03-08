import time
from pathlib import Path
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


LANGUAGE_TIERS = {
    'deep_semantic': {
        'languages': ['python', 'javascript', 'typescript', 'java', 'go', 'rust', 'cpp', 'c_sharp', 'kotlin', 'scala', 'swift'],
        'max_depth': 4,
        'chunk_strategy': 'hierarchical',
        'meaningful_depth': True,
    },
    'shallow_semantic': {
        'languages': ['bash', 'r', 'ruby', 'php', 'c'],
        'max_depth': 2,
        'chunk_strategy': 'flat',
        'meaningful_depth': True,
    },
    'structural': {
        'languages': ['json', 'yaml', 'toml'],
        'max_depth': None,
        'chunk_strategy': 'structural',
        'meaningful_depth': False,
    },
    'hybrid': {
        'languages': ['html', 'css', 'xml'],
        'max_depth': 3,
        'chunk_strategy': 'markup',
        'meaningful_depth': False,
    },
}

EXTENSION_TO_LANGUAGE = {
    '.py': 'python', '.js': 'javascript', '.jsx': 'javascript', '.ts': 'typescript', '.tsx': 'typescript', '.java': 'java', '.go': 'go', '.rs': 'rust', '.c': 'c',
    '.cpp': 'cpp', '.cxx': 'cpp', '.cc': 'cpp', '.h': 'c', '.hpp': 'cpp', '.hxx': 'cpp', '.cs': 'c_sharp', '.rb': 'ruby', '.php': 'php', '.swift': 'swift',
    '.kt': 'kotlin', '.kts': 'kotlin', '.scala': 'scala', '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash', '.html': 'html', '.htm': 'html', '.css': 'css',
    '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.toml': 'toml', '.xml': 'xml', '.r': 'r', '.R': 'r'
}


@service_metadata(
    name='ReferenceTreeSitterStrategyMS',
    version='1.0.0',
    description='Pilfered from chunkers/treesitter.py dispatch and fallback logic. Produces strategy plans and fallback line windows.',
    tags=['treesitter', 'chunking', 'strategy'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceTreeSitterStrategyMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'language': 'str'}, outputs={'tier': 'dict'}, description='Resolve language tier and strategy metadata.', tags=['treesitter', 'tier'])
    def get_language_tier(self, language: str) -> Dict[str, Any]:
        for tier_name, cfg in LANGUAGE_TIERS.items():
            if language in cfg['languages']:
                out = dict(cfg)
                out['tier'] = tier_name
                return out
        return {'tier': 'shallow_semantic', 'languages': [], 'max_depth': 2, 'chunk_strategy': 'flat', 'meaningful_depth': True}

    @service_endpoint(inputs={'file_path': 'str'}, outputs={'language': 'str', 'tier': 'dict'}, description='Resolve extension language and tier in one call.', tags=['treesitter', 'tier', 'language'])
    def classify_file(self, file_path: str) -> Dict[str, Any]:
        language = EXTENSION_TO_LANGUAGE.get(Path(file_path).suffix.lower(), '')
        return {'language': language, 'tier': self.get_language_tier(language)}

    @service_endpoint(inputs={'line_count': 'int', 'max_chunk_tokens': 'int', 'overlap_lines': 'int'}, outputs={'windows': 'list'}, description='Generate fallback line-window ranges similar to tree-sitter fallback chunker.', tags=['chunking', 'fallback'])
    def fallback_line_windows(self, line_count: int, max_chunk_tokens: int = 800, overlap_lines: int = 3) -> List[Dict[str, int]]:
        windows = []
        target_tokens = max(1, int(max_chunk_tokens))
        step_lines = max(20, target_tokens // 5)

        i = 0
        idx = 0
        while i < line_count:
            end = min(i + step_lines, line_count)
            windows.append({'index': idx, 'line_start': i, 'line_end': max(i, end - 1)})
            idx += 1
            i += max(1, step_lines - max(0, overlap_lines))
        return windows

    @service_endpoint(inputs={'file_path': 'str', 'treesitter_available': 'bool', 'parse_has_error': 'bool'}, outputs={'plan': 'dict'}, description='Create dispatch plan: choose tree-sitter strategy or fallback windows.', tags=['chunking', 'dispatch'])
    def plan_dispatch(self, file_path: str, treesitter_available: bool = True, parse_has_error: bool = False) -> Dict[str, Any]:
        info = self.classify_file(file_path)
        language = info['language']
        tier = info['tier']

        if not treesitter_available or not language or parse_has_error:
            return {
                'mode': 'fallback',
                'language': language,
                'tier': tier,
                'reason': 'treesitter_unavailable_or_parse_error',
                'strategy': 'line_window',
            }

        return {
            'mode': 'treesitter',
            'language': language,
            'tier': tier,
            'strategy': tier['chunk_strategy'],
            'meaningful_depth': tier['meaningful_depth'],
            'max_depth': tier['max_depth'],
        }

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

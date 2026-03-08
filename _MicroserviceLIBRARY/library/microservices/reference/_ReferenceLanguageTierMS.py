import time
from pathlib import Path
from typing import Any, Dict

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
    '.py': 'python', '.js': 'javascript', '.jsx': 'javascript', '.ts': 'typescript', '.tsx': 'typescript', '.java': 'java',
    '.go': 'go', '.rs': 'rust', '.c': 'c', '.cpp': 'cpp', '.cxx': 'cpp', '.cc': 'cpp', '.h': 'c', '.hpp': 'cpp',
    '.cs': 'c_sharp', '.rb': 'ruby', '.php': 'php', '.swift': 'swift', '.kt': 'kotlin', '.kts': 'kotlin', '.scala': 'scala',
    '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash', '.html': 'html', '.htm': 'html', '.css': 'css', '.json': 'json',
    '.yaml': 'yaml', '.yml': 'yaml', '.toml': 'toml', '.xml': 'xml', '.r': 'r', '.R': 'r'
}


@service_metadata(
    name='ReferenceLanguageTierMS',
    version='1.0.0',
    description='Pilfered from chunkers/treesitter.py. Maps file extensions to language + tier/chunk strategy metadata.',
    tags=['chunking', 'language', 'tiers'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceLanguageTierMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'file_path': 'str'}, outputs={'language': 'str'}, description='Resolve language id from file extension mapping.', tags=['language', 'detect'])
    def language_for_file(self, file_path: str) -> str:
        ext = Path(file_path).suffix
        return EXTENSION_TO_LANGUAGE.get(ext, '')

    @service_endpoint(inputs={'language': 'str'}, outputs={'tier': 'dict'}, description='Return tier configuration for a language, with fallback defaults.', tags=['language', 'tier'])
    def get_language_tier(self, language: str) -> Dict[str, Any]:
        for tier_name, config in LANGUAGE_TIERS.items():
            if language in config['languages']:
                out = dict(config)
                out['tier'] = tier_name
                return out
        return {
            'tier': 'shallow_semantic',
            'languages': [],
            'max_depth': 2,
            'chunk_strategy': 'flat',
            'meaningful_depth': True,
        }

    @service_endpoint(inputs={'file_path': 'str'}, outputs={'classification': 'dict'}, description='Resolve file -> language -> tier metadata in one call.', tags=['language', 'tier', 'detect'])
    def classify_file(self, file_path: str) -> Dict[str, Any]:
        language = self.language_for_file(file_path)
        tier = self.get_language_tier(language) if language else self.get_language_tier('')
        return {
            'file_path': file_path,
            'extension': Path(file_path).suffix,
            'language': language,
            'tier': tier['tier'],
            'chunk_strategy': tier['chunk_strategy'],
            'meaningful_depth': tier['meaningful_depth'],
            'max_depth': tier['max_depth'],
        }

    @service_endpoint(inputs={'language': 'str'}, outputs={'supported': 'bool'}, description='Check whether tree-sitter package is installed and language is known in tier map.', tags=['treesitter', 'support'])
    def treesitter_supported(self, language: str) -> bool:
        try:
            import tree_sitter_language_pack  # noqa: F401
        except Exception:
            return False
        return any(language in cfg['languages'] for cfg in LANGUAGE_TIERS.values())

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

import time
from pathlib import Path
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


FUNCTION_QUERIES = {
    'python': '(function_definition name: (identifier) @name) @function',
    'javascript': '(function_declaration name: (identifier) @name) @function',
    'typescript': '(function_declaration name: (identifier) @name) @function',
    'java': '(method_declaration name: (identifier) @name) @method',
    'go': '(function_declaration name: (identifier) @name) @function',
    'rust': '(function_item name: (identifier) @name) @function',
    'c': '(function_definition declarator: (function_declarator declarator: (identifier) @name)) @function',
    'cpp': '(function_definition declarator: (function_declarator declarator: (identifier) @name)) @function',
    'c_sharp': '(method_declaration name: (identifier) @name) @method',
    'ruby': '(method name: (identifier) @name) @method',
    'php': '(function_definition name: (name) @name) @function',
    'swift': '(function_declaration name: (simple_identifier) @name) @function',
    'kotlin': '(function_declaration (simple_identifier) @name) @function',
    'scala': '(function_definition name: (identifier) @name) @function',
    'bash': '(function_definition name: (word) @name) @function',
}

CLASS_QUERIES = {
    'python': '(class_definition name: (identifier) @name) @class',
    'javascript': '(class_declaration name: (identifier) @name) @class',
    'typescript': '(class_declaration name: (type_identifier) @name) @class',
    'java': '(class_declaration name: (identifier) @name) @class',
    'go': '(type_declaration (type_spec name: (type_identifier) @name)) @type',
    'rust': '(struct_item name: (type_identifier) @name) @struct',
    'c': '(struct_specifier name: (type_identifier) @name) @struct',
    'cpp': '(class_specifier name: (type_identifier) @name) @class',
    'c_sharp': '(class_declaration name: (identifier) @name) @class',
    'ruby': '(class name: (constant) @name) @class',
    'php': '(class_declaration name: (name) @name) @class',
    'swift': '(class_declaration name: (type_identifier) @name) @class',
    'kotlin': '(class_declaration (type_identifier) @name) @class',
    'scala': '(class_definition name: (identifier) @name) @class',
}

IMPORT_QUERIES = {
    'python': '(import_statement) @import (import_from_statement) @import',
    'javascript': '(import_statement) @import',
    'typescript': '(import_statement) @import',
    'java': '(import_declaration) @import',
    'go': '(import_declaration) @import',
    'rust': '(use_declaration) @import',
    'c': '(preproc_include) @import',
    'cpp': '(preproc_include) @import',
    'c_sharp': '(using_directive) @import',
    'ruby': '(call method: (identifier) @method (#match? @method "^(require|require_relative|load|import)$")) @import',
    'php': '(namespace_use_declaration) @import',
    'swift': '(import_declaration) @import',
    'kotlin': '(import_header) @import',
    'scala': '(import_declaration) @import',
}

EXTENSION_TO_LANGUAGE = {
    '.py': 'python', '.js': 'javascript', '.jsx': 'javascript', '.ts': 'typescript', '.tsx': 'typescript', '.java': 'java', '.go': 'go', '.rs': 'rust',
    '.c': 'c', '.cpp': 'cpp', '.cxx': 'cpp', '.cc': 'cpp', '.h': 'c', '.hpp': 'cpp', '.hxx': 'cpp', '.cs': 'c_sharp', '.rb': 'ruby', '.php': 'php',
    '.swift': 'swift', '.kt': 'kotlin', '.kts': 'kotlin', '.scala': 'scala', '.sh': 'bash', '.bash': 'bash', '.zsh': 'bash', '.html': 'html',
    '.htm': 'html', '.css': 'css', '.json': 'json', '.yaml': 'yaml', '.yml': 'yaml', '.toml': 'toml', '.r': 'r', '.R': 'r'
}


@service_metadata(
    name='ReferenceTreeSitterQueryRegistryMS',
    version='1.0.0',
    description='Pilfered from chunkers/treesitter.py query dictionaries. Exposes function/class/import tree-sitter query patterns by language.',
    tags=['treesitter', 'chunking', 'registry'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceTreeSitterQueryRegistryMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(inputs={'file_path': 'str'}, outputs={'language': 'str'}, description='Map file extension to tree-sitter language id.', tags=['treesitter', 'language'])
    def language_for_file(self, file_path: str) -> str:
        return EXTENSION_TO_LANGUAGE.get(Path(file_path).suffix, '')

    @service_endpoint(inputs={'language': 'str'}, outputs={'queries': 'dict'}, description='Return function/class/import query patterns for a language.', tags=['treesitter', 'queries'])
    def get_query_set(self, language: str) -> Dict[str, str]:
        return {
            'function_query': FUNCTION_QUERIES.get(language, ''),
            'class_query': CLASS_QUERIES.get(language, ''),
            'import_query': IMPORT_QUERIES.get(language, ''),
        }

    @service_endpoint(inputs={}, outputs={'languages': 'list'}, description='List languages with at least one query pattern.', tags=['treesitter', 'queries'])
    def list_languages(self) -> List[str]:
        return sorted(set(FUNCTION_QUERIES) | set(CLASS_QUERIES) | set(IMPORT_QUERIES))

    @service_endpoint(inputs={'extension': 'str'}, outputs={'supported': 'bool'}, description='Check if extension maps to a known tree-sitter language in registry.', tags=['treesitter', 'support'])
    def is_language_supported(self, extension: str) -> bool:
        return extension.lower() in EXTENSION_TO_LANGUAGE

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float', 'language_count': 'int'}, description='Standardized health check for service status and query coverage.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time, 'language_count': len(self.list_languages())}

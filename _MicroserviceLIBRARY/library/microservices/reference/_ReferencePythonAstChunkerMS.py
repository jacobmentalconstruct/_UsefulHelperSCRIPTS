import ast
import time
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferencePythonAstChunkerMS',
    version='1.0.0',
    description='Pilfered from chunkers/code.py. AST-based Python chunk boundary extraction with fallback windows.',
    tags=['chunking', 'python', 'ast'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferencePythonAstChunkerMS:
    def __init__(self):
        self.start_time = time.time()

    def _node_range(self, node: ast.AST) -> Dict[str, int]:
        return {'start': node.lineno - 1, 'end': node.end_lineno - 1}  # type: ignore[attr-defined]

    @service_endpoint(inputs={'source_text': 'str'}, outputs={'import_block': 'dict'}, description='Extract aggregate import line range for a Python module.', tags=['chunking', 'imports'])
    def collect_import_block(self, source_text: str) -> Dict[str, int]:
        tree = ast.parse(source_text)
        lines: List[int] = []
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                r = self._node_range(node)
                lines.extend(list(range(r['start'], r['end'] + 1)))
        if not lines:
            return {}
        return {'start': min(lines), 'end': max(lines)}

    @service_endpoint(inputs={'source_text': 'str', 'file_name': 'str'}, outputs={'chunks': 'list'}, description='Generate AST-based chunks for module docstring, imports, classes, methods, and functions.', tags=['chunking', 'ast'])
    def chunk_python_ast(self, source_text: str, file_name: str='module.py') -> List[Dict[str, Any]]:
        try:
            tree = ast.parse(source_text)
        except SyntaxError:
            return self.fallback_line_windows(source_text)

        chunks: List[Dict[str, Any]] = []
        import_block = self.collect_import_block(source_text)
        if import_block:
            chunks.append({'chunk_type': 'import_block', 'name': 'imports', **import_block})

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                r = self._node_range(node)
                chunks.append({'chunk_type': 'function_def', 'name': node.name, **r})
            elif isinstance(node, ast.ClassDef):
                r = self._node_range(node)
                chunks.append({'chunk_type': 'class_def', 'name': node.name, **r})
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        m = self._node_range(child)
                        chunks.append({'chunk_type': 'method_def', 'name': f'{node.name}.{child.name}', **m})

        doc = ast.get_docstring(tree)
        if doc:
            for node in ast.iter_child_nodes(tree):
                if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                    r = self._node_range(node)
                    chunks.insert(0, {'chunk_type': 'module_summary', 'name': f'{file_name} (module)', **r})
                    break

        return chunks or self.fallback_line_windows(source_text)

    @service_endpoint(inputs={'source_text': 'str', 'window_lines': 'int'}, outputs={'chunks': 'list'}, description='Fallback line-window chunking for non-parseable Python text.', tags=['chunking', 'fallback'])
    def fallback_line_windows(self, source_text: str, window_lines: int=120) -> List[Dict[str, int]]:
        lines = source_text.splitlines()
        out = []
        start = 0
        while start < len(lines):
            end = min(start + max(1, window_lines) - 1, len(lines) - 1)
            out.append({'chunk_type': 'line_window', 'start': start, 'end': end})
            start = end + 1
        return out

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

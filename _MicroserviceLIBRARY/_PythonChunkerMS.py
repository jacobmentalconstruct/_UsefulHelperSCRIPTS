import ast
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Any
from microservice_std_lib import service_metadata, service_endpoint

@dataclass
class CodeChunk:
    name: str
    type: str
    content: str
    start_line: int
    end_line: int
    docstring: str = ''

@service_metadata(name='PythonChunker', version='1.2.0', description='The Python Surgeon: Specialist in Abstract Syntax Tree (AST) parsing for Python source code.', tags=['chunking', 'python', 'ast'], capabilities=['python-ast'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class PythonChunkerMS:
    """
    Specialized Python AST Chunker.
    Focuses exclusively on identifying classes and functions to preserve code logic.
    """

    def __init__(self, config: Dict[str, Any]=None):
        self.config = config or {}
        self.start_time = time.time()

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float', 'specialty': 'str'}, description='Standardized health check for the Python specialist service.', tags=['diagnostic', 'health'])
    def get_health(self) -> Dict[str, Any]:
        """Returns the operational status of the PythonChunkerMS."""
        return {'status': 'online', 'uptime': time.time() - self.start_time, 'specialty': 'python_ast'}

    @service_endpoint(inputs={'content': 'str'}, outputs={'chunks': 'List[Dict]'}, description='Primary entry point for high-fidelity Python-specific AST chunking.', tags=['processing', 'python'])
    def chunk(self, content: str) -> List[Dict[str, Any]]:
        """Parses Python source into semantic CodeChunks."""
        chunks = self._chunk_python(content)
        return [asdict(c) for c in chunks]

    def _chunk_python(self, source: str) -> List[CodeChunk]:
        chunks = []
        try:
            tree = ast.parse(source)
            lines = source.splitlines(keepends=True)

            def get_segment(node):
                start = node.lineno - 1
                end = node.end_lineno if hasattr(node, 'end_lineno') and node.end_lineno else start + 1
                return (''.join(lines[start:end]), start + 1, end)
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    text, s, e = get_segment(node)
                    doc = ast.get_docstring(node) or ''
                    chunks.append(CodeChunk(name=f'def {node.name}', type='function', content=text, start_line=s, end_line=e, docstring=doc))
                elif isinstance(node, ast.ClassDef):
                    text, s, e = get_segment(node)
                    doc = ast.get_docstring(node) or ''
                    chunks.append(CodeChunk(name=f'class {node.name}', type='class', content=text, start_line=s, end_line=e, docstring=doc))
            if not chunks and source.strip():
                chunks.append(CodeChunk(name='module_level', type='text', content=source, start_line=1, end_line=len(lines)))
        except SyntaxError:
            chunks.append(CodeChunk(name='syntax_error_fallback', type='text', content=source, start_line=1, end_line=source.count('\n') + 1))
        return chunks
if __name__ == '__main__':
    svc = PythonChunkerMS()
    print('Service ready:', svc)
    test_code = 'class Test:\n    def run(self):\n        pass'
    results = svc.chunk(test_code)
    for c in results:
        print(f"[{c['type']}] {c['name']} (Lines {c['start_line']}-{c['end_line']})")

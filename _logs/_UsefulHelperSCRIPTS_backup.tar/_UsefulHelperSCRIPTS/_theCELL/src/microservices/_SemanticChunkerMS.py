import ast
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional
from .microservice_std_lib import service_metadata, service_endpoint
from .base_service import BaseService

@dataclass
class CodeChunk:
    name: str
    type: str
    content: str
    start_line: int
    end_line: int
    docstring: str = ''

@service_metadata(name='SemanticChunker', version='1.0.0', description='The Surgeon: Intelligent Code Splitter that parses source code into logical semantic units (Classes, Functions) using AST.', tags=['utility', 'nlp', 'parser'], capabilities=['python-ast', 'semantic-chunking'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class SemanticChunkerMS(BaseService):
    """
    Intelligent Code Splitter.
    Parses source code into logical units (Classes, Functions) 
    rather than arbitrary text windows.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        super().__init__('SemanticChunker')
        self.config = config or {}

    @service_endpoint(inputs={'content': 'str', 'filename': 'str'}, outputs={'chunks': 'List[Dict]'}, description='Main entry point to split a file into semantic chunks based on its extension and content.', tags=['processing', 'chunking'], side_effects=[])
    # ROLE: Main entry point to split a file into semantic chunks based on its extension and content.
    # INPUTS: {"content": "str", "filename": "str"}
    # OUTPUTS: {"chunks": "List[Dict]"}
    def chunk_file(self, content: str, filename: str) -> List[Dict[str, Any]]:
        """
        Splits file content into chunks.
        Returns a list of dictionaries suitable for JSON response.
        """
        chunks: List[CodeChunk] = []
        if filename.endswith('.py'):
            chunks = self._chunk_python(content)
        elif filename.lower().endswith(('.md', '.txt', '.pdf', '.html', '.htm', '.rst')):
            chunks = self._chunk_generic(content, window_size=800)
        else:
            chunks = self._chunk_generic(content, window_size=1500)
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
            if not chunks:
                return self._chunk_generic(source)
        except SyntaxError:
            return self._chunk_generic(source)
        return chunks

    def _chunk_generic(self, text: str, window_size: int=1500) -> List[CodeChunk]:
        """Sliding window for non-code files."""
        chunks = []
        text = text.replace('\r\n', '\n').replace('\r', '\n')
        lines = text.splitlines(keepends=True)
        current_chunk = []
        current_size = 0
        chunk_idx = 1
        start_line = 1
        for i, line in enumerate(lines):
            current_chunk.append(line)
            current_size += len(line)
            if current_size >= window_size:
                chunks.append(CodeChunk(name=f'Chunk {chunk_idx}', type='text_block', content=''.join(current_chunk), start_line=start_line, end_line=i + 1))
                current_chunk = []
                current_size = 0
                chunk_idx += 1
                start_line = i + 2
        if current_chunk:
            chunks.append(CodeChunk(name=f'Chunk {chunk_idx}', type='text_block', content=''.join(current_chunk), start_line=start_line, end_line=len(lines)))
        return chunks
if __name__ == '__main__':
    svc = SemanticChunkerMS()
    print('Service ready:', svc)
    test_code = "def hello():\n    print('world')\n\nclass Test:\n    pass"
    results = svc.chunk_file(test_code, 'test.py')
    print(f'Extracted {len(results)} semantic chunks.')
    for c in results:
        print(f" - [{c['type']}] {c['name']} ({c['start_line']}-{c['end_line']})")
        print(f" - [{c['type']}] {c['name']} ({c['start_line']}-{c['end_line']})")


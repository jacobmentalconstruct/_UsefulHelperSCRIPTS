import ast
from dataclasses import dataclass
from typing import List

@dataclass
class CodeChunk:
    name: str          # e.g., "class AuthMS"
    type: str          # "class", "function", "text"
    content: str       # The raw source
    start_line: int
    end_line: int
    docstring: str = "" # Captured separately for high-quality RAG

class SemanticChunker:
    """
    Intelligent Code Splitter.
    Parses source code into logical units (Classes, Functions) 
    rather than arbitrary text windows.
    """
    
    def chunk_file(self, content: str, filename: str) -> List[CodeChunk]:
        if filename.endswith(".py"):
            return self._chunk_python(content)
        return self._chunk_generic(content)

    def _chunk_python(self, source: str) -> List[CodeChunk]:
        chunks = []
        try:
            tree = ast.parse(source)
            lines = source.splitlines(keepends=True)
            
            def get_segment(node):
                start = node.lineno - 1
                end = node.end_lineno if hasattr(node, 'end_lineno') else start + 1
                return "".join(lines[start:end]), start + 1, end

            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    text, s, e = get_segment(node)
                    doc = ast.get_docstring(node) or ""
                    chunks.append(CodeChunk(
                        name=f"def {node.name}", type="function", 
                        content=text, start_line=s, end_line=e, docstring=doc
                    ))
                elif isinstance(node, ast.ClassDef):
                    text, s, e = get_segment(node)
                    doc = ast.get_docstring(node) or ""
                    chunks.append(CodeChunk(
                        name=f"class {node.name}", type="class", 
                        content=text, start_line=s, end_line=e, docstring=doc
                    ))

            # Fallback: If no classes/functions found (e.g., script file), treat as generic
            if not chunks:
                return self._chunk_generic(source)
                
        except SyntaxError:
            return self._chunk_generic(source)
            
        return chunks

    def _chunk_generic(self, text: str, window_size: int = 1500) -> List[CodeChunk]:
        """Sliding window for non-code files."""
        chunks = []
        lines = text.splitlines(keepends=True)
        current_chunk = []
        current_size = 0
        chunk_idx = 1
        start_line = 1
        
        for i, line in enumerate(lines):
            current_chunk.append(line)
            current_size += len(line)
            
            if current_size >= window_size:
                chunks.append(CodeChunk(
                    name=f"Chunk {chunk_idx}", type="text_block",
                    content="".join(current_chunk), start_line=start_line, end_line=i + 1
                ))
                current_chunk = []
                current_size = 0
                chunk_idx += 1
                start_line = i + 2
                
        if current_chunk:
            chunks.append(CodeChunk(
                name=f"Chunk {chunk_idx}", type="text_block",
                content="".join(current_chunk), start_line=start_line, end_line=len(lines)
            ))
            
        return chunks

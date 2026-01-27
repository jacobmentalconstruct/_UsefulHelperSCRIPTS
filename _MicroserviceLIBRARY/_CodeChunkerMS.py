"""
SERVICE_NAME: _CodeChunkerMS
ENTRY_POINT: _CodeChunkerMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib
EXTERNAL_DEPENDENCIES: None
"""
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from microservice_std_lib import service_metadata, service_endpoint, BaseService

@service_metadata(name='CodeChunker', version='1.0.0', description='Splits code into semantic blocks (Classes, Functions) using indentation and regex heuristics.', tags=['parsing', 'chunking', 'code'], capabilities=['filesystem:read'], side_effects=['filesystem:read'], internal_dependencies=['base_service', 'microservice_std_lib'], external_dependencies=[])
class CodeChunkerMS(BaseService):
    """
    The Surgeon (Pure Python Edition): Splits code into semantic blocks
    (Classes, Functions) using indentation and regex heuristics.
    
    Advantages: Zero dependencies. Works on any machine.
    Disadvantages: Slightly less precise than Tree-Sitter for messy code.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        super().__init__('CodeChunker')
        self.config = config or {}
        self.def_pattern = re.compile('^(\\s*)(?:async\\s+)?(?:class|def|function|func|var|const)\\s+([a-zA-Z0-9_]+)', re.MULTILINE)

    @service_endpoint(inputs={'file_path': 'str', 'max_chars': 'int'}, outputs={'chunks': 'List[Dict]'}, description='Reads a file and breaks it into logical blocks based on indentation.', tags=['parsing', 'chunking'], side_effects=['filesystem:read'])
    def chunk_file(self, file_path: str, max_chars: int=1500) -> List[Dict[str, Any]]:
        """
        Reads a file and breaks it into logical blocks based on indentation.
        """
        path = Path(file_path)
        try:
            code = path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            print(f'Error reading {file_path}: {e}')
            return []
        return self._chunk_by_indentation(code, max_chars)

    def _chunk_by_indentation(self, code: str, max_chars: int) -> List[Dict]:
        lines = code.splitlines()
        chunks = []
        current_chunk_lines = []
        current_start_line = 0
        current_indent = 0
        in_block = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped and (not in_block):
                continue
            indent_match = re.match('^(\\s*)', line)
            indent_level = len(indent_match.group(1)) if indent_match else 0
            match = self.def_pattern.match(line)
            is_def = match is not None and indent_level <= 4
            if is_def and current_chunk_lines:
                self._finalize_chunk(chunks, current_chunk_lines, current_start_line, max_chars)
                current_chunk_lines = []
                current_start_line = i + 1
                in_block = True
                current_indent = indent_level
            if in_block and stripped and (indent_level <= current_indent) and (not is_def):
                if not stripped.startswith('}'):
                    self._finalize_chunk(chunks, current_chunk_lines, current_start_line, max_chars)
                    current_chunk_lines = []
                    current_start_line = i + 1
                    in_block = False
            current_chunk_lines.append(line)
        if current_chunk_lines:
            self._finalize_chunk(chunks, current_chunk_lines, current_start_line, max_chars)
        return chunks

    def _finalize_chunk(self, chunks, lines, start_line, max_chars):
        """Recursively splits huge chunks if they exceed max_chars."""
        full_text = '\n'.join(lines)
        if not full_text.strip():
            return
        if len(full_text) > max_chars:
            self._split_large_block(chunks, lines, start_line, max_chars)
        else:
            chunks.append({'type': 'block', 'text': full_text, 'start_line': start_line, 'end_line': start_line + len(lines)})

    def _split_large_block(self, chunks, lines, start_line, max_chars):
        """Force split a large block while keeping line boundaries."""
        current_sub = []
        current_len = 0
        sub_start = start_line
        for i, line in enumerate(lines):
            if current_len + len(line) > max_chars:
                if current_sub:
                    chunks.append({'type': 'fragment', 'text': '\n'.join(current_sub), 'start_line': sub_start, 'end_line': sub_start + len(current_sub)})
                current_sub = []
                current_len = 0
                sub_start = start_line + i
            current_sub.append(line)
            current_len += len(line)
        if current_sub:
            chunks.append({'type': 'fragment', 'text': '\n'.join(current_sub), 'start_line': sub_start, 'end_line': sub_start + len(current_sub)})
if __name__ == '__main__':
    chunker = CodeChunkerMS()
    print(f'Service ready: {chunker}')
    py_code = '\nimport os\n\ndef small_helper():\n    return True\n\nclass DataProcessor:\n    def __init__(self):\n        self.data = []\n\n    def process(self, raw_input):\n        # This is a comment inside the function\n        if raw_input:\n            self.data.append(raw_input)\n        return True\n    '
    with tempfile.NamedTemporaryFile(suffix='.py', mode='w+', delete=False) as tmp:
        tmp.write(py_code)
        tmp_path = tmp.name
    try:
        print(f'--- Chunking {tmp_path} (Pure Python) ---')
        chunks = chunker.chunk_file(tmp_path)
        for i, c in enumerate(chunks):
            print(f"\n[Chunk {i}] Lines {c['start_line']}-{c['end_line']}")
            print(f"{'-' * 20}\n{c['text'].strip()}\n{'-' * 20}")
    finally:
        os.remove(tmp_path)

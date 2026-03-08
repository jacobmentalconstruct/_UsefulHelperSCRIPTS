import logging
from typing import Any, Dict, List, Optional, Tuple
from microservice_std_lib import service_metadata, service_endpoint
import time
logger = logging.getLogger('TextChunker')

@service_metadata(name='TextChunker', version='1.0.0', description='Splits text into chunks using various strategies (chars, lines).', tags=['chunking', 'nlp', 'rag'], capabilities=['compute'], internal_dependencies=['microservice_std_lib'], external_dependencies=[], side_effects=[])
class TextChunkerMS:
    """
    The Butcher: A unified service for splitting text into digestible chunks
    for RAG (Retrieval Augmented Generation).
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}

    @service_endpoint(inputs={'text': 'str', 'chunk_size': 'int', 'chunk_overlap': 'int'}, outputs={'chunks': 'List[str]'}, description='Standard sliding window split by character count.', tags=['chunking', 'chars'], side_effects=[])
    def chunk_by_chars(self, text: str, chunk_size: int=500, chunk_overlap: int=50) -> List[str]:
        """
        Standard Sliding Window. Best for prose/documentation.
        Splits purely by character count.
        """
        if chunk_size <= 0:
            raise ValueError('chunk_size must be positive')
        chunks = []
        start = 0
        text_length = len(text)
        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            if end >= text_length:
                break
            start += chunk_size - chunk_overlap
        return chunks

    @service_endpoint(inputs={'text': 'str', 'max_lines': 'int', 'max_chars': 'int'}, outputs={'chunks': 'List[Dict]'}, description='Line-preserving chunker, best for code.', tags=['chunking', 'lines', 'code'], side_effects=[])
    def chunk_by_lines(self, text: str, max_lines: int=200, max_chars: int=4000) -> List[Dict[str, Any]]:
        """
        Line-Preserving Chunker. Best for Code.
        Respects line boundaries and returns metadata about line numbers.
        """
        lines = text.splitlines()
        chunks = []
        start = 0
        while start < len(lines):
            end = min(start + max_lines, len(lines))
            chunk_str = '\n'.join(lines[start:end])
            while len(chunk_str) > max_chars and end > start + 1:
                end -= 1
                chunk_str = '\n'.join(lines[start:end])
            chunks.append({'text': chunk_str, 'start_line': start + 1, 'end_line': end})
            start = end
        return chunks

    @service_endpoint(inputs={'text': 'str', 'target_chars': 'int', 'overlap_paragraphs': 'int'}, outputs={'chunks': 'List[str]'}, description='Prose-aware paragraph chunking with overlap between windows.', tags=['chunking', 'prose', 'paragraphs'], side_effects=[])
    def chunk_by_paragraphs(self, text: str, target_chars: int=1200, overlap_paragraphs: int=1) -> List[str]:
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        if not paragraphs:
            return []

        chunks: List[str] = []
        current: List[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)
            if current and current_len + para_len + 2 > target_chars:
                chunks.append('\n\n'.join(current))
                overlap = current[-overlap_paragraphs:] if overlap_paragraphs > 0 else []
                current = list(overlap)
                current_len = sum(len(x) for x in current) + (2 * max(0, len(current) - 1))
            current.append(para)
            current_len += para_len + (2 if len(current) > 1 else 0)

        if current:
            chunks.append('\n\n'.join(current))

        return chunks

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        """Returns the operational status of the service."""
        start = getattr(self, 'start_time', None)
        if start is None:
            start = time.time()
            self.start_time = start
        return {'status': 'online', 'uptime': time.time() - start}

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    chunker = TextChunkerMS()
    print('Service ready:', chunker)
    print('--- Prose Chunking ---')
    lorem = 'A' * 100
    result = chunker.chunk_by_chars(lorem, chunk_size=40, chunk_overlap=10)
    for i, c in enumerate(result):
        print(f'Chunk {i}: len={len(c)}')
    print('\n--- Code Chunking ---')
    code = '\n'.join([f"print('Line {i}')" for i in range(1, 10)])
    result_code = chunker.chunk_by_lines(code, max_lines=3, max_chars=100)
    for i, c in enumerate(result_code):
        print(f"Chunk {i}: Lines {c['start_line']}-{c['end_line']}")

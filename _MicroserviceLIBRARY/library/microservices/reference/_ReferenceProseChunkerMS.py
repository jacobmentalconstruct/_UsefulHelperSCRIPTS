import re
import time
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


_HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$')


@service_metadata(
    name='ReferenceProseChunkerMS',
    version='1.0.0',
    description='Pilfered from chunkers/prose.py. Heading-aware and paragraph-aware chunking for markdown and text.',
    tags=['chunking', 'prose', 'markdown'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceProseChunkerMS:
    def __init__(self):
        self.start_time = time.time()

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text.split()))

    @service_endpoint(inputs={'lines': 'list'}, outputs={'sections': 'list'}, description='Split markdown lines by ATX headings and preserve heading breadcrumbs.', tags=['chunking', 'headings'])
    def split_on_headings(self, lines: List[str]) -> List[Dict[str, Any]]:
        sections: List[Dict[str, Any]] = []
        heading_stack: List[tuple] = []
        current_start = None
        current_path: List[str] = []

        def flush(end_idx: int):
            if current_start is not None and end_idx >= current_start:
                sections.append({'start': current_start, 'end': end_idx, 'heading_path': list(current_path)})

        for i, line in enumerate(lines):
            m = _HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                title = m.group(2).strip()
                flush(i - 1)
                heading_stack[:] = [(lvl, txt) for lvl, txt in heading_stack if lvl < level]
                heading_stack.append((level, title))
                current_path = [txt for _, txt in heading_stack]
                current_start = i

        flush(len(lines) - 1)
        return sections

    @service_endpoint(inputs={'lines': 'list'}, outputs={'sections': 'list'}, description='Split text lines by blank-line paragraph boundaries.', tags=['chunking', 'paragraphs'])
    def split_on_paragraphs(self, lines: List[str]) -> List[Dict[str, Any]]:
        sections: List[Dict[str, Any]] = []
        start = None
        for i, line in enumerate(lines):
            if line.strip():
                if start is None:
                    start = i
            else:
                if start is not None:
                    sections.append({'start': start, 'end': i - 1, 'heading_path': []})
                    start = None
        if start is not None:
            sections.append({'start': start, 'end': len(lines) - 1, 'heading_path': []})
        return sections

    @service_endpoint(inputs={'text': 'str', 'is_markdown': 'bool', 'max_tokens': 'int', 'overlap_lines': 'int'}, outputs={'chunks': 'list'}, description='Chunk prose by section and fallback sliding windows for oversized sections.', tags=['chunking', 'prose'])
    def chunk_prose(self, text: str, is_markdown: bool=True, max_tokens: int=800, overlap_lines: int=2) -> List[Dict[str, Any]]:
        lines = text.splitlines()
        sections = self.split_on_headings(lines) if is_markdown else self.split_on_paragraphs(lines)
        if not sections and lines:
            sections = [{'start': 0, 'end': len(lines) - 1, 'heading_path': []}]

        chunks: List[Dict[str, Any]] = []
        for section in sections:
            lo, hi = section['start'], section['end']
            section_lines = lines[lo:hi + 1]
            token_count = self._estimate_tokens('\n'.join(section_lines))
            if token_count <= max_tokens:
                chunks.append({'line_start': lo, 'line_end': hi, 'heading_path': section['heading_path'], 'text': '\n'.join(section_lines), 'tokens': token_count})
                continue

            cursor = lo
            while cursor <= hi:
                end = cursor
                tokens = 0
                while end <= hi:
                    tokens += self._estimate_tokens(lines[end])
                    if tokens > max_tokens and end > cursor:
                        break
                    end += 1
                chunk_end = min(end - 1, hi)
                chunk_lines = lines[cursor:chunk_end + 1]
                chunks.append({'line_start': cursor, 'line_end': chunk_end, 'heading_path': section['heading_path'], 'text': '\n'.join(chunk_lines), 'tokens': self._estimate_tokens('\n'.join(chunk_lines))})
                next_cursor = chunk_end + 1 - max(0, overlap_lines)
                if next_cursor <= cursor:
                    next_cursor = cursor + 1
                cursor = next_cursor

        return chunks

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

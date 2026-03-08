import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


_SEPARATOR_RE = re.compile(r'^[-=~#*_]{40,}$')
_FILE_HEADER_PATTERNS = [
    re.compile(r'^FILE:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^FILENAME:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^PATH:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^---\s+(.+\.\w+)\s+---$'),
    re.compile(r'^===\s+(.+\.\w+)\s+===$'),
    re.compile(r'^//\s*FILE:\s*(.+)$', re.IGNORECASE),
    re.compile(r'^#\s*FILE:\s*(.+)$', re.IGNORECASE),
]

_CODE_EXTENSIONS = {
    '.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.php', '.swift', '.kt', '.scala', '.r', '.sh', '.bash', '.zsh', '.sql'
}
_STRUCTURED_EXTENSIONS = {'.json', '.yaml', '.yml', '.toml', '.xml', '.csv', '.tsv'}


@service_metadata(
    name='ReferenceCompoundDetectMS',
    version='1.0.0',
    description='Pilfered from chunkers/compound.py. Detects and segments concatenated multi-file dump documents.',
    tags=['chunking', 'compound', 'detection'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceCompoundDetectMS:
    def __init__(self):
        self.start_time = time.time()

    def _is_roughly_periodic(self, positions: List[int], tolerance: float = 0.5) -> bool:
        if len(positions) < 3:
            return False
        gaps = [positions[i + 1] - positions[i] for i in range(len(positions) - 1)]
        avg = sum(gaps) / len(gaps)
        if avg <= 0:
            return False
        return all(abs(g - avg) / avg <= tolerance for g in gaps)

    def _classify_extension(self, ext: str) -> str:
        if ext in _CODE_EXTENSIONS:
            return 'code'
        if ext in _STRUCTURED_EXTENSIONS:
            return 'structured'
        return 'prose'

    @service_endpoint(inputs={'text': 'str', 'min_sections': 'int'}, outputs={'is_compound': 'bool'}, description='Fast compound-document heuristic check using separators, headers, and repeated lines.', tags=['compound', 'detect'])
    def is_compound_document(self, text: str, min_sections: int = 2) -> bool:
        lines = text.splitlines()
        if len(lines) < 10:
            return False

        sep_count = 0
        header_count = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if _SEPARATOR_RE.match(stripped):
                sep_count += 1
                for j in range(i + 1, min(i + 3, len(lines))):
                    if any(pat.match(lines[j].strip()) for pat in _FILE_HEADER_PATTERNS):
                        header_count += 1
                        break

        if header_count >= min_sections:
            return True
        if sep_count >= min_sections * 2:
            return True

        freq: Dict[str, List[int]] = defaultdict(list)
        for i, line in enumerate(lines):
            s = line.strip()
            if len(s) > 5:
                freq[s].append(i)

        for positions in freq.values():
            if len(positions) >= min_sections and self._is_roughly_periodic(positions):
                return True
        return False

    @service_endpoint(inputs={'text': 'str'}, outputs={'sections': 'list'}, description='Detect sections via separator + file header patterns.', tags=['compound', 'sections'])
    def detect_pattern_sections(self, text: str) -> List[Dict[str, Any]]:
        lines = text.splitlines()
        sections: List[Dict[str, Any]] = []
        i = 0

        while i < len(lines):
            if _SEPARATOR_RE.match(lines[i].strip()):
                j = i + 1
                while j < min(i + 4, len(lines)):
                    match = None
                    for pat in _FILE_HEADER_PATTERNS:
                        m = pat.match(lines[j].strip())
                        if m:
                            match = m
                            break
                    if match:
                        filename = match.group(1).strip()
                        content_start = j + 1
                        if content_start < len(lines) and _SEPARATOR_RE.match(lines[content_start].strip()):
                            content_start += 1

                        if sections:
                            sections[-1]['line_end'] = i - 1

                        ext = Path(filename).suffix.lower()
                        sections.append({
                            'name': filename,
                            'line_start': i,
                            'line_end': len(lines) - 1,
                            'content_start': content_start,
                            'source_type': self._classify_extension(ext),
                        })
                        i = content_start
                        break
                    j += 1
                else:
                    i += 1
            else:
                i += 1

        if sections:
            sections[-1]['line_end'] = len(lines) - 1
            for sec in sections:
                while sec['line_end'] > sec['content_start'] and not lines[sec['line_end']].strip():
                    sec['line_end'] -= 1
        return sections

    @service_endpoint(inputs={'text': 'str'}, outputs={'sections': 'list'}, description='Detect sections by repeated delimiter-like lines when explicit headers are absent.', tags=['compound', 'repetition'])
    def detect_repetition_sections(self, text: str) -> List[Dict[str, Any]]:
        lines = text.splitlines()
        freq: Dict[str, List[int]] = defaultdict(list)
        for i, line in enumerate(lines):
            s = line.strip()
            if len(s) >= 20:
                freq[s].append(i)

        delimiter_positions: List[int] = []
        for line_text, positions in freq.items():
            if len(positions) >= 2 and self._is_roughly_periodic(positions, tolerance=0.8):
                delimiter_positions.extend(positions)

        delimiter_positions = sorted(set(delimiter_positions))
        if len(delimiter_positions) < 2:
            return []

        sections: List[Dict[str, Any]] = []
        for idx, start in enumerate(delimiter_positions):
            end = delimiter_positions[idx + 1] - 1 if idx + 1 < len(delimiter_positions) else len(lines) - 1
            content_start = min(start + 1, end)
            if end - content_start + 1 < 2:
                continue
            sections.append({
                'name': f'virtual_section_{idx:02d}.txt',
                'line_start': start,
                'line_end': end,
                'content_start': content_start,
                'source_type': 'prose',
            })
        return sections

    @service_endpoint(inputs={'text': 'str'}, outputs={'sections': 'list', 'method': 'str'}, description='Full section detection: pattern first, repetition fallback.', tags=['compound', 'detect'])
    def detect_sections(self, text: str) -> Dict[str, Any]:
        pattern_sections = self.detect_pattern_sections(text)
        if pattern_sections:
            return {'sections': pattern_sections, 'method': 'pattern'}
        return {'sections': self.detect_repetition_sections(text), 'method': 'repetition'}

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

import time
from collections import defaultdict
from typing import Any, Dict, List

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceStructuralDelimiterMS',
    version='1.0.0',
    description='Pilfered from compound.find_structural_delimiters. Scores repeated line CIDs as structural delimiters.',
    tags=['compound', 'delimiter', 'analysis'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceStructuralDelimiterMS:
    def __init__(self):
        self.start_time = time.time()

    def _is_separator(self, text: str) -> bool:
        stripped = text.strip()
        if len(stripped) < 40:
            return False
        return len(set(stripped)) <= 3 and all(ch in '-=~#*_' for ch in set(stripped))

    def _is_roughly_periodic(self, positions: List[int], tolerance: float = 0.5) -> bool:
        if len(positions) < 3:
            return False
        gaps = [positions[i + 1] - positions[i] for i in range(len(positions) - 1)]
        avg = sum(gaps) / len(gaps)
        if avg <= 0:
            return False
        return all(abs(g - avg) / avg <= tolerance for g in gaps)

    @service_endpoint(inputs={'line_cids': 'list', 'lines': 'list', 'min_freq': 'int'}, outputs={'candidates': 'list'}, description='Score repeated line CIDs as likely structural delimiters.', tags=['compound', 'delimiter'])
    def find_structural_delimiters(self, line_cids: List[str], lines: List[str], min_freq: int = 3) -> List[Dict[str, Any]]:
        cid_positions: Dict[str, List[int]] = defaultdict(list)
        cid_text: Dict[str, str] = {}

        for i, (cid, line) in enumerate(zip(line_cids, lines)):
            stripped = line.strip()
            if len(stripped) > 3:
                cid_positions[cid].append(i)
                if cid not in cid_text:
                    cid_text[cid] = stripped

        candidates: List[Dict[str, Any]] = []
        for cid, positions in cid_positions.items():
            if len(positions) < min_freq:
                continue
            text = cid_text.get(cid, '')
            score = float(len(positions))
            if self._is_separator(text):
                score *= 3.0
            if self._is_roughly_periodic(positions, tolerance=0.5):
                score *= 2.0
            if len(text) < 10 and not self._is_separator(text):
                score *= 0.3
            candidates.append({'cid': cid, 'text': text, 'positions': positions, 'score': score})

        candidates.sort(key=lambda c: c['score'], reverse=True)
        return candidates

    @service_endpoint(inputs={'line_cids': 'list', 'lines': 'list', 'min_freq': 'int'}, outputs={'best': 'dict'}, description='Return top delimiter candidate or empty object if none.', tags=['compound', 'delimiter'])
    def best_delimiter(self, line_cids: List[str], lines: List[str], min_freq: int = 3) -> Dict[str, Any]:
        candidates = self.find_structural_delimiters(line_cids, lines, min_freq)
        return candidates[0] if candidates else {}

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float'}, description='Standardized health check for service status.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time}

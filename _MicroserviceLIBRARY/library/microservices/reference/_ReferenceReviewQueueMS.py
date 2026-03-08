import time
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_metadata, service_endpoint


@service_metadata(
    name='ReferenceReviewQueueMS',
    version='1.0.0',
    description='Pilfered from hitl.py. Headless review queue and decision summarization for human-in-the-loop orchestration.',
    tags=['hitl', 'review', 'workflow'],
    capabilities=['compute'],
    side_effects=[],
    internal_dependencies=['microservice_std_lib'],
    external_dependencies=[]
)
class ReferenceReviewQueueMS:
    ALLOWED_DECISIONS = {'ACCEPT', 'REJECT', 'SKIP', 'ACCEPT_ALL'}

    def __init__(self):
        self.start_time = time.time()
        self.items: List[Dict[str, Any]] = []

    @service_endpoint(inputs={'items': 'list'}, outputs={'queue_size': 'int'}, description='Initialize in-memory review queue with pending decisions.', tags=['hitl', 'queue'])
    def load_queue(self, items: List[Dict[str, Any]]) -> int:
        normalized = []
        for i, item in enumerate(items):
            row = dict(item)
            row.setdefault('item_id', f'item_{i:04d}')
            row.setdefault('title', row['item_id'])
            row.setdefault('description', '')
            row.setdefault('context', '')
            row.setdefault('candidates', [])
            row.setdefault('decision', None)
            row.setdefault('chosen_index', None)
            normalized.append(row)
        self.items = normalized
        return len(self.items)

    @service_endpoint(inputs={'item_id': 'str', 'decision': 'str', 'chosen_index': 'int'}, outputs={'ok': 'bool'}, description='Apply one review decision to a queue item.', tags=['hitl', 'decision'])
    def apply_decision(self, item_id: str, decision: str, chosen_index: Optional[int]=None) -> bool:
        d = decision.upper().strip()
        if d not in self.ALLOWED_DECISIONS:
            raise ValueError(f'Unsupported decision: {decision}')
        for item in self.items:
            if item.get('item_id') == item_id:
                item['decision'] = d
                item['chosen_index'] = chosen_index
                return True
        return False

    @service_endpoint(inputs={'decision': 'str'}, outputs={'updated': 'int'}, description='Apply a bulk decision to all undecided queue items.', tags=['hitl', 'decision'])
    def apply_bulk(self, decision: str) -> int:
        d = decision.upper().strip()
        if d not in self.ALLOWED_DECISIONS:
            raise ValueError(f'Unsupported decision: {decision}')
        updated = 0
        for item in self.items:
            if item.get('decision') is None:
                item['decision'] = d
                updated += 1
        return updated

    @service_endpoint(inputs={}, outputs={'summary': 'dict'}, description='Summarize review queue by decision class and completion state.', tags=['hitl', 'summary'])
    def summarize(self) -> Dict[str, Any]:
        summary = {'total': len(self.items), 'pending': 0, 'accepted': 0, 'rejected': 0, 'skipped': 0}
        for item in self.items:
            d = item.get('decision')
            if d is None:
                summary['pending'] += 1
            elif d == 'ACCEPT':
                summary['accepted'] += 1
            elif d == 'REJECT':
                summary['rejected'] += 1
            elif d == 'SKIP':
                summary['skipped'] += 1
            elif d == 'ACCEPT_ALL':
                summary['accepted'] += 1
        summary['completed'] = summary['pending'] == 0
        return summary

    @service_endpoint(inputs={}, outputs={'status': 'str', 'uptime': 'float', 'queue_size': 'int'}, description='Standardized health check for service status and queue state.', tags=['diagnostic', 'health'])
    def get_health(self):
        return {'status': 'online', 'uptime': time.time() - self.start_time, 'queue_size': len(self.items)}

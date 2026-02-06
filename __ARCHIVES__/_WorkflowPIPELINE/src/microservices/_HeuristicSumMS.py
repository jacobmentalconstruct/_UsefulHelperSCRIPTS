"""
SERVICE_NAME: _HeuristicSumMS
ENTRY_POINT: _HeuristicSumMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib
EXTERNAL_DEPENDENCIES: None
"""
import os
import re
from typing import Any, Dict, List, Optional
from microservice_std_lib import service_metadata, service_endpoint
from base_service import BaseService
SIG_RE = re.compile('^\\s*(def|class|function|interface|struct|impl|func)\\s+([A-Za-z_][A-Za-z0-9_]*)')
MD_HDR_RE = re.compile('^\\s{0,3}(#{1,3})\\s+(.+)')
DOC_RE = re.compile('^\\s*("{3}|\\\'{3})(.*)', re.DOTALL)

@service_metadata(name='HeuristicSum', version='1.0.0', description='Generates quick summaries of code/text files using regex heuristics (No AI).', tags=['parsing', 'summary', 'heuristics'], capabilities=['compute'], side_effects=[], internal_dependencies=['base_service', 'microservice_std_lib'], external_dependencies=[])
class HeuristicSumMS(BaseService):
    """
    The Skimmer: Generates quick summaries of code/text files without AI.
    Scans for high-value lines (headers, signatures, docstrings) and concatenates them.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        super().__init__('HeuristicSum')
        self.config = config or {}

    @service_endpoint(inputs={'text': 'str', 'filename': 'str', 'max_chars': 'int'}, outputs={'summary': 'str'}, description='Generates a summary string from the provided text.', tags=['summary', 'parsing'])
    def summarize(self, text: str, filename: str='', max_chars: int=480) -> str:
        """
        Generates a summary string from the provided text.
        """
        lines = text.splitlines()
        picks = []
        for ln in lines[:20]:
            m = MD_HDR_RE.match(ln)
            if m:
                picks.append(f'Heading: {m.group(2).strip()}')
        for ln in lines[:40]:
            m = SIG_RE.match(ln)
            if m:
                picks.append(f'{m.group(1)} {m.group(2)}')
        if lines:
            joined = '\n'.join(lines[:80])
            m = DOC_RE.match(joined)
            if m:
                after = joined.splitlines()[1:3]
                if after:
                    clean_doc = ' '.join((s.strip() for s in after)).strip()
                    picks.append(f'Doc: {clean_doc}')
        if not picks:
            head = ' '.join((l.strip() for l in lines[:2] if l.strip()))
            if head:
                picks.append(head)
        if filename:
            picks.append(f'[{os.path.basename(filename)}]')
        seen = set()
        uniq = []
        for p in picks:
            if p and p not in seen:
                uniq.append(p)
                seen.add(p)
        summary = ' | '.join(uniq)
        if len(summary) > max_chars:
            summary = summary[:max_chars - 3] + '...'
        return summary.strip() if summary else '[No summary available]'
if __name__ == '__main__':
    skimmer = HeuristicSumMS()
    print(f'Service ready: {skimmer}')
    py_code = "\n    class DataProcessor:\n        '''\n        Handles the transformation of raw input data into structured formats.\n        '''\n        def process(self, data):\n            pass\n    "
    print(f"Python Summary: {skimmer.summarize(py_code, 'processor.py')}")
    md_text = '\n    # Project Roadmap\n    ## Phase 1\n    We begin with ingestion.\n    '
    print(f"Markdown Summary: {skimmer.summarize(md_text, 'README.md')}")

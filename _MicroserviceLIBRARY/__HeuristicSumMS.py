"""
SERVICE_NAME: _HeuristicSumMS
ENTRY_POINT: __HeuristicSumMS.py
DEPENDENCIES: None
"""

import os
import re
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_metadata, service_endpoint, BaseService

# ==============================================================================
# CONFIGURATION: REGEX PATTERNS
# ==============================================================================
# Captures: def my_func, class MyClass, function myFunc, interface MyInterface
SIG_RE = re.compile(r'^\s*(def|class|function|interface|struct|impl|func)\s+([A-Za-z_][A-Za-z0-9_]*)')

# Captures: # Heading, ## Subheading
MD_HDR_RE = re.compile(r'^\s{0,3}(#{1,3})\s+(.+)')

# Captures: """ Docstring """ or ''' Docstring ''' (Start of block)
DOC_RE = re.compile(r'^\s*("{3}|\'{3})(.*)', re.DOTALL)

# ==============================================================================
# SERVICE DEFINITION
# ==============================================================================
@service_metadata(
    name="HeuristicSum",
    version="1.0.0",
    description="Generates quick summaries of code/text files using regex heuristics (No AI).",
    tags=["parsing", "summary", "heuristics"],
    capabilities=["compute"],
    dependencies=["re"],
    side_effects=[]
)
class HeuristicSumMS(BaseService):
    """
    The Skimmer: Generates quick summaries of code/text files without AI.
    Scans for high-value lines (headers, signatures, docstrings) and concatenates them.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("HeuristicSum")
        self.config = config or {}

    @service_endpoint(
        inputs={"text": "str", "filename": "str", "max_chars": "int"},
        outputs={"summary": "str"},
        description="Generates a summary string from the provided text.",
        tags=["summary", "parsing"]
    )
    def summarize(self, text: str, filename: str = "", max_chars: int = 480) -> str:
        """
        Generates a summary string from the provided text.
        """
        lines = text.splitlines()
        picks = []

        # 1. Scan top 20 lines for Markdown Headers
        for ln in lines[:20]:
            m = MD_HDR_RE.match(ln)
            if m:
                picks.append(f"Heading: {m.group(2).strip()}")

        # 2. Scan top 40 lines for Code Signatures (Functions/Classes)
        for ln in lines[:40]:
            m = SIG_RE.match(ln)
            if m:
                picks.append(f"{m.group(1)} {m.group(2)}")

        # 3. Check for Docstrings / Preamble
        if lines:
            # Join first 80 lines to check for multi-line docstrings
            joined = "\n".join(lines[:80])
            m = DOC_RE.match(joined)
            if m:
                # Grab the first few lines of the docstring content
                after = joined.splitlines()[1:3]
                if after:
                    clean_doc = " ".join(s.strip() for s in after).strip()
                    picks.append(f"Doc: {clean_doc}")

        # 4. Fallback: First non-empty line if nothing else found
        if not picks:
            head = " ".join(l.strip() for l in lines[:2] if l.strip())
            if head:
                picks.append(head)

        # 5. Add Filename Context
        if filename:
            picks.append(f"[{os.path.basename(filename)}]")

        # 6. Deduplicate and Format
        seen = set()
        uniq = []
        for p in picks:
            if p and p not in seen:
                uniq.append(p)
                seen.add(p)

        summary = " | ".join(uniq)
        
        # 7. Truncate
        if len(summary) > max_chars:
            summary = summary[:max_chars-3] + "..."
            
        return summary.strip() if summary else "[No summary available]"

# ==============================================================================
# SELF-TEST / RUNNER
# ==============================================================================
if __name__ == "__main__":
    skimmer = HeuristicSumMS()
    print(f"Service ready: {skimmer}")
    
    # Test 1: Python Code
    py_code = """
    class DataProcessor:
        '''
        Handles the transformation of raw input data into structured formats.
        '''
        def process(self, data):
            pass
    """
    print(f"Python Summary: {skimmer.summarize(py_code, 'processor.py')}")

    # Test 2: Markdown
    md_text = """
    # Project Roadmap
    ## Phase 1
    We begin with ingestion.
    """
    print(f"Markdown Summary: {skimmer.summarize(md_text, 'README.md')}")
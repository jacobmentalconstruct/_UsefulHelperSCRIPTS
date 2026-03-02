import re
import logging
from typing import Any, Dict, List, Optional, Set

from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION: PATTERNS
# ==============================================================================
# Python: "import x", "from x import y"
PY_IMPORT = re.compile(r'^\s*(?:from|import)\s+([\w\.]+)')

# JS/TS: "import ... from 'x'", "require('x')"
JS_IMPORT = re.compile(r'(?:import\s+.*?from\s+[\'"]|require\([\'"])([\.\/\w\-_]+)[\'"]')

logger = logging.getLogger("RegexWeaver")

# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="RegexWeaver",
    version="1.0.0",
    description="Fault-tolerant dependency extractor using Regex.",
    tags=["parsing", "dependencies", "regex"],
    capabilities=["compute"]
)
class RegexWeaverMS:
    """
    The Weaver: A fault-tolerant dependency extractor.
    Uses Regex to find imports, making it faster and more permissive
    than AST parsers (works on broken code).
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @service_endpoint(
        inputs={"content": "str", "language": "str"},
        outputs={"dependencies": "List[str]"},
        description="Scans code content for import statements.",
        tags=["parsing", "dependencies"],
        side_effects=[]
    )
    def extract_dependencies(self, content: str, language: str) -> List[str]:
        """
        Scans code content for import statements.
        :param language: 'python' or 'javascript' (includes ts/jsx).
        """
        dependencies: Set[str] = set()
        lines = content.splitlines()
        
        pattern = PY_IMPORT if language == 'python' else JS_IMPORT
        
        for line in lines:
            # Skip comments roughly
            if line.strip().startswith(('#', '//')):
                continue
                
            if language == 'python':
                match = pattern.match(line)
            else:
                match = pattern.search(line)
            
            if match:
                raw_dep = match.group(1)
                # Clean up: "backend.database" -> "database"
                # We usually want the leaf name for simple linking
                clean_dep = raw_dep.split('.')[-1].split('/')[-1]
                dependencies.add(clean_dep)
                
        return sorted(list(dependencies))


# --- Independent Test Block ---
if __name__ == "__main__":
    # Setup logging for test
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    
    weaver = RegexWeaverMS()
    print("Service ready:", weaver)
    
    # 1. Python Test
    py_code = """
    import os
    from backend.utils import helper
    # from commented.out import ignore_me
    import pandas as pd
    """
    print(f"Python Deps: {weaver.extract_dependencies(py_code, 'python')}")
    
    # 2. JS Test
    js_code = """
    import React from 'react';
    const utils = require('./lib/utils');
    // import hidden from 'hidden';
    """

    print(f"JS Deps:     {weaver.extract_dependencies(js_code, 'javascript')}")
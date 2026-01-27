import re
import logging
from typing import Any, Dict, List, Optional, Set
from microservice_std_lib import service_metadata, service_endpoint
PY_IMPORT = re.compile('^\\s*(?:from|import)\\s+([\\w\\.]+)')
JS_IMPORT = re.compile('(?:import\\s+.*?from\\s+[\\\'"]|require\\([\\\'"])([\\.\\/\\w\\-_]+)[\\\'"]')
logger = logging.getLogger('RegexWeaver')

@service_metadata(name='RegexWeaver', version='1.0.0', description='Fault-tolerant dependency extractor using Regex.', tags=['parsing', 'dependencies', 'regex'], capabilities=['compute'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class RegexWeaverMS:
    """
    The Weaver: A fault-tolerant dependency extractor.
    Uses Regex to find imports, making it faster and more permissive
    than AST parsers (works on broken code).
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}

    @service_endpoint(inputs={'content': 'str', 'language': 'str'}, outputs={'dependencies': 'List[str]'}, description='Scans code content for import statements.', tags=['parsing', 'dependencies'], side_effects=[])
    def extract_dependencies(self, content: str, language: str) -> List[str]:
        """
        Scans code content for import statements.
        :param language: 'python' or 'javascript' (includes ts/jsx).
        """
        dependencies: Set[str] = set()
        lines = content.splitlines()
        pattern = PY_IMPORT if language == 'python' else JS_IMPORT
        for line in lines:
            if line.strip().startswith(('#', '//')):
                continue
            if language == 'python':
                match = pattern.match(line)
            else:
                match = pattern.search(line)
            if match:
                raw_dep = match.group(1)
                clean_dep = raw_dep.split('.')[-1].split('/')[-1]
                dependencies.add(clean_dep)
        return sorted(list(dependencies))
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    weaver = RegexWeaverMS()
    print('Service ready:', weaver)
    py_code = '\n    import os\n    from backend.utils import helper\n    # from commented.out import ignore_me\n    import pandas as pd\n    '
    print(f"Python Deps: {weaver.extract_dependencies(py_code, 'python')}")
    js_code = "\n    import React from 'react';\n    const utils = require('./lib/utils');\n    // import hidden from 'hidden';\n    "
    print(f"JS Deps:     {weaver.extract_dependencies(js_code, 'javascript')}")

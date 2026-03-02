import sys
sys.path.append('..')
from orchestration import *
from dataclasses import dataclass

class EdgeRef:
    source_name: str
    target_name: str
    edge_type: str
    file_path: str
    lineno: int
import sys
sys.path.append('..')
from orchestration import *
from dataclasses import dataclass

class Block:
    text: str
    type: str
    name: str
    file_path: str
    start_line: int
    end_line: int
    hash: Optional[str] = None
    iri: Optional[URIRef] = None
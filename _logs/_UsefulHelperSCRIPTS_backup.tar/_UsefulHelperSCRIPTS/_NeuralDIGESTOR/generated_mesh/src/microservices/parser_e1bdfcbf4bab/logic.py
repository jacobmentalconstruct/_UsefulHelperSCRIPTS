import sys
sys.path.append('..')
from orchestration import *


class Parser:
    def parse(self, file_path: str, rel_path: str) -> Tuple[List[Block], List[EdgeRef]]:
        raise NotImplementedError
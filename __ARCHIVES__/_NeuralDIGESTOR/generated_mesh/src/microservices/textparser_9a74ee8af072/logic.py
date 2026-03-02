import sys
sys.path.append('..')
from orchestration import *


class TextParser(Parser):
    def parse(self, file_path: str, rel_path: str) -> Tuple[List[Block], List[EdgeRef]]:
        blocks: List[Block] = []
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        paragraphs = [p.strip('\n') for p in re.split(r'\n\s*\n', content) if p.strip()]
        line_idx = 1
        for i, para in enumerate(paragraphs):
            lines = para.split('\n')
            start = line_idx
            end = start + len(lines) - 1
            blocks.append(Block(text=para, type='paragraph', name=f"para{i+1}",
                                file_path=rel_path, start_line=start, end_line=end))
            line_idx = end + 2
        return blocks, []
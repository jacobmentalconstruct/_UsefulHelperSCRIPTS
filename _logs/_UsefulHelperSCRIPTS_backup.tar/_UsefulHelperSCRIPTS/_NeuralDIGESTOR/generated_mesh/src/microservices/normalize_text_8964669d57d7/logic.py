import sys
sys.path.append('..')
from orchestration import *


def normalize_text(text: str) -> str:
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return '\n'.join([line.rstrip() for line in text.split('\n')])
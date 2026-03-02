import sys
sys.path.append('..')
from orchestration import *
import hashlib

class ContentAddressableStore:
    def __init__(self, root: str) -> None:
        self.root = root
        os.makedirs(self.root, exist_ok=True)

    def _blob_path(self, digest: str) -> str:
        return os.path.join(self.root, digest[:2], f"{digest[2:]}.txt")

    def write_blob(self, data: str) -> str:
        norm = normalize_text(data)
        digest = hashlib.sha256(norm.encode('utf-8')).hexdigest()
        path = self._blob_path(digest)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):
            with open(path, 'w', encoding='utf-8') as f:
                f.write(norm)
        return digest
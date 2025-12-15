import os
from pathlib import Path
from typing import List, Optional
from .base_service import BaseService

class LibrarianService(BaseService):
    """
    The Manager. Handles creating, listing, and selecting Cartridges (.db files).
    """
    def __init__(self, storage_dir: str = "./cortex_dbs"):
        super().__init__("LibrarianService")
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.active_db_path: Optional[Path] = None

    def list_cartridges(self) -> List[str]:
        """Returns a list of available .db files."""
        return [f.name for f in self.storage_dir.glob("*.db")]

    def create_cartridge(self, name: str) -> str:
        """Creates a new DB path (does not initialize schema until loaded)."""
        if not name.endswith(".db"):
            name += ".db"
        return str(self.storage_dir / name)

    def set_active(self, name: str) -> str:
        """Sets the active DB path for other services to use."""
        db_path = self.storage_dir / name
        self.active_db_path = db_path
        return str(db_path)

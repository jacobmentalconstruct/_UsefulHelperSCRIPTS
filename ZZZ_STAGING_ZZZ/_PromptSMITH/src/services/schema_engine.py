# src/services/schema_engine.py
import json
import os
from typing import Callable, Dict, Optional


class SchemaEngine:
    """
    Responsible for:
      - Discovering schema JSON files in schemas_dir
      - Loading/parsing schemas into dicts
      - Polling for changes so new files appear without restart
    """

    def __init__(self, schemas_dir: str = "schemas"):
        self.schemas_dir = schemas_dir
        self._schemas: Dict[str, dict] = {}
        self._mtimes: Dict[str, float] = {}
        self.refresh()

    def refresh(self) -> None:
        os.makedirs(self.schemas_dir, exist_ok=True)

        new_schemas: Dict[str, dict] = {}
        new_mtimes: Dict[str, float] = {}

        for fname in os.listdir(self.schemas_dir):
            if not fname.lower().endswith(".json"):
                continue

            path = os.path.join(self.schemas_dir, fname)
            if not os.path.isfile(path):
                continue

            mtime = os.path.getmtime(path)
            new_mtimes[path] = mtime

            try:
                with open(path, "r", encoding="utf-8") as f:
                    schema = json.load(f)
            except Exception:
                # Malformed schema should be surfaced by UI actions;
                # for discovery we simply skip bad files.
                continue

            # Schema "name" defaults to filename stem
            schema_name = schema.get("name") or os.path.splitext(fname)[0]

            # Minimal structural expectations for our form-builder dialect
            # (kept intentionally lightweight)
            if "fields" not in schema or not isinstance(schema["fields"], list):
                continue

            new_schemas[schema_name] = schema

        self._schemas = new_schemas
        self._mtimes = new_mtimes

    def get_all_schemas(self) -> Dict[str, dict]:
        return dict(self._schemas)

    def get_schema(self, name: str) -> Optional[dict]:
        return self._schemas.get(name)

    # -------------------------
    # Polling / change detection
    # -------------------------

    def start_polling(self, tk_root, on_change: Callable[[], None], interval_ms: int = 1500) -> None:
        """
        Polls schemas_dir for filesystem changes and reloads schemas.
        If changes occur, calls on_change().

        This satisfies "add JSON schema files without needing a restart".
        """
        def tick():
            changed = self._detect_changes()
            if changed:
                self.refresh()
                on_change()
            tk_root.after(interval_ms, tick)

        tk_root.after(interval_ms, tick)

    def _detect_changes(self) -> bool:
        # Re-scan file list + mtimes and compare
        os.makedirs(self.schemas_dir, exist_ok=True)

        current_paths = set()
        for fname in os.listdir(self.schemas_dir):
            if fname.lower().endswith(".json"):
                current_paths.add(os.path.join(self.schemas_dir, fname))

        previous_paths = set(self._mtimes.keys())
        if current_paths != previous_paths:
            return True

        for path in current_paths:
            try:
                mtime = os.path.getmtime(path)
            except OSError:
                return True
            if self._mtimes.get(path) != mtime:
                return True

        return False

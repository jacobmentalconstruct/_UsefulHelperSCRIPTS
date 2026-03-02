"""
SERVICE_NAME: _ConfigStoreMS
ROLE: App Settings Persistence (Task 4.2)
"""
import json
import os
import logging
from typing import Dict, Any, Optional

class ConfigStoreMS:
    def __init__(self, filename="app_config.json"):
        self.filename = filename
        self.logger = logging.getLogger("ConfigStore")
        self.data = self._load_from_disk()

    def _load_from_disk(self) -> Dict[str, Any]:
        """Loads the JSON config or returns defaults if missing/corrupt."""
        if not os.path.exists(self.filename):
            return {}
        try:
            with open(self.filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load config: {e}")
            return {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any):
        """Updates internal data and triggers an atomic save."""
        self.data[key] = value
        self.save()

    def save(self):
        """Atomic write: Save to temp, then rename to original."""
        temp_file = f"{self.filename}.tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=4)
            os.replace(temp_file, self.filename)
        except Exception as e:
            self.logger.error(f"Atomic save failed: {e}")
            if os.path.exists(temp_file):
                os.remove(temp_file)

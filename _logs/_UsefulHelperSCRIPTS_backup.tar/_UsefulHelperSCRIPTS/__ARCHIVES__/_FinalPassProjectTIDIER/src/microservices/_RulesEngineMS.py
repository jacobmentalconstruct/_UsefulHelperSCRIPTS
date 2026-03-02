"""
SERVICE_NAME: _RulesEngineMS
ROLE: Operator Governance (Task 4.3)
"""
import logging
from typing import Dict, Any, Optional
from rules_contracts import get_default_rules

class RulesEngineMS:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.rules = get_default_rules()
        self.logger = logging.getLogger("RulesEngine")

    def get_rules(self) -> Dict[str, Any]:
        return self.rules.copy()

    def set_rules(self, new_rules: Dict[str, Any]):
        self.rules.update(new_rules)
        self.logger.info("Ruleset updated.")

    def evaluate_file(self, file_path: str) -> tuple:
        """Checks if a file is protected."""
        for p in self.rules.get("protected_files", []):
            if p in file_path:
                return False, f"File is protected by rule: {p}"
        return True, ""

    def evaluate_hunk(self, hunk: dict) -> tuple:
        """Checks hunk constraints like size or forbidden patterns."""
        content = hunk.get('content', '')
        if len(content) > self.rules.get("max_hunk_size", 99999):
            return False, "Hunk exceeds max_hunk_size"
            
        for pattern in self.rules.get("forbidden_patterns", []):
            if pattern in content:
                return False, f"Hunk contains forbidden pattern: {pattern}"
                
        return True, ""

"""
SERVICE_NAME: _RulesEngineMS
ROLE: Operator Governance (Task 4.3)
"""
import logging
from typing import Dict, Any, Optional
from .microservice_std_lib import service_metadata, service_endpoint
from .base_service import BaseService
def get_default_rules() -> Dict[str, Any]:
    """
    Returns the default safety contracts.
    Hardcoded here to remove dependency on external contract files.
    """
    return {
        "max_hunk_size": 10000,
        "protected_files": [
            "LICENSE.md", 
            "setup_env.bat", 
            ".gitignore",
            "requirements.txt"
        ],
        "forbidden_patterns": [
            "sk-proj-",  # OpenAI keys
            "ghp_",      # GitHub tokens
            "password ="
        ]
    }

@service_metadata(
    name='RulesEngine', 
    version='1.0.0', 
    description='Governance engine for safety and file protection.',
    tags=['governance', 'safety'],
    internal_dependencies=['base_service', 'microservice_std_lib']
)
class RulesEngineMS(BaseService):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__('RulesEngine')
        self.rules = get_default_rules()

    @service_endpoint(
        inputs={}, 
        outputs={'rules': 'Dict'},
        description='Returns current active ruleset.'
    )
    # ROLE: Returns current active ruleset.
    # INPUTS: {}
    # OUTPUTS: {"rules": "Dict"}
    def get_rules(self) -> Dict[str, Any]:
        return self.rules.copy()

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





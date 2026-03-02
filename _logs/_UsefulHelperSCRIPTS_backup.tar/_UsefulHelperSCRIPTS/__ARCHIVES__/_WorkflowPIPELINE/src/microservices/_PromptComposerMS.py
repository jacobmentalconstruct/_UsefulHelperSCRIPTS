"""
SERVICE_NAME: _PromptComposerMS
ROLE: AI Persona & Prompt Manager (Task 4.1)
"""
import logging
from typing import Dict, Any, Optional
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
    name='PromptComposer', 
    version='1.0.0', 
    description='Manages AI personas and instruction templates for tidying operations.', 
    tags=['ai', 'prompt-engineering', 'logic'], 
    capabilities=['prompt-composition'], 
    internal_dependencies=['microservice_std_lib']
)
class PromptComposerMS:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger("PromptComposer")
        
        # Default Template Structure
        self._template = {
            "system": "You are a senior software engineer specialized in code cleanup.",
            "instructions": "Remove all internal 'AI conversations', debug comments, and boilerplate clutter from the provided code hunk.",
            "constraints": "Maintain exact indentation and logic. Return ONLY the cleaned code. No chat, no markdown blocks.",
            "output_format": "RAW_CODE"
        }

    def get_template(self) -> Dict[str, str]:
        """Returns the current authoritative template."""
        return self._template.copy()

    def set_template(self, template: Dict[str, Any]):
        """Safely updates template keys, ignoring unknown or malformed inputs."""
        if not isinstance(template, dict):
            return
            
        for key in self._template.keys():
            if key in template and isinstance(template[key], str):
                self._template[key] = template[key]
        
        self.logger.info("Prompt template updated.")

    def validate_template(self, template_data: Any) -> tuple:
        """Validates template structure. Returns (is_ok, error_msg)."""
        if not isinstance(template_data, dict):
            return False, "Template must be a JSON object (dictionary)."
        
        required_keys = ["system", "instructions", "constraints"]
        missing = [k for k in required_keys if k not in template_data]
        if missing:
            return False, f"Missing required keys: {', '.join(missing)}"
        
        return True, """

    def compose(self, hunk_content: str, meta: Dict[str, Any]) -> str:
        """Assembles a full LLM prompt from the template and current context."""
        file_path = meta.get('file', 'unknown_file')
        hunk_name = meta.get('hunk_name', 'code_block')
        
        # Enforce safety limits on content
        safe_content = str(hunk_content)[:10000] 

        prompt = (
            f"{self._template['system']}\n\n"
            f"FILE CONTEXT: {file_path} > {hunk_name}\n"
            f"TASK: {self._template['instructions']}\n"
            f"CONSTRAINTS: {self._template['constraints']}\n\n"
            f"CODE HUNK:\n{safe_content}\n\n"
            f"CLEANED CODE:"
        )
        return prompt

    def compose_preview(self, meta: Dict[str, Any]) -> str:
        """Returns a preview of the prompt structure without the actual code."""
        return self.compose("{{ CODE_HUNK_GOES_HERE }}", meta)


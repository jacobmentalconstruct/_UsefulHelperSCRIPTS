# src/services/export_service.py
import json
from typing import Any, Dict


class ExportService:
    """
    Responsible for converting (schema, data) into injection-ready plain text.

    If schema provides "template", we do a {field} format expansion.
    Otherwise we fallback to pretty JSON.
    """

    def format_for_injection(self, schema: dict, data: Dict[str, Any]) -> str:
        template = schema.get("template")
        if template and isinstance(template, str):
            # Safe-ish formatting: unknown keys become blank
            class SafeDict(dict):
                def __missing__(self, key):
                    return ""

            return template.format_map(SafeDict(data)).rstrip() + "\n"

        # Fallback: JSON
        return json.dumps(data, ensure_ascii=False, indent=2).rstrip() + "\n"

"""Optional Ollama-backed assistant helpers."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Dict, List, Optional


class OllamaAssistantService:
    def list_models(self) -> List[Dict[str, Any]]:
        try:
            result = subprocess.run(['ollama', 'list'], capture_output=True, text=True, timeout=10, check=False)
        except Exception:
            return []
        lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
        if len(lines) <= 1:
            return []
        models: List[Dict[str, Any]] = []
        for line in lines[1:]:
            parts = re.split(r'\s{2,}', line)
            if not parts:
                continue
            name = parts[0].strip()
            size_text = parts[2].strip() if len(parts) > 2 else ''
            models.append({'name': name, 'size_text': size_text, 'size_b': self._parse_size_b(name, size_text)})
        return models

    def choose_default_model(self, size_cap_b: float) -> Optional[str]:
        compatible = [model for model in self.list_models() if model['size_b'] is None or model['size_b'] <= size_cap_b]
        if not compatible:
            return None
        compatible.sort(key=lambda item: item['size_b'] or 0.0, reverse=True)
        return compatible[0]['name']

    def summarize_service(self, model_name: str, service_payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = 'Summarize this microservice in 6 bullet points. Focus on purpose, dependencies, and risks.\n\n' + json.dumps(service_payload, indent=2)
        return self._run_model(model_name, prompt)

    def suggest_ui_schema(self, model_name: str, schema: Dict[str, Any], goal: str) -> Dict[str, Any]:
        prompt = 'Return JSON only. Suggest a revised ui_schema.json for this goal. Goal: ' + goal + '\n\nCurrent schema:\n' + json.dumps(schema, indent=2)
        return self._run_model(model_name, prompt)

    def _run_model(self, model_name: str, prompt: str) -> Dict[str, Any]:
        try:
            result = subprocess.run(['ollama', 'run', model_name, prompt], capture_output=True, text=True, timeout=60, check=False)
        except Exception as exc:
            return {'ok': False, 'error': str(exc), 'output': ''}
        output = result.stdout.strip()
        return {'ok': result.returncode == 0, 'error': result.stderr.strip(), 'output': output}

    def _parse_size_b(self, name: str, size_text: str) -> Optional[float]:
        for text in (name, size_text):
            match = re.search(r'(\d+(?:\.\d+)?)\s*[bB]', text)
            if match:
                try:
                    return float(match.group(1))
                except ValueError:
                    continue
        return None

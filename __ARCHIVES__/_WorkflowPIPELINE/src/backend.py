"""
Project: ARCHITECT
ROLE: Inference & AI Orchestration
"""
import requests
import json
import logging
import os
from typing import Optional, Dict, Any, List

OLLAMA_URL = "http://localhost:11434/api/generate"

class ArchitectBackend:
    def __init__(self, state_manager):
        self.state = state_manager
        self.logger = logging.getLogger("ArchitectBackend")

    def run_ollama_inference(self, prompt: str, model: str) -> Optional[str]:
        """Performs a non-streaming local inference via the Ollama API."""
        try:
            payload = {"model": model, "prompt": prompt, "stream": False}
            response = requests.post(OLLAMA_URL, json=payload, timeout=60)
            if response.status_code == 200:
                return response.json().get("response")
            return None
        except Exception as e:
            self.logger.error(f"Inference failed: {e}")
            return None

    def summarize_vision(self, text: str, model: str) -> Optional[str]:
        """Phase 1: Digestion of raw narrative into a formal Vision Statement."""
        prompt = (
            "Summarize the following application idea into a concise, professional vision statement. "
            "Focus strictly on the 'Core Value Loop'—what the app actually does. "
            "Keep the output under 150 words.\n\n"
            f"RAW IDEA: {text}\n\n"
            "VISION STATEMENT:"
        )
        return self.run_ollama_inference(prompt, model)

    def extract_intents(self, vision_summary: str, model: str) -> Optional[List[Dict]]:
        """Phase 2: Semantic Extraction of functional Verbs (Intents)."""
        prompt = (
            "Analyze the following app vision and list the primary functional 'Intents' (Verbs). "
            "Return ONLY a valid JSON array of objects with keys 'id', 'verb', and 'description'.\n\n"
            f"VISION: {vision_summary}\n\n"
            "JSON OUTPUT:"
        )
        response = self.run_ollama_inference(prompt, model)
        if response:
            try:
                # Sanitize response to extract JSON if the model included conversational filler
                clean_json = response.strip()
                if "```json" in clean_json:
                    clean_json = clean_json.split("```json")[1].split("```")[0].strip()
                return json.loads(clean_json)
            except Exception as e:
                self.logger.error(f"Failed to parse Intent JSON: {e}")
        return None

    def export_artifact(self, filename: str, content: str):
        """Physical Persistence: Writes validated artifacts to the project directory."""
        if not self.state.active_project: return
        p_id = self.state.active_project.project_id
        path = os.path.join(f"projects/{p_id}", filename)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        self.logger.info(f"Artifact saved: {path}")
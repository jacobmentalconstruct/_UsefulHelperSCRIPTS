"""
AIController – Manages inference loops and prompt formatting for local models.
Communicates with the Ollama API for generation and model listing.
"""
import requests
import threading
import json

OLLAMA_BASE = "http://localhost:11434"


class AIController:
    """
    Handles all AI inference operations.
    - Lists available local models
    - Formats prompts with context
    - Runs generation requests against Ollama
    """

    def __init__(self, log=None):
        self.log = log or (lambda msg: None)
        self._models = []

    # ── model discovery ─────────────────────────────────────

    def list_models(self):
        """Fetch available models from Ollama. Returns a list of model name strings."""
        try:
            resp = requests.get(f"{OLLAMA_BASE}/api/tags", timeout=3)
            if resp.status_code == 200:
                self._models = [m["name"] for m in resp.json().get("models", [])]
                self.log(f"Discovered {len(self._models)} local model(s).")
            else:
                self._models = []
                self.log(f"Ollama returned status {resp.status_code}")
        except Exception as e:
            self._models = []
            self.log(f"Ollama unreachable: {e}")
        return self._models

    # ── prompt formatting ───────────────────────────────────

    @staticmethod
    def format_prompt(user_message, context_chunks=None, system_prompt=None):
        """
        Build a prompt string for local model consumption.
        `context_chunks` is a list of chunk dicts from the sliding window.
        """
        parts = []

        if system_prompt:
            parts.append(system_prompt)

        if context_chunks:
            context_text = "\n---\n".join(ch["content"] for ch in context_chunks)
            parts.append(f"[CONTEXT]\n{context_text}\n[/CONTEXT]")

        parts.append(user_message)
        return "\n\n".join(parts)

    # ── generation ──────────────────────────────────────────

    def generate(self, model, prompt, stream_callback=None):
        """
        Send a generation request to Ollama.
        If `stream_callback` is provided, streams tokens to it.
        Otherwise, blocks and returns the full response string.
        """
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream_callback is not None,
        }

        try:
            resp = requests.post(
                f"{OLLAMA_BASE}/api/generate",
                json=payload,
                stream=(stream_callback is not None),
                timeout=120,
            )
            resp.raise_for_status()
        except Exception as e:
            error_msg = f"Generation failed: {e}"
            self.log(error_msg)
            return error_msg

        if stream_callback:
            full = []
            for line in resp.iter_lines():
                if line:
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    full.append(token)
                    stream_callback(token)
                    if chunk.get("done"):
                        break
            return "".join(full)
        else:
            data = resp.json()
            return data.get("response", "")

    def generate_async(self, model, prompt, on_token=None, on_done=None):
        """
        Run generation in a background thread.
        `on_token(str)` is called per token, `on_done(str)` with the full response.
        """
        def _run():
            result = self.generate(model, prompt, stream_callback=on_token)
            if on_done:
                on_done(result)

        threading.Thread(target=_run, daemon=True).start()

    # ── controller dispatch ─────────────────────────────────

    def handle(self, schema):
        """Controller dispatch for the BackendEngine."""
        action = schema.get("action")
        if action == "list_models":
            return {"status": "ok", "models": self.list_models()}
        elif action == "generate":
            model = schema.get("model", "")
            prompt = schema.get("prompt", "")
            context = schema.get("context_chunks")
            formatted = self.format_prompt(prompt, context, schema.get("system_prompt"))
            result = self.generate(model, formatted)
            return {"status": "ok", "response": result}
        return {"status": "error", "message": f"Unknown AI action: {action}"}

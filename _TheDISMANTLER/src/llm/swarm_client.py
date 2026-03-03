"""
SwarmClient – VRAM-aware Ollama API client for the Warm Constrained Swarm.

Manages two distinct model profiles within an 8GB VRAM budget:

  Scout  (qwen2.5-coder:0.5b) ~0.5GB VRAM
    - Triage/routing: reads Manifest + Query, returns chunk IDs
    - Kept warm indefinitely (keep_alive: -1)
    - Severely constricted KV cache (num_ctx: 512)
    - Deterministic output (temperature: 0.0)

  Surgeon (qwen2.5-coder:7b) ~6.0GB VRAM
    - Full analysis: reads anchored chunks + query, returns response
    - Full context window (num_ctx: 8192)
    - Default temperature for nuanced output

This module has ZERO awareness of database schema or context formatting.
It only constructs HTTP payloads and parses Ollama API responses.

Ollama API reference:
  POST /api/generate  — generation endpoint
  GET  /api/tags      — list loaded models
  POST /api/show      — model info
"""

import json
import requests

OLLAMA_BASE = "http://localhost:11434"

# ── Model Profiles ────────────────────────────────────────────

SCOUT_PROFILE = {
    "model":      "qwen2.5-coder:0.5b",
    "num_ctx":    512,
    "keep_alive": -1,           # Stay warm in VRAM indefinitely
    "temperature": 0.0,         # Deterministic routing — no creativity needed
    "vram_est":   "~0.5GB",     # Documentation only; not sent to API
}

SURGEON_PROFILE = {
    "model":      "qwen2.5-coder:7b",
    "num_ctx":    8192,
    "keep_alive": "5m",         # Default Ollama timeout
    "temperature": 0.7,         # Allow nuanced analysis
    "vram_est":   "~6.0GB",     # Documentation only; not sent to API
}


class SwarmClient:
    """
    Stateless Ollama HTTP client with profile-aware payload construction.

    Each method takes a prompt string and returns a response string.
    No internal state is mutated — profiles are module-level constants.
    """

    def __init__(self, base_url: str = None, log=None):
        """
        Args:
            base_url: Ollama API base URL. Defaults to http://localhost:11434
            log:      Optional logging callback (str -> None).
        """
        self.base_url = (base_url or OLLAMA_BASE).rstrip("/")
        self.log = log or (lambda msg: None)

    # ── Scout (Triage) ────────────────────────────────────────

    def scout(self, prompt: str) -> str:
        """
        Send a triage prompt to the Scout model (0.5b).

        The Scout reads the Manifest + Query and returns chunk IDs
        that are relevant to the query. Its response should be a
        compact JSON array or comma-separated list of chunk_ids.

        Args:
            prompt: Fully formatted triage prompt string.

        Returns:
            Raw response string from the Scout model.
        """
        payload = self._build_payload(SCOUT_PROFILE, prompt)
        self.log(f"Scout dispatch: {len(prompt)} chars, num_ctx={SCOUT_PROFILE['num_ctx']}")
        return self._post_generate(payload)

    # ── Surgeon (Analysis) ────────────────────────────────────

    def surgeon(self, prompt: str, stream_callback=None) -> str:
        """
        Send an analysis prompt to the Surgeon model (7b).

        The Surgeon receives anchored code chunks + query and returns
        a detailed, line-accurate response.

        Args:
            prompt:          Fully formatted analysis prompt string.
            stream_callback: Optional callback(str) invoked per token
                             for streaming output to the UI.

        Returns:
            Full response string from the Surgeon model.
        """
        payload = self._build_payload(SURGEON_PROFILE, prompt, stream=stream_callback is not None)
        self.log(f"Surgeon dispatch: {len(prompt)} chars, num_ctx={SURGEON_PROFILE['num_ctx']}")
        return self._post_generate(payload, stream_callback=stream_callback)

    # ── Model Management ──────────────────────────────────────

    def warm_up_scout(self) -> bool:
        """
        Pre-load the Scout model into VRAM by sending an empty prompt.

        This ensures the Scout is resident in memory before the first
        real query, eliminating cold-start latency. Should be called
        once at application boot.

        Returns:
            True if the warm-up succeeded, False otherwise.
        """
        payload = self._build_payload(SCOUT_PROFILE, "ping")
        self.log(f"Warming up Scout ({SCOUT_PROFILE['model']})...")
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            self.log(f"Scout warm — resident in VRAM (keep_alive={SCOUT_PROFILE['keep_alive']})")
            return True
        except Exception as e:
            self.log(f"Scout warm-up failed: {e}")
            return False

    def list_models(self) -> list:
        """
        Fetch available models from Ollama.

        Returns:
            List of model name strings, or empty list on failure.
        """
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception as e:
            self.log(f"Model listing failed: {e}")
        return []

    def check_models_available(self) -> dict:
        """
        Verify that both Scout and Surgeon models are available.

        Returns:
            {
                "scout_available": bool,
                "surgeon_available": bool,
                "scout_model": str,
                "surgeon_model": str,
                "available_models": [str, ...],
            }
        """
        available = self.list_models()
        scout_name = SCOUT_PROFILE["model"]
        surgeon_name = SURGEON_PROFILE["model"]

        return {
            "scout_available":   scout_name in available,
            "surgeon_available": surgeon_name in available,
            "scout_model":       scout_name,
            "surgeon_model":     surgeon_name,
            "available_models":  available,
        }

    # ── Internal ──────────────────────────────────────────────

    @staticmethod
    def _build_payload(profile: dict, prompt: str, stream: bool = False) -> dict:
        """
        Construct the Ollama /api/generate JSON payload from a profile.

        The payload structure:
        {
            "model":   "qwen2.5-coder:0.5b",
            "prompt":  "<the full prompt>",
            "stream":  false,
            "options": {
                "num_ctx":     512,
                "temperature": 0.0
            },
            "keep_alive": -1
        }

        Note: 'keep_alive' is a top-level key (not inside 'options').
        'num_ctx' and 'temperature' go inside 'options'.
        """
        return {
            "model":      profile["model"],
            "prompt":     prompt,
            "stream":     stream,
            "keep_alive": profile["keep_alive"],
            "options": {
                "num_ctx":     profile["num_ctx"],
                "temperature": profile["temperature"],
            },
        }

    def _post_generate(self, payload: dict, stream_callback=None) -> str:
        """
        Execute the HTTP POST to /api/generate and return the response.

        Handles both streaming and non-streaming modes:
        - Non-streaming: blocks until full response, returns response string
        - Streaming: yields tokens to stream_callback, returns full response

        Args:
            payload:         The JSON payload dict.
            stream_callback: Optional callback(str) for streaming tokens.

        Returns:
            Full response string. On error, returns "ERROR: <message>".
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                stream=payload.get("stream", False),
                timeout=120,
            )
            resp.raise_for_status()
        except requests.ConnectionError:
            msg = f"Ollama unreachable at {self.base_url}"
            self.log(msg)
            return f"ERROR: {msg}"
        except requests.Timeout:
            msg = "Ollama request timed out (120s)"
            self.log(msg)
            return f"ERROR: {msg}"
        except requests.HTTPError as e:
            msg = f"Ollama HTTP error: {e}"
            self.log(msg)
            return f"ERROR: {msg}"

        # ── Streaming mode ──
        if stream_callback:
            full_tokens = []
            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = chunk.get("response", "")
                if token:
                    full_tokens.append(token)
                    stream_callback(token)
                if chunk.get("done"):
                    break
            return "".join(full_tokens)

        # ── Non-streaming mode ──
        try:
            data = resp.json()
            return data.get("response", "")
        except json.JSONDecodeError:
            msg = "Invalid JSON in Ollama response"
            self.log(msg)
            return f"ERROR: {msg}"

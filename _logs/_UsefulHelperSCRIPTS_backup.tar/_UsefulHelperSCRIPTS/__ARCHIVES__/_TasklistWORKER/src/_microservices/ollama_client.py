import json
import urllib.request
import urllib.error


class OllamaClient:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip("/")

    # -----------------------------
    # Low-level helpers
    # -----------------------------

    def _read_json(self, resp) -> dict:
        raw = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception as e:
            raise RuntimeError(f"Ollama returned non-JSON response: {e}\nRAW:\n{raw}")

    def _request_json(self, method: str, path: str, payload: dict | None = None, timeout: int = 60) -> dict:
        url = f"{self.base_url}{path}"

        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=data, headers=headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return self._read_json(resp)
        except urllib.error.HTTPError as e:
            # HTTPError is also a file-like object; it may contain JSON
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                body = "<unable to read body>"
            raise RuntimeError(f"Ollama HTTPError {e.code} for {method} {path}: {e.reason}\nBODY:\n{body}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"Ollama URLError for {method} {path}: {e}")

    # -----------------------------
    # Public API
    # -----------------------------

    def list_models(self) -> list[str]:
        """Return list of installed model names via Ollama /api/tags."""
        obj = self._request_json("GET", "/api/tags", payload=None, timeout=30)
        models = []
        for m in obj.get("models", []) or []:
            name = m.get("name")
            if name:
                models.append(name)
        return models

    def generate(self, model: str, system: str, prompt: str, options: dict | None = None) -> str:
        """Uses Ollama /api/generate with system+prompt. Returns response text."""
        payload = {
            "model": model,
            "prompt": prompt,
            "system": system,
            "stream": False
        }
        if options:
            payload["options"] = options

        obj = self._request_json("POST", "/api/generate", payload=payload, timeout=300)
        return obj.get("response", "")


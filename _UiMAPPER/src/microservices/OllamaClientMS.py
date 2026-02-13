"""
OllamaClientMS
--------------
Minimal, dependency-free Ollama HTTP client using stdlib (urllib).

Responsibilities:
- List local models: GET /api/tags
- Generate text/JSON: POST /api/generate
- Provide timeouts + clear error reporting
- Optional streaming support (line-delimited JSON chunks)

Non-goals:
- UI
- Prompt building (InferencePromptBuilderMS)
- Output validation (InferenceResultValidatorMS)
"""

from __future__ import annotations

import json
import socket
import urllib.request
import urllib.error
from dataclasses import dataclass
from typing import Dict, Generator, List, Optional, Tuple, Union


# -------------------------
# Data Structures
# -------------------------

@dataclass(frozen=True)
class OllamaError:
    message: str
    status: Optional[int] = None
    detail: Optional[str] = None


@dataclass(frozen=True)
class OllamaResponse:
    ok: bool
    text: Optional[str] = None
    raw: Optional[Dict] = None
    error: Optional[OllamaError] = None


@dataclass
class OllamaClientConfig:
    base_url: str = "http://127.0.0.1:11434"
    timeout_sec: float = 30.0
    user_agent: str = "UiMapper/OllamaClientMS"


# -------------------------
# Service
# -------------------------

class OllamaClientMS:
    def __init__(self, config: Optional[OllamaClientConfig] = None):
        self.config = config or OllamaClientConfig()

    # -------------------------
    # Public API
    # -------------------------

    def list_models(self) -> OllamaResponse:
        """
        GET /api/tags
        Returns raw JSON plus convenience 'text' (None).
        """
        url = self._url("/api/tags")
        return self._get_json(url)

    def generate(
        self,
        *,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        format: Optional[str] = None,  # e.g. "json"
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        num_predict: Optional[int] = None,
        stream: bool = False,
        options: Optional[Dict] = None,
    ) -> Union[OllamaResponse, Generator[OllamaResponse, None, None]]:
        """
        POST /api/generate

        If stream=False:
            returns OllamaResponse with .text containing the full response field.

        If stream=True:
            returns generator yielding OllamaResponse per chunk (ok=True, raw=chunk, text=chunk.get("response")).
        """
        url = self._url("/api/generate")

        payload: Dict = {
            "model": model,
            "prompt": prompt,
            "stream": bool(stream),
        }
        if system is not None:
            payload["system"] = system
        if format is not None:
            payload["format"] = format
        if options is not None:
            payload["options"] = dict(options)

        # Convenience options
        if temperature is not None:
            payload.setdefault("options", {})
            payload["options"]["temperature"] = temperature
        if top_p is not None:
            payload.setdefault("options", {})
            payload["options"]["top_p"] = top_p
        if num_predict is not None:
            payload.setdefault("options", {})
            payload["options"]["num_predict"] = num_predict

        if stream:
            return self._post_stream_json(url, payload)
        return self._post_json(url, payload)

    # -------------------------
    # Internal HTTP helpers
    # -------------------------

    def _url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")
        if not path.startswith("/"):
            path = "/" + path
        return base + path

    def _headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": self.config.user_agent,
        }

    def _get_json(self, url: str) -> OllamaResponse:
        req = urllib.request.Request(url=url, headers=self._headers(), method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
                data = resp.read().decode("utf-8", errors="replace")
                raw = json.loads(data) if data.strip() else {}
                return OllamaResponse(ok=True, raw=raw)
        except urllib.error.HTTPError as e:
            return OllamaResponse(
                ok=False,
                error=OllamaError(
                    message="http_error",
                    status=getattr(e, "code", None),
                    detail=self._safe_read_http_error(e),
                ),
            )
        except urllib.error.URLError as e:
            return OllamaResponse(ok=False, error=OllamaError(message="url_error", detail=str(e)))
        except socket.timeout:
            return OllamaResponse(ok=False, error=OllamaError(message="timeout", detail=f">{self.config.timeout_sec}s"))
        except Exception as e:
            return OllamaResponse(ok=False, error=OllamaError(message="exception", detail=str(e)))

    def _post_json(self, url: str, payload: Dict) -> OllamaResponse:
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url=url, headers=self._headers(), data=body, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
                data = resp.read().decode("utf-8", errors="replace")
                raw = json.loads(data) if data.strip() else {}
                # Ollama returns "response" for generate
                text = raw.get("response")
                return OllamaResponse(ok=True, raw=raw, text=text)
        except urllib.error.HTTPError as e:
            return OllamaResponse(
                ok=False,
                error=OllamaError(
                    message="http_error",
                    status=getattr(e, "code", None),
                    detail=self._safe_read_http_error(e),
                ),
            )
        except urllib.error.URLError as e:
            return OllamaResponse(ok=False, error=OllamaError(message="url_error", detail=str(e)))
        except socket.timeout:
            return OllamaResponse(ok=False, error=OllamaError(message="timeout", detail=f">{self.config.timeout_sec}s"))
        except Exception as e:
            return OllamaResponse(ok=False, error=OllamaError(message="exception", detail=str(e)))

    def _post_stream_json(self, url: str, payload: Dict) -> Generator[OllamaResponse, None, None]:
        """
        Stream responses. Ollama streams JSON objects, one per line.
        """
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url=url, headers=self._headers(), data=body, method="POST")

        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout_sec) as resp:
                for line in resp:
                    try:
                        s = line.decode("utf-8", errors="replace").strip()
                        if not s:
                            continue
                        raw = json.loads(s)
                        yield OllamaResponse(ok=True, raw=raw, text=raw.get("response"))
                        if raw.get("done") is True:
                            break
                    except Exception as e:
                        yield OllamaResponse(ok=False, error=OllamaError(message="stream_parse_error", detail=str(e)))
                        break
        except urllib.error.HTTPError as e:
            yield OllamaResponse(
                ok=False,
                error=OllamaError(
                    message="http_error",
                    status=getattr(e, "code", None),
                    detail=self._safe_read_http_error(e),
                ),
            )
        except urllib.error.URLError as e:
            yield OllamaResponse(ok=False, error=OllamaError(message="url_error", detail=str(e)))
        except socket.timeout:
            yield OllamaResponse(ok=False, error=OllamaError(message="timeout", detail=f">{self.config.timeout_sec}s"))
        except Exception as e:
            yield OllamaResponse(ok=False, error=OllamaError(message="exception", detail=str(e)))

    def _safe_read_http_error(self, e: urllib.error.HTTPError) -> str:
        try:
            data = e.read().decode("utf-8", errors="replace")
            return data[:4000]
        except Exception:
            return ""


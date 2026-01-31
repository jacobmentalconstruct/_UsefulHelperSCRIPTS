import concurrent.futures
import logging
from typing import Optional, Dict, Any, List, Tuple

import requests

from src.microservices.microservice_std_lib import service_metadata, service_endpoint
from src.microservices.base_service import BaseService  # kept for std pattern / framework expectations

OLLAMA_API_URL = "http://localhost:11434/api"
logger = logging.getLogger("NeuralService")


@service_metadata(
    name="NeuralService",
    version="1.1.0",
    description="The Brain Interface: Orchestrates local AI operations via Ollama.",
    tags=["ai", "neural", "inference", "ollama"],
    capabilities=["text-generation", "embeddings", "parallel-processing", "health", "status"],
    internal_dependencies=["microservice_std_lib"],
    external_dependencies=["requests"],
)
class NeuralServiceMS:
    """
    Orchestrates local AI operations via Ollama for inference and embeddings.

    New in 1.1.0:
      - GET /api/version heartbeat
      - GET /api/ps running-models inspection
      - consolidated status payload for UI polling
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.max_workers = self.config.get("max_workers", 2)

        # Allow overriding Ollama URL via config
        self.ollama_api_url = self.config.get("ollama_api_url", OLLAMA_API_URL).rstrip("/")

        # Reuse a session (slightly faster, fewer sockets)
        self.session = requests.Session()

        self.models = {
            "fast": "qwen2.5-coder:1.5b-cpu",
            "smart": "qwen2.5:3b-cpu",
            "embed": "mxbai-embed-large:latest-cpu",
        }
        if "models" in self.config:
            self.models.update(self.config["models"])

    # -------------------------
    # Internal HTTP helpers
    # -------------------------

    def _url(self, path: str) -> str:
        # path examples: "tags", "ps", "version", "generate", "embeddings"
        return f"{self.ollama_api_url}/{path.lstrip('/')}"

    def _get_json(self, path: str, timeout: float = 2.0) -> Tuple[bool, int, Dict[str, Any], str]:
        try:
            res = self.session.get(self._url(path), timeout=timeout)
            status = res.status_code
            if status == 200:
                return True, status, res.json(), ""
            return False, status, {}, f"HTTP {status}"
        except Exception as e:
            return False, 0, {}, str(e)

    def _post_json(
        self, path: str, payload: Dict[str, Any], timeout: float = 30.0
    ) -> Tuple[bool, int, Dict[str, Any], str]:
        try:
            res = self.session.post(self._url(path), json=payload, timeout=timeout)
            status = res.status_code
            if status == 200:
                return True, status, res.json(), ""
            return False, status, {}, f"HTTP {status}"
        except Exception as e:
            return False, 0, {}, str(e)

    # -------------------------
    # Model configuration
    # -------------------------

    @service_endpoint(
        inputs={"fast_model": "str", "smart_model": "str", "embed_model": "str"},
        outputs={"status": "str", "config": "dict"},
        description="Updates the active model configurations on the fly.",
        tags=["config", "write"],
        side_effects=["config:update"],
    )
    def update_models(self, fast_model: str, smart_model: str, embed_model: str) -> Dict[str, Any]:
        self.models["fast"] = fast_model
        self.models["smart"] = smart_model
        self.models["embed"] = embed_model
        logger.info(f"Models Updated: Fast={fast_model}, Smart={smart_model}, Embed={embed_model}")
        return {"status": "success", "config": dict(self.models)}

    # -------------------------
    # Ollama health + status
    # -------------------------

    @service_endpoint(
        inputs={},
        outputs={"ok": "bool", "version": "str", "error": "str"},
        description="Gets the Ollama server version (best connectivity heartbeat).",
        tags=["health", "read"],
        side_effects=["network:read"],
    )
    def get_version(self) -> Dict[str, Any]:
        ok, _, data, err = self._get_json("version", timeout=2.0)
        if not ok:
            logger.error(f"Ollama get_version failed: {err}")
            return {"ok": False, "version": "", "error": err}
        return {"ok": True, "version": str(data.get("version", "")), "error": ""}

    @service_endpoint(
        inputs={},
        outputs={"ok": "bool", "models": "list", "error": "str"},
        description="Lists models currently loaded into memory (running) via /api/ps.",
        tags=["status", "read"],
        side_effects=["network:read"],
    )
    def list_running_models(self) -> Dict[str, Any]:
        ok, _, data, err = self._get_json("ps", timeout=2.0)
        if not ok:
            # Not fatal; UI can still show reachable + no running models
            logger.warning(f"Ollama list_running_models failed: {err}")
            return {"ok": False, "models": [], "error": err}
        return {"ok": True, "models": data.get("models", []) or [], "error": ""}

    @service_endpoint(
        inputs={"model": "str"},
        outputs={"ok": "bool", "details": "dict", "error": "str"},
        description="Shows details for a given model via /api/show.",
        tags=["status", "read"],
        side_effects=["network:read"],
    )
    def show_model(self, model: str) -> Dict[str, Any]:
        payload = {"model": model}
        ok, _, data, err = self._post_json("show", payload, timeout=5.0)
        if not ok:
            logger.warning(f"Ollama show_model({model}) failed: {err}")
            return {"ok": False, "details": {}, "error": err}
        return {"ok": True, "details": data, "error": ""}

    @service_endpoint(
        inputs={},
        outputs={
            "ok": "bool",
            "ollama_version": "str",
            "configured_models": "dict",
            "running_models": "list",
            "error": "str",
        },
        description="Consolidated status payload for UI polling: connectivity + configured + running.",
        tags=["status", "read"],
        side_effects=["network:read"],
    )
    def get_status(self) -> Dict[str, Any]:
        ver = self.get_version()
        if not ver.get("ok"):
            return {
                "ok": False,
                "ollama_version": "",
                "configured_models": dict(self.models),
                "running_models": [],
                "error": ver.get("error", "unknown error"),
            }

        ps = self.list_running_models()
        return {
            "ok": True,
            "ollama_version": ver.get("version", ""),
            "configured_models": dict(self.models),
            "running_models": ps.get("models", []) if ps.get("ok") else [],
            "error": "" if ps.get("ok") else (ps.get("error", "") or ""),
        }

    # -------------------------
    # Host stats for UI (best-effort)
    # -------------------------

    def _bytes_to_gb(self, n: float) -> float:
        try:
            return round(float(n) / (1024.0 ** 3), 2)
        except Exception:
            return 0.0

    def _get_cpu_name(self) -> str:
        # Windows best-effort via CIM, else platform.processor()
        try:
            import platform
            name = (platform.processor() or "").strip()
            if name:
                return name
        except Exception:
            pass

        try:
            import subprocess
            cmd = [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_Processor | Select-Object -First 1 -ExpandProperty Name)"
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=2)
            name = out.decode("utf-8", errors="ignore").strip()
            return name
        except Exception:
            return ""

    def _get_ram(self) -> Dict[str, float]:
        # Prefer psutil if installed
        try:
            import psutil  # type: ignore
            vm = psutil.virtual_memory()
            used = float(vm.total - vm.available)
            total = float(vm.total)
            return {
                "ram_used_gb": self._bytes_to_gb(used),
                "ram_total_gb": self._bytes_to_gb(total),
            }
        except Exception:
            return {"ram_used_gb": 0.0, "ram_total_gb": 0.0}

    def _get_gpu(self) -> Dict[str, Any]:
        # NVIDIA best-effort: try pynvml, then nvidia-smi. Otherwise blank.
        try:
            from pynvml import (  # type: ignore
                nvmlInit,
                nvmlDeviceGetHandleByIndex,
                nvmlDeviceGetName,
                nvmlDeviceGetMemoryInfo,
            )
            nvmlInit()
            h = nvmlDeviceGetHandleByIndex(0)
            name = nvmlDeviceGetName(h).decode("utf-8", errors="ignore")
            mem = nvmlDeviceGetMemoryInfo(h)
            return {
                "gpu_name": name,
                "vram_used_gb": self._bytes_to_gb(mem.used),
                "vram_total_gb": self._bytes_to_gb(mem.total),
            }
        except Exception:
            pass

        try:
            import subprocess
            cmd = [
                "nvidia-smi",
                "--query-gpu=name,memory.used,memory.total",
                "--format=csv,noheader,nounits",
            ]
            out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=2)
            line = out.decode("utf-8", errors="ignore").strip().splitlines()[0]
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                name = parts[0]
                used = float(parts[1]) / 1024.0
                total = float(parts[2]) / 1024.0
                return {
                    "gpu_name": name,
                    "vram_used_gb": round(used, 2),
                    "vram_total_gb": round(total, 2),
                }
        except Exception:
            pass

        return {"gpu_name": "", "vram_used_gb": 0.0, "vram_total_gb": 0.0}

    @service_endpoint(
        inputs={},
        outputs={
            "cpu_name": "str",
            "ram_used_gb": "float",
            "ram_total_gb": "float",
            "gpu_name": "str",
            "vram_used_gb": "float",
            "vram_total_gb": "float",
        },
        description="Best-effort host stats for UI: CPU/RAM + GPU/VRAM.",
        tags=["status", "read"],
        side_effects=[],
    )
    def get_system_stats(self) -> Dict[str, Any]:
        cpu = self._get_cpu_name()
        ram = self._get_ram()
        gpu = self._get_gpu()
        return {
            "cpu_name": cpu,
            **ram,
            **gpu,
        }

    @service_endpoint(
        inputs={},
        outputs={
            "ok": "bool",
            "ollama_version": "str",
            "configured_models": "dict",
            "running_models": "list",
            "loaded_model": "str",
            "cpu_name": "str",
            "ram_used_gb": "float",
            "ram_total_gb": "float",
            "gpu_name": "str",
            "vram_used_gb": "float",
            "vram_total_gb": "float",
            "error": "str",
        },
        description="Single consolidated payload for UI: ollama status + loaded model + host stats.",
        tags=["status", "read"],
        side_effects=["network:read"],
    )
    def get_ui_status(self) -> Dict[str, Any]:
        st = self.get_status()
        sysinfo = self.get_system_stats()

        loaded = ""
        try:
            rms = st.get("running_models") or []
            if rms and isinstance(rms, list):
                # /api/ps returns dicts like {"name": "model:tag", ...}
                if isinstance(rms[0], dict):
                    loaded = str(rms[0].get("name", "") or "")
                else:
                    loaded = str(rms[0])
        except Exception:
            loaded = ""

        return {
            "ok": bool(st.get("ok")),
            "ollama_version": str(st.get("ollama_version", "")),
            "configured_models": dict(st.get("configured_models") or {}),
            "running_models": st.get("running_models") or [],
            "loaded_model": loaded,
            "cpu_name": str(sysinfo.get("cpu_name", "") or ""),
            "ram_used_gb": float(sysinfo.get("ram_used_gb", 0.0) or 0.0),
            "ram_total_gb": float(sysinfo.get("ram_total_gb", 0.0) or 0.0),
            "gpu_name": str(sysinfo.get("gpu_name", "") or ""),
            "vram_used_gb": float(sysinfo.get("vram_used_gb", 0.0) or 0.0),
            "vram_total_gb": float(sysinfo.get("vram_total_gb", 0.0) or 0.0),
            "error": str(st.get("error", "") or ""),
        }

    @service_endpoint(
        inputs={},
        outputs={"is_alive": "bool"},
        description="Pings Ollama to verify connectivity (uses /api/version).",
        tags=["health", "read"],
        side_effects=["network:read"],
    )
    def check_connection(self) -> bool:
        ver = self.get_version()
        if ver.get("ok"):
            return True
        logger.error("Ollama connection failed. Is 'ollama serve' running?")
        return False

    # -------------------------
    # Existing endpoints (rewired to helpers)
    # -------------------------

    @service_endpoint(
        inputs={},
        outputs={"models": "List[str]"},
        description="Fetches a list of available models from the local Ollama instance.",
        tags=["ai", "read"],
        side_effects=["network:read"],
    )
    def get_available_models(self) -> List[str]:
        ok, _, data, err = self._get_json("tags", timeout=2.0)
        if not ok:
            logger.error(f"Failed to fetch models: {err}")
            return []
        return [m.get("name", "") for m in (data.get("models", []) or []) if m.get("name")]

    @service_endpoint(
        inputs={"text": "str"},
        outputs={"embedding": "list"},
        description="Generates a vector embedding for the provided text.",
        tags=["nlp", "vector", "ai"],
        side_effects=["network:read"],
    )
    def get_embedding(self, text: str) -> Optional[List[float]]:
        payload = {"model": self.models["embed"], "prompt": text}
        ok, _, data, err = self._post_json("embeddings", payload, timeout=30.0)
        if not ok:
            logger.error(f"Embedding failed: {err}")
            return None
        return data.get("embedding")

    @service_endpoint(
        inputs={"prompt": "str", "tier": "str", "format_json": "bool"},
        outputs={"response": "str"},
        description="Requests synchronous text generation from a local LLM.",
        tags=["llm", "inference"],
        side_effects=["network:read"],
    )
    def request_inference(self, prompt: str, tier: str = "fast", format_json: bool = False) -> str:
        model = self.models.get(tier, self.models["fast"])
        payload: Dict[str, Any] = {"model": model, "prompt": prompt, "stream": False}
        if format_json:
            payload["format"] = "json"

        ok, _, data, err = self._post_json("generate", payload, timeout=60.0)
        if not ok:
            logger.error(f"Inference ({tier}) failed: {err}")
            return ""
        return (data.get("response") or "").strip()

    def process_parallel(self, items: List[Any], worker_func) -> List[Any]:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(worker_func, item): item for item in items}
            for future in concurrent.futures.as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.error(f"Worker task failed: {e}")
        return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    svc = NeuralServiceMS()
    print("Service ready:", svc)

    status = svc.get_status()
    print("Status:", status)

    if svc.check_connection():
        print("Ollama Connection: OK")
        print(f"Models available: {svc.get_available_models()}")
        print("Running models:", svc.list_running_models())
        print("Testing Inference (Fast Tier)...")
        response = svc.request_inference("Why is the sky blue? Answer in 1 sentence.")
        print(f"Response: {response}")
    else:
        print("Ollama Connection: FAILED (Is Ollama running?)")


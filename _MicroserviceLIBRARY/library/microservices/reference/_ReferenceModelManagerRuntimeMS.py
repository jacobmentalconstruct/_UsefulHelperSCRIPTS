import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_endpoint, service_metadata


def _parse_pooling_type(pooling: Any) -> Optional[int]:
    if pooling is None:
        return None
    if isinstance(pooling, int):
        return pooling
    mapping = {"none": 0, "mean": 1, "cls": 2, "last": 3}
    if isinstance(pooling, str):
        return mapping.get(pooling.strip().lower(), 1)
    return None


@service_metadata(
    name="ReferenceModelManagerRuntimeMS",
    version="1.0.0",
    description="Pilfered from models/manager.py runtime logic. Computes llama.cpp params, cache status, and reload decisions without loading model binaries.",
    tags=["models", "runtime", "llama-cpp", "settings"],
    capabilities=["filesystem:read", "cpu:introspection"],
    side_effects=["filesystem:read"],
    internal_dependencies=["microservice_std_lib"],
    external_dependencies=[],
)
class ReferenceModelManagerRuntimeMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(
        inputs={"cpu_count": "int|None"},
        outputs={"threads": "int"},
        description="Compute a conservative thread count using half logical CPUs with floor of 2.",
        tags=["models", "runtime", "performance"],
    )
    def cpu_threads(self, cpu_count: Optional[int] = None) -> int:
        count = int(cpu_count) if cpu_count else int(os.cpu_count() or 4)
        return max(2, count // 2)

    @service_endpoint(
        inputs={"spec": "dict"},
        outputs={"size_hint": "str"},
        description="Estimate download size text from model spec min_size_bytes.",
        tags=["models", "download", "settings"],
    )
    def size_hint(self, spec: Dict[str, Any]) -> str:
        min_mb = float(spec.get("min_size_bytes", 0)) / 1_048_576
        return f"~{min_mb:.0f} MB"

    @service_endpoint(
        inputs={"models_dir": "str", "spec": "dict"},
        outputs={"status": "dict"},
        description="Inspect cache path and classify model file as missing, truncated, or ready.",
        tags=["models", "cache", "filesystem"],
        side_effects=["filesystem:read"],
    )
    def model_cache_status(self, models_dir: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        filename = str(spec.get("filename", "")).strip()
        min_size = int(spec.get("min_size_bytes", 10_000_000))
        if not filename:
            return {"ok": False, "error": "missing_filename"}

        dest = Path(models_dir) / filename
        if not dest.exists():
            return {
                "ok": True,
                "state": "missing",
                "path": str(dest),
                "min_size_bytes": min_size,
                "size_bytes": 0,
            }

        size_bytes = int(dest.stat().st_size)
        if size_bytes < min_size:
            return {
                "ok": True,
                "state": "truncated",
                "path": str(dest),
                "min_size_bytes": min_size,
                "size_bytes": size_bytes,
            }

        return {
            "ok": True,
            "state": "ready",
            "path": str(dest),
            "min_size_bytes": min_size,
            "size_bytes": size_bytes,
        }

    @service_endpoint(
        inputs={"models_dir": "str", "spec": "dict"},
        outputs={"plan": "dict"},
        description="Build deterministic download plan paths and validation thresholds for a model spec.",
        tags=["models", "download", "planning"],
    )
    def build_download_plan(self, models_dir: str, spec: Dict[str, Any]) -> Dict[str, Any]:
        filename = str(spec.get("filename", "")).strip()
        url = str(spec.get("url", "")).strip()
        min_size = int(spec.get("min_size_bytes", 10_000_000))
        if not filename or not url:
            return {"ok": False, "error": "missing_filename_or_url"}

        dest = Path(models_dir) / filename
        temp = dest.with_suffix(dest.suffix + ".tmp")
        return {
            "ok": True,
            "filename": filename,
            "url": url,
            "dest_path": str(dest),
            "temp_path": str(temp),
            "min_size_bytes": min_size,
            "size_hint": self.size_hint(spec),
        }

    @service_endpoint(
        inputs={"spec": "dict"},
        outputs={"params": "dict"},
        description="Compute model-aware llama.cpp kwargs for embedding models.",
        tags=["models", "embed", "llama-cpp"],
    )
    def compute_embedder_params(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        ctx = int(spec.get("context_length", 512))
        params: Dict[str, Any] = {
            "embedding": True,
            "n_ctx": ctx,
            "n_batch": ctx,
            "n_threads": self.cpu_threads(),
            "verbose": False,
        }
        pooling = _parse_pooling_type(spec.get("pooling_type"))
        if pooling is not None:
            params["pooling_type"] = pooling
        if ctx > 2048:
            params["type_k"] = 1
            params["type_v"] = 1
        return params

    @service_endpoint(
        inputs={"spec": "dict"},
        outputs={"params": "dict"},
        description="Compute model-aware llama.cpp kwargs for extraction/text generation models.",
        tags=["models", "extract", "llama-cpp"],
    )
    def compute_extractor_params(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        ctx = int(spec.get("context_length", 2048))
        return {
            "n_ctx": ctx,
            "n_batch": min(ctx, 512),
            "n_threads": self.cpu_threads(),
            "verbose": False,
        }

    @service_endpoint(
        inputs={"loaded_filename": "str|None", "selected_filename": "str"},
        outputs={"should_reload": "bool"},
        description="Determine if an in-memory model instance should be reloaded after a settings change.",
        tags=["models", "settings", "runtime"],
    )
    def should_reload_model(self, loaded_filename: Optional[str], selected_filename: str) -> bool:
        selected = str(selected_filename or "").strip()
        if not selected:
            return False
        loaded = (loaded_filename or "").strip()
        return bool(loaded and loaded != selected)

    @service_endpoint(
        inputs={"result": "Any"},
        outputs={"vector": "list[float]"},
        description="Normalize embedding result payloads across llama-cpp versions.",
        tags=["models", "embed", "compatibility"],
    )
    def normalize_embedding_result(self, result: Any) -> List[float]:
        if isinstance(result, list) and result and isinstance(result[0], list):
            return [float(x) for x in result[0]]
        if isinstance(result, list):
            return [float(x) for x in result]
        return []

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float"},
        description="Standardized health check for service status.",
        tags=["diagnostic", "health"],
    )
    def get_health(self):
        return {"status": "online", "uptime": time.time() - self.start_time}
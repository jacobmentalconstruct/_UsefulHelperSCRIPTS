import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_endpoint, service_metadata


KNOWN_MODELS: List[Dict[str, Any]] = [
    {
        "role": "embedder",
        "filename": "nomic-embed-text-v1.5.Q4_K_M.gguf",
        "display_name": "Nomic Embed Text v1.5 (Q4_K_M)",
        "description": "Fast, small, 768-dim. Good all-round default. ~80 MB.",
        "url": "https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.Q4_K_M.gguf",
        "sha256": None,
        "dims": 768,
        "context_length": 8192,
        "min_size_bytes": 50_000_000,
    },
    {
        "role": "embedder",
        "filename": "mxbai-embed-large-v1.Q4_K_M.gguf",
        "display_name": "MixedBread Embed Large v1 (Q4_K_M)",
        "description": "Higher quality, 1024-dim. Better for technical docs. ~216 MB.",
        "url": "https://huggingface.co/ChristianAzinn/mxbai-embed-large-v1-gguf/resolve/main/mxbai-embed-large-v1.Q4_K_M.gguf",
        "sha256": None,
        "dims": 1024,
        "context_length": 512,
        "min_size_bytes": 150_000_000,
    },
    {
        "role": "embedder",
        "filename": "all-MiniLM-L6-v2-Q4_K_M.gguf",
        "display_name": "All-MiniLM L6 v2 (Q4_K_M)",
        "description": "Tiny and very fast, 384-dim. Good for large codebases. ~22 MB.",
        "url": "https://huggingface.co/second-state/All-MiniLM-L6-v2-Embedding-GGUF/resolve/main/all-MiniLM-L6-v2-Q4_K_M.gguf",
        "sha256": None,
        "dims": 384,
        "context_length": 512,
        "min_size_bytes": 15_000_000,
    },
    {
        "role": "extractor",
        "filename": "qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "display_name": "Qwen 2.5 0.5B Instruct (Q4_K_M)",
        "description": "Tiny and fast. Lower extraction accuracy. ~398 MB.",
        "url": "https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/main/qwen2.5-0.5b-instruct-q4_k_m.gguf",
        "sha256": None,
        "dims": None,
        "context_length": 8192,
        "min_size_bytes": 300_000_000,
    },
    {
        "role": "extractor",
        "filename": "qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "display_name": "Qwen 2.5 1.5B Instruct (Q4_K_M)",
        "description": "Better entity extraction quality. ~1 GB.",
        "url": "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf",
        "sha256": None,
        "dims": None,
        "context_length": 8192,
        "min_size_bytes": 800_000_000,
    },
]

MAX_CHUNK_TOKENS = 512
OVERLAP_LINES = 3
SUMMARY_CHUNK_TOKENS = 256
EMBEDDING_DIMS = 768
EMBEDDING_BATCH = 16
PIPELINE_VERSION = "0.1.0"

EDGE_TYPES = [
    "PART_OF",
    "PRECEDES",
    "FOLLOWS",
    "MENTIONS",
    "ELABORATES",
    "CONTRADICTS",
    "NEAR_DUPLICATE",
    "RELATES_TO",
]

CODE_EXTENSIONS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp",
    ".h", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".scala", ".r", ".sh",
    ".bash", ".zsh",
}
PROSE_EXTENSIONS = {
    ".md", ".markdown", ".txt", ".rst", ".adoc", ".org", ".tex", ".text",
}
STRUCTURED_EXTENSIONS = {
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".xml", ".csv", ".tsv",
}
SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".bin", ".jpg", ".jpeg", ".png",
    ".gif", ".pdf", ".zip", ".gz", ".tar", ".rar", ".7z", ".mp3", ".mp4", ".mov", ".avi",
}
SKIP_DIRS = {
    ".git", "__pycache__", ".mypy_cache", ".pytest_cache", "node_modules", ".venv", "venv",
    "env", ".env", "dist", "build", ".tox", ".eggs", "*.egg-info",
}

ENTITY_EXTRACTION_PROMPT = """You are a precise information extractor. Given the text below, extract:
1. Named entities (people, organizations, products, technologies, locations)
2. Key concepts and domain terms
3. Relationships between entities where clearly stated

Return ONLY a JSON object with this exact schema - no explanation, no markdown:
{
  \"entities\": [
    {\"text\": \"<entity text>\", \"type\": \"<PERSON|ORG|PRODUCT|TECH|LOCATION|CONCEPT>\", \"salience\": <0.0-1.0>}
  ],
  \"relationships\": [
    {\"subject\": \"<entity text>\", \"predicate\": \"<verb or relation>\", \"object\": \"<entity text>\"}
  ]
}

TEXT:
{chunk_text}
"""


@service_metadata(
    name="ReferenceConfigRegistryMS",
    version="1.0.0",
    description="Pilfered from config.py. Exposes model registry, path resolution, extension typing, and ingest constants.",
    tags=["config", "models", "pipeline", "registry"],
    capabilities=["filesystem:path", "env:read", "compute"],
    side_effects=[],
    internal_dependencies=["microservice_std_lib"],
    external_dependencies=[],
)
class ReferenceConfigRegistryMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(
        inputs={"cache_root_override": "str|None"},
        outputs={"paths": "dict"},
        description="Resolve cache/models directories from override or TRIPARTITE_CACHE env fallback.",
        tags=["config", "paths"],
    )
    def get_cache_paths(self, cache_root_override: Optional[str] = None) -> Dict[str, str]:
        cache_dir = Path(cache_root_override) if cache_root_override else Path(os.environ.get("TRIPARTITE_CACHE", Path.home() / ".tripartite"))
        models_dir = cache_dir / "models"
        return {"cache_dir": str(cache_dir), "models_dir": str(models_dir)}

    @service_endpoint(
        inputs={"role": "str|None"},
        outputs={"models": "list"},
        description="Return known model specs, optionally filtered by role embedder|extractor.",
        tags=["config", "models"],
    )
    def get_known_models(self, role: Optional[str] = None) -> List[Dict[str, Any]]:
        if role is None:
            return [dict(m) for m in KNOWN_MODELS]
        role_norm = role.strip().lower()
        return [dict(m) for m in KNOWN_MODELS if str(m.get("role", "")).lower() == role_norm]

    @service_endpoint(
        inputs={"role": "str"},
        outputs={"model": "dict"},
        description="Return default model for a role (first match in registry).",
        tags=["config", "models", "defaults"],
    )
    def get_default_model(self, role: str) -> Dict[str, Any]:
        matches = self.get_known_models(role)
        return matches[0] if matches else {}

    @service_endpoint(
        inputs={"filename": "str"},
        outputs={"model": "dict"},
        description="Lookup model spec by cached filename.",
        tags=["config", "models", "lookup"],
    )
    def get_model_by_filename(self, filename: str) -> Dict[str, Any]:
        name = filename.strip()
        for model in KNOWN_MODELS:
            if model.get("filename") == name:
                return dict(model)
        return {}

    @service_endpoint(
        inputs={"path_or_name": "str"},
        outputs={"source_type": "str"},
        description="Classify source type by extension as code|prose|structured|skip|unknown.",
        tags=["config", "pipeline", "typing"],
    )
    def source_type_for_path(self, path_or_name: str) -> str:
        ext = Path(path_or_name).suffix.lower()
        if ext in SKIP_EXTENSIONS:
            return "skip"
        if ext in CODE_EXTENSIONS:
            return "code"
        if ext in PROSE_EXTENSIONS:
            return "prose"
        if ext in STRUCTURED_EXTENSIONS:
            return "structured"
        return "unknown"

    @service_endpoint(
        inputs={"path": "str"},
        outputs={"skip": "bool"},
        description="Return True when a path should be skipped by ingest walkers.",
        tags=["config", "pipeline", "filters"],
    )
    def should_skip_path(self, path: str) -> bool:
        p = Path(path)
        ext = p.suffix.lower()
        if ext in SKIP_EXTENSIONS:
            return True

        parts = {part.lower() for part in p.parts}
        for directory in SKIP_DIRS:
            d = directory.lower()
            if d == "*.egg-info":
                if any(part.endswith(".egg-info") for part in parts):
                    return True
            elif d in parts:
                return True
        return False

    @service_endpoint(
        inputs={},
        outputs={"constants": "dict"},
        description="Return core pipeline tuning constants and edge types.",
        tags=["config", "pipeline", "constants"],
    )
    def get_pipeline_constants(self) -> Dict[str, Any]:
        return {
            "max_chunk_tokens": MAX_CHUNK_TOKENS,
            "overlap_lines": OVERLAP_LINES,
            "summary_chunk_tokens": SUMMARY_CHUNK_TOKENS,
            "embedding_dims": EMBEDDING_DIMS,
            "embedding_batch": EMBEDDING_BATCH,
            "pipeline_version": PIPELINE_VERSION,
            "edge_types": list(EDGE_TYPES),
        }

    @service_endpoint(
        inputs={"chunk_text": "str"},
        outputs={"prompt": "str"},
        description="Render entity extraction prompt template for a specific chunk.",
        tags=["config", "prompt"],
    )
    def format_entity_prompt(self, chunk_text: str) -> str:
        return ENTITY_EXTRACTION_PROMPT.format(chunk_text=chunk_text)

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float"},
        description="Standardized health check for service status.",
        tags=["diagnostic", "health"],
    )
    def get_health(self):
        return {"status": "online", "uptime": time.time() - self.start_time}
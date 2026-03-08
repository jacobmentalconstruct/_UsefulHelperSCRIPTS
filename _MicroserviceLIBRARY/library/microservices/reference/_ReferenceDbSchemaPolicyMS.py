import time
from datetime import datetime, timezone
from typing import Any, Dict, List

from microservice_std_lib import service_endpoint, service_metadata


EMBED_STATUS_ENUM = {
    "pending": 0,
    "done": 1,
    "stale": 2,
    "error": 3,
}

GRAPH_STATUS_ENUM = {
    "pending": 0,
    "structural": 1,
    "done": 2,
    "error": 3,
}

INGEST_STATUS_ENUM = {
    "running": 0,
    "success": 1,
    "failed": 2,
    "partial": 3,
}

DEPLOYMENT_RULES = {
    "embeddings_required": True,
    "graph_required": "structural",
    "all_tables_required": [
        "source_files",
        "tree_nodes",
        "chunk_manifest",
        "embeddings",
        "graph_nodes",
        "graph_edges",
        "cartridge_manifest",
        "ingest_runs",
    ],
    "last_run_status_required": "success",
}


def _reverse_map(mapping: Dict[str, int]) -> Dict[int, str]:
    return {v: k for k, v in mapping.items()}


def _graph_meets_required(graph_state: str, required: str) -> bool:
    order = {"pending": 0, "structural": 1, "done": 2, "error": -1}
    state = graph_state.strip().lower()
    req = required.strip().lower()
    return order.get(state, -1) >= order.get(req, 0)


@service_metadata(
    name="ReferenceDbSchemaPolicyMS",
    version="1.0.0",
    description="Pilfered from db/schema.py policy layer. Provides schema enums, deployment rules, and deployability checks.",
    tags=["db", "schema", "policy", "deploy"],
    capabilities=["compute"],
    side_effects=[],
    internal_dependencies=["microservice_std_lib"],
    external_dependencies=[],
)
class ReferenceDbSchemaPolicyMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(
        inputs={},
        outputs={"enums": "dict"},
        description="Return manifest status enum registries from schema policy.",
        tags=["db", "schema", "enums"],
    )
    def get_status_enums(self) -> Dict[str, Dict[str, int]]:
        return {
            "embed_status": dict(EMBED_STATUS_ENUM),
            "graph_status": dict(GRAPH_STATUS_ENUM),
            "ingest_status": dict(INGEST_STATUS_ENUM),
        }

    @service_endpoint(
        inputs={},
        outputs={"rules": "dict"},
        description="Return deployment readiness rules used by orchestrators/airlock checks.",
        tags=["db", "schema", "rules"],
    )
    def get_deployment_rules(self) -> Dict[str, Any]:
        return {
            "embeddings_required": DEPLOYMENT_RULES["embeddings_required"],
            "graph_required": DEPLOYMENT_RULES["graph_required"],
            "all_tables_required": list(DEPLOYMENT_RULES["all_tables_required"]),
            "last_run_status_required": DEPLOYMENT_RULES["last_run_status_required"],
        }

    @service_endpoint(
        inputs={"kind": "str", "value": "str|int"},
        outputs={"normalized": "str"},
        description="Normalize ingest/embed/graph status from int or string into canonical label.",
        tags=["db", "schema", "normalize"],
    )
    def normalize_status(self, kind: str, value: Any) -> str:
        kind_norm = kind.strip().lower()
        if kind_norm == "embed":
            mapping = EMBED_STATUS_ENUM
        elif kind_norm == "graph":
            mapping = GRAPH_STATUS_ENUM
        elif kind_norm == "ingest":
            mapping = INGEST_STATUS_ENUM
        else:
            return "unknown"

        if isinstance(value, str):
            val = value.strip().lower()
            return val if val in mapping else "unknown"

        try:
            return _reverse_map(mapping).get(int(value), "unknown")
        except Exception:
            return "unknown"

    @service_endpoint(
        inputs={
            "existing_tables": "list[str]",
            "last_run_status": "str",
            "pending_embeddings": "int",
            "graph_state": "str",
        },
        outputs={"result": "dict"},
        description="Evaluate cartridge deployability using required table list, run status, embedding completeness, and graph state.",
        tags=["db", "schema", "deploy"],
    )
    def evaluate_deployability(
        self,
        existing_tables: List[str],
        last_run_status: str,
        pending_embeddings: int = 0,
        graph_state: str = "pending",
    ) -> Dict[str, Any]:
        table_set = {str(t).strip() for t in existing_tables}
        required_tables = list(DEPLOYMENT_RULES["all_tables_required"])
        missing_tables = [t for t in required_tables if t not in table_set]

        embeddings_required = bool(DEPLOYMENT_RULES["embeddings_required"])
        embeddings_ok = (not embeddings_required) or int(pending_embeddings) <= 0

        graph_required = str(DEPLOYMENT_RULES["graph_required"])
        graph_ok = _graph_meets_required(graph_state, graph_required)

        run_required = str(DEPLOYMENT_RULES["last_run_status_required"])
        run_ok = last_run_status.strip().lower() == run_required

        notes: List[str] = []
        if missing_tables:
            notes.append(f"Missing required tables: {', '.join(missing_tables)}")
        if not embeddings_ok:
            notes.append(f"Pending embeddings must be 0 (current={int(pending_embeddings)})")
        if not graph_ok:
            notes.append(f"Graph state '{graph_state}' does not meet required '{graph_required}'")
        if not run_ok:
            notes.append(f"Last ingest status must be '{run_required}' (current='{last_run_status}')")

        return {
            "is_deployable": not notes,
            "missing_tables": missing_tables,
            "embeddings_ok": embeddings_ok,
            "graph_ok": graph_ok,
            "run_ok": run_ok,
            "notes": notes,
        }

    @service_endpoint(
        inputs={
            "source_root": "str",
            "pipeline_ver": "str",
            "embed_model": "str",
            "embed_dims": "int",
            "title": "str",
            "description": "str",
        },
        outputs={"manifest_seed": "dict"},
        description="Build a default cartridge manifest seed payload for initialization workflows.",
        tags=["db", "schema", "manifest"],
    )
    def build_manifest_seed(
        self,
        source_root: str,
        pipeline_ver: str,
        embed_model: str,
        embed_dims: int,
        title: str = "",
        description: str = "",
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        return {
            "created_at": now,
            "updated_at": now,
            "title": title,
            "description": description,
            "schema_ver": 1,
            "pipeline_ver": pipeline_ver,
            "source_root": source_root,
            "embed_model": embed_model,
            "embed_dims": int(embed_dims),
            "structural_complete": False,
            "semantic_complete": False,
            "graph_complete": False,
            "search_index_complete": False,
            "is_deployable": False,
        }

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float"},
        description="Standardized health check for service status.",
        tags=["diagnostic", "health"],
    )
    def get_health(self):
        return {"status": "online", "uptime": time.time() - self.start_time}
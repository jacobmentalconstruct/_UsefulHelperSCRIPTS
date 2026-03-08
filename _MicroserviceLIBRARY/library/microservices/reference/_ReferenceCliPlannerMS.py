import time
from pathlib import Path
from typing import Any, Dict, Optional

from microservice_std_lib import service_endpoint, service_metadata


DB_INFO_QUERIES = {
    "source_files": "SELECT COUNT(*) FROM source_files",
    "verbatim_lines": "SELECT COUNT(*) FROM verbatim_lines",
    "tree_nodes": "SELECT COUNT(*) FROM tree_nodes",
    "chunks_total": "SELECT COUNT(*) FROM chunk_manifest",
    "embedded": "SELECT COUNT(*) FROM chunk_manifest WHERE embed_status='done'",
    "pending_embed": "SELECT COUNT(*) FROM chunk_manifest WHERE embed_status='pending'",
    "graph_nodes": "SELECT COUNT(*) FROM graph_nodes",
    "graph_edges": "SELECT COUNT(*) FROM graph_edges",
    "ingest_runs": "SELECT COUNT(*) FROM ingest_runs",
}


@service_metadata(
    name="ReferenceCliPlannerMS",
    version="1.0.0",
    description="Pilfered from cli.py. Provides deterministic CLI planning, output-path resolution, and DB info query specs.",
    tags=["cli", "pipeline", "planning"],
    capabilities=["filesystem:path", "compute"],
    side_effects=[],
    internal_dependencies=["microservice_std_lib"],
    external_dependencies=[],
)
class ReferenceCliPlannerMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(
        inputs={"source_path": "str", "output_override": "str|None"},
        outputs={"output_path": "str"},
        description="Resolve output .db path exactly like CLI default behavior.",
        tags=["cli", "paths"],
    )
    def resolve_output_path(self, source_path: str, output_override: Optional[str] = None) -> str:
        if output_override:
            return str(Path(output_override))
        source = Path(source_path)
        stem = source.stem if source.is_file() else source.name
        return str(source.parent / f"{stem}.tripartite.db")

    @service_endpoint(
        inputs={"source_path": "str|None", "info": "bool"},
        outputs={"plan": "dict"},
        description="Plan CLI mode and validate minimal source requirements for info or ingest execution.",
        tags=["cli", "validation"],
    )
    def plan_mode(self, source_path: Optional[str], info: bool = False) -> Dict[str, Any]:
        if info:
            if not source_path:
                return {"ok": False, "error": "info_requires_source", "mode": "info"}
            return {"ok": True, "mode": "info", "source": source_path}

        if not source_path:
            return {"ok": False, "error": "source_required", "mode": "help"}

        source = Path(source_path)
        if not source.exists():
            return {"ok": False, "error": "source_not_found", "mode": "ingest", "source": str(source)}

        return {
            "ok": True,
            "mode": "ingest",
            "source": str(source),
            "source_is_dir": source.is_dir(),
            "source_is_file": source.is_file(),
        }

    @service_endpoint(
        inputs={"source_path": "str", "output_override": "str|None", "lazy": "bool", "quiet": "bool", "info": "bool"},
        outputs={"plan": "dict"},
        description="Build a full normalized execution plan for CLI orchestration layers.",
        tags=["cli", "planning"],
    )
    def build_execution_plan(
        self,
        source_path: str,
        output_override: Optional[str] = None,
        lazy: bool = False,
        quiet: bool = False,
        info: bool = False,
    ) -> Dict[str, Any]:
        mode_plan = self.plan_mode(source_path, info=info)
        if not mode_plan.get("ok"):
            return mode_plan

        if mode_plan.get("mode") == "info":
            return {
                "ok": True,
                "mode": "info",
                "db_path": str(Path(source_path)),
                "queries": dict(DB_INFO_QUERIES),
            }

        output_path = self.resolve_output_path(source_path, output_override=output_override)
        return {
            "ok": True,
            "mode": "ingest",
            "source": source_path,
            "db_path": output_path,
            "lazy": bool(lazy),
            "verbose": not bool(quiet),
        }

    @service_endpoint(
        inputs={},
        outputs={"queries": "dict"},
        description="Return reusable SQL query map for --info style database summaries.",
        tags=["cli", "db", "queries"],
    )
    def get_db_info_queries(self) -> Dict[str, str]:
        return dict(DB_INFO_QUERIES)

    @service_endpoint(
        inputs={"errors_count": "int"},
        outputs={"exit_code": "int"},
        description="Compute CLI process exit code: 0 for success, 1 when errors exist.",
        tags=["cli", "status"],
    )
    def compute_exit_code(self, errors_count: int) -> int:
        return 0 if int(errors_count) <= 0 else 1

    @service_endpoint(
        inputs={"stats": "dict"},
        outputs={"summary": "str"},
        description="Format compact human-readable DB summary lines from stats payload.",
        tags=["cli", "format"],
    )
    def format_db_summary(self, stats: Dict[str, Any]) -> str:
        ordered = [
            ("source_files", "Source files"),
            ("verbatim_lines", "Verbatim lines"),
            ("tree_nodes", "Tree nodes"),
            ("chunks_total", "Chunks total"),
            ("embedded", "Embedded"),
            ("pending_embed", "Pending embed"),
            ("graph_nodes", "Graph nodes"),
            ("graph_edges", "Graph edges"),
            ("ingest_runs", "Ingest runs"),
        ]
        lines = ["Tripartite DB Summary"]
        for key, label in ordered:
            lines.append(f"- {label}: {stats.get(key, 0)}")
        return "\n".join(lines)

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float"},
        description="Standardized health check for service status.",
        tags=["diagnostic", "health"],
    )
    def get_health(self):
        return {"status": "online", "uptime": time.time() - self.start_time}
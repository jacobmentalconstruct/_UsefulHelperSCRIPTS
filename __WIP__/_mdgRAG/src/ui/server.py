"""
Graph Manifold — Web UI Server

FastAPI application serving the web interface and REST API.

Ownership: src/ui/server.py
    Provides REST endpoints for query, ingest, and manifold inspection.
    All pipeline execution is delegated to RuntimeController.run().
    Graph serialization produces Cytoscape.js-compatible JSON.

Endpoints:
    GET  /                  — Serve the single-page HTML UI
    GET  /api/health        — Health check
    POST /api/query         — Run pipeline query, return full results
    POST /api/ingest        — Ingest files into a manifold DB
    GET  /api/manifold      — Get manifold metadata and stats
    GET  /api/manifold/graph — Get full graph data for visualization

Dependencies: fastapi, uvicorn (lazy-imported by src/app.py cmd_serve).
"""

from __future__ import annotations

import json
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.core.runtime.runtime_controller import (
    RuntimeController,
    PipelineConfig,
    PipelineResult,
    PipelineError,
)
from src.core.factory.manifold_factory import ManifoldFactory
from src.core.store.manifold_store import ManifoldStore
from src.core.model_bridge.model_bridge import (
    ModelBridge,
    ModelBridgeConfig,
    ModelConnectionError,
    ModelResponseError,
)
from src.core.contracts.model_bridge_contract import EmbedRequest
from src.core.ingestion import (
    IngestionConfig,
    IngestionResult,
    ingest_file,
    ingest_directory,
)
from src.core.debug.inspection import (
    inspect_pipeline_result,
    dump_evidence_bag,
    dump_fusion_result,
    dump_hydrated_bundle,
)
from src.core.types.enums import ManifoldRole
from src.core.types.ids import ManifoldId, NodeId
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)

# Lazy imports — these are checked by _check_ui_deps() before server starts
try:
    from fastapi import FastAPI, Request
    from fastapi.responses import FileResponse, JSONResponse
except ImportError:
    FastAPI = None  # type: ignore[assignment,misc]

_STATIC_DIR = Path(__file__).parent / "static"


# ---------------------------------------------------------------------------
# Graph serialization (Cytoscape.js format)
# ---------------------------------------------------------------------------

def serialize_graph(
    manifold: Any,
    gravity_scores: Optional[Dict[NodeId, float]] = None,
    structural_scores: Optional[Dict[NodeId, float]] = None,
    semantic_scores: Optional[Dict[NodeId, float]] = None,
    store: Optional[ManifoldStore] = None,
) -> Dict[str, Any]:
    """Convert a manifold's nodes and edges to Cytoscape.js-compatible JSON.

    For RAM manifolds (VirtualManifold), uses get_nodes()/get_edges().
    For disk manifolds, uses ManifoldStore if provided (since in-memory
    collections may be empty for reopened disk manifolds).

    Args:
        manifold: Any manifold (Identity, External, or Virtual).
        gravity_scores: Optional gravity scores keyed by NodeId.
        structural_scores: Optional structural scores keyed by NodeId.
        semantic_scores: Optional semantic scores keyed by NodeId.
        store: Optional ManifoldStore for reading from disk manifolds.

    Returns:
        Dict with 'nodes' and 'edges' lists in Cytoscape.js element format.
    """
    gravity = gravity_scores or {}
    structural = structural_scores or {}
    semantic = semantic_scores or {}

    # For disk manifolds, use store if available and in-memory is empty
    raw_nodes = manifold.get_nodes()
    raw_edges = manifold.get_edges()

    if not raw_nodes and store and manifold.connection:
        conn = manifold.connection
        mid = manifold.get_metadata().manifold_id
        node_list = store.list_nodes(conn, mid)
        edge_list = store.list_edges(conn, mid)
        raw_nodes = {n.node_id: n for n in node_list}
        raw_edges = {e.edge_id: e for e in edge_list}

    nodes = []
    for nid, node in raw_nodes.items():
        nid_str = str(nid)
        nodes.append({
            "data": {
                "id": nid_str,
                "label": node.label,
                "type": node.node_type.name if hasattr(node.node_type, "name") else str(node.node_type),
                "gravity": round(gravity.get(nid, 0.0), 6),
                "structural": round(structural.get(nid, 0.0), 6),
                "semantic": round(semantic.get(nid, 0.0), 6),
                "canonical_key": node.canonical_key or "",
            }
        })

    edges = []
    for eid, edge in raw_edges.items():
        edges.append({
            "data": {
                "id": str(eid),
                "source": str(edge.from_node_id),
                "target": str(edge.to_node_id),
                "type": edge.edge_type.name if hasattr(edge.edge_type, "name") else str(edge.edge_type),
                "weight": round(edge.weight, 4),
            }
        })

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Helpers (reuse patterns from app.py)
# ---------------------------------------------------------------------------

def _load_all_node_ids(manifold: Any, store: ManifoldStore) -> List[NodeId]:
    """Read all node IDs from a manifold for projection."""
    conn = manifold.connection
    mid = manifold.get_metadata().manifold_id
    nodes = store.list_nodes(conn, mid)
    return [n.node_id for n in nodes]


def _sanitize_manifold_id(source_path: Path) -> str:
    """Derive a manifold ID from a source path."""
    name = source_path.stem if source_path.is_file() else source_path.name
    sanitized = "".join(c if c.isalnum() else "-" for c in name.lower())
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    return sanitized.strip("-") or "manifold"


def _build_embed_fn(bridge: ModelBridge) -> Callable[[str], Sequence[float]]:
    """Build an embed_fn callback from a ModelBridge instance."""
    def embed_fn(text: str) -> Sequence[float]:
        response = bridge.embed(EmbedRequest(texts=[text]))
        if response.vectors:
            return response.vectors[0]
        return []
    return embed_fn


# ---------------------------------------------------------------------------
# FastAPI application factory
# ---------------------------------------------------------------------------

def create_app(default_db: Optional[str] = None) -> Any:
    """Create and configure the FastAPI application.

    Args:
        default_db: Optional path to a default manifold DB.

    Returns:
        Configured FastAPI application instance.
    """
    if FastAPI is None:
        raise ImportError(
            "FastAPI is not installed. Run: pip install fastapi uvicorn"
        )

    app = FastAPI(
        title="Graph Manifold",
        description="Graph-native RAG system — Web UI",
        version="0.1.0",
    )

    # Store default_db in app state
    app.state.default_db = default_db

    # ------------------------------------------------------------------
    # Exception handlers
    # ------------------------------------------------------------------

    @app.exception_handler(PipelineError)
    async def pipeline_error_handler(request: Request, exc: PipelineError) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": f"Pipeline error at [{exc.stage}]: {exc}",
                "stage": exc.stage,
            },
        )

    @app.exception_handler(FileNotFoundError)
    async def fnf_error_handler(request: Request, exc: FileNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": f"File not found: {exc}"},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": str(exc)},
        )

    # ------------------------------------------------------------------
    # Static file serving
    # ------------------------------------------------------------------

    @app.get("/")
    async def serve_index() -> FileResponse:
        """Serve the single-page HTML UI."""
        return FileResponse(
            _STATIC_DIR / "index.html",
            media_type="text/html",
        )

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    @app.get("/api/health")
    async def health() -> Dict[str, str]:
        """Health check endpoint."""
        return {"status": "ok"}

    # ------------------------------------------------------------------
    # Query endpoint
    # ------------------------------------------------------------------

    @app.post("/api/query")
    async def query_endpoint(request: Request) -> JSONResponse:
        """Run the pipeline and return full results as JSON."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid JSON body"},
            )

        query_text = body.get("query", "").strip()
        if not query_text:
            return JSONResponse(
                status_code=400,
                content={"error": "Query text is required"},
            )

        db_path_str = body.get("db_path", app.state.default_db or "")
        if not db_path_str:
            return JSONResponse(
                status_code=400,
                content={"error": "db_path is required"},
            )

        db_path = Path(db_path_str).resolve()
        if not db_path.exists():
            return JSONResponse(
                status_code=404,
                content={"error": f"Database not found: {db_path}"},
            )

        alpha = float(body.get("alpha", 0.6))
        beta = float(body.get("beta", 0.4))
        skip_synthesis = body.get("skip_synthesis", True)
        synthesis_model = body.get("synthesis_model", "")
        if synthesis_model:
            skip_synthesis = False

        # Open manifold and load nodes
        factory = ManifoldFactory()
        store = ManifoldStore()
        manifold = factory.open_manifold(str(db_path))
        try:
            node_ids = _load_all_node_ids(manifold, store)

            if not node_ids:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Manifold has no nodes. Ingest data first."},
                )

            # Build config
            bridge_config = ModelBridgeConfig(
                embed_backend=body.get("embed_backend", "deterministic"),
            )
            if synthesis_model:
                bridge_config.synthesis_model = synthesis_model

            pipeline_config = PipelineConfig(
                alpha=alpha,
                beta=beta,
                skip_synthesis=skip_synthesis,
                model_bridge_config=bridge_config,
                synthesis_model=synthesis_model,
            )

            # Run pipeline
            controller = RuntimeController()
            controller.bootstrap()
            t0 = time.perf_counter()
            result = controller.run(
                query=query_text,
                external_manifold=manifold,
                external_node_ids=node_ids,
                config=pipeline_config,
            )
            total_time = time.perf_counter() - t0

            # Build response
            response_data = _build_query_response(result, total_time)
            return JSONResponse(status_code=200, content=response_data)
        finally:
            manifold.close()

    # ------------------------------------------------------------------
    # Ingest endpoint
    # ------------------------------------------------------------------

    @app.post("/api/ingest")
    async def ingest_endpoint(request: Request) -> JSONResponse:
        """Ingest files into a manifold database."""
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"error": "Invalid JSON body"},
            )

        source_str = body.get("source", "").strip()
        if not source_str:
            return JSONResponse(
                status_code=400,
                content={"error": "source path is required"},
            )

        db_path_str = body.get("db_path", "").strip()
        if not db_path_str:
            return JSONResponse(
                status_code=400,
                content={"error": "db_path is required"},
            )

        source = Path(source_str).resolve()
        if not source.exists():
            return JSONResponse(
                status_code=404,
                content={"error": f"Source not found: {source}"},
            )

        db_path = Path(db_path_str).resolve()
        skip_embeddings = body.get("skip_embeddings", True)

        factory = ManifoldFactory()
        store = ManifoldStore()
        manifold_id_str = _sanitize_manifold_id(source)
        mid = ManifoldId(manifold_id_str)

        # If user selected a folder, append a default DB filename
        if db_path.is_dir():
            db_path = db_path / f"{manifold_id_str}.db"

        # Create or open manifold
        if db_path.is_file():
            manifold = factory.open_manifold(str(db_path))
        else:
            db_path.parent.mkdir(parents=True, exist_ok=True)
            manifold = factory.create_disk_manifold(
                mid, ManifoldRole.EXTERNAL, str(db_path),
                description=f"Ingested from {source.name}",
            )

        try:
            # Build embed_fn
            embed_fn = None
            if not skip_embeddings:
                try:
                    bridge = ModelBridge(ModelBridgeConfig(
                        embed_backend=body.get("embed_backend", "deterministic"),
                    ))
                    embed_fn = _build_embed_fn(bridge)
                except Exception:
                    pass  # Continue without embeddings

            # Build config
            ing_config = IngestionConfig(
                max_chunk_tokens=body.get("max_chunk_tokens", 512),
                enable_embeddings=not skip_embeddings,
            )

            # Ingest
            t0 = time.perf_counter()
            if source.is_file():
                result = ingest_file(source, manifold, store, config=ing_config, embed_fn=embed_fn)
            else:
                result = ingest_directory(source, manifold, store, config=ing_config, embed_fn=embed_fn)
            elapsed = time.perf_counter() - t0

            return JSONResponse(
                status_code=200,
                content={
                    "status": "ok",
                    "source": str(source),
                    "db_path": str(db_path),
                    "files_processed": result.files_processed,
                    "files_skipped": result.files_skipped,
                    "chunks_created": result.chunks_created,
                    "nodes_created": result.nodes_created,
                    "edges_created": result.edges_created,
                    "embeddings_created": result.embeddings_created,
                    "warnings": result.warnings[:10],
                    "elapsed_seconds": round(elapsed, 3),
                },
            )
        finally:
            manifold.close()

    # ------------------------------------------------------------------
    # Manifold info endpoint
    # ------------------------------------------------------------------

    @app.get("/api/manifold")
    async def manifold_info(db_path: str = "") -> JSONResponse:
        """Get manifold metadata and statistics."""
        path = db_path or app.state.default_db or ""
        if not path:
            return JSONResponse(
                status_code=400,
                content={"error": "db_path query parameter is required"},
            )

        db = Path(path).resolve()
        if not db.exists():
            return JSONResponse(
                status_code=404,
                content={"error": f"Database not found: {db}"},
            )

        factory = ManifoldFactory()
        store = ManifoldStore()
        manifold = factory.open_manifold(str(db))
        try:
            meta = manifold.get_metadata()
            conn = manifold.connection

            nodes = store.list_nodes(conn, meta.manifold_id)
            edges = store.list_edges(conn, meta.manifold_id)

            return JSONResponse(
                status_code=200,
                content={
                    "manifold_id": str(meta.manifold_id),
                    "role": meta.role.name if hasattr(meta.role, "name") else str(meta.role),
                    "db_path": str(db),
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                },
            )
        finally:
            manifold.close()

    # ------------------------------------------------------------------
    # Graph data endpoint
    # ------------------------------------------------------------------

    @app.get("/api/manifold/graph")
    async def manifold_graph(db_path: str = "") -> JSONResponse:
        """Get full graph data in Cytoscape.js format."""
        path = db_path or app.state.default_db or ""
        if not path:
            return JSONResponse(
                status_code=400,
                content={"error": "db_path query parameter is required"},
            )

        db = Path(path).resolve()
        if not db.exists():
            return JSONResponse(
                status_code=404,
                content={"error": f"Database not found: {db}"},
            )

        factory = ManifoldFactory()
        store = ManifoldStore()
        manifold = factory.open_manifold(str(db))
        try:
            graph_data = serialize_graph(manifold, store=store)
            return JSONResponse(status_code=200, content=graph_data)
        finally:
            manifold.close()

    # ------------------------------------------------------------------
    # File browser endpoint
    # ------------------------------------------------------------------

    @app.get("/api/browse")
    async def browse_filesystem(path: str = "", show_files: bool = True) -> JSONResponse:
        """Browse the local filesystem for the file picker UI.

        Args:
            path: Directory to list. Defaults to cwd.
            show_files: Whether to include files (True) or just directories (False).

        Returns:
            JSON with current path, parent path, and list of entries.
        """
        target = Path(path).resolve() if path else Path.cwd()
        if not target.exists():
            return JSONResponse(
                status_code=404,
                content={"error": f"Path not found: {target}"},
            )
        if not target.is_dir():
            target = target.parent

        entries = []
        try:
            for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                # Skip hidden files/dirs and __pycache__
                if item.name.startswith(".") or item.name == "__pycache__":
                    continue
                if item.is_dir():
                    entries.append({
                        "name": item.name,
                        "path": str(item),
                        "is_dir": True,
                    })
                elif show_files:
                    entries.append({
                        "name": item.name,
                        "path": str(item),
                        "is_dir": False,
                        "size": item.stat().st_size,
                    })
        except PermissionError:
            return JSONResponse(
                status_code=403,
                content={"error": f"Permission denied: {target}"},
            )

        parent = str(target.parent) if target.parent != target else None

        return JSONResponse(
            status_code=200,
            content={
                "current": str(target),
                "parent": parent,
                "entries": entries,
            },
        )

    return app


# ---------------------------------------------------------------------------
# Response builders
# ---------------------------------------------------------------------------

def _build_query_response(result: PipelineResult, total_time: float) -> Dict[str, Any]:
    """Build a JSON-serializable response from a PipelineResult.

    Combines inspection helpers with graph serialization and scoring data.
    """
    response: Dict[str, Any] = {
        "answer_text": result.answer_text,
        "overview": inspect_pipeline_result(result),
        "timing": {k: round(v, 4) for k, v in result.timing.items()},
        "total_time": round(total_time, 4),
    }

    # Evidence bag
    if result.evidence_bag:
        response["evidence"] = dump_evidence_bag(result.evidence_bag)
    else:
        response["evidence"] = None

    # Graph data from virtual manifold
    if result.fusion_result and result.fusion_result.virtual_manifold:
        response["graph"] = serialize_graph(
            result.fusion_result.virtual_manifold,
            gravity_scores=result.gravity_scores,
            structural_scores=result.structural_scores,
            semantic_scores=result.semantic_scores,
        )
    else:
        response["graph"] = {"nodes": [], "edges": []}

    # Scores as a sorted list (top gravity first)
    scores_list = []
    for nid, g_score in sorted(
        result.gravity_scores.items(),
        key=lambda kv: kv[1],
        reverse=True,
    ):
        scores_list.append({
            "node_id": str(nid),
            "gravity": round(g_score, 6),
            "structural": round(result.structural_scores.get(nid, 0.0), 6),
            "semantic": round(result.semantic_scores.get(nid, 0.0), 6),
        })
    response["scores"] = scores_list

    # Hydrated bundle summary
    if result.hydrated_bundle:
        response["hydrated"] = dump_hydrated_bundle(result.hydrated_bundle)
    else:
        response["hydrated"] = None

    # Degradation info
    response["degraded"] = result.degraded
    response["skipped_stages"] = list(result.skipped_stages)

    return response


# ---------------------------------------------------------------------------
# Server start
# ---------------------------------------------------------------------------

def start(host: str = "localhost", port: int = 8080, default_db: Optional[str] = None) -> None:
    """Start the web UI server.

    Args:
        host: Bind host (default: localhost).
        port: Bind port (default: 8080).
        default_db: Optional path to pre-load manifold DB.
    """
    import uvicorn  # lazy import — checked by _check_ui_deps() in app.py

    app = create_app(default_db=default_db)
    print(f"Starting Graph Manifold UI at http://{host}:{port}", flush=True)
    if default_db:
        print(f"Default manifold: {default_db}", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="warning")

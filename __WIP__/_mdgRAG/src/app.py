"""
Graph Manifold -- CLI Entry Point

Three subcommands:
    ingest   Ingest files/directories into a manifold database.
    query    Run a query against an existing manifold.
    serve    Start the web UI server for interactive exploration.

Usage:
    python -m src.app ingest --source ./project --db ./manifold.db
    python -m src.app query  --db ./manifold.db --query "How does X work?"
    python -m src.app query  --db ./manifold.db --query "..." --json --verbose
    python -m src.app serve  --db ./manifold.db --port 8080

Rules:
    - No legacy path hacks or path surgery
    - Imports only new scaffold modules
    - argparse only (no external CLI deps)
    - stdout for results, stderr for logs/diagnostics
    - Web UI deps (fastapi, uvicorn) are lazy-imported by serve subcommand
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
import time
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
    ModelBridgeError,
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
from src.core.debug.inspection import inspect_pipeline_result, dump_evidence_bag
from src.core.types.enums import ManifoldRole
from src.core.types.ids import ManifoldId, NodeId
from src.utils.logging_utils import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Build the top-level argparse parser with ingest and query subcommands."""
    parser = argparse.ArgumentParser(
        prog="graph-manifold",
        description="Graph Manifold -- graph-native RAG system",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    _add_ingest_parser(subparsers)
    _add_query_parser(subparsers)
    _add_serve_parser(subparsers)

    return parser


def _add_ingest_parser(subparsers: Any) -> None:
    """Add the 'ingest' subcommand parser."""
    p = subparsers.add_parser(
        "ingest",
        help="Ingest files or directories into a manifold database",
    )
    p.set_defaults(func=cmd_ingest)

    # Required
    p.add_argument("--source", required=True, help="File or directory to ingest")
    p.add_argument("--db", required=True, help="Manifold database path (created if missing)")

    # Optional
    p.add_argument("--manifold-id", default=None, help="Override auto-derived manifold ID")
    p.add_argument(
        "--embed-backend", default="deterministic",
        choices=["deterministic", "ollama"],
        help="Embedding backend (default: deterministic)",
    )
    p.add_argument("--tokenizer-path", default="", help="Path to deterministic tokenizer artifact")
    p.add_argument("--embeddings-path", default="", help="Path to deterministic embeddings artifact")
    p.add_argument("--skip-embeddings", action="store_true", help="Skip embedding generation")
    p.add_argument("--max-chunk-tokens", type=int, default=512, help="Max tokens per chunk (default: 512)")
    p.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama base URL")


def _add_query_parser(subparsers: Any) -> None:
    """Add the 'query' subcommand parser."""
    p = subparsers.add_parser(
        "query",
        help="Run a query against an existing manifold",
    )
    p.set_defaults(func=cmd_query)

    # Required
    p.add_argument("--db", required=True, help="Manifold database path")
    p.add_argument("--query", required=True, help="Query text")

    # Scoring
    p.add_argument("--alpha", type=float, default=0.6, help="Structural scoring weight (default: 0.6)")
    p.add_argument("--beta", type=float, default=0.4, help="Semantic scoring weight (default: 0.4)")

    # Synthesis
    p.add_argument("--skip-synthesis", action="store_true", default=True,
                    help="Skip LLM synthesis (default: True)")
    p.add_argument("--synthesis-model", default="",
                    help="Ollama model for synthesis (enables synthesis)")
    p.add_argument("--ollama-url", default="http://localhost:11434", help="Ollama base URL")

    # Embedding
    p.add_argument(
        "--embed-backend", default="deterministic",
        choices=["deterministic", "ollama"],
        help="Embedding backend for query embedding (default: deterministic)",
    )
    p.add_argument("--tokenizer-path", default="", help="Path to deterministic tokenizer artifact")
    p.add_argument("--embeddings-path", default="", help="Path to deterministic embeddings artifact")

    # Output
    p.add_argument("--json", action="store_true", dest="json_output", help="Output full result as JSON")
    p.add_argument("--verbose", action="store_true", help="Print timing/scoring summary to stderr")


def _add_serve_parser(subparsers: Any) -> None:
    """Add the 'serve' subcommand parser."""
    p = subparsers.add_parser(
        "serve",
        help="Start the web UI server for interactive exploration",
    )
    p.set_defaults(func=cmd_serve)

    p.add_argument("--port", type=int, default=8080, help="Server port (default: 8080)")
    p.add_argument("--host", default="localhost", help="Bind host (default: localhost)")
    p.add_argument("--db", default="", help="Default manifold DB to pre-load (optional)")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_model_bridge_config(args: argparse.Namespace) -> ModelBridgeConfig:
    """Construct a ModelBridgeConfig from CLI arguments."""
    config = ModelBridgeConfig(
        embed_backend=getattr(args, "embed_backend", "deterministic"),
        deterministic_tokenizer_path=getattr(args, "tokenizer_path", ""),
        deterministic_embeddings_path=getattr(args, "embeddings_path", ""),
        base_url=getattr(args, "ollama_url", "http://localhost:11434"),
    )
    synthesis_model = getattr(args, "synthesis_model", "")
    if synthesis_model:
        config.synthesis_model = synthesis_model
    return config


def _build_embed_fn(bridge: ModelBridge) -> Callable[[str], Sequence[float]]:
    """Build an embed_fn callback from a ModelBridge instance."""
    def embed_fn(text: str) -> Sequence[float]:
        response = bridge.embed(EmbedRequest(texts=[text]))
        if response.vectors:
            return response.vectors[0]
        return []
    return embed_fn


def _load_all_node_ids(manifold: Any, store: ManifoldStore) -> List[NodeId]:
    """Read all node IDs from a manifold for projection."""
    conn = manifold.connection
    mid = manifold.get_metadata().manifold_id
    nodes = store.list_nodes(conn, mid)
    return [n.node_id for n in nodes]


def _sanitize_manifold_id(source_path: Path) -> str:
    """Derive a manifold ID from a source path."""
    name = source_path.stem if source_path.is_file() else source_path.name
    # Replace non-alphanumeric chars with hyphens, lowercase
    sanitized = "".join(c if c.isalnum() else "-" for c in name.lower())
    # Collapse multiple hyphens
    while "--" in sanitized:
        sanitized = sanitized.replace("--", "-")
    return sanitized.strip("-") or "manifold"


# ---------------------------------------------------------------------------
# Ingest command
# ---------------------------------------------------------------------------

def cmd_ingest(args: argparse.Namespace) -> int:
    """Execute the ingest subcommand.

    1. Resolve source path (must exist).
    2. Create or open the manifold DB.
    3. Build embed_fn from ModelBridge if embeddings enabled.
    4. Build IngestionConfig from args.
    5. Call ingest_file() or ingest_directory().
    6. Print summary to stderr.
    7. Return exit code 0 on success.
    """
    source = Path(args.source).resolve()
    if not source.exists():
        print(f"Error: Source path does not exist: {source}", file=sys.stderr)
        return 1

    db_path = Path(args.db).resolve()
    factory = ManifoldFactory()
    store = ManifoldStore()

    # Determine manifold ID
    manifold_id_str = args.manifold_id or _sanitize_manifold_id(source)
    mid = ManifoldId(manifold_id_str)

    # Create or open manifold
    if db_path.exists():
        manifold = factory.open_manifold(str(db_path))
        print(f"Opened existing manifold: {db_path}", file=sys.stderr)
    else:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        manifold = factory.create_disk_manifold(
            mid, ManifoldRole.EXTERNAL, str(db_path),
            description=f"Ingested from {source.name}",
        )
        print(f"Created new manifold: {db_path}", file=sys.stderr)

    # Build embed_fn
    embed_fn = None
    if not args.skip_embeddings:
        try:
            bridge_config = _build_model_bridge_config(args)
            bridge = ModelBridge(bridge_config)
            embed_fn = _build_embed_fn(bridge)
        except Exception as exc:
            print(f"Warning: Could not set up embeddings: {exc}", file=sys.stderr)
            print("Continuing without embeddings.", file=sys.stderr)

    # Build ingestion config
    ing_config = IngestionConfig(
        max_chunk_tokens=args.max_chunk_tokens,
        enable_embeddings=not args.skip_embeddings,
    )

    # Ingest
    t0 = time.perf_counter()
    if source.is_file():
        result = ingest_file(source, manifold, store, config=ing_config, embed_fn=embed_fn)
    else:
        result = ingest_directory(source, manifold, store, config=ing_config, embed_fn=embed_fn)
    elapsed = time.perf_counter() - t0

    # Print summary
    print(f"\n--- Ingestion Complete ---", file=sys.stderr)
    print(f"  Source:      {source}", file=sys.stderr)
    print(f"  Database:    {db_path}", file=sys.stderr)
    print(f"  Files:       {result.files_processed} processed, {result.files_skipped} skipped", file=sys.stderr)
    print(f"  Chunks:      {result.chunks_created}", file=sys.stderr)
    print(f"  Nodes:       {result.nodes_created}", file=sys.stderr)
    print(f"  Edges:       {result.edges_created}", file=sys.stderr)
    print(f"  Embeddings:  {result.embeddings_created}", file=sys.stderr)
    print(f"  Time:        {elapsed:.2f}s", file=sys.stderr)
    if result.warnings:
        print(f"  Warnings:    {len(result.warnings)}", file=sys.stderr)
        for w in result.warnings[:5]:
            print(f"    - {w}", file=sys.stderr)
        if len(result.warnings) > 5:
            print(f"    ... and {len(result.warnings) - 5} more", file=sys.stderr)

    return 0


# ---------------------------------------------------------------------------
# Query command
# ---------------------------------------------------------------------------

def cmd_query(args: argparse.Namespace) -> int:
    """Execute the query subcommand.

    1. Open the manifold DB.
    2. Load all node IDs for projection.
    3. Build PipelineConfig.
    4. Run the pipeline.
    5. Format and print output.
    6. Return exit code 0.
    """
    db_path = Path(args.db).resolve()
    if not db_path.exists():
        print(f"Error: Database does not exist: {db_path}", file=sys.stderr)
        return 1

    query_text = args.query
    if not query_text.strip():
        print("Error: Query text cannot be empty.", file=sys.stderr)
        return 1

    factory = ManifoldFactory()
    store = ManifoldStore()

    # Open manifold
    manifold = factory.open_manifold(str(db_path))

    # Load all node IDs
    node_ids = _load_all_node_ids(manifold, store)
    if not node_ids:
        print("Warning: Manifold has no nodes. Did you ingest data first?", file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Loaded {len(node_ids)} nodes from manifold.", file=sys.stderr)

    # Determine skip_synthesis
    skip_synthesis = True
    if args.synthesis_model:
        skip_synthesis = False

    # Build config
    bridge_config = _build_model_bridge_config(args)
    if args.synthesis_model:
        bridge_config.synthesis_model = args.synthesis_model

    pipeline_config = PipelineConfig(
        alpha=args.alpha,
        beta=args.beta,
        skip_synthesis=skip_synthesis,
        model_bridge_config=bridge_config,
        synthesis_model=args.synthesis_model,
    )

    # Run pipeline
    controller = RuntimeController()
    controller.bootstrap()
    result = controller.run(
        query=query_text,
        external_manifold=manifold,
        external_node_ids=node_ids,
        config=pipeline_config,
    )

    # Format output
    if args.verbose:
        verbose_text = format_verbose(result)
        print(verbose_text, file=sys.stderr)

    if args.json_output:
        json_text = format_result_json(result)
        print(json_text)
    else:
        plain_text = format_result_plain(result, skip_synthesis)
        print(plain_text)

    return 0


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def format_result_plain(result: PipelineResult, skip_synthesis: bool = False) -> str:
    """Format a PipelineResult for plain text output to stdout."""
    lines: List[str] = []

    if not skip_synthesis and result.answer_text:
        lines.append(result.answer_text)
    else:
        # Evidence summary when synthesis was skipped
        lines.append("--- Query Results (synthesis skipped) ---")
        lines.append("")

        if result.evidence_bag:
            bag = result.evidence_bag
            lines.append(f"Evidence bag: {len(bag.node_ids)} nodes, "
                         f"{len(bag.edge_ids)} edges")
            total_chunks = sum(len(refs) for refs in bag.chunk_refs.values())
            lines.append(f"Chunks referenced: {total_chunks}")
            lines.append(f"Token budget: {bag.token_budget.used_tokens}"
                         f" / {bag.token_budget.max_tokens} used")
            lines.append("")

        if result.gravity_scores:
            # Top gravity nodes
            sorted_gravity = sorted(
                result.gravity_scores.items(),
                key=lambda kv: kv[1],
                reverse=True,
            )[:10]
            lines.append("Top gravity scores:")
            for nid, score in sorted_gravity:
                lines.append(f"  {nid}: {score:.4f}")
            lines.append("")

        if result.degraded:
            lines.append("[degraded] Semantic scoring was unavailable.")
        if result.skipped_stages:
            lines.append(f"[skipped] Stages: {', '.join(result.skipped_stages)}")

        if result.evidence_context:
            lines.append("")
            lines.append("--- Evidence Context ---")
            # Truncate to first 2000 chars for readability
            ctx = result.evidence_context
            if len(ctx) > 2000:
                ctx = ctx[:2000] + "\n... (truncated)"
            lines.append(ctx)

    return "\n".join(lines)


def format_result_json(result: PipelineResult) -> str:
    """Format a PipelineResult as JSON using inspection helpers."""
    output: Dict[str, Any] = inspect_pipeline_result(result)

    if result.evidence_bag:
        output["evidence_bag"] = dump_evidence_bag(result.evidence_bag)

    # Add the answer text
    output["answer_text"] = result.answer_text

    # Add evidence context length
    output["evidence_context_length"] = len(result.evidence_context)

    return json.dumps(output, indent=2, default=str)


def format_verbose(result: PipelineResult) -> str:
    """Format verbose timing and scoring summary for stderr."""
    lines: List[str] = []
    lines.append("")
    lines.append("--- Pipeline Summary ---")
    lines.append(f"  Stages completed: {result.stage_count}")
    lines.append(f"  Degraded:         {result.degraded}")

    if result.skipped_stages:
        lines.append(f"  Skipped stages:   {', '.join(result.skipped_stages)}")

    # Timing breakdown
    if result.timing:
        lines.append("")
        lines.append("  Stage Timing:")
        for stage, elapsed in result.timing.items():
            lines.append(f"    {stage:20s} {elapsed:.4f}s")

    # Scoring summary
    lines.append("")
    lines.append("  Scoring Summary:")
    lines.append(f"    Structural nodes: {len(result.structural_scores)}")
    lines.append(f"    Semantic nodes:   {len(result.semantic_scores)}")
    lines.append(f"    Gravity nodes:    {len(result.gravity_scores)}")

    if result.gravity_scores:
        sorted_gravity = sorted(
            result.gravity_scores.items(),
            key=lambda kv: kv[1],
            reverse=True,
        )[:5]
        lines.append("")
        lines.append("  Top 5 Gravity:")
        for nid, score in sorted_gravity:
            s = result.structural_scores.get(nid, 0.0)
            t = result.semantic_scores.get(nid, 0.0)
            lines.append(f"    {str(nid):40s}  G={score:.4f}  S={s:.4f}  T={t:.4f}")

    # Evidence bag summary
    if result.evidence_bag:
        bag = result.evidence_bag
        total_chunks = sum(len(refs) for refs in bag.chunk_refs.values())
        utilization = bag.token_budget.used_tokens / max(bag.token_budget.max_tokens, 1)
        lines.append("")
        lines.append("  Evidence Bag:")
        lines.append(f"    Nodes:       {len(bag.node_ids)}")
        lines.append(f"    Edges:       {len(bag.edge_ids)}")
        lines.append(f"    Chunks:      {total_chunks}")
        lines.append(f"    Token util:  {utilization:.1%}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Serve command
# ---------------------------------------------------------------------------

def _check_ui_deps() -> bool:
    """Check that web UI dependencies (fastapi, uvicorn) are installed."""
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        return True
    except ImportError:
        return False


def cmd_serve(args: argparse.Namespace) -> int:
    """Start the web UI server for interactive pipeline exploration.

    1. Check that fastapi and uvicorn are installed.
    2. Lazy-import the server module.
    3. Start the server.
    """
    if not _check_ui_deps():
        print(
            "Web UI dependencies not installed.\n"
            "Run: pip install fastapi uvicorn\n",
            file=sys.stderr,
        )
        return 1

    from src.ui.server import start  # lazy import

    default_db = args.db if args.db else None
    if default_db:
        db_path = Path(default_db).resolve()
        if not db_path.exists():
            print(f"Error: Database does not exist: {db_path}", file=sys.stderr)
            return 1
        default_db = str(db_path)

    start(host=args.host, port=args.port, default_db=default_db)
    return 0


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def handle_error(exc: Exception, verbose: bool = False) -> int:
    """Format an error message and return exit code 1."""
    if isinstance(exc, PipelineError):
        print(f"Pipeline error at [{exc.stage}]: {exc}", file=sys.stderr)
    elif isinstance(exc, ModelConnectionError):
        print(f"Cannot reach model server: {exc}", file=sys.stderr)
    elif isinstance(exc, ModelResponseError):
        print(f"Model response error: {exc}", file=sys.stderr)
    elif isinstance(exc, FileNotFoundError):
        print(f"File not found: {exc}", file=sys.stderr)
    elif isinstance(exc, ValueError):
        print(f"Error: {exc}", file=sys.stderr)
    else:
        print(f"Error: {exc}", file=sys.stderr)

    if verbose:
        print("", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)

    return 1


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    """CLI entry point. Parses args and dispatches to subcommand."""
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    try:
        return args.func(args)
    except (PipelineError, ModelBridgeError, FileNotFoundError, ValueError) as exc:
        return handle_error(exc, getattr(args, "verbose", False))
    except Exception as exc:
        return handle_error(exc, getattr(args, "verbose", False))


if __name__ == "__main__":
    raise SystemExit(main())

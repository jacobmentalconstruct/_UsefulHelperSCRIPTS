"""
backend.py
----------
Backend orchestrator for UiMAPPER.

Design goals:
- No Tkinter code here.
- Orchestrator only: wires microservices, owns run lifecycle, cancellation, threading.
- Emits progress events through ProgressEventBusMS.
- Maintains a RunSessionState (via RunSessionStateMS).
- Produces UiMap + reports (md/json/jsonl).
- Optional inference step using Ollama (HITL decisions are returned, not UI-rendered).

Expected project layout (typical):
src/
  app.py              # dumb shell
  ui.py               # UI orchestrator
  backend.py          # THIS FILE
  microservices/
    ...               # microservices imported below

Notes:
- This module is intentionally self-contained + defensive.
- Where your existing microservice names/paths differ, adjust imports at the top.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict, is_dataclass
from pathlib import Path
from threading import Thread, Lock
from typing import Any, Callable, Dict, List, Optional, Tuple
import time
import uuid


# -------------------------
# Imports: Microservices
# -------------------------
# Adjust these import paths to match your stamped project structure.

# Core run infra
from .microservices.CancellationTokenMS import CancellationTokenMS
from .microservices.ProgressEventBusMS import ProgressEventBusMS
from .microservices.RunSessionStateMS import RunSessionStateMS, RunSessionState
from .microservices.ErrorNormalizerMS import ErrorNormalizerMS

# Discovery
from .microservices.GitignoreFilterMS import GitignoreFilterMS
from .microservices.PythonFileEnumeratorMS import PythonFileEnumeratorMS, PythonEnumConfig
from .microservices.EntrypointFinderMS import EntrypointFinderMS

# AST + mapping
from .microservices.AstParseCacheMS import AstParseCacheMS
from .microservices.AstUiMapMS import AstUiMapMS
from .microservices.UnknownCaseCollectorMS import UnknownCaseCollectorMS

# Callback graph
from .microservices.CallbackGraphBuilderMS import CallbackGraphBuilderMS

# Canonical model + reports
from .microservices.UiMapModelMS import UiMapModelMS
from .microservices.ReportWriterMS import ReportWriterMS
from .microservices.ReportSerializerMS import ReportSerializerMS

# Optional inference/HITL
from .microservices.InferencePromptBuilderMS import InferencePromptBuilderMS
from .microservices.OllamaClientMS import OllamaClientMS, OllamaClientConfig
from .microservices.InferenceResultValidatorMS import InferenceResultValidatorMS
from .microservices.HitlDecisionRouterMS import HitlDecisionRouterMS, HitlPolicy


# -------------------------
# External dependency microservice (expected)
# -------------------------
# If you already stamped ProjectCrawlMS, import it here.
# Otherwise, implement/adjust to your crawl service interface:
#   crawl(project_root: Path, path_filter: Optional[Callable[[Path], bool]]) -> Iterable[CrawlEntry]
# where CrawlEntry has: abs_path: Path, rel_path: Path, is_dir: bool
try:
    from .microservices.ProjectCrawlMS import ProjectCrawlMS, CrawlConfig
except Exception:  # pragma: no cover
    ProjectCrawlMS = None  # type: ignore
    CrawlConfig = None  # type: ignore


# -------------------------
# Backend Settings
# -------------------------

@dataclass
class BackendSettings:
    # Output folder for reports; defaults to <project_root>/_uimapper_reports
    report_out_dir: Optional[Path] = None

    # Include .pyw in enumeration
    include_pyw: bool = True

    # Inference toggles
    enable_inference: bool = False
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = ""  # e.g. "qwen2.5-coder:7b-instruct"
    ollama_timeout_sec: float = 30.0
    inference_max_cases: int = 10

    # HITL policy thresholds
    hitl_policy: HitlPolicy = field(default_factory=HitlPolicy)

    # Report formats
    write_md: bool = True
    write_json: bool = True
    write_jsonl: bool = True


# -------------------------
# Backend Orchestrator
# -------------------------

class BackendOrchestrator:
    """
    Threaded backend pipeline runner.

    Public surface:
    - start_run(project_root, settings) -> session_id
    - cancel_run(reason="user")
    - reset_session()
    - get_state_dict()
    - get_state()  (returns RunSessionState)
    - take_latest_decision_plan()  (returns plan once; then cleared)

    Progress + logs emitted through ProgressEventBusMS (provided or internal).
    """

    def __init__(
        self,
        *,
        event_bus: Optional[ProgressEventBusMS] = None,
    ):
        self.bus = event_bus or ProgressEventBusMS()
        self.token = CancellationTokenMS()
        self.state_ms = RunSessionStateMS()
        self.err_ms = ErrorNormalizerMS()

        self._state_lock = Lock()
        self._session: RunSessionState = self.state_ms.new_session(session_id=self._new_session_id())
        self._worker: Optional[Thread] = None
        self._latest_decision_plan: Optional[Dict[str, Any]] = None

        # Microservices (stateless or light state)
        self.py_enum_ms = PythonFileEnumeratorMS(PythonEnumConfig(include_pyw=True))
        self.ast_cache_ms = AstParseCacheMS()
        self.uimap_model_ms = UiMapModelMS()
        self.report_writer_ms = ReportWriterMS()
        self.report_serializer_ms = ReportSerializerMS()

        self.cb_graph_ms = CallbackGraphBuilderMS()
        self.unknown_collector_ms = UnknownCaseCollectorMS()

        self.infer_prompt_ms = InferencePromptBuilderMS()
        self.infer_validator_ms = InferenceResultValidatorMS()
        self.hitl_router_ms = HitlDecisionRouterMS()

        # Crawl + mapping are created per run (need project root)
        self._crawl_ms = None

    # -------------------------
    # Public API
    # -------------------------

    def start_run(self, project_root: Path, settings: Optional[BackendSettings] = None) -> str:
        """
        Start a new run. If a run is active, this will refuse and return current session_id.
        """
        settings = settings or BackendSettings()
        project_root = Path(project_root).resolve()

        with self._state_lock:
            if self._worker is not None and self._worker.is_alive():
                self.bus.emit(
                    type="backend",
                    message="Run already in progress; start_run ignored.",
                    level="warn",
                    meta={"session_id": self._session.session_id},
                )
                return self._session.session_id

            # Fresh session for each run
            self._session = self.state_ms.new_session(session_id=self._new_session_id())
            self._latest_decision_plan = None
            self.token.reset()
            self.ast_cache_ms.clear()

            self.state_ms.set_project_root(self._session, project_root)
            self.state_ms.set_status(self._session, "running")
            self._emit_stage("start", f"Starting run for: {project_root}")

            # Apply config updates
            self.py_enum_ms.config.include_pyw = bool(settings.include_pyw)
            self.hitl_router_ms.policy = settings.hitl_policy

            # Ensure crawl service exists (constructed per-run because it needs project_root)
            if ProjectCrawlMS is None or CrawlConfig is None:
                self.state_ms.set_status(self._session, "error", error="ProjectCrawlMS import failed")
                self.bus.emit(type="error", message="ProjectCrawlMS not available; cannot run.", level="error")
                return self._session.session_id

            try:
                self._crawl_ms = ProjectCrawlMS(CrawlConfig(root=project_root))
            except Exception as e:
                msg = f"ProjectCrawlMS failed to initialize: {e}"
                self.state_ms.set_status(self._session, "error", error=msg)
                self.bus.emit(type="error", message=msg, level="error")
                return self._session.session_id

            # Spawn worker
            self._worker = Thread(
                target=self._run_worker,
                args=(project_root, settings),
                daemon=True,
                name=f"UiMapperBackend-{self._session.session_id}",
            )
            self._worker.start()
            return self._session.session_id

    def cancel_run(self, reason: str = "user") -> None:
        self.token.cancel(reason=reason)
        self.bus.emit(type="cancel", message=f"Cancellation requested: {reason}", level="warn")

    def reset_session(self) -> None:
        with self._state_lock:
            if self._worker is not None and self._worker.is_alive():
                self.cancel_run("reset_session")
            self.state_ms.reset(self._session)
            self._latest_decision_plan = None
            self.ast_cache_ms.clear()
            self.token.reset()
        self.bus.emit(type="backend", message="Session reset.", level="info")

    def get_state(self) -> RunSessionState:
        with self._state_lock:
            return self._session

    def get_state_dict(self) -> Dict[str, Any]:
        with self._state_lock:
            return self._session.to_dict()

    def take_latest_decision_plan(self) -> Optional[Dict[str, Any]]:
        """
        Returns the last decision plan (if any) once, then clears it.
        UI orchestrator calls this after run completes to present approvals.
        """
        with self._state_lock:
            plan = self._latest_decision_plan
            self._latest_decision_plan = None
            return plan

    # -------------------------
    # Worker
    # -------------------------

    def _run_worker(self, project_root: Path, settings: BackendSettings) -> None:
        t0 = time.time()
        try:
            cancel = self.token.predicate()

            # -------------------------
            # Stage 1: .gitignore filter
            # -------------------------
            self._emit_stage("gitignore", "Loading .gitignore rules...")
            gitignore_ms = GitignoreFilterMS(root=project_root)
            gitignore_ms.load()
            git_pred = gitignore_ms.predicate()

            if cancel():
                return self._finish_cancelled()

            # -------------------------
            # Stage 2: Crawl project
            # -------------------------
            self._emit_stage("crawl", "Crawling project...")
            crawl_entries = []
            for entry in self._crawl_ms.crawl(path_filters=[git_pred]):
                if cancel():
                    return self._finish_cancelled()
                crawl_entries.append(entry)
                # update session counters lightly
                try:
                    self.state_ms.add_entry(self._session, entry.rel_path, entry.is_dir)
                except Exception:
                    pass

            self._emit_stage("crawl", f"Crawl complete. Entries: {len(crawl_entries)}")

            # -------------------------
            # Stage 3: Enumerate Python files
            # -------------------------
            self._emit_stage("enumerate", "Enumerating Python files...")
            py_files = self.py_enum_ms.enumerate(crawl_entries)
            self.state_ms.set_py_files(self._session, py_files)
            self._emit_stage("enumerate", f"Python files: {len(py_files)}")

            if cancel():
                return self._finish_cancelled()

            # -------------------------
            # Stage 4: Entrypoint candidates
            # -------------------------
            self._emit_stage("entrypoints", "Finding entrypoint candidates...")
            ep_finder = EntrypointFinderMS(project_root=project_root)
            candidates = ep_finder.find_candidates(py_files)
            self.state_ms.set_entrypoints(self._session, candidates)
            self._emit_stage("entrypoints", f"Entrypoint candidates: {len(candidates)}")

            if cancel():
                return self._finish_cancelled()

            # -------------------------
            # Stage 5: AST parse
            # -------------------------
            self._emit_stage("ast", "Parsing ASTs...")
            ast_by_path: Dict[Path, Any] = {}
            for p in py_files:
                if cancel():
                    return self._finish_cancelled()
                res = self.ast_cache_ms.parse(p)
                if res.ok and res.tree is not None:
                    ast_by_path[p] = res.tree
                    self.state_ms.add_ast_ok(self._session, p)
                else:
                    err = res.error
                    self.state_ms.add_ast_error(
                        self._session,
                        {
                            "path": str(p),
                            "message": getattr(err, "message", "parse_error"),
                            "lineno": getattr(err, "lineno", None),
                            "col": getattr(err, "col_offset", None),
                        },
                    )

            self._emit_stage("ast", f"AST parsed. ok={self._session.counters.ast_ok} err={self._session.counters.ast_err}")

            if cancel():
                return self._finish_cancelled()

            # -------------------------
            # Stage 6: UI map
            # -------------------------
            self._emit_stage("map", "Building UI map...")
            mapper = AstUiMapMS(project_root=project_root)
            ui_map_obj = mapper.map_project(
                ast_by_path,
                cancel=cancel,
                log=self.bus.make_logger("map"),
            )

            # Consolidate unknowns (optional, but useful for inference selection)
            self.unknown_collector_ms.clear()
            for u in getattr(ui_map_obj, "unknowns", []) or []:
                where = getattr(u, "where", None)
                self.unknown_collector_ms.record(
                    kind=getattr(u, "kind", "unknown"),
                    detail=getattr(u, "detail", ""),
                    path=Path(getattr(where, "path", str(project_root))),
                    lineno=getattr(where, "lineno", None),
                    col=getattr(where, "col", None),
                    snippet=getattr(u, "snippet", None),
                    context=getattr(u, "context", None) or {},
                )

            # Normalize to dict for state storage
            if isinstance(ui_map_obj, dict):
                ui_map_dict = ui_map_obj
            else:
                to_dict = getattr(ui_map_obj, "to_dict", None)
                if callable(to_dict):
                    ui_map_dict = to_dict()
                elif is_dataclass(ui_map_obj):
                    ui_map_dict = asdict(ui_map_obj)
                else:
                    ui_map_dict = dict(getattr(ui_map_obj, "__dict__", {}) or {})

            self.state_ms.set_ui_map(self._session, ui_map_dict)
            self._emit_stage(
                "map",
                f"UI map built. windows={self._session.counters.windows} widgets={self._session.counters.widgets} unknowns={self._session.counters.unknowns}",
            )

            if cancel():
                return self._finish_cancelled()

            # -------------------------
            # Stage 7: Callback graph
            # -------------------------
            self._emit_stage("graph", "Building callback graph...")
            graph = self.cb_graph_ms.build(ast_by_path, ui_map_obj)
            # Store minimal callback graph for UI; keep it light
            graph_dict = {
                "nodes": {k: {"kind": v.kind, "key": v.key} for k, v in graph.nodes.items()},
                "edges": [
                    {"src": f"{e.src.kind}:{e.src.key}", "dst": f"{e.dst.kind}:{e.dst.key}", "kind": e.kind}
                    for e in graph.edges
                ],
                "unknowns": list(graph.unknowns),
            }
            with self._state_lock:
                self._session.callback_graph = graph_dict
            self._emit_stage("graph", f"Callback graph: nodes={len(graph.nodes)} edges={len(graph.edges)}")

            if cancel():
                return self._finish_cancelled()

            # -------------------------
            # Stage 8: Optional inference (prepare HITL plan)
            # -------------------------
            if settings.enable_inference:
                self._emit_stage("inference", "Preparing inference prompt...")
                unknown_cases = self.unknown_collector_ms.select_for_inference(max_items=settings.inference_max_cases)
                if not unknown_cases:
                    self._emit_stage("inference", "No unknown cases selected; skipping inference.")
                elif not settings.ollama_model.strip():
                    self._emit_stage("inference", "No ollama_model set; skipping inference.", level="warn")
                else:
                    prompt = self.infer_prompt_ms.build_prompt(
                        project_root=str(project_root),
                        unknown_cases=unknown_cases,
                    )

                    self._emit_stage("inference", f"Calling Ollama model: {settings.ollama_model}")
                    client = OllamaClientMS(
                        OllamaClientConfig(
                            base_url=settings.ollama_base_url,
                            timeout_sec=settings.ollama_timeout_sec,
                        )
                    )
                    resp = client.generate(
                        model=settings.ollama_model,
                        prompt=prompt,
                        format="json",
                        stream=False,
                    )
                    if not resp.ok or not resp.text:
                        self._emit_stage(
                            "inference",
                            "Ollama inference failed; continuing without applying results.",
                            level="warn",
                        )
                    else:
                        outcome = self.infer_validator_ms.validate_json_text(resp.text)
                        if not outcome.ok:
                            self._emit_stage(
                                "inference",
                                "Inference JSON invalid; continuing without applying results.",
                                level="warn",
                                meta={"errors": [e.message for e in outcome.errors]},
                            )
                        else:
                            plan = self.hitl_router_ms.build_plan(outcome.results)

                            # Auto-apply decisions conservatively (currently adds annotations)
                            auto_applied = 0
                            for item in plan.items:
                                if item.action == "auto_apply":
                                    self.uimap_model_ms.apply_inference_patch(
                                        ui_map_obj,
                                        case_id=item.case_id,
                                        classification=item.classification,
                                        extracted=item.extracted,
                                        notes=item.notes,
                                    )
                                    auto_applied += 1

                            # Store remaining decisions for UI to present (ask_user)
                            plan_dict = {
                                "stats": dict(plan.stats),
                                "items": [
                                    {
                                        "case_id": it.case_id,
                                        "classification": it.classification,
                                        "confidence": it.confidence,
                                        "action": it.action,
                                        "extracted": dict(it.extracted),
                                        "notes": it.notes,
                                    }
                                    for it in plan.items
                                ],
                            }
                            with self._state_lock:
                                self._latest_decision_plan = plan_dict

                            # Refresh state ui_map after annotation
                            ui_map_dict2 = ui_map_obj.to_dict() if hasattr(ui_map_obj, "to_dict") else ui_map_obj  # type: ignore
                            self.state_ms.set_ui_map(self._session, ui_map_dict2)

                            self._emit_stage(
                                "inference",
                                f"Inference complete. auto_applied={auto_applied} ask_user={plan.stats.get('ask_user', 0)}",
                            )

            if cancel():
                return self._finish_cancelled()

            # -------------------------
            # Stage 9: Reports
            # -------------------------
            out_dir = settings.report_out_dir
            if out_dir is None:
                out_dir = project_root / "_uimapper_reports"
            out_dir = Path(out_dir).resolve()
            out_dir.mkdir(parents=True, exist_ok=True)

            md_path = out_dir / "uimap_report.md"
            json_path = out_dir / "uimap_report.json"
            jsonl_path = out_dir / "uimap_report.jsonl"

            self._emit_stage("report", f"Writing reports to: {out_dir}")

            # Reports expect dict-like structures (use .get). Normalize UiMap before writing.
            if isinstance(ui_map_obj, dict):
                report_uimap = ui_map_obj
            else:
                to_dict = getattr(ui_map_obj, "to_dict", None)
                if callable(to_dict):
                    report_uimap = to_dict()
                elif is_dataclass(ui_map_obj):
                    report_uimap = asdict(ui_map_obj)
                else:
                    report_uimap = dict(getattr(ui_map_obj, "__dict__", {}) or {})

            if settings.write_md:
                self.report_writer_ms.write_markdown(report_uimap, md_path)
            if settings.write_json:
                self.report_serializer_ms.write_json(report_uimap, json_path)
            if settings.write_jsonl:
                self.report_serializer_ms.write_jsonl(report_uimap, jsonl_path)

            self.state_ms.set_report_paths(
                self._session,
                md=md_path if settings.write_md else None,
                json_path=json_path if settings.write_json else None,
                jsonl=jsonl_path if settings.write_jsonl else None,
            )

            # Done
            dt = time.time() - t0
            with self._state_lock:
                self._session.meta["duration_sec"] = round(dt, 3)
            self.state_ms.set_status(self._session, "done")
            self._emit_stage("done", f"Run complete in {dt:.2f}s.")

        except Exception as e:
            ne = self.err_ms.normalize(e, include_traceback=False)
            self.state_ms.set_status(self._session, "error", error=ne.message)
            self.bus.emit(type="error", message=ne.message, level="error", meta=ne.to_dict())

    # -------------------------
    # Internal helpers
    # -------------------------

    def _finish_cancelled(self) -> None:
        self.state_ms.set_status(self._session, "cancelled", error=self.token.reason())
        self.bus.emit(type="cancelled", message="Run cancelled.", level="warn", meta={"reason": self.token.reason()})

    def _emit_stage(self, stage: str, message: str, *, level: str = "info", meta: Optional[Dict[str, Any]] = None) -> None:
        self.bus.emit(type="stage", message=f"{stage}: {message}", level=level, meta=meta or {})

    def _new_session_id(self) -> str:
        return uuid.uuid4().hex[:10]


# -------------------------
# Optional: module-level convenience singleton
# -------------------------

_backend_singleton: Optional[BackendOrchestrator] = None


def get_backend(event_bus: Optional[ProgressEventBusMS] = None) -> BackendOrchestrator:
    global _backend_singleton
    if _backend_singleton is None:
        _backend_singleton = BackendOrchestrator(event_bus=event_bus)
    return _backend_singleton









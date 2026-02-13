"""
RunSessionStateMS
-----------------
State container for a single "run" of the UI mapping pipeline.

Why:
- Orchestrators need a shared object to store:
    - selected project root
    - discovered file lists
    - parse results
    - ui_map artifacts
    - report output paths
    - timings + counters
- UI layer needs to observe state changes (polling or events)

Responsibilities:
- Hold session fields in a structured dataclass
- Provide reset/clear methods
- Provide lightweight update helpers + counters
- Keep it UI-agnostic (no Tk variables)

Non-goals:
- Persistence (save/load) — could be another microservice later
- Threading
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class RunCounters:
    dirs_seen: int = 0
    files_seen: int = 0
    py_files: int = 0
    ast_ok: int = 0
    ast_err: int = 0
    widgets: int = 0
    windows: int = 0
    unknowns: int = 0


@dataclass
class RunSessionState:
    session_id: str

    project_root: Optional[str] = None

    # Discovery
    all_entries: List[str] = field(default_factory=list)
    py_files: List[str] = field(default_factory=list)
    entrypoint_candidates: List[Dict[str, Any]] = field(default_factory=list)

    # AST
    ast_ok_paths: List[str] = field(default_factory=list)
    ast_error_items: List[Dict[str, Any]] = field(default_factory=list)

    # Mapping outputs
    ui_map: Optional[Dict[str, Any]] = None  # usually UiMap.to_dict()
    callback_graph: Optional[Dict[str, Any]] = None

    # Reports
    report_md_path: Optional[str] = None
    report_json_path: Optional[str] = None
    report_jsonl_path: Optional[str] = None

    # Timing + counters
    counters: RunCounters = field(default_factory=RunCounters)
    meta: Dict[str, Any] = field(default_factory=dict)

    # Errors / status
    status: str = "idle"  # idle|running|cancelled|done|error
    last_error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RunSessionStateMS:
    """
    Provides session creation + mutation helpers.
    """

    def new_session(self, session_id: str) -> RunSessionState:
        return RunSessionState(session_id=session_id)

    def reset(self, s: RunSessionState) -> None:
        sid = s.session_id
        s.__dict__.clear()
        # Re-init minimal
        fresh = RunSessionState(session_id=sid)
        s.__dict__.update(fresh.__dict__)

    # -------------------------
    # Update helpers
    # -------------------------

    def set_project_root(self, s: RunSessionState, root: Path) -> None:
        s.project_root = str(Path(root).resolve())

    def set_status(self, s: RunSessionState, status: str, error: Optional[str] = None) -> None:
        s.status = status
        s.last_error = error

    def add_entry(self, s: RunSessionState, rel_path: Path, is_dir: bool) -> None:
        s.all_entries.append(rel_path.as_posix())
        if is_dir:
            s.counters.dirs_seen += 1
        else:
            s.counters.files_seen += 1

    def set_py_files(self, s: RunSessionState, py_files: List[Path]) -> None:
        s.py_files = [p.as_posix() for p in py_files]
        s.counters.py_files = len(py_files)

    def set_entrypoints(self, s: RunSessionState, candidates: List[object]) -> None:
        """
        candidates: duck-typed EntrypointCandidate(path, score, reasons)
        """
        out: List[Dict[str, Any]] = []
        for c in candidates:
            out.append(
                {
                    "path": getattr(c, "path").as_posix() if getattr(c, "path", None) else "",
                    "score": int(getattr(c, "score", 0)),
                    "reasons": list(getattr(c, "reasons", []) or []),
                }
            )
        s.entrypoint_candidates = out

    def add_ast_ok(self, s: RunSessionState, path: Path) -> None:
        s.ast_ok_paths.append(path.as_posix())
        s.counters.ast_ok += 1

    def add_ast_error(self, s: RunSessionState, err_item: Dict[str, Any]) -> None:
        s.ast_error_items.append(dict(err_item))
        s.counters.ast_err += 1

    def set_ui_map(self, s: RunSessionState, ui_map_dict: Dict[str, Any]) -> None:
        s.ui_map = dict(ui_map_dict)
        # attempt to update counters
        s.counters.windows = len((ui_map_dict.get("windows") or {}))
        s.counters.widgets = len((ui_map_dict.get("widgets") or {}))
        s.counters.unknowns = len((ui_map_dict.get("unknowns") or []))

    def set_report_paths(
        self,
        s: RunSessionState,
        *,
        md: Optional[Path] = None,
        json_path: Optional[Path] = None,
        jsonl: Optional[Path] = None,
    ) -> None:
        if md is not None:
            s.report_md_path = Path(md).as_posix()
        if json_path is not None:
            s.report_json_path = Path(json_path).as_posix()
        if jsonl is not None:
            s.report_jsonl_path = Path(jsonl).as_posix()


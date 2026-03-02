"""
UiMapModelMS
------------
Canonical data model + helpers for UI mapping results.

Why:
- Multiple services (AstUiMapMS, CallbackGraphBuilderMS, ReportWriterMS, UI)
  need a shared, stable schema.
- This microservice owns:
    - dataclasses
    - merging/patching helpers
    - deterministic ID assignment helpers (optional)
    - lightweight query helpers

Responsibilities:
- Define UiMap, UiWindow, UiWidget, UnknownCase, SourceLoc
- Provide safe merge/patch operations (e.g., apply inference result)
- Provide export-ready dict conversion (pure python primitives)

Non-goals:
- AST traversal
- Report formatting (ReportWriterMS)
- LLM prompts/validation
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# -------------------------
# Core Structures
# -------------------------

@dataclass(frozen=True)
class SourceLoc:
    path: str
    lineno: Optional[int] = None
    col: Optional[int] = None


@dataclass
class UiWindow:
    window_id: str
    created_at: SourceLoc
    title_calls: List[str] = field(default_factory=list)
    geometry_calls: List[str] = field(default_factory=list)
    config_calls: List[str] = field(default_factory=list)


@dataclass
class UiWidget:
    widget_id: str
    widget_type: str
    parent_id: Optional[str]
    created_at: SourceLoc

    kwargs: Dict[str, str] = field(default_factory=dict)

    layout_calls: List[str] = field(default_factory=list)
    config_calls: List[str] = field(default_factory=list)

    # Callbacks / event wiring
    command_targets: List[str] = field(default_factory=list)
    bind_events: List[str] = field(default_factory=list)


@dataclass
class UnknownCase:
    kind: str
    detail: str
    where: SourceLoc
    snippet: Optional[str] = None
    context: Dict[str, str] = field(default_factory=dict)


@dataclass
class UiMap:
    project_root: str

    windows: Dict[str, UiWindow] = field(default_factory=dict)
    widgets: Dict[str, UiWidget] = field(default_factory=dict)

    unknowns: List[UnknownCase] = field(default_factory=list)
    parse_errors: List[str] = field(default_factory=list)

    # Optional graphs / enrichments
    callback_edges: List[Dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to JSON-serializable dict deterministically.
        """
        def _sort_dict(d: Dict[str, Any]) -> Dict[str, Any]:
            return {k: d[k] for k in sorted(d.keys(), key=lambda x: str(x).lower())}

        out = asdict(self)

        # Deterministic ordering for dict fields
        out["windows"] = _sort_dict(out.get("windows", {}))
        out["widgets"] = _sort_dict(out.get("widgets", {}))

        # Deterministic ordering for unknowns (by file/line/kind)
        out["unknowns"] = sorted(
            out.get("unknowns", []),
            key=lambda u: (
                str(u.get("where", {}).get("path", "")).lower(),
                int(u.get("where", {}).get("lineno") or 0),
                str(u.get("kind", "")).lower(),
                str(u.get("detail", "")).lower(),
            ),
        )
        return out


# -------------------------
# Service
# -------------------------

class UiMapModelMS:
    """
    Helper operations around UiMap.
    """

    # -------------------------
    # Construction helpers
    # -------------------------

    def new_map(self, project_root: Path) -> UiMap:
        return UiMap(project_root=str(Path(project_root).resolve()))

    def loc(self, path: Path, node: Optional[object] = None) -> SourceLoc:
        return SourceLoc(
            path=str(Path(path).resolve()),
            lineno=getattr(node, "lineno", None) if node is not None else None,
            col=getattr(node, "col_offset", None) if node is not None else None,
        )

    # -------------------------
    # Unknown handling
    # -------------------------

    def add_unknown(
        self,
        ui_map: UiMap,
        *,
        kind: str,
        detail: str,
        where: SourceLoc,
        snippet: Optional[str] = None,
        context: Optional[Dict[str, str]] = None,
    ) -> None:
        ui_map.unknowns.append(
            UnknownCase(
                kind=kind,
                detail=detail,
                where=where,
                snippet=snippet,
                context=context or {},
            )
        )

    # -------------------------
    # Patch / merge helpers
    # -------------------------

    def apply_inference_patch(
        self,
        ui_map: UiMap,
        *,
        case_id: str,
        classification: str,
        extracted: Dict[str, Optional[str]],
        notes: str = "",
    ) -> None:
        """
        Apply a validated inference result conservatively.
        This function does NOT remove unknowns automatically. It can annotate.

        Strategy:
        - For now, we simply append an annotation unknown with kind="inference_applied"
          so downstream report can show what happened.
        - Later, you can map case_id -> specific unknown index and "resolve" it.
        """
        self.add_unknown(
            ui_map,
            kind="inference_applied",
            detail=f"{case_id} classification={classification} notes={notes}".strip(),
            where=SourceLoc(path=ui_map.project_root),
            snippet=None,
            context={k: (v if v is not None else "") for k, v in extracted.items()},
        )

    def merge_maps(self, base: UiMap, other: UiMap) -> UiMap:
        """
        Merge two UiMaps. Deterministic, conservative:
        - windows/widgets merged by id (other overwrites on key collision)
        - unknowns concatenated
        - parse_errors concatenated
        """
        out = UiMap(project_root=base.project_root)

        out.windows = dict(base.windows)
        out.windows.update(other.windows)

        out.widgets = dict(base.widgets)
        out.widgets.update(other.widgets)

        out.unknowns = list(base.unknowns) + list(other.unknowns)
        out.parse_errors = list(base.parse_errors) + list(other.parse_errors)
        out.callback_edges = list(base.callback_edges) + list(other.callback_edges)

        return out

    # -------------------------
    # Query helpers
    # -------------------------

    def widgets_by_type(self, ui_map: UiMap, widget_type: str) -> List[UiWidget]:
        wt = widget_type.strip()
        return [w for w in ui_map.widgets.values() if w.widget_type == wt]

    def root_windows(self, ui_map: UiMap) -> List[UiWindow]:
        return list(ui_map.windows.values())


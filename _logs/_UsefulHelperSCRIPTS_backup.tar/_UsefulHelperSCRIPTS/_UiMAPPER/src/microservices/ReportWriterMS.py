"""
ReportWriterMS
--------------
Generate human-readable reports from UiMap.

Responsibilities:
- Produce Markdown (primary) report from UiMapModelMS.UiMap (or compatible dict)
- Keep output deterministic (stable ordering)
- Provide a compact executive summary + detailed sections:
    - windows
    - widgets (grouped by type)
    - layout/config calls
    - callbacks/binds
    - unknown cases
    - parse errors

Non-goals:
- File dialogs / choosing output paths (UI orchestrator)
- JSON serialization (ReportSerializerMS can do raw export)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json


# -------------------------
# Config
# -------------------------

@dataclass
class ReportWriterConfig:
    include_timestamp: bool = True
    max_unknown_examples: int = 50
    max_call_items_per_widget: int = 50


# -------------------------
# Service
# -------------------------

class ReportWriterMS:
    def __init__(self, config: Optional[ReportWriterConfig] = None):
        self.config = config or ReportWriterConfig()

    def build_markdown(self, ui_map: object) -> str:
        """
        ui_map: duck-typed UiMap or dict-like
        """
        m = self._as_dict(ui_map)

        lines: List[str] = []
        lines.append("# UI Mapper Report")
        if self.config.include_timestamp:
            lines.append(f"_Generated: {datetime.now().isoformat(timespec='seconds')}_")
        lines.append("")
        lines.append(f"**Project Root:** `{m.get('project_root', '')}`")
        lines.append("")

        # Summary
        windows = m.get("windows", {}) or {}
        widgets = m.get("widgets", {}) or {}
        unknowns = m.get("unknowns", []) or []
        parse_errors = m.get("parse_errors", []) or []

        lines.append("## Summary")
        lines.append(f"- Windows detected: **{len(windows)}**")
        lines.append(f"- Widgets detected: **{len(widgets)}**")
        lines.append(f"- Unknown cases: **{len(unknowns)}**")
        lines.append(f"- Parse errors: **{len(parse_errors)}**")
        lines.append("")

        # Windows
        lines.append("## Windows")
        if not windows:
            lines.append("_None detected._")
        else:
            for win_id in sorted(windows.keys(), key=lambda x: str(x).lower()):
                w = windows[win_id]
                lines.extend(self._render_window(win_id, w))
        lines.append("")

        # Widgets grouped by type
        lines.append("## Widgets")
        if not widgets:
            lines.append("_None detected._")
        else:
            by_type: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
            for wid, w in widgets.items():
                wt = str(w.get("widget_type", "<?>"))
                by_type.setdefault(wt, []).append((wid, w))

            for wt in sorted(by_type.keys(), key=lambda x: str(x).lower()):
                lines.append(f"### {wt} ({len(by_type[wt])})")
                for wid, w in sorted(by_type[wt], key=lambda t: str(t[0]).lower()):
                    lines.extend(self._render_widget(wid, w))
                lines.append("")
        lines.append("")

        # Unknowns
        lines.append("## Unknown Cases")
        if not unknowns:
            lines.append("_None._")
        else:
            # sort by file/line/kind
            unknowns_sorted = sorted(
                unknowns,
                key=lambda u: (
                    str(u.get("where", {}).get("path", "")).lower(),
                    int(u.get("where", {}).get("lineno") or 0),
                    str(u.get("kind", "")).lower(),
                    str(u.get("detail", "")).lower(),
                ),
            )
            shown = unknowns_sorted[: self.config.max_unknown_examples]
            lines.append(f"_Showing {len(shown)} of {len(unknowns_sorted)}._")
            lines.append("")
            for u in shown:
                lines.extend(self._render_unknown(u))
        lines.append("")

        # Parse errors
        lines.append("## Parse Errors")
        if not parse_errors:
            lines.append("_None._")
        else:
            for e in parse_errors:
                lines.append(f"- {e}")
        lines.append("")

        return "\n".join(lines).rstrip() + "\n"

    def write_markdown(self, ui_map: object, out_path: Path) -> Path:
        out_path = Path(out_path)
        md = self.build_markdown(ui_map)
        out_path.write_text(md, encoding="utf-8")
        return out_path

    # -------------------------
    # Render helpers
    # -------------------------

    def _render_window(self, win_id: str, w: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        created_at = w.get("created_at", {}) or {}
        where = self._render_loc(created_at)

        lines.append(f"### {win_id}")
        lines.append(f"- Created at: {where}")

        titles = w.get("title_calls", []) or []
        geos = w.get("geometry_calls", []) or []
        cfgs = w.get("config_calls", []) or []

        if titles:
            lines.append("- Title calls:")
            for t in titles[: self.config.max_call_items_per_widget]:
                lines.append(f"  - `{t}`")
        if geos:
            lines.append("- Geometry calls:")
            for g in geos[: self.config.max_call_items_per_widget]:
                lines.append(f"  - `{g}`")
        if cfgs:
            lines.append("- Config calls:")
            for c in cfgs[: self.config.max_call_items_per_widget]:
                lines.append(f"  - `{c}`")

        return lines

    def _render_widget(self, wid: str, w: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        created_at = w.get("created_at", {}) or {}
        where = self._render_loc(created_at)

        parent = w.get("parent_id", None)
        lines.append(f"- **{wid}** (parent: `{parent}`) — created at {where}")

        kwargs = w.get("kwargs", {}) or {}
        if kwargs:
            lines.append("  - kwargs:")
            for k in sorted(kwargs.keys(), key=lambda x: str(x).lower()):
                lines.append(f"    - `{k}` = `{kwargs[k]}`")

        layouts = w.get("layout_calls", []) or []
        if layouts:
            lines.append("  - layout:")
            for lc in layouts[: self.config.max_call_items_per_widget]:
                lines.append(f"    - `{lc}`")

        cfgs = w.get("config_calls", []) or []
        if cfgs:
            lines.append("  - config:")
            for c in cfgs[: self.config.max_call_items_per_widget]:
                lines.append(f"    - `{c}`")

        cmds = w.get("command_targets", []) or []
        if cmds:
            lines.append("  - commands:")
            for c in cmds:
                lines.append(f"    - `{c}`")

        binds = w.get("bind_events", []) or []
        if binds:
            lines.append("  - binds:")
            for b in binds:
                lines.append(f"    - `{b}`")

        return lines

    def _render_unknown(self, u: Dict[str, Any]) -> List[str]:
        lines: List[str] = []
        kind = u.get("kind", "unknown")
        detail = u.get("detail", "")
        where = self._render_loc(u.get("where", {}) or {})
        lines.append(f"- **{kind}** @ {where}")
        if detail:
            lines.append(f"  - detail: {detail}")

        snippet = u.get("snippet", None)
        if snippet:
            lines.append("  - snippet:")
            lines.append("```")
            lines.extend(self._clip_lines(str(snippet), 80))
            lines.append("```")

        ctx = u.get("context", {}) or {}
        if ctx:
            lines.append("  - context:")
            for k in sorted(ctx.keys(), key=lambda x: str(x).lower()):
                v = ctx[k]
                if v is None:
                    v = ""
                lines.append(f"    - {k}: {v}")

        return lines

    def _render_loc(self, loc: Dict[str, Any]) -> str:
        p = loc.get("path", "<?>")
        ln = loc.get("lineno", None)
        col = loc.get("col", None)
        if ln is None and col is None:
            return f"`{p}`"
        return f"`{p}:{ln if ln is not None else '?'}:{col if col is not None else '?'}`"

    def _clip_lines(self, s: str, max_lines: int) -> List[str]:
        lines = s.splitlines()
        if len(lines) <= max_lines:
            return lines
        return lines[:max_lines] + ["... (truncated)"]

    def _as_dict(self, ui_map: object) -> Dict[str, Any]:
        """
        Accept UiMap dataclass with to_dict(), or a dict.
        Ensures nested values are dict-like + JSON-safe so report rendering can use .get().
        """
        def _to_jsonable(v: Any) -> Any:
            if v is None or isinstance(v, (str, int, float, bool)):
                return v
            if isinstance(v, Path):
                return str(v)
            if isinstance(v, dict):
                return {str(_to_jsonable(k)): _to_jsonable(val) for k, val in v.items()}
            if isinstance(v, (list, tuple, set)):
                return [_to_jsonable(x) for x in v]

            try:
                from dataclasses import is_dataclass, asdict
                if is_dataclass(v):
                    return _to_jsonable(asdict(v))
            except Exception:
                pass

            to_dict = getattr(v, "to_dict", None)
            if callable(to_dict):
                try:
                    return _to_jsonable(to_dict())
                except Exception:
                    pass

            d = getattr(v, "__dict__", None)
            if isinstance(d, dict):
                return _to_jsonable(d)

            return str(v)

        # Normalize top-level
        if isinstance(ui_map, dict):
            base = ui_map
        else:
            to_dict = getattr(ui_map, "to_dict", None)
            if callable(to_dict):
                base = to_dict()
            else:
                base = {}
                for k in ("project_root", "windows", "widgets", "unknowns", "parse_errors", "callback_edges"):
                    base[k] = getattr(ui_map, k, None)

        out_any = _to_jsonable(base)
        return out_any if isinstance(out_any, dict) else {"value": out_any}



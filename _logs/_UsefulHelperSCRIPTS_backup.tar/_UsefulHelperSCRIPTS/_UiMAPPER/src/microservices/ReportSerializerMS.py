"""
ReportSerializerMS
------------------
Serialize UiMap artifacts to JSON (and optionally JSONL) in a deterministic way.

Responsibilities:
- Write UiMap.to_dict() output to:
    - JSON (pretty)
    - JSON (compact)
    - JSONL (optional): stream records (widgets/windows/unknowns) for tooling
- Provide stable ordering for deterministic diffs

Non-goals:
- Markdown rendering (ReportWriterMS)
- Choosing output paths (UI orchestrator)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


# -------------------------
# Config
# -------------------------

@dataclass
class ReportSerializerConfig:
    pretty: bool = True
    indent: int = 2
    ensure_ascii: bool = False
    sort_keys: bool = True


# -------------------------
# Service
# -------------------------

class ReportSerializerMS:
    def __init__(self, config: Optional[ReportSerializerConfig] = None):
        self.config = config or ReportSerializerConfig()

    # -------------------------
    # JSON
    # -------------------------

    def dumps_json(self, ui_map: object) -> str:
        data = self._as_dict(ui_map)
        if self.config.pretty:
            return json.dumps(
                data,
                indent=self.config.indent,
                ensure_ascii=self.config.ensure_ascii,
                sort_keys=self.config.sort_keys,
            ) + "\n"
        return json.dumps(
            data,
            ensure_ascii=self.config.ensure_ascii,
            sort_keys=self.config.sort_keys,
            separators=(",", ":"),
        ) + "\n"

    def write_json(self, ui_map: object, out_path: Path) -> Path:
        out_path = Path(out_path)
        out_path.write_text(self.dumps_json(ui_map), encoding="utf-8")
        return out_path

    # -------------------------
    # JSONL (optional tooling export)
    # -------------------------

    def write_jsonl(self, ui_map: object, out_path: Path) -> Path:
        """
        Writes multiple JSONL record types:
            {"type":"meta", ...}
            {"type":"window", "id":..., ...}
            {"type":"widget", "id":..., ...}
            {"type":"unknown", ...}
            {"type":"parse_error", ...}
        """
        out_path = Path(out_path)
        data = self._as_dict(ui_map)

        with out_path.open("w", encoding="utf-8") as f:
            # meta
            meta = {"type": "meta", "project_root": data.get("project_root", "")}
            f.write(json.dumps(meta, ensure_ascii=self.config.ensure_ascii) + "\n")

            windows = data.get("windows", {}) or {}
            for win_id in sorted(windows.keys(), key=lambda x: str(x).lower()):
                rec = {"type": "window", "id": win_id}
                rec.update(windows[win_id])
                f.write(json.dumps(rec, ensure_ascii=self.config.ensure_ascii) + "\n")

            widgets = data.get("widgets", {}) or {}
            for wid in sorted(widgets.keys(), key=lambda x: str(x).lower()):
                rec = {"type": "widget", "id": wid}
                rec.update(widgets[wid])
                f.write(json.dumps(rec, ensure_ascii=self.config.ensure_ascii) + "\n")

            unknowns = data.get("unknowns", []) or []
            for u in unknowns:
                rec = {"type": "unknown"}
                rec.update(u)
                f.write(json.dumps(rec, ensure_ascii=self.config.ensure_ascii) + "\n")

            parse_errors = data.get("parse_errors", []) or []
            for e in parse_errors:
                rec = {"type": "parse_error", "error": e}
                f.write(json.dumps(rec, ensure_ascii=self.config.ensure_ascii) + "\n")

        return out_path

    # -------------------------
    # Internal
    # -------------------------

    def _as_dict(self, ui_map: object) -> Dict[str, Any]:
        def _to_jsonable(v: Any) -> Any:
            # Primitives
            if v is None or isinstance(v, (str, int, float, bool)):
                return v

            # Path-like
            if isinstance(v, Path):
                return str(v)

            # Containers
            if isinstance(v, dict):
                return {str(_to_jsonable(k)): _to_jsonable(val) for k, val in v.items()}
            if isinstance(v, (list, tuple, set)):
                return [_to_jsonable(x) for x in v]

            # dataclasses
            try:
                from dataclasses import is_dataclass, asdict
                if is_dataclass(v):
                    return _to_jsonable(asdict(v))
            except Exception:
                pass

            # objects with to_dict
            to_dict = getattr(v, "to_dict", None)
            if callable(to_dict):
                try:
                    return _to_jsonable(to_dict())
                except Exception:
                    pass

            # fallback: __dict__
            d = getattr(v, "__dict__", None)
            if isinstance(d, dict):
                return _to_jsonable(d)

            # last resort: stringify
            return str(v)

        # Normalize the top-level map first
        if isinstance(ui_map, dict):
            base = ui_map
        else:
            to_dict = getattr(ui_map, "to_dict", None)
            if callable(to_dict):
                base = to_dict()
            else:
                # best-effort attribute extraction
                base = {}
                for k in ("project_root", "windows", "widgets", "unknowns", "parse_errors", "callback_edges"):
                    base[k] = getattr(ui_map, k, None)

        out_any = _to_jsonable(base)
        return out_any if isinstance(out_any, dict) else {"value": out_any}



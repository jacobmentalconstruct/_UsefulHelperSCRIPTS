"""UI schema validation, preview, and commit helpers."""

from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Any, Dict, List, Optional

from .constants import UI_PACKS


class UiSchemaPreviewService:
    def default_schema(self, ui_pack: str='tkinter_base_pack') -> Dict[str, Any]:
        pack = UI_PACKS.get(ui_pack, UI_PACKS['headless_pack'])
        return json.loads(json.dumps(pack['manifest']))

    def load_schema(self, path: Path) -> Dict[str, Any]:
        return json.loads(Path(path).read_text(encoding='utf-8'))

    def validate_schema(self, schema: Dict[str, Any]) -> List[str]:
        errors: List[str] = []
        if not isinstance(schema, dict):
            return ['Schema must be a JSON object.']
        if 'layout' not in schema or not isinstance(schema['layout'], dict):
            errors.append('Schema must contain a layout object.')
        if 'theme' not in schema or not isinstance(schema['theme'], dict):
            errors.append('Schema must contain a theme object.')
        self._validate_layout_node(schema.get('layout', {}), errors)
        return errors

    def _validate_layout_node(self, node: Dict[str, Any], errors: List[str]) -> None:
        node_type = str(node.get('type', '')).strip()
        if node_type not in {'row', 'col', 'panel'}:
            errors.append(f'Invalid layout node type: {node_type!r}')
            return
        if node_type == 'panel' and not str(node.get('id', '')).strip():
            errors.append('Panel nodes must include a non-empty id.')
        for child in node.get('children', []) or []:
            if isinstance(child, dict):
                self._validate_layout_node(child, errors)
            else:
                errors.append('Layout children must be objects.')

    def render_preview(self, parent: tk.Misc, schema: Dict[str, Any]) -> tk.Toplevel:
        errors = self.validate_schema(schema)
        if errors:
            raise ValueError('; '.join(errors))
        win = tk.Toplevel(parent)
        win.title('UI Schema Preview')
        theme = schema.get('theme', {})
        bg = theme.get('background', '#202124')
        fg = theme.get('foreground', '#f1f3f4')
        win.configure(bg=bg)
        self._build_node(win, schema['layout'], bg=bg, fg=fg)
        return win

    def _build_node(self, parent: tk.Misc, node: Dict[str, Any], *, bg: str, fg: str):
        node_type = node.get('type', 'panel')
        if node_type == 'panel':
            frame = ttk.Frame(parent, padding=6)
            if isinstance(parent, ttk.PanedWindow):
                parent.add(frame, weight=int(node.get('weight', 1)))
            else:
                frame.pack(fill='both', expand=True)
            label = ttk.Label(frame, text=node.get('id', 'panel'))
            label.pack(anchor='center', pady=12)
            return frame
        orient = tk.HORIZONTAL if node_type == 'row' else tk.VERTICAL
        pane = ttk.PanedWindow(parent, orient=orient)
        if isinstance(parent, ttk.PanedWindow):
            parent.add(pane, weight=int(node.get('weight', 1)))
        else:
            pane.pack(fill='both', expand=True)
        for child in node.get('children', []) or []:
            self._build_node(pane, child, bg=bg, fg=fg)
        return pane


class UiSchemaCommitService:
    def commit(self, schema: Dict[str, Any], app_dir: Path) -> Path:
        app_dir = Path(app_dir)
        app_dir.mkdir(parents=True, exist_ok=True)
        target = app_dir / 'ui_schema.json'
        target.write_text(json.dumps(schema, indent=2), encoding='utf-8')
        return target

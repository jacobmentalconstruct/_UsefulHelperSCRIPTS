"""Deterministic catalog query service for the librarian and stamper."""

from __future__ import annotations

from contextlib import contextmanager
import os
import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional

from .catalog import CatalogBuilder, stable_id
from .constants import (
    APP_BLUEPRINT_TEMPLATES,
    DEFAULT_CATALOG_DB_PATH,
    GROUPED_MANAGER_SERVICE_MAP,
    SPECIAL_UI_PACKS,
    UI_PACKS,
    VALID_RESOLUTION_PROFILES,
    VALID_VENDOR_MODES,
)
from .models import AppBlueprintManifest


class LibraryQueryService:
    def __init__(self, catalog_db_path: Path | None=None, auto_build: bool=True):
        catalog_override = catalog_db_path or os.environ.get("APP_FOUNDRY_CATALOG_DB_PATH") or DEFAULT_CATALOG_DB_PATH
        self.catalog_db_path = Path(catalog_override).resolve()
        self.builder = CatalogBuilder(catalog_db_path=self.catalog_db_path)
        if auto_build and not self.catalog_db_path.exists():
            self.builder.build()

    def build_catalog(self, incremental: bool=True) -> Dict[str, Any]:
        return self.builder.build(incremental=incremental)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if not self.catalog_db_path.exists():
            self.builder.build()
        conn = sqlite3.connect(self.catalog_db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def list_layers(self) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT layer FROM services WHERE layer != '' ORDER BY layer").fetchall()
        return [row['layer'] for row in rows]

    def latest_catalog_build_id(self) -> str:
        with self._connect() as conn:
            row = conn.execute('SELECT build_id FROM catalog_builds ORDER BY generated_at_utc DESC LIMIT 1').fetchone()
        return row['build_id'] if row else ''

    def list_services(self, layer: Optional[str]=None) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            if layer:
                rows = conn.execute('SELECT s.*, a.import_key, a.source_path FROM services s JOIN artifacts a ON a.artifact_id = s.artifact_id WHERE s.layer = ? ORDER BY s.layer, s.class_name', (layer,)).fetchall()
            else:
                rows = conn.execute('SELECT s.*, a.import_key, a.source_path FROM services s JOIN artifacts a ON a.artifact_id = s.artifact_id ORDER BY s.layer, s.class_name').fetchall()
        return [self._service_row_to_dict(row) for row in rows]

    def describe_service(self, identifier: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = self._resolve_service_row(conn, identifier)
            if row is None:
                return None
            endpoints = conn.execute('SELECT * FROM endpoints WHERE service_id = ? ORDER BY method_name', (row['service_id'],)).fetchall()
        payload = self._service_row_to_dict(row)
        payload['endpoints'] = [dict(endpoint) for endpoint in endpoints]
        payload['dependencies'] = self.show_dependencies(identifier)
        return payload

    def show_dependencies(self, identifier: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            row = self._resolve_service_row(conn, identifier)
            if row is None:
                return None
            rows = conn.execute(
                '''
                SELECT d.*, s.class_name AS dst_class_name, s.service_name AS dst_service_name,
                       a.import_key AS dst_import_key, a.source_path AS dst_source_path
                FROM dependencies d
                LEFT JOIN services s ON s.service_id = d.dst_service_id
                LEFT JOIN artifacts a ON a.artifact_id = d.dst_artifact_id
                WHERE d.src_service_id = ? OR d.src_artifact_id = ?
                ORDER BY d.dependency_type, d.dependency_id
                ''',
                (row['service_id'], row['artifact_id']),
            ).fetchall()
        payload = {'service': self._service_row_to_dict(row), 'code_dependencies': [], 'runtime_dependencies': [], 'external_dependencies': []}
        for dep in rows:
            item = {
                'dependency_type': dep['dependency_type'],
                'is_resolved': bool(dep['is_resolved']),
                'evidence_type': dep['evidence_type'],
                'target': dep['external_name'] or dep['pack_name'] or dep['dst_class_name'] or dep['dst_service_name'] or dep['dst_import_key'] or json.loads(dep['evidence_json']).get('ref', ''),
                'target_import_key': dep['dst_import_key'],
                'target_source_path': dep['dst_source_path'],
            }
            if dep['dependency_type'] == 'requires_external':
                payload['external_dependencies'].append(item)
            elif dep['dependency_type'] in {'requires_runtime', 'hosted_by', 'packaged_with'}:
                payload['runtime_dependencies'].append(item)
            else:
                payload['code_dependencies'].append(item)
        return payload

    def list_orchestrators(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT artifact_id, import_key, source_path FROM artifacts WHERE kind = 'module' AND source_path LIKE ? ORDER BY import_key", ('%\\library\\orchestrators\\%',)).fetchall()
        return [dict(row) for row in rows]

    def list_managers(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT artifact_id, import_key, source_path FROM artifacts WHERE kind = 'module' AND source_path LIKE ? ORDER BY import_key", ('%\\library\\managers\\%',)).fetchall()
        payload = [dict(row) for row in rows]
        payload.append({'artifact_id': 'grouped_runtime_map', 'import_key': 'grouped_runtime_map', 'source_path': 'in_memory', 'implemented_layers': GROUPED_MANAGER_SERVICE_MAP})
        return payload

    def show_ui_components(self) -> List[Dict[str, Any]]:
        return self.list_services(layer='ui')

    def list_templates(self) -> List[Dict[str, Any]]:
        return [
            {
                'template_id': template['template_id'],
                'name': template['name'],
                'description': template['description'],
                'microservices': list(template.get('microservices', [])),
                'vendor_mode': template.get('vendor_mode', 'module_ref'),
                'resolution_profile': template.get('resolution_profile', 'app_ready'),
                'tags': list(template.get('tags', [])),
            }
            for template in APP_BLUEPRINT_TEMPLATES.values()
        ]

    def template_blueprint(
        self,
        template_id: str,
        destination: str='',
        name: str='',
        vendor_mode: Optional[str]=None,
        resolution_profile: Optional[str]=None,
    ) -> Dict[str, Any]:
        template = APP_BLUEPRINT_TEMPLATES.get(str(template_id).strip())
        if template is None:
            raise KeyError(f'Unknown template: {template_id}')
        effective_vendor_mode = vendor_mode or template.get('vendor_mode', 'module_ref')
        effective_resolution_profile = resolution_profile or template.get('resolution_profile', 'app_ready')
        effective_name = name.strip() or template.get('name', 'Stamped App')
        payload = self.recommend_blueprint(
            template.get('microservices', []),
            destination=destination,
            name=effective_name,
            vendor_mode=effective_vendor_mode,
            resolution_profile=effective_resolution_profile,
        )
        payload['settings_defaults'].update(template.get('settings_defaults', {}))
        payload['settings_defaults']['app_title'] = effective_name
        payload['template_id'] = template['template_id']
        payload['template_name'] = template['name']
        payload['template_description'] = template['description']
        payload['template_tags'] = list(template.get('tags', []))
        return payload

    def validate_manifest(self, manifest_input: AppBlueprintManifest | Dict[str, Any]) -> Dict[str, Any]:
        manifest = manifest_input if isinstance(manifest_input, AppBlueprintManifest) else AppBlueprintManifest.from_dict(manifest_input)
        errors: List[str] = []
        warnings: List[str] = []
        if not manifest.name.strip():
            errors.append('Manifest name is required.')
        if not manifest.destination.strip():
            errors.append('Manifest destination is required.')
        if manifest.vendor_mode not in VALID_VENDOR_MODES:
            errors.append(f'Unsupported vendor_mode: {manifest.vendor_mode}')
        if manifest.resolution_profile not in VALID_RESOLUTION_PROFILES:
            errors.append(f'Unsupported resolution_profile: {manifest.resolution_profile}')
        if manifest.ui_pack not in UI_PACKS and manifest.ui_pack not in SPECIAL_UI_PACKS:
            errors.append(f'Unsupported ui_pack: {manifest.ui_pack}')
        if not manifest.microservices and not manifest.modules:
            errors.append('Manifest must select at least one microservice or module.')
        unknown_services: List[str] = []
        unknown_modules: List[str] = []
        with self._connect() as conn:
            for identifier in manifest.microservices:
                if self._resolve_service_row(conn, identifier) is None:
                    unknown_services.append(str(identifier))
            for identifier in manifest.modules:
                if self._resolve_artifact_row(conn, identifier) is None:
                    unknown_modules.append(str(identifier))
        if unknown_services:
            errors.append('Unknown services: ' + ', '.join(sorted(unknown_services)))
        if unknown_modules:
            errors.append('Unknown modules: ' + ', '.join(sorted(unknown_modules)))
        if manifest.ui_pack == 'headless_pack' and any(str(layer).strip() == 'ui' for layer in manifest.manager_layers):
            warnings.append('Headless pack selected with ui manager layers.')
        return {
            'ok': not errors,
            'errors': errors,
            'warnings': warnings,
            'normalized_manifest': manifest.to_dict(),
        }

    def recommend_blueprint(self, selected_services: Iterable[str], destination: str='', name: str='', vendor_mode: str='module_ref', resolution_profile: str='app_ready') -> Dict[str, Any]:
        selected_ids = [str(item).strip() for item in selected_services if str(item).strip()]
        selected_rows: List[Dict[str, Any]] = []
        with self._connect() as conn:
            for identifier in selected_ids:
                row = self._resolve_service_row(conn, identifier)
                if row is not None:
                    selected_rows.append(self._service_row_to_dict(row))
        app_name = name.strip() or 'Stamped App'
        ui_selected = any(('ui' in service['tags']) or any(cap.startswith('ui:') for cap in service['capabilities']) for service in selected_rows)
        ui_pack = 'tkinter_base_pack' if ui_selected else 'headless_pack'
        orchestrator = 'tkinter_shell_orchestrator' if ui_selected else 'headless_backend_orchestrator'
        manager_layers = sorted({layer for layer, service_names in GROUPED_MANAGER_SERVICE_MAP.items() for service in selected_rows if service['class_name'] in service_names or service['service_name'] in service_names})
        manifest = AppBlueprintManifest(
            app_id=stable_id('app', app_name, vendor_mode, resolution_profile, '|'.join(sorted(service['class_name'] for service in selected_rows))),
            name=app_name,
            destination=destination,
            vendor_mode=vendor_mode,
            resolution_profile=resolution_profile,
            ui_pack=ui_pack,
            orchestrator=orchestrator,
            manager_layers=manager_layers,
            microservices=sorted({service['class_name'] for service in selected_rows}),
            modules=[],
            settings_defaults={'app_title': app_name, 'assistant_enabled': False},
            hooks={},
        )
        payload = manifest.to_dict()
        payload['selected_services'] = selected_rows
        return payload

    def _resolve_service_row(self, conn: sqlite3.Connection, identifier: str) -> Optional[sqlite3.Row]:
        target = str(identifier).strip()
        if not target:
            return None
        row = conn.execute(
            'SELECT s.*, a.import_key, a.source_path FROM services s JOIN artifacts a ON a.artifact_id = s.artifact_id WHERE s.service_id = ? OR s.class_name = ? OR s.service_name = ? OR a.import_key = ? ORDER BY s.class_name LIMIT 1',
            (target, target, target, target),
        ).fetchone()
        if row is not None:
            return row
        return conn.execute('SELECT s.*, a.import_key, a.source_path FROM services s JOIN artifacts a ON a.artifact_id = s.artifact_id WHERE a.source_path LIKE ? ORDER BY s.class_name LIMIT 1', (f'%\\{target}.py',)).fetchone()

    def _resolve_artifact_row(self, conn: sqlite3.Connection, identifier: str) -> Optional[sqlite3.Row]:
        target = str(identifier).strip()
        if not target:
            return None
        return conn.execute(
            'SELECT artifact_id, source_path, file_cid, import_key FROM artifacts WHERE is_deleted = 0 AND (import_key = ? OR source_path LIKE ? OR source_path LIKE ?) LIMIT 1',
            (target, f'%\\{target}.py', f'%\\{target}'),
        ).fetchone()

    def _service_row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        return {
            'service_id': row['service_id'],
            'artifact_id': row['artifact_id'],
            'class_name': row['class_name'],
            'service_name': row['service_name'],
            'version': row['version'],
            'layer': row['layer'],
            'description': row['description'],
            'tags': json.loads(row['tags_json']),
            'capabilities': json.loads(row['capabilities_json']),
            'side_effects': json.loads(row['side_effects_json']),
            'import_key': row['import_key'],
            'source_path': row['source_path'],
        }

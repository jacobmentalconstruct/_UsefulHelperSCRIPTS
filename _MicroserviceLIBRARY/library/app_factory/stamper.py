"""Manifest resolver and app stamper."""

from __future__ import annotations

import hashlib
import json
import os
import py_compile
import shutil
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import (
    DEFAULT_RUNTIME_COMPAT_DIRS,
    GROUPED_MANAGER_SERVICE_MAP,
    IGNORED_EXTERNAL_DEPENDENCIES,
    LIBRARY_ROOT,
    LOCAL_HELPER_MODULES,
    UI_PACKS,
    WORKSPACE_ROOT,
)
from .models import AppBlueprintManifest, ResolvedArtifact, StamperValidationResult
from .query import LibraryQueryService
from .ui_schema import UiSchemaCommitService, UiSchemaPreviewService


class AppStamper:
    def __init__(self, query_service: Optional[LibraryQueryService]=None):
        self.query_service = query_service or LibraryQueryService()
        self.ui_preview = UiSchemaPreviewService()
        self.ui_commit = UiSchemaCommitService()
        self.library_root = Path(LIBRARY_ROOT).resolve()
        self.workspace_root = Path(WORKSPACE_ROOT).resolve()

    def stamp(self, manifest_input: AppBlueprintManifest | Dict[str, Any], ui_schema_override: Optional[Dict[str, Any]]=None) -> Dict[str, Any]:
        manifest = manifest_input if isinstance(manifest_input, AppBlueprintManifest) else AppBlueprintManifest.from_dict(manifest_input)
        self.query_service.build_catalog()
        manifest_validation = self.query_service.validate_manifest(manifest)
        if not manifest_validation['ok']:
            validation = StamperValidationResult(errors=list(manifest_validation['errors']), warnings=list(manifest_validation['warnings']))
            return {
                'app_dir': str(Path(manifest.destination).resolve()) if manifest.destination else '',
                'written_files': [],
                'validation': validation.to_dict(),
                'external_dependencies': [],
                'resolved_artifacts': [],
                'lockfile_path': '',
                'manifest_validation': manifest_validation,
            }
        resolved = self._resolve_manifest(manifest)
        app_dir = Path(manifest.destination).resolve()
        app_dir.mkdir(parents=True, exist_ok=True)
        self._cleanup_previous_stamp(app_dir, manifest.vendor_mode)
        written_files: List[str] = []
        if manifest.vendor_mode == 'static' and resolved['validation'].ok():
            written_files.extend(self._copy_static_vendor_tree(app_dir, resolved))
        settings_path = app_dir / 'settings.json'
        manifest_path = app_dir / 'app_manifest.json'
        requirements_path = app_dir / 'requirements.txt'
        pyright_path = app_dir / 'pyrightconfig.json'
        env_path = app_dir / '.env'
        settings_payload = self._build_settings_payload(manifest, resolved, app_dir)
        settings_payload = self._merge_existing_settings(app_dir, settings_payload)
        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2), encoding='utf-8')
        settings_path.write_text(json.dumps(settings_payload, indent=2), encoding='utf-8')
        requirements_path.write_text('\n'.join(sorted(resolved['external_dependencies'])) + ('\n' if resolved['external_dependencies'] else ''), encoding='utf-8')
        pyright_path.write_text(json.dumps({'extraPaths': settings_payload['compat_paths']}, indent=2), encoding='utf-8')
        env_path.write_text('PYTHONPATH=' + os.pathsep.join(settings_payload['compat_paths']) + '\n', encoding='utf-8')
        written_files.extend([str(manifest_path), str(settings_path), str(requirements_path), str(pyright_path), str(env_path)])
        (app_dir / 'backend.py').write_text(self._build_backend_py(manifest, resolved), encoding='utf-8')
        (app_dir / 'ui.py').write_text(self._build_ui_py(manifest, resolved), encoding='utf-8')
        (app_dir / 'app.py').write_text(self._build_app_py(), encoding='utf-8')
        written_files.extend([str(app_dir / 'backend.py'), str(app_dir / 'ui.py'), str(app_dir / 'app.py')])
        schema = ui_schema_override if ui_schema_override is not None else self.ui_preview.default_schema(manifest.ui_pack)
        self.ui_commit.commit(schema, app_dir)
        written_files.append(str(app_dir / 'ui_schema.json'))
        compile_results = self._compile_tree(app_dir)
        resolved['validation'].compile_results = compile_results
        if resolved['validation'].ok() and compile_results.get('errors'):
            resolved['validation'].errors.extend(compile_results['errors'])
        lock_path = None
        if resolved['validation'].ok():
            lock_path = app_dir / '.stamper_lock.json'
            lock_path.write_text(json.dumps(self._build_lockfile(manifest, resolved, app_dir), indent=2), encoding='utf-8')
            written_files.append(str(lock_path))
        return {
            'app_dir': str(app_dir),
            'written_files': written_files,
            'validation': resolved['validation'].to_dict(),
            'external_dependencies': sorted(resolved['external_dependencies']),
            'resolved_artifacts': [artifact.to_dict() for artifact in resolved['resolved_artifacts'].values()],
            'lockfile_path': str(lock_path) if lock_path else '',
            'manifest_validation': manifest_validation,
        }

    def load_app_manifest(self, app_dir: Path | str) -> Dict[str, Any]:
        app_dir = Path(app_dir).resolve()
        manifest_path = app_dir / 'app_manifest.json'
        if not manifest_path.exists():
            raise FileNotFoundError(manifest_path)
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        return AppBlueprintManifest.from_dict(payload).to_dict()

    def inspect_app(self, app_dir: Path | str) -> Dict[str, Any]:
        app_dir = Path(app_dir).resolve()
        manifest_path = app_dir / 'app_manifest.json'
        lock_path = app_dir / '.stamper_lock.json'
        schema_path = app_dir / 'ui_schema.json'
        errors: List[str] = []
        warnings: List[str] = []
        manifest_payload: Dict[str, Any] = {}
        manifest_validation: Dict[str, Any] = {'ok': False, 'errors': [], 'warnings': []}
        current_manifest_hash = ''
        if manifest_path.exists():
            try:
                manifest_payload = AppBlueprintManifest.from_dict(
                    json.loads(manifest_path.read_text(encoding='utf-8'))
                ).to_dict()
                manifest_validation = self.query_service.validate_manifest(manifest_payload)
                current_manifest_hash = hashlib.sha256(
                    json.dumps(manifest_payload, sort_keys=True).encode('utf-8')
                ).hexdigest()
            except Exception as exc:
                errors.append(f'Failed to read manifest: {exc}')
        else:
            errors.append(f'Missing app manifest: {manifest_path}')
        lock: Dict[str, Any] = {}
        if lock_path.exists():
            try:
                lock = json.loads(lock_path.read_text(encoding='utf-8'))
            except Exception as exc:
                errors.append(f'Failed to read lockfile: {exc}')
        else:
            errors.append(f'Missing lockfile: {lock_path}')
        integrity = self.verify_app_integrity(app_dir)
        lock_inspection = self._inspect_lock_entries(lock) if lock else self._empty_lock_inspection()
        latest_catalog_build_id = self.query_service.latest_catalog_build_id()
        locked_build_id = str(lock.get('catalog_build_id', '')).strip()
        manifest_hash_matches_lock = None
        if current_manifest_hash and lock:
            manifest_hash_matches_lock = current_manifest_hash == str(lock.get('locked_blueprint_hash', '')).strip()
            if manifest_hash_matches_lock is False:
                warnings.append('app_manifest.json differs from the lockfile blueprint hash.')
        ui_schema_snapshot_matches = None
        if schema_path.exists() and lock:
            snapshot_hash = str(lock.get('ui_schema_snapshot_hash', '')).strip()
            if snapshot_hash:
                ui_schema_snapshot_matches = self._hash_file(schema_path) == snapshot_hash
        restamp_recommended = bool(
            errors
            or not manifest_validation.get('ok', False)
            or not integrity.get('ok', False)
            or manifest_hash_matches_lock is False
            or lock_inspection['missing_library_artifacts']
            or lock_inspection['library_artifact_drift']
        )
        return {
            'app_dir': str(app_dir),
            'manifest_path': str(manifest_path),
            'lockfile_path': str(lock_path),
            'ui_schema_path': str(schema_path),
            'manifest_exists': manifest_path.exists(),
            'lockfile_exists': lock_path.exists(),
            'ui_schema_exists': schema_path.exists(),
            'manifest': manifest_payload,
            'manifest_validation': manifest_validation,
            'current_manifest_hash': current_manifest_hash,
            'locked_blueprint_hash': lock.get('locked_blueprint_hash', ''),
            'manifest_hash_matches_lock': manifest_hash_matches_lock,
            'integrity': integrity,
            'catalog_build_id_current': latest_catalog_build_id,
            'catalog_build_id_locked': locked_build_id,
            'catalog_build_changed': bool(locked_build_id and latest_catalog_build_id and locked_build_id != latest_catalog_build_id),
            'ui_schema_snapshot_matches': ui_schema_snapshot_matches,
            'lock_inspection': lock_inspection,
            'warnings': warnings + list(manifest_validation.get('warnings', [])),
            'errors': errors + list(manifest_validation.get('errors', [])),
            'restamp_recommended': restamp_recommended,
        }

    def upgrade_report(self, app_dir: Path | str) -> Dict[str, Any]:
        self.query_service.build_catalog()
        app_dir = Path(app_dir).resolve()
        inspection = self.inspect_app(app_dir)
        report = {
            'app_dir': str(app_dir),
            'inspection': inspection,
            'artifact_changes': {
                'added': [],
                'removed': [],
                'changed': [],
                'unchanged': [],
            },
            'external_dependency_changes': {
                'added': [],
                'removed': [],
                'unchanged': [],
            },
            'current_resolution_validation': {'ok': False, 'errors': [], 'warnings': []},
            'upgrade_recommended': bool(inspection.get('restamp_recommended')),
        }
        if inspection['errors'] or not inspection.get('manifest'):
            return report
        manifest = AppBlueprintManifest.from_dict(inspection['manifest'])
        manifest_validation = self.query_service.validate_manifest(manifest)
        report['current_resolution_validation'] = manifest_validation
        if not manifest_validation['ok']:
            report['upgrade_recommended'] = True
            return report
        current_resolution = self._resolve_manifest(manifest)
        report['current_resolution_validation'] = current_resolution['validation'].to_dict()
        lock_path = app_dir / '.stamper_lock.json'
        lock = json.loads(lock_path.read_text(encoding='utf-8')) if lock_path.exists() else {}
        locked_artifacts = lock.get('resolved_library_artifacts', [])
        current_artifacts = [artifact.to_dict() for artifact in current_resolution['resolved_artifacts'].values()]
        locked_map = {self._artifact_diff_key(entry): entry for entry in locked_artifacts}
        current_map = {self._artifact_diff_key(entry): entry for entry in current_artifacts}

        all_keys = sorted(set(locked_map) | set(current_map))
        for key in all_keys:
            locked_entry = locked_map.get(key)
            current_entry = current_map.get(key)
            if locked_entry and not current_entry:
                report['artifact_changes']['removed'].append(locked_entry)
                continue
            if current_entry and not locked_entry:
                report['artifact_changes']['added'].append(current_entry)
                continue
            if not locked_entry or not current_entry:
                continue
            if locked_entry.get('file_cid') != current_entry.get('file_cid'):
                report['artifact_changes']['changed'].append({
                    'artifact_id': current_entry.get('artifact_id') or locked_entry.get('artifact_id', ''),
                    'source_path': current_entry.get('source_path') or locked_entry.get('source_path', ''),
                    'old_file_cid': locked_entry.get('file_cid', ''),
                    'new_file_cid': current_entry.get('file_cid', ''),
                    'materialization_mode': current_entry.get('materialization_mode', ''),
                })
            else:
                report['artifact_changes']['unchanged'].append(current_entry)

        locked_external = sorted(set(lock.get('external_dependencies', [])))
        current_external = sorted(current_resolution['external_dependencies'])
        locked_external_set = set(locked_external)
        current_external_set = set(current_external)
        report['external_dependency_changes'] = {
            'added': sorted(current_external_set - locked_external_set),
            'removed': sorted(locked_external_set - current_external_set),
            'unchanged': sorted(locked_external_set & current_external_set),
        }
        report['upgrade_recommended'] = bool(
            inspection.get('restamp_recommended')
            or report['artifact_changes']['added']
            or report['artifact_changes']['removed']
            or report['artifact_changes']['changed']
            or report['external_dependency_changes']['added']
            or report['external_dependency_changes']['removed']
            or not current_resolution['validation'].ok()
        )
        return report

    def restamp_existing_app(
        self,
        app_dir: Path | str,
        destination: Optional[str]=None,
        name: Optional[str]=None,
        vendor_mode: Optional[str]=None,
        resolution_profile: Optional[str]=None,
        preserve_ui_schema: bool=True,
    ) -> Dict[str, Any]:
        app_dir = Path(app_dir).resolve()
        manifest_payload = self.load_app_manifest(app_dir)
        manifest_payload['destination'] = destination or str(app_dir)
        if name is not None:
            manifest_payload['name'] = name
        if vendor_mode is not None:
            manifest_payload['vendor_mode'] = vendor_mode
        if resolution_profile is not None:
            manifest_payload['resolution_profile'] = resolution_profile
        schema_override = None
        schema_path = app_dir / 'ui_schema.json'
        if preserve_ui_schema and schema_path.exists():
            try:
                schema_override = json.loads(schema_path.read_text(encoding='utf-8'))
            except Exception:
                schema_override = None
        report = self.stamp(manifest_payload, ui_schema_override=schema_override)
        report['restamped_from'] = str(app_dir)
        report['preserved_ui_schema'] = bool(schema_override is not None)
        return report

    def verify_app_integrity(self, app_dir: Path) -> Dict[str, Any]:
        app_dir = Path(app_dir).resolve()
        lock_path = app_dir / '.stamper_lock.json'
        if not lock_path.exists():
            return {'ok': False, 'errors': ['Missing .stamper_lock.json'], 'checked': []}
        lock = json.loads(lock_path.read_text(encoding='utf-8'))
        inspection = self._inspect_lock_entries(lock)
        return {'ok': not inspection['errors'], **inspection}

    def _cleanup_previous_stamp(self, app_dir: Path, vendor_mode: str) -> None:
        lock_path = app_dir / '.stamper_lock.json'
        if lock_path.exists():
            lock_path.unlink()
        vendor_root = app_dir / 'vendor'
        if vendor_root.exists() and vendor_root.is_dir():
            shutil.rmtree(vendor_root)

    def _empty_lock_inspection(self) -> Dict[str, Any]:
        return {
            'checked': [],
            'errors': [],
            'missing_generated_python_files': [],
            'generated_python_file_drift': [],
            'missing_generated_support_files': [],
            'generated_support_file_drift': [],
            'missing_library_artifacts': [],
            'library_artifact_drift': [],
        }

    def _inspect_lock_entries(self, lock: Dict[str, Any]) -> Dict[str, Any]:
        inspection = self._empty_lock_inspection()
        for entry in lock.get('generated_python_files', []):
            file_path = Path(entry['path'])
            inspection['checked'].append(str(file_path))
            if not file_path.exists():
                inspection['missing_generated_python_files'].append(str(file_path))
                inspection['errors'].append(f'Missing generated file: {file_path}')
                continue
            if self._hash_file(file_path) != entry['sha256']:
                inspection['generated_python_file_drift'].append(str(file_path))
                inspection['errors'].append(f'Generated file drift: {file_path}')
        for entry in lock.get('generated_support_files', []):
            file_path = Path(entry['path'])
            inspection['checked'].append(str(file_path))
            if not file_path.exists():
                inspection['missing_generated_support_files'].append(str(file_path))
                inspection['errors'].append(f'Missing generated support file: {file_path}')
                continue
            if self._hash_file(file_path) != entry['sha256']:
                inspection['generated_support_file_drift'].append(str(file_path))
                inspection['errors'].append(f'Generated support file drift: {file_path}')
        for entry in lock.get('resolved_library_artifacts', []):
            target = Path(entry['target_path']) if entry.get('materialization_mode') == 'static' else Path(entry['source_path'])
            inspection['checked'].append(str(target))
            if not target.exists():
                inspection['missing_library_artifacts'].append(str(target))
                inspection['errors'].append(f'Missing library artifact: {target}')
                continue
            if self._hash_file(target) != entry['file_cid']:
                inspection['library_artifact_drift'].append(str(target))
                inspection['errors'].append(f'Library artifact drift: {target}')
        return inspection

    def _artifact_diff_key(self, entry: Dict[str, Any]) -> str:
        artifact_id = str(entry.get('artifact_id', '')).strip()
        if artifact_id:
            return artifact_id
        return str(entry.get('source_path', '')).strip()

    def _resolve_manifest(self, manifest: AppBlueprintManifest) -> Dict[str, Any]:
        validation = StamperValidationResult()
        resolved_services: Dict[str, Dict[str, Any]] = {}
        resolved_artifacts: Dict[str, ResolvedArtifact] = {}
        external_dependencies: set[str] = set()
        with self.query_service._connect() as conn:
            for identifier in manifest.microservices:
                row = self.query_service._resolve_service_row(conn, identifier)
                if row is None:
                    validation.errors.append(f'Unknown service selection: {identifier}')
                    continue
                self._resolve_service(conn, row['service_id'], manifest, resolved_services, resolved_artifacts, external_dependencies, validation, [])
            for module_identifier in manifest.modules:
                self._resolve_artifact_by_identifier(conn, module_identifier, resolved_services, resolved_artifacts, validation)
            if manifest.ui_pack in UI_PACKS and manifest.ui_pack != 'headless_pack':
                for pack_service in UI_PACKS[manifest.ui_pack]['services']:
                    row = self.query_service._resolve_service_row(conn, pack_service['class_name'])
                    if row is not None:
                        self._resolve_service(conn, row['service_id'], manifest, resolved_services, resolved_artifacts, external_dependencies, validation, [])
        return {
            'resolved_services': resolved_services,
            'resolved_artifacts': resolved_artifacts,
            'external_dependencies': external_dependencies,
            'validation': validation,
        }

    def _resolve_service(self, conn: sqlite3.Connection, service_id: str, manifest: AppBlueprintManifest, resolved_services: Dict[str, Dict[str, Any]], resolved_artifacts: Dict[str, ResolvedArtifact], external_dependencies: set[str], validation: StamperValidationResult, active_path: List[str]) -> None:
        if service_id in active_path:
            validation.cycle_warnings.append(' -> '.join(active_path + [service_id]))
            return
        if service_id in resolved_services:
            return
        row = conn.execute('SELECT s.*, a.import_key, a.source_path, a.file_cid FROM services s JOIN artifacts a ON a.artifact_id = s.artifact_id WHERE s.service_id = ?', (service_id,)).fetchone()
        if row is None:
            validation.errors.append(f'Unknown service id: {service_id}')
            return
        payload = self.query_service._service_row_to_dict(row)
        endpoints = conn.execute('SELECT method_name, inputs_json, outputs_json, description, tags_json, mode FROM endpoints WHERE service_id = ? ORDER BY method_name', (service_id,)).fetchall()
        payload['endpoints'] = [dict(item) for item in endpoints]
        payload['manager_layer'] = next(
            (
                layer
                for layer, names in GROUPED_MANAGER_SERVICE_MAP.items()
                if payload['class_name'] in names or payload['service_name'] in names
            ),
            '',
        )
        resolved_services[service_id] = payload
        self._add_resolved_artifact(resolved_artifacts, row['artifact_id'], row['source_path'], row['file_cid'], row['import_key'], manifest.vendor_mode, row['class_name'], row['service_name'])
        active_path.append(service_id)
        dep_rows = conn.execute('SELECT * FROM dependencies WHERE src_service_id = ? OR src_artifact_id = ?', (service_id, row['artifact_id'])).fetchall()
        for dep in dep_rows:
            dep_type = dep['dependency_type']
            if dep_type == 'requires_external' and dep['external_name']:
                normalized = self._normalize_external_dependency(dep['external_name'])
                if normalized:
                    external_dependencies.add(normalized)
                continue
            if dep_type in {'packaged_with', 'requires_runtime', 'hosted_by'} and manifest.resolution_profile != 'app_ready':
                continue
            if dep['pack_name']:
                for pack_service in UI_PACKS.get(dep['pack_name'], {}).get('services', []):
                    target = self.query_service._resolve_service_row(conn, pack_service['class_name'])
                    if target is not None:
                        self._resolve_service(conn, target['service_id'], manifest, resolved_services, resolved_artifacts, external_dependencies, validation, active_path)
                continue
            if dep['dst_service_id']:
                self._resolve_service(conn, dep['dst_service_id'], manifest, resolved_services, resolved_artifacts, external_dependencies, validation, active_path)
                continue
            if dep['dst_artifact_id']:
                self._resolve_artifact(conn, dep['dst_artifact_id'], manifest, resolved_services, resolved_artifacts, external_dependencies, validation, active_path)
                continue
            if dep_type == 'requires_code':
                ref = json.loads(dep['evidence_json']).get('ref', '')
                validation.missing_dependencies.append(f'Unresolved code dependency for {row["class_name"]}: {ref}')
        active_path.pop()

    def _resolve_artifact(self, conn: sqlite3.Connection, artifact_id: str, manifest: AppBlueprintManifest, resolved_services: Dict[str, Dict[str, Any]], resolved_artifacts: Dict[str, ResolvedArtifact], external_dependencies: set[str], validation: StamperValidationResult, active_path: List[str]) -> None:
        row = conn.execute('SELECT artifact_id, source_path, file_cid, import_key FROM artifacts WHERE artifact_id = ?', (artifact_id,)).fetchone()
        if row is None:
            validation.errors.append(f'Unknown artifact id: {artifact_id}')
            return
        self._add_resolved_artifact(resolved_artifacts, row['artifact_id'], row['source_path'], row['file_cid'], row['import_key'], manifest.vendor_mode, '', '')
        service_rows = conn.execute('SELECT service_id FROM services WHERE artifact_id = ? ORDER BY class_name', (artifact_id,)).fetchall()
        if len(service_rows) == 1:
            self._resolve_service(conn, service_rows[0]['service_id'], manifest, resolved_services, resolved_artifacts, external_dependencies, validation, active_path)

    def _resolve_artifact_by_identifier(self, conn: sqlite3.Connection, identifier: str, resolved_services: Dict[str, Dict[str, Any]], resolved_artifacts: Dict[str, ResolvedArtifact], validation: StamperValidationResult) -> None:
        target = str(identifier).strip()
        if not target:
            return
        row = conn.execute('SELECT artifact_id, source_path, file_cid, import_key FROM artifacts WHERE import_key = ? OR source_path LIKE ? OR source_path LIKE ? LIMIT 1', (target, f'%\\{target}.py', f'%\\{target}')).fetchone()
        if row is None:
            validation.errors.append(f'Unknown module selection: {identifier}')
            return
        self._add_resolved_artifact(resolved_artifacts, row['artifact_id'], row['source_path'], row['file_cid'], row['import_key'], 'static', '', '')

    def _add_resolved_artifact(self, resolved_artifacts: Dict[str, ResolvedArtifact], artifact_id: str, source_path: str, file_cid: str, import_key: str, materialization_mode: str, class_name: str, service_name: str) -> None:
        if artifact_id in resolved_artifacts:
            return
        resolved_artifacts[artifact_id] = ResolvedArtifact(artifact_id=artifact_id, source_path=source_path, target_path='', file_cid=file_cid, materialization_mode=materialization_mode, import_key=import_key, class_name=class_name, service_name=service_name)

    def _copy_static_vendor_tree(self, app_dir: Path, resolved: Dict[str, Any]) -> List[str]:
        vendor_root = app_dir / 'vendor'
        written: List[str] = []
        support_files = self._required_static_support_files(resolved)
        all_sources = support_files + [Path(item.source_path) for item in resolved['resolved_artifacts'].values()]
        seen: set[str] = set()
        for source in all_sources:
            if not source.exists() or str(source) in seen:
                continue
            seen.add(str(source))
            relative = source.relative_to(self.workspace_root)
            target = vendor_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            written.append(str(target))
            if source.suffix == '.py' and str(source).startswith(str(self.library_root)):
                for parent in source.parents:
                    if parent == self.workspace_root or parent == self.workspace_root.parent:
                        break
                    init_file = parent / '__init__.py'
                    if init_file.exists() and str(init_file) not in seen:
                        seen.add(str(init_file))
                        rel_init = init_file.relative_to(self.workspace_root)
                        target_init = vendor_root / rel_init
                        target_init.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(init_file, target_init)
                        written.append(str(target_init))
        for artifact in resolved['resolved_artifacts'].values():
            relative = Path(artifact.source_path).relative_to(self.workspace_root)
            artifact.target_path = str((vendor_root / relative).resolve())
            artifact.materialization_mode = 'static'
        return written

    def _required_static_support_files(self, resolved: Dict[str, Any]) -> List[Path]:
        files = [self.library_root / '__init__.py', self.library_root / 'microservice_std_lib.py', self.library_root / 'base_service.py', self.library_root / 'document_utils.py']
        if any(service['layer'] == 'grouped' or service['class_name'] in {'Blake3HashMS', 'MerkleRootMS', 'VerbatimStoreMS', 'TemporalChainMS', 'DagOpsMS', 'IntervalIndexMS', 'DirectedFlowMS', 'SemanticSearchMS', 'LexicalIndexMS', 'OntologyMS', 'PropertyGraphMS', 'IdentityAnchorMS', 'LayerHealthMS', 'WalkerTraceMS', 'CrossLayerResolverMS', 'ManifoldProjectorMS', 'HypergraphMS'} for service in resolved['resolved_services'].values()):
            files.extend([
                self.library_root / 'managers' / '__init__.py',
                self.library_root / 'managers' / 'managers.py',
                self.library_root / 'orchestrators' / '__init__.py',
                self.library_root / 'orchestrators' / 'layer_hub.py',
                self.library_root / 'orchestrators' / 'microservice_std_lib_registry.py',
                self.library_root / 'microservices' / 'grouped' / 'storage_group.py',
                self.library_root / 'microservices' / 'grouped' / 'structure_group.py',
                self.library_root / 'microservices' / 'grouped' / 'meaning_relation_observability_manifold_groups.py',
            ])
        return [path for path in files if path.exists()]

    def _build_settings_payload(self, manifest: AppBlueprintManifest, resolved: Dict[str, Any], app_dir: Path) -> Dict[str, Any]:
        if manifest.vendor_mode == 'static':
            canonical_import_root = str((app_dir / 'vendor').resolve())
            compat_paths = [canonical_import_root]
            compat_paths.extend(str(path.resolve()) for path in (app_dir / 'vendor' / 'library', app_dir / 'vendor' / 'library' / 'managers', app_dir / 'vendor' / 'library' / 'orchestrators') if path.exists())
            compat_paths.extend(str(path.parent.resolve()) for path in (Path(item.target_path) for item in resolved['resolved_artifacts'].values()) if path.parent.exists())
        else:
            canonical_import_root = str(self.workspace_root)
            compat_paths = [str(self.workspace_root), str(self.library_root)]
            compat_paths.extend(str(path.resolve()) for path in DEFAULT_RUNTIME_COMPAT_DIRS if path.exists())
            compat_paths.extend(str(Path(item.source_path).parent.resolve()) for item in resolved['resolved_artifacts'].values())
        deduped: List[str] = []
        for item in compat_paths:
            if item not in deduped:
                deduped.append(item)
        return {
            'canonical_import_root': canonical_import_root,
            'compat_paths': deduped,
            'catalog_db_path': str(self.query_service.catalog_db_path),
            'vendor_mode': manifest.vendor_mode,
            'ui_pack': manifest.ui_pack,
            'app_title': manifest.settings_defaults.get('app_title', manifest.name),
            'assistant': {'enabled': False, 'provider': 'ollama', 'model_name': '', 'size_cap_b': 4.0},
        }

    def _merge_existing_settings(self, app_dir: Path, generated_settings: Dict[str, Any]) -> Dict[str, Any]:
        settings_path = app_dir / 'settings.json'
        if not settings_path.exists():
            return generated_settings
        try:
            existing = json.loads(settings_path.read_text(encoding='utf-8'))
        except Exception:
            return generated_settings
        if not isinstance(existing, dict):
            return generated_settings
        merged = dict(generated_settings)
        managed_keys = set(generated_settings.keys())
        for key, value in existing.items():
            if key not in managed_keys:
                merged[key] = value
        existing_assistant = existing.get('assistant', {})
        if isinstance(existing_assistant, dict):
            assistant = dict(generated_settings.get('assistant', {}))
            assistant.update(existing_assistant)
            merged['assistant'] = assistant
        return merged

    def _hash_file(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _normalize_external_dependency(self, dependency_name: str) -> str:
        candidate = str(dependency_name).strip()
        if not candidate:
            return ''
        root_name = candidate.split('.')[0]
        if candidate.startswith('library.') or candidate.startswith('_'):
            return ''
        if candidate in LOCAL_HELPER_MODULES or root_name in LOCAL_HELPER_MODULES:
            return ''
        if candidate in IGNORED_EXTERNAL_DEPENDENCIES or root_name in IGNORED_EXTERNAL_DEPENDENCIES:
            return ''
        stdlib_names = getattr(sys, 'stdlib_module_names', set())
        if candidate in stdlib_names or root_name in stdlib_names:
            return ''
        return candidate

    def _compile_tree(self, app_dir: Path) -> Dict[str, Any]:
        compiled: List[str] = []
        errors: List[str] = []
        for path in app_dir.rglob('*.py'):
            try:
                py_compile.compile(str(path), doraise=True)
                compiled.append(str(path))
            except Exception as exc:
                errors.append(f'{path}: {exc}')
        return {'compiled': compiled, 'errors': errors}

    def _build_lockfile(self, manifest: AppBlueprintManifest, resolved: Dict[str, Any], app_dir: Path) -> Dict[str, Any]:
        generated_python_files = []
        for name in ('app.py', 'backend.py', 'ui.py'):
            path = app_dir / name
            generated_python_files.append({'path': str(path), 'sha256': self._hash_file(path)})
        generated_support_files = []
        for name in ('requirements.txt', 'pyrightconfig.json', '.env'):
            path = app_dir / name
            if path.exists():
                generated_support_files.append({'path': str(path), 'sha256': self._hash_file(path)})
        schema_path = app_dir / 'ui_schema.json'
        return {
            'locked_blueprint_hash': hashlib.sha256(json.dumps(manifest.to_dict(), sort_keys=True).encode('utf-8')).hexdigest(),
            'catalog_build_id': self.query_service.latest_catalog_build_id(),
            'vendor_mode': manifest.vendor_mode,
            'resolved_library_artifacts': [artifact.to_dict() for artifact in resolved['resolved_artifacts'].values()],
            'generated_python_files': generated_python_files,
            'generated_support_files': generated_support_files,
            'external_dependencies': sorted(resolved['external_dependencies']),
            'integrity_scope': {
                'included': ['generated_python_files', 'generated_support_files', 'resolved_library_artifacts'],
                'excluded': ['ui_schema.json', 'settings.json'],
            },
            'ui_schema_snapshot_hash': self._hash_file(schema_path) if schema_path.exists() else '',
        }

    def _build_app_py(self) -> str:
        return '''import argparse\nimport json\nimport os\nimport sys\nfrom pathlib import Path\n\n\ndef _bootstrap():\n    app_dir = Path(__file__).resolve().parent\n    settings = json.loads((app_dir / "settings.json").read_text(encoding="utf-8"))\n    paths = [settings.get("canonical_import_root", "")] + list(settings.get("compat_paths", []))\n    for candidate in paths:\n        if candidate and candidate not in sys.path:\n            sys.path.insert(0, candidate)\n    return settings\n\n\nSETTINGS = _bootstrap()\n\nfrom backend import BackendRuntime\nfrom ui import launch_ui, run_headless\n\n\ndef main(argv=None):\n    parser = argparse.ArgumentParser(description="Stamped app entry point")\n    parser.add_argument("--health", action="store_true", help="Print health JSON and exit")\n    parser.add_argument("--no-ui", action="store_true", help="Run without launching the Tkinter UI")\n    args = parser.parse_args(argv)\n    runtime = BackendRuntime()\n    if args.health:\n        print(json.dumps(runtime.health(), indent=2))\n        return 0\n    if args.no_ui or SETTINGS.get("ui_pack") == "headless_pack":\n        print(json.dumps(run_headless(runtime), indent=2))\n        return 0\n    launch_ui(runtime)\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'''

    def _build_backend_py(self, manifest: AppBlueprintManifest, resolved: Dict[str, Any]) -> str:
        specs: List[Dict[str, Any]] = []
        for service in sorted(resolved['resolved_services'].values(), key=lambda item: item['class_name']):
            manager_layer = ''
            for layer, service_names in GROUPED_MANAGER_SERVICE_MAP.items():
                if service['class_name'] in service_names or service['service_name'] in service_names:
                    manager_layer = layer
                    break
            specs.append({
                'service_id': service['service_id'],
                'class_name': service['class_name'],
                'service_name': service['service_name'],
                'module_import': service['import_key'],
                'description': service['description'],
                'tags': service['tags'],
                'capabilities': service['capabilities'],
                'manager_layer': manager_layer,
                'registry_name': service['service_name'],
                'is_ui': ('ui' in service['tags']) or any(cap.startswith('ui:') for cap in service['capabilities']),
                'endpoints': service['endpoints'],
            })
        return 'import importlib\nimport json\nfrom pathlib import Path\n\nSERVICE_SPECS = ' + repr(specs) + '\n\nclass BackendRuntime:\n    def __init__(self):\n        self.app_dir = Path(__file__).resolve().parent\n        self.settings = json.loads((self.app_dir / "settings.json").read_text(encoding="utf-8"))\n        self._instances = {}\n        self._hub = None\n        self._hub_error = ""\n        if any(spec.get("manager_layer") for spec in SERVICE_SPECS):\n            try:\n                from library.orchestrators import LayerHub\n                self._hub = LayerHub()\n            except Exception as exc:\n                self._hub_error = str(exc)\n\n    def list_services(self):\n        return list(SERVICE_SPECS)\n\n    def _find_spec(self, name):\n        target = str(name).strip()\n        for spec in SERVICE_SPECS:\n            if target in {spec["class_name"], spec["service_name"], spec["service_id"]}:\n                return spec\n        return None\n\n    def get_service(self, name, config=None):\n        spec = self._find_spec(name)\n        if spec is None:\n            raise KeyError(name)\n        cache_key = spec["class_name"]\n        if config is None and cache_key in self._instances:\n            return self._instances[cache_key]\n        if spec.get("manager_layer") and self._hub is not None:\n            manager = self._hub.get_manager(spec["manager_layer"])\n            if manager is not None:\n                service = manager.get(spec["registry_name"]) or manager.get(spec["class_name"])\n                if service is not None:\n                    self._instances[cache_key] = service\n                    return service\n        module = importlib.import_module(spec["module_import"])\n        cls = getattr(module, spec["class_name"])\n        try:\n            instance = cls(config or {})\n        except TypeError:\n            instance = cls()\n        if config is None:\n            self._instances[cache_key] = instance\n        return instance\n\n    def call(self, service_name, endpoint, **kwargs):\n        service = self.get_service(service_name, config=kwargs.pop("_config", None))\n        fn = getattr(service, endpoint)\n        return fn(**kwargs)\n\n    def health(self):\n        report = {"instantiated": {}, "deferred": [], "manager_hub_error": self._hub_error}\n        for spec in SERVICE_SPECS:\n            if spec["class_name"] in self._instances:\n                service = self._instances[spec["class_name"]]\n                try:\n                    report["instantiated"][spec["class_name"]] = service.get_health()\n                except Exception as exc:\n                    report["instantiated"][spec["class_name"]] = {"status": "error", "error": str(exc)}\n            else:\n                report["deferred"].append(spec["class_name"])\n        return report\n\n    def shutdown(self):\n        for service in list(self._instances.values()):\n            closer = getattr(service, "shutdown", None)\n            if callable(closer):\n                closer()\n'

    def _build_ui_py(self, manifest: AppBlueprintManifest, resolved: Dict[str, Any]) -> str:
        return 'import json\nimport tkinter as tk\nfrom pathlib import Path\nfrom tkinter import messagebox, scrolledtext, ttk\n\nDEFAULT_THEME = {\n    "background": "#14181D",\n    "foreground": "#F3EEE7",\n    "accent": "#C9773B",\n    "accent_alt": "#2D7F86",\n    "panel_bg": "#10161E",\n    "terminal_bg": "#0A0F16",\n    "muted": "#8C97A6",\n    "border": "#334155",\n}\n\n\ndef _load_schema(app_dir):\n    schema_path = app_dir / "ui_schema.json"\n    if not schema_path.exists():\n        return {"layout": {"type": "panel", "id": "details", "weight": 1}, "theme": dict(DEFAULT_THEME)}\n    schema = json.loads(schema_path.read_text(encoding="utf-8"))\n    theme = dict(DEFAULT_THEME)\n    theme.update(schema.get("theme", {}))\n    schema["theme"] = theme\n    return schema\n\n\ndef _apply_theme(root, theme):\n    style = ttk.Style(root)\n    try:\n        style.theme_use("clam")\n    except Exception:\n        pass\n    background = theme.get("background", DEFAULT_THEME["background"])\n    foreground = theme.get("foreground", DEFAULT_THEME["foreground"])\n    accent = theme.get("accent", DEFAULT_THEME["accent"])\n    accent_alt = theme.get("accent_alt", DEFAULT_THEME["accent_alt"])\n    panel_bg = theme.get("panel_bg", DEFAULT_THEME["panel_bg"])\n    muted = theme.get("muted", DEFAULT_THEME["muted"])\n    border = theme.get("border", DEFAULT_THEME["border"])\n    root.configure(bg=background)\n    style.configure("TFrame", background=background)\n    style.configure("Panel.TFrame", background=panel_bg)\n    style.configure("TLabel", background=background, foreground=foreground)\n    style.configure("Panel.TLabel", background=panel_bg, foreground=foreground)\n    style.configure("Heading.TLabel", background=background, foreground=foreground, font=("Segoe UI Semibold", 11))\n    style.configure("Muted.TLabel", background=background, foreground=muted)\n    style.configure("TButton", background=panel_bg, foreground=foreground, bordercolor=border, padding=6)\n    style.map("TButton", background=[("active", accent_alt)], foreground=[("active", foreground)])\n    style.configure("Accent.TButton", background=accent, foreground=foreground, bordercolor=accent, padding=6)\n    style.map("Accent.TButton", background=[("active", "#D48B57")], foreground=[("active", foreground)])\n    style.configure("TLabelframe", background=background, foreground=foreground)\n    style.configure("TLabelframe.Label", background=background, foreground=foreground)\n    style.configure("TPanedwindow", background=background)\n    return theme\n\n\ndef _build_layout(parent, node, panels):\n    node_type = node.get("type", "panel")\n    if node_type == "panel":\n        frame = ttk.Frame(parent, padding=6, style="Panel.TFrame")\n        if isinstance(parent, ttk.PanedWindow):\n            parent.add(frame, weight=int(node.get("weight", 1)))\n        else:\n            frame.pack(fill="both", expand=True)\n        panels[node.get("id", "panel")] = frame\n        return frame\n    orient = tk.HORIZONTAL if node_type == "row" else tk.VERTICAL\n    pane = ttk.PanedWindow(parent, orient=orient)\n    if isinstance(parent, ttk.PanedWindow):\n        parent.add(pane, weight=int(node.get("weight", 1)))\n    else:\n        pane.pack(fill="both", expand=True)\n    for child in node.get("children", []) or []:\n        _build_layout(pane, child, panels)\n    return pane\n\n\ndef run_headless(runtime, settings=None):\n    return {\n        "status": "headless",\n        "health": runtime.health(),\n        "services": runtime.list_services(),\n        "app_title": (settings or {}).get("app_title", "Stamped App"),\n    }\n\n\ndef launch_ui(runtime):\n    app_dir = Path(__file__).resolve().parent\n    settings = json.loads((app_dir / "settings.json").read_text(encoding="utf-8"))\n    schema = _load_schema(app_dir)\n    root = tk.Tk()\n    theme = _apply_theme(root, schema.get("theme", dict(DEFAULT_THEME)))\n    panel_bg = theme.get("panel_bg", DEFAULT_THEME["panel_bg"])\n    foreground = theme.get("foreground", DEFAULT_THEME["foreground"])\n    accent = theme.get("accent", DEFAULT_THEME["accent"])\n    terminal_bg = theme.get("terminal_bg", DEFAULT_THEME["terminal_bg"])\n    border = theme.get("border", DEFAULT_THEME["border"])\n\n    root.title(settings.get("app_title", "Stamped App"))\n    root.geometry("1180x780")\n    panels = {}\n    _build_layout(root, schema.get("layout", {"type": "panel", "id": "details", "weight": 1}), panels)\n    services_panel = panels.get("services") or next(iter(panels.values()))\n    details_panel = panels.get("details") or services_panel\n    actions_panel = panels.get("actions") or details_panel\n\n    listbox = tk.Listbox(\n        services_panel,\n        bg=panel_bg,\n        fg=foreground,\n        selectbackground=accent,\n        selectforeground=foreground,\n        borderwidth=0,\n        relief="flat",\n        highlightthickness=1,\n        highlightbackground=border,\n        highlightcolor=accent,\n        activestyle="none",\n    )\n    listbox.pack(fill="both", expand=True)\n\n    ttk.Label(details_panel, text=settings.get("app_title", "Stamped App"), style="Heading.TLabel").pack(anchor="w")\n    ttk.Label(details_panel, text="Stamped with AppFoundry and driven by the selected service set.", style="Muted.TLabel").pack(anchor="w", pady=(0, 6))\n\n    details = scrolledtext.ScrolledText(\n        details_panel,\n        wrap="word",\n        bg=terminal_bg,\n        fg=foreground,\n        insertbackground=foreground,\n        selectbackground=accent,\n        selectforeground=foreground,\n        relief="flat",\n        borderwidth=0,\n    )\n    details.pack(fill="both", expand=True)\n\n    mount_frame = ttk.LabelFrame(details_panel, text="Mounted UI Service", padding=6)\n    mount_frame.pack(fill="both", expand=True, pady=(8, 0))\n\n    status_var = tk.StringVar(value="Ready.")\n    ttk.Label(actions_panel, textvariable=status_var, style="Panel.TLabel", wraplength=320, justify="left").pack(fill="x", pady=(0, 8))\n\n    specs = runtime.list_services()\n    for spec in specs:\n        listbox.insert(tk.END, spec["class_name"])\n\n    def set_status(message):\n        status_var.set(message)\n\n    def write_details(payload):\n        details.delete("1.0", tk.END)\n        if isinstance(payload, (dict, list)):\n            details.insert(tk.END, json.dumps(payload, indent=2))\n        else:\n            details.insert(tk.END, str(payload))\n\n    def selected_spec():\n        if not listbox.curselection():\n            return None\n        return specs[listbox.curselection()[0]]\n\n    def show_spec():\n        spec = selected_spec()\n        if spec is None:\n            return\n        write_details(spec)\n        set_status(f"Showing service metadata for {spec[\'class_name\']}.")\n\n    def show_health():\n        write_details(runtime.health())\n        set_status("Showing runtime health report.")\n\n    def mount_ui_service():\n        spec = selected_spec()\n        if spec is None:\n            return\n        if not spec.get("is_ui"):\n            messagebox.showinfo("Mount UI", f"{spec[\'class_name\']} is not tagged as a UI service.")\n            return\n        for child in mount_frame.winfo_children():\n            child.destroy()\n        try:\n            service = runtime.get_service(spec["class_name"], config={"parent": mount_frame})\n            packer = getattr(service, "pack", None)\n            if callable(packer):\n                service.pack(fill="both", expand=True)\n            else:\n                ttk.Label(mount_frame, text=f"Mounted {spec[\'class_name\']} (no pack method)").pack(fill="both", expand=True)\n            set_status(f"Mounted {spec[\'class_name\']} into the preview pane.")\n        except Exception as exc:\n            set_status("UI mount failed.")\n            messagebox.showerror("Mount UI", str(exc))\n\n    listbox.bind("<<ListboxSelect>>", lambda _event: show_spec())\n    if specs:\n        listbox.selection_set(0)\n        show_spec()\n\n    ttk.Button(actions_panel, text="Describe", style="Accent.TButton", command=show_spec).pack(fill="x", pady=4)\n    ttk.Button(actions_panel, text="Health", command=show_health).pack(fill="x", pady=4)\n    ttk.Button(actions_panel, text="Mount UI Service", command=mount_ui_service).pack(fill="x", pady=4)\n    ttk.Button(actions_panel, text="Quit", command=root.destroy).pack(fill="x", pady=4)\n    root.mainloop()\n'

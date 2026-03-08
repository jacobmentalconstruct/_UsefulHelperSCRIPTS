"""Static catalog builder for the canonical library package."""

from __future__ import annotations

import ast
import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import (
    APP_FACTORY_VERSION,
    DEFAULT_CATALOG_DB_PATH,
    DEFAULT_MAPPING_REPORT_PATH,
    LIBRARY_ROOT,
    LOCAL_HELPER_MODULES,
    PACK_SERVICE_CLASS_NAMES,
    UI_PACKS,
    WORKSPACE_ROOT,
)
from .models import CatalogBuildReport


@dataclass
class ParsedEndpoint:
    endpoint_id: str
    service_id: str
    method_name: str
    inputs_json: str
    outputs_json: str
    description: str
    tags_json: str
    mode: str


@dataclass
class ParsedService:
    service_id: str
    artifact_id: str
    class_name: str
    service_name: str
    version: str
    layer: str
    description: str
    tags: List[str] = field(default_factory=list)
    capabilities: List[str] = field(default_factory=list)
    side_effects: List[str] = field(default_factory=list)
    internal_dependencies: List[str] = field(default_factory=list)
    external_dependencies: List[str] = field(default_factory=list)
    endpoints: List[ParsedEndpoint] = field(default_factory=list)


@dataclass
class ParsedModule:
    artifact_id: str
    source_path: str
    relative_path: str
    import_key: str
    file_cid: str
    size_bytes: int
    mtime_ns: int
    layer: str
    imports: List[Dict[str, Any]] = field(default_factory=list)
    services: List[ParsedService] = field(default_factory=list)


def stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256('||'.join(parts).encode('utf-8')).hexdigest()[:24]
    return f'{prefix}_{digest}'


def hash_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def json_dumps(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True)


def decorator_name(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        return decorator_name(node.func)
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ''


def literal_value(node: Optional[ast.AST], default: Any=None) -> Any:
    if node is None:
        return default
    try:
        return ast.literal_eval(node)
    except Exception:
        return default


def resolve_value(node: Optional[ast.AST], symbols: Optional[Dict[str, Any]]=None, default: Any=None) -> Any:
    if node is None:
        return default
    symbols = symbols or {}
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return symbols.get(node.id, default)
    if isinstance(node, ast.List):
        return [resolve_value(item, symbols, default) for item in node.elts]
    if isinstance(node, ast.Tuple):
        return [resolve_value(item, symbols, default) for item in node.elts]
    if isinstance(node, ast.Set):
        return [resolve_value(item, symbols, default) for item in node.elts]
    if isinstance(node, ast.Dict):
        result: Dict[Any, Any] = {}
        for key, value in zip(node.keys, node.values):
            resolved_key = resolve_value(key, symbols, default)
            resolved_value = resolve_value(value, symbols, default)
            if resolved_key is not default:
                result[resolved_key] = resolved_value
        return result
    try:
        return ast.literal_eval(node)
    except Exception:
        return default


def module_import_key(path: Path, workspace_root: Path) -> str:
    relative = path.relative_to(workspace_root).with_suffix('')
    if relative.name == '__init__':
        return '.'.join(relative.parts[:-1])
    return '.'.join(relative.parts)


def resolve_relative_import(current_import_key: str, level: int, module_name: Optional[str]) -> str:
    base_parts = current_import_key.split('.')[:-1]
    if level <= 0:
        return module_name or ''
    cutoff = max(0, len(base_parts) - level + 1)
    target = base_parts[:cutoff]
    if module_name:
        target.extend(module_name.split('.'))
    return '.'.join(part for part in target if part)


def sanitize_text_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


class CatalogBuilder:
    def __init__(self, library_root: Path | None=None, catalog_db_path: Path | None=None, mapping_report_path: Path | None=None):
        self.library_root = Path(library_root or LIBRARY_ROOT).resolve()
        self.workspace_root = self.library_root.parent
        self.catalog_db_path = Path(catalog_db_path or DEFAULT_CATALOG_DB_PATH).resolve()
        self.mapping_report_path = Path(mapping_report_path or DEFAULT_MAPPING_REPORT_PATH).resolve()

    def build(self, incremental: bool=True) -> Dict[str, Any]:
        self.catalog_db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.catalog_db_path)
        conn.row_factory = sqlite3.Row
        try:
            self._ensure_schema(conn)
            build_id = stable_id('build', datetime.now(timezone.utc).isoformat(), APP_FACTORY_VERSION)
            self._insert_build_row(conn, build_id)
            for row in self._discover_package_artifacts():
                conn.execute(
                    'INSERT OR REPLACE INTO artifacts (artifact_id, parent_artifact_id, source_path, kind, import_key, file_cid, size_bytes, mtime_ns, is_deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)',
                    (row['artifact_id'], row['parent_artifact_id'], row['source_path'], row['kind'], row['import_key'], row['file_cid'], row['size_bytes'], row['mtime_ns']),
                )
            current_modules = self._discover_modules()
            existing_modules = {row['source_path']: dict(row) for row in conn.execute("SELECT artifact_id, source_path, file_cid FROM artifacts WHERE kind='module'")}
            current_paths = {module.source_path for module in current_modules}
            changed_count = 0
            unchanged_count = 0
            for parsed_module in current_modules:
                existing = existing_modules.get(parsed_module.source_path)
                if incremental and existing and existing['file_cid'] == parsed_module.file_cid:
                    unchanged_count += 1
                    continue
                changed_count += 1
                self._upsert_module(conn, parsed_module)
            deleted_paths = [path for path in existing_modules.keys() if path not in current_paths]
            for deleted_path in deleted_paths:
                self._tombstone_module(conn, deleted_path)
            self._upsert_packs(conn)
            self._re_resolve_dependencies(conn)
            self._write_mapping_report()
            services_indexed = conn.execute('SELECT COUNT(*) FROM services').fetchone()[0]
            endpoints_indexed = conn.execute('SELECT COUNT(*) FROM endpoints').fetchone()[0]
            dependencies_indexed = conn.execute('SELECT COUNT(*) FROM dependencies').fetchone()[0]
            conn.commit()
            report = CatalogBuildReport(
                build_id=build_id,
                catalog_db_path=str(self.catalog_db_path),
                scanned_modules=len(current_modules),
                changed_modules=changed_count,
                unchanged_modules=unchanged_count,
                deleted_modules=len(deleted_paths),
                services_indexed=services_indexed,
                endpoints_indexed=endpoints_indexed,
                dependencies_indexed=dependencies_indexed,
                mapping_report_path=str(self.mapping_report_path),
            )
            return report.to_dict()
        finally:
            conn.close()

    def _ensure_schema(self, conn: sqlite3.Connection) -> None:
        conn.executescript('''
            CREATE TABLE IF NOT EXISTS catalog_builds (build_id TEXT PRIMARY KEY, generated_at_utc TEXT NOT NULL, source_root TEXT NOT NULL, tool_version TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS artifacts (artifact_id TEXT PRIMARY KEY, parent_artifact_id TEXT, source_path TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, import_key TEXT NOT NULL, file_cid TEXT NOT NULL, size_bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL, is_deleted INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS services (service_id TEXT PRIMARY KEY, artifact_id TEXT NOT NULL, class_name TEXT NOT NULL, service_name TEXT NOT NULL, version TEXT NOT NULL, layer TEXT NOT NULL, description TEXT NOT NULL, tags_json TEXT NOT NULL, capabilities_json TEXT NOT NULL, side_effects_json TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS endpoints (endpoint_id TEXT PRIMARY KEY, service_id TEXT NOT NULL, method_name TEXT NOT NULL, inputs_json TEXT NOT NULL, outputs_json TEXT NOT NULL, description TEXT NOT NULL, tags_json TEXT NOT NULL, mode TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS dependencies (dependency_id TEXT PRIMARY KEY, src_service_id TEXT, src_artifact_id TEXT, dst_service_id TEXT, dst_artifact_id TEXT, external_name TEXT, pack_name TEXT, dependency_type TEXT NOT NULL, evidence_type TEXT NOT NULL, evidence_json TEXT NOT NULL, is_resolved INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS packs (pack_id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, version TEXT NOT NULL, manifest_json TEXT NOT NULL, status TEXT NOT NULL);
        ''')

    def _insert_build_row(self, conn: sqlite3.Connection, build_id: str) -> None:
        conn.execute('INSERT OR REPLACE INTO catalog_builds (build_id, generated_at_utc, source_root, tool_version) VALUES (?, ?, ?, ?)', (build_id, datetime.now(timezone.utc).isoformat(), str(self.library_root), APP_FACTORY_VERSION))

    def _discover_package_artifacts(self) -> List[Dict[str, Any]]:
        packages: List[Dict[str, Any]] = []
        for init_file in self.library_root.rglob('__init__.py'):
            if self._should_skip_path(init_file):
                continue
            package_dir = init_file.parent
            relative = package_dir.relative_to(self.workspace_root)
            parent_artifact_id = None
            if package_dir != self.library_root:
                parent_dir = package_dir.parent
                if (parent_dir / '__init__.py').exists():
                    parent_artifact_id = stable_id('artifact', str(parent_dir.relative_to(self.workspace_root)))
            packages.append({
                'artifact_id': stable_id('artifact', str(relative)),
                'parent_artifact_id': parent_artifact_id,
                'source_path': str(package_dir.resolve()),
                'kind': 'package',
                'import_key': '.'.join(relative.parts),
                'file_cid': hash_bytes(init_file.read_bytes()),
                'size_bytes': init_file.stat().st_size,
                'mtime_ns': init_file.stat().st_mtime_ns,
            })
        return packages

    def _discover_modules(self) -> List[ParsedModule]:
        modules: List[ParsedModule] = []
        for path in self.library_root.rglob('*.py'):
            if path.name == '__init__.py' or self._should_skip_path(path):
                continue
            modules.append(self._parse_module(path))
        return sorted(modules, key=lambda item: item.source_path)

    def _should_skip_path(self, path: Path) -> bool:
        parts = path.relative_to(self.library_root).parts
        if '__pycache__' in parts:
            return True
        if not parts:
            return False
        if parts[0] == 'tests':
            return True
        if len(parts) >= 2 and parts[0] == 'catalog' and parts[1] in {'install_staging', 'install_reports'}:
            return True
        return False

    def _parse_module(self, path: Path) -> ParsedModule:
        payload = path.read_bytes()
        text = payload.decode('utf-8', errors='ignore')
        tree = ast.parse(text, filename=str(path))
        module_symbols = self._extract_module_symbols(tree)
        relative = path.relative_to(self.workspace_root)
        parsed = ParsedModule(
            artifact_id=stable_id('artifact', str(relative)),
            source_path=str(path.resolve()),
            relative_path=str(relative),
            import_key=module_import_key(path, self.workspace_root),
            file_cid=hash_bytes(payload),
            size_bytes=path.stat().st_size,
            mtime_ns=path.stat().st_mtime_ns,
            layer=self._service_layer_for_path(path),
        )
        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    parsed.imports.append({'import_name': alias.name, 'kind': 'import', 'source': alias.name})
            elif isinstance(node, ast.ImportFrom):
                parsed.imports.append({
                    'import_name': resolve_relative_import(parsed.import_key, node.level, node.module),
                    'kind': 'from',
                    'source': node.module or '',
                    'level': node.level,
                })
            elif isinstance(node, ast.ClassDef):
                service = self._parse_service_class(node, parsed, module_symbols)
                if service:
                    parsed.services.append(service)
        return parsed

    def _extract_module_symbols(self, tree: ast.Module) -> Dict[str, Any]:
        symbols: Dict[str, Any] = {}
        sentinel = object()
        for node in tree.body:
            if isinstance(node, ast.Assign):
                resolved = resolve_value(node.value, symbols, sentinel)
                if resolved is sentinel:
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        symbols[target.id] = resolved
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                resolved = resolve_value(node.value, symbols, sentinel)
                if resolved is not sentinel:
                    symbols[node.target.id] = resolved
        return symbols

    def _parse_service_class(self, node: ast.ClassDef, parsed_module: ParsedModule, module_symbols: Optional[Dict[str, Any]]=None) -> Optional[ParsedService]:
        metadata_call: Optional[ast.Call] = None
        for decorator in node.decorator_list:
            if decorator_name(decorator) == 'service_metadata' and isinstance(decorator, ast.Call):
                metadata_call = decorator
                break
        if metadata_call is None:
            return None
        values = self._parse_service_metadata_call(metadata_call, module_symbols)
        service_id = stable_id('service', parsed_module.artifact_id, node.name)
        service = ParsedService(
            service_id=service_id,
            artifact_id=parsed_module.artifact_id,
            class_name=node.name,
            service_name=str(values.get('name', node.name)).strip() or node.name,
            version=str(values.get('version', '0.0.0')).strip() or '0.0.0',
            layer=parsed_module.layer,
            description=str(values.get('description', '')).strip(),
            tags=sanitize_text_list(values.get('tags', [])),
            capabilities=sanitize_text_list(values.get('capabilities', [])),
            side_effects=sanitize_text_list(values.get('side_effects', [])),
            internal_dependencies=sanitize_text_list(values.get('internal_dependencies', [])),
            external_dependencies=sanitize_text_list(values.get('external_dependencies', values.get('dependencies', []))),
        )
        for child in node.body:
            if not isinstance(child, ast.FunctionDef):
                continue
            endpoint_call: Optional[ast.Call] = None
            for decorator in child.decorator_list:
                if decorator_name(decorator) == 'service_endpoint' and isinstance(decorator, ast.Call):
                    endpoint_call = decorator
                    break
            if endpoint_call is None:
                continue
            endpoint_values = self._parse_endpoint_metadata_call(endpoint_call, module_symbols)
            service.endpoints.append(
                ParsedEndpoint(
                    endpoint_id=stable_id('endpoint', service_id, child.name),
                    service_id=service_id,
                    method_name=child.name,
                    inputs_json=json_dumps(endpoint_values.get('inputs', {})),
                    outputs_json=json_dumps(endpoint_values.get('outputs', {})),
                    description=str(endpoint_values.get('description', '')).strip(),
                    tags_json=json_dumps(sanitize_text_list(endpoint_values.get('tags', []))),
                    mode=str(endpoint_values.get('mode', 'sync')).strip() or 'sync',
                )
            )
        return service

    def _parse_service_metadata_call(self, call: ast.Call, module_symbols: Optional[Dict[str, Any]]=None) -> Dict[str, Any]:
        keys = ['name', 'version', 'description', 'tags']
        data: Dict[str, Any] = {}
        for index, arg in enumerate(call.args):
            if index < len(keys):
                data[keys[index]] = resolve_value(arg, module_symbols)
        for keyword in call.keywords:
            if keyword.arg:
                data[keyword.arg] = resolve_value(keyword.value, module_symbols)
        return data

    def _parse_endpoint_metadata_call(self, call: ast.Call, module_symbols: Optional[Dict[str, Any]]=None) -> Dict[str, Any]:
        keys = ['inputs', 'outputs', 'description']
        data: Dict[str, Any] = {}
        for index, arg in enumerate(call.args):
            if index < len(keys):
                data[keys[index]] = resolve_value(arg, module_symbols)
        for keyword in call.keywords:
            if keyword.arg:
                data[keyword.arg] = resolve_value(keyword.value, module_symbols)
        return data

    def _service_layer_for_path(self, path: Path) -> str:
        parts = path.relative_to(self.library_root).parts
        if len(parts) >= 3 and parts[0] == 'microservices':
            return parts[1]
        if len(parts) >= 2:
            return parts[0]
        return 'library'

    def _upsert_module(self, conn: sqlite3.Connection, parsed_module: ParsedModule) -> None:
        parent_artifact_id = stable_id('artifact', str(Path(parsed_module.relative_path).parent))
        conn.execute(
            'INSERT OR REPLACE INTO artifacts (artifact_id, parent_artifact_id, source_path, kind, import_key, file_cid, size_bytes, mtime_ns, is_deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)',
            (parsed_module.artifact_id, parent_artifact_id, parsed_module.source_path, 'module', parsed_module.import_key, parsed_module.file_cid, parsed_module.size_bytes, parsed_module.mtime_ns),
        )
        existing_service_ids = [row[0] for row in conn.execute('SELECT service_id FROM services WHERE artifact_id = ?', (parsed_module.artifact_id,)).fetchall()]
        if existing_service_ids:
            placeholders = ','.join('?' for _ in existing_service_ids)
            conn.execute(f'DELETE FROM endpoints WHERE service_id IN ({placeholders})', existing_service_ids)
            conn.execute(f'DELETE FROM dependencies WHERE src_service_id IN ({placeholders})', existing_service_ids)
        conn.execute('DELETE FROM services WHERE artifact_id = ?', (parsed_module.artifact_id,))
        conn.execute('DELETE FROM dependencies WHERE src_artifact_id = ?', (parsed_module.artifact_id,))
        for service in parsed_module.services:
            conn.execute(
                'INSERT OR REPLACE INTO services (service_id, artifact_id, class_name, service_name, version, layer, description, tags_json, capabilities_json, side_effects_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                (service.service_id, service.artifact_id, service.class_name, service.service_name, service.version, service.layer, service.description, json_dumps(service.tags), json_dumps(service.capabilities), json_dumps(service.side_effects)),
            )
            for endpoint in service.endpoints:
                conn.execute(
                    'INSERT OR REPLACE INTO endpoints (endpoint_id, service_id, method_name, inputs_json, outputs_json, description, tags_json, mode) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                    (endpoint.endpoint_id, endpoint.service_id, endpoint.method_name, endpoint.inputs_json, endpoint.outputs_json, endpoint.description, endpoint.tags_json, endpoint.mode),
                )
            for internal_dep in service.internal_dependencies:
                self._upsert_dependency_row(conn, stable_id('dep', service.service_id, 'requires_code', internal_dep), service.service_id, None, None, None, None, None, 'requires_code', 'declared_internal_dependency', json_dumps({'ref': internal_dep}), 0)
            for external_dep in service.external_dependencies:
                self._upsert_dependency_row(conn, stable_id('dep', service.service_id, 'requires_external', external_dep), service.service_id, None, None, None, external_dep, None, 'requires_external', 'declared_external_dependency', json_dumps({'ref': external_dep}), 1)
            if service.layer == 'ui' and service.class_name not in PACK_SERVICE_CLASS_NAMES and service.service_name not in PACK_SERVICE_CLASS_NAMES:
                self._upsert_dependency_row(conn, stable_id('dep', service.service_id, 'packaged_with', 'tkinter_base_pack'), service.service_id, None, None, None, None, 'tkinter_base_pack', 'packaged_with', 'curated_ui_pack_rule', json_dumps({'ref': 'tkinter_base_pack'}), 1)
        for import_row in parsed_module.imports:
            import_name = str(import_row.get('import_name', '')).strip()
            if not import_name:
                continue
            if import_name.startswith('library.') or import_name.startswith('_') or import_name in LOCAL_HELPER_MODULES:
                self._upsert_dependency_row(conn, stable_id('dep', parsed_module.artifact_id, 'requires_code', import_name), None, parsed_module.artifact_id, None, None, None, None, 'requires_code', 'import_analysis', json_dumps({'ref': import_name}), 0)

    def _upsert_dependency_row(self, conn: sqlite3.Connection, dependency_id: str, src_service_id: Optional[str], src_artifact_id: Optional[str], dst_service_id: Optional[str], dst_artifact_id: Optional[str], external_name: Optional[str], pack_name: Optional[str], dependency_type: str, evidence_type: str, evidence_json: str, is_resolved: int) -> None:
        conn.execute(
            'INSERT OR REPLACE INTO dependencies (dependency_id, src_service_id, src_artifact_id, dst_service_id, dst_artifact_id, external_name, pack_name, dependency_type, evidence_type, evidence_json, is_resolved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (dependency_id, src_service_id, src_artifact_id, dst_service_id, dst_artifact_id, external_name, pack_name, dependency_type, evidence_type, evidence_json, is_resolved),
        )

    def _tombstone_module(self, conn: sqlite3.Connection, deleted_path: str) -> None:
        row = conn.execute("SELECT artifact_id FROM artifacts WHERE source_path = ? AND kind='module'", (deleted_path,)).fetchone()
        if row is None:
            return
        artifact_id = row['artifact_id']
        existing_service_ids = [item[0] for item in conn.execute('SELECT service_id FROM services WHERE artifact_id = ?', (artifact_id,)).fetchall()]
        if existing_service_ids:
            placeholders = ','.join('?' for _ in existing_service_ids)
            conn.execute(f'DELETE FROM endpoints WHERE service_id IN ({placeholders})', existing_service_ids)
            conn.execute(f'DELETE FROM dependencies WHERE src_service_id IN ({placeholders})', existing_service_ids)
        conn.execute('UPDATE artifacts SET is_deleted = 1 WHERE artifact_id = ?', (artifact_id,))
        conn.execute('DELETE FROM dependencies WHERE src_artifact_id = ?', (artifact_id,))
        conn.execute('UPDATE dependencies SET dst_artifact_id = NULL, is_resolved = 0 WHERE dst_artifact_id = ?', (artifact_id,))
        conn.execute('DELETE FROM services WHERE artifact_id = ?', (artifact_id,))

    def _upsert_packs(self, conn: sqlite3.Connection) -> None:
        for pack_id, pack in UI_PACKS.items():
            conn.execute(
                'INSERT OR REPLACE INTO packs (pack_id, name, kind, version, manifest_json, status) VALUES (?, ?, ?, ?, ?, ?)',
                (pack_id, pack['name'], pack['kind'], pack['version'], json_dumps(pack['manifest']), 'active'),
            )

    def _re_resolve_dependencies(self, conn: sqlite3.Connection) -> None:
        artifacts = conn.execute("SELECT artifact_id, source_path, import_key FROM artifacts WHERE kind='module' AND is_deleted = 0").fetchall()
        services = conn.execute('SELECT service_id, artifact_id, class_name, service_name FROM services').fetchall()
        artifact_by_import: Dict[str, str] = {}
        artifact_by_stem: Dict[str, str] = {}
        for row in artifacts:
            artifact_by_import[row['import_key']] = row['artifact_id']
            artifact_by_stem.setdefault(Path(row['source_path']).stem, row['artifact_id'])
        service_by_class: Dict[str, str] = {}
        service_by_name: Dict[str, str] = {}
        for row in services:
            service_by_class.setdefault(row['class_name'], row['service_id'])
            service_by_name.setdefault(row['service_name'], row['service_id'])
        dependency_rows = conn.execute('SELECT dependency_id, evidence_json, external_name, pack_name FROM dependencies').fetchall()
        for row in dependency_rows:
            if row['external_name'] or row['pack_name']:
                conn.execute('UPDATE dependencies SET is_resolved = 1 WHERE dependency_id = ?', (row['dependency_id'],))
                continue
            ref = str(json.loads(row['evidence_json']).get('ref', '')).strip()
            dst_service_id = None
            dst_artifact_id = None
            if ref in service_by_class:
                dst_service_id = service_by_class[ref]
            elif ref in service_by_name:
                dst_service_id = service_by_name[ref]
            elif ref in artifact_by_import:
                dst_artifact_id = artifact_by_import[ref]
            elif ref in artifact_by_stem:
                dst_artifact_id = artifact_by_stem[ref]
            conn.execute('UPDATE dependencies SET dst_service_id = ?, dst_artifact_id = ?, is_resolved = ? WHERE dependency_id = ?', (dst_service_id, dst_artifact_id, 1 if dst_service_id or dst_artifact_id else 0, row['dependency_id']))

    def _write_mapping_report(self) -> None:
        self.mapping_report_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_catalog_path = self.library_root / 'catalog' / 'library_catalog.json'
        report: Dict[str, Any] = {'generated_at_utc': datetime.now(timezone.utc).isoformat(), 'source': str(legacy_catalog_path), 'mappings': []}
        if legacy_catalog_path.exists():
            payload = json.loads(legacy_catalog_path.read_text(encoding='utf-8'))
            for plan in payload.get('plans', []):
                report['mappings'].append({'legacy_source': plan.get('source', ''), 'canonical_destination': plan.get('destination', ''), 'service_name': plan.get('service_name', ''), 'class_name': plan.get('class_name', ''), 'layer': plan.get('layer', '')})
        self.mapping_report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')

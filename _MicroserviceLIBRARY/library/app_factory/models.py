"""Dataclasses shared across the app-factory modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AppBlueprintManifest:
    app_id: str
    name: str
    destination: str
    vendor_mode: str = "module_ref"
    resolution_profile: str = "app_ready"
    ui_pack: str = "headless_pack"
    orchestrator: str = "headless_backend_orchestrator"
    manager_layers: List[str] = field(default_factory=list)
    microservices: List[str] = field(default_factory=list)
    modules: List[str] = field(default_factory=list)
    settings_defaults: Dict[str, Any] = field(default_factory=dict)
    hooks: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "AppBlueprintManifest":
        return cls(
            app_id=str(payload.get("app_id", "")).strip(),
            name=str(payload.get("name", "")).strip(),
            destination=str(payload.get("destination", "")).strip(),
            vendor_mode=str(payload.get("vendor_mode", "module_ref")).strip(),
            resolution_profile=str(payload.get("resolution_profile", "app_ready")).strip(),
            ui_pack=str(payload.get("ui_pack", "headless_pack")).strip(),
            orchestrator=str(payload.get("orchestrator", "headless_backend_orchestrator")).strip(),
            manager_layers=list(payload.get("manager_layers", []) or []),
            microservices=list(payload.get("microservices", []) or []),
            modules=list(payload.get("modules", []) or []),
            settings_defaults=dict(payload.get("settings_defaults", {}) or {}),
            hooks=dict(payload.get("hooks", {}) or {}),
        )


@dataclass
class ResolvedArtifact:
    artifact_id: str
    source_path: str
    target_path: str
    file_cid: str
    materialization_mode: str
    import_key: str = ""
    class_name: str = ""
    service_name: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StamperValidationResult:
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    cycle_warnings: List[str] = field(default_factory=list)
    missing_dependencies: List[str] = field(default_factory=list)
    compile_results: Dict[str, Any] = field(default_factory=dict)

    def ok(self) -> bool:
        return not self.errors and not self.missing_dependencies

    def to_dict(self) -> Dict[str, Any]:
        return {
            "warnings": list(self.warnings),
            "errors": list(self.errors),
            "cycle_warnings": list(self.cycle_warnings),
            "missing_dependencies": list(self.missing_dependencies),
            "compile_results": dict(self.compile_results),
            "ok": self.ok(),
        }


@dataclass
class CatalogBuildReport:
    build_id: str
    catalog_db_path: str
    scanned_modules: int
    changed_modules: int
    unchanged_modules: int
    deleted_modules: int
    services_indexed: int
    endpoints_indexed: int
    dependencies_indexed: int
    mapping_report_path: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


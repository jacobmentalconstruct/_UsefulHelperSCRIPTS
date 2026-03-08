"""Sandboxed app stamping, patching, validation, and promotion helpers."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .constants import APP_FACTORY_VERSION, WORKSPACE_ROOT
from .models import AppBlueprintManifest
from .query import LibraryQueryService
from .stamper import AppStamper

DEFAULT_SANDBOX_ROOT = Path(WORKSPACE_ROOT).resolve() / "_sanbox" / "apps"
PATCHER_SCRIPT = Path(WORKSPACE_ROOT).resolve() / "_curationTOOLS" / "tokenizing_patcher_with_cli.py"
STATE_FILE_NAME = "sandbox_state.json"
TRANSFORM_LOCK_NAME = ".transform_lock.json"
APP_FACTORY_META_DIR = ".app_factory"
APP_PATCH_DIR = Path(APP_FACTORY_META_DIR) / "patches"
APP_REPORT_DIR = Path(APP_FACTORY_META_DIR) / "reports"


class SandboxWorkflow:
    def __init__(
        self,
        query_service: Optional[LibraryQueryService] = None,
        sandbox_root: Optional[Path | str] = None,
        patcher_script: Optional[Path | str] = None,
    ):
        self.query_service = query_service or LibraryQueryService()
        self.stamper = AppStamper(self.query_service)
        self.sandbox_root = Path(sandbox_root).resolve() if sandbox_root else DEFAULT_SANDBOX_ROOT
        self.patcher_script = Path(patcher_script).resolve() if patcher_script else PATCHER_SCRIPT

    def sandbox_stamp(
        self,
        run_id: str,
        *,
        template_id: Optional[str] = None,
        manifest_path: Optional[Path | str] = None,
        sandbox_root: Optional[Path | str] = None,
        name: Optional[str] = None,
        vendor_mode: Optional[str] = None,
        resolution_profile: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        workspace_root = self._workspace_root(run_id, sandbox_root)
        if workspace_root.exists():
            if not force:
                raise FileExistsError(f"Sandbox workspace already exists: {workspace_root}")
            shutil.rmtree(workspace_root)
        base_dir = workspace_root / "base"
        working_dir = workspace_root / "working"
        patch_dir = workspace_root / "patches"
        report_dir = workspace_root / "reports"
        for path in (base_dir, working_dir, patch_dir, report_dir):
            path.mkdir(parents=True, exist_ok=True)
        app_patch_dir = working_dir / APP_PATCH_DIR
        app_report_dir = working_dir / APP_REPORT_DIR
        app_patch_dir.mkdir(parents=True, exist_ok=True)
        app_report_dir.mkdir(parents=True, exist_ok=True)

        manifest = self._prepare_manifest(
            base_dir=base_dir,
            template_id=template_id,
            manifest_path=manifest_path,
            name=name,
            vendor_mode=vendor_mode,
            resolution_profile=resolution_profile,
        )
        stamp_report = self.stamper.stamp(manifest)
        if not stamp_report["validation"]["ok"]:
            report = {
                "workspace_root": str(workspace_root),
                "base_app_dir": str(base_dir),
                "working_app_dir": str(working_dir),
                "stamp_report": stamp_report,
                "ok": False,
            }
            self._write_json(report_dir / "stamp_report.json", report)
            return report

        self._copy_tree(base_dir, working_dir)
        self._rewrite_copied_app(source_root=base_dir, target_root=working_dir)
        state = {
            "version": APP_FACTORY_VERSION,
            "run_id": self._sanitize_run_id(run_id),
            "workspace_root": str(workspace_root),
            "base_app_dir": str(base_dir),
            "working_app_dir": str(working_dir),
            "workspace_patch_dir": str(patch_dir),
            "workspace_report_dir": str(report_dir),
            "app_patch_dir": str(app_patch_dir),
            "app_report_dir": str(app_report_dir),
            "template_id": template_id or "",
            "source_manifest_path": str(Path(manifest_path).resolve()) if manifest_path else "",
            "last_promotion_destination": "",
        }
        self._write_state(workspace_root, state)
        working_integrity = self.stamper.verify_app_integrity(working_dir)
        report = {
            "workspace_root": str(workspace_root),
            "base_app_dir": str(base_dir),
            "working_app_dir": str(working_dir),
            "state_path": str(workspace_root / STATE_FILE_NAME),
            "stamp_report": stamp_report,
            "working_stamp_integrity": working_integrity,
            "ok": stamp_report["validation"]["ok"] and working_integrity["ok"],
        }
        self._write_json(report_dir / "stamp_report.json", report)
        self._write_json(app_report_dir / "stamp_report.json", report)
        return report

    def sandbox_apply(
        self,
        workspace: Path | str,
        patch_manifests: Sequence[Path | str] | None = None,
        *,
        backup: bool = True,
    ) -> Dict[str, Any]:
        state = self._load_state(workspace)
        workspace_root = Path(state["workspace_root"])
        working_dir = Path(state["working_app_dir"])
        workspace_patch_dir = Path(state["workspace_patch_dir"])
        workspace_report_dir = Path(state["workspace_report_dir"])
        app_patch_dir = Path(state["app_patch_dir"])
        app_report_dir = Path(state["app_report_dir"])
        app_patch_dir.mkdir(parents=True, exist_ok=True)
        app_report_dir.mkdir(parents=True, exist_ok=True)

        manifest_paths = [Path(item).resolve() for item in (patch_manifests or [])]
        if not manifest_paths:
            manifest_paths = sorted(workspace_patch_dir.glob("*.json"))
        if not manifest_paths:
            raise FileNotFoundError("No patch manifests supplied and none found in the sandbox patch directory.")

        existing_patch_count = len(list(app_patch_dir.glob("*.json")))
        validate_reports: List[Dict[str, Any]] = []
        apply_reports: List[Dict[str, Any]] = []
        copied_patch_records: List[Dict[str, Any]] = []
        for offset, patch_manifest in enumerate(manifest_paths, start=1):
            if not patch_manifest.exists():
                raise FileNotFoundError(patch_manifest)
            validate_report = self._run_patcher("validate", patch_manifest, working_dir)
            validate_reports.append(validate_report)
            if not validate_report["ok"]:
                report = {
                    "workspace_root": str(workspace_root),
                    "working_app_dir": str(working_dir),
                    "validate_reports": validate_reports,
                    "apply_reports": apply_reports,
                    "transform_lock_path": "",
                    "ok": False,
                }
                self._write_json(workspace_report_dir / "apply_report.json", report)
                self._write_json(app_report_dir / "apply_report.json", report)
                return report

            patch_name = f"{existing_patch_count + offset:02d}_{patch_manifest.name}"
            workspace_patch_copy = workspace_patch_dir / patch_name
            app_patch_copy = app_patch_dir / patch_name
            shutil.copy2(patch_manifest, workspace_patch_copy)
            shutil.copy2(patch_manifest, app_patch_copy)
            copied_patch_records.append(
                {
                    "source_path": str(patch_manifest),
                    "workspace_path": str(workspace_patch_copy),
                    "app_path": self._relative_path(app_patch_copy, working_dir),
                    "sha256": self._hash_file(app_patch_copy),
                }
            )
            apply_report = self._run_patcher("apply", patch_manifest, working_dir, backup=backup)
            apply_reports.append(apply_report)
            if not apply_report["ok"]:
                report = {
                    "workspace_root": str(workspace_root),
                    "working_app_dir": str(working_dir),
                    "validate_reports": validate_reports,
                    "apply_reports": apply_reports,
                    "copied_patch_records": copied_patch_records,
                    "transform_lock_path": "",
                    "ok": False,
                }
                self._write_json(workspace_report_dir / "apply_report.json", report)
                self._write_json(app_report_dir / "apply_report.json", report)
                return report

        transform_lock = self._build_transform_lock(working_dir, Path(state["base_app_dir"]))
        transform_lock_path = working_dir / TRANSFORM_LOCK_NAME
        transform_lock_path.write_text(json.dumps(transform_lock, indent=2), encoding="utf-8")
        report = {
            "workspace_root": str(workspace_root),
            "working_app_dir": str(working_dir),
            "validate_reports": validate_reports,
            "apply_reports": apply_reports,
            "copied_patch_records": copied_patch_records,
            "transform_lock_path": str(transform_lock_path),
            "ok": True,
        }
        state["transform_lock_path"] = str(transform_lock_path)
        self._write_state(workspace_root, state)
        self._write_json(workspace_report_dir / "apply_report.json", report)
        self._write_json(app_report_dir / "apply_report.json", report)
        return report

    def sandbox_validate(self, workspace: Path | str) -> Dict[str, Any]:
        state = self._load_state(workspace)
        workspace_root = Path(state["workspace_root"])
        working_dir = Path(state["working_app_dir"])
        workspace_report_dir = Path(state["workspace_report_dir"])
        app_report_dir = Path(state["app_report_dir"])

        compile_results = self.stamper._compile_tree(working_dir)
        health_result = self._run_app_command(working_dir, "--health")
        no_ui_result = self._run_app_command(working_dir, "--no-ui")
        stamp_integrity = self.stamper.verify_app_integrity(working_dir)
        transform_integrity = None
        transform_lock_path = working_dir / TRANSFORM_LOCK_NAME
        if transform_lock_path.exists():
            transform_integrity = self.verify_transform_lock(working_dir)
        active_integrity = transform_integrity if transform_integrity is not None else stamp_integrity
        report = {
            "workspace_root": str(workspace_root),
            "working_app_dir": str(working_dir),
            "compile_results": compile_results,
            "health_result": health_result,
            "no_ui_result": no_ui_result,
            "stamp_integrity": stamp_integrity,
            "transform_integrity": transform_integrity,
            "active_integrity": "transform" if transform_integrity is not None else "stamp",
            "ok": not compile_results["errors"]
            and health_result["ok"]
            and no_ui_result["ok"]
            and active_integrity["ok"],
        }
        self._write_json(workspace_report_dir / "validate_report.json", report)
        self._write_json(app_report_dir / "validate_report.json", report)
        return report

    def sandbox_promote(
        self,
        workspace: Path | str,
        destination: Path | str,
        *,
        force: bool = False,
    ) -> Dict[str, Any]:
        state = self._load_state(workspace)
        workspace_root = Path(state["workspace_root"])
        working_dir = Path(state["working_app_dir"])
        workspace_report_dir = Path(state["workspace_report_dir"])
        destination_dir = Path(destination).resolve()
        if destination_dir.exists():
            if not force:
                raise FileExistsError(f"Promotion destination already exists: {destination_dir}")
            shutil.rmtree(destination_dir)
        self._copy_tree(working_dir, destination_dir, ignore_patterns=["__pycache__", "*.pyc", "*.bak"])
        self._rewrite_copied_app(source_root=working_dir, target_root=destination_dir)
        transform_lock_path = destination_dir / TRANSFORM_LOCK_NAME
        if transform_lock_path.exists():
            transform_lock = self._build_transform_lock(destination_dir, Path(state["base_app_dir"]))
            transform_lock_path.write_text(json.dumps(transform_lock, indent=2), encoding="utf-8")
        validation = self._validate_app_dir(destination_dir)
        state["last_promotion_destination"] = str(destination_dir)
        self._write_state(workspace_root, state)
        report = {
            "workspace_root": str(workspace_root),
            "working_app_dir": str(working_dir),
            "destination_app_dir": str(destination_dir),
            "validation": validation,
            "ok": validation["ok"],
        }
        self._write_json(workspace_report_dir / "promote_report.json", report)
        return report

    def verify_transform_lock(self, app_dir: Path | str) -> Dict[str, Any]:
        app_dir = Path(app_dir).resolve()
        lock_path = app_dir / TRANSFORM_LOCK_NAME
        if not lock_path.exists():
            return {"ok": False, "errors": [f"Missing {TRANSFORM_LOCK_NAME}"], "checked": []}
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        inspection = {
            "checked": [],
            "errors": [],
            "missing_generated_python_files": [],
            "generated_python_file_drift": [],
            "missing_generated_support_files": [],
            "generated_support_file_drift": [],
            "missing_runtime_config_files": [],
            "runtime_config_file_drift": [],
            "missing_patch_manifests": [],
            "patch_manifest_drift": [],
            "missing_library_artifacts": [],
            "library_artifact_drift": [],
            "missing_source_stamp_lock": [],
            "source_stamp_lock_drift": [],
        }
        for section, missing_key, drift_key in (
            ("generated_python_files", "missing_generated_python_files", "generated_python_file_drift"),
            ("generated_support_files", "missing_generated_support_files", "generated_support_file_drift"),
            ("runtime_config_files", "missing_runtime_config_files", "runtime_config_file_drift"),
            ("patch_manifests", "missing_patch_manifests", "patch_manifest_drift"),
        ):
            for entry in lock.get(section, []):
                target = app_dir / entry["path"]
                inspection["checked"].append(str(target))
                if not target.exists():
                    inspection[missing_key].append(str(target))
                    inspection["errors"].append(f"Missing {section[:-1].replace('_', ' ')}: {target}")
                    continue
                if self._hash_file(target) != entry["sha256"]:
                    inspection[drift_key].append(str(target))
                    inspection["errors"].append(f"Drift detected in {section[:-1].replace('_', ' ')}: {target}")
        source_lock_entry = lock.get("source_stamp_lock", {})
        source_lock_path = app_dir / source_lock_entry.get("path", ".stamper_lock.json")
        inspection["checked"].append(str(source_lock_path))
        if not source_lock_path.exists():
            inspection["missing_source_stamp_lock"].append(str(source_lock_path))
            inspection["errors"].append(f"Missing source stamp lock: {source_lock_path}")
        elif source_lock_entry.get("sha256") and self._hash_file(source_lock_path) != source_lock_entry["sha256"]:
            inspection["source_stamp_lock_drift"].append(str(source_lock_path))
            inspection["errors"].append(f"Source stamp lock drift: {source_lock_path}")
        for entry in lock.get("resolved_library_artifacts", []):
            target = Path(entry["target_path"]) if entry.get("materialization_mode") == "static" else Path(entry["source_path"])
            inspection["checked"].append(str(target))
            if not target.exists():
                inspection["missing_library_artifacts"].append(str(target))
                inspection["errors"].append(f"Missing library artifact: {target}")
                continue
            if self._hash_file(target) != entry["file_cid"]:
                inspection["library_artifact_drift"].append(str(target))
                inspection["errors"].append(f"Library artifact drift: {target}")
        inspection["ok"] = not inspection["errors"]
        return inspection

    def _workspace_root(self, run_id: str, sandbox_root: Optional[Path | str]) -> Path:
        root = Path(sandbox_root).resolve() if sandbox_root else self.sandbox_root
        return root / self._sanitize_run_id(run_id)

    def _sanitize_run_id(self, run_id: str) -> str:
        cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", str(run_id).strip())
        return cleaned.strip("._") or "sandbox_app"

    def _prepare_manifest(
        self,
        *,
        base_dir: Path,
        template_id: Optional[str],
        manifest_path: Optional[Path | str],
        name: Optional[str],
        vendor_mode: Optional[str],
        resolution_profile: Optional[str],
    ) -> AppBlueprintManifest:
        if bool(template_id) == bool(manifest_path):
            raise ValueError("Provide exactly one of template_id or manifest_path.")
        if template_id:
            payload = self.query_service.template_blueprint(
                template_id,
                destination=str(base_dir),
                name=name or "",
                vendor_mode=vendor_mode or None,
                resolution_profile=resolution_profile or None,
            )
        else:
            payload = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
            if name:
                payload["name"] = name
            if vendor_mode:
                payload["vendor_mode"] = vendor_mode
            if resolution_profile:
                payload["resolution_profile"] = resolution_profile
            payload["destination"] = str(base_dir)
        return AppBlueprintManifest.from_dict(payload)

    def _load_state(self, workspace: Path | str) -> Dict[str, Any]:
        workspace_root = Path(workspace).resolve()
        state_path = workspace_root / STATE_FILE_NAME
        if not state_path.exists():
            raise FileNotFoundError(state_path)
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            raise ValueError(f"Invalid sandbox state: {state_path}")
        state["workspace_root"] = str(workspace_root)
        state["base_app_dir"] = str(self._resolve_state_path(state.get("base_app_dir", ""), workspace_root, workspace_root / "base"))
        state["working_app_dir"] = str(self._resolve_state_path(state.get("working_app_dir", ""), workspace_root, workspace_root / "working"))
        state["workspace_patch_dir"] = str(self._resolve_state_path(state.get("workspace_patch_dir", ""), workspace_root, workspace_root / "patches"))
        state["workspace_report_dir"] = str(self._resolve_state_path(state.get("workspace_report_dir", ""), workspace_root, workspace_root / "reports"))
        state["app_patch_dir"] = str(self._resolve_state_path(state.get("app_patch_dir", ""), workspace_root, workspace_root / APP_PATCH_DIR))
        state["app_report_dir"] = str(self._resolve_state_path(state.get("app_report_dir", ""), workspace_root, workspace_root / APP_REPORT_DIR))
        if state.get("transform_lock_path"):
            state["transform_lock_path"] = str(self._resolve_state_path(state.get("transform_lock_path", ""), workspace_root, workspace_root / "working" / TRANSFORM_LOCK_NAME))
        return state

    def _resolve_state_path(self, raw_path: Any, workspace_root: Path, fallback: Path) -> Path:
        raw = str(raw_path or '').strip()
        if not raw:
            return fallback.resolve()
        if raw == '.':
            return workspace_root.resolve()
        candidate = Path(raw)
        if not candidate.is_absolute():
            return (workspace_root / candidate).resolve()
        try:
            if candidate.exists():
                return candidate.resolve()
        except Exception:
            pass
        return fallback.resolve()

    def _write_state(self, workspace_root: Path, state: Dict[str, Any]) -> None:
        self._write_json(workspace_root / STATE_FILE_NAME, state)

    def _write_json(self, path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _copy_tree(self, source: Path, destination: Path, ignore_patterns: Optional[List[str]] = None) -> None:
        ignore = shutil.ignore_patterns(*(ignore_patterns or [])) if ignore_patterns else None
        shutil.copytree(source, destination, dirs_exist_ok=True, ignore=ignore)

    def _rewrite_copied_app(self, *, source_root: Path, target_root: Path) -> None:
        self._rewrite_manifest_destination(target_root)
        self._rewrite_stamp_lock(source_root, target_root)
        app_patch_dir = target_root / APP_PATCH_DIR
        app_report_dir = target_root / APP_REPORT_DIR
        app_patch_dir.mkdir(parents=True, exist_ok=True)
        app_report_dir.mkdir(parents=True, exist_ok=True)

    def _rewrite_manifest_destination(self, app_dir: Path) -> None:
        manifest_path = app_dir / "app_manifest.json"
        if not manifest_path.exists():
            return
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["destination"] = str(app_dir)
        manifest_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _rewrite_stamp_lock(self, source_root: Path, target_root: Path) -> None:
        lock_path = target_root / ".stamper_lock.json"
        manifest_path = target_root / "app_manifest.json"
        schema_path = target_root / "ui_schema.json"
        if not lock_path.exists() or not manifest_path.exists():
            return
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for section in ("generated_python_files", "generated_support_files"):
            for entry in lock.get(section, []):
                old_path = Path(entry["path"])
                try:
                    relative = old_path.resolve().relative_to(source_root.resolve())
                except Exception:
                    relative = Path(old_path.name)
                new_path = (target_root / relative).resolve()
                entry["path"] = str(new_path)
                if new_path.exists():
                    entry["sha256"] = self._hash_file(new_path)
        for artifact in lock.get("resolved_library_artifacts", []):
            if artifact.get("materialization_mode") != "static":
                continue
            target_path = artifact.get("target_path", "")
            if not target_path:
                continue
            old_path = Path(target_path)
            try:
                relative = old_path.resolve().relative_to(source_root.resolve())
            except Exception:
                continue
            new_path = (target_root / relative).resolve()
            artifact["target_path"] = str(new_path)
            if new_path.exists():
                artifact["file_cid"] = self._hash_file(new_path)
        lock["locked_blueprint_hash"] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode("utf-8")).hexdigest()
        lock["ui_schema_snapshot_hash"] = self._hash_file(schema_path) if schema_path.exists() else ""
        lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")

    def _build_transform_lock(self, app_dir: Path, base_app_dir: Path) -> Dict[str, Any]:
        app_manifest_path = app_dir / "app_manifest.json"
        app_manifest = json.loads(app_manifest_path.read_text(encoding="utf-8")) if app_manifest_path.exists() else {}
        stamp_lock_path = app_dir / ".stamper_lock.json"
        stamp_lock = json.loads(stamp_lock_path.read_text(encoding="utf-8")) if stamp_lock_path.exists() else {}
        generated_python_files = self._collect_hashed_files(app_dir, ("app.py", "backend.py", "ui.py"))
        generated_support_files = self._collect_hashed_files(app_dir, ("requirements.txt", "pyrightconfig.json", ".env"))
        runtime_config_files = self._collect_hashed_files(app_dir, ("app_manifest.json", "settings.json", "ui_schema.json"))
        patch_manifests = []
        patch_root = app_dir / APP_PATCH_DIR
        for path in sorted(patch_root.glob("*.json")):
            patch_manifests.append({
                "path": self._relative_path(path, app_dir),
                "sha256": self._hash_file(path),
                "name": path.name,
            })
        return {
            "transform_lock_version": "1.0",
            "app_factory_version": APP_FACTORY_VERSION,
            "app_dir": str(app_dir),
            "base_app_dir": str(base_app_dir),
            "locked_blueprint_hash": hashlib.sha256(json.dumps(app_manifest, sort_keys=True).encode("utf-8")).hexdigest() if app_manifest else "",
            "vendor_mode": app_manifest.get("vendor_mode", stamp_lock.get("vendor_mode", "")),
            "source_stamp_lock": {
                "path": ".stamper_lock.json",
                "sha256": self._hash_file(stamp_lock_path) if stamp_lock_path.exists() else "",
            },
            "patch_manifests": patch_manifests,
            "generated_python_files": generated_python_files,
            "generated_support_files": generated_support_files,
            "runtime_config_files": runtime_config_files,
            "resolved_library_artifacts": stamp_lock.get("resolved_library_artifacts", []),
            "external_dependencies": stamp_lock.get("external_dependencies", []),
            "integrity_scope": {
                "included": [
                    "generated_python_files",
                    "generated_support_files",
                    "runtime_config_files",
                    "patch_manifests",
                    "resolved_library_artifacts",
                ],
                "excluded": [],
            },
        }

    def _collect_hashed_files(self, app_dir: Path, names: Sequence[str]) -> List[Dict[str, str]]:
        entries: List[Dict[str, str]] = []
        for name in names:
            path = app_dir / name
            if path.exists():
                entries.append({"path": self._relative_path(path, app_dir), "sha256": self._hash_file(path)})
        return entries

    def _relative_path(self, path: Path, root: Path) -> str:
        return path.resolve().relative_to(root.resolve()).as_posix()

    def _hash_file(self, path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _run_patcher(self, mode: str, patch_manifest: Path, root_dir: Path, *, backup: bool = False) -> Dict[str, Any]:
        command = [sys.executable, str(self.patcher_script), mode, str(patch_manifest), "--root-dir", str(root_dir)]
        if mode == "apply" and backup:
            command.append("--backup")
        result = subprocess.run(command, capture_output=True, text=True, timeout=240, check=False)
        payload: Dict[str, Any]
        stdout = result.stdout.strip()
        if stdout:
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = {"stdout": stdout}
        else:
            payload = {}
        if result.stderr.strip():
            payload.setdefault("stderr", result.stderr.strip())
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "command": command,
            "payload": payload,
        }

    def _run_app_command(self, app_dir: Path, *args: str) -> Dict[str, Any]:
        command = [sys.executable, "app.py", *args]
        result = subprocess.run(command, cwd=app_dir, capture_output=True, text=True, timeout=240, check=False)
        stdout = result.stdout.strip()
        payload: Any = stdout
        if stdout:
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = stdout
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "command": command,
            "payload": payload,
            "stderr": result.stderr.strip(),
        }

    def _validate_app_dir(self, app_dir: Path) -> Dict[str, Any]:
        compile_results = self.stamper._compile_tree(app_dir)
        health_result = self._run_app_command(app_dir, "--health")
        no_ui_result = self._run_app_command(app_dir, "--no-ui")
        transform_lock_path = app_dir / TRANSFORM_LOCK_NAME
        if transform_lock_path.exists():
            integrity = self.verify_transform_lock(app_dir)
            active = "transform"
        else:
            integrity = self.stamper.verify_app_integrity(app_dir)
            active = "stamp"
        return {
            "compile_results": compile_results,
            "health_result": health_result,
            "no_ui_result": no_ui_result,
            "integrity": integrity,
            "active_integrity": active,
            "ok": not compile_results["errors"] and health_result["ok"] and no_ui_result["ok"] and integrity["ok"],
        }

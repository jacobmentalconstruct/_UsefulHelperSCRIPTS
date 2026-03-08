"""CLI entry points for the app-factory package."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import CatalogBuilder
from .librarian_ui import LibrarianApp
from .models import AppBlueprintManifest
from .query import LibraryQueryService
from .runner_ui import PipelineRunnerApp
from .sandbox import SandboxWorkflow
from .stamper import AppStamper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Library app-factory tooling.")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("build-catalog", help="Build or refresh the SQLite catalog.")
    subparsers.add_parser("launch-ui", help="Launch the librarian Tkinter UI.")
    subparsers.add_parser("launch-runner-ui", help="Launch the pipeline runner UI.")
    subparsers.add_parser("list-templates", help="List built-in manifest templates.")

    stamp_parser = subparsers.add_parser("stamp", help="Stamp an app from a manifest JSON file.")
    stamp_parser.add_argument("manifest", help="Path to a manifest JSON file.")

    template_parser = subparsers.add_parser("template-manifest", help="Generate a manifest from a built-in template.")
    template_parser.add_argument("template_id", help="Template identifier.")
    template_parser.add_argument("--destination", default="", help="Optional destination path.")
    template_parser.add_argument("--name", default="", help="Optional app name override.")
    template_parser.add_argument("--vendor-mode", choices=["module_ref", "static"], default="")
    template_parser.add_argument("--resolution-profile", choices=["app_ready", "strict", "explicit_pack"], default="")
    template_parser.add_argument("--output", default="", help="Optional file path to write the manifest JSON.")

    stamp_template_parser = subparsers.add_parser("stamp-template", help="Generate and stamp an app directly from a built-in template.")
    stamp_template_parser.add_argument("template_id", help="Template identifier.")
    stamp_template_parser.add_argument("--destination", required=True, help="Destination path for the stamped app.")
    stamp_template_parser.add_argument("--name", default="", help="Optional app name override.")
    stamp_template_parser.add_argument("--vendor-mode", choices=["module_ref", "static"], default="")
    stamp_template_parser.add_argument("--resolution-profile", choices=["app_ready", "strict", "explicit_pack"], default="")

    validate_parser = subparsers.add_parser("validate-manifest", help="Validate a manifest JSON file without stamping.")
    validate_parser.add_argument("manifest", help="Path to a manifest JSON file.")

    inspect_parser = subparsers.add_parser("inspect-app", help="Inspect a stamped app for drift and restamp readiness.")
    inspect_parser.add_argument("app_dir", help="Stamped app directory.")

    upgrade_parser = subparsers.add_parser("upgrade-report", help="Compare a stamped app lockfile to the current catalog resolution.")
    upgrade_parser.add_argument("app_dir", help="Stamped app directory.")

    restamp_parser = subparsers.add_parser("restamp", help="Restamp an existing app from its app_manifest.json.")
    restamp_parser.add_argument("app_dir", help="Existing stamped app directory.")
    restamp_parser.add_argument("--destination", help="Optional new destination directory.", default="")
    restamp_parser.add_argument("--name", help="Optional override app name.", default="")
    restamp_parser.add_argument("--vendor-mode", choices=["module_ref", "static"], default="")
    restamp_parser.add_argument("--resolution-profile", choices=["app_ready", "strict", "explicit_pack"], default="")
    restamp_parser.add_argument("--no-preserve-ui-schema", action="store_true", help="Do not carry forward the existing ui_schema.json.")

    verify_parser = subparsers.add_parser("verify", help="Verify stamped app integrity.")
    verify_parser.add_argument("app_dir", help="Stamped app directory.")

    sandbox_stamp_parser = subparsers.add_parser("sandbox-stamp", help="Create a sandbox workspace and stamp a base app into base/working.")
    sandbox_stamp_parser.add_argument("--run-id", required=True, help="Sandbox workspace name.")
    sandbox_stamp_parser.add_argument("--sandbox-root", default="", help="Optional sandbox root directory. Defaults to _sandbox/apps. Legacy _sanbox paths are still accepted.")
    stamp_source = sandbox_stamp_parser.add_mutually_exclusive_group(required=True)
    stamp_source.add_argument("--template-id", default="", help="Built-in template identifier to stamp into the sandbox.")
    stamp_source.add_argument("--manifest", default="", help="Path to a manifest JSON file to stamp into the sandbox.")
    sandbox_stamp_parser.add_argument("--name", default="", help="Optional app name override.")
    sandbox_stamp_parser.add_argument("--vendor-mode", choices=["module_ref", "static"], default="")
    sandbox_stamp_parser.add_argument("--resolution-profile", choices=["app_ready", "strict", "explicit_pack"], default="")
    sandbox_stamp_parser.add_argument("--force", action="store_true", help="Delete and recreate the sandbox workspace if it already exists.")

    sandbox_apply_parser = subparsers.add_parser("sandbox-apply", help="Validate and apply one or more patch manifests to sandbox working/.")
    sandbox_apply_parser.add_argument("workspace", help="Sandbox workspace directory.")
    sandbox_apply_parser.add_argument("patch_manifests", nargs="*", help="Optional patch manifest paths. If omitted, use manifests already staged in sandbox patches/.")
    sandbox_apply_parser.add_argument("--no-backup", action="store_true", help="Do not create .bak files when applying patches in place.")

    sandbox_validate_parser = subparsers.add_parser("sandbox-validate", help="Compile, health-check, and integrity-check sandbox working/.")
    sandbox_validate_parser.add_argument("workspace", help="Sandbox workspace directory.")

    sandbox_promote_parser = subparsers.add_parser("sandbox-promote", help="Copy sandbox working/ to a final destination and validate it.")
    sandbox_promote_parser.add_argument("workspace", help="Sandbox workspace directory.")
    sandbox_promote_parser.add_argument("--destination", required=True, help="Final app destination directory.")
    sandbox_promote_parser.add_argument("--force", action="store_true", help="Replace the destination if it already exists.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "build-catalog":
        report = CatalogBuilder().build()
        print(json.dumps(report, indent=2))
        return 0

    if args.command == "launch-ui":
        CatalogBuilder().build()
        LibrarianApp(LibraryQueryService()).run()
        return 0

    if args.command == "launch-runner-ui":
        PipelineRunnerApp(LibraryQueryService(auto_build=False)).run()
        return 0

    if args.command == "list-templates":
        report = LibraryQueryService().list_templates()
        print(json.dumps(report, indent=2))
        return 0

    if args.command == "stamp":
        manifest = AppBlueprintManifest.from_dict(
            json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        )
        report = AppStamper().stamp(manifest)
        print(json.dumps(report, indent=2))
        return 0 if report["validation"]["ok"] else 1

    if args.command == "template-manifest":
        report = LibraryQueryService().template_blueprint(
            args.template_id,
            destination=args.destination,
            name=args.name,
            vendor_mode=args.vendor_mode or None,
            resolution_profile=args.resolution_profile or None,
        )
        if args.output:
            Path(args.output).write_text(
                json.dumps({key: value for key, value in report.items() if key != "selected_services"}, indent=2),
                encoding="utf-8",
            )
        print(json.dumps(report, indent=2))
        return 0

    if args.command == "stamp-template":
        manifest = LibraryQueryService().template_blueprint(
            args.template_id,
            destination=args.destination,
            name=args.name,
            vendor_mode=args.vendor_mode or None,
            resolution_profile=args.resolution_profile or None,
        )
        report = AppStamper().stamp(manifest)
        print(json.dumps(report, indent=2))
        return 0 if report["validation"]["ok"] else 1

    if args.command == "validate-manifest":
        manifest = AppBlueprintManifest.from_dict(
            json.loads(Path(args.manifest).read_text(encoding="utf-8"))
        )
        report = LibraryQueryService().validate_manifest(manifest)
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    if args.command == "inspect-app":
        report = AppStamper().inspect_app(Path(args.app_dir))
        print(json.dumps(report, indent=2))
        return 0 if not report["errors"] else 1

    if args.command == "upgrade-report":
        report = AppStamper().upgrade_report(Path(args.app_dir))
        print(json.dumps(report, indent=2))
        return 0 if not report["inspection"]["errors"] else 1

    if args.command == "restamp":
        report = AppStamper().restamp_existing_app(
            Path(args.app_dir),
            destination=args.destination or None,
            name=args.name or None,
            vendor_mode=args.vendor_mode or None,
            resolution_profile=args.resolution_profile or None,
            preserve_ui_schema=not args.no_preserve_ui_schema,
        )
        print(json.dumps(report, indent=2))
        return 0 if report["validation"]["ok"] else 1

    if args.command == "verify":
        report = AppStamper().verify_app_integrity(Path(args.app_dir))
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    if args.command == "sandbox-stamp":
        report = SandboxWorkflow().sandbox_stamp(
            run_id=args.run_id,
            template_id=args.template_id or None,
            manifest_path=args.manifest or None,
            sandbox_root=args.sandbox_root or None,
            name=args.name or None,
            vendor_mode=args.vendor_mode or None,
            resolution_profile=args.resolution_profile or None,
            force=args.force,
        )
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    if args.command == "sandbox-apply":
        report = SandboxWorkflow().sandbox_apply(
            args.workspace,
            patch_manifests=args.patch_manifests,
            backup=not args.no_backup,
        )
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    if args.command == "sandbox-validate":
        report = SandboxWorkflow().sandbox_validate(args.workspace)
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    if args.command == "sandbox-promote":
        report = SandboxWorkflow().sandbox_promote(args.workspace, args.destination, force=args.force)
        print(json.dumps(report, indent=2))
        return 0 if report["ok"] else 1

    parser.print_help()
    return 0

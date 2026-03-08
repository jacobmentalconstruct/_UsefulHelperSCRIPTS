import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from library.app_factory.catalog import CatalogBuilder, stable_id
from library.app_factory.constants import canonicalize_sandbox_path
from library.app_factory.models import AppBlueprintManifest
from library.app_factory.packs import InstallPackManager
from library.app_factory.pipeline_runner import SandboxRunConfig, build_sandbox_command_queue
from library.app_factory.query import LibraryQueryService
from library.app_factory.sandbox import SandboxWorkflow
from library.app_factory.stamper import AppStamper
from library.app_factory.ui_schema import UiSchemaPreviewService


class AppFactoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.temp_root = Path(cls._tmp.name)
        cls.repo_root = Path(__file__).resolve().parents[2]
        cls.catalog_db = cls.temp_root / "catalog.db"
        cls.query = LibraryQueryService(catalog_db_path=cls.catalog_db, auto_build=False)
        cls.query.build_catalog(incremental=False)
        cls.stamper = AppStamper(cls.query)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def _app_dir(self, name: str) -> Path:
        path = self.temp_root / name
        if path.exists():
            shutil.rmtree(path)
        return path

    def _run_health(self, app_dir: Path) -> dict:
        result = subprocess.run(
            [sys.executable, "app.py", "--health"],
            cwd=app_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
        return json.loads(result.stdout)

    def _run_cli_json(self, *args: str) -> tuple[int, object]:
        result = subprocess.run(
            [sys.executable, "-m", "library.app_factory", *args],
            cwd=self.repo_root,
            capture_output=True,
            text=True,
            timeout=240,
            check=False,
        )
        payload = json.loads(result.stdout) if result.stdout.strip() else None
        return result.returncode, payload

    def test_catalog_indexes_metadata_and_runtime_dependencies(self):
        archive_bot = self.query.describe_service("ArchiveBotMS")
        self.assertIsNotNone(archive_bot)
        self.assertEqual(archive_bot["service_name"], "ArchiveBot")
        self.assertEqual(archive_bot["version"], "1.1.0")

        explorer_deps = self.query.show_dependencies("ExplorerWidgetMS")
        self.assertIsNotNone(explorer_deps)
        self.assertTrue(
            any(item["target"] == "tkinter_base_pack" for item in explorer_deps["runtime_dependencies"])
        )
        self.assertTrue(explorer_deps["code_dependencies"])

    def test_recommend_blueprint_defaults_headless_and_ui_packs(self):
        headless = self.query.recommend_blueprint(
            ["FingerprintScannerMS"],
            destination=str(self.temp_root / "headless"),
            name="Headless Test",
        )
        self.assertEqual(headless["ui_pack"], "headless_pack")
        self.assertEqual(headless["orchestrator"], "headless_backend_orchestrator")

        ui_manifest = self.query.recommend_blueprint(
            ["ExplorerWidgetMS"],
            destination=str(self.temp_root / "ui"),
            name="UI Test",
        )
        self.assertEqual(ui_manifest["ui_pack"], "tkinter_base_pack")
        self.assertEqual(ui_manifest["orchestrator"], "tkinter_shell_orchestrator")

    def test_template_catalog_and_template_blueprint(self):
        templates = self.query.list_templates()
        template_ids = {item["template_id"] for item in templates}
        self.assertIn("headless_scanner", template_ids)
        self.assertIn("ui_explorer_workbench", template_ids)
        self.assertIn("semantic_pipeline_tool", template_ids)
        self.assertIn("storage_layer_lab", template_ids)
        self.assertIn("manifold_layer_lab", template_ids)

        headless_template = self.query.template_blueprint(
            "headless_scanner",
            destination=str(self.temp_root / "template_headless"),
            name="Template Headless",
        )
        self.assertEqual(headless_template["ui_pack"], "headless_pack")
        self.assertEqual(headless_template["template_id"], "headless_scanner")
        self.assertTrue(self.query.validate_manifest(headless_template)["ok"])

        ui_template = self.query.template_blueprint(
            "ui_explorer_workbench",
            destination=str(self.temp_root / "template_ui"),
            name="Template UI",
        )
        self.assertEqual(ui_template["ui_pack"], "tkinter_base_pack")
        self.assertEqual(ui_template["template_id"], "ui_explorer_workbench")
        self.assertTrue(self.query.validate_manifest(ui_template)["ok"])

    def test_template_blueprint_stamps_successfully(self):
        app_dir = self._app_dir("template_stamp_app")
        manifest = self.query.template_blueprint(
            "headless_scanner",
            destination=str(app_dir),
            name="Template Stamp App",
        )
        report = self.stamper.stamp(manifest)
        self.assertTrue(report["validation"]["ok"], msg=json.dumps(report, indent=2))
        health = self._run_health(app_dir)
        self.assertIn("FingerprintScannerMS", health["deferred"])

    def test_grouped_template_stamps_successfully(self):
        app_dir = self._app_dir("grouped_template_app")
        manifest = self.query.template_blueprint(
            "storage_layer_lab",
            destination=str(app_dir),
            name="Grouped Template App",
        )
        report = self.stamper.stamp(manifest)
        self.assertTrue(report["validation"]["ok"], msg=json.dumps(report, indent=2))
        health = self._run_health(app_dir)
        self.assertIn("Blake3HashMS", health["deferred"])

    def test_validate_manifest_rejects_bad_vendor_mode(self):
        manifest = self.query.recommend_blueprint(
            ["FingerprintScannerMS"],
            destination=str(self.temp_root / "invalid"),
            name="Invalid App",
        )
        manifest["vendor_mode"] = "symlink"
        report = self.query.validate_manifest(manifest)
        self.assertFalse(report["ok"])
        self.assertTrue(any("vendor_mode" in error for error in report["errors"]))

    def test_cli_list_templates_and_stamp_template(self):
        code, templates = self._run_cli_json("list-templates")
        self.assertEqual(code, 0)
        template_ids = {item["template_id"] for item in templates}
        self.assertIn("headless_scanner", template_ids)

        app_dir = self._app_dir("cli_template_app")
        code, stamp_report = self._run_cli_json(
            "stamp-template",
            "headless_scanner",
            "--destination",
            str(app_dir),
            "--name",
            "CLI Template App",
        )
        self.assertEqual(code, 0, msg=json.dumps(stamp_report, indent=2))
        self.assertTrue(stamp_report["validation"]["ok"])

        code, upgrade_report = self._run_cli_json("upgrade-report", str(app_dir))
        self.assertEqual(code, 0, msg=json.dumps(upgrade_report, indent=2))
        self.assertFalse(upgrade_report["upgrade_recommended"])

    def test_module_ref_stamp_boots_and_lock_ignores_ui_schema(self):
        app_dir = self._app_dir("module_ref_app")
        manifest = self.query.recommend_blueprint(
            ["FingerprintScannerMS"],
            destination=str(app_dir),
            name="Module Ref App",
        )
        report = self.stamper.stamp(manifest)
        self.assertTrue(report["validation"]["ok"], msg=json.dumps(report, indent=2))
        self.assertTrue((app_dir / "pyrightconfig.json").exists())
        self.assertTrue((app_dir / ".stamper_lock.json").exists())

        health = self._run_health(app_dir)
        self.assertIn("FingerprintScannerMS", health["deferred"])

        integrity = self.stamper.verify_app_integrity(app_dir)
        self.assertTrue(integrity["ok"], msg=integrity)

        schema_path = app_dir / "ui_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["theme"]["accent"] = "#224466"
        schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        integrity_after_schema = self.stamper.verify_app_integrity(app_dir)
        self.assertTrue(integrity_after_schema["ok"], msg=integrity_after_schema)

        requirements_path = app_dir / "requirements.txt"
        requirements_path.write_text(requirements_path.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")
        integrity_after_requirements = self.stamper.verify_app_integrity(app_dir)
        self.assertFalse(integrity_after_requirements["ok"])
        self.assertTrue(any("requirements.txt" in item for item in integrity_after_requirements["errors"]))

        backend_path = app_dir / "backend.py"
        backend_path.write_text(backend_path.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
        integrity_after_code = self.stamper.verify_app_integrity(app_dir)
        self.assertFalse(integrity_after_code["ok"])
        self.assertTrue(any("backend.py" in item for item in integrity_after_code["errors"]))

    def test_inspect_and_restamp_existing_app_preserves_ui_schema(self):
        app_dir = self._app_dir("restamp_app")
        manifest = self.query.recommend_blueprint(
            ["FingerprintScannerMS"],
            destination=str(app_dir),
            name="Restamp Source App",
        )
        report = self.stamper.stamp(manifest)
        self.assertTrue(report["validation"]["ok"], msg=json.dumps(report, indent=2))

        schema_path = app_dir / "ui_schema.json"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        schema["theme"]["accent"] = "#335577"
        schema_path.write_text(json.dumps(schema, indent=2), encoding="utf-8")
        settings_path = app_dir / "settings.json"
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
        settings["assistant"]["enabled"] = True
        settings["assistant"]["model_name"] = "qwen2.5-coder:3b"
        settings["custom_runtime_flag"] = "keep-me"
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

        inspect_clean = self.stamper.inspect_app(app_dir)
        self.assertTrue(inspect_clean["manifest_hash_matches_lock"])
        self.assertFalse(inspect_clean["restamp_recommended"])
        upgrade_clean = self.stamper.upgrade_report(app_dir)
        self.assertFalse(upgrade_clean["upgrade_recommended"])
        self.assertFalse(upgrade_clean["artifact_changes"]["changed"])

        manifest_path = app_dir / "app_manifest.json"
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_payload["name"] = "Restamped Name"
        manifest_path.write_text(json.dumps(manifest_payload, indent=2), encoding="utf-8")

        inspect_dirty = self.stamper.inspect_app(app_dir)
        self.assertFalse(inspect_dirty["manifest_hash_matches_lock"])
        self.assertTrue(inspect_dirty["restamp_recommended"])

        restamp_report = self.stamper.restamp_existing_app(app_dir)
        self.assertTrue(restamp_report["validation"]["ok"], msg=json.dumps(restamp_report, indent=2))
        self.assertTrue(restamp_report["preserved_ui_schema"])

        restamped_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(restamped_manifest["name"], "Restamped Name")
        restamped_schema = json.loads(schema_path.read_text(encoding="utf-8"))
        self.assertEqual(restamped_schema["theme"]["accent"], "#335577")
        restamped_settings = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertTrue(restamped_settings["assistant"]["enabled"])
        self.assertEqual(restamped_settings["assistant"]["model_name"], "qwen2.5-coder:3b")
        self.assertEqual(restamped_settings["custom_runtime_flag"], "keep-me")

        inspect_after = self.stamper.inspect_app(app_dir)
        self.assertTrue(inspect_after["manifest_hash_matches_lock"])
        self.assertFalse(inspect_after["restamp_recommended"])

    def test_upgrade_report_detects_locked_artifact_delta(self):
        app_dir = self._app_dir("upgrade_report_app")
        manifest = self.query.recommend_blueprint(
            ["FingerprintScannerMS"],
            destination=str(app_dir),
            name="Upgrade Report App",
        )
        report = self.stamper.stamp(manifest)
        self.assertTrue(report["validation"]["ok"], msg=json.dumps(report, indent=2))

        lock_path = app_dir / ".stamper_lock.json"
        lock_payload = json.loads(lock_path.read_text(encoding="utf-8"))
        lock_payload["resolved_library_artifacts"][0]["file_cid"] = "bogus-cid"
        lock_path.write_text(json.dumps(lock_payload, indent=2), encoding="utf-8")

        upgrade_report = self.stamper.upgrade_report(app_dir)
        self.assertTrue(upgrade_report["upgrade_recommended"])
        self.assertEqual(len(upgrade_report["artifact_changes"]["changed"]), 1)
        self.assertFalse(upgrade_report["artifact_changes"]["added"])
        self.assertFalse(upgrade_report["artifact_changes"]["removed"])

    def test_static_stamp_is_self_contained_and_boots(self):
        app_dir = self._app_dir("static_app")
        manifest = self.query.recommend_blueprint(
            ["FingerprintScannerMS"],
            destination=str(app_dir),
            name="Static App",
            vendor_mode="static",
        )
        report = self.stamper.stamp(manifest)
        self.assertTrue(report["validation"]["ok"], msg=json.dumps(report, indent=2))
        self.assertTrue((app_dir / "vendor" / "library" / "microservices" / "core" / "_FingerprintScannerMS.py").exists())

        health = self._run_health(app_dir)
        self.assertIn("FingerprintScannerMS", health["deferred"])

    def test_filtered_external_dependencies_exclude_ttk(self):
        app_dir = self._app_dir("ui_requirements_app")
        manifest = self.query.recommend_blueprint(
            ["ExplorerWidgetMS"],
            destination=str(app_dir),
            name="UI Requirements App",
        )
        report = self.stamper.stamp(manifest)
        self.assertTrue(report["validation"]["ok"], msg=json.dumps(report, indent=2))
        requirements_text = (app_dir / "requirements.txt").read_text(encoding="utf-8")
        self.assertNotIn("ttk", requirements_text)

    def test_cycle_detection_warns_and_terminates(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            catalog_db = temp_dir / "cycle.db"
            builder = CatalogBuilder(catalog_db_path=catalog_db)
            conn = sqlite3.connect(catalog_db)
            conn.row_factory = sqlite3.Row
            builder._ensure_schema(conn)

            artifact_a = stable_id("artifact", "library.fake.a")
            artifact_b = stable_id("artifact", "library.fake.b")
            service_a = stable_id("service", artifact_a, "ServiceA")
            service_b = stable_id("service", artifact_b, "ServiceB")

            conn.execute(
                "INSERT INTO artifacts (artifact_id, parent_artifact_id, source_path, kind, import_key, file_cid, size_bytes, mtime_ns, is_deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (artifact_a, None, str(temp_dir / "a.py"), "module", "library.fake.a", "cid-a", 1, 1),
            )
            conn.execute(
                "INSERT INTO artifacts (artifact_id, parent_artifact_id, source_path, kind, import_key, file_cid, size_bytes, mtime_ns, is_deleted) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
                (artifact_b, None, str(temp_dir / "b.py"), "module", "library.fake.b", "cid-b", 1, 1),
            )
            conn.execute(
                "INSERT INTO services (service_id, artifact_id, class_name, service_name, version, layer, description, tags_json, capabilities_json, side_effects_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (service_a, artifact_a, "ServiceA", "ServiceA", "1.0.0", "core", "", "[]", "[]", "[]"),
            )
            conn.execute(
                "INSERT INTO services (service_id, artifact_id, class_name, service_name, version, layer, description, tags_json, capabilities_json, side_effects_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (service_b, artifact_b, "ServiceB", "ServiceB", "1.0.0", "core", "", "[]", "[]", "[]"),
            )
            conn.execute(
                "INSERT INTO dependencies (dependency_id, src_service_id, src_artifact_id, dst_service_id, dst_artifact_id, external_name, pack_name, dependency_type, evidence_type, evidence_json, is_resolved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (stable_id("dep", service_a, service_b), service_a, None, service_b, None, None, None, "requires_code", "test", '{"ref": "ServiceB"}', 1),
            )
            conn.execute(
                "INSERT INTO dependencies (dependency_id, src_service_id, src_artifact_id, dst_service_id, dst_artifact_id, external_name, pack_name, dependency_type, evidence_type, evidence_json, is_resolved) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (stable_id("dep", service_b, service_a), service_b, None, service_a, None, None, None, "requires_code", "test", '{"ref": "ServiceA"}', 1),
            )
            conn.commit()
            conn.close()

            query = LibraryQueryService(catalog_db_path=catalog_db, auto_build=False)
            stamper = AppStamper(query)
            manifest = AppBlueprintManifest(
                app_id="cycle-app",
                name="Cycle App",
                destination=str(temp_dir / "cycle_app"),
                microservices=["ServiceA"],
            )

            resolved = stamper._resolve_manifest(manifest)
            self.assertTrue(resolved["validation"].cycle_warnings)
            self.assertFalse(resolved["validation"].errors)

    def test_install_pack_skips_collisions_and_rebuilds_catalog(self):
        with tempfile.TemporaryDirectory() as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            library_root = temp_dir / "library"
            (library_root / "__init__.py").parent.mkdir(parents=True, exist_ok=True)
            (library_root / "__init__.py").write_text("", encoding="utf-8")

            builder = CatalogBuilder(
                library_root=library_root,
                catalog_db_path=temp_dir / "catalog.db",
                mapping_report_path=temp_dir / "mapping.json",
            )
            builder.build(incremental=False)
            manager = InstallPackManager(builder, library_root=library_root)

            pack_one = temp_dir / "pack_one" / "library" / "microservices" / "core"
            pack_one.mkdir(parents=True, exist_ok=True)
            (pack_one.parent / "__init__.py").write_text("", encoding="utf-8")
            (pack_one / "__init__.py").write_text("", encoding="utf-8")
            (pack_one / "_PackDemoMS.py").write_text(
                "from microservice_std_lib import service_metadata\n\n"
                "@service_metadata(name='PackDemo', version='1.0.0', description='demo', tags=['test'])\n"
                "class PackDemoMS:\n"
                "    pass\n",
                encoding="utf-8",
            )

            report_one = manager.install(pack_one.parents[2])
            self.assertTrue(report_one["copied"])
            self.assertFalse(report_one["collisions"])
            installed_file = library_root / "microservices" / "core" / "_PackDemoMS.py"
            self.assertTrue(installed_file.exists())

            pack_two = temp_dir / "pack_two" / "library" / "microservices" / "core"
            pack_two.mkdir(parents=True, exist_ok=True)
            (pack_two.parent / "__init__.py").write_text("", encoding="utf-8")
            (pack_two / "__init__.py").write_text("", encoding="utf-8")
            (pack_two / "_PackDemoMS.py").write_text(
                "from microservice_std_lib import service_metadata\n\n"
                "@service_metadata(name='PackDemo', version='2.0.0', description='demo', tags=['test'])\n"
                "class PackDemoMS:\n"
                "    pass\n",
                encoding="utf-8",
            )

            report_two = manager.install(pack_two.parents[2])
            self.assertFalse(report_two["copied"])
            self.assertTrue(report_two["collisions"])
            self.assertIn(str(installed_file), report_two["collisions"])
            self.assertIn("1.0.0", installed_file.read_text(encoding="utf-8"))


    def test_default_schema_uses_foundry_palette(self):
        preview = UiSchemaPreviewService()
        schema = preview.default_schema('tkinter_base_pack')
        theme = schema['theme']
        self.assertEqual(theme['background'], '#14181D')
        self.assertEqual(theme['accent'], '#C9773B')
        self.assertEqual(theme['panel_bg'], '#10161E')

    def test_build_sandbox_command_queue(self):
        patch_manifest = self.temp_root / 'runner_patch.json'
        patch_manifest.write_text('{}', encoding='utf-8')
        config = SandboxRunConfig(
            run_id='runner_case',
            template_id='ui_explorer_workbench',
            name='Runner Case',
            sandbox_root=str(self.temp_root / 'runner_sandbox'),
            patch_manifests=[str(patch_manifest)],
            promote_destination=str(self.temp_root / 'runner_promoted' / 'runner_case'),
        )
        plan = build_sandbox_command_queue(config)
        self.assertEqual(len(plan['commands']), 4)
        self.assertIn('sandbox-stamp', plan['display_commands'][0])
        self.assertIn('sandbox-apply', plan['display_commands'][1])
        self.assertNotIn(str(patch_manifest.resolve()), plan['display_commands'][1])
        self.assertIn('/inputs/patch0/runner_patch.json', plan['display_commands'][1])
        self.assertIn('sandbox-promote', plan['display_commands'][3])
        self.assertTrue(plan['workspace_root'].endswith('runner_case'))
        self.assertEqual(plan['display_workspace_root'], '/workspace/apps/runner_case')

    def test_build_docker_sandbox_command_queue(self):
        patch_manifest = self.temp_root / 'docker_runner_patch.json'
        patch_manifest.write_text('{}', encoding='utf-8')
        docker_sandbox_root = self.repo_root / '_sandbox' / 'apps'
        with mock.patch('library.app_factory.pipeline_runner.docker_preflight', return_value={
            'available': True,
            'binary_path': 'docker',
            'server_version': '27.0.0',
            'user_message': 'Docker ready (27.0.0).',
        }):
            config = SandboxRunConfig(
                run_id='docker_runner_case',
                template_id='ui_explorer_workbench',
                name='Docker Runner Case',
                sandbox_root=str(docker_sandbox_root),
                patch_manifests=[str(patch_manifest)],
                promote_destination=str(self.repo_root / '_sandbox' / 'promoted' / 'docker_runner_case'),
                vendor_mode='static',
                execution_backend='docker',
            )
            plan = build_sandbox_command_queue(config)
        self.assertEqual(plan['execution_backend'], 'docker')
        self.assertEqual(len(plan['commands']), 4)
        self.assertEqual(plan['display_workspace_root'], '/workspace/apps/docker_runner_case')
        self.assertIn('[docker] python -m library.app_factory sandbox-stamp', plan['display_commands'][0])
        self.assertIn('/inputs/patch0/docker_runner_patch.json', plan['display_commands'][1])
        self.assertEqual(plan['commands'][0].args[0], 'docker')
        self.assertIn('sandbox-promote', plan['display_commands'][3])

    def test_build_docker_sandbox_command_queue_requires_host_approval(self):
        with mock.patch('library.app_factory.pipeline_runner.docker_preflight', return_value={
            'available': True,
            'binary_path': 'docker',
            'server_version': '27.0.0',
            'user_message': 'Docker ready (27.0.0).',
        }):
            config = SandboxRunConfig(
                run_id='docker_runner_case',
                template_id='ui_explorer_workbench',
                sandbox_root=str(self.repo_root / '_sandbox' / 'apps'),
                promote_destination=str(self.temp_root / 'outside' / 'app'),
                vendor_mode='static',
                execution_backend='docker',
                allow_host_writes=False,
            )
            with self.assertRaises(ValueError):
                build_sandbox_command_queue(config)

    def test_legacy_sanbox_paths_remap_to_canonical_sandbox(self):
        legacy_apps_root = self.repo_root / '_sanbox' / 'apps'
        legacy_promoted_root = self.repo_root / '_sanbox' / 'promoted'
        config = SandboxRunConfig(
            run_id='legacy_case',
            template_id='ui_explorer_workbench',
            sandbox_root=str(legacy_apps_root),
            promote_destination=str(legacy_promoted_root / 'legacy_case'),
        )
        self.assertEqual(
            config.resolved_sandbox_root(),
            (self.repo_root / '_sandbox' / 'apps').resolve(),
        )
        self.assertEqual(
            config.resolved_promote_destination(),
            (self.repo_root / '_sandbox' / 'promoted' / 'legacy_case').resolve(),
        )
        self.assertEqual(
            canonicalize_sandbox_path(legacy_apps_root / 'legacy_case'),
            (self.repo_root / '_sandbox' / 'apps' / 'legacy_case').resolve(),
        )

    def test_query_service_uses_catalog_env_override(self):
        custom_catalog = self.temp_root / 'env_catalog.db'
        with mock.patch.dict('os.environ', {'APP_FOUNDRY_CATALOG_DB_PATH': str(custom_catalog)}):
            query = LibraryQueryService(auto_build=False)
        self.assertEqual(query.catalog_db_path, custom_catalog.resolve())

    def test_sandbox_workflow_generates_transform_lock_and_promotes(self):
        sandbox_root = self.temp_root / "sandbox_workflow"
        workflow = SandboxWorkflow(
            self.query,
            sandbox_root=sandbox_root,
            patcher_script=self.repo_root / "_curationTOOLS" / "tokenizing_patcher_with_cli.py",
        )
        stamp_report = workflow.sandbox_stamp(
            run_id="ui_case",
            template_id="ui_explorer_workbench",
            name="Sandbox Workflow App",
            force=True,
        )
        self.assertTrue(stamp_report["ok"], msg=json.dumps(stamp_report, indent=2))
        workspace_root = Path(stamp_report["workspace_root"])
        working_dir = Path(stamp_report["working_app_dir"])
        working_manifest = json.loads((working_dir / "app_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(working_manifest["destination"], str(working_dir))
        self.assertTrue(self.stamper.verify_app_integrity(working_dir)["ok"])

        patch_manifest = self.temp_root / "sandbox_transform_patch.json"
        patch_manifest.write_text(
            json.dumps(
                {
                    "files": [
                        {
                            "path": "app.py",
                            "hunks": [
                                {
                                    "description": "Tag headless sandbox workflow output",
                                    "search_block": '        print(json.dumps(run_headless(runtime), indent=2))\n',
                                    "replace_block": '        print(json.dumps({"status": "sandbox-workflow", "payload": run_headless(runtime)}, indent=2))\n',
                                    "use_patch_indent": False,
                                }
                            ],
                        },
                        {
                            "path": "settings.json",
                            "hunks": [
                                {
                                    "description": "Retitle sandbox app",
                                    "search_block": '  "app_title": "Sandbox Workflow App",\n',
                                    "replace_block": '  "app_title": "Sandbox Workflow App Patched",\n',
                                    "use_patch_indent": False,
                                }
                            ],
                        },
                        {
                            "path": "ui_schema.json",
                            "hunks": [
                                {
                                    "description": "Adjust accent token",
                                    "search_block": '    "accent": "#C9773B",\n',
                                    "replace_block": '    "accent": "#C56D3A",\n',
                                    "use_patch_indent": False,
                                }
                            ],
                        },
                    ]
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        apply_report = workflow.sandbox_apply(workspace_root, [patch_manifest], backup=False)
        self.assertTrue(apply_report["ok"], msg=json.dumps(apply_report, indent=2))
        self.assertTrue((working_dir / ".transform_lock.json").exists())
        stamp_integrity_after_patch = self.stamper.verify_app_integrity(working_dir)
        self.assertFalse(stamp_integrity_after_patch["ok"])

        validate_report = workflow.sandbox_validate(workspace_root)
        self.assertTrue(validate_report["ok"], msg=json.dumps(validate_report, indent=2))
        self.assertEqual(validate_report["active_integrity"], "transform")
        self.assertTrue(validate_report["transform_integrity"]["ok"])

        promoted_dir = self._app_dir("sandbox_promoted_app")
        promote_report = workflow.sandbox_promote(workspace_root, promoted_dir)
        self.assertTrue(promote_report["ok"], msg=json.dumps(promote_report, indent=2))
        promoted_manifest = json.loads((promoted_dir / "app_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(promoted_manifest["destination"], str(promoted_dir))
        self.assertTrue((promoted_dir / ".transform_lock.json").exists())
        promoted_validate = workflow.verify_transform_lock(promoted_dir)
        self.assertTrue(promoted_validate["ok"], msg=json.dumps(promoted_validate, indent=2))

    def test_cli_sandbox_stamp_and_promote(self):
        sandbox_root = self.temp_root / "cli_sandbox"
        code, stamp_report = self._run_cli_json(
            "sandbox-stamp",
            "--run-id",
            "cli_case",
            "--template-id",
            "headless_scanner",
            "--sandbox-root",
            str(sandbox_root),
            "--name",
            "CLI Sandbox App",
        )
        self.assertEqual(code, 0, msg=json.dumps(stamp_report, indent=2))
        workspace_root = Path(stamp_report["workspace_root"])

        patch_manifest = self.temp_root / "cli_sandbox_patch.json"
        patch_manifest.write_text(
            json.dumps(
                {
                    "default_use_patch_indent": True,
                    "files": [
                        {
                            "path": "settings.json",
                            "hunks": [
                                {
                                    "description": "Retitle CLI sandbox app",
                                    "search_block": '  "app_title": "CLI Sandbox App",\n',
                                    "replace_block": '  "app_title": "CLI Sandbox App Patched",\n',
                                }
                            ],
                        },
                        {
                            "path": "app.py",
                            "hunks": [
                                {
                                    "description": "Retitle headless status for CLI sandbox validation",
                                    "search_block": '        print(json.dumps(run_headless(runtime), indent=2))\n',
                                    "replace_block": '        print(json.dumps({"status": "cli-sandbox", "payload": run_headless(runtime)}, indent=2))\n',
                                }
                            ],
                        },
                    ],
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        code, apply_report = self._run_cli_json("sandbox-apply", str(workspace_root), str(patch_manifest))
        self.assertEqual(code, 0, msg=json.dumps(apply_report, indent=2))
        self.assertTrue(apply_report["ok"], msg=json.dumps(apply_report, indent=2))

        code, validate_report = self._run_cli_json("sandbox-validate", str(workspace_root))
        self.assertEqual(code, 0, msg=json.dumps(validate_report, indent=2))
        self.assertTrue(validate_report["ok"], msg=json.dumps(validate_report, indent=2))
        self.assertEqual(validate_report["active_integrity"], "transform")

        promoted_dir = self._app_dir("cli_sandbox_promoted")
        code, promote_report = self._run_cli_json(
            "sandbox-promote",
            str(workspace_root),
            "--destination",
            str(promoted_dir),
        )
        self.assertEqual(code, 0, msg=json.dumps(promote_report, indent=2))
        self.assertTrue(promote_report["ok"], msg=json.dumps(promote_report, indent=2))
        self.assertTrue((promoted_dir / ".transform_lock.json").exists())


if __name__ == "__main__":
    unittest.main()



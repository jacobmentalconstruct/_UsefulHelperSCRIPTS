# App Factory

Deterministic catalog, librarian, template, and app-stamping tooling for the canonical `library/` package.

## Scope

This v1 flow is filesystem-canonical and static-analysis driven:

- `library/` is the source of truth
- `library/catalog/catalog.db` is a derived index
- manifests define stamped apps
- templates provide starter app shapes
- the assistant is optional

## Core Commands

Build or refresh the catalog:

```powershell
python -m library.app_factory build-catalog
```

List built-in templates:

```powershell
python -m library.app_factory list-templates
```

Generate a manifest from a template:

```powershell
python -m library.app_factory template-manifest ui_explorer_workbench --destination _design-docs\template_ui_app --name "Template UI App"
```

Stamp directly from a template:

```powershell
python -m library.app_factory stamp-template headless_scanner --destination _design-docs\template_stamp_smoke --name "Template Stamp Smoke"
```

Validate a manifest before stamping:

```powershell
python -m library.app_factory validate-manifest path\to\app_manifest.json
```

Stamp from an explicit manifest:

```powershell
python -m library.app_factory stamp path\to\app_manifest.json
```

Inspect a stamped app:

```powershell
python -m library.app_factory inspect-app _design-docs\stamped_smoke
```

Compare a stamped app against the current catalog resolution:

```powershell
python -m library.app_factory upgrade-report _design-docs\stamped_smoke
```

Verify lockfile integrity:

```powershell
python -m library.app_factory verify _design-docs\stamped_smoke
```

Restamp an existing app from its `app_manifest.json`:

```powershell
python -m library.app_factory restamp _design-docs\stamped_smoke
```

## Sandbox Workflow

Use the sandbox commands when you want to stamp a deterministic base app, apply multi-file tokenizing patches, validate the transformed result, and only then promote it.

Stamp a workspace from a template or manifest:

```powershell
python -m library.app_factory sandbox-stamp --run-id demo_case --template-id ui_explorer_workbench --force
```

Apply one or more multi-file patch manifests:

```powershell
python -m library.app_factory sandbox-apply _sanbox\apps\demo_case path\to\patch_manifest.json
```

Validate the transformed workspace:

```powershell
python -m library.app_factory sandbox-validate _sanbox\apps\demo_case
```

Promote the validated working app into a final destination:

```powershell
python -m library.app_factory sandbox-promote _sanbox\apps\demo_case --destination _sanbox\promoted\demo_case --force
```

The sandbox workflow writes `.transform_lock.json` after patch application. That lock extends the original stamp lock to include transformed Python files, runtime config, and copied patch manifests.

### Patcher Indentation Defaults

The tokenizing patcher now supports `default_use_patch_indent` at both the manifest root and per-file entry level. That is the safer default for Python-heavy multi-file transforms because hunks can preserve their literal indentation without having to repeat `use_patch_indent` on every hunk. A hunk can still override the default explicitly.

Launch the Tk librarian UI:

```powershell
python -m library.app_factory launch-ui
```

Launch the pipeline runner UI:

```powershell
python -m library.app_factory launch-runner-ui
```

## Catalog UI

The `Catalog` tab now uses a split inspector layout:

- left: layer filter, service list, actions
- right top: stable service summary
- right middle: detail tabs for:
  - `Overview`
  - `Endpoints`
  - `Dependencies`
  - `Source`
  - `Raw JSON`
- right bottom: `Results` panel for action output

The service list also supports a right-click menu for contextual actions such as inspect, explain, dependency lookup, and blueprint recommendation.

## Pipeline Runner UI

The runner UI is a separate Tk surface for demo and operator workflows. It builds a queue of real sandbox commands, renders them into a terminal-style pane, streams stdout/stderr live, and writes JSONL replay logs under `_sanbox/runs/`.

It now supports two execution backends:

- `local`: runs commands on the host, but redacts displayed paths in the queue and terminal
- `docker`: runs stamp/apply/validate in a container, forces `static` vendoring, mounts the repo read-only at `/repo`, mounts `_sanbox` writable at `/workspace`, and leaves host promotion as a separate approval-gated step when the target is outside `_sanbox`

If Docker is missing or the daemon is not running, the runner surfaces a clear remediation message instead of a raw subprocess failure.

Use it when you want to drive:

- `sandbox-stamp`
- `sandbox-apply`
- `sandbox-validate`
- `sandbox-promote`

from one window while preserving a reproducible command trail.

## Privacy Scrub Surface

Primary files and artifacts to audit when you want to reduce path disclosure further:

- `library/app_factory/stamper.py`
- `library/app_factory/sandbox.py`
- `library/app_factory/pipeline_runner.py`
- `library/app_factory/runner_ui.py`
- stamped app `settings.json`
- stamped app `.stamper_lock.json`
- transformed app `.transform_lock.json`
- stamped app `app_manifest.json`
- `library/catalog/catalog.db` source-path fields

Fields to watch in particular:

- `source_path`
- `target_path`
- `canonical_import_root`
- `compat_paths`
- rendered command lines
- serialized sandbox reports

## Boilerplate Theme

Fresh Tk starter apps now stamp with the foundry palette by default through `ui_schema.json` and the generated `ui.py` template. That gives the base app the same graphite/copper/teal direction as the librarian and runner UIs.

## Vendor Modes

- `module_ref`
  - default dev mode
  - stamped app imports from the canonical library path
  - app writes `settings.json`, `.env`, and `pyrightconfig.json`
- `static`
  - deployment/export mode
  - resolved library artifacts are copied under `vendor/`

## Restamp Policy

Current restamp behavior:

- preserves `ui_schema.json`
- preserves existing `assistant` settings
- preserves unknown user-owned top-level settings keys
- rewrites generated bootstrap settings such as:
  - `canonical_import_root`
  - `compat_paths`
  - `catalog_db_path`
  - `vendor_mode`
  - `ui_pack`
  - `app_title`

## Integrity Policy

Lockfiles enforce:

- generated Python files
- generated support files:
  - `requirements.txt`
  - `pyrightconfig.json`
  - `.env`
- resolved library artifacts

Lockfiles do not enforce:

- `ui_schema.json`
- mutable runtime settings outside generated bootstrap fields

## Template Set

Current built-in templates:

- `headless_scanner`
- `ui_explorer_workbench`
- `semantic_pipeline_tool`
- `storage_layer_lab`
- `manifold_layer_lab`

## Test Status

Automated regression coverage currently validates:

- catalog build and metadata extraction
- dependency buckets
- template generation
- `module_ref` and `static` stamping
- integrity verification
- inspect / upgrade-report / restamp flow
- pack install collision handling

See [_design-docs/TEST_PHASE_CHECKLIST.md](C:/Users/jacob/Documents/_UsefulHelperSCRIPTS/_MicroserviceLIBRARY/_design-docs/TEST_PHASE_CHECKLIST.md) for the manual test-phase checklist.

# AppFoundry

Layered microservice library, catalog, and app-stamping toolkit for building Python/Tkinter applications from reusable parts.

## What This Repo Contains

- `library/`
  - canonical source for microservices, managers, orchestrators, modules, and the app factory
- `library/app_factory/`
  - catalog builder
  - query layer
  - Tk librarian UI
  - pipeline runner UI
  - manifest validator
  - app stamper
- `library/catalog/`
  - derived catalog artifacts such as `catalog.db`
- `_design-docs/`
  - design notes, smoke outputs, and test-phase checklist
- `_curationTOOLS/`
  - migration and patch tooling

## Quick Start

1. Create or refresh the local virtual environment:

```bat
setup_env.bat
```

2. Launch the Tk librarian UI:

```bat
run.bat
```

3. Launch the sandbox runner UI:

```bat
run_sanboxer.bat
```

4. Or use the CLI directly:

```powershell
python -m library.app_factory --help
```

## Common Commands

Build or refresh the catalog:

```powershell
python -m library.app_factory build-catalog
```

List built-in starter templates:

```powershell
python -m library.app_factory list-templates
```

Launch the librarian UI:

```powershell
python -m library.app_factory launch-ui
```

Launch the pipeline runner UI:

```powershell
python -m library.app_factory launch-runner-ui
```

Stamp a starter app:

```powershell
python -m library.app_factory stamp-template headless_scanner --destination _design-docs\qa_headless --name "QA Headless"
```

Run the sandbox workflow end to end:

```powershell
python -m library.app_factory sandbox-stamp --run-id foundry_project_lens_20260307 --manifest _sanbox\manifests\foundry_project_lens_20260307.json --force
python -m library.app_factory sandbox-apply _sanbox\apps\foundry_project_lens_20260307 _sanbox\apps\foundry_project_lens_20260307\patches\project_lens_transform.json
python -m library.app_factory sandbox-validate _sanbox\apps\foundry_project_lens_20260307
python -m library.app_factory sandbox-promote _sanbox\apps\foundry_project_lens_20260307 --destination _sanbox\promoted\foundry_project_lens_20260307 --force
```

## Notes

- The canonical code lives under `library/`.
- Root-level compatibility shims are kept for legacy import paths.
- The core librarian/catalog/stamper flow does not require third-party Python packages beyond a standard Python installation with Tkinter.
- Ollama is optional and only used for assistant features.
- Newly stamped Tk apps now default to the foundry palette in `ui_schema.json`.
- The pipeline runner supports `local` and `docker` backends. Docker mode forces `static` vendoring, redacts displayed paths to logical `/repo` and `/workspace` roots, and requires explicit approval before promoting outside `_sanbox`.
- If Docker is not installed or the daemon is not running, the runner shows clear remediation text instead of failing with a raw subprocess error.
- Some microservices import optional third-party packages for specialized workflows. Those are documented in `requirements.txt` but are not required for launching the librarian UI.

## Manual Test Checklist

See [_design-docs/TEST_PHASE_CHECKLIST.md](C:/Users/jacob/Documents/_UsefulHelperSCRIPTS/_MicroserviceLIBRARY/_design-docs/TEST_PHASE_CHECKLIST.md).

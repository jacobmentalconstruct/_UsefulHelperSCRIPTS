# Test Phase Checklist

Use this checklist before calling the app-factory flow test-ready.

## Automated Baseline

Run:

```powershell
python -m unittest library.tests.test_app_factory -v
python -m library.app_factory build-catalog
python -m library.app_factory list-templates
```

Expected:

- all tests pass
- catalog builds without errors
- template list returns the current built-in template set

## CLI Flow

Run:

```powershell
python -m library.app_factory stamp-template headless_scanner --destination _design-docs\qa_headless --name "QA Headless"
python -m library.app_factory inspect-app _design-docs\qa_headless
python -m library.app_factory upgrade-report _design-docs\qa_headless
python -m library.app_factory verify _design-docs\qa_headless
python -m library.app_factory restamp _design-docs\qa_headless
```

Check:

- stamp succeeds
- inspect shows no blocking errors
- upgrade report shows no unexpected artifact drift immediately after stamping
- verify returns `ok: true`
- restamp succeeds and preserves `ui_schema.json`

## Tk Librarian Manual Pass

Launch:

```powershell
python -m library.app_factory launch-ui
```

Manual checks:

1. `Catalog` tab
   - rebuild catalog
   - select a service
   - confirm the summary panel updates without losing prior action output
   - inspect `Overview`, `Endpoints`, `Dependencies`, `Source`, and `Raw JSON`
   - use right-click on a service and run `Explain Selected Service`
   - show dependencies
   - list UI components
   - list orchestrators
   - list managers

2. `Manifest` tab
   - load a template
   - validate the manifest
   - stamp from template
   - load destination app
   - inspect destination app
   - upgrade report
   - restamp existing app
   - preview schema

3. `Packs` tab
   - browse a local folder or zip
   - install pack
   - confirm collisions are reported instead of overwritten

4. `Assistant` tab
   - refresh models
   - confirm no crash if Ollama is unavailable

## Runtime Checks

For at least one `module_ref` app and one `static` app:

```powershell
python app.py --health
python app.py --no-ui
```

Check:

- process exits cleanly
- health JSON is returned
- no import errors

## Drift Checks

1. Change `ui_schema.json`
   - `verify` should still pass
2. Change `backend.py`
   - `verify` should fail
3. Change `requirements.txt`
   - `verify` should fail

## Signoff Conditions

Call the system test-ready when:

- automated tests pass
- CLI flow passes
- one manual Tk pass completes without blocker defects
- `module_ref` and `static` health checks pass
- verify/inspect/upgrade-report/restamp all behave as expected

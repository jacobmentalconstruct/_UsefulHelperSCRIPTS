# ProjectMapper Snapshot Compiler

ProjectMapper Snapshot Compiler is a small desktop utility for translating a project folder into a portable SQLite snapshot. It is intended to make project state easier to inspect, share, archive, and hand off to agents or other tools.

The app scans a selected root folder, displays the project tree, allows files and folders to be included or excluded, and compiles the selected project state into a SQLite database.

![ProjectMapper screenshot](assets/Screenshots/Screenshot_ex01.PNG)

## Core Purpose

ProjectMapper creates a point-in-time project snapshot that can include:

- Project folder structure
- Selected text-readable file contents
- Inclusion and exclusion state
- Skipped path records
- Exclusion rules
- Local environment hints
- Embedded snapshot manifest
- Optional markdown projections
- Optional binary blob preservation for backup/rehydration use

The SQLite snapshot is the primary truth source. Markdown exports are derived views intended for easier reading or sharing.

## Main Workflow

1. Choose a project root folder.
2. Review the generated folder tree.
3. Check or uncheck files and folders as needed.
4. Add exclusion patterns if necessary.
5. Compile the SQLite snapshot.
6. Optionally export markdown views:
   - Project tree
   - Filedump
   - Combined tree and filedump

## Managing Exclusions

Click **Exclusions** to open the resizable rule manager. It lists built-in rules,
custom filename patterns, and supported rules imported from the current root's
`.gitignore`, with their source and match type.

- Check **Exclude (hide)** to hide matching files/folders from the mapper. Uncheck it
  to allow matches, unless another rule excludes them. The tree refreshes automatically.
- Use **Select** to choose rows for batch actions without changing what the mapper shows.
- **Select All** and **Deselect All** change the row selection.
- **Exclude Selected** turns on the selected exclusion rules; **Allow Selected** turns
  them off. **Delete Selected** removes the selected rules.
- Add a filename pattern such as `*.tmp` directly in the manager. Patterns use
  wildcards, not regular expressions.

Changes last for the current app session. Deleting an imported rule removes it
from the app's exclusion policy without editing `.gitignore`; rescanning does not
restore it during that session. Overrides for imported rules are scoped to their
project root. Built-in and custom rule changes apply across roots in the session.
Unchecking the main **Apply exclusions (hide matches)** switch allows matches without
clearing the individual rule checkboxes. A path matching multiple rules remains
excluded until all matching rules are disabled or deleted. Compile a new snapshot
after changing exclusions to capture the updated tree and rule states.

## Blank-Slate Vendor Export

ProjectMapper can export a clean, vendible copy of itself for external testing.
This is separate from project snapshot exports. It creates an installable app
folder and zip under `vendor_exports/` with no Git history, virtual environment,
Python caches, previous `_projectmapper` records, SQLite snapshot databases,
logs, local `.env*` files, or generated export history.

From the UI, use:

```text
Export Vendor App
```

From the command line:

```bash
python tools/export_vendor_app.py
```

The generated package includes an `INSTALL_FRESH_START.md` file for testers.
The expected fresh-start test is:

1. Copy or unzip the vendor export into a blank external test project.
2. Run `setup_env.bat`.
3. Run `run.bat`.
4. Choose a project root in the app and compile a new snapshot.

New test records are created only when the exported app is run against a chosen
project root.

## Snapshot Outputs

By default, ProjectMapper writes outputs to a `_projectmapper` folder inside the selected project root.

Typical outputs include:

```text
<ProjectName>_snapshot.sqlite3
<ProjectName>_project_tree.md
<ProjectName>_project_filedump.md
<ProjectName>_project_tree_and_filedump.md
```

## SQLite Snapshot Contents

The snapshot database may include tables such as:

```text
snapshot_metadata
snapshot_manifest
project_tree
project_files
project_blobs
snapshot_exclusion_rules
snapshot_skipped_paths
snapshot_mapper_state
snapshot_environment
snapshot_outputs
snapshot_errors
```

`project_files` stores selected text-readable files.

`project_blobs` is optional and is used only when binary blob preservation is enabled.

## Markdown Exports

The project tree export is useful as a lightweight surface map of the project. It can be shared without including the full file contents, allowing an agent or reviewer to see the project shape and request specific follow-up files when needed.

The filedump export contains selected captured text files.

The combined export places the project tree before the filedump for easier single-document handoff.

## Binary Preservation

Binary blob preservation is optional and disabled by default.

When enabled, selected binary-like files can be stored in the SQLite snapshot as blobs. This allows the snapshot to serve more like a backup or rehydration artifact, while the default mode remains lighter and more suitable for agent communication.

## Running

From the project root:

```bash
python src/app.py
```

Or, depending on the local environment:

```bash
py src/app.py
```

## Notes

ProjectMapper is currently implemented as a single-file Tkinter application. The internal source is organized with section markers to keep the monolith patchable and easy to evolve.

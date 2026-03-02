"""
ExportController – Validates and writes the final modularized code back to disk.
Handles export previews, file writing with backup, and multi-file export jobs.
Zero UI dependencies.
"""
import os
import datetime
from backend.modules.patch_engine import PatchEngine


class ExportController:
    """
    Manages the export of curated/patched code to the filesystem.
    Steps:
    1. Validate the export (check paths, detect conflicts)
    2. Preview changes (generate diffs)
    3. Execute the export (write files with backup)
    """

    def __init__(self, project_root, log=None):
        self.project_root = project_root
        self.log = log or (lambda msg: None)
        self.backup_dir = os.path.join(project_root, "_backupBIN")
        os.makedirs(self.backup_dir, exist_ok=True)

    def handle(self, schema):
        """Controller dispatch for BackendEngine."""
        action = schema.get("action")

        if action == "preview":
            return self._preview_export(schema)
        elif action == "execute":
            return self._execute_export(schema)
        elif action == "validate":
            return self._validate_export(schema)
        elif action == "apply_patches":
            return self._apply_patches(schema)
        return {"status": "error", "message": f"Unknown export action: {action}"}

    # ── validation ──────────────────────────────────────────

    def _validate_export(self, schema):
        """
        Validate an export job before execution.
        Checks that all target paths are writable and no conflicts exist.

        Schema:
        {
            "files": [
                {"path": "src/backend/modules/utils.py", "content": "..."},
                ...
            ]
        }
        """
        files = schema.get("files", [])
        errors = []
        warnings = []

        for f in files:
            path = f.get("path", "")
            content = f.get("content", "")

            if not path:
                errors.append("Empty path in export list")
                continue

            abs_path = self._abs(path)

            # Check parent directory exists or can be created
            parent = os.path.dirname(abs_path)
            if not os.path.isdir(parent):
                try:
                    os.makedirs(parent, exist_ok=True)
                except OSError as e:
                    errors.append(f"Cannot create directory for {path}: {e}")

            # Check for overwrites
            if os.path.isfile(abs_path):
                warnings.append(f"Will overwrite: {path}")

            # Check content is non-empty
            if not content.strip():
                warnings.append(f"Empty content for: {path}")

        return {
            "status": "ok" if not errors else "error",
            "errors": errors,
            "warnings": warnings,
            "file_count": len(files),
        }

    # ── preview ─────────────────────────────────────────────

    def _preview_export(self, schema):
        """
        Generate diffs for all files in the export job.
        Returns a list of diff previews.
        """
        files = schema.get("files", [])
        previews = []

        for f in files:
            path = f.get("path", "")
            new_content = f.get("content", "")
            abs_path = self._abs(path)

            original = ""
            if os.path.isfile(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8") as fh:
                        original = fh.read()
                except (OSError, UnicodeDecodeError):
                    original = ""

            diff = PatchEngine.preview(original, new_content)

            previews.append({
                "path": path,
                "is_new": not os.path.isfile(abs_path),
                "original_lines": len(original.splitlines()),
                "new_lines": len(new_content.splitlines()),
                "diff": diff,
            })

        return {
            "status": "ok",
            "previews": previews,
        }

    # ── execution ───────────────────────────────────────────

    def _execute_export(self, schema):
        """
        Write all files in the export job to disk.
        Existing files are backed up to _backupBIN/ first.
        """
        files = schema.get("files", [])

        # Validate first
        validation = self._validate_export(schema)
        if validation["status"] == "error":
            return validation

        written = []
        failed = []

        for f in files:
            path = f.get("path", "")
            content = f.get("content", "")
            abs_path = self._abs(path)

            try:
                # Backup existing file
                if os.path.isfile(abs_path):
                    self._backup(abs_path)

                # Write new content
                os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                with open(abs_path, "w", encoding="utf-8") as fh:
                    fh.write(content)

                written.append(path)
                self.log(f"Exported: {path}")
            except (OSError, IOError) as e:
                failed.append({"path": path, "error": str(e)})
                self.log(f"Export failed: {path} - {e}")

        return {
            "status": "ok" if not failed else "partial",
            "written": written,
            "failed": failed,
        }

    # ── patching ────────────────────────────────────────────

    def _apply_patches(self, schema):
        """
        Apply a list of patches to a file and optionally write the result.

        Schema:
        {
            "file": "path/to/file.py",
            "patches": [{op, match, value, ...}],
            "write": true/false (default: false = preview only)
        }
        """
        file_path = schema.get("file")
        patches = schema.get("patches", [])
        write = schema.get("write", False)

        if not file_path:
            return {"status": "error", "message": "No file specified"}

        abs_path = self._abs(file_path)
        if not os.path.isfile(abs_path):
            return {"status": "error", "message": f"File not found: {file_path}"}

        # Validate patches
        ok, errors = PatchEngine.validate_patches(patches)
        if not ok:
            return {"status": "error", "message": "Invalid patches", "errors": errors}

        # Read original
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                original = f.read()
        except (OSError, UnicodeDecodeError) as e:
            return {"status": "error", "message": f"Read failed: {e}"}

        # Apply patches
        patched, results = PatchEngine.apply_patches(original, patches)
        diff = PatchEngine.preview(original, patched)

        success_count = sum(1 for r in results if r["success"])

        # Optionally write
        if write and success_count > 0:
            self._backup(abs_path)
            with open(abs_path, "w", encoding="utf-8") as f:
                f.write(patched)
            self.log(f"Patched: {file_path} ({success_count}/{len(patches)} ops applied)")

        return {
            "status": "ok",
            "original": original,
            "patched": patched,
            "diff": diff,
            "patch_results": results,
            "success_count": success_count,
            "total_patches": len(patches),
            "written": write and success_count > 0,
        }

    # ── helpers ─────────────────────────────────────────────

    def _abs(self, path):
        if os.path.isabs(path):
            return path
        return os.path.join(self.project_root, path)

    def _backup(self, abs_path):
        """Copy an existing file to _backupBIN/ with a timestamp."""
        import shutil
        name = os.path.basename(abs_path)
        stem, ext = os.path.splitext(name)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = os.path.join(self.backup_dir, f"{stem}_{ts}{ext}")
        shutil.copy2(abs_path, dest)
        self.log(f"Backup: {name} -> _backupBIN/{stem}_{ts}{ext}")

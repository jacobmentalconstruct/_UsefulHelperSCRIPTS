"""
FileController – Handles disk I/O and the _backupBIN versioning logic.
Every save operation transparently copies the existing file to a
timestamped archive before writing the new content.
"""
import os
import shutil
import hashlib
import datetime
import threading


class FileController:
    """
    Manages file read/write with automatic archival.
    Also provides live-sync monitoring helpers.
    """

    def __init__(self, project_root, log=None):
        self.project_root = project_root
        self.log = log or (lambda msg: None)
        self.backup_dir = os.path.join(project_root, "_backupBIN")
        os.makedirs(self.backup_dir, exist_ok=True)

        # Live-sync state: tracks on-disk hashes to detect external changes
        self._known_hashes = {}
        self._sync_paused = set()  # file paths with unsaved editor changes

    # ── read / write ────────────────────────────────────────

    def read_file(self, path):
        """Read a file and return its content string (utf-8)."""
        abs_path = self._abs(path)
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        self._known_hashes[abs_path] = self._hash(content)
        return content

    def write_file(self, path, content):
        """
        Archive the current version (if it exists) then write new content.
        Returns the archive path or None if no prior version existed.
        """
        abs_path = self._abs(path)
        archive_path = None

        if os.path.isfile(abs_path):
            archive_path = self._archive(abs_path)

        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

        self._known_hashes[abs_path] = self._hash(content)
        self._sync_paused.discard(abs_path)
        self.log(f"Saved: {path}" + (f"  (backup: {archive_path})" if archive_path else ""))
        return archive_path

    def list_files(self, directory=None, extensions=None):
        """
        Walk a directory and return relative paths.
        `extensions` is an optional set like {'.py', '.js'}.
        """
        root = self._abs(directory) if directory else self.project_root
        results = []
        for dirpath, _dirs, files in os.walk(root):
            # Skip hidden and backup directories
            if any(part.startswith(".") or part == "_backupBIN" for part in dirpath.split(os.sep)):
                continue
            for fname in files:
                if extensions and os.path.splitext(fname)[1].lower() not in extensions:
                    continue
                full = os.path.join(dirpath, fname)
                results.append(os.path.relpath(full, self.project_root))
        return sorted(results)

    # ── archival ────────────────────────────────────────────

    def _archive(self, abs_path):
        """Copy the existing file to _backupBIN/ with a timestamp suffix."""
        name = os.path.basename(abs_path)
        stem, ext = os.path.splitext(name)
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{stem}_{ts}{ext}"
        dest = os.path.join(self.backup_dir, archive_name)
        shutil.copy2(abs_path, dest)
        self.log(f"Archived: {name} -> _backupBIN/{archive_name}")
        return dest

    # ── live sync ───────────────────────────────────────────

    def pause_sync(self, path):
        """Mark a file as having unsaved editor changes (skip disk-sync)."""
        self._sync_paused.add(self._abs(path))

    def resume_sync(self, path):
        """Re-enable disk-sync for a file."""
        self._sync_paused.discard(self._abs(path))

    def check_disk_changed(self, path):
        """
        Return True if the file on disk differs from the last known content.
        Returns False if sync is paused for this file.
        """
        abs_path = self._abs(path)
        if abs_path in self._sync_paused:
            return False
        if not os.path.isfile(abs_path):
            return abs_path in self._known_hashes  # deleted?
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                current_hash = self._hash(f.read())
        except (OSError, UnicodeDecodeError):
            return False
        return current_hash != self._known_hashes.get(abs_path)

    # ── helpers ─────────────────────────────────────────────

    def _abs(self, path):
        if os.path.isabs(path):
            return path
        return os.path.join(self.project_root, path)

    @staticmethod
    def _hash(content):
        return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

    def handle(self, schema):
        """Controller dispatch for the BackendEngine."""
        action = schema.get("action")
        path = schema.get("path", "")
        if action == "read":
            return {"status": "ok", "content": self.read_file(path)}
        elif action == "write":
            archive = self.write_file(path, schema.get("content", ""))
            return {"status": "ok", "archive": archive}
        elif action == "list":
            exts = schema.get("extensions")
            return {"status": "ok", "files": self.list_files(path or None, exts)}
        return {"status": "error", "message": f"Unknown file action: {action}"}

import ast
import json
import os
import queue
import threading
import time
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ----------------------------
# Data model
# ----------------------------

@dataclass
class PlannedEdit:
    file_path: Path
    func_name: str
    insert_at_line_0based: int  # where we insert header (0-based index into lines)
    old_header_span: tuple | None  # (start_line_0based, end_line_0based_exclusive) if replacing
    new_header_lines: list[str]

# ----------------------------
# Logging (thread-safe UI)
# ----------------------------

class TkLog:
    def __init__(self, text_widget: tk.Text):
        self.text = text_widget
        self.q = queue.Queue()
        self._closed = False

    def write(self, msg: str):
        if self._closed:
            return
        ts = time.strftime("%H:%M:%S")
        self.q.put(f"[{ts}] {msg}\n")

    def pump(self):
        """Call periodically from Tk main thread."""
        try:
            while True:
                line = self.q.get_nowait()
                self.text.configure(state="normal")
                self.text.insert("end", line)
                self.text.see("end")
                self.text.configure(state="disabled")
        except queue.Empty:
            return

    def close(self):
        self._closed = True

# ----------------------------
# AST helpers
# ----------------------------

def _is_service_endpoint_decorator(dec: ast.expr) -> bool:
    """
    Matches:
      @service_endpoint(...)
      @microservice_std_lib.service_endpoint(...)
      @something.service_endpoint(...)
    """
    if isinstance(dec, ast.Call):
        f = dec.func
        if isinstance(f, ast.Name) and f.id == "service_endpoint":
            return True
        if isinstance(f, ast.Attribute) and f.attr == "service_endpoint":
            return True
    return False

def _literal_eval_safe(node: ast.AST):
    try:
        return ast.literal_eval(node)
    except Exception:
        return None

def _extract_endpoint_kwargs(dec_call: ast.Call) -> dict:
    """
    Extracts literal keyword args from @service_endpoint(inputs=..., outputs=..., description=...).
    In your library, these become wrapper._endpoint_info fields (inputs/outputs/description/etc.). 
    :contentReference[oaicite:4]{index=4}
    """
    out = {}
    for kw in dec_call.keywords or []:
        if kw.arg is None:
            # **kwargs unpack; ignore safely
            continue
        out[kw.arg] = _literal_eval_safe(kw.value)
    return out

# ----------------------------
# Text edit helpers (comment insertion/replacement)
# ----------------------------

ROLE_PREFIX = "# ROLE:"
INPUTS_PREFIX = "# INPUTS:"
OUTPUTS_PREFIX = "# OUTPUTS:"

def _format_inline(obj) -> str:
    """
    Formats dict-ish inputs/outputs compactly.
    """
    if obj is None:
        return "{}"
    if isinstance(obj, dict):
        # stable order for diffs
        return json.dumps(obj, sort_keys=True)
    return str(obj)

def _build_header(description: str | None, inputs_obj, outputs_obj, indent: str) -> list[str]:
    role = (description or "").strip() or "N/A"
    return [
        f"{indent}{ROLE_PREFIX} {role}\n",
        f"{indent}{INPUTS_PREFIX} {_format_inline(inputs_obj)}\n",
        f"{indent}{OUTPUTS_PREFIX} {_format_inline(outputs_obj)}\n",
    ]

def _leading_ws(line: str) -> str:
    i = 0
    while i < len(line) and line[i] in (" ", "\t"):
        i += 1
    return line[:i]

def _find_existing_header_block(lines: list[str], def_line_0: int) -> tuple | None:
    """
    If the lines immediately above the def contain ROLE/INPUTS/OUTPUTS comment block,
    return (start, end_exclusive) to replace it.

    We scan up to 6 lines above the def to be forgiving about blank lines.
    """
    start_scan = max(0, def_line_0 - 6)
    window = lines[start_scan:def_line_0]

    # Work from bottom upward to find a contiguous block that includes ROLE/INPUTS/OUTPUTS
    indices = []
    for i, line in enumerate(window):
        s = line.lstrip()
        if s.startswith((ROLE_PREFIX, INPUTS_PREFIX, OUTPUTS_PREFIX)):
            indices.append(start_scan + i)

    if not indices:
        return None

    # If these markers are not close to def, skip replacement
    if max(indices) < def_line_0 - 6:
        return None

    # Expand to contiguous-ish block: include blank lines between marker lines
    block_start = min(indices)
    block_end = max(indices) + 1

    # Pull block_end upward if there are trailing blank lines just before def
    while block_end < def_line_0 and lines[block_end].strip() == "":
        block_end += 1

    # Also include any blank lines directly above the first marker (optional)
    while block_start > 0 and lines[block_start - 1].strip() == "":
        block_start -= 1

    return (block_start, def_line_0)

def plan_edits_for_file(path: Path, log: TkLog) -> list[PlannedEdit]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    # Normalize line endings only in memory; we preserve original by re-joining with existing \n in lines.
    lines = raw.splitlines(keepends=True)

    try:
        tree = ast.parse(raw)
    except SyntaxError as e:
        log.write(f"SKIP (syntax error): {path.name} :: {e}")
        return []

    edits: list[PlannedEdit] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.decorator_list:
            continue

        dec_call = None
        for dec in node.decorator_list:
            if _is_service_endpoint_decorator(dec):
                dec_call = dec  # type: ignore[assignment]
                break
        if dec_call is None or not isinstance(dec_call, ast.Call):
            continue

        kwargs = _extract_endpoint_kwargs(dec_call)
        inputs_obj = kwargs.get("inputs")
        outputs_obj = kwargs.get("outputs")
        desc = kwargs.get("description")

        def_line_0 = (node.lineno - 1) if getattr(node, "lineno", None) else None
        if def_line_0 is None or def_line_0 < 0 or def_line_0 >= len(lines):
            continue

        indent = _leading_ws(lines[def_line_0])

        new_header = _build_header(desc, inputs_obj, outputs_obj, indent)

        existing = _find_existing_header_block(lines, def_line_0)
        if existing:
            insert_at = existing[0]
            span = existing
            log.write(f"PLAN replace header: {path.name} :: {node.name} @ line {def_line_0+1}")
        else:
            insert_at = def_line_0
            span = None
            log.write(f"PLAN insert header:  {path.name} :: {node.name} @ line {def_line_0+1}")

        edits.append(
            PlannedEdit(
                file_path=path,
                func_name=node.name,
                insert_at_line_0based=insert_at,
                old_header_span=span,
                new_header_lines=new_header,
            )
        )

    return edits

def apply_edits_to_text(raw: str, edits: list[PlannedEdit]) -> str:
    lines = raw.splitlines(keepends=True)

    # Apply from bottom to top to keep line indices stable.
    # For each file, edits must be sorted descending by insertion position.
    edits_sorted = sorted(edits, key=lambda e: e.insert_at_line_0based, reverse=True)

    for e in edits_sorted:
        if e.old_header_span:
            start, end = e.old_header_span
            # Replace that region with new header (and ensure exactly one blank line after header? no)
            lines[start:end] = e.new_header_lines
        else:
            lines[e.insert_at_line_0based:e.insert_at_line_0based] = e.new_header_lines

    return "".join(lines)

# ----------------------------
# Tkinter App
# ----------------------------

class MarkupApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Microservice Endpoint Markup Tool")
        self.geometry("920x620")

        self.log_text = tk.Text(self, height=24, wrap="word", state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=10, pady=(10, 6))

        self.log = TkLog(self.log_text)

        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=10, pady=(0, 10))

        self.dir_var = tk.StringVar(value=str(Path.cwd()))
        ttk.Label(bar, text="microservices dir:").grid(row=0, column=0, sticky="w")
        ttk.Entry(bar, textvariable=self.dir_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(bar, text="Browse...", command=self.browse_dir).grid(row=0, column=2, padx=(0, 6))

        self.scan_btn = ttk.Button(bar, text="Scan", command=self.start_scan)
        self.scan_btn.grid(row=0, column=3, padx=(0, 6))

        self.save_btn = ttk.Button(bar, text="Save Changes", command=self.save_changes, state="disabled")
        self.save_btn.grid(row=0, column=4, padx=(0, 6))

        self.cancel_btn = ttk.Button(bar, text="Cancel", command=self.cancel_run, state="disabled")
        self.cancel_btn.grid(row=0, column=5)

        bar.columnconfigure(1, weight=1)

        self._worker: threading.Thread | None = None
        self._cancel_flag = threading.Event()

        self._planned_by_file: dict[Path, list[PlannedEdit]] = {}
        self._touched_files: set[Path] = set()

        # UI log pump
        self.after(50, self._tick)

    def _tick(self):
        self.log.pump()
        self.after(50, self._tick)

    def browse_dir(self):
        d = filedialog.askdirectory(title="Select src/microservices folder")
        if d:
            self.dir_var.set(d)

    def start_scan(self):
        micro_dir = Path(self.dir_var.get()).expanduser().resolve()
        if not micro_dir.exists() or not micro_dir.is_dir():
            messagebox.showerror("Invalid folder", "Please select a valid microservices directory.")
            return

        self._planned_by_file.clear()
        self._touched_files.clear()
        self._cancel_flag.clear()

        self.save_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.scan_btn.configure(state="disabled")

        self.log.write(f"Scan start: {micro_dir}")
        self._worker = threading.Thread(target=self._scan_worker, args=(micro_dir,), daemon=True)
        self._worker.start()

    def cancel_run(self):
        self.log.write("Cancel requested...")
        self._cancel_flag.set()

    def _scan_worker(self, micro_dir: Path):
        # Ignore library files
        ignore = {"__init__.py", "base_service.py", "microservice_std_lib.py", "fix.py", "document_utils.py"}
        py_files = sorted([p for p in micro_dir.glob("*.py") if p.name not in ignore])

        total_edits = 0

        for p in py_files:
            if self._cancel_flag.is_set():
                self.log.write("Scan cancelled.")
                break

            self.log.write(f"Parse AST: {p.name}")
            try:
                edits = plan_edits_for_file(p, self.log)
            except Exception as e:
                self.log.write(f"ERROR planning {p.name}: {e}")
                continue

            if edits:
                self._planned_by_file[p] = edits
                total_edits += len(edits)
                self.log.write(f"Planned {len(edits)} edit(s) in {p.name}")
            else:
                self.log.write(f"No endpoints found in {p.name}")

        if not self._cancel_flag.is_set():
            self.log.write(f"Scan complete. Files with changes: {len(self._planned_by_file)} | Total planned edits: {total_edits}")

        # Enable Save if we have edits and not cancelled
        def _enable():
            self.scan_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            if self._planned_by_file and not self._cancel_flag.is_set():
                self.save_btn.configure(state="normal")
            else:
                self.save_btn.configure(state="disabled")

        self.after(0, _enable)

    def save_changes(self):
        if not self._planned_by_file:
            messagebox.showinfo("Nothing to do", "No planned edits.")
            return

        if not messagebox.askyesno("Confirm", f"Apply changes to {len(self._planned_by_file)} file(s)? Backups (.bak) will be created."):
            return

        self.save_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.scan_btn.configure(state="disabled")
        self._cancel_flag.clear()

        self._worker = threading.Thread(target=self._save_worker, daemon=True)
        self._worker.start()

    def _save_worker(self):
        for path, edits in sorted(self._planned_by_file.items(), key=lambda kv: kv[0].name):
            if self._cancel_flag.is_set():
                self.log.write("Save cancelled.")
                break

            try:
                raw = path.read_text(encoding="utf-8", errors="replace")
                new_text = apply_edits_to_text(raw, edits)

                if new_text == raw:
                    self.log.write(f"SKIP unchanged: {path.name}")
                    continue

                bak = path.with_suffix(path.suffix + ".bak")
                if not bak.exists():
                    bak.write_text(raw, encoding="utf-8")
                    self.log.write(f"Backup created: {bak.name}")

                path.write_text(new_text, encoding="utf-8")
                self._touched_files.add(path)
                self.log.write(f"UPDATED: {path.name} ({len(edits)} endpoint header(s))")
            except Exception as e:
                self.log.write(f"ERROR writing {path.name}: {e}")

        def _done():
            self.scan_btn.configure(state="normal")
            self.cancel_btn.configure(state="disabled")
            # keep planned edits, but disable save if none actually written
            if self._touched_files:
                messagebox.showinfo("Done", f"Updated {len(self._touched_files)} file(s). Backups saved as *.bak.")
            else:
                messagebox.showinfo("Done", "No files were modified.")

        self.after(0, _done)

if __name__ == "__main__":
    # This tool is designed around your decorator contract:
    # @service_endpoint(inputs=..., outputs=..., description=..., tags=..., side_effects=..., mode=...)
    # :contentReference[oaicite:5]{index=5}
    app = MarkupApp()
    app.mainloop()

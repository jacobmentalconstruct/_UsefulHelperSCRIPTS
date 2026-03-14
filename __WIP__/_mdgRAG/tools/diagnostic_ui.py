"""
Graph Manifold — Diagnostic UI

Tkinter-based diagnostic tool with two panels:
  1. Test Runner  — auto-discovers test files, run individually or all
  2. API Explorer — auto-discovers public modules, classes, functions with signatures

Zero maintenance: new test files and new modules are discovered automatically
at startup. No UI code changes needed when the project grows.

Launch: python tools/diagnostic_ui.py
    or: diag.bat (from project root)
"""

from __future__ import annotations

import ast
import glob
import importlib
import inspect
import os
import subprocess
import sys
import tempfile
import threading
import shutil
import tkinter as tk
from tkinter import filedialog, ttk, scrolledtext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Resolve project root (one level up from tools/)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = PROJECT_ROOT / "tests"
SRC_CORE_DIR = PROJECT_ROOT / "src" / "core"

# Ensure project root is on sys.path for imports
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ============================================================================
# Test Discovery
# ============================================================================

def discover_test_files() -> List[Path]:
    """Find all test_*.py files in the tests/ directory, sorted by name."""
    pattern = str(TESTS_DIR / "test_*.py")
    files = sorted(glob.glob(pattern))
    return [Path(f) for f in files]


def count_tests_in_file(filepath: Path) -> int:
    """Count test functions/methods in a file using AST parsing (no import needed)."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return 0

    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            count += 1
    return count


def extract_phase_label(filepath: Path) -> str:
    """Extract a human-readable label from a test filename."""
    name = filepath.stem  # test_phase5_scoring -> test_phase5_scoring
    # Strip 'test_' prefix
    label = name[5:] if name.startswith("test_") else name
    # Convert underscores to spaces, title case
    return label.replace("_", " ").title()


# ============================================================================
# API Discovery
# ============================================================================

# Packages to scan for public API
CORE_PACKAGES = [
    "src.core.runtime",
    "src.core.factory.manifold_factory",
    "src.core.store.manifold_store",
    "src.core.debug",
    "src.core.math.scoring",
    "src.core.math.friction",
    "src.core.math.annotator",
    "src.core.extraction.extractor",
    "src.core.hydration.hydrator",
    "src.core.model_bridge.model_bridge",
    "src.core.model_bridge.deterministic_provider",
    "src.core.projection.query_projection",
    "src.core.projection.identity_projection",
    "src.core.projection.external_projection",
    "src.core.fusion.fusion_engine",
    "src.core.manifolds.base_manifold",
    "src.core.manifolds.virtual_manifold",
    "src.core.types.ids",
    "src.core.types.enums",
    "src.core.types.graph",
    "src.core.types.provenance",
    "src.core.types.bindings",
    "src.core.types.runtime_state",
    "src.core.contracts.projection_contract",
    "src.core.contracts.fusion_contract",
    "src.core.contracts.evidence_bag_contract",
    "src.core.contracts.hydration_contract",
    "src.core.contracts.model_bridge_contract",
    "src.core.contracts.manifold_contract",
]


def discover_api_entries() -> List[Dict[str, Any]]:
    """
    Import each core module and extract public classes and functions
    with their signatures and docstrings.

    Returns list of dicts:
        {module, name, kind, signature, docstring, lineno}
    """
    entries: List[Dict[str, Any]] = []

    for mod_path in CORE_PACKAGES:
        try:
            mod = importlib.import_module(mod_path)
        except Exception as exc:
            entries.append({
                "module": mod_path,
                "name": "(import failed)",
                "kind": "error",
                "signature": str(exc),
                "docstring": "",
                "lineno": 0,
            })
            continue

        for attr_name in sorted(dir(mod)):
            if attr_name.startswith("_"):
                continue

            obj = getattr(mod, attr_name, None)
            if obj is None:
                continue

            # Only include items defined in this module (not re-imports from stdlib)
            obj_module = getattr(obj, "__module__", None)
            if obj_module and not obj_module.startswith("src."):
                continue

            kind = None
            if inspect.isclass(obj):
                kind = "class"
            elif inspect.isfunction(obj):
                kind = "function"
            else:
                continue

            try:
                sig = str(inspect.signature(obj))
            except (ValueError, TypeError):
                sig = "(...)"

            doc = inspect.getdoc(obj) or ""
            # Truncate long docstrings for the list view
            first_line = doc.split("\n")[0] if doc else ""

            try:
                lineno = inspect.getsourcelines(obj)[1]
            except (OSError, TypeError):
                lineno = 0

            entries.append({
                "module": mod_path,
                "name": attr_name,
                "kind": kind,
                "signature": sig,
                "docstring": doc,
                "first_line": first_line,
                "lineno": lineno,
            })

    return entries


# ============================================================================
# UI Application
# ============================================================================

class DiagnosticUI:
    """Main diagnostic UI with tabbed panels."""

    # Color scheme
    BG = "#1e1e2e"
    BG_SECONDARY = "#282840"
    FG = "#cdd6f4"
    FG_DIM = "#6c7086"
    ACCENT = "#89b4fa"
    GREEN = "#a6e3a1"
    RED = "#f38ba8"
    YELLOW = "#f9e2af"
    ORANGE = "#fab387"
    SURFACE = "#313244"
    OVERLAY = "#45475a"

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Graph Manifold — Diagnostic UI")
        self.root.geometry("1100x750")
        self.root.configure(bg=self.BG)
        self.root.minsize(900, 600)

        self._setup_styles()
        self._build_header()
        self._build_status_bar()
        self._build_notebook()
        self._build_test_runner_tab()
        self._build_api_explorer_tab()
        self._build_embedder_tab()

    def _setup_styles(self) -> None:
        """Configure ttk styles for dark theme."""
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(".", background=self.BG, foreground=self.FG)
        style.configure("TNotebook", background=self.BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.SURFACE,
                        foreground=self.FG, padding=[14, 6],
                        font=("Consolas", 10, "bold"))
        style.map("TNotebook.Tab",
                  background=[("selected", self.ACCENT)],
                  foreground=[("selected", self.BG)])

        style.configure("TFrame", background=self.BG)
        style.configure("Surface.TFrame", background=self.BG_SECONDARY)

        style.configure("TLabel", background=self.BG, foreground=self.FG,
                        font=("Consolas", 10))
        style.configure("Header.TLabel", font=("Consolas", 14, "bold"),
                        foreground=self.ACCENT)
        style.configure("Dim.TLabel", foreground=self.FG_DIM)
        style.configure("Pass.TLabel", foreground=self.GREEN)
        style.configure("Fail.TLabel", foreground=self.RED)

        style.configure("TButton", background=self.SURFACE, foreground=self.FG,
                        font=("Consolas", 9), padding=[10, 4])
        style.map("TButton",
                  background=[("active", self.OVERLAY)],
                  foreground=[("active", self.ACCENT)])

        style.configure("Run.TButton", background=self.ACCENT,
                        foreground=self.BG, font=("Consolas", 9, "bold"))

        style.configure("Treeview", background=self.BG_SECONDARY,
                        foreground=self.FG, fieldbackground=self.BG_SECONDARY,
                        font=("Consolas", 9), rowheight=24)
        style.configure("Treeview.Heading", background=self.SURFACE,
                        foreground=self.ACCENT, font=("Consolas", 9, "bold"))
        style.map("Treeview",
                  background=[("selected", self.OVERLAY)],
                  foreground=[("selected", self.ACCENT)])

    def _build_header(self) -> None:
        """Project title bar."""
        header = ttk.Frame(self.root)
        header.pack(fill=tk.X, padx=12, pady=(10, 4))

        ttk.Label(header, text="Graph Manifold", style="Header.TLabel").pack(
            side=tk.LEFT)
        ttk.Label(header, text="Diagnostic UI",
                  style="Dim.TLabel").pack(side=tk.LEFT, padx=(10, 0))

    def _build_notebook(self) -> None:
        """Create tabbed notebook."""
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

    def _build_status_bar(self) -> None:
        """Bottom status bar — packed early with side=BOTTOM so it stays pinned."""
        self.status_var = tk.StringVar(value="Ready")
        bar = ttk.Frame(self.root)
        bar.pack(side=tk.BOTTOM, fill=tk.X, padx=12, pady=(0, 6))
        ttk.Label(bar, textvariable=self.status_var,
                  style="Dim.TLabel").pack(side=tk.LEFT)

    # -----------------------------------------------------------------------
    # Tab 1: Test Runner
    # -----------------------------------------------------------------------

    def _build_test_runner_tab(self) -> None:
        """Build the test runner panel."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" Tests ")

        # Top control bar
        controls = ttk.Frame(tab)
        controls.pack(fill=tk.X, padx=8, pady=6)

        ttk.Button(controls, text="Run All", style="Run.TButton",
                   command=self._run_all_tests).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(controls, text="Run Selected",
                   command=self._run_selected_test).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(controls, text="Refresh",
                   command=self._refresh_test_list).pack(side=tk.LEFT)

        self.test_summary_var = tk.StringVar(value="")
        ttk.Label(controls, textvariable=self.test_summary_var,
                  style="Dim.TLabel").pack(side=tk.RIGHT)

        # Paned: test list (left) + output (right)
        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        # Test file list
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)

        columns = ("file", "tests", "status")
        self.test_tree = ttk.Treeview(list_frame, columns=columns,
                                       show="headings", selectmode="browse")
        self.test_tree.heading("file", text="Test File")
        self.test_tree.heading("tests", text="Tests")
        self.test_tree.heading("status", text="Status")
        self.test_tree.column("file", width=260, minwidth=150)
        self.test_tree.column("tests", width=50, minwidth=40, anchor=tk.CENTER)
        self.test_tree.column("status", width=80, minwidth=60, anchor=tk.CENTER)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                   command=self.test_tree.yview)
        self.test_tree.configure(yscrollcommand=scrollbar.set)
        self.test_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.test_tree.bind("<Double-1>", lambda e: self._run_selected_test())

        # Output panel
        output_frame = ttk.Frame(paned)
        paned.add(output_frame, weight=2)

        self.test_output = scrolledtext.ScrolledText(
            output_frame, wrap=tk.WORD, font=("Consolas", 9),
            bg=self.BG_SECONDARY, fg=self.FG, insertbackground=self.FG,
            selectbackground=self.OVERLAY, selectforeground=self.ACCENT,
            borderwidth=0, highlightthickness=0,
        )
        self.test_output.pack(fill=tk.BOTH, expand=True)

        # Configure output text tags for coloring
        self.test_output.tag_configure("pass", foreground=self.GREEN)
        self.test_output.tag_configure("fail", foreground=self.RED)
        self.test_output.tag_configure("warn", foreground=self.YELLOW)
        self.test_output.tag_configure("info", foreground=self.ACCENT)
        self.test_output.tag_configure("dim", foreground=self.FG_DIM)

        # Load test files
        self._test_files: List[Path] = []
        self._test_results: Dict[str, str] = {}  # filename -> "pass"/"fail"/"?"
        self._refresh_test_list()

    def _refresh_test_list(self) -> None:
        """Discover and display test files."""
        self.test_tree.delete(*self.test_tree.get_children())
        self._test_files = discover_test_files()
        self._test_results.clear()

        total_tests = 0
        for fp in self._test_files:
            count = count_tests_in_file(fp)
            total_tests += count
            status = self._test_results.get(fp.name, "—")
            self.test_tree.insert("", tk.END, iid=fp.name,
                                  values=(fp.stem, str(count), status))

        self.test_summary_var.set(
            f"{len(self._test_files)} files, {total_tests} tests")
        self.status_var.set(f"Discovered {len(self._test_files)} test files")

    def _run_selected_test(self) -> None:
        """Run the currently selected test file."""
        sel = self.test_tree.selection()
        if not sel:
            self.status_var.set("No test file selected")
            return

        filename = sel[0]
        filepath = TESTS_DIR / filename
        if filepath.exists():
            self._run_tests_async([filepath])

    def _run_all_tests(self) -> None:
        """Run all discovered test files sequentially."""
        if self._test_files:
            self._run_tests_async(list(self._test_files))

    def _run_tests_async(self, files: List[Path]) -> None:
        """Run test files in a background thread to keep UI responsive."""
        self.status_var.set(f"Running {len(files)} test file(s)...")
        self.test_output.delete("1.0", tk.END)

        def worker():
            passed_total = 0
            failed_total = 0

            for fp in files:
                self._append_output(f"\n{'='*60}\n", "dim")
                self._append_output(f"Running: {fp.stem}\n", "info")
                self._append_output(f"{'='*60}\n", "dim")

                try:
                    result = subprocess.run(
                        [sys.executable, "-m", "pytest", str(fp), "-v",
                         "--tb=short", "--no-header", "-q"],
                        capture_output=True, text=True, timeout=120,
                        cwd=str(PROJECT_ROOT),
                    )
                    output = result.stdout + result.stderr

                    # Parse results
                    for line in output.splitlines():
                        if "PASSED" in line:
                            self._append_output(line + "\n", "pass")
                        elif "FAILED" in line:
                            self._append_output(line + "\n", "fail")
                        elif "ERROR" in line:
                            self._append_output(line + "\n", "fail")
                        elif "warning" in line.lower():
                            self._append_output(line + "\n", "warn")
                        else:
                            self._append_output(line + "\n")

                    # Determine pass/fail
                    if result.returncode == 0:
                        status = "PASS"
                        tag = "pass"
                        passed_total += 1
                    else:
                        status = "FAIL"
                        tag = "fail"
                        failed_total += 1

                    self._test_results[fp.name] = status
                    self._update_tree_status(fp.name, status)

                except subprocess.TimeoutExpired:
                    self._append_output("TIMEOUT (120s)\n", "fail")
                    self._test_results[fp.name] = "TIMEOUT"
                    self._update_tree_status(fp.name, "TIMEOUT")
                    failed_total += 1
                except Exception as exc:
                    self._append_output(f"ERROR: {exc}\n", "fail")
                    self._test_results[fp.name] = "ERROR"
                    self._update_tree_status(fp.name, "ERROR")
                    failed_total += 1

            # Summary
            self._append_output(f"\n{'='*60}\n", "dim")
            summary = f"Done: {passed_total} passed, {failed_total} failed"
            tag = "pass" if failed_total == 0 else "fail"
            self._append_output(summary + "\n", tag)
            self.root.after(0, lambda: self.status_var.set(summary))

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _append_output(self, text: str, tag: Optional[str] = None) -> None:
        """Thread-safe append to the output text widget."""
        def _do():
            self.test_output.insert(tk.END, text, tag if tag else ())
            self.test_output.see(tk.END)
        self.root.after(0, _do)

    def _update_tree_status(self, filename: str, status: str) -> None:
        """Thread-safe update of a treeview row's status column."""
        def _do():
            try:
                values = self.test_tree.item(filename, "values")
                self.test_tree.item(filename,
                                    values=(values[0], values[1], status))
            except tk.TclError:
                pass
        self.root.after(0, _do)

    # -----------------------------------------------------------------------
    # Tab 2: API Explorer
    # -----------------------------------------------------------------------

    def _build_api_explorer_tab(self) -> None:
        """Build the API explorer panel."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" API Explorer ")

        # Top control bar
        controls = ttk.Frame(tab)
        controls.pack(fill=tk.X, padx=8, pady=6)

        ttk.Button(controls, text="Refresh",
                   command=self._refresh_api_list).pack(side=tk.LEFT)

        # Filter
        ttk.Label(controls, text="  Filter:").pack(side=tk.LEFT)
        self.api_filter_var = tk.StringVar()
        self.api_filter_var.trace_add("write", self._on_api_filter_changed)
        filter_entry = ttk.Entry(controls, textvariable=self.api_filter_var,
                                  width=30, font=("Consolas", 9))
        filter_entry.pack(side=tk.LEFT, padx=(4, 0))

        self.api_summary_var = tk.StringVar(value="")
        ttk.Label(controls, textvariable=self.api_summary_var,
                  style="Dim.TLabel").pack(side=tk.RIGHT)

        # Kind filter buttons
        self.show_classes_var = tk.BooleanVar(value=True)
        self.show_functions_var = tk.BooleanVar(value=True)

        tk.Checkbutton(controls, text="Classes", variable=self.show_classes_var,
                       command=self._apply_api_filter, bg=self.BG,
                       fg=self.FG, selectcolor=self.SURFACE,
                       activebackground=self.BG, activeforeground=self.ACCENT,
                       font=("Consolas", 9)).pack(side=tk.LEFT, padx=(12, 0))
        tk.Checkbutton(controls, text="Functions", variable=self.show_functions_var,
                       command=self._apply_api_filter, bg=self.BG,
                       fg=self.FG, selectcolor=self.SURFACE,
                       activebackground=self.BG, activeforeground=self.ACCENT,
                       font=("Consolas", 9)).pack(side=tk.LEFT, padx=(4, 0))

        # Paned: API list (left) + detail (right)
        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        # API list
        list_frame = ttk.Frame(paned)
        paned.add(list_frame, weight=1)

        columns = ("kind", "name", "module")
        self.api_tree = ttk.Treeview(list_frame, columns=columns,
                                      show="headings", selectmode="browse")
        self.api_tree.heading("kind", text="Kind")
        self.api_tree.heading("name", text="Name")
        self.api_tree.heading("module", text="Module")
        self.api_tree.column("kind", width=60, minwidth=50, anchor=tk.CENTER)
        self.api_tree.column("name", width=220, minwidth=120)
        self.api_tree.column("module", width=200, minwidth=120)

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL,
                                   command=self.api_tree.yview)
        self.api_tree.configure(yscrollcommand=scrollbar.set)
        self.api_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.api_tree.bind("<<TreeviewSelect>>", self._on_api_select)

        # Detail panel
        detail_frame = ttk.Frame(paned)
        paned.add(detail_frame, weight=2)

        self.api_detail = scrolledtext.ScrolledText(
            detail_frame, wrap=tk.WORD, font=("Consolas", 9),
            bg=self.BG_SECONDARY, fg=self.FG, insertbackground=self.FG,
            selectbackground=self.OVERLAY, selectforeground=self.ACCENT,
            borderwidth=0, highlightthickness=0,
        )
        self.api_detail.pack(fill=tk.BOTH, expand=True)

        self.api_detail.tag_configure("heading", foreground=self.ACCENT,
                                       font=("Consolas", 11, "bold"))
        self.api_detail.tag_configure("sig", foreground=self.YELLOW,
                                       font=("Consolas", 10))
        self.api_detail.tag_configure("kind_tag", foreground=self.ORANGE)
        self.api_detail.tag_configure("module_path", foreground=self.FG_DIM)
        self.api_detail.tag_configure("doc", foreground=self.FG)
        self.api_detail.tag_configure("section", foreground=self.GREEN,
                                       font=("Consolas", 9, "bold"))

        # Store all entries for filtering
        self._api_entries: List[Dict[str, Any]] = []
        self._refresh_api_list()

    def _refresh_api_list(self) -> None:
        """Discover and display API entries."""
        self.status_var.set("Scanning API surface...")
        self.root.update_idletasks()

        self._api_entries = discover_api_entries()
        self._apply_api_filter()
        self.status_var.set(
            f"Discovered {len(self._api_entries)} API entries")

    def _apply_api_filter(self, *args) -> None:
        """Apply text and kind filters to the API tree."""
        self.api_tree.delete(*self.api_tree.get_children())

        filter_text = self.api_filter_var.get().lower()
        show_classes = self.show_classes_var.get()
        show_functions = self.show_functions_var.get()

        visible = 0
        for i, entry in enumerate(self._api_entries):
            # Kind filter
            if entry["kind"] == "class" and not show_classes:
                continue
            if entry["kind"] == "function" and not show_functions:
                continue

            # Text filter (searches name, module, and first_line of docstring)
            if filter_text:
                searchable = (
                    entry["name"].lower() + " " +
                    entry["module"].lower() + " " +
                    entry.get("first_line", "").lower()
                )
                if filter_text not in searchable:
                    continue

            kind_label = "cls" if entry["kind"] == "class" else "fn"
            # Shorten module path for display
            mod_short = entry["module"].replace("src.core.", "")

            self.api_tree.insert("", tk.END, iid=str(i),
                                  values=(kind_label, entry["name"], mod_short))
            visible += 1

        self.api_summary_var.set(
            f"{visible}/{len(self._api_entries)} entries")

    def _on_api_filter_changed(self, *args) -> None:
        """Callback when filter text changes."""
        self._apply_api_filter()

    def _on_api_select(self, event) -> None:
        """Show detail for selected API entry."""
        sel = self.api_tree.selection()
        if not sel:
            return

        idx = int(sel[0])
        if idx >= len(self._api_entries):
            return

        entry = self._api_entries[idx]
        self.api_detail.delete("1.0", tk.END)

        # Name heading
        self.api_detail.insert(tk.END, entry["name"], "heading")
        self.api_detail.insert(tk.END, "\n")

        # Kind and module
        self.api_detail.insert(tk.END, entry["kind"].upper(), "kind_tag")
        self.api_detail.insert(tk.END, "  in  ", "doc")
        self.api_detail.insert(tk.END, entry["module"], "module_path")
        if entry.get("lineno"):
            self.api_detail.insert(
                tk.END, f"  (line {entry['lineno']})", "module_path")
        self.api_detail.insert(tk.END, "\n\n")

        # Signature
        self.api_detail.insert(tk.END, "Signature\n", "section")
        if entry["kind"] == "class":
            # Show __init__ signature for classes
            self.api_detail.insert(
                tk.END, f"class {entry['name']}{entry['signature']}\n", "sig")
        else:
            self.api_detail.insert(
                tk.END, f"def {entry['name']}{entry['signature']}\n", "sig")
        self.api_detail.insert(tk.END, "\n")

        # Docstring
        if entry.get("docstring"):
            self.api_detail.insert(tk.END, "Documentation\n", "section")
            self.api_detail.insert(tk.END, entry["docstring"] + "\n", "doc")
            self.api_detail.insert(tk.END, "\n")

        # For classes, also show public methods
        if entry["kind"] == "class":
            self._show_class_methods(entry)

    def _show_class_methods(self, entry: Dict[str, Any]) -> None:
        """Append public methods of a class to the detail view."""
        try:
            mod = importlib.import_module(entry["module"])
            cls = getattr(mod, entry["name"], None)
            if cls is None:
                return
        except Exception:
            return

        methods = []
        for name in sorted(dir(cls)):
            if name.startswith("_") and name != "__init__":
                continue
            obj = getattr(cls, name, None)
            if not callable(obj):
                continue
            if isinstance(obj, property):
                continue

            try:
                sig = str(inspect.signature(obj))
            except (ValueError, TypeError):
                sig = "(...)"

            doc = inspect.getdoc(obj) or ""
            first_line = doc.split("\n")[0] if doc else ""
            methods.append((name, sig, first_line))

        if methods:
            self.api_detail.insert(tk.END, "Public Methods\n", "section")
            for name, sig, first_line in methods:
                self.api_detail.insert(tk.END, f"  {name}", "sig")
                self.api_detail.insert(tk.END, f"{sig}", "module_path")
                if first_line:
                    self.api_detail.insert(
                        tk.END, f"\n    {first_line}", "doc")
                self.api_detail.insert(tk.END, "\n")

    # -----------------------------------------------------------------------
    # Tab 3: Embedder
    # -----------------------------------------------------------------------

    def _build_embedder_tab(self) -> None:
        """Build the embedder/tokenizer diagnostic tab."""
        tab = ttk.Frame(self.notebook)
        self.notebook.add(tab, text=" Embedder ")

        # Provider state
        self._embed_provider = None

        # === Controls frame (top) ===
        controls = ttk.Frame(tab)
        controls.pack(fill=tk.X, padx=8, pady=6)

        # Row 1: Artifact paths
        path_frame = ttk.Frame(controls)
        path_frame.pack(fill=tk.X, pady=(0, 4))

        ttk.Label(path_frame, text="Tokenizer:").pack(side=tk.LEFT)
        self._tok_path_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self._tok_path_var,
                  width=40, font=("Consolas", 9)).pack(side=tk.LEFT, padx=(4, 8))

        ttk.Label(path_frame, text="Embeddings:").pack(side=tk.LEFT)
        self._emb_path_var = tk.StringVar()
        ttk.Entry(path_frame, textvariable=self._emb_path_var,
                  width=40, font=("Consolas", 9)).pack(side=tk.LEFT, padx=(4, 8))

        # Row 2: Action buttons + status
        btn_frame = ttk.Frame(controls)
        btn_frame.pack(fill=tk.X, pady=(0, 4))

        ttk.Button(btn_frame, text="Train from File", style="Run.TButton",
                   command=self._embed_train_from_file).pack(
                       side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Load Artifacts",
                   command=self._embed_load_artifacts).pack(
                       side=tk.LEFT, padx=(0, 6))
        ttk.Button(btn_frame, text="Generate Demo",
                   command=self._embed_generate_demo).pack(
                       side=tk.LEFT, padx=(0, 6))

        self._embed_status_var = tk.StringVar(value="No artifacts loaded")
        ttk.Label(btn_frame, textvariable=self._embed_status_var,
                  style="Dim.TLabel").pack(side=tk.LEFT, padx=(12, 0))

        # Row 3: Input + Tokenize / Embed buttons
        input_frame = ttk.Frame(controls)
        input_frame.pack(fill=tk.X)

        ttk.Label(input_frame, text="Input:").pack(side=tk.LEFT)
        self._embed_input_var = tk.StringVar(value="hello world")
        ttk.Entry(input_frame, textvariable=self._embed_input_var,
                  width=50, font=("Consolas", 9)).pack(
                      side=tk.LEFT, padx=(4, 8))

        ttk.Button(input_frame, text="Tokenize",
                   command=self._embed_tokenize).pack(side=tk.LEFT, padx=(0, 6))
        ttk.Button(input_frame, text="Embed", style="Run.TButton",
                   command=self._embed_run).pack(side=tk.LEFT)

        # === Paned: Forward path (left) + Results (right) ===
        paned = ttk.PanedWindow(tab, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        # Left pane: Forward path
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        self._embed_forward = scrolledtext.ScrolledText(
            left_frame, wrap=tk.WORD, font=("Consolas", 9),
            bg=self.BG_SECONDARY, fg=self.FG, insertbackground=self.FG,
            selectbackground=self.OVERLAY, selectforeground=self.ACCENT,
            borderwidth=0, highlightthickness=0,
        )
        self._embed_forward.pack(fill=tk.BOTH, expand=True)

        # Right pane: Embedding results + reverse lookup
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=1)

        self._embed_results = scrolledtext.ScrolledText(
            right_frame, wrap=tk.WORD, font=("Consolas", 9),
            bg=self.BG_SECONDARY, fg=self.FG, insertbackground=self.FG,
            selectbackground=self.OVERLAY, selectforeground=self.ACCENT,
            borderwidth=0, highlightthickness=0,
        )
        self._embed_results.pack(fill=tk.BOTH, expand=True)

        # Configure text tags for both panes
        for widget in (self._embed_forward, self._embed_results):
            widget.tag_configure("heading", foreground=self.ACCENT,
                                 font=("Consolas", 11, "bold"))
            widget.tag_configure("section", foreground=self.GREEN,
                                 font=("Consolas", 9, "bold"))
            widget.tag_configure("symbol", foreground=self.YELLOW)
            widget.tag_configure("id", foreground=self.ORANGE)
            widget.tag_configure("vector", foreground=self.FG)
            widget.tag_configure("dim", foreground=self.FG_DIM)
            widget.tag_configure("sim_high", foreground=self.GREEN)
            widget.tag_configure("sim_med", foreground=self.YELLOW)
            widget.tag_configure("sim_low", foreground=self.FG_DIM)
            widget.tag_configure("error", foreground=self.RED)
            widget.tag_configure("info", foreground=self.ACCENT)

    # -- Embedder helpers --------------------------------------------------

    def _embed_append_forward(self, text: str, tag: Optional[str] = None) -> None:
        """Thread-safe append to the forward-path pane."""
        def _do():
            self._embed_forward.insert(tk.END, text, tag if tag else ())
            self._embed_forward.see(tk.END)
        self.root.after(0, _do)

    def _embed_append_results(self, text: str, tag: Optional[str] = None) -> None:
        """Thread-safe append to the results pane."""
        def _do():
            self._embed_results.insert(tk.END, text, tag if tag else ())
            self._embed_results.see(tk.END)
        self.root.after(0, _do)

    def _embed_clear_panes(self) -> None:
        """Clear both output panes."""
        def _do():
            self._embed_forward.delete("1.0", tk.END)
            self._embed_results.delete("1.0", tk.END)
        self.root.after(0, _do)

    def _embed_train_from_file(self) -> None:
        """Open file picker, train BPE-SVD pipeline, and load the resulting artifacts."""
        path = filedialog.askopenfilename(
            title="Select training file",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        self._embed_clear_panes()
        self._embed_status_var.set("Training...")
        self.status_var.set(f"Training on: {Path(path).name}")

        def worker():
            try:
                import numpy as np
                from src.core.training.bpe_trainer import BPETrainer
                from src.core.training.cooccurrence import compute_counts
                from src.core.training.npmi_matrix import build_npmi_matrix
                from src.core.training.spectral import compute_embeddings

                src_file = Path(path)
                if not src_file.is_file():
                    raise FileNotFoundError(f"File not found: {path}")

                vocab_size = 2000
                embedding_dims = 64
                window_size = 5

                # Step 1: Copy file to temp directory (BPETrainer needs a dir)
                self._embed_append_forward("TRAINING PIPELINE\n", "heading")
                self._embed_append_forward("=" * 40 + "\n\n", "dim")

                tmp_dir = tempfile.mkdtemp(prefix="mdg_train_")
                try:
                    dest = Path(tmp_dir) / src_file.name
                    if not dest.suffix.lower() == ".txt":
                        dest = dest.with_suffix(".txt")
                    shutil.copy2(str(src_file), str(dest))

                    # Step 2: Train BPE tokenizer
                    self._embed_append_forward("Step 1: BPE Tokenizer\n", "section")
                    trainer = BPETrainer(vocab_size=vocab_size)
                    trainer.train(tmp_dir)

                    artifacts_dir = Path(tempfile.mkdtemp(prefix="mdg_artifacts_"))
                    tok_path = artifacts_dir / "tokenizer.json"
                    emb_path = artifacts_dir / "embeddings.npy"
                    trainer.save(str(tok_path))

                    vocab = trainer.vocab
                    merges = trainer.merges
                    eow = trainer.end_of_word

                    self._embed_append_forward(
                        f"  vocab: {len(vocab)} symbols, "
                        f"{len(merges)} merges\n", "info")

                    # Step 3: Encode corpus into token streams
                    self._embed_append_forward(
                        "\nStep 2: Encode Corpus\n", "section")

                    with open(str(src_file), "r", encoding="utf-8",
                              errors="ignore") as f:
                        corpus_text = f.read()

                    token_streams: List[List[int]] = []
                    for line in corpus_text.splitlines():
                        line = line.strip()
                        if line:
                            ids: List[int] = []
                            for word in line.split():
                                symbols: List[str] = list(word) + [eow]
                                for a, b in merges:
                                    merged = a + b
                                    i = 0
                                    new: List[str] = []
                                    while i < len(symbols):
                                        if (i < len(symbols) - 1
                                                and symbols[i] == a
                                                and symbols[i + 1] == b):
                                            new.append(merged)
                                            i += 2
                                        else:
                                            new.append(symbols[i])
                                            i += 1
                                    symbols = new
                                for sym in symbols:
                                    ids.append(vocab.get(sym, -1))
                            if ids:
                                token_streams.append(ids)

                    total_tokens = sum(len(s) for s in token_streams)
                    self._embed_append_forward(
                        f"  {total_tokens} tokens in "
                        f"{len(token_streams)} lines\n", "info")

                    if not token_streams:
                        raise ValueError(
                            "Corpus produced no tokens — file may be empty.")

                    # Step 4: Co-occurrence counting
                    self._embed_append_forward(
                        "\nStep 3: Co-occurrence\n", "section")
                    pair_counts, token_counts = compute_counts(
                        token_streams, window_size=window_size)
                    self._embed_append_forward(
                        f"  {len(pair_counts)} pairs observed\n", "info")

                    # Step 5: NPMI association matrix
                    self._embed_append_forward(
                        "\nStep 4: NPMI Matrix\n", "section")
                    npmi_mat = build_npmi_matrix(
                        pair_counts, token_counts, len(vocab))
                    self._embed_append_forward(
                        f"  {npmi_mat.shape[0]}\u00d7{npmi_mat.shape[1]}, "
                        f"{npmi_mat.nnz} nonzero\n", "info")

                    # Step 6: SVD compression
                    effective_dims = min(embedding_dims, len(vocab) - 1)
                    if effective_dims < 1:
                        raise ValueError(
                            f"Vocabulary too small ({len(vocab)}) for SVD.")
                    self._embed_append_forward(
                        f"\nStep 5: SVD ({effective_dims}d)\n", "section")
                    emb_matrix = compute_embeddings(npmi_mat, k=effective_dims)
                    self._embed_append_forward(
                        f"  {emb_matrix.shape[0]} tokens \u00d7 "
                        f"{emb_matrix.shape[1]} dims\n", "info")

                    # Step 7: Save artifacts
                    np.save(str(emb_path), emb_matrix)

                    self._embed_append_forward(
                        f"\nArtifacts saved to:\n", "section")
                    self._embed_append_forward(
                        f"  {tok_path}\n  {emb_path}\n", "dim")

                    # Step 8: Load provider
                    def _finish():
                        self._tok_path_var.set(str(tok_path))
                        self._emb_path_var.set(str(emb_path))
                        self._embed_load_artifacts()
                        self.status_var.set("Training complete — model ready")
                    self.root.after(0, _finish)

                    # Right pane: summary
                    self._embed_append_results(
                        "TRAINING COMPLETE\n", "heading")
                    self._embed_append_results("=" * 40 + "\n\n", "dim")
                    self._embed_append_results(
                        f"File:       {src_file.name}\n", "info")
                    self._embed_append_results(
                        f"Vocab:      {len(vocab)} symbols\n", "info")
                    self._embed_append_results(
                        f"Merges:     {len(merges)}\n", "info")
                    self._embed_append_results(
                        f"Pairs:      {len(pair_counts)}\n", "info")
                    self._embed_append_results(
                        f"Dimensions: {effective_dims}\n", "info")
                    self._embed_append_results(
                        f"\nReady to tokenize and embed.\n", "dim")

                finally:
                    shutil.rmtree(tmp_dir, ignore_errors=True)

            except Exception as exc:
                self._embed_append_forward(f"\nERROR: {exc}\n", "error")
                def _err():
                    self._embed_status_var.set(f"Training failed: {exc}")
                    self.status_var.set(f"Training failed: {exc}")
                self.root.after(0, _err)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _embed_generate_demo(self) -> None:
        """Generate tiny demo artifacts in a temp directory and load them."""
        import json
        try:
            import numpy as np
        except ImportError:
            self._embed_status_var.set("ERROR: numpy not installed")
            return

        tmp_dir = tempfile.mkdtemp(prefix="mdg_embed_demo_")
        tok_path = os.path.join(tmp_dir, "tokenizer.json")
        emb_path = os.path.join(tmp_dir, "embeddings.npy")

        spec = {
            "vocab": {
                "h": 0, "e": 1, "l": 2, "o": 3, "</w>": 4,
                "w": 5, "r": 6, "d": 7, "he": 8, "ll": 9, "lo": 10,
            },
            "merges": [["h", "e"], ["l", "l"], ["l", "o"]],
            "end_of_word": "</w>",
        }
        with open(tok_path, "w", encoding="utf-8") as f:
            json.dump(spec, f)

        rng = np.random.RandomState(42)
        embeddings = rng.randn(11, 4).astype(np.float32)
        np.save(emb_path, embeddings)

        self._tok_path_var.set(tok_path)
        self._emb_path_var.set(emb_path)
        self._embed_load_artifacts()

    def _embed_load_artifacts(self) -> None:
        """Load DeterministicEmbedProvider from the paths in the UI entries."""
        tok_path = self._tok_path_var.get().strip()
        emb_path = self._emb_path_var.get().strip()

        if not tok_path or not emb_path:
            self._embed_status_var.set("ERROR: Both paths required")
            return

        try:
            from src.core.model_bridge.deterministic_provider import (
                DeterministicEmbedProvider,
            )
            self._embed_provider = DeterministicEmbedProvider(tok_path, emb_path)
            vocab_size = len(self._embed_provider.vocab)
            dims = self._embed_provider._dimensions
            matrix_rows = self._embed_provider._embeddings.shape[0]
            self._embed_status_var.set(
                f"Loaded: vocab={vocab_size}, matrix={matrix_rows}\u00d7{dims}")
            self.status_var.set("Embedder: artifacts loaded successfully")
        except Exception as exc:
            self._embed_provider = None
            self._embed_status_var.set(f"ERROR: {exc}")
            self.status_var.set(f"Embedder load failed: {exc}")

    def _embed_tokenize(self) -> None:
        """Tokenize input text and display BPE symbols + token IDs."""
        if self._embed_provider is None:
            self._embed_status_var.set("Load artifacts first")
            return

        text = self._embed_input_var.get().strip()
        if not text:
            return

        self._embed_clear_panes()

        def worker():
            try:
                provider = self._embed_provider

                self._embed_append_forward("FORWARD PATH\n", "heading")
                self._embed_append_forward("=" * 40 + "\n\n", "dim")

                # Step 1: BPE symbols per word
                self._embed_append_forward("Step 1: BPE Symbols\n", "section")
                words = text.strip().split()
                for word in words:
                    symbols = provider._encode_word(word)
                    sym_str = "  ".join(f"[{s}]" for s in symbols)
                    self._embed_append_forward(f'  "{word}" \u2192 ', "dim")
                    self._embed_append_forward(f"{sym_str}\n", "symbol")

                # Step 2: Token IDs
                self._embed_append_forward("\nStep 2: Token IDs\n", "section")
                token_ids = provider._encode(text)
                ids_str = ", ".join(str(tid) for tid in token_ids)
                self._embed_append_forward(f"  [{ids_str}]\n", "id")

                # Step 3: Decode round-trip
                self._embed_append_forward(
                    "\nStep 3: Decode (ID \u2192 Symbol)\n", "section")
                decoded = provider.decode_token_ids(token_ids)
                dec_str = ", ".join(decoded)
                self._embed_append_forward(f"  [{dec_str}]\n", "symbol")

                self._embed_append_forward(
                    f"\nToken count: {len(token_ids)}\n", "info")

                # Right pane hint
                self._embed_append_results("Tokenize-only mode\n", "heading")
                self._embed_append_results(
                    "Press [Embed] to compute vectors and reverse lookup.\n",
                    "dim")

            except Exception as exc:
                self._embed_append_forward(f"\nERROR: {exc}\n", "error")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    def _embed_run(self) -> None:
        """Full pipeline: tokenize -> embed -> reverse nearest tokens."""
        if self._embed_provider is None:
            self._embed_status_var.set("Load artifacts first")
            return

        text = self._embed_input_var.get().strip()
        if not text:
            return

        self._embed_clear_panes()

        def worker():
            try:
                import math
                provider = self._embed_provider

                # === LEFT PANE: Forward path ===
                self._embed_append_forward("FORWARD PATH\n", "heading")
                self._embed_append_forward("=" * 40 + "\n\n", "dim")

                # Step 1: BPE symbols per word
                self._embed_append_forward("Step 1: BPE Symbols\n", "section")
                words = text.strip().split()
                for word in words:
                    symbols = provider._encode_word(word)
                    sym_str = "  ".join(f"[{s}]" for s in symbols)
                    self._embed_append_forward(f'  "{word}" \u2192 ', "dim")
                    self._embed_append_forward(f"{sym_str}\n", "symbol")

                # Step 2: Token IDs
                self._embed_append_forward("\nStep 2: Token IDs\n", "section")
                token_ids = provider._encode(text)
                ids_str = ", ".join(str(tid) for tid in token_ids)
                self._embed_append_forward(f"  [{ids_str}]\n", "id")

                # Step 3: Decode round-trip
                self._embed_append_forward(
                    "\nStep 3: Decode (ID \u2192 Symbol)\n", "section")
                decoded = provider.decode_token_ids(token_ids)
                dec_str = ", ".join(decoded)
                self._embed_append_forward(f"  [{dec_str}]\n", "symbol")

                self._embed_append_forward(
                    f"\nToken count: {len(token_ids)}\n", "info")

                # Step 4: Embed
                result = provider.embed_texts([text])
                pooled = result.vectors[0]

                self._embed_append_forward("\nStep 4: Mean Pool\n", "section")
                vec_str = ", ".join(f"{v:.4f}" for v in pooled)
                self._embed_append_forward(f"  [{vec_str}]\n", "vector")

                norm = math.sqrt(sum(x * x for x in pooled))
                self._embed_append_forward(
                    f"  dims={len(pooled)}  norm={norm:.4f}\n", "dim")

                # === RIGHT PANE: Results + Reverse ===
                self._embed_append_results("EMBEDDING RESULT\n", "heading")
                self._embed_append_results("=" * 40 + "\n\n", "dim")

                self._embed_append_results("Pooled Vector\n", "section")
                self._embed_append_results(f"  [{vec_str}]\n", "vector")
                self._embed_append_results(
                    f"  dims={len(pooled)}  norm={norm:.4f}\n\n", "dim")

                # Reverse: nearest tokens
                self._embed_append_results(
                    "REVERSE: Nearest Tokens\n", "section")
                self._embed_append_results("-" * 40 + "\n", "dim")

                nearest = provider.nearest_tokens(pooled, k=10)
                for symbol, sim, token_vec in nearest:
                    if sim >= 0.7:
                        tag = "sim_high"
                    elif sim >= 0.3:
                        tag = "sim_med"
                    else:
                        tag = "sim_low"

                    tv_str = ", ".join(f"{v:.3f}" for v in token_vec[:4])
                    if len(token_vec) > 4:
                        tv_str += ", ..."
                    self._embed_append_results(
                        f"  {symbol:<10s} cos={sim:+.4f}  [{tv_str}]\n", tag)

                self._embed_append_results(
                    f"\n{len(nearest)} nearest tokens shown\n", "dim")

            except Exception as exc:
                self._embed_append_forward(f"\nERROR: {exc}\n", "error")
                self._embed_append_results(f"\nERROR: {exc}\n", "error")

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

    # -----------------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------------

    def run(self) -> None:
        """Start the Tkinter event loop."""
        self.root.mainloop()


# ============================================================================
# Entry point
# ============================================================================

def main() -> None:
    app = DiagnosticUI()
    app.run()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Microservice Syntax Tree Transformer (Prototype)

This tool:
- Loads a JSON tasklist (tasklist_microservice_refactor.json).
- Lets the user select a folder of Python files.
- Iterates over each .py file in that folder.
- Runs a simple, ordered pipeline of tasks per file.
- Logs all activity to a Tkinter UI log panel and stderr.

NOTE:
- This prototype focuses on orchestration + monitoring.
- The actual "parse / scaffold / patch" logic is stubbed out with clear hooks
  where you can integrate:
    - your semantic diff-based patcher
    - Ollama / Qwen model calls
    - your microservice-specific scaffold + IR logic.
"""

# =========================================================
# 1. IMPORTS
# =========================================================

import sys
import os
import json
import threading
import queue
import time
from typing import List, Dict, Any, Optional

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import scrolledtext

from microservices._TokenizingPatcherMS import TokenizingPatcherMS

# =========================================================
# 2. GLOBAL CONFIGURATION
# =========================================================

WINDOW_TITLE = "Microservice Syntax Tree Transformer"
WINDOW_WIDTH = 1000
WINDOW_HEIGHT = 700
LOG_FONT = ("Consolas", 10)

DEFAULT_TASKLIST_PATH = os.path.join(
    os.path.dirname(__file__),
    "tasklist_microservice_refactor.json"
)

VALID_EXTENSIONS = [".py"]

LOG_PREFIX_INFO = "[INFO]"
LOG_PREFIX_WARN = "[WARN]"
LOG_PREFIX_ERROR = "[ERROR]"
LOG_PREFIX_TASK = "[TASK]"
LOG_PREFIX_FILE = "[FILE]"

# =========================================================
# 3. LOGGING + UTILITY HELPERS
# =========================================================

class UILogger:
    """
    Thread-safe logger that writes to:
    - a Tkinter Text/ScrolledText widget (if available)
    - stderr

    Uses an internal queue to synchronize log messages
    from worker threads into the main Tkinter thread.
    """

    def __init__(self, text_widget: Optional[tk.Text] = None):
        self.text_widget = text_widget
        self.queue: "queue.Queue[str]" = queue.Queue()
        self._stop = False

    def attach_widget(self, text_widget: tk.Text) -> None:
        self.text_widget = text_widget

    def log(self, prefix: str, message: str) -> None:
        line = f"{prefix} {message}"
        print(line, file=sys.stderr)
        self.queue.put(line + "\n")

    def info(self, message: str) -> None:
        self.log(LOG_PREFIX_INFO, message)

    def warn(self, message: str) -> None:
        self.log(LOG_PREFIX_WARN, message)

    def error(self, message: str) -> None:
        self.log(LOG_PREFIX_ERROR, message)

    def task(self, message: str) -> None:
        self.log(LOG_PREFIX_TASK, message)

    def file(self, message: str) -> None:
        self.log(LOG_PREFIX_FILE, message)

    def pump(self):
        """
        Drain the queue into the UI text widget.
        This should be called periodically from the Tkinter main thread.
        """
        if self.text_widget is None:
            while not self.queue.empty():
                _ = self.queue.get_nowait()
            return

        try:
            while True:
                line = self.queue.get_nowait()
                self.text_widget.insert(tk.END, line)
                self.text_widget.see(tk.END)
        except queue.Empty:
            pass

        if not self._stop:
            self.text_widget.after(100, self.pump)

    def stop(self):
        self._stop = True


def load_tasklist(tasklist_path: str, logger: UILogger) -> List[Dict[str, Any]]:
    logger.info(f"Loading tasklist from: {tasklist_path}")
    if not os.path.exists(tasklist_path):
        logger.error(f"Tasklist not found at: {tasklist_path}")
        return []

    try:
        with open(tasklist_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            logger.error("Tasklist JSON is not a list.")
            return []
        logger.info(f"Loaded {len(data)} tasks from tasklist.")
        return data
    except Exception as e:
        logger.error(f"Failed to load tasklist JSON: {e}")
        return []


def discover_python_files(root_folder: str, logger: UILogger) -> List[str]:
    logger.info(f"Scanning for Python files in: {root_folder}")
    results: List[str] = []

    for dirpath, dirnames, filenames in os.walk(root_folder):
        for name in filenames:
            _, ext = os.path.splitext(name)
            if ext.lower() in VALID_EXTENSIONS:
                full_path = os.path.join(dirpath, name)
                results.append(full_path)

    logger.info(f"Discovered {len(results)} Python files.")
    return results

# =========================================================
# 4. CORE PIPELINE ROLES (STUBS)
# =========================================================

class RefactorContext:
    """
    Per-file context for the refactor pipeline.
    """

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.original_source: str = ""
        self.ir: Dict[str, Any] = {}
        self.scaffold_source: str = ""


class ParserRole:
    """
    Task: 'parse_file'
    Loads the file and extracts a minimal IR.
    """

    TASK_NAME = "parse_file"

    def run(self, ctx: RefactorContext, logger: UILogger) -> None:
            import ast

            logger.task(f"[{self.TASK_NAME}] Parsing file: {ctx.file_path}")
            try:
                with open(ctx.file_path, "r", encoding="utf-8") as f:
                    ctx.original_source = f.read()
            except Exception as e:
                logger.error(f"[{self.TASK_NAME}] Failed to read file: {e}")
                return

            try:
                tree = ast.parse(ctx.original_source)
            except Exception as e:
                logger.error(f"[{self.TASK_NAME}] AST parse error: {e}")
                return

            ir = {
                "file_path": ctx.file_path,
                "service_name": None,
                "imports": [],
                "endpoints": [],
                "metadata": {},
            }

            # --- Extract imports ---
            for node in tree.body:
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        ir["imports"].append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        ir["imports"].append(f"{module}.{alias.name}")

            # --- Find the service class ---
            for node in tree.body:
                if isinstance(node, ast.ClassDef):
                    for deco in node.decorator_list:
                        if isinstance(deco, ast.Call) and getattr(deco.func, "id", None) == "service_metadata":
                            ir["service_name"] = node.name

                            # Extract metadata arguments
                            meta = {}
                            for kw in deco.keywords:
                                try:
                                    meta[kw.arg] = ast.literal_eval(kw.value)
                                except Exception:
                                    meta[kw.arg] = None
                            ir["metadata"] = meta

                            # Extract endpoints
                            for item in node.body:
                                if isinstance(item, ast.FunctionDef):
                                    for d in item.decorator_list:
                                        if isinstance(d, ast.Call) and getattr(d.func, "id", None) == "service_endpoint":
                                            endpoint_info = {"name": item.name, "inputs": {}, "outputs": {}, "description": None, "tags": [], "side_effects": [], "mode": "sync"}
                                            for kw in d.keywords:
                                                try:
                                                    endpoint_info[kw.arg] = ast.literal_eval(kw.value)
                                                except Exception:
                                                    endpoint_info[kw.arg] = None
                                            ir["endpoints"].append(endpoint_info)

            ctx.ir = ir
            logger.info(f"[{self.TASK_NAME}] IR extracted: service={ir['service_name']}, endpoints={len(ir['endpoints'])}")


class ScaffoldRole:
    """
    Task: 'generate_scaffold'
    Creates the symbolic scaffold with placeholders.
    """

    TASK_NAME = "generate_scaffold"

    # --- STUB SCAFFOLD (will be replaced by patch) ---
    SCAFFOLD_TEMPLATE = """# {{IMPORTS}}

    from microservice_std_lib import service_metadata, service_endpoint
    from base_service import BaseService
    from typing import Dict, Any, Optional

    @service_metadata(
        name=\"{{SERVICE_NAME}}\",
        version=\"{{VERSION}}\",
        description=\"{{DESCRIPTION}}\",
        tags={{TAGS}},
        capabilities={{CAPABILITIES}},
        dependencies={{DEPENDENCIES}},
        side_effects={{SIDE_EFFECTS}}
    )
    class {{CLASS_NAME}}(BaseService):
        def __init__(self):
            super().__init__(\"{{SERVICE_NAME}}\")
            # {{INIT}}

        # {{ENDPOINTS}}
    """

    def run(self, ctx: RefactorContext, logger: UILogger) -> None:
        logger.task(f"[{self.TASK_NAME}] Generating scaffold.")
        ctx.scaffold_source = self.SCAFFOLD_TEMPLATE
        logger.info(f"[{self.TASK_NAME}] Scaffold initialized (stub).")


class PatchRole:
    """
    Handles all patch_* tasks.
    """

    SUPPORTED_TASKS = {
        "patch_imports",
        "patch_metadata",
        "patch_class_header",
        "patch_init",
        "patch_endpoints",
        "final_cleanup",
    }

    def __init__(self, get_base_dir):
        """get_base_dir: callable that returns the current sandbox folder (or None)."""
        self.get_base_dir = get_base_dir
        self.patcher = None

    def run(self, task_name: str, ctx: RefactorContext, logger: UILogger) -> None:
        if task_name not in self.SUPPORTED_TASKS:
            logger.warn(f"[PatchRole] Unsupported task: {task_name}")
            return

        base_dir = self.get_base_dir()
        if not base_dir:
            logger.warn(f"[PatchRole] No base directory selected; skipping task: {task_name}")
            return

        self._ensure_patcher(base_dir, logger)
        if self.patcher is None:
            logger.error("[PatchRole] Patcher could not be initialized.")
            return

        logger.task(f"[{task_name}] Generating patch hunk...")
        hunk_obj = self._generate_patch_hunk(task_name, ctx, logger)

        if not hunk_obj:
            logger.warn(f"[{task_name}] No hunk generated.")
            return

        logger.task(f"[{task_name}] Applying patch hunk via TokenizingPatcherMS...")
        self._apply_patch(hunk_obj, ctx, base_dir, logger)

    def _ensure_patcher(self, base_dir: str, logger: UILogger) -> None:
        if self.patcher is not None:
            return
        try:
            self.patcher = TokenizingPatcherMS(
                config={
                    "base_dir": base_dir,
                    "default_force_indent": False,
                    "allow_absolute_paths": False,
                }
            )
            logger.info(f"[PatchRole] TokenizingPatcherMS initialized with base_dir={base_dir}")
        except Exception as e:
            logger.error(f"[PatchRole] Failed to initialize TokenizingPatcherMS: {e}")
            self.patcher = None

    def _generate_patch_hunk(self, task_name: str, ctx: RefactorContext, logger: UILogger) -> Dict[str, Any]:
            """
            Generate a JSON patch hunk for the given task.
            Patch 4 implements the first real transformation: patch_imports.
            """

            # ------------------------------------------------------------
            # PATCH 4: REAL IMPLEMENTATION FOR patch_imports
            # ------------------------------------------------------------
            if task_name == "patch_imports":
                imports = ctx.ir.get("imports", [])

                # Normalize imports
                cleaned = []
                for imp in imports:
                    if imp and isinstance(imp, str):
                        cleaned.append(imp.strip())

                cleaned = sorted(set(cleaned))

                # Convert to canonical Python import lines
                lines = []
                for imp in cleaned:
                    if "." in imp:
                        module, name = imp.rsplit(".", 1)
                        lines.append(f"from {module} import {name}")
                    else:
                        lines.append(f"import {imp}")

                import_block = "\n".join(lines)

                # Build patch hunk to replace the IMPORTS placeholder
                return {
                    "hunks": [
                        {
                            "description": "Insert canonical import block",
                            "search_block": "# {{IMPORTS}}",
                            "replace_block": import_block,
                            "use_patch_indent": false
                        }
                    ]
                }

            # ------------------------------------------------------------
            # PLACEHOLDERS FOR FUTURE PATCHES
            # ------------------------------------------------------------
            if task_name == "patch_metadata":
                        meta = ctx.ir.get("metadata", {})

                        # Extract fields with defaults
                        name = meta.get("name", ctx.ir.get("service_name", "UnknownService"))
                        version = meta.get("version", "1.0.0")
                        description = meta.get("description", "No description provided.")
                        tags = meta.get("tags", [])
                        capabilities = meta.get("capabilities", [])
                        dependencies = meta.get("dependencies", [])
                        side_effects = meta.get("side_effects", [])

                        # Convert lists/dicts to Python literal strings
                        import json
                        tags_str = json.dumps(tags)
                        capabilities_str = json.dumps(capabilities)
                        dependencies_str = json.dumps(dependencies)
                        side_effects_str = json.dumps(side_effects)

                        # Build the metadata block
                        metadata_block = f"@service_metadata(\n    name=\"{name}\",\n    version=\"{version}\",\n    description=\"{description}\",\n    tags={tags_str},\n    capabilities={capabilities_str},\n    dependencies={dependencies_str},\n    side_effects={side_effects_str}\n)"

                        return {
                            "hunks": [
                                {
                                    "description": "Insert service metadata block",
                                    "search_block": "@service_metadata(",
                                    "replace_block": metadata_block,
                                    "use_patch_indent": false
                                }
                            ]
                        }

            if task_name == "patch_class_header":
                        # Extract class name from IR
                        class_name = ctx.ir.get("service_name", "UnknownService")

                        # Build replacement header
                        header_block = f"class {class_name}(BaseService):"

                        return {
                            "hunks": [
                                {
                                    "description": "Replace class header with actual service class name",
                                    "search_block": "class {{CLASS_NAME}}(BaseService):",
                                    "replace_block": header_block,
                                    "use_patch_indent": false
                                }
                            ]
                        }

            if task_name == "patch_init":
                        meta = ctx.ir.get("metadata", {})
                        service_name = ctx.ir.get("service_name", "UnknownService")

                        # Build metadata dict literal
                        import json
                        meta_literal = json.dumps(meta, indent=4)

                        init_block = (
                            f"super().__init__(\"{service_name}\")\n"
                            f"        self.metadata = {meta_literal}\n"
                            f"        self.endpoints = []  # populated in patch_endpoints"
                        )

                        return {
                            "hunks": [
                                {
                                    "description": "Insert canonical __init__ body",
                                    "search_block": "# {{INIT}}",
                                    "replace_block": init_block,
                                    "use_patch_indent": false
                                }
                            ]
                        }

            if task_name == "patch_endpoints":
                        endpoints = ctx.ir.get("endpoints", [])
                        import json

                        blocks = []
                        for ep in endpoints:
                            name = ep.get("name", "unnamed_endpoint")
                            inputs = json.dumps(ep.get("inputs", {}), indent=4)
                            outputs = json.dumps(ep.get("outputs", {}), indent=4)
                            description = ep.get("description", "Auto-generated endpoint.")
                            tags = json.dumps(ep.get("tags", []))
                            side_effects = json.dumps(ep.get("side_effects", []))
                            mode = ep.get("mode", "sync")

                            decorator = (
                                f"@service_endpoint(\n"
                                f"    name=\"{name}\",\n"
                                f"    inputs={inputs},\n"
                                f"    outputs={outputs},\n"
                                f"    description=\"{description}\",\n"
                                f"    tags={tags},\n"
                                f"    side_effects={side_effects},\n"
                                f"    mode=\"{mode}\"\n"
                                f")"
                            )

                            method = (
                                f"def {name}(self, **kwargs):\n"
                                f"        \"\"\"Auto-generated endpoint method.\n"
                                f"        Inputs: {inputs}\n"
                                f"        Outputs: {outputs}\n"
                                f"        \"\"\"\n"
                                f"        pass"
                            )

                            blocks.append(decorator + "\n" + method)

                        endpoint_block = "\n\n".join(blocks) if blocks else "# No endpoints detected"

                        return {
                            "hunks": [
                                {
                                    "description": "Insert generated endpoint methods",
                                    "search_block": "# {{ENDPOINTS}}",
                                    "replace_block": endpoint_block,
                                    "use_patch_indent": false
                                }
                            ]
                        }

            if task_name == "final_cleanup":
                        """
                        Patch 9: Final cleanup pass.
                        Removes leftover placeholders, normalizes whitespace, and ensures
                        the file ends cleanly.
                        """

                        cleanup_hunks = [
                            {
                                "description": "Remove leftover placeholder markers",
                                "search_block": "{{IMPORTS}}",
                                "replace_block": "",
                                "use_patch_indent": false
                            },
                            {
                                "description": "Remove leftover metadata placeholder",
                                "search_block": "{{METADATA}}",
                                "replace_block": "",
                                "use_patch_indent": false
                            },
                            {
                                "description": "Remove leftover class name placeholder",
                                "search_block": "{{CLASS_NAME}}",
                                "replace_block": "",
                                "use_patch_indent": false
                            },
                            {
                                "description": "Remove leftover init placeholder",
                                "search_block": "{{INIT}}",
                                "replace_block": "",
                                "use_patch_indent": false
                            },
                            {
                                "description": "Remove leftover endpoints placeholder",
                                "search_block": "{{ENDPOINTS}}",
                                "replace_block": "",
                                "use_patch_indent": false
                            },
                            {
                                "description": "Collapse double blank lines",
                                "search_block": "\n\n\n",
                                "replace_block": "\n\n",
                                "use_patch_indent": false
                            },
                            {
                                "description": "Ensure file ends with a newline",
                                "search_block": "\n$",
                                "replace_block": "\n",
                                "use_patch_indent": false
                            }
                        ]

                        return {"hunks": cleanup_hunks}

            logger.warn(f"No hunk generator implemented for task: {task_name}")
            return None

    def _apply_patch(self, hunk_obj: Dict[str, Any], ctx: RefactorContext, base_dir: str, logger: UILogger) -> None:
        """Call TokenizingPatcherMS to apply the patch to ctx.file_path."""
        import os
        import json

        try:
            # Compute path relative to base_dir so the patcher stays sandboxed
            rel_path = os.path.relpath(ctx.file_path, base_dir)
        except Exception as e:
            logger.error(f"[PatchRole] Failed to compute relative path for {ctx.file_path}: {e}")
            return

        try:
            schema_str = json.dumps(hunk_obj)
        except Exception as e:
            logger.error(f"[PatchRole] Failed to serialize patch hunk: {e}")
            return

        # First do a dry-run
        try:
            dry_result = self.patcher.apply_patch_to_file(
                target_path=rel_path,
                patch_schema=schema_str,
                dry_run=True,
                return_preview=True,
            )
        except Exception as e:
            logger.error(f"[PatchRole] Exception during dry-run patch: {e}")
            return

        if not dry_result.get("success"):
            logger.error(f"[PatchRole] Dry-run patch failed: {dry_result.get('message')}")
            return

        preview = dry_result.get("patched_preview")
        if preview is not None:
            logger.info(f"[PatchRole] Dry-run patched preview length: {len(preview)} characters")

        # Now apply destructively
        try:
            apply_result = self.patcher.apply_patch_to_file(
                target_path=rel_path,
                patch_schema=schema_str,
                dry_run=False,
                return_preview=False,
            )
        except Exception as e:
            logger.error(f"[PatchRole] Exception during destructive patch: {e}")
            return

        if not apply_result.get("success"):
            logger.error(f"[PatchRole] Destructive patch failed: {apply_result.get('message')}")
            return

        logger.info(f"[PatchRole] Patch applied successfully to {ctx.file_path}")


# =========================================================
# 5. TASKLIST-DRIVEN PIPELINE EXECUTION
# =========================================================

class RefactorEngine:
    """
    Orchestrates:
    - loading the tasklist
    - discovering files
    - running each task over each file
    """

    def __init__(self, logger: UILogger, get_base_dir, tasklist_path: str = DEFAULT_TASKLIST_PATH):
        self.logger = logger
        self.get_base_dir = get_base_dir
        self.tasklist_path = tasklist_path
        self.tasklist: List[Dict[str, Any]] = []
        self.parser = ParserRole()
        self.scaffold = ScaffoldRole()
        self.patcher = PatchRole(get_base_dir)

    def load_tasklist(self) -> None:
        self.tasklist = load_tasklist(self.tasklist_path, self.logger)

    def run_for_folder(self, folder: str) -> None:
        if not self.tasklist:
            self.logger.error("No tasklist loaded. Aborting.")
            return

        files = discover_python_files(folder, self.logger)
        if not files:
            self.logger.warn("No Python files found in selected folder.")
            return

        for file_path in files:
            self.logger.file(f"Processing file: {file_path}")
            ctx = RefactorContext(file_path)
            self._run_for_file(ctx)

        self.logger.info("Refactor pipeline complete for all files.")

    def _run_for_file(self, ctx: RefactorContext) -> None:
        for task in self.tasklist:
            task_name = task.get("task")
            description = task.get("description", "")
            self.logger.task(f"Running task '{task_name}': {description}")

            if task_name == ParserRole.TASK_NAME:
                self.parser.run(ctx, self.logger)
            elif task_name == ScaffoldRole.TASK_NAME:
                self.scaffold.run(ctx, self.logger)
            else:
                self.patcher.run(task_name, ctx, self.logger)

            time.sleep(0.05)

# =========================================================
# 6. TKINTER UI
# =========================================================

class RefactorApp(tk.Tk):
    """
    Tkinter UI wrapper for:
    - choosing a folder
    - kicking off the refactor pipeline
    - monitoring logs
    """

    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")

        self.logger = UILogger()
        self.engine = RefactorEngine(self.logger, lambda: self.selected_folder)

        self.selected_folder: Optional[str] = None
        self.worker_thread: Optional[threading.Thread] = None
        self._is_running = False

        self._build_ui()

        self.logger.attach_widget(self.log_text)
        self.logger.pump()

        self.engine.load_tasklist()

    def _build_ui(self) -> None:
        top_frame = tk.Frame(self)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        folder_label = tk.Label(top_frame, text="Target folder:")
        folder_label.pack(side=tk.LEFT)

        self.folder_var = tk.StringVar(value="")
        folder_entry = tk.Entry(top_frame, textvariable=self.folder_var, width=60)
        folder_entry.pack(side=tk.LEFT, padx=5)

        browse_btn = tk.Button(top_frame, text="Browse...", command=self._on_browse)
        browse_btn.pack(side=tk.LEFT, padx=5)

        self.run_btn = tk.Button(top_frame, text="Run Refactor", command=self._on_run)
        self.run_btn.pack(side=tk.LEFT, padx=10)

        self.status_var = tk.StringVar(value="Idle")
        status_label = tk.Label(self, textvariable=self.status_var, anchor="w")
        status_label.pack(side=tk.TOP, fill=tk.X, padx=10)

        self.log_text = scrolledtext.ScrolledText(self, font=LOG_FONT, wrap=tk.WORD)
        self.log_text.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)

    def _on_browse(self) -> None:
        folder = filedialog.askdirectory(title="Select folder containing microservices")
        if folder:
            self.selected_folder = folder
            self.folder_var.set(folder)
            self.logger.info(f"Selected folder: {folder}")

    def _on_run(self) -> None:
        if self._is_running:
            messagebox.showinfo("In Progress", "The refactor pipeline is already running.")
            return

        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showerror("Invalid Folder", "Please select a valid folder first.")
            return

        self.selected_folder = folder
        self._is_running = True
        self.status_var.set("Running...")
        self.run_btn.config(state=tk.DISABLED)

        self.logger.info(f"Starting refactor pipeline for folder: {folder}")

        self.worker_thread = threading.Thread(
            target=self._run_in_background,
            args=(folder,),
            daemon=True,
        )
        self.worker_thread.start()

        self.after(250, self._check_worker)

    def _run_in_background(self, folder: str) -> None:
        try:
            self.engine.run_for_folder(folder)
        except Exception as e:
            self.logger.error(f"Unexpected error in worker thread: {e}")
        finally:
            self._is_running = False

    def _check_worker(self) -> None:
        if self._is_running:
            self.after(250, self._check_worker)
        else:
            self.status_var.set("Idle")
            self.run_btn.config(state=tk.NORMAL)
            self.logger.info("Refactor pipeline finished or aborted.")

# =========================================================
# 7. ENTRYPOINT
# =========================================================

def main():
    app = RefactorApp()
    app.mainloop()


if __name__ == "__main__":
    main()




#!/usr/bin/env python3
"""
ui.py

Tkinter UI wrapper for _HelperScriptExeMAKER.

Design:
- Thin wrapper that gathers user inputs and calls engine.build_exe(...)
- Runs build in a background thread so UI stays responsive
- Streams logs into UI via a logging.Handler
"""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
# No changes to imports; assuming 'engine' is available at runtime
from typing import Optional, List

# -----------------------------
# Theme
# -----------------------------

THEME = {
    "bg": "#151521",
    "panel": "#1e1e2f",
    "panel2": "#24243a",
    "text": "#e6e6e6",
    "muted": "#b6b6c8",
    "accent": "#7aa2f7",
    "entry_bg": "#101019",
    "entry_fg": "#e6e6e6",
    "border": "#3a3a5e",
}


# -----------------------------
# Logging -> Tkinter bridge
# -----------------------------

class TkQueueHandler(logging.Handler):
    """Logging handler that writes formatted log records to a queue."""
    def __init__(self, q: "queue.Queue[str]"):
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            self.q.put(msg)
        except Exception:
            # Never crash UI due to logging
            pass


# -----------------------------
# UI State
# -----------------------------

@dataclass
class BuildFormState:
    project_root: str = ""
    dest_dir: str = ""
    mode: str = "onedir"      # onedir | onefile
    clean: bool = False
    console: bool = False
    icon_path: str = ""
    include_data_text: str = ""  # multiline: relative folder names or absolute paths


# -----------------------------
# Main App
# -----------------------------

class ExeMakerUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("HelperScriptExeMAKER")
        self.root.geometry("980x700")

        # Dark theme baseline (applied once)
        self._apply_dark_theme()

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self._build_thread: Optional[threading.Thread] = None
        self._build_in_progress = False

        self.state = BuildFormState()

        self._setup_logging_bridge()
        self._build_layout()
        self._schedule_log_drain()

    def _apply_dark_theme(self) -> None:
        """Configure a simple dark theme for tk + ttk widgets."""
        self.colors = THEME.copy()

        try:
            self.root.configure(bg=self.colors["bg"])
        except Exception:
            pass

        style = ttk.Style(self.root)

        try:
            style.theme_use("clam")
        except Exception:
            pass

        bg = self.colors["bg"]
        panel = self.colors["panel"]
        panel2 = self.colors["panel2"]
        fg = self.colors["text"]
        muted = self.colors["muted"]
        accent = self.colors["accent"]
        entry_bg = self.colors["entry_bg"]
        entry_fg = self.colors["entry_fg"]
        border = self.colors["border"]

        # Base
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground=fg)
        style.configure("TLabelframe", background=bg, foreground=fg)
        style.configure("TLabelframe.Label", background=bg, foreground=fg)

        # Inputs
        style.configure("TEntry", fieldbackground=entry_bg, foreground=entry_fg)
        style.configure("TCombobox", fieldbackground=entry_bg, foreground=entry_fg)

        # Buttons
        style.configure(
            "TButton",
            background=panel,
            foreground=fg,
            bordercolor=border,
            focusthickness=1,
            focuscolor=accent,
        )
        try:
            style.map(
                "TButton",
                background=[("active", panel2), ("pressed", panel2)],
                foreground=[("disabled", muted)],
            )
        except Exception:
            pass

    def _setup_logging_bridge(self) -> None:
        """Attach a queue handler to root logger so engine logs appear in UI."""
        handler = TkQueueHandler(self.log_queue)
        handler.setLevel(logging.DEBUG)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s", "%H:%M:%S")
        handler.setFormatter(fmt)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)

    def _build_layout(self) -> None:
        """Construct the UI layout."""
        # Top frame: form controls
        top = ttk.Frame(self.root, padding=10)
        top.pack(side=tk.TOP, fill=tk.X)

        # Middle: include-data + options
        mid = ttk.Frame(self.root, padding=10)
        mid.pack(side=tk.TOP, fill=tk.BOTH, expand=False)

        # Bottom: logs
        bottom = ttk.Frame(self.root, padding=10)
        bottom.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        # --- Row 0: Project Root
        ttk.Label(top, text="Target Project Root:").grid(row=0, column=0, sticky="w")
        self.project_var = tk.StringVar(value=self.state.project_root)
        project_entry = ttk.Entry(top, textvariable=self.project_var, width=80)
        project_entry.grid(row=0, column=1, sticky="we", padx=(8, 8))
        ttk.Button(top, text="Browse…", command=self._browse_project).grid(row=0, column=2, sticky="e")

        # --- Row 1: Destination Dir
        ttk.Label(top, text="Destination Folder:").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.dest_var = tk.StringVar(value=self.state.dest_dir)
        dest_entry = ttk.Entry(top, textvariable=self.dest_var, width=80)
        dest_entry.grid(row=1, column=1, sticky="we", padx=(8, 8), pady=(8, 0))
        ttk.Button(top, text="Browse…", command=self._browse_dest).grid(row=1, column=2, sticky="e", pady=(8, 0))

        # Make column 1 stretch
        top.grid_columnconfigure(1, weight=1)

        # --- Options row
        opts = ttk.Frame(mid)
        opts.pack(side=tk.TOP, fill=tk.X)

        ttk.Label(opts, text="Mode:").grid(row=0, column=0, sticky="w")
        self.mode_var = tk.StringVar(value=self.state.mode)
        mode_combo = ttk.Combobox(opts, textvariable=self.mode_var, values=["onedir", "onefile"], width=10, state="readonly")
        mode_combo.grid(row=0, column=1, sticky="w", padx=(6, 16))

        self.clean_var = tk.BooleanVar(value=self.state.clean)
        ttk.Checkbutton(opts, text="Clean build artifacts", variable=self.clean_var).grid(row=0, column=2, sticky="w", padx=(0, 16))

        self.console_var = tk.BooleanVar(value=self.state.console)
        ttk.Checkbutton(opts, text="Console window", variable=self.console_var).grid(row=0, column=3, sticky="w")

        # --- Icon picker row
        ttk.Label(opts, text="Icon (.ico):").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.icon_var = tk.StringVar(value=self.state.icon_path)
        icon_entry = ttk.Entry(opts, textvariable=self.icon_var, width=60)
        icon_entry.grid(row=1, column=1, columnspan=2, sticky="we", padx=(6, 8), pady=(8, 0))
        ttk.Button(opts, text="Browse…", command=self._browse_icon).grid(row=1, column=3, sticky="e", pady=(8, 0))

        opts.grid_columnconfigure(2, weight=1)

        # --- Include-data box
        inc_label = "Include Data Directories (one per line; relative to project root or absolute paths)"
        inc = ttk.LabelFrame(mid, text=inc_label)
        inc.pack(side=tk.TOP, fill=tk.BOTH, expand=False, pady=(10, 0))

        self.include_text = tk.Text(inc, height=6, wrap="none")
        self.include_text.configure(
            bg="#1e1e2f",
            fg="#e6e6e6",
            insertbackground="#e6e6e6",
            highlightthickness=1,
            highlightbackground="#2a2a3f",
            relief="flat",
        )
        self.include_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll_y = ttk.Scrollbar(inc, orient="vertical", command=self.include_text.yview)
        scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        self.include_text.configure(yscrollcommand=scroll_y.set)

        # --- Action buttons
        actions = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        actions.pack(side=tk.TOP, fill=tk.X)

        self.build_btn = ttk.Button(actions, text="Build EXE", command=self._on_build)
        self.build_btn.pack(side=tk.LEFT)

        self.cert_btn = ttk.Button(actions, text="Setup Self-Sign Cert", command=self._on_setup_cert)
        self.cert_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(actions, textvariable=self.status_var).pack(side=tk.LEFT, padx=(12, 0))

        # --- Logs
        log_frame = ttk.LabelFrame(bottom, text="Build Log")
        log_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)

        self.log_text = tk.Text(log_frame, wrap="word")
        self.log_text.configure(
            bg="#0f0f16",
            fg="#e6e6e6",
            insertbackground="#e6e6e6",
            highlightthickness=1,
            highlightbackground="#2a2a3f",
            relief="flat",
        )
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.log_text.configure(yscrollcommand=log_scroll.set)

        # Initial guidance
        self._append_log("UI ready. Choose a project root and destination, then click Build EXE.\n")

    # ---------- Browse handlers ----------
    def _browse_project(self) -> None:
        path = filedialog.askdirectory(title="Select Target Project Root")
        if path:
            self.project_var.set(path)

    def _browse_dest(self) -> None:
        path = filedialog.askdirectory(title="Select Destination Folder")
        if path:
            self.dest_var.set(path)

    def _browse_icon(self) -> None:
        path = filedialog.askopenfilename(
            title="Select .ico file",
            filetypes=[("Icon files", "*.ico"), ("All files", "*.*")]
        )
        if path:
            self.icon_var.set(path)

    # ---------- Build workflow ----------
    def _on_setup_cert(self) -> None:
        project = self.project_var.get().strip()
        if not project or not Path(project).exists():
            messagebox.showerror("Error", "Select a project root first.")
            return
        
        cert_path = Path(project) / "developer_cert.pfx"
        try:
            import engine
            if engine.create_self_signed_cert(cert_path):
                messagebox.showinfo("Cert Created", f"Certificate created at {cert_path.name}.\n\nIMPORTANT: You must manually install this into your 'Trusted Root Certification Authorities' once for signing to be valid on this PC.")
            else:
                messagebox.showerror("Error", "Failed to create cert. Ensure PowerShell is accessible.")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _on_setup_cert(self) -> None:
        project = self.project_var.get().strip()
        if not project or not Path(project).exists():
            messagebox.showerror("Error", "Select a project root first.")
            return
        
        cert_path = Path(project) / "developer_cert.pfx"
        try:
            if __package__:
                from . import engine
            else:
                import engine

            if engine.create_self_signed_cert(cert_path):
                messagebox.showinfo("Cert Created", f"Certificate created at {cert_path.name}.\n\nIMPORTANT: You must manually install this into your 'Trusted Root Certification Authorities' once for signing to be valid on this PC.")
            else:
                messagebox.showerror("Error", "Failed to create cert. Ensure PowerShell is accessible.")
        except Exception as e:
            messagebox.showerror("Error", f"Import or Execution Error: {str(e)}")

    def _on_setup_cert(self) -> None:
        project = self.project_var.get().strip()
        if not project or not Path(project).exists():
            messagebox.showerror("Error", "Select a project root first.")
            return
        
        cert_path = Path(project) / "developer_cert.pfx"
        try:
            if __package__:
                from . import engine
            else:
                import engine

            if engine.create_self_signed_cert(cert_path):
                messagebox.showinfo("Cert Created", f"Certificate created at {cert_path.name}.\n\nIMPORTANT: You must manually install this into your 'Trusted Root Certification Authorities' once for signing to be valid on this PC.")
            else:
                messagebox.showerror("Error", "Failed to create cert. Ensure PowerShell is accessible.")
        except Exception as e:
            messagebox.showerror("Error", f"Import or Execution Error: {str(e)}")

    def _on_build(self) -> None:
        if self._build_in_progress:
            messagebox.showinfo("Build in progress", "A build is already running.")
            return

        project = self.project_var.get().strip()
        dest = self.dest_var.get().strip()
        if not project or not Path(project).exists():
            messagebox.showerror("Invalid Project Root", "Please choose a valid Target Project Root folder.")
            return
        if not dest or not Path(dest).exists():
            messagebox.showerror("Invalid Destination", "Please choose a valid Destination folder.")
            return

        mode = self.mode_var.get().strip() or "onedir"
        clean = bool(self.clean_var.get())
        console = bool(self.console_var.get())
        icon = self.icon_var.get().strip() or None

        include_data = self._parse_include_data(project)

        self._build_in_progress = True
        self.build_btn.configure(state="disabled")
        self.status_var.set("Building…")

        self._append_log("\n--- BUILD START ---\n")
        self._append_log(f"Project: {project}\nDest:    {dest}\nMode:    {mode}\nClean:   {clean}\nConsole: {console}\n")
        if icon:
            self._append_log(f"Icon:    {icon}\n")
        if include_data:
            self._append_log(f"Include: {include_data}\n")

        self._build_thread = threading.Thread(
            target=self._build_worker,
            args=(project, dest, mode, clean, console, icon, include_data),
            daemon=True
        )
        self._build_thread.start()

    def _parse_include_data(self, project_root: str) -> List[str]:
        """Read include-data lines from text box."""
        raw = self.include_text.get("1.0", "end").strip()
        if not raw:
            return []
        lines = []
        for line in raw.splitlines():
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            lines.append(s)
        return lines

    def _build_worker(
        self,
        project: str,
        dest: str,
        mode: str,
        clean: bool,
        console: bool,
        icon: Optional[str],
        include_data: List[str],
    ) -> None:
        """Background thread: call engine.build_exe and report results."""
        try:
            try:
                from . import engine  # type: ignore
            except (ImportError, ValueError):
                import engine  # type: ignore

            output_path, report_path = engine.build_exe(
                project=project,
                dest=dest,
                mode=mode,
                clean=clean,
                console=console,
                icon=icon,
                include_data=include_data,
                venv=None,
            )
            msg = f"[UI] Build complete.\n[UI] Output: {output_path}\n[UI] Report: {report_path}\n"
            self.log_queue.put(msg)
            self._finish_build(success=True)

        except Exception as e:
            self.log_queue.put(f"[UI] ERROR: {e}\n")
            self._finish_build(success=False)

    def _finish_build(self, success: bool) -> None:
        """Marshal UI updates back to the Tk thread."""
        def _done():
            self._build_in_progress = False
            self.build_btn.configure(state="normal")
            self.status_var.set("Build complete." if success else "Build failed.")
            self._append_log("--- BUILD END ---\n")
            if success:
                messagebox.showinfo("Build complete", "Build completed successfully.")
            else:
                messagebox.showerror("Build failed", "Build failed. See log output for details.")

        self.root.after(0, _done)

    # ---------- Log display ----------
    def _schedule_log_drain(self) -> None:
        self._drain_logs()
        self.root.after(100, self._schedule_log_drain)

    def _drain_logs(self) -> None:
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._append_log(msg + "\n" if not msg.endswith("\n") else msg)
        except queue.Empty:
            return

    def _append_log(self, text: str) -> None:
        self.log_text.insert("end", text)
        self.log_text.see("end")


def run() -> None:
    root = tk.Tk()
    app = ExeMakerUI(root)
    root.mainloop()


def main() -> int:
    run()
    return 0


if __name__ == "__main__":
    run()



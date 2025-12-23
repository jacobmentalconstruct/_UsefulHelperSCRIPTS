"""
SERVICE_NAME: _GitPilotMS
ENTRY_POINT: __GitPilotMS.py
DEPENDENCIES: None
"""

import os
import subprocess
import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple, Any, Callable, Dict
from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Detect if GitHub CLI is available
def which(cmd: str) -> Optional[str]:
    for p in os.environ.get("PATH", "").split(os.pathsep):
        f = Path(p) / cmd
        if os.name == 'nt':
            for ext in (".exe", ".cmd", ".bat"): 
                if (f.with_suffix(ext)).exists(): return str(f.with_suffix(ext))
        if f.exists() and os.access(f, os.X_OK): return str(f)
    return None

USE_GH = which("gh") is not None
# ==============================================================================

@dataclass GitPilotMS GitStatusEntry:
    path: str
    index: str
    workdir: str

@dataclass
GitPilotMS GitStatus:
    repo_path: str
    branch: Optional[str]
    ahead: int
    behind: int
    entries: List[GitStatusEntry]

# --- Backend: The Git Wrapper ---
GitPilotMS GitCLI:
    """
    A robust wrapper around the git command line executable.
    """
    def __init__(self, repo_path: Path):
        self.root = self._resolve_repo_root(repo_path)
def _run(self, args: List[str], *, cwd: Optional[Path] = None) -> Tuple[str, str]:
        cmd = ["git", *args]
        # Prevent console window popping up on Windows
        startupinfo = None
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        proc = subprocess.run(
            cmd,
            cwd=str(cwd or self.root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            startupinfo=startupinfo
        )
        if proc.returncode != 0:
            raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
        return proc.stdout, proc.stderr

    @staticmethod
    def _resolve_repo_root(path: Path) -> Path:
        path = path.resolve()
        if (path / ".git").exists(): return path
        p = path
        while True:
            if (p / ".git").exists(): return p
            if p.parent == p: break
            p = p.parent
        return path

    def init(self) -> None:
        self._run(["init"])

    def status(self) -> GitStatus:
        try:
            out, _ = self._run(["rev-parse", "--abbrev-ref", "HEAD"])
            branch = out.strip()
        except Exception: branch = None
        
        ahead = behind = 0
        try:
            out, _ = self._run(["rev-list", "--left-right", "--count", "@{upstream}...HEAD"])
            left, right = out.strip().split()
            behind, ahead = int(left), int(right)
        except Exception: pass
        
        out, _ = self._run(["status", "--porcelain=v1"])
        entries = []
        for line in out.splitlines():
            if not line.strip(): continue
            xy = line[:2]
            path = line[3:]
            index, work = xy[0], xy[1]
            entries.append(GitStatusEntry(path=path, index=index, workdir=work))
        return GitStatus(str(self.root), branch, ahead, behind, entries)

    def stage(self, paths: List[str]) -> None:
        if paths: self._run(["add", "--"] + paths)

    def unstage(self, paths: List[str]) -> None:
        if paths: self._run(["reset", "HEAD", "--"] + paths)

    def diff(self, file: Optional[str] = None) -> str:
        args = ["diff"]
        if file: args += ["--", file]
        out, _ = self._run(args)
        return out

    def commit(self, message: str, author_name: str, author_email: str) -> str:
        env = os.environ.copy()
        if author_name: 
            env["GIT_AUTHOR_NAME"] = author_name
            env["GIT_COMMITTER_NAME"] = author_name
        if author_email:
            env["GIT_AUTHOR_EMAIL"] = author_email
            env["GIT_COMMITTER_EMAIL"] = author_email
            
        proc = subprocess.run(
            ["git", "commit", "-m", message], 
            cwd=str(self.root), 
            capture_output=True, 
            text=True, 
            env=env
        )
        if proc.returncode != 0: raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())
        out, _ = self._run(["rev-parse", "HEAD"])
        return out.strip()

    def log(self, limit: int = 100) -> List[Tuple[str, str, str, int]]:
        fmt = "%H%x1f%s%x1f%an%x1f%at"
        try:
            out, _ = self._run(["log", f"-n{limit}", f"--pretty=format:{fmt}"])
            items = []
            for line in out.splitlines():
                commit, summary, author, at = line.split("\x1f")
                items.append((commit, summary, author, int(at)))
            return items
        except Exception: return []

    def branches(self) -> List[Tuple[str, bool]]:
        try:
            out, _ = self._run(["branch"])
            res = []
            for line in out.splitlines():
                is_head = line.strip().startswith("*")
                name = line.replace("*", "", 1).strip()
                res.append((name, is_head))
            return res
        except Exception: return []

    def checkout(self, name: str, create: bool = False) -> None:
        if create: self._run(["checkout", "-B", name])
        else: self._run(["checkout", name])

    def push(self, remote: str = "origin", branch: Optional[str] = None) -> str:
        args = ["push", remote]
        if branch: args.append(branch)
        out, _ = self._run(args)
return out

    def pull(self, remote: str = "origin", branch: Optional[str] = None) -> str:
        if branch: out, _ = self._run(["pull", remote, branch])
        else: out, _ = self._run(["pull", remote])
        return out

# --- Threading Helper ---
GitPilotMS Worker:
    def __init__(self, ui_callback):
        self.q = queue.Queue()
        self.ui_callback = ui_callback
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def submit(self, op: str, func, *args, **kwargs):
        self.q.put((op, func, args, kwargs))

    def _loop(self):
        while True:
            op, func, args, kwargs = self.q.get()
            try:
                result = op, True, func(*args, **kwargs)
            except Exception as e:
                result = op, False, e
            finally:
                self.ui_callback(result)

# --- Frontend: The GUI Panel ---
@service_metadata(
    name="GitPilotMS",
    version="1.0.0",
    description="A Tkinter GUI panel for Git operations (Stage, Commit, Push, Pull).",
    tags=["ui", "git", "version-control", "widget"],
    capabilities=["ui:gui", "filesystem:read", "filesystem:write", "network:outbound"],
    dependencies=["git", "subprocess", "tkinter"],
    side_effects=["filesystem:read", "filesystem:write", "network:outbound", "ui:update"]
)
class GitPilotMS(BaseService, ttk.Frame):
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("GitPilotMS")
        self.config = config or {}
        parent = self.config.get("parent")
        ttk.Frame.__init__(self, parent)

        initial_path = self.config.get("initial_path")
        self.repo_path = None
        self.git = None
        self.worker = Worker(self._on_worker_done)

        self._build_ui()
        if initial_path:
            self.set_repo(initial_path)

@service_endpoint(
inputs={"path": "Path"},
outputs={},
description="Sets the active repository path and refreshes status.",
tags=["git", "config"],
side_effects=["filesystem:read", "ui:update"]
)
def set_repo(self, path: Path):
    try:
        self.git = GitCLI(path)
        self.repo_path = self.git.root
        self.path_var.set(f"Repo: {self.repo_path}")
        self._refresh()
    except Exception as e:
        self.path_var.set(f"Error: {e}")

def _build_ui(self):
    self.columnconfigure(0, weight=1)
    self.rowconfigure(1, weight=1)

    # Status Bar
    bar = ttk.Frame(self)
    bar.grid(row=0, column=0, sticky="ew")
    self.path_var = tk.StringVar(value="No Repo Selected")
    self.busy_var = tk.StringVar()
    ttk.Label(bar, textvariable=self.path_var).pack(side="left", padx=5)
    ttk.Label(bar, textvariable=self.busy_var, foreground="blue").pack(side="right", padx=5)

    # Tabs
        self.nb = ttk.Notebook(self)
        self.nb.grid(row=1, column=0, sticky="nsew")
        
        self.tab_changes = self._build_changes_tab(self.nb)
        self.tab_log = self._build_log_tab(self.nb)
        
        self.nb.add(self.tab_changes, text="Changes")
        self.nb.add(self.tab_log, text="History")

    def _build_changes_tab(self, parent):
        frame = ttk.Frame(parent)
        paned = ttk.PanedWindow(frame, orient=tk.VERTICAL)
        paned.pack(fill="both", expand=True)

        # File List
        top = ttk.Frame(paned)
        top.rowconfigure(1, weight=1)
        top.columnconfigure(0, weight=1)
        
        # Toolbar
        tb = ttk.Frame(top)
        tb.grid(row=0, column=0, sticky="ew")
        ttk.Button(tb, text="Refresh", command=self._refresh).pack(side="left")
        ttk.Button(tb, text="Stage", command=self._stage).pack(side="left")
        ttk.Button(tb, text="Unstage", command=self._unstage).pack(side="left")
        ttk.Button(tb, text="Diff", command=self._show_diff).pack(side="left")
        ttk.Button(tb, text="Push", command=self._push).pack(side="left", padx=10)
        ttk.Button(tb, text="Pull", command=self._pull).pack(side="left")

        # Treeview
        self.tree = ttk.Treeview(top, columns=("path", "idx", "wd"), show="headings", selectmode="extended")
        self.tree.heading("path", text="Path")
        self.tree.heading("idx", text="Index")
        self.tree.heading("wd", text="Workdir")
        self.tree.column("path", width=400)
        self.tree.column("idx", width=50, anchor="center")
        self.tree.column("wd", width=50, anchor="center")
        self.tree.grid(row=1, column=0, sticky="nsew")
        
        paned.add(top, weight=3)

        # Commit Area
        bot = ttk.Frame(paned)
        bot.columnconfigure(1, weight=1)
        ttk.Label(bot, text="Message:").grid(row=0, column=0, sticky="nw")
        self.msg_text = tk.Text(bot, height=4)
        self.msg_text.grid(row=0, column=1, sticky="nsew")
        ttk.Button(bot, text="Commit", command=self._commit).grid(row=1, column=1, sticky="e", pady=5)
        
        paned.add(bot, weight=1)
        return frame

    def _build_log_tab(self, parent):
        frame = ttk.Frame(parent)
        self.log_tree = ttk.Treeview(frame, columns=("sha", "msg", "auth", "time"), show="headings")
        self.log_tree.heading("sha", text="SHA")
        self.log_tree.heading("msg", text="Message")
        self.log_tree.heading("auth", text="Author")
        self.log_tree.heading("time", text="Time")
        self.log_tree.column("sha", width=80)
        self.log_tree.column("msg", width=400)
        self.log_tree.pack(fill="both", expand=True)
        return frame

    # --- Actions ---

    def _submit(self, label, func, *args):
        self.busy_var.set(f"{label}...")
        self.worker.submit(label, func, *args)

    def _on_worker_done(self, result):
        self.after(0, self._handle_result, result)

    def _handle_result(self, result):
        label, ok, data = result
        self.busy_var.set("")
        if not ok:
            messagebox.showerror("Error", str(data))
            return
        
        if label == "refresh":
            status, logs = data
            self.tree.delete(*self.tree.get_children())
            for e in status.entries:
                self.tree.insert("", "end", values=(e.path, e.index, e.workdir))
            
            self.log_tree.delete(*self.log_tree.get_children())
            for sha, msg, auth, ts in logs:
                t_str = time.strftime('%Y-%m-%d %H:%M', time.localtime(ts))
                self.log_tree.insert("", "end", values=(sha[:7], msg, auth, t_str))
        
        if label == "diff":
            top = tk.Toplevel(self)
            top.title("Diff")
            txt = tk.Text(top, font=("Consolas", 10))
            txt.pack(fill="both", expand=True)
            txt.insert("1.0", data)

        if label in ["stage", "unstage", "commit", "push", "pull"]:
            self._refresh()

    def _refresh(self):
        if not self.git: return
        self._submit("refresh", lambda: (self.git.status(), self.git.log()))

    def _get_selection(self):
        return [self.tree.item(i)['values'][0] for i in self.tree.selection()]

    def _stage(self):
        paths = self._get_selection()
        if paths: self._submit("stage", self.git.stage, paths)

    def _unstage(self):
        paths = self._get_selection()
        if paths: self._submit("unstage", self.git.unstage, paths)

    def _commit(self):
        msg = self.msg_text.get("1.0", "end").strip()
        if not msg: return
        self._submit("commit", self.git.commit, msg, "GitPilot", "pilot@local")
        self.msg_text.delete("1.0", "end")

    def _push(self):
        self._submit("push", self.git.push)

    def _pull(self):
        self._submit("pull", self.git.pull)

    def _show_diff(self):
        sel = self._get_selection()
        file = sel[0] if sel else None
        self._submit("diff", self.git.diff, file)

# --- Independent Test Block ---
if __name__ == "__main__":
    root = tk.Tk()
    root.title("Git Pilot Test")
    root.geometry("800x600")
    
    # Use current directory
    cwd = Path(os.getcwd())
    
    panel = GitPilotMS({"parent": root, "initial_path": cwd})
    print("Service ready:", panel)
    panel.pack(fill="both", expand=True)
    
    root.mainloop()


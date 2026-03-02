import sys
import os
import argparse
import shutil
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, font
from pathlib import Path

# ==============================================================================
# 1. CORE ENGINE (Business Logic)
# ==============================================================================

def _norm_path(p: str) -> str:
    """
    Normalize paths for robust equality comparisons on Windows/macOS/Linux.
    """
    try:
        return os.path.normcase(os.path.realpath(os.path.abspath(p)))
    except Exception:
        return os.path.normcase(os.path.abspath(p))


def find_git_root(start_path: str) -> str | None:
    """
    Walk upward from start_path to find a directory containing `.git`.
    Returns the repo root path or None.
    """
    try:
        p = Path(start_path).resolve()
    except Exception:
        p = Path(start_path)

    # If a file is passed, start from its parent
    if p.is_file():
        p = p.parent

    for parent in [p] + list(p.parents):
        if (parent / ".git").is_dir():
            return str(parent)
    return None


class GitOpsEngine:
    """
    Encapsulates Git-related operations for a single repository.
    """
    def __init__(self, repo_path=None):
        self.repo_path = repo_path or os.getcwd()

    # --- Environment Checks ---------------------------------------------------

    def is_git_available(self) -> bool:
        """Return True if `git` is available on PATH."""
        return shutil.which("git") is not None

    def is_valid_repo(self) -> bool:
        """Return True if repo_path contains a .git directory."""
        if not self.repo_path or not os.path.isdir(self.repo_path):
            return False
        git_dir = os.path.join(self.repo_path, ".git")
        return os.path.isdir(git_dir)

    def has_gitignore(self) -> bool:
        """Return True if a .gitignore exists in the repo root."""
        gitignore_path = os.path.join(self.repo_path, ".gitignore")
        return os.path.exists(gitignore_path)

    # --- Low-Level Git Runner -------------------------------------------------

    def _run_git(self, args, log_callback=None):
        """
        Run a git command inside repo_path.

        args: list of arguments, e.g. ["git", "status", "--porcelain"]
        log_callback: optional function that accepts a string for UI logging.
        """
        if log_callback is None:
            def log_callback(_: str):
                return

        try:
            result = subprocess.run(
                args,
                cwd=self.repo_path,
                capture_output=True,
                text=True
            )
        except FileNotFoundError:
            log_callback("ERROR: Git executable not found.\n")
            return 1, "", "Git executable not found."

        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if stdout:
            log_callback(stdout + "\n")
        if stderr:
            log_callback(stderr + "\n")

        return result.returncode, stdout, stderr

    # --- Status Helpers -------------------------------------------------------

    def get_status_porcelain(self, log_callback=None) -> str | None:
        """
        Return the porcelain status output (possibly empty if clean),
        or None on error.
        """
        code, out, _ = self._run_git(["git", "status", "--porcelain"], log_callback)
        if code != 0:
            return None
        return out

    # --- Core Operation -------------------------------------------------------

    def commit_and_push(
        self,
        message: str,
        allow_without_gitignore: bool = False,
        log_callback=None
    ) -> bool:
        """
        Execute: git add ., git commit -m message, git push.

        Returns True on success, False on failure.
        """
        if log_callback is None:
            log_callback = lambda s: None

        if not message.strip():
            log_callback("ERROR: Commit message is empty.\n")
            return False

        if not self.is_git_available():
            log_callback("ERROR: Git not found on PATH.\n")
            return False

        if not self.is_valid_repo():
            log_callback("ERROR: Selected folder is not a valid Git repository.\n")
            return False

        if not allow_without_gitignore and not self.has_gitignore():
            log_callback("WARNING: No .gitignore detected; operation blocked by policy.\n")
            return False

        status_out = self.get_status_porcelain(log_callback)
        if status_out is None:
            log_callback("ERROR: Unable to determine git status.\n")
            return False

        if not status_out.strip():
            log_callback("INFO: Nothing to commit (working tree clean).\n")
            return False

        log_callback("Running: git add .\n")
        code, _, _ = self._run_git(["git", "add", "."], log_callback)
        if code != 0:
            log_callback("ERROR: git add failed.\n")
            return False

        log_callback("Running: git commit\n")
        code, commit_out, commit_err = self._run_git(
            ["git", "commit", "-m", message],
            log_callback
        )
        if code != 0:
            combined = (commit_out + "\n" + commit_err).lower()
            if "nothing to commit" in combined:
                log_callback("INFO: Nothing to commit after git add.\n")
            else:
                log_callback("ERROR: git commit failed.\n")
                return False

        log_callback("Running: git push\n")
        code, _, _ = self._run_git(["git", "push"], log_callback)
        if code != 0:
            log_callback("ERROR: git push failed.\n")
            return False

        log_callback("SUCCESS: Commit & push completed.\n")
        return True

    def push_only(self, log_callback=None) -> bool:
        """Execute: git push."""
        if log_callback is None:
            log_callback = lambda s: None

        if not self.is_git_available():
            log_callback("ERROR: Git not found on PATH.\n")
            return False

        if not self.is_valid_repo():
            log_callback("ERROR: Selected folder is not a valid Git repository.\n")
            return False

        log_callback("Running: git push\n")
        code, _, _ = self._run_git(["git", "push"], log_callback)
        if code != 0:
            log_callback("ERROR: git push failed.\n")
            return False

        log_callback("SUCCESS: Push completed.\n")
        return True


# ==============================================================================
# 2. GUI LAYER (The Visual Cortex)
# ==============================================================================

class GitCommitGUI:
    """
    Small dark-themed Tk GUI for commit + push operations.
    """
    def __init__(self, root, engine: GitOpsEngine):
        self.root = root
        self.engine = engine

        self.root.title("Git Commit & Push Helper")
        self.root.geometry("600x260")
        self.root.configure(bg="#050505")
        self.root.resizable(False, False)

        # --- FONTS ---
        self.f_mono = font.Font(family="Consolas", size=10)
        self.f_ui = font.Font(family="Segoe UI", size=9)

        # --- STATE ---
        self.repo_var = tk.StringVar(value=self.engine.repo_path)
        self.msg_var = tk.StringVar(value="")

        # --- Recursion UX state ---
        self._self_repo_root = find_git_root(Path(__file__).resolve().parent)
        self._self_repo_note_shown_for = None  # normalized path or None
        self._autofill_message = "Self-test / recursion check"

        self._build_ui()

        # React to repo path edits (manual typing or folder picker)
        self.repo_var.trace_add("write", self._on_repo_change)

        # Apply initial self-repo behavior on startup (if launching in repo root)
        self._on_repo_change()

    # UI Construction ----------------------------------------------------------

    def _build_ui(self):
        self.status_var = tk.StringVar(value="Ready.")
        status_label = tk.Label(
            self.root,
            textvariable=self.status_var,
            bg="#222222",
            fg="#888888",
            bd=1,
            relief=tk.SUNKEN,
            anchor="w",
            font=self.f_ui
        )
        status_label.pack(side=tk.BOTTOM, fill=tk.X)

        container = tk.Frame(self.root, bg="#050505")
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # REPO ROW
        repo_frame = tk.Frame(container, bg="#050505")
        repo_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(repo_frame, text="Repository:", bg="#050505", fg="#f0f0f0", font=self.f_ui).pack(side=tk.LEFT)

        tk.Entry(
            repo_frame,
            textvariable=self.repo_var,
            bg="#111111",
            fg="#f0f0f0",
            insertbackground="#f0f0f0",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#444444",
            font=self.f_mono
        ).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 4))

        tk.Button(
            repo_frame,
            text="…",
            width=3,
            bg="#333333",
            fg="#f0f0f0",
            activebackground="#555555",
            activeforeground="#ffffff",
            relief="flat",
            command=self._browse_repo
        ).pack(side=tk.LEFT)

        # COMMIT MESSAGE ROW
        msg_frame = tk.Frame(container, bg="#050505")
        msg_frame.pack(fill=tk.X, pady=(0, 8))

        tk.Label(msg_frame, text="Commit message:", bg="#050505", fg="#f0f0f0", font=self.f_ui).pack(side=tk.LEFT)

        entry_msg = tk.Entry(
            msg_frame,
            textvariable=self.msg_var,
            bg="#111111",
            fg="#f0f0f0",
            insertbackground="#f0f0f0",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#444444",
            font=self.f_mono
        )
        entry_msg.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(8, 0))
        entry_msg.bind("<Return>", self._on_commit_push)

        # BUTTON ROW
        btn_frame = tk.Frame(container, bg="#050505")
        btn_frame.pack(fill=tk.X, pady=(0, 8))

        self.btn_commit = tk.Button(
            btn_frame,
            text="Commit & Push",
            bg="#333333",
            fg="#f0f0f0",
            activebackground="#555555",
            activeforeground="#ffffff",
            relief="flat",
            command=self._on_commit_push
        )
        self.btn_commit.pack(side=tk.LEFT)

        tk.Button(
            btn_frame,
            text="Close",
            bg="#333333",
            fg="#f0f0f0",
            activebackground="#555555",
            activeforeground="#ffffff",
            relief="flat",
            command=self.root.destroy
        ).pack(side=tk.RIGHT)

        # LOG AREA
        log_frame = tk.Frame(container, bg="#050505")
        log_frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(log_frame, text="Log:", bg="#050505", fg="#f0f0f0", font=self.f_ui).pack(anchor="w")

        self.txt_log = tk.Text(
            log_frame,
            height=6,
            bg="#101010",
            fg="#f0f0f0",
            insertbackground="#f0f0f0",
            relief="flat",
            highlightthickness=1,
            highlightbackground="#444444",
            wrap="word",
            font=self.f_mono
        )
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        self._log("Git Commit & Push Helper ready.\n")

    # Helpers ------------------------------------------------------------------

    def _browse_repo(self):
        initial = self.repo_var.get() or os.getcwd()
        folder = filedialog.askdirectory(initialdir=initial)
        if folder:
            self.repo_var.set(folder)

    def _log(self, text: str):
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", text)
        if not text.endswith("\n"):
            self.txt_log.insert("end", "\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")

    def _update_status(self, text: str):
        self.status_var.set(text)
        self.root.update_idletasks()

    # Recursion UX -------------------------------------------------------------

    def _is_self_repo_selected(self) -> bool:
        """
        True if the selected repo (or its git root) equals this script's repo root.
        """
        if not self._self_repo_root:
            return False

        selected = self.repo_var.get().strip()
        if not selected:
            return False

        selected_root = find_git_root(selected)
        if not selected_root:
            return False

        return _norm_path(selected_root) == _norm_path(self._self_repo_root)

    def _on_repo_change(self, *_):
        """
        Triggered when repo_var changes. Handles:
        - Logging a note if operating on its own repo (informational only).
        - Autofilling commit message gracefully.
        """
        if self._is_self_repo_selected():
            norm_self = _norm_path(self._self_repo_root)
            if self._self_repo_note_shown_for != norm_self:
                self._log("NOTE: Self-repo detected (operating on this tool's own repository).\n")
                self._self_repo_note_shown_for = norm_self
                self._update_status("Self-repo detected.")

            # Autofill only if helpful (don't override custom messages)
            current_msg = self.msg_var.get().strip()
            if current_msg == "" or current_msg == self._autofill_message:
                self.msg_var.set(self._autofill_message)
        else:
            self._update_status("Ready.")

    # Main action --------------------------------------------------------------

    def _on_commit_push(self, event=None):
        self.txt_log.configure(state="normal")
        self.txt_log.delete("1.0", "end")
        self.txt_log.configure(state="disabled")

        repo = self.repo_var.get().strip()
        msg = self.msg_var.get().strip()
        self.engine.repo_path = repo

        def log_cb(s: str):
            self._log(s)

        if not self.engine.is_git_available():
            messagebox.showerror("Error", "Git is not available on PATH.")
            self._log("ERROR: Git not found on PATH.\n")
            self._update_status("Error: git missing.")
            return

        if not repo or not os.path.isdir(repo):
            messagebox.showerror("Error", "Repository folder does not exist.")
            self._log("ERROR: Invalid repository path.\n")
            self._update_status("Error: invalid repo path.")
            return

        if not self.engine.is_valid_repo():
            messagebox.showerror("Error", "Selected folder is not a Git repository (missing .git).")
            self._log("ERROR: No .git directory found in selected folder.\n")
            self._update_status("Error: not a git repo.")
            return

        if not msg:
            messagebox.showwarning("Missing commit message", "Please enter a commit message.")
            self._log("WARNING: Commit message is empty.\n")
            self._update_status("Awaiting commit message.")
            return

        # .gitignore HITL
        if not self.engine.has_gitignore():
            self._log("WARNING: No .gitignore detected.\n")
            proceed = messagebox.askyesno(
                "No .gitignore found",
                "No .gitignore file detected.\n\n"
                "This will add and commit ALL files, including build artifacts, virtualenvs, etc.\n\n"
                "Continue anyway?"
            )
            if not proceed:
                self._log("User aborted: no .gitignore present.\n")
                self._update_status("Aborted (no .gitignore).")
                return

        self._log(f"Using repo: {repo}\n")
        self._log(f"Commit message: {msg}\n")
        self._log("-" * 40 + "\n")

        self.btn_commit.configure(state="disabled")
        self._update_status("Running git operations...")

        try:
            status_out = self.engine.get_status_porcelain(log_cb)
            if status_out is None:
                messagebox.showerror("Error", "Failed to run 'git status'. See log for details.")
                self._update_status("Error: git status failed.")
                return

            if not status_out.strip():
                self._log("No local changes detected (working tree clean).\n")
                push_anyway = messagebox.askyesno(
                    "No changes to commit",
                    "No changes detected to commit.\n\n"
                    "Do you still want to run 'git push'?"
                )
                if not push_anyway:
                    self._log("User aborted: no changes to commit; push skipped.\n")
                    self._update_status("Aborted (nothing to commit).")
                    return

                success = self.engine.push_only(log_cb)
                if success:
                    messagebox.showinfo("Success", "Push completed successfully (no new commit).")
                    self._update_status("Push complete (no new commit).")
                else:
                    messagebox.showerror("Push failed", "git push failed. See log for details.")
                    self._update_status("Push failed.")
                return

            success = self.engine.commit_and_push(
                message=msg,
                allow_without_gitignore=True,
                log_callback=log_cb
            )

            if success:
                messagebox.showinfo("Success", "Commit & push completed successfully.")
                self._update_status("Commit & push complete.")
            else:
                messagebox.showerror("Error", "Commit and/or push failed. See log for details.")
                self._update_status("Commit/push failed.")
        finally:
            self.btn_commit.configure(state="normal")


# ==============================================================================
# 3. CLI LAYER (Utility)
# ==============================================================================

def run_cli():
    parser = argparse.ArgumentParser(description="Git Commit & Push Helper CLI")
    parser.add_argument("-r", "--repo", default=os.getcwd(), help="Path to the Git repository.")
    parser.add_argument("-m", "--message", required=True, help="Commit message.")
    parser.add_argument("--force-without-gitignore", action="store_true",
                        help="Allow commit/push even if .gitignore is missing.")
    parser.add_argument("--push-only", action="store_true", help="Skip commit and just run git push.")

    args = parser.parse_args()
    engine = GitOpsEngine(repo_path=args.repo)

    def log_cb(s: str):
        sys.stdout.write(s)
        if not s.endswith("\n"):
            sys.stdout.write("\n")
        sys.stdout.flush()

    if not engine.is_git_available():
        print("ERROR: Git is not available on PATH.", file=sys.stderr)
        sys.exit(1)

    if not engine.is_valid_repo():
        print("ERROR: Selected folder is not a Git repository (missing .git).", file=sys.stderr)
        sys.exit(1)

    if args.push_only:
        ok = engine.push_only(log_cb)
        sys.exit(0 if ok else 1)

    if not args.force_without_gitignore and not engine.has_gitignore():
        print("ERROR: No .gitignore found. Use --force-without-gitignore to override.", file=sys.stderr)
        sys.exit(1)

    ok = engine.commit_and_push(
        message=args.message,
        allow_without_gitignore=args.force_without_gitignore,
        log_callback=log_cb
    )
    sys.exit(0 if ok else 1)


# ==============================================================================
# 4. ENTRY POINT
# ==============================================================================

def run_gui():
    engine = GitOpsEngine()
    root = tk.Tk()
    GitCommitGUI(root, engine)
    root.mainloop()

def main():
    if len(sys.argv) > 1:
        run_cli()
    else:
        run_gui()

if __name__ == "__main__":
    main()

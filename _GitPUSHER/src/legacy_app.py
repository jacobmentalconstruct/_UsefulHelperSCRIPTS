import sys
import os
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, font, filedialog

# ==============================================================================
# 1. CORE ENGINE (Now with Branching & Syncing)
# ==============================================================================

class GitOpsEngine:
    def __init__(self, repo_path=None):
        self.repo_path = repo_path or os.getcwd()

    def _run(self, args):
        try:
            res = subprocess.run(["git"] + args, cwd=self.repo_path, capture_output=True, text=True, encoding="utf-8")
            return res.returncode, res.stdout.strip(), res.stderr.strip()
        except FileNotFoundError:
            return 1, "", "Git not found."

    def is_valid_repo(self):
        return os.path.isdir(os.path.join(self.repo_path, ".git"))

    def get_current_branch(self):
        _, out, _ = self._run(["branch", "--show-current"])
        return out or "Unknown"

    def get_all_branches(self):
        code, out, _ = self._run(["branch"])
        if code != 0:
            return []
        return [b.replace("*", "").strip() for b in out.splitlines() if b.strip()]

    def checkout_branch(self, branch_name, create=False):
        if create:
            return self._run(["checkout", "-b", branch_name])
        return self._run(["checkout", branch_name])

    def get_status_short(self):
        _, out, _ = self._run(["status", "--porcelain"])
        return out if out else "Working tree clean."

    def pull(self):
        branch = self.get_current_branch()
        return self._run(["pull", "origin", branch])

    def full_init(self, remote_url, commit_msg):
        steps = [
            (["init"], "Initializing..."),
            (["branch", "-M", "main"], "Setting branch to main..."),
            (["remote", "add", "origin", remote_url], "Adding remote..."),
            (["add", "."], "Staging files..."),
            (["commit", "-m", commit_msg], "First commit..."),
            (["push", "-u", "origin", "main"], "Pushing to origin...")
        ]
        logs = []
        for cmd, desc in steps:
            code, out, err = self._run(cmd)
            logs.append(f"[{desc}] {out if code == 0 else err}")
            if code != 0 and "branch" not in desc: 
                return False, "\n".join(logs)
        return True, "\n".join(logs)

# ==============================================================================
# 2. UI LAYER (Hex-Perfect Style)
# ==============================================================================

class GitPusherUI:
    def __init__(self, root):
        self.root = root
        self.engine = GitOpsEngine()
        
        # Color Palette
        self.C_PRI = "#1E1E2F"   # Primary Background
        self.C_SEC = "#252526"   # Secondary Background
        self.C_DEEP = "#151521"  # Console/Log Background
        self.C_INP = "#2A2A3F"   # Input fields
        self.C_ACC = "#007ACC"   # Active Blue Accent
        self.C_SUC = "#90EE90"   # Success Green
        self.C_ERR = "#C23621"   # Warning Red

        self.root.title("Git Pusher - Systems Thinker Edition")
        self.root.geometry("1000x750")
        self.root.configure(bg=self.C_PRI)

        self.f_mono = font.Font(family="Consolas", size=10)
        self.f_ui = font.Font(family="Segoe UI", size=9)
        self.f_bold = font.Font(family="Segoe UI", size=10, weight="bold")
        
        self._setup_styles()
        self._build_ui()
        self.refresh_state()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook", background=self.C_PRI, borderwidth=0)
        style.configure("TNotebook.Tab", background=self.C_SEC, foreground="#aaa", padding=[15, 5])
        style.map("TNotebook.Tab", background=[("selected", self.C_ACC)], foreground=[("selected", "#fff")])
        style.configure("TFrame", background=self.C_PRI)

    def _build_ui(self):
        # Header (Indigo-Grey)
        header = tk.Frame(self.root, bg=self.C_PRI, pady=10, padx=15)
        header.pack(fill=tk.X)
        
        tk.Label(header, text="PROJECT ROOT:", bg=self.C_PRI, fg="#888", font=self.f_ui).pack(side=tk.LEFT)
        self.path_var = tk.StringVar(value=self.engine.repo_path)
        path_entry = tk.Entry(header, textvariable=self.path_var, bg=self.C_INP, fg="#8dbdff", 
                              relief="flat", font=self.f_mono, insertbackground="white")
        path_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=15)
        
        tk.Button(header, text="Choose...", bg=self.C_SEC, fg="#fff", relief="flat", padx=10,
                  command=self._browse_folder).pack(side=tk.RIGHT)

        # Tabs
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)

        # --- TAB: QUICK PUSH ---
        self.tab_push = ttk.Frame(self.nb)
        self.nb.add(self.tab_push, text=" QUICK COMMIT & PUSH ")
        
        main_push_frame = tk.Frame(self.tab_push, bg=self.C_PRI, padx=20, pady=20)
        main_push_frame.pack(fill=tk.BOTH, expand=True)

        # Top Section: Info & Branch Row
        info_row = tk.Frame(main_push_frame, bg=self.C_PRI)
        info_row.pack(fill=tk.X, pady=(0, 15))
        
        self.branch_label = tk.Label(info_row, text="BRANCH: Unknown", bg=self.C_PRI, fg=self.C_ACC, font=self.f_bold)
        self.branch_label.pack(side=tk.LEFT, padx=(0, 10))
        
        tk.Button(info_row, text="Manage Branches", bg=self.C_SEC, fg="#fff", relief="flat", 
                  command=self._open_branch_manager, font=self.f_ui, padx=8).pack(side=tk.LEFT)
        
        tk.Button(info_row, text="Refresh Status", bg=self.C_SEC, fg="#ccc", relief="flat", 
                  command=self.refresh_state, font=self.f_ui, padx=8).pack(side=tk.RIGHT)

        # Commit Message
        tk.Label(main_push_frame, text="COMMIT MESSAGE:", bg=self.C_PRI, fg="#888", font=self.f_ui).pack(anchor="w")
        self.msg_entry = tk.Entry(main_push_frame, bg=self.C_INP, fg="#fff", font=self.f_mono, relief="flat", insertbackground="white")
        self.msg_entry.pack(fill=tk.X, pady=(5, 10))

        # Action Row (Pull Toggle + Push Button)
        action_row = tk.Frame(main_push_frame, bg=self.C_PRI)
        action_row.pack(fill=tk.X, pady=(0, 15))

        self.pull_var = tk.BooleanVar(value=False)
        tk.Checkbutton(action_row, text="Pull from origin before pushing (Sync)", variable=self.pull_var, 
                       bg=self.C_PRI, fg="#aaa", selectcolor=self.C_INP, activebackground=self.C_PRI, 
                       activeforeground="#fff", font=self.f_ui).pack(side=tk.LEFT)

        tk.Button(action_row, text="Push Changes to Origin", bg=self.C_ACC, fg="#fff", font=self.f_bold,
                  relief="flat", pady=10, padx=20, command=self._on_quick_push).pack(side=tk.RIGHT)

        # Viewpanel (Boxed with Scrollbar)
        tk.Label(main_push_frame, text="STAGED / MODIFIED FILES:", bg=self.C_PRI, fg="#888", font=self.f_ui).pack(anchor="w")
        view_frame = tk.Frame(main_push_frame, bg=self.C_DEEP, bd=1, relief="solid", highlightthickness=0)
        view_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        
        self.view_scroll = tk.Scrollbar(view_frame, bg=self.C_SEC)
        self.view_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        
        self.view_panel = tk.Text(view_frame, bg=self.C_DEEP, fg=self.C_SUC, font=self.f_mono, 
                                  relief="flat", yscrollcommand=self.view_scroll.set, padx=10, pady=10)
        self.view_panel.pack(fill=tk.BOTH, expand=True)
        self.view_scroll.config(command=self.view_panel.yview)

        # --- TAB: INITIALIZE ---
        self.tab_init = ttk.Frame(self.nb)
        self.nb.add(self.tab_init, text=" INITIALIZE REPOSITORY ")
        
        init_container = tk.Frame(self.tab_init, bg=self.C_PRI, padx=20, pady=20)
        init_container.pack(fill=tk.BOTH, expand=True)

        tk.Label(init_container, text="GITHUB REMOTE URL:", bg=self.C_PRI, fg="#888", font=self.f_ui).pack(anchor="w")
        self.url_entry = tk.Entry(init_container, bg=self.C_INP, fg="#fff", font=self.f_mono, relief="flat", insertbackground="white")
        self.url_entry.insert(0, "https://github.com/jacobplambert/")
        self.url_entry.pack(fill=tk.X, pady=(5, 15))

        tk.Label(init_container, text="INITIAL COMMIT MESSAGE:", bg=self.C_PRI, fg="#888", font=self.f_ui).pack(anchor="w")
        self.init_msg_entry = tk.Entry(init_container, bg=self.C_INP, fg="#fff", font=self.f_mono, relief="flat", insertbackground="white")
        self.init_msg_entry.insert(0, "Initial commit")
        self.init_msg_entry.pack(fill=tk.X, pady=(5, 20))

        tk.Button(init_container, text="Initialize and Push to Remote", bg="#28a745", fg="#fff", font=self.f_bold,
                  relief="flat", pady=12, command=self._on_full_init).pack(fill=tk.X)

        # Global Console Area
        tk.Label(self.root, text="SYSTEM LOG:", bg=self.C_PRI, fg="#888", font=self.f_ui, padx=15).pack(anchor="w")
        log_frame = tk.Frame(self.root, bg=self.C_DEEP, padx=5, pady=5)
        log_frame.pack(fill=tk.BOTH, expand=False, padx=15, pady=(0, 10))
        
        self.log_scroll = tk.Scrollbar(log_frame, bg=self.C_SEC)
        self.log_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.log_text = tk.Text(log_frame, bg=self.C_DEEP, fg="#aaa", font=self.f_mono, relief="flat", height=6, yscrollcommand=self.log_scroll.set)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_scroll.config(command=self.log_text.yview)
        
        self.status_bar = tk.Label(self.root, text="Ready.", bg=self.C_DEEP, fg=self.C_SUC, anchor="w", padx=15, font=self.f_ui)
        self.status_bar.pack(fill=tk.X)

    # --- UI Helpers ---

    def _log(self, msg, color="#aaa"):
        self.log_text.insert("end", f"{msg}\n")
        self.log_text.see("end")

    def _browse_folder(self):
        folder = filedialog.askdirectory()
        if folder:
            self.path_var.set(folder)
            self.refresh_state()

    def refresh_state(self):
        self.engine.repo_path = self.path_var.get()
        if not self.engine.is_valid_repo():
            self.status_bar.config(text="WARNING: Not a git repository.", fg=self.C_ERR)
            self.branch_label.config(text="BRANCH: N/A", fg="#555")
            self.view_panel.config(state="normal")
            self.view_panel.delete("1.0", "end")
            self.view_panel.config(state="disabled")
        else:
            self.status_bar.config(text="Git Repository Detected.", fg=self.C_SUC)
            self.branch_label.config(text=f"BRANCH: {self.engine.get_current_branch()}", fg=self.C_ACC)
            self.view_panel.config(state="normal")
            self.view_panel.delete("1.0", "end")
            self.view_panel.insert("end", self.engine.get_status_short())
            self.view_panel.config(state="disabled")

    # --- Dialogs & Workflows ---

    def _open_branch_manager(self):
        if not self.engine.is_valid_repo():
            messagebox.showerror("Error", "Not a valid git repository.")
            return

        dlg = tk.Toplevel(self.root)
        dlg.title("Branch Manager")
        dlg.geometry("400x350")
        dlg.configure(bg=self.C_PRI)
        dlg.transient(self.root)
        dlg.grab_set()

        tk.Label(dlg, text="EXISTING BRANCHES:", bg=self.C_PRI, fg="#888", font=self.f_ui).pack(anchor="w", padx=15, pady=(15, 5))
        
        list_frame = tk.Frame(dlg, bg=self.C_DEEP, bd=1, relief="solid")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=5)
        
        lb = tk.Listbox(list_frame, bg=self.C_DEEP, fg=self.C_ACC, font=self.f_mono, relief="flat", highlightthickness=0)
        lb.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        branches = self.engine.get_all_branches()
        for b in branches:
            lb.insert(tk.END, b)

        def _checkout_selected():
            sel = lb.curselection()
            if not sel: return
            branch = lb.get(sel[0])
            code, out, err = self.engine.checkout_branch(branch)
            if code == 0:
                self._log(f"[BRANCH] Switched to {branch}")
                self.refresh_state()
                dlg.destroy()
            else:
                messagebox.showerror("Checkout Failed", err)

        tk.Button(dlg, text="Checkout Selected", bg=self.C_SEC, fg="#fff", relief="flat", command=_checkout_selected).pack(fill=tk.X, padx=15, pady=5)

        tk.Label(dlg, text="CREATE NEW BRANCH:", bg=self.C_PRI, fg="#888", font=self.f_ui).pack(anchor="w", padx=15, pady=(10, 5))
        new_b_entry = tk.Entry(dlg, bg=self.C_INP, fg="#fff", font=self.f_mono, relief="flat", insertbackground="white")
        new_b_entry.pack(fill=tk.X, padx=15, pady=5)

        def _create_and_checkout():
            new_branch = new_b_entry.get().strip()
            if not new_branch: return
            code, out, err = self.engine.checkout_branch(new_branch, create=True)
            if code == 0:
                self._log(f"[BRANCH] Created and switched to {new_branch}")
                self.refresh_state()
                dlg.destroy()
            else:
                messagebox.showerror("Creation Failed", err)

        tk.Button(dlg, text="Create & Checkout", bg=self.C_ACC, fg="#fff", relief="flat", command=_create_and_checkout).pack(fill=tk.X, padx=15, pady=(5, 15))

    def _on_quick_push(self):
        if not self.engine.is_valid_repo():
            if messagebox.askyesno("Init Required", "This folder is not a git repo. Switch to Initialize tab?"):
                self.nb.select(self.tab_init)
            return

        msg = self.msg_entry.get().strip()
        if not msg:
            messagebox.showwarning("Missing Info", "Please enter a commit message.")
            return

        self.root.config(cursor="watch")
        
        # 1. Handle Pull / Sync if checked
        if self.pull_var.get():
            self._log("[INFO] Pulling from origin...")
            code, out, err = self.engine.pull()
            if code != 0:
                self._log(f"[ERROR] Pull failed: {err}")
                self.root.config(cursor="")
                if not messagebox.askyesno("Pull Failed", "Could not pull from origin. There might be a conflict. Continue pushing anyway?"):
                    return
            else:
                self._log("[SUCCESS] Pulled latest changes.")

        # 2. Add, Commit, Push
        self._log(f"[INFO] Staging and Committing: {msg}")
        self.engine._run(["add", "."])
        code, out, err = self.engine._run(["commit", "-m", msg])
        
        if code == 0 or "nothing to commit" in out.lower():
            self._log("[INFO] Pushing to origin...")
            code, out, err = self.engine._run(["push"])
            if code == 0:
                self._log(f"[SUCCESS] {out or err}")
                self.msg_entry.delete(0, tk.END)
                self.refresh_state()
            else:
                self._log(f"[ERROR] Push Failed: {err}")
        else:
            self._log(f"[ERROR] Commit Failed: {err}")
        
        self.root.config(cursor="")

    def _on_full_init(self):
        url = self.url_entry.get().strip()
        msg = self.init_msg_entry.get().strip()
        
        if not url or not msg:
            messagebox.showwarning("Missing Info", "URL and Message are required for Init.")
            return

        self._log("[SYSTEM] Starting Full Repository Initialization...")
        self.root.config(cursor="watch")
        success, full_log = self.engine.full_init(url, msg)
        self._log(full_log)
        self.root.config(cursor="")
        
        if success:
            messagebox.showinfo("Success", "Repository initialized and pushed!")
            self.refresh_state()
        else:
            messagebox.showerror("Failed", "Initialization failed. Check logs.")

if __name__ == "__main__":
    root = tk.Tk()
    app = GitPusherUI(root)
    root.mainloop()
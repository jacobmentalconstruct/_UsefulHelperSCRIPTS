import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

# ==============================================================================
# CONFIGURATION
# ==============================================================================
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
MICROSERVICE_LIB_PATH = ROOT_DIR / "_MicroserviceLIBRARY"
CONFIG_FILE = ROOT_DIR / "helper_apps.json"

GLOBAL_IGNORE_PATTERNS = [
    ".git", ".gitignore", ".gitattributes", ".vscode", ".idea",
    "__pycache__", "*.pyc", "*.pyo", ".DS_Store", "Thumbs.db",
    ".venv", "venv", "env", "node_modules",
    "_logs", "*.log", "*.tmp", "dist", "build",
    "*.exe", "*.dll", "*.so", "*.bin", "*.iso", "*.zip", "*.tar", "*.gz",
    "package-lock.json", "yarn.lock" 
]

@dataclass
class AppConfig:
    name: str
    folder: Path
    python_cmd: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)

    @property
    def has_src_app(self) -> bool:
        return (self.folder / "src" / "app.py").is_file()

    def resolve_python(self) -> List[str]:
        if self.python_cmd:
            cmd = self.python_cmd
            if os.path.sep in cmd or "/" in cmd:
                return [str((self.folder / cmd).resolve())]
            return [cmd]

        win_candidate = self.folder / ".venv" / "Scripts" / "pythonw.exe"
        win_fallback = self.folder / ".venv" / "Scripts" / "python.exe"
        
        if win_candidate.is_file(): return [str(win_candidate.resolve())]
        if win_fallback.is_file(): return [str(win_fallback.resolve())]
        
        return ["pyw"] if os.name == "nt" else [sys.executable]

# ---------- Discovery & Launch Logic ----------

def discover_apps(base_dir: Path) -> List[AppConfig]:
    apps = []
    if base_dir.is_dir():
        for child in base_dir.iterdir():
            if child.is_dir() and (child / "src" / "app.py").is_file():
                apps.append(AppConfig(name=child.name, folder=child))
    return sorted(apps, key=lambda a: a.name.lower())

def launch_app(app_cfg: AppConfig):
    if not app_cfg.has_src_app:
        messagebox.showerror("Error", f"Missing src/app.py in:\n{app_cfg.folder}")
        return
    cmd = app_cfg.resolve_python() + ["-m", "src.app"]
    env = os.environ.copy()
    env.update(app_cfg.env)
    try:
        subprocess.Popen(cmd, cwd=str(app_cfg.folder), env=env)
    except Exception as e:
        messagebox.showerror("Launch failed", f"Failed to launch {app_cfg.name}:\n{e}")

# ==============================================================================
# UI COMPONENTS
# ==============================================================================

class MicroserviceSelector(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Scaffolding Details")
        self.geometry("600x800")
        self.configure(bg="#1e1e2f")
        self.colors = getattr(parent, 'widget_colors', {"bg": "#151521", "fg": "white", "selectbg": "#007ACC"})
        
        self.confirmed = False
        self.selected_files = []
        self.target_path = None
        self.available_files = {}

        if MICROSERVICE_LIB_PATH.exists():
            for f in MICROSERVICE_LIB_PATH.glob("*MS.py"):
                self.available_files[f.name] = f
                self.available_files[f.stem.lstrip("_")] = f

        self._build_ui()
        self.transient(parent)
        self.grab_set()

    def _build_ui(self):
        # Folder Picker Row
        frame_folder = ttk.LabelFrame(self, text="Step 1: Target Location", padding=10)
        frame_folder.pack(fill="x", padx=10, pady=10)
        self.lbl_path = ttk.Label(frame_folder, text="No folder selected...", foreground="#ff6666", wraplength=450)
        self.lbl_path.pack(side="left", padx=5)
        ttk.Button(frame_folder, text="Browse...", command=self._on_browse).pack(side="right")

        # Microservice Selection
        ttk.Label(self, text="Step 2: Select Microservices:", font=("Segoe UI", 10, "bold")).pack(pady=5)
        
        frame_list = ttk.Frame(self)
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)
        canvas = tk.Canvas(frame_list, bg="#1e1e2f", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_list, orient="vertical", command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg="#1e1e2f")
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.check_vars = {}
        unique_paths = sorted(list(set(self.available_files.values())), key=lambda p: p.name)
        style = ttk.Style()
        style.configure("TCheckbutton", background="#1e1e2f", foreground="white")

        for f in unique_paths:
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(scrollable_frame, text=f.name, variable=var, style="TCheckbutton")
            cb.pack(anchor="w", padx=5, pady=2)
            self.check_vars[f] = var

        # Footer
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=10, padx=10)
        self.btn_create = tk.Button(btn_frame, text="CREATE APP", bg="#444444", fg="gray", 
                                   state="disabled", command=self._on_confirm, borderwidth=0, padx=15)
        self.btn_create.pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right")

    def _on_browse(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Target Location", initialdir=str(ROOT_DIR))
        if path:
            self.target_path = Path(path)
            self.lbl_path.config(text=str(self.target_path), foreground="#00FF00")
            self.btn_create.config(state="normal", bg="#007ACC", fg="white")

    def _on_confirm(self):
        self.selected_files = [f for f, var in self.check_vars.items() if var.get()]
        self.confirmed = True
        self.destroy()

class AppLauncherUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Useful Helper Apps Launcher")
        self.root.geometry("900x600")
        self._setup_styles()
        self._build_widgets()
        self._refresh_all()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        bg_main, bg_dark, accent = "#1e1e2f", "#151521", "#007ACC"
        self.root.configure(bg=bg_main)
        style.configure("TFrame", background=bg_main)
        style.configure("TLabel", background=bg_main, foreground="white")
        style.configure("TLabelframe", background=bg_main, foreground="white")
        style.configure("TLabelframe.Label", background=bg_main, foreground="white")
        style.configure("TButton", background="#2a2a3f", foreground="white", borderwidth=0)
        style.map("TButton", background=[("active", accent)])
        self.widget_colors = {"bg": bg_dark, "fg": "lightgray", "selectbg": accent}

    def _build_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # --- LEFT COLUMN ---
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 1. Available Apps (The "Expander")
        ttk.Label(left_frame, text="Available Apps", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.app_listbox = tk.Listbox(left_frame, bg=self.widget_colors["bg"], 
                                      fg=self.widget_colors["fg"], selectbackground=self.widget_colors["selectbg"], 
                                      borderwidth=0, highlightthickness=1, highlightbackground="#333333")
        # fill=BOTH and expand=True makes this fill the column by default
        self.app_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        self.app_listbox.bind("<<ListboxSelect>>", lambda e: self._on_select(self.app_listbox))

        # 2. Archives Control (Checkbutton)
        self.archive_var = tk.BooleanVar(value=False)
        self.archive_check = ttk.Checkbutton(
            left_frame, text="Show Archives", variable=self.archive_var, command=self._toggle_archives
        )
        self.archive_check.pack(anchor="w", pady=5)

        # 3. Archives Listbox (The "Contractor")
        self.archive_frame = ttk.Frame(left_frame)
        # Note: We do NOT pack archive_frame yet.
        
        self.archive_listbox = tk.Listbox(self.archive_frame, height=8, width=40, bg=self.widget_colors["bg"],
                                          fg=self.widget_colors["fg"], selectbackground=self.widget_colors["selectbg"],
                                          borderwidth=0, highlightthickness=1, highlightbackground="#333333")
        self.archive_listbox.pack(fill=tk.X, expand=False) # Only fills width, height is fixed
        self.archive_listbox.bind("<<ListboxSelect>>", lambda e: self._on_select(self.archive_listbox))

        # RIGHT DETAILS
        right_frame = ttk.Frame(main_frame, padding=(15, 0))
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        self.details_text = tk.Text(right_frame, height=10, wrap="word", state="disabled",
                                    bg=self.widget_colors["bg"], fg=self.widget_colors["fg"], 
                                    borderwidth=0, padx=10, pady=10)
        self.details_text.pack(fill=tk.BOTH, expand=True)

        btn_row = ttk.Frame(right_frame)
        btn_row.pack(fill=tk.X, pady=(15, 0))
        
        ttk.Button(btn_row, text="Launch", command=self._on_launch_clicked).pack(side=tk.LEFT)
        ttk.Button(btn_row, text="Create New...", command=self._on_create_clicked).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_row, text="Refresh", command=self._refresh_all).pack(side=tk.LEFT)

        ttk.Button(btn_row, text="VENV", width=5, command=self._on_open_venv).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btn_row, text="PS", width=3, command=self._on_open_ps).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btn_row, text="CMD", width=4, command=self._on_open_cmd).pack(side=tk.RIGHT, padx=2)
        ttk.Button(btn_row, text="Folder", command=self._on_open_folder).pack(side=tk.RIGHT)

    def _toggle_archives(self):
        if self.archive_var.get():
            # Show Archives: Pack at the bottom, don't let it expand
            self.archive_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.archive_check)
        else:
            # Hide Archives: Remove from layout
            self.archive_frame.pack_forget()

    def _refresh_all(self):
        self.active_apps = discover_apps(ROOT_DIR)
        self.archived_apps = discover_apps(ROOT_DIR / "__ARCHIVES__")
        
        self.app_listbox.delete(0, tk.END)
        for a in self.active_apps: self.app_listbox.insert(tk.END, a.name)
        
        self.archive_listbox.delete(0, tk.END)
        for a in self.archived_apps: self.archive_listbox.insert(tk.END, a.name)

    def _on_select(self, listbox):
        selection = listbox.curselection()
        if not selection: return
        name = listbox.get(selection[0])
        app = next((a for a in self.active_apps + self.archived_apps if a.name == name), None)
        if app:
            self.selected_app = app
            self.details_text.config(state="normal")
            self.details_text.delete("1.0", tk.END)
            self.details_text.insert("1.0", f"Name: {app.name}\nFolder: {app.folder}\nPython: {' '.join(app.resolve_python())}")
            self.details_text.config(state="disabled")

    def _on_create_clicked(self):
        name = simpledialog.askstring("New App", "Enter project name:")
        if not name: return
        safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-')).strip()
        
        selector = MicroserviceSelector(self.root)
        self.root.wait_window(selector)
        if not selector.confirmed or not selector.target_path: return

        target_dir = selector.target_path / safe_name
        self._write_boilerplate(target_dir, selector.selected_files)
        self._refresh_all()
        messagebox.showinfo("Success", f"App {safe_name} created.")

    def _write_boilerplate(self, root_path: Path, services: List[Path]):
        root_path.mkdir(parents=True, exist_ok=True)
        (root_path / "src").mkdir(exist_ok=True)
        ms_dir = root_path / "src" / "microservices"
        ms_dir.mkdir(exist_ok=True)
        for dep in ["microservice_std_lib.py", "base_service.py", "document_utils.py"]:
            src = MICROSERVICE_LIB_PATH / dep
            if src.exists(): shutil.copy2(src, ms_dir / dep)
        for s in services: shutil.copy2(s, ms_dir / s.name)

    def _on_launch_clicked(self):
        if hasattr(self, 'selected_app'): launch_app(self.selected_app)

    def _on_open_venv(self):
        if hasattr(self, 'selected_app'):
            act = self.selected_app.folder / ".venv" / "Scripts" / "activate.bat"
            if act.exists(): subprocess.Popen(["cmd.exe", "/k", str(act)], cwd=str(self.selected_app.folder))
            else: self._on_open_cmd()

    def _on_open_folder(self):
        if hasattr(self, 'selected_app'): os.startfile(self.selected_app.folder)

    def _on_open_cmd(self):
        if hasattr(self, 'selected_app'): subprocess.Popen(["start", "cmd"], shell=True, cwd=self.selected_app.folder)

    def _on_open_ps(self):
        if hasattr(self, 'selected_app'): subprocess.Popen(["start", "powershell"], shell=True, cwd=self.selected_app.folder)

if __name__ == "__main__":
    root = tk.Tk()
    AppLauncherUI(root)
    root.mainloop()
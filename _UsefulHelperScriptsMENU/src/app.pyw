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


# ---------- Data model ----------

@dataclass
class AppConfig:
    name: str
    folder: Path              # absolute
    python_cmd: Optional[str] = None  # interpreter or "py"
    env: Dict[str, str] = field(default_factory=dict)

    @property
    def has_src_app(self) -> bool:
        return (self.folder / "src" / "app.py").is_file()

    def resolve_python(self) -> List[str]:
        """
        Determine the Python command list to run for this app.
        Priority:
        1. Explicit python_cmd (absolute or relative to folder, or just 'py').
        2. .venv inside app folder.
        3. 'py' (on Windows) or sys.executable elsewhere.
        """
        # 1. Explicit config
        if self.python_cmd:
            cmd = self.python_cmd
            # If relative path, resolve to inside app folder
            if os.path.sep in cmd or "/" in cmd:
                python_path = (self.folder / cmd).resolve()
                return [str(python_path)]
            else:
                # e.g., "py" or "python"
                return [cmd]

        # 2. Local venv
        win_candidate = self.folder / ".venv" / "Scripts" / "pythonw.exe"
        win_fallback = self.folder / ".venv" / "Scripts" / "python.exe"
        nix_candidate = self.folder / ".venv" / "bin" / "python"

        if win_candidate.is_file():
            return [str(win_candidate.resolve())]
        if win_fallback.is_file():
            return [str(win_fallback.resolve())]
        if nix_candidate.is_file():
            return [str(nix_candidate.resolve())]

        # 3. Fallback to system
        if os.name == "nt":
            return ["pyw"]
        return [sys.executable]


# ---------- Config discovery ----------

# Go up 3 levels: src -> _UsefulHelperScriptsMENU -> _UsefulHelperSCRIPTS (Root)
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_FILE = ROOT_DIR / "helper_apps.json"


def load_config_file() -> Dict[str, AppConfig]:
    """
    Load helper_apps.json if it exists.
    Returns a mapping of folder (resolved) -> AppConfig
    """
    configs: Dict[str, AppConfig] = {}

    if not CONFIG_FILE.is_file():
        return configs

    try:
        raw = json.load(CONFIG_FILE.open("r", encoding="utf-8"))
    except Exception as e:
        print(f"[WARN] Failed to load {CONFIG_FILE}: {e}")
        return configs

    for entry in raw:
        folder = ROOT_DIR / entry["folder"]
        name = entry.get("name", folder.name)
        python_cmd = entry.get("python")
        env = entry.get("env", {})

        cfg = AppConfig(
            name=name,
            folder=folder,
            python_cmd=python_cmd,
            env=env,
        )
        configs[str(folder.resolve())] = cfg

    return configs


def discover_apps() -> List[AppConfig]:
    """
    Discover app folders that contain src/app.py.
    Merge with config entries when present.
    """
    configs_by_folder = load_config_file()
    apps: Dict[str, AppConfig] = {}

    # 1. From config (even if src/app.py missing, we keep but mark missing)
    for folder_key, cfg in configs_by_folder.items():
        apps[folder_key] = cfg

    # 2. Auto-discover any dir with src/app.py (one level deep by default)
    for child in ROOT_DIR.iterdir():
        if not child.is_dir():
            continue
        candidate = child / "src" / "app.py"
        if candidate.is_file():
            key = str(child.resolve())
            if key not in apps:
                apps[key] = AppConfig(name=child.name, folder=child)

    # Filter out ones that truly have no src/app.py AND weren’t meant to be virtual
    # (We keep them though, but you can choose to hide them instead).
    return list(apps.values())


# ---------- Launcher logic ----------

def launch_app(app_cfg: AppConfig):
    if not app_cfg.has_src_app:
        messagebox.showerror(
            "Missing app.py",
            f"Could not find src/app.py in:\n{app_cfg.folder}",
        )
        return

    python_cmd = app_cfg.resolve_python()

    cmd = python_cmd + ["-m", "src.app"]

    env = os.environ.copy()
    env.update(app_cfg.env)

    try:
        if os.name == "nt":
            # Spawn in a new console on Windows
            subprocess.Popen(
                cmd,
                cwd=str(app_cfg.folder),
                env=env,
                # creationflags=subprocess.CREATE_NEW_CONSOLE,
            )
        else:
            # On Linux/macOS, normal Popen is usually fine
            subprocess.Popen(
                cmd,
                cwd=str(app_cfg.folder),
                env=env,
            )
    except Exception as e:
        messagebox.showerror(
            "Launch failed",
            f"Failed to launch {app_cfg.name}:\n\n{e}",
        )


# ---------- Tkinter UI ----------

class AppLauncherUI:
    def __init__(self, root: tk.Tk, apps: List[AppConfig]):
        self.root = root
        # Fix: Ensure apps are sorted safely even if empty
        self.apps = sorted(apps, key=lambda a: a.name.lower())
        self.app_by_name = {a.name: a for a in self.apps}

        self.root.title("Useful Helper Apps Launcher")
        self.root.geometry("600x400")

        self._build_widgets()

    def _build_widgets(self):
        # FIX: Added proper indentation here
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left: app list
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)

        ttk.Label(left_frame, text="Available Apps").pack(anchor="w")

        self.app_listbox = tk.Listbox(left_frame, height=20)
        self.app_listbox.pack(fill=tk.BOTH, expand=True)
        self.app_listbox.bind("<Double-1>", self._on_double_click)

        for app in self.apps:
            suffix = "" if app.has_src_app else " (missing src/app.py)"
            self.app_listbox.insert(tk.END, f"{app.name}{suffix}")

        # Right: details + launch
        right_frame = ttk.Frame(main_frame, padding=(10, 0))
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.details_text = tk.Text(
            right_frame, height=10, wrap="word", state="disabled"
        )
        self.details_text.pack(fill=tk.BOTH, expand=True)

        btn_frame = ttk.Frame(right_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))

        self.launch_button = ttk.Button(
            btn_frame, text="Launch Selected App", command=self._on_launch_clicked
        )
        self.launch_button.pack(side=tk.LEFT)

        self.create_button = ttk.Button(
            btn_frame, text="Create New", command=self._on_create_clicked
        )
        self.create_button.pack(side=tk.LEFT, padx=(5, 0))

        self.refresh_button = ttk.Button(
            btn_frame, text="Refresh Apps", command=self._on_refresh_clicked
        )
        self.refresh_button.pack(side=tk.LEFT, padx=(5, 0))

        # --- New Tools (Right Aligned) ---
        self.btn_ps = ttk.Button(
            btn_frame, text="PS", width=3, command=self._on_open_powershell
        )
        self.btn_ps.pack(side=tk.RIGHT, padx=(5, 0))

        self.btn_cmd = ttk.Button(
            btn_frame, text="CMD", width=4, command=self._on_open_cmd
        )
        self.btn_cmd.pack(side=tk.RIGHT, padx=(5, 0))

        self.btn_explore = ttk.Button(
            btn_frame, text="Folder", command=self._on_open_folder
        )
        self.btn_explore.pack(side=tk.RIGHT, padx=(5, 0))

        self.app_listbox.bind("<<ListboxSelect>>", self._on_select)

    def _on_create_clicked(self):
        name = simpledialog.askstring("New App", "Enter name for new app (Folder Name):")
        if not name:
            return
        
        # Basic sanitization
        safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-')).strip()
        if not safe_name:
            messagebox.showerror("Error", "Invalid name.")
            return

        target_dir = ROOT_DIR / safe_name
        if target_dir.exists():
            messagebox.showerror("Error", f"Folder '{safe_name}' already exists.")
            return

        try:
            self._write_boilerplate(target_dir)
            self._on_refresh_clicked()
            messagebox.showinfo("Success", f"Created {safe_name}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create app: {e}")

    def _write_boilerplate(self, root_path: Path):
        # Define the master template path
        template_source = ROOT_DIR / "_BoilerPlatePythonTEMPLATE"

        if template_source.is_dir():
            # OPTION A: Copy from your existing template folder
            # shutil.copytree requires the destination to NOT exist, but we created 
            # root_path logic earlier. So we copy contents manually or use dirs_exist_ok.
            try:
                shutil.copytree(template_source, root_path, dirs_exist_ok=True)
                print(f"[Info] Cloned template from {template_source}")
                return
            except Exception as e:
                messagebox.showerror("Template Error", f"Failed to copy template:\n{e}")
                return
        
        # OPTION B: Fallback (If template folder is missing)
        # This ensures the launcher still works even if you move the template folder.
        messagebox.showwarning("Template Missing", 
            f"Could not find '{template_source.name}'.\nUsing minimal fallback.")
        
        root_path.mkdir(parents=True, exist_ok=True)
        (root_path / "src").mkdir(exist_ok=True)
        (root_path / "requirements.txt").touch()
        (root_path / "src" / "__init__.py").touch()
        
        # Minimal app.py so it runs
        with (root_path / "src" / "app.py").open("w", encoding="utf-8") as f:
            f.write("def main():\n    print('Template folder missing! This is a fallback.')\n\nif __name__ == '__main__':\n    main()")

    def _on_refresh_clicked(self):
        """Re-discover apps and refresh the listbox/details without restarting the launcher."""
        # FIX: Added proper indentation here
        self.apps = sorted(discover_apps(), key=lambda a: a.name.lower())
        self.app_by_name = {a.name: a for a in self.apps}

        # Repopulate listbox
        self.app_listbox.delete(0, tk.END)
        for app in self.apps:
            suffix = "" if app.has_src_app else " (missing src/app.py)"
            self.app_listbox.insert(tk.END, f"{app.name}{suffix}")

        # Reset details panel
        self.details_text.config(state="normal")
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert(
            "1.0",
            "Refreshed app list.\n\nSelect an app to see details.",
        )
        self.details_text.config(state="disabled")

    def _on_open_folder(self):
        app = self._get_selected_app()
        if app and app.folder.is_dir():
            if os.name == "nt":
                os.startfile(app.folder)
            else:
                # Linux/Mac fallback
                subprocess.Popen(["xdg-open", str(app.folder)])

    def _on_open_cmd(self):
        app = self._get_selected_app()
        if app and app.folder.is_dir():
            if os.name == "nt":
                subprocess.Popen(["start", "cmd"], shell=True, cwd=app.folder)

    def _on_open_powershell(self):
        app = self._get_selected_app()
        if app and app.folder.is_dir():
            if os.name == "nt":
                subprocess.Popen(["start", "powershell"], shell=True, cwd=app.folder)

    def _get_selected_app(self) -> Optional[AppConfig]:
        selection = self.app_listbox.curselection()
        if not selection:
            return None
        idx = selection[0]
        name_with_suffix = self.app_listbox.get(idx)
        name = name_with_suffix.split(" (missing")[0]
        return self.app_by_name.get(name)

    def _on_select(self, event=None):
        app = self._get_selected_app()
        if not app:
            return
        self._update_details(app)

    def _update_details(self, app: AppConfig):
        folder_display = str(app.folder)
        python_cmd = " ".join(app.resolve_python())
        has_app = "Yes" if app.has_src_app else "No"

        env_lines = "\n".join(
            [f"  {k}={v}" for k, v in app.env.items()]
        ) or "  (none)"

        text = (
            f"Name: {app.name}\n"
            f"Folder: {folder_display}\n"
            f"Has src/app.py: {has_app}\n"
            f"Python command: {python_cmd}\n"
            f"Extra env vars:\n{env_lines}\n"
        )

        self.details_text.config(state="normal")
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert("1.0", text)
        self.details_text.config(state="disabled")

    def _on_launch_clicked(self):
        app = self._get_selected_app()
        if not app:
            messagebox.showinfo("No selection", "Please select an app to launch.")
            return
        launch_app(app)

    def _on_double_click(self, event=None):
        self._on_launch_clicked()


def main():
    apps = discover_apps()
    
    # FIX: Initialize root immediately
    root = tk.Tk()
    
    # FIX: If no apps, just show a message or launch empty. 
    # Do NOT return silently.
    if not apps:
        # Option A: Show error then open empty UI
        messagebox.showinfo(
            "No Apps Found", 
            "No apps were found in subfolders.\n\nThe launcher will open empty. "
            "Add folders with 'src/app.py' and click Refresh."
        )
        # Or Option B: Just pass empty list to UI (which is what we do below)

    AppLauncherUI(root, apps)
    root.mainloop()


if __name__ == "__main__":
    main()






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
# Path to your Microservice Library
MICROSERVICE_LIB_PATH = Path(r"C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_MicroserviceLIBRARY")

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
            if os.path.sep in cmd or "/" in cmd:
                python_path = (self.folder / cmd).resolve()
                return [str(python_path)]
            else:
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
    configs_by_folder = load_config_file()
    apps: Dict[str, AppConfig] = {}

    # 1. From config
    for folder_key, cfg in configs_by_folder.items():
        apps[folder_key] = cfg

    # 2. Auto-discover
    for child in ROOT_DIR.iterdir():
        if not child.is_dir():
            continue
        candidate = child / "src" / "app.py"
        if candidate.is_file():
            key = str(child.resolve())
            if key not in apps:
                apps[key] = AppConfig(name=child.name, folder=child)

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
            subprocess.Popen(
                cmd,
                cwd=str(app_cfg.folder),
                env=env,
            )
        else:
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

# ==============================================================================
# NEW: MICROSERVICE SELECTOR MODAL
# ==============================================================================
class MicroserviceSelector(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Select Microservices to Inject")
        self.geometry("600x600")
        self.confirmed = False
        self.selected_files = [] # List of Path objects
        
        self._build_ui()
        self.transient(parent)
        self.grab_set()
        
    def _build_ui(self):
        # 1. Header
        lbl = ttk.Label(self, text="Select capabilities to add to your new app:", font=("Segoe UI", 10, "bold"))
        lbl.pack(pady=10)
        
        # 2. Scrollable Checkbox List
        frame_list = ttk.Frame(self)
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)
        
        canvas = tk.Canvas(frame_list, bg="#f0f0f0")
        scrollbar = ttk.Scrollbar(frame_list, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        # 3. Populate
        self.check_vars = {} # name -> BooleanVar
        
        if MICROSERVICE_LIB_PATH.exists():
            files = sorted([f for f in MICROSERVICE_LIB_PATH.glob("*MS.py")])
            for f in files:
                var = tk.BooleanVar()
                cb = ttk.Checkbutton(scrollable_frame, text=f.name, variable=var)
                cb.pack(anchor="w", padx=5, pady=2)
                self.check_vars[f] = var
        else:
            ttk.Label(scrollable_frame, text=f"Library not found at:\n{MICROSERVICE_LIB_PATH}").pack()

        # 4. Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=10, padx=10)
        
        ttk.Button(btn_frame, text="Create App", command=self._on_confirm).pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right")
        
    def _on_confirm(self):
        self.selected_files = [f for f, var in self.check_vars.items() if var.get()]
        self.confirmed = True
        self.destroy()

# ---------- Tkinter UI ----------

class AppLauncherUI:
    def __init__(self, root: tk.Tk, apps: List[AppConfig]):
        self.root = root
        self.apps = sorted(apps, key=lambda a: a.name.lower())
        self.app_by_name = {a.name: a for a in self.apps}

        self.root.title("Useful Helper Apps Launcher")
        self.root.geometry("800x500") # Slightly wider

        self._build_widgets()

    def _build_widgets(self):
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Left: app list
        left_frame = ttk.Frame(main_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False)

        ttk.Label(left_frame, text="Available Apps").pack(anchor="w")

        self.app_listbox = tk.Listbox(left_frame, height=20, width=40)
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
            btn_frame, text="Launch", command=self._on_launch_clicked
        )
        self.launch_button.pack(side=tk.LEFT)

        self.create_button = ttk.Button(
            btn_frame, text="Create New App...", command=self._on_create_clicked
        )
        self.create_button.pack(side=tk.LEFT, padx=(5, 0))

        self.refresh_button = ttk.Button(
            btn_frame, text="Refresh", command=self._on_refresh_clicked
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
        # 1. Ask for Name
        name = simpledialog.askstring("New App", "Enter name for new app (Folder Name):")
        if not name: return
        
        safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-')).strip()
        if not safe_name:
            messagebox.showerror("Error", "Invalid name.")
            return

        target_dir = ROOT_DIR / safe_name
        if target_dir.exists():
            messagebox.showerror("Error", f"Folder '{safe_name}' already exists.")
            return

        # 2. Ask for Microservices
        selector = MicroserviceSelector(self.root)
        self.root.wait_window(selector)
        
        if not selector.confirmed:
            return # User cancelled

        # 3. Create
        try:
            self._write_boilerplate(target_dir, selector.selected_files)
            self._on_refresh_clicked()
            messagebox.showinfo("Success", f"Created {safe_name} with {len(selector.selected_files)} services.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to create app: {e}")

    def _write_boilerplate(self, root_path: Path, services: List[Path] = None):
        # A. Copy Template if exists
        launcher_folder = Path(__file__).resolve().parent.parent
        template_source = launcher_folder / "_BoilerPlatePythonTEMPLATE"

        if template_source.is_dir():
            try:
                shutil.copytree(template_source, root_path, dirs_exist_ok=True)
                print(f"[Info] Cloned template from {template_source}")
            except Exception as e:
                messagebox.showerror("Template Error", f"Failed to copy template:\n{e}")
                return
        else:
            # Fallback structure
            root_path.mkdir(parents=True, exist_ok=True)
            (root_path / "src").mkdir(exist_ok=True)
            (root_path / "requirements.txt").touch()
            (root_path / "src" / "__init__.py").touch()
            
            # Basic app.py fallback
            with (root_path / "src" / "app.py").open("w", encoding="utf-8") as f:
                f.write("def main():\n    print('Hello World')\n\nif __name__ == '__main__':\n    main()")

        # B. Inject Microservices
        if services:
            ms_dir = root_path / "src" / "microservices"
            ms_dir.mkdir(exist_ok=True)
            
            # 1. Copy microservice_std_lib.py (Required dependency)
            std_lib = MICROSERVICE_LIB_PATH / "microservice_std_lib.py"
            if std_lib.exists():
                shutil.copy2(std_lib, ms_dir / "microservice_std_lib.py")
            
            # 2. Copy Selected Files
            for svc_path in services:
                shutil.copy2(svc_path, ms_dir / svc_path.name)
            
            # 3. Generate a 'Smart' app.py that imports them
            self._overwrite_app_py_with_imports(root_path, services)

    def _overwrite_app_py_with_imports(self, root_path: Path, services: List[Path]):
        """Overwrites src/app.py with a version that imports the selected services."""
        app_py = root_path / "src" / "app.py"
        
        imports = []
        inits = []
        
        for svc in services:
            # Filename: _AuthMS.py -> Class: AuthMS (Assuming convention)
            module_name = svc.stem # _AuthMS
            class_name = svc.stem.replace("_", "") # AuthMS
            
            # Correction: Your files define classes like 'AuthMS' inside '_AuthMS.py'
            # But wait, some might be '_TkinterAppShellMS' -> 'TkinterAppShellMS'
            # Let's assume class name matches filename without underscore for now, 
            # or just import the module to be safe.
            
            # Logic: from src.microservices._AuthMS import AuthMS
            # Note: We need to handle the underscore correctly. 
            # If file is _AuthMS.py, class is usually AuthMS.
            clean_class_name = module_name[1:] if module_name.startswith("_") else module_name
            
            imports.append(f"from src.microservices.{module_name} import {clean_class_name}")
            inits.append(f"    # {clean_class_name} initialized")
            inits.append(f"    {clean_class_name.lower()} = {clean_class_name}()")
            inits.append(f"    print('Service Loaded:', {clean_class_name.lower()})")

        content = [
            "import sys",
            "import os",
            "# Add src to path so imports work cleanly",
            "sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))",
            "",
            "# --- Microservice Imports ---"
        ]
        content.extend(imports)
        content.append("")
        content.append("def main():")
        content.append("    print('--- Booting Microservice App ---')")
        content.extend(inits)
        content.append("    print('--- System Ready ---')")
        content.append("")
        content.append("if __name__ == '__main__':")
        content.append("    main()")
        
        with open(app_py, "w", encoding="utf-8") as f:
            f.write("\n".join(content))

    def _on_refresh_clicked(self):
        self.apps = sorted(discover_apps(), key=lambda a: a.name.lower())
        self.app_by_name = {a.name: a for a in self.apps}
        self.app_listbox.delete(0, tk.END)
        for app in self.apps:
            suffix = "" if app.has_src_app else " (missing src/app.py)"
            self.app_listbox.insert(tk.END, f"{app.name}{suffix}")
        
        self.details_text.config(state="normal")
        self.details_text.delete("1.0", tk.END)
        self.details_text.insert("1.0", "Refreshed app list.")
        self.details_text.config(state="disabled")

    def _on_open_folder(self):
        app = self._get_selected_app()
        if app and app.folder.is_dir():
            if os.name == "nt":
                os.startfile(app.folder)
            else:
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
        if not app: return
        self._update_details(app)

    def _update_details(self, app: AppConfig):
        folder_display = str(app.folder)
        python_cmd = " ".join(app.resolve_python())
        has_app = "Yes" if app.has_src_app else "No"
        env_lines = "\n".join([f"  {k}={v}" for k, v in app.env.items()]) or "  (none)"

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
    root = tk.Tk()
    if not apps:
        messagebox.showinfo("No Apps Found", "No apps found. Create one!")
    AppLauncherUI(root, apps)
    root.mainloop()


if __name__ == "__main__":
    main()
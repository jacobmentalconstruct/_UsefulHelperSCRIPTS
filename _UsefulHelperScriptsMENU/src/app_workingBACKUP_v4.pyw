import json
import os
import shutil
import subprocess
import sys
import datetime
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
        
        self.confirmed = False
        self.selected_files = []
        self.target_path = None
        self.safe_name = ""
        self.available_files = {}

        if MICROSERVICE_LIB_PATH.exists():
            for f in MICROSERVICE_LIB_PATH.glob("*MS.py"):
                self.available_files[f.name] = f
                self.available_files[f.stem.lstrip("_")] = f

        self._build_ui()
        self.transient(parent)
        self.grab_set()

    def _build_ui(self):
        frame_name = ttk.LabelFrame(self, text="Step 1: Project Name", padding=10)
        frame_name.pack(fill="x", padx=10, pady=5)
        self.ent_name = ttk.Entry(frame_name)
        self.ent_name.pack(fill="x")

        frame_folder = ttk.LabelFrame(self, text="Step 2: Target Location", padding=10)
        frame_folder.pack(fill="x", padx=10, pady=5)
        self.lbl_path = ttk.Label(frame_folder, text="No folder selected...", foreground="#ff6666", wraplength=450)
        self.lbl_path.pack(side="left", padx=5)
        ttk.Button(frame_folder, text="Browse...", command=self._on_browse).pack(side="right")

        ttk.Label(self, text="Step 3: Select Microservices:", font=("Segoe UI", 10, "bold")).pack(pady=5)
        
        frame_list = ttk.Frame(self)
        frame_list.pack(fill="both", expand=True, padx=10, pady=5)
        self.canvas = tk.Canvas(frame_list, bg="#1e1e2f", highlightthickness=0)
        scrollbar = ttk.Scrollbar(frame_list, orient="vertical", command=self.canvas.yview)
        scrollable_frame = tk.Frame(self.canvas, bg="#1e1e2f")
        scrollable_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.canvas.bind_all("<MouseWheel>", self._on_canvas_scroll)

        self.check_vars = {}
        unique_paths = sorted(list(set(self.available_files.values())), key=lambda p: p.name)
        
        for f in unique_paths:
            var = tk.BooleanVar()
            cb = ttk.Checkbutton(scrollable_frame, text=f.name, variable=var, style="TCheckbutton")
            cb.pack(anchor="w", padx=5, pady=2)
            self.check_vars[f] = var

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=10, padx=10)
        self.btn_create = tk.Button(btn_frame, text="CREATE APP", bg="#444444", fg="gray", 
                                   state="disabled", command=self._on_confirm, borderwidth=0, padx=15)
        self.btn_create.pack(side="right", padx=5)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="right")

    def _on_canvas_scroll(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _on_browse(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Select Target Location", initialdir=str(ROOT_DIR))
        if path:
            self.target_path = Path(path)
            self.lbl_path.config(text=str(self.target_path), foreground="#00FF00")
            self.btn_create.config(state="normal", bg="#007ACC", fg="white")

    def _on_confirm(self):
        name = self.ent_name.get().strip()
        if not name:
            messagebox.showerror("Error", "Project name is required.")
            return
        self.safe_name = "".join(c for c in name if c.isalnum() or c in ('_', '-')).strip()
        if not self.target_path:
            messagebox.showerror("Error", "Target location is required.")
            return
        self.selected_files = [f for f, var in self.check_vars.items() if var.get()]
        self.confirmed = True
        self.unbind_all("<MouseWheel>")
        self.destroy()

class AppLauncherUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Useful Helper Apps Launcher")
        self.root.geometry("1100x700")
        self.root.minsize(900, 600)
        self.root.resizable(True, True)
        self.last_selected_name = None
        self.colors = {
            "bg_main": "#1e1e2f",    
            "bg_dark": "#151521",    
            "bg_status": "#252538",  
            "accent": "#007ACC",     
            "border": "#33334d",     
            "fg": "#d1d1e0"          
        }
        self.root.configure(bg=self.colors["bg_main"])
        self._setup_styles()
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._refresh_listbox_only())
        
        self._build_widgets()
        self._refresh_all()
        self._build_context_menu()

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        
        style.configure("TFrame", background=self.colors["bg_main"])
        style.configure("TLabel", background=self.colors["bg_main"], foreground=self.colors["fg"])
        style.configure("Status.TLabel", background=self.colors["bg_status"], foreground=self.colors["fg"], padding=5)
        
        style.configure("TCheckbutton", background=self.colors["bg_main"], foreground=self.colors["fg"])
        style.map("TCheckbutton", background=[('active', self.colors["bg_main"])], foreground=[('active', 'white')])

        style.configure("TButton", background="#2a2a3f", foreground="white", borderwidth=0)
        style.map("TButton", background=[("active", self.colors["accent"])])
        
        self.widget_colors = {"bg": self.colors["bg_dark"], "fg": self.colors["fg"], "selectbg": self.colors["accent"]}

    def _build_widgets(self):
        # 1. STATUS BAR
        self.status_bar = ttk.Label(self.root, text=" Ready", style="Status.TLabel", anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        # 2. MAIN CONTENT WRAPPER
        content_wrapper = tk.Frame(self.root, bg=self.colors["bg_main"], highlightthickness=0)
        content_wrapper.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 3. PANED WINDOW - Surgical Fix: tk.PanedWindow does not support 'highlightthickness'
        self.paned = tk.PanedWindow(
            content_wrapper, 
            orient=tk.HORIZONTAL, 
            bg=self.colors["bg_main"],
            borderwidth=0, 
            sashwidth=4,
            sashpad=0
        )
        self.paned.pack(fill=tk.BOTH, expand=True)

        # LEFT PANEL
        left_panel = tk.Frame(self.paned, bg=self.colors["bg_main"], highlightthickness=0)
        self.paned.add(left_panel, width=300)

        left_inner = ttk.Frame(left_panel)
        left_inner.pack(fill=tk.BOTH, expand=True, padx=(5, 15), pady=5)

        search_container = ttk.Frame(left_inner)
        search_container.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(search_container, text="Search Apps", font=("Segoe UI", 8)).pack(anchor="w")
        ttk.Entry(search_container, textvariable=self.search_var).pack(fill=tk.X)

        ttk.Label(left_inner, text="Available Apps", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.app_listbox = tk.Listbox(
            left_inner, 
            bg=self.widget_colors["bg"], 
            fg=self.widget_colors["fg"], 
            selectbackground=self.widget_colors["selectbg"], 
            borderwidth=0, 
            highlightthickness=1, 
            highlightbackground=self.colors["border"]
        )
        self.app_listbox.pack(fill=tk.BOTH, expand=True, pady=(0, 5))
        self.app_listbox.bind("<<ListboxSelect>>", lambda e: self._on_select(self.app_listbox))
        self.app_listbox.bind("<Button-3>", self._show_context_menu)
        self.app_listbox.bind("<Double-1>", self._on_double_click)

        self.archive_var = tk.BooleanVar(value=False)
        self.archive_check = ttk.Checkbutton(
            left_inner, text="Show Archives", variable=self.archive_var, command=self._toggle_archives
        )
        self.archive_check.pack(anchor="w", pady=5)

        self.archive_frame = ttk.Frame(left_inner)
        self.archive_listbox = tk.Listbox(
            self.archive_frame, 
            height=8, 
            bg=self.widget_colors["bg"],
            fg=self.widget_colors["fg"], 
            selectbackground=self.widget_colors["selectbg"],
            borderwidth=0, 
            highlightthickness=1, 
            highlightbackground=self.colors["border"]
        )
        self.archive_listbox.pack(fill=tk.X, expand=False)
        self.archive_listbox.bind("<<ListboxSelect>>", lambda e: self._on_select(self.archive_listbox))
        self.archive_listbox.bind("<Button-3>", self._show_context_menu)
        self.archive_listbox.bind("<Double-1>", self._on_double_click)

        # RIGHT PANEL
        right_panel = tk.Frame(self.paned, bg=self.colors["bg_main"], highlightthickness=0)
        self.paned.add(right_panel)

        right_inner = ttk.Frame(right_panel)
        right_inner.pack(fill=tk.BOTH, expand=True, padx=(15, 5), pady=5)
        
        self.details_text = tk.Text(
            right_inner, 
            height=10, 
            wrap="word", 
            state="disabled",
            bg=self.widget_colors["bg"], 
            fg=self.widget_colors["fg"], 
            borderwidth=0, 
            padx=10, 
            pady=10, 
            highlightthickness=1, 
            highlightbackground=self.colors["border"]
        )
        self.details_text.pack(fill=tk.BOTH, expand=True)

        btn_row = ttk.Frame(right_inner)
        btn_row.pack(fill=tk.X, pady=(15, 0))

        left_btn_grp = ttk.Frame(btn_row)
        left_btn_grp.pack(side=tk.LEFT)
        ttk.Button(left_btn_grp, text="Launch", command=self._on_launch_clicked).pack(side=tk.LEFT)
        ttk.Button(left_btn_grp, text="Create New...", command=self._on_create_clicked).pack(side=tk.LEFT, padx=5)
        ttk.Button(left_btn_grp, text="Refresh", command=self._refresh_all).pack(side=tk.LEFT)

        right_btn_grp = ttk.Frame(btn_row)
        right_btn_grp.pack(side=tk.RIGHT)
        ttk.Button(right_btn_grp, text="VENV", width=6, command=self._on_open_venv).pack(side=tk.RIGHT, padx=2)
        ttk.Button(right_btn_grp, text="PS", width=4, command=self._on_open_ps).pack(side=tk.RIGHT, padx=2)
        ttk.Button(right_btn_grp, text="CMD", width=5, command=self._on_open_cmd).pack(side=tk.RIGHT, padx=2)
        ttk.Button(right_btn_grp, text="Folder", command=self._on_open_folder).pack(side=tk.RIGHT)

    def _on_double_click(self, event=None):
        self._on_launch_clicked()

    def _toggle_archives(self):
        if self.archive_var.get():
            self.archive_frame.pack(side=tk.BOTTOM, fill=tk.X, before=self.archive_check)
        else:
            self.archive_frame.pack_forget()

    def _set_status(self, text):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        self.status_bar.config(text=f" [{ts}] {text}")

    def _refresh_all(self):
        self.active_apps = discover_apps(ROOT_DIR)
        self.archived_apps = discover_apps(ROOT_DIR / "__ARCHIVES__")
        self._refresh_listbox_only()

    def _refresh_listbox_only(self):
        query = self.search_var.get().lower()
        targets = [
            (self.app_listbox, self.active_apps, '🐍 '), 
            (self.archive_listbox, self.archived_apps, '📦 ')
        ]
        
        for lb, app_list, default_icon in targets:
            lb.delete(0, tk.END)
            for a in app_list:
                if query in a.name.lower():
                    if default_icon == '📦 ':
                        icon = '📦 '
                    else:
                        icon = '🐍 ' if a.has_src_app else '⭕ '
                    lb.insert(tk.END, f"{icon}{a.name}")
            
            if self.last_selected_name:
                all_items = lb.get(0, tk.END)
                for idx, display_val in enumerate(all_items):
                    if display_val[2:] == self.last_selected_name:
                        lb.selection_set(idx)
                        lb.activate(idx)
                        lb.see(idx) 
                        break

        self._set_status(f"Refreshed list ({len(self.active_apps)} active, {len(self.archived_apps)} archived)")

    def _on_select(self, listbox):
        sel = listbox.curselection()
        if not sel: return
        
        raw_val = listbox.get(sel[0])
        self.last_selected_name = raw_val[2:]
        
        app = next((a for a in self.active_apps + self.archived_apps if a.name == self.last_selected_name), None)
        if app:
            self.selected_app = app
            self.details_text.config(state="normal")
            self.details_text.delete("1.0", tk.END)
            self.details_text.insert("1.0", f"Name: {app.name}\nFolder: {app.folder}\nPython: {' '.join(app.resolve_python())}")
            self.details_text.config(state="disabled")

    def _build_context_menu(self):
        self.context_menu = tk.Menu(self.root, tearoff=0, bg=self.widget_colors["bg"], fg="white")
        self.context_menu.add_command(label="🚀 Launch", command=self._on_launch_clicked)
        self.context_menu.add_separator()
        self.context_menu.add_command(label="📂 Open Folder", command=self._on_open_folder)
        self.context_menu.add_command(label="💻 CMD Terminal", command=self._on_open_cmd)
        self.context_menu.add_command(label="🐚 PowerShell", command=self._on_open_ps)
        self.context_menu.add_command(label="🐍 VENV Terminal", command=self._on_open_venv)

    def _show_context_menu(self, event):
        widget = event.widget
        index = widget.nearest(event.y)
        widget.selection_clear(0, tk.END)
        widget.selection_set(index)
        self._on_select(widget)
        self.context_menu.post(event.x_root, event.y_root)

    def _on_create_clicked(self):
        selector = MicroserviceSelector(self.root)
        self.root.wait_window(selector)
        if selector.confirmed:
            target = selector.target_path / selector.safe_name
            try:
                target.mkdir(parents=True, exist_ok=True)
                self._write_boilerplate(target, selector.selected_files)
                self._refresh_all()
                self._set_status(f"Created: {selector.safe_name}")
                messagebox.showinfo("Success", f"App {selector.safe_name} created.")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to create app: {e}")

    def _write_boilerplate(self, root_path, services):
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
            subprocess.Popen(["cmd.exe", "/k", str(act)] if act.exists() else ["start", "cmd"], cwd=str(self.selected_app.folder))

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
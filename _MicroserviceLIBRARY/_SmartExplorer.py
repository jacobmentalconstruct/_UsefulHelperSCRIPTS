# ==============================================================================
# MICROSERVICE METADATA
# ==============================================================================
__MICROSERVICE_METADATA__ = {
    "name": "Smart Explorer",
    "display_name": "Smart Explorer",
    "icon": "📂", 
    "description": "Dev-aware file browser with venv detection and terminal integration.",
    "version": "1.0.0",
    "inputs": ["root", "msg_queue"],
    "outputs": ["file_open", "terminal_launch"],
    "tags": ["explorer", "system", "satellite"]
}

import os
import sys
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from pathlib import Path
from datetime import datetime
import shutil

# ==============================================================================
# HELPER: SYSTEM ICONS & ACTIONS
# ==============================================================================
class ExplorerEngine:
    def __init__(self):
        self.history = []
        self.history_idx = -1
        
    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024: return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    def format_time(self, ts):
        return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")

    def find_venv(self, start_path):
        """Walks up the tree looking for a .venv folder."""
        curr = Path(start_path)
        if curr.is_file(): curr = curr.parent
        
        for _ in range(5): # Check 5 levels up
            venv = curr / ".venv"
            if venv.exists(): return venv
            if curr.parent == curr: break
            curr = curr.parent
        return None

    def open_terminal(self, path):
        """Opens system terminal at path."""
        if os.name == 'nt':
            subprocess.Popen(f'start cmd /k "cd /d {path}"', shell=True)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-a', 'Terminal', path])
        else:
            subprocess.Popen(['x-terminal-emulator', '--working-directory', path])

# ==============================================================================
# SATELLITE UI
# ==============================================================================
class SmartExplorer:
    def __init__(self, root, msg_queue):
        self.queue = msg_queue
        self.engine = ExplorerEngine()
        
        # 1. Window Setup
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.geometry("1000x700+150+150")
        self.win.configure(bg="#202020")
        self.win.attributes("-topmost", True)
        
        # State
        self.current_path = Path(os.getcwd())
        self.font_size = 10
        self.icons = {}
        
        self._gen_icons()
        self._build_ui()
        self._bind_events()
        self.navigate(self.current_path)

    def _gen_icons(self):
        # Programmatic Icons (Folder/File) to avoid external deps
        # Yellow Folder
        ifld = tk.PhotoImage(width=16, height=16)
        ifld.put(("#F4D03F",), to=(1,2,15,14))
        ifld.put(("#F4D03F",), to=(1,1,6,2)) # Tab
        self.icons["folder"] = ifld
        
        # White File
        ifile = tk.PhotoImage(width=16, height=16)
        ifile.put(("#EEE",), to=(2,1,13,15))
        ifile.put(("#CCC",), to=(2,1,13,1)) # Top border
        self.icons["file"] = ifile
        
        # Python File (Blue/Yellow hint)
        ipy = tk.PhotoImage(width=16, height=16)
        ipy.put(("#3776AB",), to=(2,1,13,15))
        ipy.put(("#FFD43B",), to=(5,5,10,10))
        self.icons["py"] = ipy

    def _build_ui(self):
        # -- TITLE BAR --
        title = tk.Frame(self.win, bg="#2d2d2d", height=30)
        title.pack(fill="x")
        tk.Label(title, text="  📂 Smart Explorer", bg="#2d2d2d", fg="#ccc", font=("Arial", 9, "bold")).pack(side="left")
        tk.Button(title, text="✕", command=self.close, bg="#c23621", fg="white", bd=0, width=4).pack(side="right")
        self.title_bar = title

        # -- ADDRESS BAR --
        nav = tk.Frame(self.win, bg="#252526", pady=5)
        nav.pack(fill="x")
        
        self._btn(nav, "⬅", self.go_back)
        self._btn(nav, "⬆", self.go_up)
        
        self.ent_path = tk.Entry(nav, bg="#1e1e1e", fg="#007ACC", font=("Consolas", 10), bd=0)
        self.ent_path.pack(side="left", fill="x", expand=True, padx=5, ipady=4)
        self.ent_path.bind("<Return>", lambda e: self.navigate(self.ent_path.get()))
        
        self._btn(nav, "Go", lambda: self.navigate(self.ent_path.get()))

        # -- TREEVIEW --
        # Custom Style for dark mode
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Explorer.Treeview", background="#202020", foreground="#ccc", 
                        fieldbackground="#202020", borderwidth=0, rowheight=24)
        style.map("Explorer.Treeview", background=[('selected', '#333')])
        style.configure("Explorer.Treeview.Heading", background="#2d2d2d", foreground="#888", relief="flat")

        self.tree = ttk.Treeview(self.win, columns=("size", "date", "type"), 
                                show="tree headings", style="Explorer.Treeview")
        
        self.tree.heading("#0", text="Name", anchor="w")
        self.tree.heading("size", text="Size", anchor="e")
        self.tree.heading("date", text="Date Modified", anchor="w")
        self.tree.heading("type", text="Type", anchor="w")
        
        self.tree.column("#0", width=400)
        self.tree.column("size", width=80, anchor="e")
        self.tree.column("date", width=150)
        self.tree.column("type", width=80)

        sb = ttk.Scrollbar(self.win, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        
        self.tree.pack(side="left", fill="both", expand=True, padx=(5,0), pady=5)
        sb.pack(side="right", fill="y", pady=5)

        # -- STATUS BAR --
        self.lbl_status = tk.Label(self.win, text="Ready.", bg="#007ACC", fg="white", anchor="w", font=("Arial", 8))
        self.lbl_status.pack(fill="x", side="bottom")

    def _btn(self, parent, text, cmd):
        tk.Button(parent, text=text, command=cmd, bg="#333", fg="#ccc", bd=0, padx=8, pady=2).pack(side="left", padx=2)

    def _bind_events(self):
        # Navigation
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree.bind("<Return>", self.on_double_click)
        
        # Context Menu
        self.tree.bind("<Button-3>", self.show_context_menu)
        
        # Zoom (Shift + Scroll)
        self.tree.bind("<Shift-MouseWheel>", self.on_zoom)
        # Linux scroll support
        self.tree.bind("<Shift-Button-4>", lambda e: self.on_zoom(tk.Event(), delta=1)) 
        self.tree.bind("<Shift-Button-5>", lambda e: self.on_zoom(tk.Event(), delta=-1))

        # Drag Window
        self.title_bar.bind("<Button-1>", self._start_move)
        self.title_bar.bind("<B1-Motion>", self._do_move)

    # ==========================================================================
    # LOGIC: NAVIGATION
    # ==========================================================================
    def navigate(self, path_input):
        try:
            p = Path(path_input).resolve()
            if not p.exists(): raise FileNotFoundError
            if not p.is_dir(): p = p.parent
            
            self.current_path = p
            self.ent_path.delete(0, tk.END)
            self.ent_path.insert(0, str(p))
            
            # Update History
            if not self.engine.history or self.engine.history[self.engine.history_idx] != p:
                self.engine.history.append(p)
                self.engine.history_idx = len(self.engine.history) - 1
            
            self._refresh_tree()
            self.lbl_status.config(text=f" {len(self.tree.get_children())} items")
            
        except Exception as e:
            messagebox.showerror("Error", f"Cannot navigate to:\n{path_input}\n\n{e}")

    def _refresh_tree(self):
        # Clear
        for i in self.tree.get_children(): self.tree.delete(i)
        
        try:
            # Sort: Folders first
            items = sorted(list(self.current_path.iterdir()), key=lambda x: (not x.is_dir(), x.name.lower()))
            
            for item in items:
                # Meta
                stats = item.stat()
                size_str = self.engine.format_size(stats.st_size) if item.is_file() else ""
                date_str = self.engine.format_time(stats.st_mtime)
                type_str = "Folder" if item.is_dir() else item.suffix.upper()[1:] + " File"
                
                # Icon
                icon = self.icons["folder"] if item.is_dir() else self.icons["file"]
                if item.suffix == ".py": icon = self.icons["py"]
                
                # Insert
                self.tree.insert("", "end", iid=str(item), text=f" {item.name}", image=icon, 
                               values=(size_str, date_str, type_str))
                               
        except PermissionError:
            self.lbl_status.config(text=" Access Denied")

    def go_up(self):
        self.navigate(self.current_path.parent)

    def go_back(self):
        if self.engine.history_idx > 0:
            self.engine.history_idx -= 1
            self.navigate(self.engine.history[self.engine.history_idx])

    # ==========================================================================
    # LOGIC: ACTIONS & ZOOM
    # ==========================================================================
    def on_double_click(self, event):
        sel = self.tree.selection()
        if not sel: return
        
        path = Path(sel[0])
        
        if path.is_dir():
            self.navigate(path)
        else:
            self._launch_file(path)

    def _launch_file(self, path):
        if path.suffix == ".py":
            # Smart Launch for Python
            venv = self.engine.find_venv(path)
            prefix = f"(.venv) " if venv else ""
            
            action = messagebox.askyesnocancel("Launch Python", 
                                             f"{prefix}Run {path.name}?\n\nYes = Run in Terminal\nNo = Edit/Open System Default")
            if action is None: return # Cancel
            
            if action: # YES -> Run
                self._run_in_terminal(path, venv)
            else: # NO -> Open
                os.startfile(path) if os.name == 'nt' else subprocess.call(('xdg-open', str(path)))
        else:
            # Standard Open
            os.startfile(path) if os.name == 'nt' else subprocess.call(('xdg-open', str(path)))

    def _run_in_terminal(self, script_path, venv_path):
        """Builds the command to activate venv and run script."""
        cmd_str = ""
        if venv_path and os.name == 'nt':
            activate = venv_path / "Scripts" / "activate.bat"
            cmd_str = f'call "{activate}" && python "{script_path}" && pause'
        else:
            cmd_str = f'python "{script_path}" && pause'
            
        subprocess.Popen(f'start cmd /k "{cmd_str}"', shell=True)
        if self.queue:
            self.queue.put({"type": "LOG", "payload": f"Explorer: Launched {script_path.name}"})

    def show_context_menu(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: 
            # Clicked on empty space -> Folder Menu
            path = self.current_path
        else:
            self.tree.selection_set(item_id)
            path = Path(item_id)

        m = tk.Menu(self.win, tearoff=0, bg="#2d2d2d", fg="#eee")
        
        if path.is_dir():
            m.add_command(label="📂 Open", command=lambda: self.navigate(path))
            m.add_separator()
            m.add_command(label="💻 Open Terminal Here", command=lambda: self.engine.open_terminal(path))
            m.add_separator()
            m.add_command(label="📋 Copy Path", command=lambda: self.win.clipboard_append(str(path)))
        else:
            m.add_command(label="▶ Run (Smart)", command=lambda: self._launch_file(path))
            m.add_command(label="📝 Edit", command=lambda: os.startfile(path))
            m.add_separator()
            m.add_command(label="📋 Copy Path", command=lambda: self.win.clipboard_append(str(path)))
            
        m.tk_popup(event.x_root, event.y_root)

    def on_zoom(self, event, delta=None):
        # Handle Windows (event.delta) vs Linux (delta arg)
        if delta is None:
            if event.delta > 0: delta = 1
            elif event.delta < 0: delta = -1
            else: delta = 0
            
        new_size = self.font_size + delta
        if 8 <= new_size <= 24:
            self.font_size = new_size
            
            # Update Style
            s = ttk.Style()
            s.configure("Explorer.Treeview", font=("Segoe UI", self.font_size), rowheight=int(self.font_size * 2.4))
            self.lbl_status.config(text=f" Zoom: {self.font_size}pt")

    # -- DRAG & CLOSE --
    def close(self): self.win.destroy()
    def _start_move(self, e): self.x, self.y = e.x, e.y
    def _do_move(self, e):
        x = self.win.winfo_x() + (e.x - self.x)
        y = self.win.winfo_y() + (e.y - self.y)
        self.win.geometry(f"+{x}+{y}")

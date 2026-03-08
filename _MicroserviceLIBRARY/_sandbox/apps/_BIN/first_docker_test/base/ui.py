import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk

DEFAULT_THEME = {
    "background": "#14181D",
    "foreground": "#F3EEE7",
    "accent": "#C9773B",
    "accent_alt": "#2D7F86",
    "panel_bg": "#10161E",
    "terminal_bg": "#0A0F16",
    "muted": "#8C97A6",
    "border": "#334155",
}


def _load_schema(app_dir):
    schema_path = app_dir / "ui_schema.json"
    if not schema_path.exists():
        return {"layout": {"type": "panel", "id": "details", "weight": 1}, "theme": dict(DEFAULT_THEME)}
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    theme = dict(DEFAULT_THEME)
    theme.update(schema.get("theme", {}))
    schema["theme"] = theme
    return schema


def _apply_theme(root, theme):
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    background = theme.get("background", DEFAULT_THEME["background"])
    foreground = theme.get("foreground", DEFAULT_THEME["foreground"])
    accent = theme.get("accent", DEFAULT_THEME["accent"])
    accent_alt = theme.get("accent_alt", DEFAULT_THEME["accent_alt"])
    panel_bg = theme.get("panel_bg", DEFAULT_THEME["panel_bg"])
    muted = theme.get("muted", DEFAULT_THEME["muted"])
    border = theme.get("border", DEFAULT_THEME["border"])
    root.configure(bg=background)
    style.configure("TFrame", background=background)
    style.configure("Panel.TFrame", background=panel_bg)
    style.configure("TLabel", background=background, foreground=foreground)
    style.configure("Panel.TLabel", background=panel_bg, foreground=foreground)
    style.configure("Heading.TLabel", background=background, foreground=foreground, font=("Segoe UI Semibold", 11))
    style.configure("Muted.TLabel", background=background, foreground=muted)
    style.configure("TButton", background=panel_bg, foreground=foreground, bordercolor=border, padding=6)
    style.map("TButton", background=[("active", accent_alt)], foreground=[("active", foreground)])
    style.configure("Accent.TButton", background=accent, foreground=foreground, bordercolor=accent, padding=6)
    style.map("Accent.TButton", background=[("active", "#D48B57")], foreground=[("active", foreground)])
    style.configure("TLabelframe", background=background, foreground=foreground)
    style.configure("TLabelframe.Label", background=background, foreground=foreground)
    style.configure("TPanedwindow", background=background)
    return theme


def _build_layout(parent, node, panels):
    node_type = node.get("type", "panel")
    if node_type == "panel":
        frame = ttk.Frame(parent, padding=6, style="Panel.TFrame")
        if isinstance(parent, ttk.PanedWindow):
            parent.add(frame, weight=int(node.get("weight", 1)))
        else:
            frame.pack(fill="both", expand=True)
        panels[node.get("id", "panel")] = frame
        return frame
    orient = tk.HORIZONTAL if node_type == "row" else tk.VERTICAL
    pane = ttk.PanedWindow(parent, orient=orient)
    if isinstance(parent, ttk.PanedWindow):
        parent.add(pane, weight=int(node.get("weight", 1)))
    else:
        pane.pack(fill="both", expand=True)
    for child in node.get("children", []) or []:
        _build_layout(pane, child, panels)
    return pane


def run_headless(runtime, settings=None):
    return {
        "status": "headless",
        "health": runtime.health(),
        "services": runtime.list_services(),
        "app_title": (settings or {}).get("app_title", "Stamped App"),
    }


def launch_ui(runtime):
    app_dir = Path(__file__).resolve().parent
    settings = json.loads((app_dir / "settings.json").read_text(encoding="utf-8"))
    schema = _load_schema(app_dir)
    root = tk.Tk()
    theme = _apply_theme(root, schema.get("theme", dict(DEFAULT_THEME)))
    panel_bg = theme.get("panel_bg", DEFAULT_THEME["panel_bg"])
    foreground = theme.get("foreground", DEFAULT_THEME["foreground"])
    accent = theme.get("accent", DEFAULT_THEME["accent"])
    terminal_bg = theme.get("terminal_bg", DEFAULT_THEME["terminal_bg"])
    border = theme.get("border", DEFAULT_THEME["border"])

    root.title(settings.get("app_title", "Stamped App"))
    root.geometry("1180x780")
    panels = {}
    _build_layout(root, schema.get("layout", {"type": "panel", "id": "details", "weight": 1}), panels)
    services_panel = panels.get("services") or next(iter(panels.values()))
    details_panel = panels.get("details") or services_panel
    actions_panel = panels.get("actions") or details_panel

    listbox = tk.Listbox(
        services_panel,
        bg=panel_bg,
        fg=foreground,
        selectbackground=accent,
        selectforeground=foreground,
        borderwidth=0,
        relief="flat",
        highlightthickness=1,
        highlightbackground=border,
        highlightcolor=accent,
        activestyle="none",
    )
    listbox.pack(fill="both", expand=True)

    ttk.Label(details_panel, text=settings.get("app_title", "Stamped App"), style="Heading.TLabel").pack(anchor="w")
    ttk.Label(details_panel, text="Stamped with AppFoundry and driven by the selected service set.", style="Muted.TLabel").pack(anchor="w", pady=(0, 6))

    details = scrolledtext.ScrolledText(
        details_panel,
        wrap="word",
        bg=terminal_bg,
        fg=foreground,
        insertbackground=foreground,
        selectbackground=accent,
        selectforeground=foreground,
        relief="flat",
        borderwidth=0,
    )
    details.pack(fill="both", expand=True)

    mount_frame = ttk.LabelFrame(details_panel, text="Mounted UI Service", padding=6)
    mount_frame.pack(fill="both", expand=True, pady=(8, 0))

    status_var = tk.StringVar(value="Ready.")
    ttk.Label(actions_panel, textvariable=status_var, style="Panel.TLabel", wraplength=320, justify="left").pack(fill="x", pady=(0, 8))

    specs = runtime.list_services()
    for spec in specs:
        listbox.insert(tk.END, spec["class_name"])

    def set_status(message):
        status_var.set(message)

    def write_details(payload):
        details.delete("1.0", tk.END)
        if isinstance(payload, (dict, list)):
            details.insert(tk.END, json.dumps(payload, indent=2))
        else:
            details.insert(tk.END, str(payload))

    def selected_spec():
        if not listbox.curselection():
            return None
        return specs[listbox.curselection()[0]]

    def show_spec():
        spec = selected_spec()
        if spec is None:
            return
        write_details(spec)
        set_status(f"Showing service metadata for {spec['class_name']}.")

    def show_health():
        write_details(runtime.health())
        set_status("Showing runtime health report.")

    def mount_ui_service():
        spec = selected_spec()
        if spec is None:
            return
        if not spec.get("is_ui"):
            messagebox.showinfo("Mount UI", f"{spec['class_name']} is not tagged as a UI service.")
            return
        for child in mount_frame.winfo_children():
            child.destroy()
        try:
            service = runtime.get_service(spec["class_name"], config={"parent": mount_frame})
            packer = getattr(service, "pack", None)
            if callable(packer):
                service.pack(fill="both", expand=True)
            else:
                ttk.Label(mount_frame, text=f"Mounted {spec['class_name']} (no pack method)").pack(fill="both", expand=True)
            set_status(f"Mounted {spec['class_name']} into the preview pane.")
        except Exception as exc:
            set_status("UI mount failed.")
            messagebox.showerror("Mount UI", str(exc))

    listbox.bind("<<ListboxSelect>>", lambda _event: show_spec())
    if specs:
        listbox.selection_set(0)
        show_spec()

    ttk.Button(actions_panel, text="Describe", style="Accent.TButton", command=show_spec).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="Health", command=show_health).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="Mount UI Service", command=mount_ui_service).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="Quit", command=root.destroy).pack(fill="x", pady=4)
    root.mainloop()

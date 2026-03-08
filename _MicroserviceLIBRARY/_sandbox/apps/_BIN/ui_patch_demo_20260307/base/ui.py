import json
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk


def _load_schema(app_dir):
    schema_path = app_dir / "ui_schema.json"
    if not schema_path.exists():
        return {"layout": {"type": "panel", "id": "details", "weight": 1}, "theme": {}}
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _build_layout(parent, node, panels):
    node_type = node.get("type", "panel")
    if node_type == "panel":
        frame = ttk.Frame(parent, padding=6)
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


def run_headless(runtime):
    return {"status": "headless", "health": runtime.health(), "services": runtime.list_services()}


def launch_ui(runtime):
    app_dir = Path(__file__).resolve().parent
    settings = json.loads((app_dir / "settings.json").read_text(encoding="utf-8"))
    schema = _load_schema(app_dir)
    root = tk.Tk()
    root.title(settings.get("app_title", "Stamped App"))
    root.geometry("1100x760")
    panels = {}
    _build_layout(root, schema.get("layout", {"type": "panel", "id": "details", "weight": 1}), panels)
    services_panel = panels.get("services") or next(iter(panels.values()))
    details_panel = panels.get("details") or services_panel
    actions_panel = panels.get("actions") or details_panel
    listbox = tk.Listbox(services_panel)
    listbox.pack(fill="both", expand=True)
    details = scrolledtext.ScrolledText(details_panel, wrap="word")
    details.pack(fill="both", expand=True)
    mount_frame = ttk.Frame(details_panel)
    mount_frame.pack(fill="both", expand=True)
    specs = runtime.list_services()
    for spec in specs:
        listbox.insert(tk.END, spec["class_name"])

    def selected_spec():
        if not listbox.curselection():
            return None
        return specs[listbox.curselection()[0]]

    def show_spec():
        spec = selected_spec()
        if spec is None:
            return
        details.delete("1.0", tk.END)
        details.insert(tk.END, json.dumps(spec, indent=2))

    def show_health():
        details.delete("1.0", tk.END)
        details.insert(tk.END, json.dumps(runtime.health(), indent=2))

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
        except Exception as exc:
            messagebox.showerror("Mount UI", str(exc))

    ttk.Button(actions_panel, text="Describe", command=show_spec).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="Health", command=show_health).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="Mount UI Service", command=mount_ui_service).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="Quit", command=root.destroy).pack(fill="x", pady=4)
    root.mainloop()

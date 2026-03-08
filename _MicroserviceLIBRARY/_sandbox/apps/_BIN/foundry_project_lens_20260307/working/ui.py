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


def run_headless(runtime, settings=None):
    settings = settings or {}
    target_root = Path(settings.get("project_root") or settings.get("canonical_import_root") or Path.cwd()).resolve()
    report = {
        "status": "headless",
        "target_root": str(target_root),
        "health": runtime.health(),
        "services": runtime.list_services(),
    }
    try:
        scan = runtime.call("FingerprintScannerMS", "scan_project", root_path=str(target_root))
        report["project_scan"] = {
            "root": scan.get("root", str(target_root)),
            "project_fingerprint": scan.get("project_fingerprint", ""),
            "file_count": scan.get("file_count", 0),
        }
    except Exception as exc:
        report["project_scan_error"] = str(exc)
    try:
        system_report = runtime.call("SysInspectorMS", "generate_report")
        report["system_report_preview"] = system_report.splitlines()[:12]
    except Exception as exc:
        report["system_report_error"] = str(exc)
    return report


def launch_ui(runtime):
    app_dir = Path(__file__).resolve().parent
    settings = json.loads((app_dir / "settings.json").read_text(encoding="utf-8"))
    schema = _load_schema(app_dir)
    project_root = Path(settings.get("project_root") or settings.get("canonical_import_root") or app_dir).resolve()
    root = tk.Tk()
    root.title(settings.get("app_title", "Stamped App"))
    root.geometry("1240x820")
    panels = {}
    _build_layout(root, schema.get("layout", {"type": "panel", "id": "details", "weight": 1}), panels)
    services_panel = panels.get("services") or next(iter(panels.values()))
    details_panel = panels.get("details") or services_panel
    actions_panel = panels.get("actions") or details_panel

    listbox = tk.Listbox(services_panel)
    listbox.pack(fill="both", expand=True)

    header = ttk.Label(details_panel, text=f"Target root: {project_root}", anchor="w")
    header.pack(fill="x", pady=(0, 6))

    details = scrolledtext.ScrolledText(details_panel, wrap="word", height=20)
    details.pack(fill="both", expand=True)

    mount_frame = ttk.LabelFrame(details_panel, text="Mounted UI Service", padding=6)
    mount_frame.pack(fill="both", expand=True, pady=(8, 0))

    status_var = tk.StringVar(value=f"Ready. Target root: {project_root}")
    ttk.Label(actions_panel, textvariable=status_var, anchor="w", justify="left", wraplength=320).pack(fill="x", pady=(0, 8))

    specs = runtime.list_services()
    for spec in specs:
        listbox.insert(tk.END, spec["class_name"])

    def set_status(message):
        status_var.set(message)

    def write_details(value):
        details.delete("1.0", tk.END)
        if isinstance(value, (dict, list)):
            details.insert(tk.END, json.dumps(value, indent=2))
            return
        details.insert(tk.END, str(value))

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

    def scan_project():
        set_status(f"Scanning {project_root} ...")
        try:
            report = runtime.call("FingerprintScannerMS", "scan_project", root_path=str(project_root))
            summary = {
                "root": report.get("root", str(project_root)),
                "project_fingerprint": report.get("project_fingerprint", ""),
                "file_count": report.get("file_count", 0),
            }
            file_hashes = report.get("file_hashes") or {}
            if file_hashes:
                preview_items = sorted(file_hashes.items())[:25]
                summary["file_hash_preview"] = dict(preview_items)
            write_details(summary)
            set_status(f"Scan complete: {summary['file_count']} files fingerprinted.")
        except Exception as exc:
            set_status("Project scan failed.")
            messagebox.showerror("Scan Project", str(exc))

    def show_system_audit():
        set_status("Running system audit ...")
        try:
            write_details(runtime.call("SysInspectorMS", "generate_report"))
            set_status("System audit complete.")
        except Exception as exc:
            set_status("System audit failed.")
            messagebox.showerror("System Audit", str(exc))

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
            set_status(f"Mounted {spec['class_name']} into the workspace pane.")
        except Exception as exc:
            set_status("UI mount failed.")
            messagebox.showerror("Mount UI", str(exc))

    listbox.bind("<<ListboxSelect>>", lambda _event: show_spec())
    if specs:
        listbox.selection_set(0)
        show_spec()

    ttk.Button(actions_panel, text="Describe", command=show_spec).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="Health", command=show_health).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="Scan Project", command=scan_project).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="System Audit", command=show_system_audit).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="Mount UI Service", command=mount_ui_service).pack(fill="x", pady=4)
    ttk.Button(actions_panel, text="Quit", command=root.destroy).pack(fill="x", pady=4)
    root.mainloop()

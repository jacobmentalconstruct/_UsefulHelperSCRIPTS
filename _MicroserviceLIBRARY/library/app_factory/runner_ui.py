from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Any

from .constants import WORKSPACE_ROOT
from .pipeline_runner import DEFAULT_DOCKER_IMAGE, SandboxRunConfig, build_sandbox_command_queue, docker_preflight, execute_command_queue
from .query import LibraryQueryService

THEME = {
    'bg': '#14181D',
    'panel': '#10161E',
    'panel_alt': '#17202B',
    'fg': '#F3EEE7',
    'muted': '#8C97A6',
    'accent': '#C9773B',
    'accent_alt': '#2D7F86',
    'border': '#334155',
    'terminal_bg': '#0A0F16',
    'terminal_fg': '#E6E2DA',
    'terminal_system': '#7DD3FC',
    'terminal_error': '#F87171',
    'terminal_success': '#86EFAC',
}


class PipelineRunnerApp:
    def __init__(self, query_service: LibraryQueryService | None = None):
        self.query = query_service or LibraryQueryService(auto_build=False)
        self.root = tk.Tk()
        self.root.title('AppFoundry Pipeline Runner')
        self.root.geometry('1480x960')
        self.root.configure(bg=THEME['bg'])
        self._style = ttk.Style(self.root)
        try:
            self._style.theme_use('clam')
        except Exception:
            pass
        self._configure_styles()

        self.event_queue: queue.Queue[dict] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stop_event: threading.Event | None = None
        self.current_plan: dict[str, Any] | None = None

        self.run_id_var = tk.StringVar(value='demo_run')
        self.template_var = tk.StringVar(value='ui_explorer_workbench')
        self.manifest_var = tk.StringVar(value='')
        self.name_var = tk.StringVar(value='Demo App')
        self.sandbox_root_var = tk.StringVar(value=str((WORKSPACE_ROOT / '_sanbox' / 'apps').resolve()))
        self.promote_destination_var = tk.StringVar(value=str((WORKSPACE_ROOT / '_sanbox' / 'promoted' / 'demo_run').resolve()))
        self.execution_backend_var = tk.StringVar(value='local')
        self.vendor_mode_var = tk.StringVar(value='module_ref')
        self.resolution_profile_var = tk.StringVar(value='app_ready')
        self.docker_image_var = tk.StringVar(value=DEFAULT_DOCKER_IMAGE)
        self.force_stamp_var = tk.BooleanVar(value=True)
        self.backup_patches_var = tk.BooleanVar(value=True)
        self.promote_after_var = tk.BooleanVar(value=True)
        self.allow_host_writes_var = tk.BooleanVar(value=False)
        self.typing_speed_var = tk.DoubleVar(value=0.008)
        self.status_var = tk.StringVar(value='Ready.')
        self.backend_status_var = tk.StringVar(value='')

        self.templates = {item['template_id']: item for item in self.query.list_templates()}
        if self.template_var.get() not in self.templates and self.templates:
            self.template_var.set(next(iter(self.templates)))

        self._build_ui()
        self.run_id_var.trace_add('write', self._sync_defaults)
        self.template_var.trace_add('write', self._sync_defaults)
        self.execution_backend_var.trace_add('write', self._sync_backend_defaults)
        self._sync_defaults()
        self._sync_backend_defaults()
        self.root.after(50, self._drain_events)

    def _configure_styles(self) -> None:
        self._style.configure('TFrame', background=THEME['bg'])
        self._style.configure('Panel.TFrame', background=THEME['panel'])
        self._style.configure('TLabel', background=THEME['bg'], foreground=THEME['fg'])
        self._style.configure('Panel.TLabel', background=THEME['panel'], foreground=THEME['fg'])
        self._style.configure('Muted.TLabel', background=THEME['bg'], foreground=THEME['muted'])
        self._style.configure('Heading.TLabel', background=THEME['bg'], foreground=THEME['fg'], font=('Segoe UI Semibold', 11))
        self._style.configure('TButton', background=THEME['panel_alt'], foreground=THEME['fg'], bordercolor=THEME['border'], padding=6)
        self._style.map('TButton', background=[('active', THEME['panel'])])
        self._style.configure('Accent.TButton', background=THEME['accent'], foreground=THEME['fg'], bordercolor=THEME['accent'], padding=6)
        self._style.map('Accent.TButton', background=[('active', '#D48B57')])
        self._style.configure('Secondary.TButton', background=THEME['accent_alt'], foreground=THEME['fg'], bordercolor=THEME['accent_alt'], padding=6)
        self._style.map('Secondary.TButton', background=[('active', '#3997A2')])
        self._style.configure('TCheckbutton', background=THEME['bg'], foreground=THEME['fg'])
        self._style.configure('TEntry', fieldbackground=THEME['panel'], foreground=THEME['fg'], insertcolor=THEME['fg'])
        self._style.configure('TCombobox', fieldbackground=THEME['panel'], foreground=THEME['fg'])
        self._style.configure('TLabelframe', background=THEME['bg'], foreground=THEME['fg'])
        self._style.configure('TLabelframe.Label', background=THEME['bg'], foreground=THEME['fg'])
        self._style.configure('TProgressbar', troughcolor=THEME['panel'], background=THEME['accent'])
        self._style.configure('TPanedwindow', background=THEME['bg'])

    def _build_ui(self) -> None:
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill='both', expand=True, padx=10, pady=10)

        control_frame = ttk.Frame(paned, style='Panel.TFrame', padding=10)
        terminal_frame = ttk.Frame(paned, style='Panel.TFrame', padding=10)
        paned.add(control_frame, weight=1)
        paned.add(terminal_frame, weight=2)

        self._build_controls(control_frame)
        self._build_terminal(terminal_frame)

    def _build_controls(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text='Pipeline Config', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(
            parent,
            text='Queue stamp/apply/validate/promote steps and stream the run into a redacted terminal view.',
            style='Muted.TLabel',
            wraplength=400,
        ).pack(anchor='w', pady=(0, 8))

        fields = ttk.Frame(parent, style='Panel.TFrame')
        fields.pack(fill='x')
        for column in (0, 1, 2):
            fields.columnconfigure(column, weight=1 if column == 1 else 0)

        self._labeled_entry(fields, 0, 'Run ID', self.run_id_var)
        self._labeled_combo(fields, 1, 'Template', self.template_var, values=sorted(self.templates))
        self._labeled_entry(fields, 2, 'Manifest', self.manifest_var, browse=self._browse_manifest)
        self._labeled_entry(fields, 3, 'App Name', self.name_var)
        self._labeled_combo(fields, 4, 'Backend', self.execution_backend_var, values=['local', 'docker'])
        self._labeled_combo(fields, 5, 'Vendor Mode', self.vendor_mode_var, values=['module_ref', 'static'])
        self._labeled_combo(fields, 6, 'Resolution', self.resolution_profile_var, values=['app_ready', 'strict', 'explicit_pack'])
        self._labeled_entry(fields, 7, 'Docker Image', self.docker_image_var)
        self._labeled_entry(fields, 8, 'Sandbox Root', self.sandbox_root_var)
        self._labeled_entry(fields, 9, 'Promote To', self.promote_destination_var)

        options = ttk.Frame(parent, style='Panel.TFrame')
        options.pack(fill='x', pady=(8, 8))
        ttk.Checkbutton(options, text='Force stamp workspace', variable=self.force_stamp_var).pack(anchor='w')
        ttk.Checkbutton(options, text='Create .bak files during patch apply', variable=self.backup_patches_var).pack(anchor='w')
        ttk.Checkbutton(options, text='Promote after validate', variable=self.promote_after_var).pack(anchor='w')
        ttk.Checkbutton(options, text='Approve host writes outside _sanbox', variable=self.allow_host_writes_var).pack(anchor='w')
        ttk.Label(options, textvariable=self.backend_status_var, style='Muted.TLabel', wraplength=400, justify='left').pack(anchor='w', pady=(6, 0))
        speed_row = ttk.Frame(parent, style='Panel.TFrame')
        speed_row.pack(fill='x', pady=(0, 8))
        ttk.Label(speed_row, text='Typing Delay (sec)', style='Panel.TLabel').pack(side='left')
        ttk.Entry(speed_row, textvariable=self.typing_speed_var, width=8).pack(side='left', padx=(8, 0))

        patch_frame = ttk.LabelFrame(parent, text='Patch Manifests', padding=8)
        patch_frame.pack(fill='both', expand=False, pady=(0, 8))
        self.patch_list = tk.Listbox(
            patch_frame,
            height=7,
            bg=THEME['panel_alt'],
            fg=THEME['fg'],
            selectbackground=THEME['accent'],
            selectforeground=THEME['fg'],
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=THEME['border'],
            highlightcolor=THEME['accent'],
        )
        self.patch_list.pack(fill='both', expand=True)
        patch_buttons = ttk.Frame(patch_frame, style='Panel.TFrame')
        patch_buttons.pack(fill='x', pady=(6, 0))
        ttk.Button(patch_buttons, text='Add', style='Secondary.TButton', command=self._add_patch_manifests).pack(side='left')
        ttk.Button(patch_buttons, text='Remove', command=self._remove_selected_patch).pack(side='left', padx=(6, 0))
        ttk.Button(patch_buttons, text='Clear', command=self._clear_patches).pack(side='left', padx=(6, 0))

        queue_frame = ttk.LabelFrame(parent, text='Command Queue', padding=8)
        queue_frame.pack(fill='both', expand=True)
        self.queue_preview = tk.Text(
            queue_frame,
            height=16,
            wrap='word',
            bg=THEME['terminal_bg'],
            fg=THEME['terminal_fg'],
            insertbackground=THEME['terminal_fg'],
            relief='flat',
            borderwidth=0,
        )
        self.queue_preview.pack(fill='both', expand=True)

        controls = ttk.Frame(parent, style='Panel.TFrame')
        controls.pack(fill='x', pady=(8, 0))
        ttk.Button(controls, text='Build Queue', command=self._build_plan).pack(fill='x')
        ttk.Button(controls, text='Run Pipeline', style='Accent.TButton', command=self._start_run).pack(fill='x', pady=(6, 0))
        ttk.Button(controls, text='Abort', command=self._abort_run).pack(fill='x', pady=(6, 0))

    def _build_terminal(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text='Terminal Stream', style='Heading.TLabel').pack(anchor='w')
        ttk.Label(
            parent,
            text='Command echo and stdout/stderr are redacted to logical paths. Docker mode uses /repo and /workspace.',
            style='Muted.TLabel',
            wraplength=860,
        ).pack(anchor='w', pady=(0, 8))

        self.progress = ttk.Progressbar(parent, mode='indeterminate')
        self.progress.pack(fill='x', pady=(0, 8))
        ttk.Label(parent, textvariable=self.status_var, style='Panel.TLabel').pack(anchor='w', pady=(0, 6))

        self.terminal = tk.Text(
            parent,
            wrap='word',
            bg=THEME['terminal_bg'],
            fg=THEME['terminal_fg'],
            insertbackground=THEME['terminal_fg'],
            relief='flat',
            borderwidth=0,
            font=('Cascadia Mono', 10),
        )
        self.terminal.pack(fill='both', expand=True)
        self.terminal.tag_configure('prompt', foreground=THEME['accent'])
        self.terminal.tag_configure('stdout', foreground=THEME['terminal_fg'])
        self.terminal.tag_configure('system', foreground=THEME['terminal_system'])
        self.terminal.tag_configure('error', foreground=THEME['terminal_error'])
        self.terminal.tag_configure('success', foreground=THEME['terminal_success'])

    def _labeled_entry(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, browse=None) -> None:
        ttk.Label(parent, text=label, style='Panel.TLabel').grid(row=row, column=0, sticky='w', pady=3)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky='ew', pady=3, padx=(8, 8))
        if browse is not None:
            ttk.Button(parent, text='Browse', command=browse).grid(row=row, column=2, sticky='ew', pady=3)

    def _labeled_combo(self, parent: ttk.Frame, row: int, label: str, variable: tk.StringVar, values: list[str]) -> None:
        ttk.Label(parent, text=label, style='Panel.TLabel').grid(row=row, column=0, sticky='w', pady=3)
        ttk.Combobox(parent, textvariable=variable, values=values, state='readonly').grid(row=row, column=1, sticky='ew', pady=3, padx=(8, 8))

    def _sync_defaults(self, *_args) -> None:
        run_id = self.run_id_var.get().strip() or 'demo_run'
        if not self.name_var.get().strip() or self.name_var.get().endswith(' Demo'):
            template_id = self.template_var.get().strip()
            template_name = self.templates.get(template_id, {}).get('name', 'Demo App')
            self.name_var.set(f'{template_name} Demo')
        default_promote = (WORKSPACE_ROOT / '_sanbox' / 'promoted' / run_id).resolve()
        self.promote_destination_var.set(str(default_promote))

    def _sync_backend_defaults(self, *_args) -> None:
        backend = self.execution_backend_var.get().strip().lower()
        if backend == 'docker':
            self.vendor_mode_var.set('static')
            preflight = docker_preflight()
            if preflight.get('available'):
                self.backend_status_var.set(
                    f'Docker ready ({preflight.get("server_version", "unknown")}). Runs execute in a container with /repo read-only and /workspace writable.'
                )
            else:
                self.backend_status_var.set(str(preflight.get('user_message', 'Docker is unavailable.')))
        else:
            self.backend_status_var.set('Local backend active. Terminal output is path-redacted, but commands execute on the host.')

    def _browse_manifest(self) -> None:
        path = filedialog.askopenfilename(title='Select manifest JSON', filetypes=[('JSON files', '*.json')])
        if path:
            self.manifest_var.set(path)

    def _add_patch_manifests(self) -> None:
        paths = filedialog.askopenfilenames(title='Select patch manifests', filetypes=[('JSON files', '*.json')])
        for path in paths:
            if path not in self.patch_list.get(0, tk.END):
                self.patch_list.insert(tk.END, path)

    def _remove_selected_patch(self) -> None:
        selection = list(self.patch_list.curselection())
        for index in reversed(selection):
            self.patch_list.delete(index)

    def _clear_patches(self) -> None:
        self.patch_list.delete(0, tk.END)

    def _collect_config(self) -> SandboxRunConfig:
        return SandboxRunConfig(
            run_id=self.run_id_var.get().strip(),
            template_id='' if self.manifest_var.get().strip() else self.template_var.get().strip(),
            manifest_path=self.manifest_var.get().strip(),
            name=self.name_var.get().strip(),
            sandbox_root=self.sandbox_root_var.get().strip(),
            patch_manifests=list(self.patch_list.get(0, tk.END)),
            promote_destination=self.promote_destination_var.get().strip() if self.promote_after_var.get() else '',
            vendor_mode=self.vendor_mode_var.get().strip(),
            resolution_profile=self.resolution_profile_var.get().strip(),
            force_stamp=self.force_stamp_var.get(),
            backup_patches=self.backup_patches_var.get(),
            promote_after=self.promote_after_var.get(),
            execution_backend=self.execution_backend_var.get().strip(),
            docker_image=self.docker_image_var.get().strip() or DEFAULT_DOCKER_IMAGE,
            allow_host_writes=self.allow_host_writes_var.get(),
        )
    def _build_plan(self) -> None:
        try:
            config = self._collect_config()
            plan = build_sandbox_command_queue(config)
        except Exception as exc:
            messagebox.showerror('Build Queue', str(exc))
            return
        self.current_plan = plan
        self.queue_preview.delete('1.0', tk.END)
        self.queue_preview.insert(tk.END, f'Backend: {plan["execution_backend"]}\n')
        self.queue_preview.insert(tk.END, f'Workspace: {plan["display_workspace_root"]}\n')
        self.queue_preview.insert(tk.END, f'Promote to: {plan["display_promote_destination"]}\n')
        self.queue_preview.insert(tk.END, f'Run log: {plan["display_run_log_path"]}\n')
        if plan.get('preflight'):
            self.queue_preview.insert(tk.END, f'Preflight: {plan["preflight"].get("user_message", "")}\n')
        if plan.get('notices'):
            self.queue_preview.insert(tk.END, 'Notices:\n')
            for item in plan['notices']:
                self.queue_preview.insert(tk.END, f'  - {item}\n')
        self.queue_preview.insert(tk.END, '\n')
        for index, command in enumerate(plan['display_commands'], start=1):
            self.queue_preview.insert(tk.END, f'{index}. {command}\n')
        self.status_var.set('Queue built.')

    def _start_run(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            messagebox.showinfo('Pipeline Runner', 'A pipeline is already running.')
            return
        self._build_plan()
        if not self.current_plan:
            return
        self.terminal.delete('1.0', tk.END)
        self.status_var.set('Running pipeline ...')
        self.progress.start(10)
        self.stop_event = threading.Event()
        typing_delay = max(0.0, float(self.typing_speed_var.get() or 0.0))

        def _emit(event: dict) -> None:
            self.event_queue.put(event)

        def _run() -> None:
            result = execute_command_queue(
                self.current_plan['commands'],
                on_event=_emit,
                stop_event=self.stop_event,
                typing_delay=typing_delay,
                run_log_path=self.current_plan['run_log_path'],
                display_run_log_path=self.current_plan['display_run_log_path'],
            )
            self.event_queue.put({'type': 'runner_result', 'result': result})

        self.worker = threading.Thread(target=_run, daemon=True)
        self.worker.start()

    def _abort_run(self) -> None:
        if self.stop_event is not None:
            self.stop_event.set()
            self.status_var.set('Abort requested ...')

    def _drain_events(self) -> None:
        try:
            while True:
                event = self.event_queue.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.root.after(50, self._drain_events)

    def _handle_event(self, event: dict) -> None:
        event_type = event.get('type', '')
        if event_type == 'run_started':
            self._append_terminal(f"[runner] log -> {event.get('run_log_path', '')}\\n", 'system')
            return
        if event_type == 'step_started':
            self.status_var.set(f"Running step {event.get('step_index')}: {event.get('label', '')}")
            self._append_terminal(f"\\n[step] {event.get('label', '')}\\n", 'system')
            return
        if event_type == 'command_char':
            self._append_terminal(event.get('text', ''), 'prompt', scroll=False)
            self.terminal.see(tk.END)
            return
        if event_type == 'stdout':
            text = event.get('text', '')
            tag = 'error' if 'ERROR' in text or 'Traceback' in text else 'stdout'
            self._append_terminal(text, tag)
            return
        if event_type == 'step_finished':
            tag = 'success' if int(event.get('returncode', 1)) == 0 else 'error'
            self._append_terminal(f"[exit] {event.get('label', '')} -> {event.get('returncode')}\\n", tag)
            return
        if event_type == 'run_finished':
            self.progress.stop()
            if event.get('ok'):
                self.status_var.set('Pipeline complete.')
                self._append_terminal('[runner] pipeline complete\\n', 'success')
            else:
                self.status_var.set('Pipeline failed.')
                self._append_terminal('[runner] pipeline failed\\n', 'error')
            return
        if event_type == 'run_aborted':
            self.progress.stop()
            self.status_var.set('Pipeline aborted.')
            self._append_terminal('[runner] pipeline aborted\\n', 'error')
            return
        if event_type == 'runner_result':
            self.progress.stop()
            result = event.get('result', {}) or {}
            if result.get('ok'):
                self.status_var.set('Pipeline complete.')
            elif result.get('aborted'):
                self.status_var.set('Pipeline aborted.')
            else:
                self.status_var.set('Pipeline failed.')
            return

    def _append_terminal(self, text: str, tag: str, *, scroll: bool = True) -> None:
        self.terminal.insert(tk.END, text, tag)
        if scroll:
            self.terminal.see(tk.END)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    PipelineRunnerApp().run()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

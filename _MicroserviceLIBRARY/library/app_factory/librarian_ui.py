"""Menu-driven Tkinter librarian UI for catalog browsing and app stamping."""

from __future__ import annotations

import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any, Dict, List

from .assistant import OllamaAssistantService
from .packs import InstallPackManager
from .query import LibraryQueryService
from .stamper import AppStamper
from .ui_schema import UiSchemaCommitService, UiSchemaPreviewService

THEME = {
    'app_bg': '#14181D',
    'panel_bg': '#1B222B',
    'panel_alt_bg': '#222C38',
    'panel_soft_bg': '#2A3644',
    'field_bg': '#10161E',
    'field_alt_bg': '#16202A',
    'border': '#3A4959',
    'text': '#E7EDF3',
    'muted_text': '#97A6B5',
    'accent': '#C56D3A',
    'accent_hover': '#D9824C',
    'accent_active': '#A65A30',
    'secondary': '#2F7684',
    'secondary_hover': '#3B8FA0',
    'secondary_active': '#275D69',
    'selection': '#35566C',
    'success': '#4FAA80',
    'warning': '#D7A45A',
    'busy': '#E0A458',
}


class LibrarianApp:
    def __init__(self, query_service: LibraryQueryService | None=None):
        self.query_service = query_service or LibraryQueryService()
        self.stamper = AppStamper(self.query_service)
        self.ui_preview = UiSchemaPreviewService()
        self.ui_commit = UiSchemaCommitService()
        self.assistant = OllamaAssistantService()
        self.pack_manager = InstallPackManager(self.query_service.builder)
        self.root = tk.Tk()
        self.root.title('Library Librarian')
        self.root.geometry('1400x900')
        self._setup_theme()
        self._busy_count = 0
        self.assistant_requires_model: List[ttk.Button] = []
        self.selected_services: List[str] = []
        self.current_services: List[Dict[str, Any]] = []
        self.catalog_service_payload: Dict[str, Any] | None = None
        self.catalog_dependency_payload: Dict[str, Any] | None = None
        self._build_ui()
        self._refresh_services()
        self.root.after(150, self._refresh_models)

    def run(self) -> None:
        self.root.mainloop()

    def _setup_theme(self) -> None:
        self.root.configure(bg=THEME['app_bg'])
        self.root.option_add('*TCombobox*Listbox*Background', THEME['field_bg'])
        self.root.option_add('*TCombobox*Listbox*Foreground', THEME['text'])
        self.root.option_add('*TCombobox*Listbox*selectBackground', THEME['selection'])
        self.root.option_add('*TCombobox*Listbox*selectForeground', THEME['text'])
        style = ttk.Style(self.root)
        if 'clam' in style.theme_names():
            style.theme_use('clam')
        style.configure('.', background=THEME['panel_bg'], foreground=THEME['text'])
        style.configure('TFrame', background=THEME['panel_bg'])
        style.configure('TPanedwindow', background=THEME['app_bg'])
        style.configure('TLabel', background=THEME['panel_bg'], foreground=THEME['text'])
        style.configure('TLabelframe', background=THEME['panel_bg'], bordercolor=THEME['border'])
        style.configure('TLabelframe.Label', background=THEME['panel_bg'], foreground=THEME['text'])
        style.configure('TEntry', fieldbackground=THEME['field_bg'], foreground=THEME['text'])
        style.configure(
            'TCombobox',
            fieldbackground=THEME['field_bg'],
            background=THEME['panel_alt_bg'],
            foreground=THEME['text'],
            arrowcolor=THEME['text'],
            bordercolor=THEME['border'],
        )
        style.map(
            'TCombobox',
            fieldbackground=[('readonly', THEME['field_bg'])],
            background=[('readonly', THEME['panel_alt_bg'])],
            foreground=[('readonly', THEME['text'])],
        )
        style.configure(
            'TButton',
            background=THEME['panel_alt_bg'],
            foreground=THEME['text'],
            bordercolor=THEME['border'],
            padding=(10, 6),
        )
        style.map(
            'TButton',
            background=[('active', THEME['panel_soft_bg']), ('pressed', THEME['secondary_active'])],
            foreground=[('disabled', THEME['muted_text'])],
        )
        style.configure('Accent.TButton', background=THEME['accent'], foreground=THEME['text'], bordercolor=THEME['accent_active'], padding=(10, 6))
        style.map('Accent.TButton', background=[('active', THEME['accent_hover']), ('pressed', THEME['accent_active'])])
        style.configure('Secondary.TButton', background=THEME['secondary'], foreground=THEME['text'], bordercolor=THEME['secondary_active'], padding=(10, 6))
        style.map('Secondary.TButton', background=[('active', THEME['secondary_hover']), ('pressed', THEME['secondary_active'])])
        style.configure(
            'Busy.Horizontal.TProgressbar',
            troughcolor=THEME['field_alt_bg'],
            background=THEME['busy'],
            bordercolor=THEME['border'],
            lightcolor=THEME['busy'],
            darkcolor=THEME['accent_active'],
        )
        style.configure('TNotebook', background=THEME['app_bg'], borderwidth=0, tabmargins=(2, 2, 2, 0))
        style.configure('TNotebook.Tab', background=THEME['panel_alt_bg'], foreground=THEME['muted_text'], padding=(12, 7), borderwidth=0)
        style.map(
            'TNotebook.Tab',
            background=[('selected', THEME['accent']), ('active', THEME['panel_soft_bg'])],
            foreground=[('selected', THEME['text']), ('active', THEME['text'])],
        )

    def _apply_text_theme(self, widget: tk.Text) -> None:
        widget.configure(
            bg=THEME['field_bg'],
            fg=THEME['text'],
            insertbackground=THEME['text'],
            selectbackground=THEME['selection'],
            selectforeground=THEME['text'],
            relief=tk.FLAT,
            borderwidth=0,
            padx=8,
            pady=8,
            highlightthickness=1,
            highlightbackground=THEME['border'],
            highlightcolor=THEME['accent'],
        )

    def _apply_listbox_theme(self, widget: tk.Listbox) -> None:
        widget.configure(
            bg=THEME['field_bg'],
            fg=THEME['text'],
            selectbackground=THEME['selection'],
            selectforeground=THEME['text'],
            activestyle='none',
            relief=tk.FLAT,
            borderwidth=0,
            highlightthickness=1,
            highlightbackground=THEME['border'],
            highlightcolor=THEME['accent'],
        )

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True, padx=8, pady=(8, 0))
        self.catalog_tab = ttk.Frame(notebook)
        self.manifest_tab = ttk.Frame(notebook)
        self.assistant_tab = ttk.Frame(notebook)
        self.packs_tab = ttk.Frame(notebook)
        notebook.add(self.catalog_tab, text='Catalog')
        notebook.add(self.manifest_tab, text='Manifest')
        notebook.add(self.assistant_tab, text='Assistant')
        notebook.add(self.packs_tab, text='Packs')
        self._build_catalog_tab()
        self._build_manifest_tab()
        self._build_assistant_tab()
        self._build_packs_tab()

        busy_frame = ttk.Frame(self.root, padding=(10, 6))
        busy_frame.pack(fill='x', padx=8, pady=(0, 8))
        self.busy_var = tk.StringVar(value='Ready.')
        self.busy_label = ttk.Label(busy_frame, textvariable=self.busy_var, foreground=THEME['muted_text'])
        self.busy_label.pack(side='left')
        self.busy_progress = ttk.Progressbar(
            busy_frame,
            mode='indeterminate',
            style='Busy.Horizontal.TProgressbar',
            length=160,
        )

    def _set_busy(self, message: str) -> None:
        self._busy_count += 1
        self.busy_var.set(message)
        if not self.busy_progress.winfo_ismapped():
            self.busy_progress.pack(side='right')
        self.busy_progress.start(12)
        self.root.configure(cursor='watch')

    def _clear_busy(self) -> None:
        self._busy_count = max(0, self._busy_count - 1)
        if self._busy_count > 0:
            return
        self.busy_progress.stop()
        if self.busy_progress.winfo_ismapped():
            self.busy_progress.pack_forget()
        self.busy_var.set('Ready.')
        self.root.configure(cursor='')

    def _set_text_content(self, widget: tk.Text, content: str) -> None:
        widget.delete('1.0', tk.END)
        widget.insert(tk.END, content)

    def _run_background_action(
        self,
        worker,
        on_success,
        busy_message: str,
        on_error=None,
    ) -> None:
        def _runner() -> None:
            try:
                result = worker()
            except Exception as exc:
                def _handle_error() -> None:
                    self._clear_busy()
                    if on_error is not None:
                        on_error(exc)
                    else:
                        messagebox.showerror('Assistant', str(exc))
                self.root.after(0, _handle_error)
                return

            def _handle_success() -> None:
                self._clear_busy()
                on_success(result)

            self.root.after(0, _handle_success)

        self._set_busy(busy_message)
        threading.Thread(target=_runner, daemon=True).start()

    def _build_catalog_tab(self) -> None:
        container = ttk.Frame(self.catalog_tab, padding=8)
        container.pack(fill='both', expand=True)
        panes = ttk.PanedWindow(container, orient=tk.HORIZONTAL)
        panes.pack(fill='both', expand=True)
        left = ttk.Frame(panes)
        right = ttk.Frame(panes)
        panes.add(left, weight=2)
        panes.add(right, weight=5)
        ttk.Label(left, text='Layer').pack(anchor='w')
        self.layer_var = tk.StringVar(value='all')
        self.layer_combo = ttk.Combobox(left, textvariable=self.layer_var, state='readonly')
        self.layer_combo.pack(fill='x', pady=4)
        self.layer_combo.bind('<<ComboboxSelected>>', lambda *_: self._refresh_services())
        self.service_list = tk.Listbox(left, selectmode=tk.EXTENDED)
        self._apply_listbox_theme(self.service_list)
        self.service_list.pack(fill='both', expand=True)
        self.service_list.bind('<<ListboxSelect>>', lambda *_: self._show_selected_service())
        self.service_list.bind('<Button-3>', self._show_service_context_menu)
        self.catalog_context_menu = tk.Menu(
            self.root,
            tearoff=0,
            bg=THEME['panel_alt_bg'],
            fg=THEME['text'],
            activebackground=THEME['accent'],
            activeforeground=THEME['text'],
            relief=tk.FLAT,
            bd=1,
        )
        self.catalog_context_menu.add_command(label='Inspect Selected Service', command=self._show_selected_service)
        self.catalog_context_menu.add_command(label='Explain Selected Service', command=self._explain_selected_service)
        self.catalog_context_menu.add_command(label='Show Dependencies', command=self._show_selected_dependencies)
        self.catalog_context_menu.add_separator()
        self.catalog_context_menu.add_command(label='Recommend Blueprint', command=self._recommend_blueprint)
        button_bar = ttk.Frame(left)
        button_bar.pack(fill='x', pady=6)
        ttk.Button(button_bar, text='Rebuild Catalog', command=self._rebuild_catalog, style='Secondary.TButton').pack(fill='x', pady=2)
        ttk.Button(button_bar, text='Explain Selected', command=self._explain_selected_service, style='Secondary.TButton').pack(fill='x', pady=2)
        ttk.Button(button_bar, text='Show Dependencies', command=self._show_selected_dependencies).pack(fill='x', pady=2)
        ttk.Button(button_bar, text='List UI Components', command=self._list_ui_components).pack(fill='x', pady=2)
        ttk.Button(button_bar, text='List Orchestrators', command=self._list_orchestrators).pack(fill='x', pady=2)
        ttk.Button(button_bar, text='List Managers', command=self._list_managers).pack(fill='x', pady=2)
        ttk.Button(button_bar, text='Recommend Blueprint', command=self._recommend_blueprint, style='Accent.TButton').pack(fill='x', pady=2)

        summary_frame = ttk.LabelFrame(right, text='Selected Service', padding=8)
        summary_frame.pack(fill='x')
        summary_grid = ttk.Frame(summary_frame)
        summary_grid.pack(fill='x', expand=True)
        self.catalog_summary_vars: Dict[str, tk.StringVar] = {}
        summary_fields = [
            ('display_name', 'Name'),
            ('class_name', 'Class'),
            ('layer', 'Layer'),
            ('version', 'Version'),
            ('ui_status', 'UI Service'),
            ('endpoint_count', 'Endpoints'),
            ('dependency_count', 'Dependencies'),
            ('tags', 'Tags'),
            ('capabilities', 'Capabilities'),
            ('import_key', 'Import Key'),
            ('source_path', 'Source Path'),
        ]
        for row_index, (field_key, label_text) in enumerate(summary_fields):
            summary_grid.rowconfigure(row_index, weight=0)
            summary_grid.columnconfigure(1, weight=1)
            ttk.Label(summary_grid, text=label_text).grid(row=row_index, column=0, sticky='nw', padx=(0, 8), pady=2)
            value_var = tk.StringVar(value='-')
            self.catalog_summary_vars[field_key] = value_var
            ttk.Label(
                summary_grid,
                textvariable=value_var,
                justify='left',
                anchor='w',
                wraplength=720,
            ).grid(row=row_index, column=1, sticky='ew', pady=2)

        self.catalog_notebook = ttk.Notebook(right)
        self.catalog_notebook.pack(fill='both', expand=True, pady=(8, 8))
        self.catalog_overview_tab = ttk.Frame(self.catalog_notebook)
        self.catalog_endpoints_tab = ttk.Frame(self.catalog_notebook)
        self.catalog_dependencies_tab = ttk.Frame(self.catalog_notebook)
        self.catalog_source_tab = ttk.Frame(self.catalog_notebook)
        self.catalog_raw_json_tab = ttk.Frame(self.catalog_notebook)
        self.catalog_notebook.add(self.catalog_overview_tab, text='Overview')
        self.catalog_notebook.add(self.catalog_endpoints_tab, text='Endpoints')
        self.catalog_notebook.add(self.catalog_dependencies_tab, text='Dependencies')
        self.catalog_notebook.add(self.catalog_source_tab, text='Source')
        self.catalog_notebook.add(self.catalog_raw_json_tab, text='Raw JSON')
        self.catalog_overview_text = self._create_readonly_text(self.catalog_overview_tab)
        self.catalog_endpoints_text = self._create_readonly_text(self.catalog_endpoints_tab)
        self.catalog_dependencies_text = self._create_readonly_text(self.catalog_dependencies_tab)
        self.catalog_source_text = self._create_readonly_text(self.catalog_source_tab)
        self.catalog_raw_json_text = self._create_readonly_text(self.catalog_raw_json_tab)

        results_frame = ttk.LabelFrame(right, text='Results', padding=8)
        results_frame.pack(fill='both', expand=True)
        self.catalog_results_text = self._create_readonly_text(results_frame, height=10)
        self._clear_catalog_inspector()

    def _build_manifest_tab(self) -> None:
        container = ttk.Frame(self.manifest_tab, padding=8)
        container.pack(fill='both', expand=True)
        controls = ttk.Frame(container)
        controls.pack(fill='x')
        ttk.Label(controls, text='Template').grid(row=0, column=0, sticky='w', padx=4, pady=4)
        self.template_options = self.query_service.list_templates()
        self.template_label_to_id = {
            f"{template['template_id']} :: {template['name']}": template['template_id']
            for template in self.template_options
        }
        self.template_var = tk.StringVar(value=next(iter(self.template_label_to_id.keys()), ''))
        self.template_combo = ttk.Combobox(
            controls,
            textvariable=self.template_var,
            state='readonly',
            values=list(self.template_label_to_id.keys()),
        )
        self.template_combo.grid(row=0, column=1, sticky='ew', padx=4, pady=4)
        ttk.Button(controls, text='Load Template', command=self._load_selected_template, style='Secondary.TButton').grid(row=0, column=2, sticky='ew', padx=4, pady=4)
        ttk.Button(controls, text='Stamp Template', command=self._stamp_selected_template, style='Accent.TButton').grid(row=0, column=3, sticky='ew', padx=4, pady=4)
        ttk.Label(controls, text='App Name').grid(row=1, column=0, sticky='w', padx=4, pady=4)
        self.app_name_var = tk.StringVar(value='Stamped App')
        ttk.Entry(controls, textvariable=self.app_name_var, width=40).grid(row=1, column=1, sticky='ew', padx=4, pady=4)
        ttk.Label(controls, text='Destination').grid(row=2, column=0, sticky='w', padx=4, pady=4)
        self.destination_var = tk.StringVar(value=str(Path.cwd() / 'stamped_app'))
        ttk.Entry(controls, textvariable=self.destination_var, width=60).grid(row=2, column=1, sticky='ew', padx=4, pady=4)
        ttk.Button(controls, text='Browse', command=self._browse_destination, style='Secondary.TButton').grid(row=2, column=2, sticky='ew', padx=4, pady=4)
        ttk.Label(controls, text='Vendor Mode').grid(row=3, column=0, sticky='w', padx=4, pady=4)
        self.vendor_mode_var = tk.StringVar(value='module_ref')
        ttk.Combobox(controls, textvariable=self.vendor_mode_var, state='readonly', values=['module_ref', 'static']).grid(row=3, column=1, sticky='ew', padx=4, pady=4)
        ttk.Label(controls, text='Resolution').grid(row=4, column=0, sticky='w', padx=4, pady=4)
        self.resolution_var = tk.StringVar(value='app_ready')
        ttk.Combobox(controls, textvariable=self.resolution_var, state='readonly', values=['app_ready', 'strict', 'explicit_pack']).grid(row=4, column=1, sticky='ew', padx=4, pady=4)
        controls.columnconfigure(1, weight=1)
        editors = ttk.PanedWindow(container, orient=tk.HORIZONTAL)
        editors.pack(fill='both', expand=True, pady=8)
        manifest_frame = ttk.Frame(editors)
        schema_frame = ttk.Frame(editors)
        editors.add(manifest_frame, weight=3)
        editors.add(schema_frame, weight=2)
        ttk.Label(manifest_frame, text='app_manifest.json').pack(anchor='w')
        self.manifest_text = tk.Text(manifest_frame, wrap='word')
        self._apply_text_theme(self.manifest_text)
        self.manifest_text.pack(fill='both', expand=True)
        ttk.Label(schema_frame, text='ui_schema.json').pack(anchor='w')
        self.schema_text = tk.Text(schema_frame, wrap='word')
        self._apply_text_theme(self.schema_text)
        self.schema_text.pack(fill='both', expand=True)
        actions = ttk.Frame(container)
        actions.pack(fill='x')
        ttk.Button(actions, text='Load Destination App', command=self._load_destination_app).pack(side='left', padx=4)
        ttk.Button(actions, text='Inspect Destination App', command=self._inspect_destination_app).pack(side='left', padx=4)
        ttk.Button(actions, text='Upgrade Report', command=self._upgrade_report).pack(side='left', padx=4)
        ttk.Button(actions, text='Preview Schema', command=self._preview_schema).pack(side='left', padx=4)
        ttk.Button(actions, text='Validate Manifest', command=self._validate_manifest, style='Secondary.TButton').pack(side='left', padx=4)
        ttk.Button(actions, text='Commit Schema To Destination', command=self._commit_schema).pack(side='left', padx=4)
        ttk.Button(actions, text='Restamp Existing App', command=self._restamp_existing_app, style='Accent.TButton').pack(side='right', padx=4)
        ttk.Button(actions, text='Stamp App', command=self._stamp_manifest, style='Accent.TButton').pack(side='right', padx=4)
        manifest_results = ttk.LabelFrame(container, text='Results', padding=8)
        manifest_results.pack(fill='both', expand=True, pady=(8, 0))
        self.details_text = tk.Text(manifest_results, wrap='word', height=12)
        self._apply_text_theme(self.details_text)
        self.details_text.pack(fill='both', expand=True)

    def _build_assistant_tab(self) -> None:
        container = ttk.Frame(self.assistant_tab, padding=8)
        container.pack(fill='both', expand=True)
        row = ttk.Frame(container)
        row.pack(fill='x')
        ttk.Label(row, text='Model').pack(side='left', padx=4)
        self.model_var = tk.StringVar(value='')
        self.model_combo = ttk.Combobox(row, textvariable=self.model_var, state='readonly')
        self.model_combo.pack(side='left', fill='x', expand=True, padx=4)
        self.model_combo.bind('<<ComboboxSelected>>', lambda *_: self._update_assistant_model_state())
        ttk.Label(row, text='Size Cap (B)').pack(side='left', padx=4)
        self.size_cap_var = tk.StringVar(value='4')
        ttk.Entry(row, textvariable=self.size_cap_var, width=8).pack(side='left', padx=4)
        ttk.Button(row, text='Refresh Models', command=self._refresh_models, style='Secondary.TButton').pack(side='left', padx=4)
        summarize_button = ttk.Button(row, text='Summarize Selected Service', command=self._assistant_summarize)
        summarize_button.pack(side='left', padx=4)
        schema_button = ttk.Button(row, text='Suggest UI Schema', command=self._assistant_schema, style='Accent.TButton')
        schema_button.pack(side='left', padx=4)
        self.assistant_requires_model = [summarize_button, schema_button]
        self.assistant_model_status_var = tk.StringVar(value='No model loaded. Refresh models to enable inference.')
        ttk.Label(container, textvariable=self.assistant_model_status_var, foreground=THEME['muted_text']).pack(anchor='w', pady=(8, 0))
        self.assistant_text = tk.Text(container, wrap='word')
        self._apply_text_theme(self.assistant_text)
        self.assistant_text.pack(fill='both', expand=True, pady=8)
        self._set_text_content(
            self.assistant_text,
            'Deterministic explanations are available from the Catalog tab. Load a model here to enable inference features.',
        )
        self._update_assistant_model_state()

    def _build_packs_tab(self) -> None:
        container = ttk.Frame(self.packs_tab, padding=8)
        container.pack(fill='both', expand=True)
        row = ttk.Frame(container)
        row.pack(fill='x')
        ttk.Label(row, text='Pack Source').pack(side='left', padx=4)
        self.pack_source_var = tk.StringVar(value='')
        ttk.Entry(row, textvariable=self.pack_source_var).pack(side='left', fill='x', expand=True, padx=4)
        ttk.Button(row, text='Browse', command=self._browse_pack_source, style='Secondary.TButton').pack(side='left', padx=4)
        ttk.Button(row, text='Install Pack', command=self._install_pack, style='Accent.TButton').pack(side='left', padx=4)
        self.pack_text = tk.Text(container, wrap='word')
        self._apply_text_theme(self.pack_text)
        self.pack_text.pack(fill='both', expand=True, pady=8)

    def _refresh_services(self) -> None:
        layers = ['all'] + self.query_service.list_layers()
        self.layer_combo['values'] = layers
        if self.layer_var.get() not in layers:
            self.layer_var.set('all')
        layer = None if self.layer_var.get() == 'all' else self.layer_var.get()
        services = self.query_service.list_services(layer=layer)
        self.current_services = services
        self.service_list.delete(0, tk.END)
        for service in services:
            self.service_list.insert(tk.END, f"{service['layer']} :: {service['class_name']}")
        self._clear_catalog_inspector()

    def _selected_service_objects(self) -> List[Dict[str, Any]]:
        return [self.current_services[index] for index in self.service_list.curselection()]

    def _show_selected_service(self) -> None:
        selected = self._selected_service_objects()
        if not selected:
            self._clear_catalog_inspector()
            return
        payload = self.query_service.describe_service(selected[0]['class_name'])
        if not payload:
            self._clear_catalog_inspector()
            return
        self.catalog_service_payload = payload
        self.catalog_dependency_payload = payload.get('dependencies')
        self._populate_catalog_inspector(payload)

    def _show_selected_dependencies(self) -> None:
        selected = self._selected_service_objects()
        if not selected:
            return
        payload = self.query_service.show_dependencies(selected[0]['class_name'])
        self.catalog_dependency_payload = payload
        if self.catalog_service_payload is not None:
            self._populate_catalog_inspector(self.catalog_service_payload)
        self.catalog_notebook.select(self.catalog_dependencies_tab)
        self._write_catalog_result('Dependency Report', payload)

    def _list_ui_components(self) -> None:
        payload = self.query_service.show_ui_components()
        self._write_catalog_result('UI Components', payload)

    def _list_orchestrators(self) -> None:
        payload = self.query_service.list_orchestrators()
        self._write_catalog_result('Orchestrators', payload)

    def _list_managers(self) -> None:
        payload = self.query_service.list_managers()
        self._write_catalog_result('Managers', payload)

    def _rebuild_catalog(self) -> None:
        payload = self.query_service.build_catalog(incremental=True)
        self._refresh_services()
        self._write_catalog_result('Catalog Rebuild', payload)

    def _recommend_blueprint(self) -> None:
        selected = [service['class_name'] for service in self._selected_service_objects()]
        payload = self.query_service.recommend_blueprint(
            selected,
            destination=self.destination_var.get(),
            name=self.app_name_var.get(),
            vendor_mode=self.vendor_mode_var.get(),
            resolution_profile=self.resolution_var.get(),
        )
        self.manifest_text.delete('1.0', tk.END)
        self.manifest_text.insert(tk.END, json.dumps({key: value for key, value in payload.items() if key != 'selected_services'}, indent=2))
        schema = self.ui_preview.default_schema(payload.get('ui_pack', 'headless_pack'))
        self.schema_text.delete('1.0', tk.END)
        self.schema_text.insert(tk.END, json.dumps(schema, indent=2))
        self._write_catalog_result('Recommended Blueprint', payload)

    def _create_readonly_text(self, parent: tk.Widget, height: int=12) -> tk.Text:
        widget = tk.Text(parent, wrap='word', height=height)
        self._apply_text_theme(widget)
        widget.pack(fill='both', expand=True)
        widget.configure(state='disabled')
        return widget

    def _set_readonly_text(self, widget: tk.Text, content: str) -> None:
        widget.configure(state='normal')
        widget.delete('1.0', tk.END)
        widget.insert(tk.END, content)
        widget.configure(state='disabled')

    def _clear_catalog_inspector(self) -> None:
        self.catalog_service_payload = None
        self.catalog_dependency_payload = None
        for variable in self.catalog_summary_vars.values():
            variable.set('-')
        empty_message = 'Select a service from the left-hand list to inspect it.'
        self._set_readonly_text(self.catalog_overview_text, empty_message)
        self._set_readonly_text(self.catalog_endpoints_text, empty_message)
        self._set_readonly_text(self.catalog_dependencies_text, empty_message)
        self._set_readonly_text(self.catalog_source_text, empty_message)
        self._set_readonly_text(self.catalog_raw_json_text, empty_message)
        self._set_readonly_text(
            self.catalog_results_text,
            'Action results appear here. Selection details stay in the tabs above.',
        )

    def _populate_catalog_inspector(self, payload: Dict[str, Any]) -> None:
        dependencies = self.catalog_dependency_payload or payload.get('dependencies') or {}
        self.catalog_dependency_payload = dependencies
        counts = self._dependency_counts(dependencies)
        self.catalog_summary_vars['display_name'].set(payload.get('service_name') or payload.get('class_name', '-'))
        self.catalog_summary_vars['class_name'].set(payload.get('class_name', '-'))
        self.catalog_summary_vars['layer'].set(payload.get('layer', '-'))
        self.catalog_summary_vars['version'].set(payload.get('version', '-'))
        self.catalog_summary_vars['ui_status'].set('Yes' if self._is_ui_service(payload) else 'No')
        self.catalog_summary_vars['endpoint_count'].set(str(len(payload.get('endpoints', []))))
        self.catalog_summary_vars['dependency_count'].set(
            f"code {counts['code']} | runtime {counts['runtime']} | external {counts['external']}"
        )
        self.catalog_summary_vars['tags'].set(', '.join(payload.get('tags', [])) or '-')
        self.catalog_summary_vars['capabilities'].set(', '.join(payload.get('capabilities', [])) or '-')
        self.catalog_summary_vars['import_key'].set(payload.get('import_key', '-'))
        self.catalog_summary_vars['source_path'].set(payload.get('source_path', '-'))
        self._set_readonly_text(self.catalog_overview_text, self._format_service_overview(payload, dependencies))
        self._set_readonly_text(self.catalog_endpoints_text, self._format_endpoints(payload.get('endpoints', [])))
        self._set_readonly_text(self.catalog_dependencies_text, self._format_dependencies(dependencies))
        self._set_readonly_text(self.catalog_source_text, self._format_source_preview(payload))
        self._set_readonly_text(self.catalog_raw_json_text, json.dumps(payload, indent=2))

    def _dependency_counts(self, dependencies: Dict[str, Any] | None) -> Dict[str, int]:
        payload = dependencies or {}
        return {
            'code': len(payload.get('code_dependencies', [])),
            'runtime': len(payload.get('runtime_dependencies', [])),
            'external': len(payload.get('external_dependencies', [])),
        }

    def _is_ui_service(self, payload: Dict[str, Any]) -> bool:
        return payload.get('layer') == 'ui' or 'ui' in payload.get('tags', []) or any(
            str(capability).startswith('ui:') for capability in payload.get('capabilities', [])
        )

    def _format_service_overview(self, payload: Dict[str, Any], dependencies: Dict[str, Any] | None) -> str:
        counts = self._dependency_counts(dependencies)
        lines = [
            f"Name: {payload.get('service_name') or payload.get('class_name', '-')}",
            f"Class: {payload.get('class_name', '-')}",
            f"Layer: {payload.get('layer', '-')}",
            f"Version: {payload.get('version', '-')}",
            f"UI Service: {'Yes' if self._is_ui_service(payload) else 'No'}",
            '',
            'Purpose',
            '-------',
            payload.get('description') or 'No description recorded.',
            '',
            'Capabilities',
            '------------',
            ', '.join(payload.get('capabilities', [])) or 'None recorded.',
            '',
            'Side Effects',
            '------------',
            ', '.join(payload.get('side_effects', [])) or 'None recorded.',
            '',
            'Dependency Summary',
            '------------------',
            f"Code: {counts['code']}",
            f"Runtime: {counts['runtime']}",
            f"External: {counts['external']}",
        ]
        return '\n'.join(lines)

    def _format_endpoints(self, endpoints: List[Dict[str, Any]]) -> str:
        if not endpoints:
            return 'No endpoints recorded.'
        blocks: List[str] = []
        for endpoint in endpoints:
            blocks.append(
                '\n'.join(
                    [
                        endpoint.get('method_name', '(unknown endpoint)'),
                        f"  Mode: {endpoint.get('mode', '-')}",
                        f"  Inputs: {endpoint.get('inputs_json', '{}')}",
                        f"  Outputs: {endpoint.get('outputs_json', '{}')}",
                        f"  Tags: {endpoint.get('tags_json', '[]')}",
                        f"  Description: {endpoint.get('description', '') or 'No description recorded.'}",
                    ]
                )
            )
        return '\n\n'.join(blocks)

    def _format_dependencies(self, dependencies: Dict[str, Any] | None) -> str:
        if not dependencies:
            return 'No dependency data recorded.'
        sections = [
            ('Code Dependencies', dependencies.get('code_dependencies', [])),
            ('Runtime Dependencies', dependencies.get('runtime_dependencies', [])),
            ('External Dependencies', dependencies.get('external_dependencies', [])),
        ]
        lines: List[str] = []
        for title, items in sections:
            lines.append(title)
            lines.append('-' * len(title))
            if not items:
                lines.append('None.')
            else:
                for item in items:
                    target = item.get('target') or item.get('target_import_key') or '(unresolved)'
                    evidence = item.get('evidence_type', '-')
                    source_path = item.get('target_source_path') or ''
                    lines.append(f"- {target}")
                    lines.append(f"  evidence: {evidence}")
                    if source_path:
                        lines.append(f"  source: {source_path}")
            lines.append('')
        return '\n'.join(lines).strip()

    def _format_source_preview(self, payload: Dict[str, Any]) -> str:
        source_path = Path(str(payload.get('source_path', '')).strip())
        lines = [
            f"Import Key: {payload.get('import_key', '-')}",
            f"Source Path: {source_path if source_path else '-'}",
            '',
        ]
        if not source_path or not source_path.exists():
            lines.append('Source preview unavailable.')
            return '\n'.join(lines)
        try:
            source_text = source_path.read_text(encoding='utf-8')
        except UnicodeDecodeError:
            source_text = source_path.read_text(encoding='utf-8', errors='replace')
        source_lines = source_text.splitlines()
        preview_limit = 80
        preview = source_lines[:preview_limit]
        lines.append('Preview')
        lines.append('-------')
        lines.extend(f'{index + 1:>4}: {line}' for index, line in enumerate(preview))
        if len(source_lines) > preview_limit:
            lines.append('')
            lines.append(f'... truncated after {preview_limit} lines')
        return '\n'.join(lines)

    def _write_catalog_result(self, title: str, payload: Any) -> None:
        if isinstance(payload, str):
            body = payload
        else:
            body = json.dumps(payload, indent=2)
        content = f'{title}\n{"=" * len(title)}\n{body}'
        self._set_readonly_text(self.catalog_results_text, content)

    def _show_service_context_menu(self, event: tk.Event) -> None:
        if self.service_list.size() == 0:
            return
        index = self.service_list.nearest(event.y)
        if index < 0:
            return
        self.service_list.selection_clear(0, tk.END)
        self.service_list.selection_set(index)
        self.service_list.activate(index)
        self._show_selected_service()
        try:
            self.catalog_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.catalog_context_menu.grab_release()

    def _resolve_assistant_model(self) -> str:
        return self.model_var.get().strip()

    def _update_assistant_model_state(self) -> None:
        model_name = self.model_var.get().strip()
        enabled = bool(model_name)
        for button in self.assistant_requires_model:
            if enabled:
                button.state(['!disabled'])
            else:
                button.state(['disabled'])
        if hasattr(self, 'assistant_model_status_var'):
            if enabled:
                self.assistant_model_status_var.set(f'Model loaded: {model_name}')
            else:
                self.assistant_model_status_var.set('No model loaded. Refresh models to enable inference.')

    def _deterministic_service_explanation(self, payload: Dict[str, Any], dependencies: Dict[str, Any] | None) -> str:
        counts = self._dependency_counts(dependencies)
        endpoint_names = [endpoint.get('method_name', '-') for endpoint in payload.get('endpoints', [])]
        lines = [
            f"{payload.get('service_name') or payload.get('class_name', 'This service')} is a {payload.get('layer', 'general')} microservice.",
            payload.get('description') or 'No description recorded.',
            '',
            f"Version: {payload.get('version', '-')}",
            f"Primary endpoints: {', '.join(endpoint_names) if endpoint_names else 'none recorded'}",
            f"Capabilities: {', '.join(payload.get('capabilities', [])) or 'none recorded'}",
            f"Code dependencies: {counts['code']}",
            f"Runtime dependencies: {counts['runtime']}",
            f"External dependencies: {counts['external']}",
        ]
        if payload.get('tags'):
            lines.append(f"Tags: {', '.join(payload.get('tags', []))}")
        if payload.get('side_effects'):
            lines.append(f"Side effects: {', '.join(payload.get('side_effects', []))}")
        return '\n'.join(lines)

    def _explain_selected_service(self) -> None:
        selected = self._selected_service_objects()
        if not selected:
            messagebox.showwarning('Explain Selected Service', 'Select a service first.')
            return
        payload = self.query_service.describe_service(selected[0]['class_name'])
        if not payload:
            messagebox.showwarning('Explain Selected Service', 'Could not resolve the selected service.')
            return
        self.catalog_service_payload = payload
        self.catalog_dependency_payload = payload.get('dependencies') or self.query_service.show_dependencies(selected[0]['class_name'])
        self._populate_catalog_inspector(payload)
        fallback = self._deterministic_service_explanation(payload, self.catalog_dependency_payload)
        model_name = self._resolve_assistant_model()
        if model_name:
            pending = f'Running {model_name} on the selected service...'
            self._set_text_content(self.assistant_text, pending)
            self._write_catalog_result('Assistant Summary', pending)

            def _worker():
                return self.assistant.summarize_service(model_name, payload)

            def _on_success(result):
                final_output = fallback
                title = 'Service Explanation'
                if result.get('ok') and result.get('output', '').strip():
                    final_output = result['output']
                    title = f'Assistant Summary ({model_name})'
                else:
                    failure_note = result.get('error', '').strip() or 'Assistant response was empty.'
                    final_output = f'Assistant fallback reason: {failure_note}\n\n{fallback}'
                self._set_text_content(self.assistant_text, final_output)
                self._write_catalog_result(title, final_output)

            self._run_background_action(_worker, _on_success, f'Inferring with {model_name}...')
            return
        self._set_text_content(self.assistant_text, fallback)
        self._write_catalog_result('Service Explanation', fallback)

    def _load_selected_template(self) -> None:
        try:
            label = self.template_var.get().strip()
            template_id = self.template_label_to_id.get(label, '')
            if not template_id:
                messagebox.showwarning('Load Template', 'Select a template first.')
                return
            payload = self.query_service.template_blueprint(
                template_id,
                destination=self.destination_var.get(),
                name=self.app_name_var.get(),
                vendor_mode=self.vendor_mode_var.get(),
                resolution_profile=self.resolution_var.get(),
            )
            self.app_name_var.set(payload.get('name', self.app_name_var.get()))
            self.vendor_mode_var.set(payload.get('vendor_mode', self.vendor_mode_var.get()))
            self.resolution_var.set(payload.get('resolution_profile', self.resolution_var.get()))
            self.manifest_text.delete('1.0', tk.END)
            self.manifest_text.insert(tk.END, json.dumps({key: value for key, value in payload.items() if key != 'selected_services'}, indent=2))
            schema = self.ui_preview.default_schema(payload.get('ui_pack', 'headless_pack'))
            self.schema_text.delete('1.0', tk.END)
            self.schema_text.insert(tk.END, json.dumps(schema, indent=2))
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert(tk.END, json.dumps(payload, indent=2))
        except Exception as exc:
            messagebox.showerror('Load Template', str(exc))

    def _stamp_selected_template(self) -> None:
        try:
            label = self.template_var.get().strip()
            template_id = self.template_label_to_id.get(label, '')
            if not template_id:
                messagebox.showwarning('Stamp Template', 'Select a template first.')
                return
            payload = self.query_service.template_blueprint(
                template_id,
                destination=self.destination_var.get(),
                name=self.app_name_var.get(),
                vendor_mode=self.vendor_mode_var.get(),
                resolution_profile=self.resolution_var.get(),
            )
            report = self.stamper.stamp(payload)
            self.manifest_text.delete('1.0', tk.END)
            self.manifest_text.insert(tk.END, json.dumps({key: value for key, value in payload.items() if key != 'selected_services'}, indent=2))
            schema = self.ui_preview.default_schema(payload.get('ui_pack', 'headless_pack'))
            self.schema_text.delete('1.0', tk.END)
            self.schema_text.insert(tk.END, json.dumps(schema, indent=2))
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert(tk.END, json.dumps(report, indent=2))
            if report['validation']['ok']:
                messagebox.showinfo('Stamp Template', f"Stamped app at {report['app_dir']}")
            else:
                messagebox.showwarning('Stamp Template', 'Stamp completed with validation errors. See details.')
        except Exception as exc:
            messagebox.showerror('Stamp Template', str(exc))

    def _browse_destination(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.destination_var.get() or str(Path.cwd()))
        if selected:
            self.destination_var.set(selected)

    def _preview_schema(self) -> None:
        try:
            schema = json.loads(self.schema_text.get('1.0', tk.END).strip())
            self.ui_preview.render_preview(self.root, schema)
        except Exception as exc:
            messagebox.showerror('Preview Schema', str(exc))

    def _load_destination_app(self) -> None:
        try:
            app_dir = Path(self.destination_var.get()).resolve()
            manifest = self.stamper.load_app_manifest(app_dir)
            self.app_name_var.set(manifest.get('name', self.app_name_var.get()))
            self.vendor_mode_var.set(manifest.get('vendor_mode', self.vendor_mode_var.get()))
            self.resolution_var.set(manifest.get('resolution_profile', self.resolution_var.get()))
            self.manifest_text.delete('1.0', tk.END)
            self.manifest_text.insert(tk.END, json.dumps(manifest, indent=2))
            schema_path = app_dir / 'ui_schema.json'
            if schema_path.exists():
                schema = json.loads(schema_path.read_text(encoding='utf-8'))
                self.schema_text.delete('1.0', tk.END)
                self.schema_text.insert(tk.END, json.dumps(schema, indent=2))
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert(tk.END, json.dumps({'loaded_app_dir': str(app_dir), 'manifest': manifest}, indent=2))
        except Exception as exc:
            messagebox.showerror('Load Destination App', str(exc))

    def _inspect_destination_app(self) -> None:
        try:
            report = self.stamper.inspect_app(Path(self.destination_var.get()))
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert(tk.END, json.dumps(report, indent=2))
            if report['errors']:
                messagebox.showwarning('Inspect Destination App', 'Inspection found issues. See details.')
            else:
                messagebox.showinfo('Inspect Destination App', 'Inspection completed.')
        except Exception as exc:
            messagebox.showerror('Inspect Destination App', str(exc))

    def _upgrade_report(self) -> None:
        try:
            report = self.stamper.upgrade_report(Path(self.destination_var.get()))
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert(tk.END, json.dumps(report, indent=2))
            if report['inspection']['errors']:
                messagebox.showwarning('Upgrade Report', 'Upgrade report found blocking issues. See details.')
            elif report['upgrade_recommended']:
                messagebox.showinfo('Upgrade Report', 'Differences found. Review the report before restamping.')
            else:
                messagebox.showinfo('Upgrade Report', 'No upgrade changes detected.')
        except Exception as exc:
            messagebox.showerror('Upgrade Report', str(exc))

    def _commit_schema(self) -> None:
        try:
            schema = json.loads(self.schema_text.get('1.0', tk.END).strip())
            target = self.ui_commit.commit(schema, Path(self.destination_var.get()))
            messagebox.showinfo('Commit Schema', f'Wrote {target}')
        except Exception as exc:
            messagebox.showerror('Commit Schema', str(exc))

    def _stamp_manifest(self) -> None:
        try:
            payload = json.loads(self.manifest_text.get('1.0', tk.END).strip())
            payload['destination'] = self.destination_var.get()
            payload['name'] = self.app_name_var.get()
            payload['vendor_mode'] = self.vendor_mode_var.get()
            payload['resolution_profile'] = self.resolution_var.get()
            validation = self.query_service.validate_manifest(payload)
            if not validation['ok']:
                self.details_text.delete('1.0', tk.END)
                self.details_text.insert(tk.END, json.dumps(validation, indent=2))
                messagebox.showwarning('Stamp App', 'Manifest validation failed. See details.')
                return
            report = self.stamper.stamp(payload)
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert(tk.END, json.dumps(report, indent=2))
            if report['validation']['ok']:
                messagebox.showinfo('Stamp App', f"Stamped app at {report['app_dir']}")
            else:
                messagebox.showwarning('Stamp App', 'Stamp completed with validation errors. See details.')
        except Exception as exc:
            messagebox.showerror('Stamp App', str(exc))

    def _validate_manifest(self) -> None:
        try:
            payload = json.loads(self.manifest_text.get('1.0', tk.END).strip())
            payload['destination'] = self.destination_var.get()
            payload['name'] = self.app_name_var.get()
            payload['vendor_mode'] = self.vendor_mode_var.get()
            payload['resolution_profile'] = self.resolution_var.get()
            report = self.query_service.validate_manifest(payload)
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert(tk.END, json.dumps(report, indent=2))
            if report['ok']:
                messagebox.showinfo('Validate Manifest', 'Manifest validation passed.')
            else:
                messagebox.showwarning('Validate Manifest', 'Manifest validation failed. See details.')
        except Exception as exc:
            messagebox.showerror('Validate Manifest', str(exc))

    def _restamp_existing_app(self) -> None:
        try:
            report = self.stamper.restamp_existing_app(
                Path(self.destination_var.get()),
                preserve_ui_schema=True,
            )
            self.details_text.delete('1.0', tk.END)
            self.details_text.insert(tk.END, json.dumps(report, indent=2))
            if report['validation']['ok']:
                messagebox.showinfo('Restamp Existing App', f"Restamped app at {report['app_dir']}")
            else:
                messagebox.showwarning('Restamp Existing App', 'Restamp completed with validation errors. See details.')
        except Exception as exc:
            messagebox.showerror('Restamp Existing App', str(exc))

    def _refresh_models(self) -> None:
        try:
            cap = float(self.size_cap_var.get())
        except ValueError:
            cap = 4.0
        models = self.assistant.list_models()
        model_names = [model['name'] for model in models]
        self.model_combo['values'] = model_names
        current = self.model_var.get().strip()
        default = self.assistant.choose_default_model(cap) if models else None
        if current and current in model_names:
            self.model_var.set(current)
        elif default:
            self.model_var.set(default)
        else:
            self.model_var.set('')
        self._update_assistant_model_state()
        if models:
            self._set_text_content(self.assistant_text, json.dumps(models, indent=2))
        else:
            self._set_text_content(
                self.assistant_text,
                'No Ollama models detected. Start Ollama, install a local model, then click Refresh Models.',
            )

    def _assistant_summarize(self) -> None:
        if not self._resolve_assistant_model():
            messagebox.showwarning('Assistant', 'Load and select an Ollama model first.')
            return
        self._explain_selected_service()

    def _assistant_schema(self) -> None:
        model_name = self.model_var.get().strip()
        if not model_name:
            messagebox.showwarning('Assistant', 'Select an Ollama model first.')
            return
        try:
            schema = json.loads(self.schema_text.get('1.0', tk.END).strip())
        except Exception as exc:
            messagebox.showerror('Assistant', str(exc))
            return
        pending = f'Generating a schema suggestion with {model_name}...'
        self._set_text_content(self.assistant_text, pending)
        self._write_catalog_result('Assistant Schema Suggestion', pending)

        def _worker():
            return self.assistant.suggest_ui_schema(model_name, schema, 'Improve clarity and usability for a stamped Tkinter app.')

        def _on_success(result):
            formatted = json.dumps(result, indent=2)
            self._set_text_content(self.assistant_text, formatted)
            self._write_catalog_result('Assistant Schema Suggestion', formatted)

        self._run_background_action(_worker, _on_success, f'Generating UI schema with {model_name}...')

    def _browse_pack_source(self) -> None:
        selected = filedialog.askopenfilename(title='Select pack zip or folder')
        if not selected:
            selected = filedialog.askdirectory(title='Select pack folder')
        if selected:
            self.pack_source_var.set(selected)

    def _install_pack(self) -> None:
        source = self.pack_source_var.get().strip()
        if not source:
            return
        try:
            report = self.pack_manager.install(source)
            self.pack_text.delete('1.0', tk.END)
            self.pack_text.insert(tk.END, json.dumps(report, indent=2))
            self._refresh_services()
        except Exception as exc:
            messagebox.showerror('Install Pack', str(exc))

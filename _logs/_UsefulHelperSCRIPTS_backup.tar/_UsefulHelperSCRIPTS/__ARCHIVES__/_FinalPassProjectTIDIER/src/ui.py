"""
PROJECT: _UsefulHelperSCRIPTS - Project Tidier
ROLE: UI Orchestrator (Pure Tkinter Edition)
"""
import tkinter as tk
from tkinter import ttk
import os

# Internal Microservice Imports
from _TkinterAppShellMS import TkinterAppShellMS
from _ExplorerWidgetMS import ExplorerWidgetMS
from _LogViewMS import LogViewMS
from _OllamaModelSelectorMS import OllamaModelSelectorMS
from _TkinterThemeManagerMS import TkinterThemeManagerMS
from _ThoughtStreamMS import ThoughtStreamMS

class ProjectTidierUI:
    """
    Manages the layout of the Project Tidier interface using standard Tkinter widgets.
    """
    def __init__(self, signal_bus, state, telemetry):
        self.bus = signal_bus
        self.state = state
        self.telemetry = telemetry
        
        # 1. Initialize the AppShell container
        self.theme_mgr = TkinterThemeManagerMS()
        self.shell = TkinterAppShellMS({
            'title': 'Project Tidier | Pure Tkinter',
            'theme_manager': self.theme_mgr,
            'geometry': '1400x900'
        })
        
        self.container = self.shell.get_main_container()
        self.colors = self.theme_mgr.get_theme()
        
        self._setup_layout()

    def _setup_layout(self):
        # --- Top Toolbar (Model Selection & Launch) ---
        self.top_bar = tk.Frame(self.container, bg=self.colors['panel_bg'], height=50)
        self.top_bar.pack(side='top', fill='x', pady=(0, 5))
        
        # Check for persisted model selection
        self.bus.subscribe("config_loaded", lambda d: self.model_selector.set_selected_model(d.get('last_model')))
        
        self.model_selector = OllamaModelSelectorMS({
            'parent': self.top_bar,
            'bg': self.colors['panel_bg'],
            'on_change': lambda m: self.bus.emit("model_swapped", m)
        })
        self.model_selector.pack(side='left', padx=10)
        
        self.tidy_btn = tk.Button(
            self.top_bar, text="🚀 START TIDY", 
            command=self._on_tidy_click,
            bg=self.colors['accent'], fg='white', relief='flat', padx=20
        )
        self.tidy_btn.pack(side='right', padx=10, pady=5)

        # --- Paned Workspace (Explorer + Review) ---
        self.workspace = ttk.PanedWindow(self.container, orient='horizontal')
        self.workspace.pack(fill='both', expand=True)

        # Left Sidebar (Project Explorer)
        self.explorer_frame = tk.Frame(self.workspace)
        self.explorer = ExplorerWidgetMS({
            'parent': self.explorer_frame,
            'root_path': os.getcwd()
        })
        self.explorer.pack(fill='both', expand=True)
        self.workspace.add(self.explorer_frame, weight=1)

        # Center Stage (Review Pane)
        self.review_stage = tk.Frame(self.workspace, bg=self.colors['background'])
        self._setup_review_pane()
        self.workspace.add(self.review_stage, weight=4)

        # Right Panel (Neural Inspector)
        self.neural_inspector = ThoughtStreamMS({'parent': self.workspace})
        self.workspace.add(self.neural_inspector, weight=2)

        # --- Bottom Panel (Log Telemetry) ---
        self.log_panel = tk.Frame(self.container, height=200)
        self.log_panel.pack(side='bottom', fill='x', pady=(5, 0))
        
        self.console = LogViewMS({'parent': self.log_panel})
        self.console.pack(fill='both', expand=True)

    def _setup_review_pane(self):
        """Standard side-by-side text widgets for reviewing AI changes."""
        self.review_label = tk.Label(self.review_stage, text="Review Hunk: Waiting...", bg=self.colors['background'], fg=self.colors['foreground'])
        self.review_label.pack(pady=5)

        self.diff_container = tk.Frame(self.review_stage, bg=self.colors['background'])
        self.diff_container.pack(fill='both', expand=True, padx=10, pady=5)

        # Pure Tkinter Text Widgets for Original vs. Cleaned
        self.before_txt = tk.Text(self.diff_container, bg='#1e1e1e', fg='#d4d4d4', font=('Consolas', 10))
        self.after_txt = tk.Text(self.diff_container, bg='#1e1e1e', fg='#d4d4d4', font=('Consolas', 10))
        self.before_txt.pack(side='left', fill='both', expand=True, padx=5)
        self.after_txt.pack(side='left', fill='both', expand=True, padx=5)

        # Approval Buttons
        self.btn_frame = tk.Frame(self.review_stage, bg=self.colors['background'])
        self.btn_frame.pack(side='bottom', fill='x', pady=10)
        
        self.approve_btn = tk.Button(self.btn_frame, text="✅ APPROVE", state='disabled', 
                                    command=self._on_approve_click,
                                    bg=self.colors['success'], fg='white', width=15)
        self.approve_btn.pack(side='right', padx=10)

        self.skip_btn = tk.Button(self.btn_frame, text="❌ SKIP", state='disabled', 
                                 command=self._on_skip_click,
                                 bg='#cc3333', fg='white', width=15)
        self.skip_btn.pack(side='right', padx=10)

        # --- Prompt Config Section ---
        self.prompt_frame = tk.LabelFrame(self.review_stage, text="Prompt Configuration (JSON)", 
                                         bg=self.colors['background'], fg=self.colors['foreground'])
        self.prompt_frame.pack(side='bottom', fill='x', padx=10, pady=10)
        
        self.prompt_text = tk.Text(self.prompt_frame, height=6, bg='#1e1e1e', fg='#ce9178', font=('Consolas', 9))
        self.prompt_text.pack(fill='x', padx=5, pady=5)
        
        self.prompt_apply_btn = tk.Button(self.prompt_frame, text="APPLY TEMPLATE", 
                                         command=self._on_apply_prompt_click, 
                                         bg=self.colors['accent'], fg='white')
        self.prompt_apply_btn.pack(side='right', padx=5, pady=2)

        # --- Rules / Tasklist Section ---
        self.rules_frame = tk.LabelFrame(self.review_stage, text="Rules & Constraints (JSON)", 
                                        bg=self.colors['background'], fg=self.colors['foreground'])
        self.rules_frame.pack(side='bottom', fill='x', padx=10, pady=10)

        self.rules_text = tk.Text(self.rules_frame, height=6, bg='#1e1e1e', fg='#ce9178', font=('Consolas', 9))
        self.rules_text.pack(fill='x', padx=5, pady=5)

        self.rules_apply_btn = tk.Button(self.rules_frame, text="APPLY RULES", 
                                        command=self._on_apply_rules_click, 
                                        bg=self.colors['accent'], fg='white')
        self.rules_apply_btn.pack(side='right', padx=5, pady=2)

        # Request initial rules data
        self.bus.emit("rules_requested", {})
        
        # Request initial template data
        self.bus.emit("prompt_template_requested", {})

    def _on_new_thought(self, data):
        """Updates the Neural Inspector with a thought bubble."""
        self.neural_inspector.add_thought_bubble(
            data['file'], data['chunk_id'], data['content'], 
            data['vector'], data['color']
        )

    def display_review_hunk(self, data):
        """Displays the 'before' and 'after' code for human confirmation."""
        self.review_label.config(text=f"Reviewing: {data['file']} > {data['hunk_name']}")
        
        self.before_txt.delete('1.0', 'end')
        self.before_txt.insert('1.0', data['before'])
        
        self.after_txt.delete('1.0', 'end')
        self.after_txt.insert('1.0', data['after'])
        self.approve_btn.config(state='normal')
        self.skip_btn.config(state='normal')

    def _on_approve_click(self):
        self.approve_btn.config(state='disabled')
        self.skip_btn.config(state='disabled')
        self.bus.emit("user_approve_hunk", True)

    def _on_skip_click(self):
        self.approve_btn.config(state='disabled')
        self.skip_btn.config(state='disabled')
        self.bus.emit("user_approve_hunk", False)

    def load_prompt_template(self, template_dict):
        """Displays current template in the JSON editor."""
        import json
        self.prompt_text.delete('1.0', 'end')
        self.prompt_text.insert('1.0', json.dumps(template_dict, indent=2))

    def _on_apply_prompt_click(self):
        """Parses and emits the updated prompt template."""
        import json
        raw_text = self.prompt_text.get('1.0', 'end-1c')
        try:
            new_template = json.loads(raw_text)
            self.bus.emit("prompt_template_updated", new_template)
        except json.JSONDecodeError as e:
            self.bus.emit("notify_error", {"message": f"Invalid JSON in Prompt Config: {str(e)}"})

    def load_rules(self, rules_dict):
        """Displays current rules in the JSON editor."""
        import json
        self.rules_text.delete('1.0', 'end')
        self.rules_text.insert('1.0', json.dumps(rules_dict, indent=2))

    def _on_apply_rules_click(self):
        """Parses and emits the updated ruleset."""
        import json
        raw_text = self.rules_text.get('1.0', 'end-1c')
        try:
            new_rules = json.loads(raw_text)
            self.bus.emit("rules_updated", new_rules)
        except json.JSONDecodeError as e:
            self.bus.emit("notify_error", {"message": f"Invalid JSON in Rules: {str(e)}"})

    def _on_tidy_click(self):
        selected = self.explorer.get_selected_paths()
        model = self.model_selector.get_selected_model()
        self.bus.emit("start_tidy_process", {"paths": selected, "model": model})

    def refresh_from_telemetry(self):
        """Authoritatively updates the UI from the Telemetry Spine."""
        snapshot = self.telemetry.get_snapshot()
        
        # 1. Update status bar (Phase/File/Error)
        phase = snapshot.get('phase', 'IDLE')
        active = snapshot.get('active_file')
        err = snapshot.get('last_error')
        
        status_msg = f"PHASE: {phase}"
        if active: status_msg += f" | FILE: {active}"
        if err: status_msg += f" | ERROR: {err[:30]}..."
        
        self.review_label.config(text=status_msg)

        # 2. Sync Logs from the authoritative Journal
        events = self.telemetry.get_recent_events(limit=50)
        self.console.set_journal_events(events)

        # 3. Sync Button States based on Engine Blocked status
        if not snapshot.get('engine_blocked', False):
            self.approve_btn.config(state='disabled')
            self.skip_btn.config(state='disabled')

        # 4. Schedule next authoritative refresh (250ms)
        self.shell.root.after(250, self.refresh_from_telemetry)

    def launch(self):
        self.shell.launch()







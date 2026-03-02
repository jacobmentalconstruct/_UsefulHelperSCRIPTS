"""
Project: ARCHITECT
ROLE: LifeCycle UI & Human-in-the-Loop Orchestration
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from microservices._TkinterAppShellMS import TkinterAppShellMS
from microservices._OllamaModelSelectorMS import OllamaModelSelectorMS
from state import Phase

class AppUI:
    def __init__(self, shell: TkinterAppShellMS, state_manager, backend):
        self.shell = shell
        self.state = state_manager
        self.backend = backend
        self.container = shell.get_main_container()
        self.bg_color = self.shell.colors.get('background', '#1e1e1e')
        self.accent_color = self.shell.colors.get('accent', '#007acc')
        self.show_splash()

    def clear_container(self):
        for widget in self.container.winfo_children():
            widget.destroy()

    def show_splash(self):
        """Phase 0: Project Library & Entry."""
        self.clear_container()
        self.state.global_phase = Phase.SPLASH
        
        frame = tk.Frame(self.container, bg=self.bg_color)
        frame.place(relx=0.5, rely=0.5, anchor='center')

        tk.Label(frame, text="PROJECT ARCHITECT", font=('Segoe UI', 32, 'bold'), 
                 fg=self.accent_color, bg=frame.cget('bg')).pack(pady=10)
        
        projects = self.state.list_projects()
        if projects:
            tk.Label(frame, text="RESUME RECENT PROJECT:", fg="#888", bg=frame.cget('bg')).pack(pady=(20, 5))
            self.proj_list = tk.Listbox(frame, bg="#2d2d2d", fg="white", height=6, width=50)
            self.proj_list.pack(pady=5)
            for p in projects:
                self.proj_list.insert('end', f" {p['id']} [{p['phase']}]")
            
            tk.Button(frame, text="LOAD SELECTED", command=self.load_selected).pack(pady=5)

        btn_frame = tk.Frame(frame, bg=frame.cget('bg'))
        btn_frame.pack(pady=30)
        tk.Button(btn_frame, text="NEW PROJECT", width=15, command=self.prompt_new_project).pack(side='left', padx=10)
        tk.Button(btn_frame, text="EXIT ENGINE", width=15, command=self.shell.shutdown).pack(side='left', padx=10)

    def load_selected(self):
        selection = self.proj_list.curselection()
        if selection:
            p_id = self.proj_list.get(selection[0]).split(" ")[1]
            self.state.load_project(p_id)
            self.navigate_to_phase()

    def prompt_new_project(self):
        name = simpledialog.askstring("New Project", "Enter Project Name:")
        if name:
            self.state.create_project(name)
            self.show_ideation_panel()

    def navigate_to_phase(self):
        p = self.state.active_project
        if p.current_phase == Phase.IDEATION: self.show_ideation_panel()
        elif p.current_phase == Phase.EXTRACTION: self.show_extraction_panel()

    def show_ideation_panel(self):
        """Phase 1: Narrative Vision."""
        self.clear_container()
        p = self.state.active_project
        header = tk.Frame(self.container, bg="#2d2d2d", height=40)
        header.pack(fill='x', side='top')
        tk.Label(header, text=f"PHASE 1: NARRATIVE VISION | {p.project_id}", fg="white", bg="#2d2d2d").pack(side='left', padx=10)
        tk.Button(header, text="BACK", command=self.show_splash).pack(side='right', padx=10)

        main = tk.Frame(self.container, bg=self.bg_color)
        main.pack(fill='both', expand=True, padx=40, pady=20)

        self.txt = tk.Text(main, bg="#111", fg="white", insertbackground="white", font=('Consolas', 12), height=15)
        self.txt.insert('1.0', p.vision_text)
        self.txt.pack(fill='both', expand=True, pady=10)

        ctrl = tk.Frame(main, bg=main.cget('bg'))
        ctrl.pack(fill='x')
        self.model_selector = OllamaModelSelectorMS({'parent': ctrl})
        self.model_selector.pack(side='left')

        tk.Button(ctrl, text="PROCESS (LOCAL AI)", bg=self.accent_color, fg="white", command=self.run_vision).pack(side='right', padx=5)
        tk.Button(ctrl, text="MANUAL PASTE", command=self.manual_vision).pack(side='right')

    def run_vision(self):
        raw = self.txt.get('1.0', 'end').strip()
        model = self.model_selector.get_selected_model()
        summary = self.backend.summarize_vision(raw, model)
        if summary: self.review_summary(summary)

    def manual_vision(self):
        summary = simpledialog.askstring("Manual Insertion", "Paste Vision Summary:")
        if summary: self.review_summary(summary)

    def review_summary(self, summary_text):
        if messagebox.askyesno("Confirm Vision", f"Accept this Vision Statement?\n\n{summary_text}"):
            self.backend.export_artifact("Vision.md", summary_text)
            self.state.active_project.vision_text = self.txt.get('1.0', 'end').strip()
            self.state.transition_to(Phase.EXTRACTION)
            self.show_extraction_panel()

    def show_extraction_panel(self):
        self.clear_container()
        tk.Label(self.container, text="PHASE 2: EXTRACTION UNLOCKED", fg="white", bg=self.bg_color).pack(pady=100)
        tk.Button(self.container, text="BACK", command=self.show_ideation_panel).pack()
import sys
import argparse
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import os
import sqlite3
import threading
import queue
import json
import time

# --- SYSTEM PATH SETUP ---
# Ensure src/ is importable as a top-level root so _micro_services can be imported directly.
_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# --- MICROSERVICE IMPORTS ---
from _micro_services._LibrarianServiceMS.librarian_service import LibrarianMS
from _micro_services._ScannerMS.scanner import ScannerMS
from _micro_services._IngestEngineMS.ingest_engine import IngestEngine
from _micro_services._GraphEngineMS.graph_view import GraphView
from _micro_services._ThoughtStreamMS.thought_stream import ThoughtStream
from _micro_services._SearchEngineMS.search_engine import SearchEngineMS
from _micro_services._ExporterMS.exporter import ExporterMS

# --- UI CONSTANTS ---
BG_COLOR = "#1e1e2f"
SIDEBAR_COLOR = "#171725"
ACCENT_COLOR = "#007ACC"
DANGER_COLOR = "#D32F2F"
SUCCESS_COLOR = "#388E3C"
TEXT_COLOR = "#e0e0e0"
EDITOR_BG = "#252526"
MODAL_BG = "#252526"

# ==============================================================================
#  CORE GUI CLASSES
# ==============================================================================

class Sidebar(tk.Frame):
    def __init__(self, parent, app, librarian: LibrarianMS):
        super().__init__(parent, bg=SIDEBAR_COLOR, width=250)
        self.app = app
        self.librarian = librarian
    
        self.pack_propagate(False)

        tk.Label(self, text="CORTEX DB", bg=SIDEBAR_COLOR, fg=ACCENT_COLOR, font=("Consolas", 14, "bold"), pady=20).pack(fill="x")
        tk.Label(self, text="ACTIVE KNOWLEDGE BASES", bg=SIDEBAR_COLOR, fg="#666", font=("Arial", 8, "bold"), anchor="w", padx=10).pack(fill="x")
        
        self.db_listbox = tk.Listbox(self, bg=SIDEBAR_COLOR, fg=TEXT_COLOR, bd=0, highlightthickness=0, selectbackground=ACCENT_COLOR)
        self.db_listbox.pack(fill="both", expand=True, padx=5, pady=5)
        self.db_listbox.bind("<<ListboxSelect>>", self.on_db_select)

        # Bottom Controls
        btn_frame = tk.Frame(self, bg=SIDEBAR_COLOR, pady=10)
        btn_frame.pack(fill="x", side="bottom")
        tk.Button(btn_frame, text="REFRESH LIST", bg="#2d2d44", fg="white", relief="flat", command=self.refresh_list).pack(fill="x", padx=10)

        self.refresh_list()

    def refresh_list(self):
        self.db_listbox.delete(0, tk.END)
        dbs = self.librarian.list_kbs()
        for db in dbs:
            self.db_listbox.insert(tk.END, db)

    def on_db_select(self, event):
        selection = self.db_listbox.curselection()
        if selection:
            db_name = self.db_listbox.get(selection[0])
            self.app.set_active_db(db_name)

class SettingsModal(tk.Toplevel):
    def __init__(self, parent, current_embed, current_helper, current_architect, ingestor_factory, callback):
        super().__init__(parent)
        self.title("Neural Configuration")
        self.geometry("450x350")
        self.configure(bg=MODAL_BG)
        self.ingestor_factory = ingestor_factory
        self.callback = callback
        
        x = parent.winfo_x() + (parent.winfo_width() // 2) - 225
        y = parent.winfo_y() + (parent.winfo_height() // 2) - 175
        self.geometry(f"+{x}+{y}")

        self.embed_var = tk.StringVar(value=current_embed)
        self.helper_var = tk.StringVar(value=current_helper)
        self.architect_var = tk.StringVar(value=current_architect)

        p = 20
        tk.Label(self, text="Main Architect (Reasoning/Chat):", bg=MODAL_BG, fg="white", font=("Arial", 9, "bold")).pack(anchor="w", padx=p, pady=(p, 5))
        self.architect_combo = ttk.Combobox(self, textvariable=self.architect_var, width=40)
        self.architect_combo.pack(padx=p, fill="x")
        
        tk.Label(self, text="Helper Agent (Fast Tags/Summary):", bg=MODAL_BG, fg="#A020F0", font=("Arial", 9, "bold")).pack(anchor="w", padx=p, pady=(15, 5))
        self.helper_combo = ttk.Combobox(self, textvariable=self.helper_var, width=40)
        self.helper_combo.pack(padx=p, fill="x")

        tk.Label(self, text="Embedder (Vectors):", bg=MODAL_BG, fg="#007ACC", font=("Arial", 9, "bold")).pack(anchor="w", padx=p, pady=(15, 5))
        self.embed_combo = ttk.Combobox(self, textvariable=self.embed_var, width=40)
        self.embed_combo.pack(padx=p, fill="x")

        btn_frame = tk.Frame(self, bg=MODAL_BG, pady=20)
        btn_frame.pack(fill="x", side="bottom")

        tk.Button(btn_frame, text="Apply Settings", bg=ACCENT_COLOR, fg="white", relief="flat", padx=15, pady=5, command=self.save_and_close).pack(side="right", padx=p)
        tk.Button(btn_frame, text="↻ Refresh Models", bg="#444", fg="white", relief="flat", padx=10, pady=5, command=self.refresh_models).pack(side="left", padx=p)

        # Defer model loading to allow window to render first
        self.after(100, lambda: self.refresh_models(silent=True))

    def refresh_models(self, silent=False):
        try:
            temp_engine = self.ingestor_factory("temp_scan.db")
            available_models = temp_engine.get_available_models()
            if available_models:
                self.embed_combo['values'] = tuple(available_models)
                self.helper_combo['values'] = tuple(available_models)
                self.architect_combo['values'] = tuple(available_models)
                if not silent: messagebox.showinfo("Ollama", f"Found {len(available_models)} models.")
            else:
                if not silent: messagebox.showwarning("Ollama", "No models found.")
        except Exception as e:
            if not silent: messagebox.showerror("Error", str(e))

    def save_and_close(self):
        self.callback(self.embed_var.get(), self.helper_var.get(), self.architect_var.get())
        self.destroy()

class IngestView(tk.Frame):
    def __init__(self, parent, app, scanner: ScannerMS, ingestor_factory):
        super().__init__(parent, bg=BG_COLOR)
        self.app = app
        self.scanner = scanner
        self.ingestor_factory = ingestor_factory
        self.current_tree = None
        self.current_engine = None # Reference to active engine for cancelling
        
        self.selected_embed = "mxbai-embed-large:latest-cpu"
        self.selected_helper = "qwen2.5:3b-cpu"
        self.selected_architect = "qwen2.5:7b"
        
        self.paned = ttk.PanedWindow(self, orient="horizontal")
        self.paned.pack(fill="both", expand=True)

        left_frame = tk.Frame(self.paned, bg=BG_COLOR)
        self.paned.add(left_frame, weight=1)

        # --- CONTROL PANEL ---
        ctrl_frame = tk.Frame(left_frame, bg=BG_COLOR, pady=10, padx=10)
        ctrl_frame.pack(fill="x")

        # Row 1: Source Picker
        row1 = tk.Frame(ctrl_frame, bg=BG_COLOR)
        row1.pack(fill="x", pady=2)
        tk.Label(row1, text="SOURCE:", bg=BG_COLOR, fg="gray", width=10, anchor="w").pack(side="left")
        self.path_entry = tk.Entry(row1, bg="#2d2d44", fg="white", insertbackground="white")
        self.path_entry.pack(side="left", fill="x", expand=True, padx=5)
        self.path_entry.insert(0, os.getcwd()) 
        tk.Button(row1, text="📂 Folder", bg="#444", fg="white", relief="flat", command=self.browse_folder).pack(side="left", padx=1)
        tk.Button(row1, text="📄 File", bg="#444", fg="white", relief="flat", command=self.browse_file).pack(side="left", padx=1)
        
        # Row 2: Scan Options & Target DB
        row2 = tk.Frame(ctrl_frame, bg=BG_COLOR)
        row2.pack(fill="x", pady=5)
        
        tk.Label(row2, text="WEB DEPTH:", bg=BG_COLOR, fg="gray", width=10, anchor="w").pack(side="left")
        self.depth_spin = tk.Spinbox(row2, from_=0, to=5, width=3, bg="#2d2d44", fg="white", buttonbackground="#444")
        self.depth_spin.pack(side="left", padx=(5, 15))

        tk.Button(row2, text="🔍 SCAN TARGET", bg=ACCENT_COLOR, fg="white", relief="flat", command=self.run_scan).pack(side="left", padx=5)
        
        # Target DB Selector
        tk.Label(row2, text="TARGET DB:", bg=BG_COLOR, fg="gray", padx=10).pack(side="left")

        # Default to NONE (disables ingestion until a real DB is selected)
        self.target_db_var = tk.StringVar(value="NONE")
        self.target_db_combo = ttk.Combobox(row2, textvariable=self.target_db_var, width=90, state="readonly")
        self.target_db_combo.pack(side="left", fill="x", padx=5)
        self.target_db_combo.bind("<<ComboboxSelected>>", self.on_db_combo_select)

        # Artifact Type Selector (explicit cartridge contract)
        tk.Label(row2, text="ARTIFACT:", bg=BG_COLOR, fg="gray", padx=10).pack(side="left")
        self.artifact_type_var = tk.StringVar(value="UNKNOWN")
        self.artifact_type_combo = ttk.Combobox(row2, textvariable=self.artifact_type_var, width=14, state="readonly")
        self.artifact_type_combo['values'] = ("UNKNOWN", "CODEBASE", "DOCUMENTS", "WEBSITE", "MIXED")
        self.artifact_type_combo.pack(side="left", padx=5)
        self.artifact_type_combo.bind("<<ComboboxSelected>>", lambda e: self._sync_db_dependent_controls())

        # New DB Button (inline creation mode)
        tk.Button(row2, text="➕ NEW", bg="#444", fg="white", relief="flat", command=self.create_new_db_dialog).pack(side="left", padx=(5, 2))

        # Inline New-DB name entry (disabled until NEW is clicked)
        self._new_db_placeholder = "type new db name and press Enter"
        self.new_db_var = tk.StringVar(value=self._new_db_placeholder)
        self.new_db_entry = tk.Entry(row2, textvariable=self.new_db_var, bg="#2d2d44", fg="#777", insertbackground="white", state="disabled", width=28)
        self.new_db_entry.pack(side="left", padx=(2, 0))
        self.new_db_entry.bind("<FocusIn>", self._on_new_db_focus_in)
        self.new_db_entry.bind("<FocusOut>", self._on_new_db_focus_out)
        self.new_db_entry.bind("<Return>", self._on_new_db_enter)

        self.refresh_db_combo()
        self._sync_db_dependent_controls()

        # Tree View for Scan Results
        self.tree = ttk.Treeview(left_frame, selectmode="extended")
        self.tree.pack(fill="both", expand=True, padx=10, pady=5)
        
        # --- ACTION BAR ---
        action_frame = tk.Frame(left_frame, bg="#101018", pady=10, padx=10)
        action_frame.pack(fill="x", side="bottom")
        
        # Config Cog
        tk.Button(action_frame, text="⚙", bg="#101018", fg="#666", font=("Arial", 16), bd=0, command=self.open_settings).pack(side="left", padx=(0, 10))
        self.lbl_config = tk.Label(action_frame, text="[Default Config]", bg="#101018", fg="gray", font=("Consolas", 9))
        self.lbl_config.pack(side="left")
        self._update_config_label()
        
        # Traffic Light Controls
        btn_box = tk.Frame(action_frame, bg="#101018")
        btn_box.pack(side="right")

        self.reconstruct_btn = tk.Button(btn_box, text="♻ RECONSTRUCT", bg="#444", fg="white", relief="flat", command=self.reconstruct_files)
        self.reconstruct_btn.pack(side="right", padx=5)

        self.cancel_btn = tk.Button(btn_box, text="🛑 CANCEL", bg=DANGER_COLOR, fg="white", relief="flat", state="disabled", command=self.cancel_ingestion)
        self.cancel_btn.pack(side="right", padx=5)

        self.ingest_btn = tk.Button(btn_box, text="▶ START INGESTION", bg="gray", fg="white", relief="flat", state="disabled", command=self.start_ingestion)
        self.ingest_btn.pack(side="right", padx=5)
        
        self.lbl_status = tk.Label(action_frame, text="Ready", bg="#101018", fg="gray")
        self.lbl_status.pack(side="right", padx=10)

        self.stream = ThoughtStream(self.paned)
        self.paned.add(self.stream, weight=0) 

    def refresh_db_combo(self):
        # Always include a NONE sentinel so the user can't accidentally ingest into "no selection"
        dbs = ["NONE"] + self.app.librarian.list_kbs()
        self.target_db_combo['values'] = dbs

        # Prefer active_db if set, else keep current selection, else default to NONE
        if self.app.active_db:
            self.target_db_combo.set(self.app.active_db)
            self.target_db_var.set(self.app.active_db)
        else:
            cur = (self.target_db_var.get() or "").strip()
            if cur not in dbs:
                self.target_db_combo.set("NONE")
                self.target_db_var.set("NONE")

        self._sync_db_dependent_controls()

    def on_db_combo_select(self, event):
        selected = (self.target_db_var.get() or "").strip()
        if not selected or selected == "NONE":
            self.app.active_db = None
            self._sync_db_dependent_controls()
            return

        self.app.set_active_db(selected)
        self._sync_db_dependent_controls()

    def _sync_db_dependent_controls(self):
        """Enable/disable controls that require a real active DB."""
        selected = (self.target_db_var.get() or "").strip()
        has_db = bool(selected) and selected != "NONE"

        artifact = "UNKNOWN"
        if hasattr(self, "artifact_type_var"):
            artifact = (self.artifact_type_var.get() or "UNKNOWN").strip().upper()
        has_artifact = bool(artifact) and artifact != "UNKNOWN"

        # If scan is ready, ingestion button should still be blocked unless a DB + Artifact are selected
        if hasattr(self, "ingest_btn"):
            if has_db and has_artifact and self.current_tree:
                self.ingest_btn.config(state="normal", bg=ACCENT_COLOR)
            else:
                self.ingest_btn.config(state="disabled", bg="gray")

        if hasattr(self, "reconstruct_btn"):
            self.reconstruct_btn.config(state=("normal" if has_db else "disabled"))

    def create_new_db_dialog(self):
        """Enter 'new DB creation' mode: enable the inline entry and focus it."""
        self.new_db_entry.config(state="normal")
        self.new_db_entry.focus_set()
        # Select placeholder text for quick overwrite
        self.new_db_entry.selection_range(0, tk.END)

    def _on_new_db_focus_in(self, event=None):
        val = self.new_db_var.get()
        if val == self._new_db_placeholder:
            self.new_db_var.set("")
            self.new_db_entry.config(fg="white")

    def _on_new_db_focus_out(self, event=None):
        val = (self.new_db_var.get() or "").strip()
        if not val:
            self.new_db_var.set(self._new_db_placeholder)
            self.new_db_entry.config(fg="#777")
            self.new_db_entry.config(state="disabled")

    def _on_new_db_enter(self, event=None):
        raw = (self.new_db_var.get() or "").strip()
        if not raw or raw == self._new_db_placeholder:
            return

        # Ensure extension
        if not raw.lower().endswith('.db'):
            raw += '.db'

        try:
            result = self.app.librarian.create_kb(raw)
            actual_name = result.get('name', raw)

            self.app.sidebar.refresh_list()
            self.refresh_db_combo()
            self.app.set_active_db(actual_name)
            self.target_db_combo.set(actual_name)
            self.target_db_var.set(actual_name)

            # Exit creation mode
            self.new_db_var.set(self._new_db_placeholder)
            self.new_db_entry.config(fg="#777")
            self.new_db_entry.config(state="disabled")
            self._sync_db_dependent_controls()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)

    def browse_file(self):
        path = filedialog.askopenfilename()
        if path:
            self.path_entry.delete(0, tk.END)
            self.path_entry.insert(0, path)

    def open_settings(self):
        SettingsModal(self, self.selected_embed, self.selected_helper, self.selected_architect, self.ingestor_factory, self.on_settings_saved)

    def on_settings_saved(self, new_embed, new_helper, new_architect):
        self.selected_embed = new_embed
        self.selected_helper = new_helper
        self.selected_architect = new_architect
        self._update_config_label()

    def _update_config_label(self):
        e_name = self.selected_embed.split(':')[0]
        h_name = self.selected_helper.split(':')[0]
        a_name = self.selected_architect.split(':')[0]
        self.lbl_config.config(text=f"[{a_name} | {h_name} | {e_name}]")

    def run_scan(self):
        path = self.path_entry.get().strip()
        try:
            depth = int(self.depth_spin.get())
        except ValueError:
            depth = 0

        if not path: return

        self.lbl_status.config(text="Scanning...")
        self.config(cursor="watch")
        self.update_idletasks()
        
        try:
            # Run scan
            data = self.scanner.scan_directory(path, web_depth=depth)
        finally:
            self.config(cursor="")
        
        if not data:
            messagebox.showerror("Error", "Invalid path or URL")
            self.lbl_status.config(text="Scan Failed")
            return
            
        self.current_tree = data
        self._populate_tree("", data)
        self._sync_db_dependent_controls()
        self.lbl_status.config(text="Scan Complete. Select a DB and Ingest.")

    def _populate_tree(self, parent_id, node):
        if parent_id == "": self.tree.delete(*self.tree.get_children())
        display_text = f"{node['text']}"
        if node.get('type') == 'binary': display_text += " [BIN]"
        if node.get('type') == 'web': display_text += " [WEB]"
        
        oid = self.tree.insert(parent_id, "end", text=display_text, open=True)
        for child in node.get('children', []): self._populate_tree(oid, child)

    def start_ingestion(self):
        target_db = (self.target_db_var.get() or "").strip()
        if not target_db or target_db == "NONE":
            messagebox.showwarning("Warning", "Please select a Target DB (not NONE).")
            return

        artifact = (self.artifact_type_var.get() if hasattr(self, "artifact_type_var") else "UNKNOWN")
        artifact = (artifact or "UNKNOWN").strip().upper()
        if artifact == "UNKNOWN":
            messagebox.showwarning("Warning", "Please select an Artifact Type (not UNKNOWN).")
            return

        # Handle New DB Creation Logic
        if not target_db.lower().endswith('.db'):
            target_db += '.db'

        existing_dbs = self.app.librarian.list_kbs()
        if target_db not in existing_dbs:
            # Auto-create (IMPORTANT: use canonical returned name)
            try:
                result = self.app.librarian.create_kb(target_db)
                target_db = result.get('name', target_db)
                self.app.sidebar.refresh_list()
                self.refresh_db_combo()
            except Exception as e:
                messagebox.showerror("Error", f"Could not create DB: {e}")
                return

        # Set Active (canonical)
        self.app.set_active_db(target_db)
        self.target_db_var.set(target_db)
        self.target_db_combo.set(target_db)
        self._sync_db_dependent_controls()

        files = self.scanner.flatten_tree(self.current_tree)
        if not files: return

        # UI State Lock
        self.ingest_btn.config(state="disabled", text="RUNNING...")
        self.cancel_btn.config(state="normal")
        self.reconstruct_btn.config(state="disabled")

        embed_model = self.selected_embed
        summary_model = self.selected_helper 
        db_path = os.path.join(self.app.librarian.storage_dir, target_db)

        # Stamp cartridge contract fields into manifest BEFORE ingestion begins
        try:
            source = (self.path_entry.get() or "").strip()
            try:
                depth = int(self.depth_spin.get())
            except Exception:
                depth = 0

            artifact_profile = {
                "artifact_type": artifact,
                "source": source,
                "web_depth": depth,
                "ui": "_NeoCORTEX",
                "stamped_at": time.time()
            }
            source_prov = {
                "source": source,
                "web_depth": depth,
                "stamped_at": time.time()
            }

            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute("CREATE TABLE IF NOT EXISTS manifest (key TEXT PRIMARY KEY, value TEXT)")
            cur.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("artifact_type", artifact))
            cur.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("artifact_profile", json.dumps(artifact_profile)))
            cur.execute("INSERT OR REPLACE INTO manifest (key, value) VALUES (?, ?)", ("source_provenance", json.dumps(source_prov)))
            conn.commit()
            conn.close()
        except Exception:
            # Never block ingest if manifest stamping fails
            pass
        
        # Instantiate Engine and keep ref for cancelling
        self.current_engine = self.ingestor_factory(db_path)
        self.msg_queue = queue.Queue()
        
        def worker():
            for status in self.current_engine.process_files(files, embed_model, summary_model):
                self.msg_queue.put(status)
            self.msg_queue.put(None)

        threading.Thread(target=worker, daemon=True).start()
        self.check_queue()

    def cancel_ingestion(self):
        if self.current_engine:
            self.current_engine.abort()
            self.lbl_status.config(text="Stopping...")
            self.cancel_btn.config(state="disabled")

    def reconstruct_files(self):
        if not self.app.active_db:
            messagebox.showwarning("Warning", "Select a Knowledge Base first.")
            return

        target_dir = filedialog.askdirectory(title="Select Reconstruction Destination")
        if not target_dir: return

        try:
            db_path = os.path.join(self.app.librarian.storage_dir, self.app.active_db)
            count, errors = self.app.exporter.export_knowledge_base(db_path, target_dir)
            
            msg = f"Reconstruction Complete.\nFiles Restored: {count}"
            if errors: msg += f"\nErrors: {len(errors)} (Check logs)"
            messagebox.showinfo("Result", msg)
        except Exception as e:
            messagebox.showerror("Failed", str(e))

    def check_queue(self):
        try:
            while True:
                status = self.msg_queue.get_nowait()
                if status is None:
                    # DONE
                    self.ingest_btn.config(state="normal", text="START INGESTION")
                    self.cancel_btn.config(state="disabled")
                    self.reconstruct_btn.config(state="normal")
                    self.lbl_status.config(text="Ingestion Cycle Ended.")
                    self.current_engine = None
                    if self.app.active_db: 
                        self.app.editor_view.refresh_file_list()
                        self.app.db_view.refresh_data()
                    return
                
                self.lbl_status.config(text=f"{status.progress_percent:.1f}% - {status.log_message}")
                if status.thought_frame:
                    tf = status.thought_frame
                    self.stream.add_thought_bubble(tf['file'], tf['chunk_index'], tf['content'], tf['vector_preview'], tf['concept_color'])
        except queue.Empty:
            pass
        self.after(100, self.check_queue)

class DatabaseView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_COLOR)
        self.app = app
        
        toolbar = tk.Frame(self, bg=SIDEBAR_COLOR, pady=5, padx=5)
        toolbar.pack(fill="x")
        
        tk.Label(toolbar, text="TABLE:", bg=SIDEBAR_COLOR, fg="gray", font=("Arial", 8, "bold")).pack(side="left")
        self.table_var = tk.StringVar(value="files")
        self.table_combo = ttk.Combobox(toolbar, textvariable=self.table_var, width=15, state="readonly")
        self.table_combo['values'] = ('files', 'chunks', 'diff_log', 'graph_nodes', 'graph_edges', 'manifest')
        self.table_combo.pack(side="left", padx=5)
        self.table_combo.bind("<<ComboboxSelected>>", self.refresh_data)

        tk.Label(toolbar, text="FILTER (SQL LIKE):", bg=SIDEBAR_COLOR, fg="gray", font=("Arial", 8, "bold")).pack(side="left", padx=(15, 5))
        self.search_entry = tk.Entry(toolbar, bg="#2d2d44", fg="white", insertbackground="white")
        self.search_entry.pack(side="left", fill="x", expand=True)
        self.search_entry.bind("<Return>", self.refresh_data)
        
        tk.Button(toolbar, text="💾 SAVE SELECTED", bg=ACCENT_COLOR, fg="white", relief="flat", command=self.export_selected).pack(side="right", padx=5)
        
        self.tree_frame = tk.Frame(self, bg=BG_COLOR)
        self.tree_frame.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.tree = ttk.Treeview(self.tree_frame, show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.tree.grid(column=0, row=0, sticky='nsew')
        vsb.grid(column=1, row=0, sticky='ns')
        hsb.grid(column=0, row=1, sticky='ew')
        
        self.tree.bind("<Double-1>", self.on_double_click)
        self.tree_frame.grid_columnconfigure(0, weight=1)
        self.tree_frame.grid_rowconfigure(0, weight=1)

    def refresh_data(self, event=None):
        if not self.app.active_db: return
        table = self.table_var.get()
        query_filter = self.search_entry.get().strip()
        self.tree.delete(*self.tree.get_children())
        
        db_path = os.path.join(self.app.librarian.storage_dir, self.app.active_db)
        if not os.path.exists(db_path): return

        try:
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            sql = f"SELECT * FROM {table}"
            params = []
            
            if query_filter:
                cols = self._get_columns(cursor, table)
                text_cols = [c for c in cols if 'id' in c or 'path' in c or 'content' in c or 'label' in c]
                if text_cols:
                    conditions = " OR ".join([f"{col} LIKE ?" for col in text_cols])
                    sql += f" WHERE {conditions}"
                    params = [f"%{query_filter}%" for _ in text_cols]

            sql += " LIMIT 100"
            cursor.execute(sql, params)
            rows = cursor.fetchall()
            
            if rows:
                col_names = rows[0].keys()
                self.tree['columns'] = col_names
                for col in col_names:
                    self.tree.heading(col, text=col)
                    self.tree.column(col, width=100)
                
                for row in rows:
                    values = [str(val)[:50] + "..." if len(str(val)) > 50 else val for val in row]
                    self.tree.insert("", "end", values=values, tags=(str(row[0]),)) # Tag with ID if possible
            conn.close()
        except Exception as e:
            print(f"Inspector Error: {e}")

    def _get_columns(self, cursor, table):
        cursor.execute(f"PRAGMA table_info({table})")
        return [row[1] for row in cursor.fetchall()]

    def on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item: return
        values = self.tree.item(item, 'values')
        if not values: return
        
        # Simple Viewer
        top = tk.Toplevel(self)
        top.geometry("600x400")
        txt = scrolledtext.ScrolledText(top, bg=EDITOR_BG, fg=TEXT_COLOR)
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", f"{values}")

    def export_selected(self):
        # Implementation similar to previous, kept brief for this file
        pass

class EditorView(tk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent, bg=BG_COLOR)
        self.app = app
        self.current_file = None
        
        self.paned = ttk.PanedWindow(self, orient="horizontal")
        self.paned.pack(fill="both", expand=True)

        left_frame = tk.Frame(self.paned, bg=SIDEBAR_COLOR)
        self.paned.add(left_frame, weight=1)
        tk.Label(left_frame, text="EXPLORER", bg=SIDEBAR_COLOR, fg="#888", font=("Arial", 8, "bold"), anchor="w", padx=5).pack(fill="x", pady=(5,0))

        self.file_tree = ttk.Treeview(left_frame, selectmode="browse", show="tree")
        self.file_tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.file_tree.bind("<<TreeviewSelect>>", self.on_file_select)
        
        center_frame = tk.Frame(self.paned, bg=EDITOR_BG)
        self.paned.add(center_frame, weight=4)
        
        toolbar = tk.Frame(center_frame, bg=EDITOR_BG)
        toolbar.pack(fill="x", pady=5, padx=10)
        self.lbl_current_file = tk.Label(toolbar, text="No file selected", bg=EDITOR_BG, fg=ACCENT_COLOR, font=("Consolas", 10, "bold"))
        self.lbl_current_file.pack(side="left")
        self.btn_save = tk.Button(toolbar, text="SAVE CHANGES", bg="#2d2d44", fg="white", relief="flat", state="disabled", command=self.save_changes)
        self.btn_save.pack(side="right")

        self.editor = scrolledtext.ScrolledText(center_frame, bg=EDITOR_BG, fg=TEXT_COLOR, font=("Consolas", 11), insertbackground="white", undo=True)
        self.editor.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        right_frame = tk.Frame(self.paned, bg=SIDEBAR_COLOR)
        self.paned.add(right_frame, weight=2)
        
        tk.Label(right_frame, text="NEURAL SEARCH", bg=SIDEBAR_COLOR, fg="#888", font=("Arial", 8, "bold"), anchor="w", padx=5).pack(fill="x", pady=(5,0))
        
        search_box = tk.Frame(right_frame, bg=SIDEBAR_COLOR, pady=5, padx=5)
        search_box.pack(fill="x")
        
        self.search_var = tk.StringVar()
        self.entry_search = tk.Entry(search_box, textvariable=self.search_var, bg="#2d2d44", fg="white", insertbackground="white")
        self.entry_search.pack(side="left", fill="x", expand=True)
        self.entry_search.bind("<Return>", self.perform_search)
        
        tk.Button(search_box, text="GO", bg=ACCENT_COLOR, fg="white", relief="flat", width=3, command=self.perform_search).pack(side="right", padx=(5,0))
        
        self.results_tree = ttk.Treeview(right_frame, selectmode="browse", show="tree")
        self.results_tree.pack(fill="both", expand=True, padx=5, pady=5)
        self.results_tree.bind("<<TreeviewSelect>>", self.on_result_select)

    def refresh_file_list(self):
        for item in self.file_tree.get_children(): self.file_tree.delete(item)
        if not self.app.active_db: return
        try:
            files = self.app.librarian.list_files_in_kb(self.app.active_db)
            for path in files:
                self.file_tree.insert("", "end", iid=path, text=path)
        except Exception as e:
            print(f"Error listing files: {e}")

    def on_file_select(self, event):
        selection = self.file_tree.selection()
        if not selection: return
        file_path = selection[0]
        content = self.app.librarian.get_file_content(self.app.active_db, file_path)
        if content is None: return
        self.current_file = file_path
        self.lbl_current_file.config(text=f"EDITING: {file_path}")
        self.editor.delete(1.0, tk.END)
        self.editor.insert(tk.END, content)
        self.btn_save.config(state="normal", bg=ACCENT_COLOR)

    def save_changes(self):
        if not self.app.active_db or not self.current_file: return
        new_content = self.editor.get(1.0, tk.END).strip()
        try:
            result = self.app.librarian.update_file(self.app.active_db, self.current_file, new_content, author="user")
            messagebox.showinfo("Success", f"File saved.\nDiff Size: {result.get('diff_size')} bytes")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def perform_search(self, event=None):
        query = self.search_var.get().strip()
        if not query or not self.app.active_db: return
        self.results_tree.delete(*self.results_tree.get_children())
        db_path = os.path.join(self.app.librarian.storage_dir, self.app.active_db)
        results = self.app.search_engine.search(db_path, query, limit=15)
        for i, res in enumerate(results):
            score_pct = int(res['score'] * 100) if res['score'] <= 1 else int(res['score'])
            display = f"[{score_pct}] {os.path.basename(res['path'])}"
            self.results_tree.insert("", "end", text=display, values=(res['path'], res['snippet']))

    def on_result_select(self, event):
        selection = self.results_tree.selection()
        if not selection: return
        item = self.results_tree.item(selection[0])
        values = item['values']
        if not values: return
        file_path = values[0]
        content = self.app.librarian.get_file_content(self.app.active_db, file_path)
        if not content: return
        self.current_file = file_path
        self.lbl_current_file.config(text=f"EDITING: {file_path}")
        self.editor.delete(1.0, tk.END)
        self.editor.insert(tk.END, content)
        self.btn_save.config(state="normal", bg=ACCENT_COLOR)
        snippet_start = values[1].replace("...", "").strip()[:20] 
        start_idx = self.editor.search(snippet_start, "1.0", stopindex=tk.END)
        if start_idx:
            self.editor.see(start_idx)
            self.editor.tag_add("highlight", start_idx, f"{start_idx} lineend")
            self.editor.tag_config("highlight", background="#333344", foreground="#00FF00")

class NeoCortexApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("_NeoCORTEX v1.1 (Universal)")
        self.geometry("1200x800")
        self.configure(bg=BG_COLOR)

        # 1. Initialize Services
        self.librarian = LibrarianMS("./cortex_dbs")
        self.scanner = ScannerMS()
        self.search_engine = SearchEngineMS()
        self.exporter = ExporterMS()
        self.ingest_factory = lambda db_path: IngestEngine(db_path)
        
        self.active_db = None

        # 2. Setup Layout
        self._setup_ui()

    def _setup_ui(self):
        self.sidebar = Sidebar(self, self, self.librarian)
        self.sidebar.pack(side="left", fill="y")

        self.main_area = tk.Frame(self, bg=BG_COLOR)
        self.main_area.pack(side="right", fill="both", expand=True)
        
        style = ttk.Style()
        style.theme_use('clam')
        style.configure("TNotebook", background=BG_COLOR, borderwidth=0)
        style.configure("TNotebook.Tab", background="#2d2d44", foreground="white", padding=[10, 5])
        style.map("TNotebook.Tab", background=[("selected", ACCENT_COLOR)])

        self.notebook = ttk.Notebook(self.main_area)
        self.notebook.pack(fill="both", expand=True)

        self.ingest_view = IngestView(self.notebook, self, self.scanner, self.ingest_factory)
        self.notebook.add(self.ingest_view, text="  INGEST & WEAVE  ")

        self.editor_view = EditorView(self.notebook, self)
        self.notebook.add(self.editor_view, text="  KNOWLEDGE EDITOR  ")

        self.db_view = DatabaseView(self.notebook, self)
        self.notebook.add(self.db_view, text="  DATABASE INSPECTOR  ")

        self.graph_view = GraphView(self.notebook)
        self.notebook.add(self.graph_view, text="  NEURAL GRAPH  ")

    def set_active_db(self, db_name):
        self.active_db = db_name
        self.title(f"_NeoCORTEX v1.1 - Connected to [{db_name}]")
        self.editor_view.refresh_file_list()
        self.db_view.refresh_data()
        self.ingest_view.refresh_db_combo() # Sync Ingest View
        
        db_path = os.path.join(self.librarian.storage_dir, db_name)
        self.after(100, lambda: self.graph_view.load_from_db(db_path))

# ==============================================================================
#  HYBRID ENTRY POINT
# ==============================================================================

# --- CORE LOGIC (Importable) ---
def core_logic():
    # Placeholder for headless functionality or library access
    pass

# --- GUI MODE (Default / Showcase) ---
def run_gui():
    app = NeoCortexApp()
    app.mainloop()

# --- CLI MODE (Utility) ---
def run_cli():
    parser = argparse.ArgumentParser(description="_NeoCORTEX Neural Factory CLI")
    parser.add_argument("--ingest", help="Path to a folder or file to ingest headlessly", type=str)
    parser.add_argument("--db", help="Target database name for headless ingest", type=str)
    args = parser.parse_args()

    if args.ingest:
        print(f"[CLI] Headless ingestion initiated for: {args.ingest}")
        print("[CLI] NOTE: Headless mode is a work-in-progress stub.")
        print("[CLI] Please launch without arguments to use the GUI Factory.")
    else:
        parser.print_help()

def main():
    if len(sys.argv) > 1:
        run_cli()
    else:
        run_gui()

if __name__ == "__main__":
    main()
import tkinter as tk
from tkinter import ttk, filedialog
import threading
import json

class MainOrchestrator:
    """
    The Operator. 
    Binds the UI (Shell) to the Brain (Neural) and Memory (Cartridge).
    """
    def __init__(self, services):
        self.svc = services
        self.root = self.svc['shell'].root
        self.container = self.svc['shell'].get_main_container()
        
        # State
        self.selected_model = tk.StringVar(value="qwen2.5:3b-cpu")
        self.is_thinking = False

        # Session State (Stage-1)
        self.session_var = tk.StringVar(value="")
        self.active_session_id = ""

        # Active File State (for deictic queries like "this file")
        self.active_file_paths = []
        self.active_file_primary = ""

        # Build UI
        self._setup_layout()
        self._refresh_models()

        # --- Stage-1 Sessions ---
        # Default to a new session on startup
        try:
            self.active_session_id = self.svc['memory'].new_session("Session")
        except Exception:
            self.active_session_id = ""

        self._refresh_sessions()
        self._log_system("System Ready. Waiting for input.")

    def _setup_layout(self):
        # --- Split View: Chat (Left) vs System/RAG (Right) ---
        # We use standard tk.PanedWindow to allow easy background coloring
        paned = tk.PanedWindow(self.container, orient=tk.HORIZONTAL, bg="#1e1e1e")
        paned.pack(fill="both", expand=True)

        # LEFT: Chat Interface
        left_frame = ttk.Frame(paned)
        # REMOVED: weight=3 (Not supported in tk.PanedWindow)
        paned.add(left_frame)

        # 1. Chat History
        self.chat_display = tk.Text(left_frame, bg="#252526", fg="#cccccc", font=("Consolas", 10), state="disabled", wrap="word")
        self.chat_display.pack(fill="both", expand=True, padx=5, pady=5)

        # 2. Input Area
        input_frame = ttk.Frame(left_frame)
        input_frame.pack(fill="x", padx=5, pady=5)
        
        self.prompt_entry = tk.Text(input_frame, height=3, bg="#333333", fg="white", insertbackground="white")
        self.prompt_entry.pack(side="left", fill="x", expand=True)
        self.prompt_entry.bind("<Return>", self._handle_return_key)

        # 3. Submit Button
        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(side="right", fill="y")
        
        send_btn = tk.Button(btn_frame, text="SEND", command=self.on_send, bg="#007acc", fg="white")
        send_btn.pack(fill="both", expand=True, padx=2)

        # RIGHT: System Control & RAG
        right_frame = ttk.Frame(paned)
        # REMOVED: weight=1 (Not supported in tk.PanedWindow)
        paned.add(right_frame)

        # 1. Model Picker
        controls = ttk.LabelFrame(right_frame, text="Cortex Controls")
        controls.pack(fill="x", padx=5, pady=5)

        ttk.Label(controls, text="Active Model:").pack(anchor="w", padx=5)
        self.model_menu = ttk.OptionMenu(controls, self.selected_model, "loading...", "loading...")
        self.model_menu.pack(fill="x", padx=5, pady=5)

        # 1b. Session Controls (Stage-1)
        ttk.Label(controls, text="Active Session:").pack(anchor="w", padx=5)
        self.session_menu = ttk.OptionMenu(controls, self.session_var, "(new session)", "(new session)")
        self.session_menu.pack(fill="x", padx=5, pady=2)

        sess_btn_row = ttk.Frame(controls)
        sess_btn_row.pack(fill="x", padx=5, pady=2)
        tk.Button(sess_btn_row, text="New Session", command=self.on_new_session, bg="#2d2d30", fg="#ccc").pack(side="left", fill="x", expand=True, padx=(0, 2))
        tk.Button(sess_btn_row, text="Forget Last Turn", command=self.on_forget_last_turn, bg="#2d2d30", fg="#ccc").pack(side="left", fill="x", expand=True, padx=(2, 0))

        # 2. RAG Controls
        rag_frame = ttk.LabelFrame(right_frame, text="Memory Injection")
        rag_frame.pack(fill="x", padx=5, pady=5)
        
        tk.Button(rag_frame, text="Ingest File(s)", command=self.on_ingest_click, bg="#2d2d30", fg="#ccc").pack(fill="x", padx=5, pady=2)
        
        # 3. ThoughtStream (The Neural Inspector)
        self.thought_stream = self.svc['thought_stream']
        self.thought_stream.pack(in_=right_frame, fill="both", expand=True, padx=5, pady=5)

    def _refresh_models(self):
        """Fetch models from Ollama in background"""
        def _fetch():
            models = self.svc['neural'].get_available_models()
            if models:
                menu = self.model_menu["menu"]
                menu.delete(0, "end")
                for m in models:
                    menu.add_command(label=m, command=tk._setit(self.selected_model, m))
                self.selected_model.set(models[0])
        threading.Thread(target=_fetch, daemon=True).start()

    def _handle_return_key(self, event):
        if not event.state & 0x0001: # Shift not held
            self.on_send()
            return "break" # Prevent newline

    # --- ACTIONS ---

    def _refresh_sessions(self):
        """Fetch known sessions and rebuild the session dropdown."""
        try:
            sessions = self.svc['memory'].list_sessions() or {}
        except Exception:
            sessions = {}

        menu = self.session_menu["menu"]
        menu.delete(0, "end")

        # Sort by last_active_at if present
        items = list(sessions.values())
        items.sort(key=lambda x: x.get("last_active_at", ""), reverse=True)

        # If no sessions exist, keep placeholder
        if not items:
            menu.add_command(label="(new session)", command=tk._setit(self.session_var, "(new session)"))
            self.session_var.set("(new session)")
            return

        # Populate menu
        label_for_active = None
        for s in items:
            sid = s.get("id", "")
            name = s.get("name", "Session")
            label = f"{name} | {sid[:8]}"
            if sid and sid == self.active_session_id:
                label_for_active = label
            menu.add_command(label=label, command=lambda l=label, sid=sid: self.on_select_session(l, sid))

        # Set visible label
        if label_for_active:
            self.session_var.set(label_for_active)
        else:
            # Default to the first item
            first = items[0]
            self.active_session_id = first.get("id", "")
            self.session_var.set(f"{first.get('name','Session')} | {self.active_session_id[:8]}")
            if self.active_session_id:
                try:
                    self.svc['memory'].set_active_session(self.active_session_id)
                except Exception:
                    pass

    def on_select_session(self, label: str, session_id: str):
        """Switch active session."""
        self.session_var.set(label)
        self.active_session_id = session_id
        try:
            self.svc['memory'].set_active_session(session_id)
            self._log_system(f"Switched to session: {label}")
        except Exception as e:
            self._log_system(f"Session switch failed: {e}")

    def on_new_session(self):
        """Create and switch to a new session."""
        try:
            self.active_session_id = self.svc['memory'].new_session("Session")
            self._refresh_sessions()
            self._log_system("New session created.")
        except Exception as e:
            self._log_system(f"New session failed: {e}")

    def on_forget_last_turn(self):
        """Forget last turn (stage-1): remove last 2 entries from session log."""
        try:
            removed = self.svc['memory'].forget_last_entries(2)
            self._log_system(f"Forgot last turn. Removed {removed} entries.")
        except Exception as e:
            self._log_system(f"Forget failed: {e}")

    def _is_deictic_file_query(self, user_text: str) -> bool:
        t = (user_text or "").strip().lower()
        if not t:
            return False
        triggers = [
            "this file",
            "that file",
            "the file i uploaded",
            "the file i ingested",
            "tell me about this file",
            "what is this file"
        ]
        return any(x in t for x in triggers)

    def on_send(self):
        if self.is_thinking: return
        text = self.prompt_entry.get("1.0", "end").strip()
        if not text: return

        self.prompt_entry.delete("1.0", "end")
        self._append_chat("User", text)
        
        # 1. Add to Short Term Memory
        self.svc['memory'].add_entry("user", text)

        # 2. Check RAG (Hybrid Search)
        # We spawn a thread to keep UI responsive
        threading.Thread(target=self._run_inference_pipeline, args=(text,), daemon=True).start()

    def _run_inference_pipeline(self, user_text):
        self.is_thinking = True
        
        # Step 1: Search Cartridge (RAG)
        self._log_system("Searching Long-Term Memory...")

        # Deictic file binding: if the user says "this file", anchor to the last ingested file.
        rag_query = user_text
        active_file_header = ""
        if self._is_deictic_file_query(user_text) and self.active_file_primary:
            try:
                import os
                base = os.path.basename(self.active_file_primary)
                rag_query = base
                active_file_header = f"\nACTIVE FILE:\n- {self.active_file_primary}\n"
            except Exception:
                rag_query = user_text

        rag_hits = self.svc['search'].search(
            db_path=self.svc['cartridge'].db_path,
            query=rag_query,
            limit=5
        )

        context_str = ""
        if rag_hits:
            self._log_system(f"Found {len(rag_hits)} memory fragments.")
            snippets = [f"- {h['snippet']} (Source: {h['path']})" for h in rag_hits]
            context_str = "\nCONTEXT FROM MEMORY:\n" + "\n".join(snippets) + "\n"

        # Step 2: Construct Prompt
        # We get recent history from CognitiveMemoryMS (now session-scoped)
        history = self.svc['memory'].get_context(limit=5)

        session_info = ""
        try:
            s = self.svc['memory'].get_active_session()
            if s.get("session_id"):
                session_info = f"\nSESSION:\n- {s.get('session_name','Session')} | {s.get('session_id','')[:8]}\n"
        except Exception:
            pass

        full_prompt = (
            f"System: Use the context below if relevant.\n"
            f"{session_info}"
            f"{active_file_header}"
            f"{context_str}\n\n"
            f"History:\n{history}\n\n"
            f"User: {user_text}\nAssistant:"
        )
        
        # Step 3: Inference
        self._log_system(f"Thinking ({self.selected_model.get()})...")
        response = self.svc['neural'].request_inference(
            prompt=full_prompt, 
            tier=self.selected_model.get()
        )

        # Step 4: Display & Save
        self.root.after(0, lambda: self._append_chat("Assistant", response))
        self.svc['memory'].add_entry("assistant", response)
        self.svc['memory'].commit_turn() # Flushes if full
        self.is_thinking = False

    def on_ingest_click(self):
        files = filedialog.askopenfilenames(title="Select files to Ingest")
        if not files: return

        # Track active file(s) for deictic queries like "this file"
        self.active_file_paths = list(files)
        self.active_file_primary = files[-1] if files else ""
        
        def _ingest():
            self._log_system(f"Ingesting {len(files)} files...")
            engine = self.svc['ingest']
            
            # Use the generator pattern from your IngestEngineMS
            for status in engine.process_files(list(files), model_name=self.selected_model.get()):
                # Update ThoughtStream with the "Thought Frame" if available
                if status.thought_frame:
                     self.root.after(0, lambda s=status: self.svc['thought_stream'].add_thought_bubble(
                         s.current_file, 
                         s.thought_frame['chunk_index'],
                         s.thought_frame['content'],
                         s.thought_frame['vector_preview'],
                         "#00FF00"
                     ))
                else:
                    self._log_system(status.log_message)
            
            self._log_system("Ingestion Complete.")

        threading.Thread(target=_ingest, daemon=True).start()

    # --- HELPERS ---

    def _append_chat(self, role, text):
        self.chat_display.configure(state="normal")
        tag = "user" if role == "User" else "ai"
        self.chat_display.insert("end", f"\n{role}: ", tag)
        self.chat_display.insert("end", f"{text}\n")
        self.chat_display.see("end")
        self.chat_display.configure(state="disabled")
        
        # Simple styling
        self.chat_display.tag_config("user", foreground="#4ec9b0", font=("Consolas", 10, "bold"))
        self.chat_display.tag_config("ai", foreground="#ce9178", font=("Consolas", 10, "bold"))

    def _log_system(self, msg):
        """Pipes simple text logs to the ThoughtStream as a fallback"""
        # We construct a fake 'thought bubble' for system messages
        if self.svc.get('thought_stream'):
            self.root.after(0, lambda: self.svc['thought_stream'].add_thought_bubble(
                "SYSTEM", 0, msg, [], "#888888"
            ))

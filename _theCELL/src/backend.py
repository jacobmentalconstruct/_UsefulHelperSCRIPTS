import sqlite3
import os
import json
import logging
import threading
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from src.microservices._IngestEngineMS import IngestEngineMS
from src.microservices._FeedbackValidationMS import FeedbackValidationMS
from src.microservices._SignalBusMS import SignalBusMS
from src.microservices._CognitiveMemoryMS import CognitiveMemoryMS
from src.microservices._HydrationFactoryMS import HydrationFactoryMS
from src.microservices._ErrorNotifierMS import ErrorNotifierMS
from src.microservices._ConfigStoreMS import ConfigStoreMS
from src.microservices._CodeFormatterMS import CodeFormatterMS
from src.microservices._TreeMapperMS import TreeMapperMS
from src.microservices._VectorFactoryMS import VectorFactoryMS
from src.microservices.microservice_std_lib import service_metadata

class Backend:
    """
    ROLE: Orchestration / Logic Hub
    SERVICES: Ingest, Validation, SignalBus, Memory, Factory, Notifier, ConfigStore
    STATE: Persistent (SQLite / JSON)
    """
    def __init__(self, db_path: str = None, memory_path: str = None):
        # BOOTSTRAP: Define persistence paths
        project_root = os.path.abspath(os.getcwd())
        db_dir = os.path.join(project_root, "_db")
        os.makedirs(db_dir, exist_ok=True)

        if db_path is None:
            db_path = os.path.join(db_dir, "app_internal.db")

        self.db_path = db_path
        self.logger = logging.getLogger(self.__class__.__name__)
        self._init_db()

        self.engine = IngestEngineMS()
        self.validator = FeedbackValidationMS()
        self.bus = SignalBusMS()
        self.notifier = ErrorNotifierMS(self.bus)
        self.config_store = ConfigStoreMS()

        # BOOTSTRAP: Initialize Specialists (orchestration-owned)
        self.formatter = CodeFormatterMS()
        self.mapper = TreeMapperMS()
        self.vector_factory = VectorFactoryMS()

        # DI: Package and inject services into the Fabricator
        specialists = {
            'formatter': self.formatter,
            'mapper': self.mapper,
            'vector_factory': self.vector_factory,
            'ingest_engine': self.engine
        }
        self.factory = HydrationFactoryMS(services=specialists)
        
        # Configure memory with Long-Term flush capability (Phase 7)
        mem_config = {
             'persistence_path': memory_path,
            'summarizer_func': self._summarize_memory_stub, 
            'long_term_ingest_func': self._flush_to_vector_db
        } if memory_path else {
            'summarizer_func': self._summarize_memory_stub,
            'long_term_ingest_func': self._flush_to_vector_db
        }
        self.memory = CognitiveMemoryMS(config=mem_config)
        
        # Initialize state from persistent storage
        self.system_role: str = self.get_setting('last_system_role') or "You are a helpful AI assistant."

    def get_models(self):
        """Fetches available Ollama models."""
        models = self.engine.get_available_models()
        return models if models else ["No Models Found"]

    def set_system_role(self, role_text: str) -> None:
        self.system_role = role_text
        self.save_setting('last_system_role', role_text)

    def _init_db(self) -> None:
        # TASK: Schema Initialization
        # SCOPE: Personas, Roles, Prompts
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript("""
                    -- SECTION: IDENTITY REPOSITORIES --
                    CREATE TABLE IF NOT EXISTS personas (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name TEXT UNIQUE,
                        role_text TEXT,
                        sys_prompt_text TEXT,
                        task_prompt_text TEXT,
                        is_default INTEGER DEFAULT 0,
                        last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    CREATE TABLE IF NOT EXISTS saved_roles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, content TEXT, is_default INTEGER DEFAULT 0);
                    CREATE TABLE IF NOT EXISTS saved_sys_prompts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, content TEXT, is_default INTEGER DEFAULT 0);
                    CREATE TABLE IF NOT EXISTS saved_task_prompts (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, content TEXT, is_default INTEGER DEFAULT 0);
                """)

                # --- Lightweight migration for existing DBs ---
                # If the DB already existed, the personas table may be missing columns.
                try:
                    cols = {row[1] for row in conn.execute("PRAGMA table_info(personas)").fetchall()}
                    if 'task_prompt_text' not in cols:
                        conn.execute("ALTER TABLE personas ADD COLUMN task_prompt_text TEXT")
                    if 'last_modified' not in cols:
                        conn.execute("ALTER TABLE personas ADD COLUMN last_modified TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                    if 'is_default' not in cols:
                        conn.execute("ALTER TABLE personas ADD COLUMN is_default INTEGER DEFAULT 0")
                except sqlite3.Error as mig_e:
                    self.logger.error(f"Personas migration failed: {mig_e}")

        except sqlite3.Error as e:
            self.logger.error(f"Database initialization failed: {e}")

    def save_setting(self, key: str, value: Any) -> None:
        self.config_store.set(key, value)

    def get_setting(self, key: str) -> Optional[Any]:
        return self.config_store.get(key)

    def save_persona(self, name: str, role: str, sys_prompt: str, task_prompt: str = "", is_default: bool = False) -> bool:
        """Persist or update a bonded AI Persona template."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if is_default:
                    conn.execute("UPDATE personas SET is_default = 0")

                # Use UPSERT so we UPDATE in-place on name collisions instead of DELETE+INSERT (OR REPLACE)
                conn.execute(
                    """
                    INSERT INTO personas (name, role_text, sys_prompt_text, task_prompt_text, is_default, last_modified)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(name) DO UPDATE SET
                        role_text=excluded.role_text,
                        sys_prompt_text=excluded.sys_prompt_text,
                        task_prompt_text=excluded.task_prompt_text,
                        is_default=excluded.is_default,
                        last_modified=excluded.last_modified
                    """,
                    (name, role, sys_prompt, task_prompt, 1 if is_default else 0, datetime.now().isoformat())
                )
            return True
        except sqlite3.Error as e:
            self.logger.error(f"Failed to save persona '{name}': {e}")
            return False

    def get_default_item(self, table_name: str) -> Optional[str]:
        """Retrieves the content of the item flagged as default for a given table."""
        with sqlite3.connect(self.db_path) as conn:
            col = "role_text" if table_name == 'personas' else "content"
            res = conn.execute(f"SELECT {col} FROM {table_name} WHERE is_default = 1").fetchone()
            return res[0] if res else None

    def get_repository_items(self, table_name: str) -> List[Tuple[int, str, str, int]]:
        """Generic fetch for any repository table including default flag."""
        valid_tables = ['saved_roles', 'saved_sys_prompts', 'saved_task_prompts', 'personas']
        if table_name not in valid_tables: return []
        
        with sqlite3.connect(self.db_path) as conn:
            # Personas uses role_text for the 'Preview' column
            if table_name == 'personas':
                return conn.execute("SELECT id, name, role_text, is_default FROM personas ORDER BY name ASC").fetchall()
            return conn.execute(f"SELECT id, name, content, is_default FROM {table_name} ORDER BY name ASC").fetchall()

    def save_repository_item(self, table_name: str, name: str, content: str, is_default: bool = False) -> bool:
        """Universal save for modular instruction fragments with default enforcement."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                if is_default:
                    conn.execute(f"UPDATE {table_name} SET is_default = 0")
                conn.execute(f"INSERT OR REPLACE INTO {table_name} (name, content, is_default) VALUES (?, ?, ?)", 
                             (name, content, 1 if is_default else 0))
            return True
        except sqlite3.Error as e:
            self.logger.error(f"Repo save failed for {table_name}: {e}")
            return False

    def set_as_default(self, table_name: str, item_id: int) -> None:
        """Sets a specific item as the default for its repository."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(f"UPDATE {table_name} SET is_default = 0")
            conn.execute(f"UPDATE {table_name} SET is_default = 1 WHERE id = ?", (item_id,))

    def delete_repository_item(self, table_name: str, item_id: int) -> bool:
        """Generic delete for any repository table."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(f"DELETE FROM {table_name} WHERE id = ?", (item_id,))
            return True
        except sqlite3.Error: return False

    def process_submission(self, content: str, model: str, role: str, prompt: str) -> Dict[str, Any]:
        # ACTION: Generate Artifact -> Start Threaded Inference
        # INPUTS: content (raw), model (ID), role (text), prompt (text)
        artifact = {
            "metadata": {
                "model": model,
                "timestamp": datetime.now().isoformat(),
                "source": "_theCELL_Idea_Ingestor",
                "version": "1.0.0"
            },
            "instructions": {
                "system_role": role,
                "system_prompt": prompt
            },
            "payload": content.strip()
        }

        # Add User Input to Working Memory
        self.memory.add_entry(role="user", content=content, metadata=artifact['metadata'])

        self.logger.info(f"Artifact generated for model: {model}")
        self.bus.emit(SignalBusMS.SIGNAL_PROCESS_START, artifact)

        # The Pulse: Start Threaded Inference
        thread = threading.Thread(target=self._run_inference_thread, args=(artifact,))
        thread.daemon = True
        thread.start()

        return artifact

    def _run_inference_thread(self, artifact: Dict[str, Any]):
        """
        Background worker that streams tokens from the Engine to the SignalBus.
        """
        try:
            model = artifact['metadata']['model']
            sys_role = artifact['instructions']['system_role']
            sys_prompt = artifact['instructions']['system_prompt']
            user_payload = artifact['payload']

            # Combine role/prompt context
            full_system = f"{sys_role}\n{sys_prompt}".strip()

            response_buffer = []
            
            # Connect to IngestEngine stream
            stream = self.engine.generate_stream(prompt=user_payload, model=model, system=full_system)
            
            for token in stream:
                # Emit token to UI
                self.bus.emit(SignalBusMS.SIGNAL_LOG_APPEND, token)
                response_buffer.append(token)

            final_response = "".join(response_buffer)
            
            # Hydrate artifact with result
            artifact['response'] = final_response
            
            # Add AI Response to Working Memory
            self.memory.add_entry(role="assistant", content=final_response, metadata=artifact['metadata'])

            # Signal Completion (UI triggers HITL buttons)
            self.bus.emit(SignalBusMS.SIGNAL_PROCESS_COMPLETE, artifact)

        except Exception as e:
            error_msg = f"Inference failed: {str(e)}"
            self.logger.error(error_msg)
            self.bus.emit(SignalBusMS.SIGNAL_LOG_APPEND, f"\n[SYSTEM ERROR]: {error_msg}")

    def spawn_child(self, parent_artifact: Dict[str, Any]) -> None:
        """
        Prepares a new Cell by combining the parent's product with the current memory context,
        then emits a signal requesting the UI to launch the new window.
        """
        # 1. Summarize Parent Context (The Hippocampus)
        context_summary = self.memory.get_context(limit=10)
        
        # 2. Create Child DNA
        child_payload = {
            "source_artifact": parent_artifact,
            "inherited_context": context_summary,
            "spawn_timestamp": datetime.now().isoformat()
        }

        self.logger.info("Spawning child cell requested...")
        
        # 3. Signal the System (AppShell) to launch the GUI
        self.bus.emit(SignalBusMS.SIGNAL_SPAWN_REQUESTED, child_payload)

    # --- INTEGRATION: Hydration & Export ---
    def export_artifact(self, artifact: Dict[str, Any], destination: str, path: str = None) -> Dict[str, Any]:
        # ROLE: Factory Router
        # MODES: scaffold, memory, blueprint
        try:
            mode_map = {"File": "scaffold", "Vector": "memory", "Project Capture": "blueprint"}
            mode = mode_map.get(destination, "scaffold")
            
            # If Vector, we assume a default collection if not specified
            target = path if path else ("cell_memory_bank" if destination == "Vector" else "export.txt")
            
            return self.factory.hydrate_artifact(artifact, mode=mode, destination=target)
        except Exception as e:
            self.bus.emit(SignalBusMS.SIGNAL_ERROR, {"message": f"Export failed: {str(e)}", "level": "ERROR"})
            return {"status": "error", "message": str(e)}

    # --- Phase 5: Feedback Loop ---
    def record_feedback(self, artifact: Dict[str, Any], is_accepted: bool) -> None:
        """Submits the turn to the FeedbackValidator for training."""
        self.validator.validate_artifact(artifact, is_accepted)

    # --- Phase 7: Long-Term Memory Helpers ---
    def _summarize_memory_stub(self, text: str) -> str:
        """Simple truncation summarizer. Ideally uses an LLM call."""
        return f"Session Summary [{datetime.now().isoformat()}]: {text[:200]}..."

    def _flush_to_vector_db(self, text: str, metadata: Dict[str, Any]) -> None:
        """Callback for CognitiveMemory to save flushed context to Vector Store."""
        artifact = {
            "payload": text,
            "metadata": metadata
        }
        # We use the factory to 'hydrate' this into the memory bank
        self.factory.hydrate_artifact(artifact, mode="memory", destination="long_term_history")



















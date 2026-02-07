import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from src.microservices._IngestEngineMS import IngestEngineMS
from src.microservices._FeedbackValidationMS import FeedbackValidationMS

class Backend:
    """
    Orchestration layer managing state persistence and microservice integration.
    """
    def __init__(self, db_path: str = None):
        # Default DB location: project_root/_db/app_internal.db
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
        """Initialize schema for application state and user personas."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.executescript("""
                    -- SECTION: APP CONFIGURATION --
                    CREATE TABLE IF NOT EXISTS app_settings (
                        setting_key TEXT PRIMARY KEY, 
                        setting_value TEXT
                    );
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
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT OR REPLACE INTO app_settings (setting_key, setting_value) VALUES (?, ?)", (key, str(value)))

    def get_setting(self, key: str) -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            res = conn.execute("SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)).fetchone()
            return res[0] if res else None

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
        """
        Synthesizes UI inputs into a standardized JSON artifact for downstream services.
        """
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

        self.logger.info(f"Artifact generated for model: {model}")
        return artifact













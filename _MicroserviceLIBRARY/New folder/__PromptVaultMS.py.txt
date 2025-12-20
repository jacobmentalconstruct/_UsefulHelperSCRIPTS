"""
SERVICE_NAME: _PromptVaultMS
ENTRY_POINT: __PromptVaultMS.py
DEPENDENCIES: pydantic, jinja2
"""

# --- RUNTIME DEPENDENCY CHECK ---
import importlib.util, sys
REQUIRED = ["pydantic", "jinja2"]
MISSING = []
for lib in REQUIRED:
    # Clean version numbers for check (e.g., pygame==2.0 -> pygame)
    clean_lib = lib.split('>=')[0].split('==')[0].split('>')[0].replace('-', '_')
    if importlib.util.find_spec(clean_lib) is None:
        if clean_lib == 'pywebview': clean_lib = 'webview' # Common alias
        if importlib.util.find_spec(clean_lib) is None:
            MISSING.append(lib)

if MISSING:
    print('\n' + '!'*60)
    print(f'MISSING DEPENDENCIES for _PromptVaultMS:')
    print(f'Run:  pip install {" ".join(MISSING)}')
    print('!'*60 + '\n')
    # sys.exit(1) # Uncomment to force stop if missing

import sqlite3
import json
import uuid
import logging
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable
from pydantic import BaseModel, Field, ValidationError
from jinja2 import Environment, BaseLoader

# ==============================================================================
# CONFIGURATION
# ==============================================================================
DB_PATH = Path(__file__).parent / "prompt_vault.db"
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("PromptVault")
# ==============================================================================

# --- Data Models ---

class PromptVaultMS(BaseModel):
    """A specific historical version of a prompt."""
    version_num: int
    content: str
    author: str
    timestamp: datetime.datetime
    embedding: Optional[List[float]] = None

class PromptTemplate(BaseModel):
    """The master record for a prompt."""
    id: str
    slug: str
    title: str
    description: Optional[str] = ""
    tags: List[str] = []
    latest_version_num: int
    versions: List[PromptVaultMS] = []
    
    @property
    def latest(self) -> PromptVaultMS:
        """Helper to get the most recent content."""
        if not self.versions:
            raise ValueError("No versions found.")
        # versions are stored sorted by DB insertion usually, but let's be safe
        return sorted(self.versions, key=lambda v: v.version_num)[-1]

# --- Database Management ---

class PromptVaultMS:
    """
    The Vault: A persistent SQLite store for managing, versioning, 
    and rendering AI prompts.
    """
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()
        self.jinja_env = Environment(loader=BaseLoader())

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Bootstraps the schema."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS templates (
                    id TEXT PRIMARY KEY,
                    slug TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    tags_json TEXT,
                    latest_version INTEGER DEFAULT 1,
                    created_at TIMESTAMP,
                    updated_at TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS versions (
                    id TEXT PRIMARY KEY,
                    template_id TEXT,
                    version_num INTEGER,
                    content TEXT,
                    author TEXT,
                    timestamp TIMESTAMP,
                    embedding_json TEXT,
                    FOREIGN KEY(template_id) REFERENCES templates(id)
                )
            """)
# --- CRUD Operations ---

    def create_template(self, slug: str, title: str, content: str, author: str = "system", tags: List[str] = None) -> PromptTemplate:
        """Creates a new prompt template with an initial version 1."""
        tags = tags or []
        now = datetime.datetime.utcnow()
        t_id = str(uuid.uuid4())
        v_id = str(uuid.uuid4())

        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO templates (id, slug, title, description, tags_json, latest_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (t_id, slug, title, "", json.dumps(tags), 1, now, now)
                )
                conn.execute(
                    "INSERT INTO versions (id, template_id, version_num, content, author, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                    (v_id, t_id, 1, content, author, now)
                )
            log.info(f"Created template: {slug}")
            return self.get_template(slug)
        except sqlite3.IntegrityError:
            raise ValueError(f"Template '{slug}' already exists.")

    def add_version(self, slug: str, content: str, author: str = "user") -> PromptTemplate:
        """Adds a new version to an existing template."""
        current = self.get_template(slug)
        if not current:
            raise ValueError(f"Template '{slug}' not found.")

        new_ver = current.latest_version_num + 1
        now = datetime.datetime.utcnow()
        v_id = str(uuid.uuid4())

        with self._get_conn() as conn:
            conn.execute(
                "INSERT INTO versions (id, template_id, version_num, content, author, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (v_id, current.id, new_ver, content, author, now)
            )
conn.execute(
                "UPDATE templates SET latest_version = ?, updated_at = ? WHERE id = ?",
                (new_ver, now, current.id)
            )
        log.info(f"Updated {slug} to v{new_ver}")
        return self.get_template(slug)

    def get_template(self, slug: str) -> Optional[PromptTemplate]:
        """Retrieves a full template with all history."""
        with self._get_conn() as conn:
            # 1. Fetch Template
            row = conn.execute("SELECT * FROM templates WHERE slug = ?", (slug,)).fetchone()
            if not row: return None

            # 2. Fetch Versions
            v_rows = conn.execute("SELECT * FROM versions WHERE template_id = ? ORDER BY version_num ASC", (row['id'],)).fetchall()

            versions = []
            for v in v_rows:
                versions.append(PromptVaultMS(
                    version_num=v['version_num'],
                    content=v['content'],
                    author=v['author'],
                    timestamp=v['timestamp']
                    # embedding logic skipped for brevity
                ))

            return PromptTemplate(
                id=row['id'],
                slug=row['slug'],
                title=row['title'],
                description=row['description'],
                tags=json.loads(row['tags_json']),
                latest_version_num=row['latest_version'],
                versions=versions
            )

    def render(self, slug: str, context: Dict[str, Any] = None) -> str:
        """Fetches the latest version and renders it with Jinja2."""
        template = self.get_template(slug)
if not template:
            raise ValueError(f"Template '{slug}' not found.")
        
        raw_text = template.latest.content
        jinja_template = self.jinja_env.from_string(raw_text)
        return jinja_template.render(**(context or {}))

    def list_slugs(self) -> List[str]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT slug FROM templates").fetchall()
            return [r[0] for r in rows]

# --- Independent Test Block ---
if __name__ == "__main__":
    import os
    
    # 1. Setup
    if DB_PATH.exists(): os.remove(DB_PATH)
    vault = PromptVaultMS()
    
    # 2. Create
    print("--- Creating Prompt ---")
    vault.create_template(
        slug="greet_user",
        title="Greeting Protocol",
        content="Hello {{ name }}, welcome to the {{ system_name }}!",
        tags=["ui", "onboarding"]
    )
    
    # 3. Versioning
    print("--- Updating Prompt ---")
    vault.add_version("greet_user", "Greetings, {{ name }}. System {{ system_name }} is online.")
    
    # 4. Retrieval & Rendering
    print("--- Rendering ---")
    final_text = vault.render("greet_user", {"name": "Alice", "system_name": "Nexus"})
    print(f"Rendered Output: {final_text}")
    
    # 5. Inspection
    tpl = vault.get_template("greet_user")
print(f"Current Version: v{tpl.latest_version_num}")
print(f"History: {[v.content for v in tpl.versions]}")
# Cleanup
if DB_PATH.exists(): os.remove(DB_PATH)

import importlib.util
import sys
import sqlite3
import json
import uuid
import logging
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
REQUIRED = ['pydantic', 'jinja2']
MISSING = []
for lib in REQUIRED:
    if importlib.util.find_spec(lib) is None:
        MISSING.append(lib)
if MISSING:
    print('\n' + '!' * 60)
    print(f'MISSING DEPENDENCIES for _PromptVaultMS:')
    print(f"Run:  pip install {' '.join(MISSING)}")
    print('!' * 60 + '\n')
from pydantic import BaseModel
from jinja2 import Environment, BaseLoader
from microservice_std_lib import service_metadata, service_endpoint
DB_PATH = Path(__file__).parent / 'prompt_vault.db'
logger = logging.getLogger('PromptVault')

class PromptVersion(BaseModel):
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
    description: Optional[str] = ''
    tags: List[str] = []
    latest_version_num: int
    versions: List[PromptVersion] = []

    @property
    def latest(self) -> PromptVersion:
        """Helper to get the most recent content."""
        if not self.versions:
            raise ValueError('No versions found.')
        return sorted(self.versions, key=lambda v: v.version_num)[-1]

@service_metadata(name='PromptVault', version='1.0.0', description='A persistent SQLite store for managing, versioning, and rendering AI prompts.', tags=['prompt', 'database', 'versioning', 'jinja'], capabilities=['db:sqlite', 'filesystem:read', 'filesystem:write'], internal_dependencies=['microservice_std_lib'], external_dependencies=['jinja2', 'pydantic'])
class PromptVaultMS:
    """
    The Vault: A persistent SQLite store for managing, versioning, 
    and rendering AI prompts.
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}
        self.db_path = Path(self.config.get('db_path', DB_PATH))
        self._init_db()
        self.jinja_env = Environment(loader=BaseLoader())

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Bootstraps the schema."""
        with self._get_conn() as conn:
            conn.execute('\n                CREATE TABLE IF NOT EXISTS templates (\n                    id TEXT PRIMARY KEY,\n                    slug TEXT UNIQUE NOT NULL,\n                    title TEXT NOT NULL,\n                    description TEXT,\n                    tags_json TEXT,\n                    latest_version INTEGER DEFAULT 1,\n                    created_at TIMESTAMP,\n                    updated_at TIMESTAMP\n                )\n            ')
            conn.execute('\n                CREATE TABLE IF NOT EXISTS versions (\n                    id TEXT PRIMARY KEY,\n                    template_id TEXT,\n                    version_num INTEGER,\n                    content TEXT,\n                    author TEXT,\n                    timestamp TIMESTAMP,\n                    embedding_json TEXT,\n                    FOREIGN KEY(template_id) REFERENCES templates(id)\n                )\n            ')

    @service_endpoint(inputs={'slug': 'str', 'title': 'str', 'content': 'str', 'author': 'str', 'tags': 'List[str]'}, outputs={'template': 'Dict'}, description='Creates a new prompt template with an initial version.', tags=['prompt', 'create'], side_effects=['db:write'])
    def create_template(self, slug: str, title: str, content: str, author: str='system', tags: List[str]=None) -> Dict[str, Any]:
        """Creates a new prompt template with an initial version 1."""
        tags = tags or []
        now = datetime.datetime.utcnow()
        t_id = str(uuid.uuid4())
        v_id = str(uuid.uuid4())
        try:
            with self._get_conn() as conn:
                conn.execute('INSERT INTO templates (id, slug, title, description, tags_json, latest_version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)', (t_id, slug, title, '', json.dumps(tags), 1, now, now))
                conn.execute('INSERT INTO versions (id, template_id, version_num, content, author, timestamp) VALUES (?, ?, ?, ?, ?, ?)', (v_id, t_id, 1, content, author, now))
            logger.info(f'Created template: {slug}')
            tpl = self.get_template(slug)
            return tpl.dict() if tpl else {}
        except sqlite3.IntegrityError:
            raise ValueError(f"Template '{slug}' already exists.")

    @service_endpoint(inputs={'slug': 'str', 'content': 'str', 'author': 'str'}, outputs={'template': 'Dict'}, description='Adds a new version to an existing template.', tags=['prompt', 'update'], side_effects=['db:write'])
    def add_version(self, slug: str, content: str, author: str='user') -> Dict[str, Any]:
        """Adds a new version to an existing template."""
        current = self.get_template(slug)
        if not current:
            raise ValueError(f"Template '{slug}' not found.")
        new_ver = current.latest_version_num + 1
        now = datetime.datetime.utcnow()
        v_id = str(uuid.uuid4())
        with self._get_conn() as conn:
            conn.execute('INSERT INTO versions (id, template_id, version_num, content, author, timestamp) VALUES (?, ?, ?, ?, ?, ?)', (v_id, current.id, new_ver, content, author, now))
            conn.execute('UPDATE templates SET latest_version = ?, updated_at = ? WHERE id = ?', (new_ver, now, current.id))
        logger.info(f'Updated {slug} to v{new_ver}')
        tpl = self.get_template(slug)
        return tpl.dict() if tpl else {}

    @service_endpoint(inputs={'slug': 'str'}, outputs={'template': 'Optional[PromptTemplate]'}, description='Retrieves a full template with all history.', tags=['prompt', 'read'], side_effects=['db:read'])
    def get_template(self, slug: str) -> Optional[PromptTemplate]:
        """Retrieves a full template with all history."""
        with self._get_conn() as conn:
            row = conn.execute('SELECT * FROM templates WHERE slug = ?', (slug,)).fetchone()
            if not row:
                return None
            v_rows = conn.execute('SELECT * FROM versions WHERE template_id = ? ORDER BY version_num ASC', (row['id'],)).fetchall()
            versions = []
            for v in v_rows:
                versions.append(PromptVersion(version_num=v['version_num'], content=v['content'], author=v['author'], timestamp=v['timestamp']))
            return PromptTemplate(id=row['id'], slug=row['slug'], title=row['title'], description=row['description'], tags=json.loads(row['tags_json']), latest_version_num=row['latest_version'], versions=versions)

    @service_endpoint(inputs={'slug': 'str', 'context': 'Dict'}, outputs={'rendered_text': 'str'}, description='Fetches the latest version and renders it with Jinja2.', tags=['prompt', 'render'], side_effects=['db:read'])
    def render(self, slug: str, context: Optional[Dict[str, Any]]=None) -> str:
        """Fetches the latest version and renders it with Jinja2."""
        template = self.get_template(slug)
        if not template:
            raise ValueError(f"Template '{slug}' not found.")
        raw_text = template.latest.content
        jinja_template = self.jinja_env.from_string(raw_text)
        return jinja_template.render(**context or {})

    @service_endpoint(inputs={}, outputs={'slugs': 'List[str]'}, description='Lists all available prompt slugs.', tags=['prompt', 'list'], side_effects=['db:read'])
    def list_slugs(self) -> List[str]:
        with self._get_conn() as conn:
            rows = conn.execute('SELECT slug FROM templates').fetchall()
            return [r[0] for r in rows]
if __name__ == '__main__':
    import os
    db_file = Path('test_prompt_vault.db')
    if db_file.exists():
        os.remove(db_file)
    vault = PromptVaultMS({'db_path': db_file})
    print('Service ready:', vault)
    print('--- Creating Prompt ---')
    vault.create_template(slug='greet_user', title='Greeting Protocol', content='Hello {{ name }}, welcome to the {{ system_name }}!', tags=['ui', 'onboarding'])
    print('--- Updating Prompt ---')
    vault.add_version('greet_user', 'Greetings, {{ name }}. System {{ system_name }} is online.')
    print('--- Rendering ---')
    final_text = vault.render('greet_user', {'name': 'Alice', 'system_name': 'Nexus'})
    print(f'Rendered Output: {final_text}')
    tpl = vault.get_template('greet_user')
    if tpl:
        print(f'Current Version: v{tpl.latest_version_num}')
        print(f'History: {[v.content for v in tpl.versions]}')
    if db_file.exists():
        os.remove(db_file)

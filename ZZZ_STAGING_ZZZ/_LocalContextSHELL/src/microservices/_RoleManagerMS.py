import importlib.util
import sys
import sqlite3
import json
import uuid
import logging
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

# --- RUNTIME DEPENDENCY CHECK ---
REQUIRED = ["pydantic"]
MISSING = []

for lib in REQUIRED:
    if importlib.util.find_spec(lib) is None:
        MISSING.append(lib)

if MISSING:
    print('\n' + '!'*60)
    print(f'MISSING DEPENDENCIES for _RoleManagerMS:')
    print(f'Run:  pip install {" ".join(MISSING)}')
    print('!'*60 + '\n')
    # Proceeding so the class definition loads, but functionality will break.

from pydantic import BaseModel
from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION & MODELS
# ==============================================================================

DB_PATH = Path("roles.db")
logger = logging.getLogger("RoleManager")

class RoleModel(BaseModel):
    """Data model representing an Agent Persona."""
    id: str
    name: str
    description: Optional[str] = ""
    system_prompt: str
    knowledge_bases: List[str] = []
    memory_policy: str = "scratchpad" # or 'auto_commit'
    created_at: datetime.datetime


# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="RoleManager",
    version="1.0.0",
    description="Manages Agent Personas (Roles), including System Prompts and Memory Settings.",
    tags=["roles", "personas", "db"],
    capabilities=["db:sqlite"]
)
class RoleManagerMS:
    """
    The Casting Director: Manages Agent Personas (Roles).
    Persists configuration for System Prompts, Attached KBs, and Memory Settings.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        # Allow config to override DB path
        self.db_path = Path(self.config.get("db_path", DB_PATH))
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS roles (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    description TEXT,
                    system_prompt TEXT NOT NULL,
                    knowledge_bases_json TEXT,
                    memory_policy TEXT,
                    created_at TIMESTAMP
                )
            """)

    @service_endpoint(
        inputs={"name": "str", "system_prompt": "str", "description": "str", "kbs": "List[str]"},
        outputs={"role": "Dict"},
        description="Creates a new Agent Persona.",
        tags=["roles", "create"],
        side_effects=["db:write"]
    )
    def create_role(self, name: str, system_prompt: str, description: str = "", kbs: List[str] = None) -> Dict[str, Any]:
        """Creates a new Agent Persona."""
        role_id = str(uuid.uuid4())
        now = datetime.datetime.utcnow()
        kbs_json = json.dumps(kbs or [])
        
        try:
            with self._get_conn() as conn:
                conn.execute(
                    "INSERT INTO roles (id, name, description, system_prompt, knowledge_bases_json, memory_policy, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (role_id, name, description, system_prompt, kbs_json, "scratchpad", now)
                )
            logger.info(f"Created Role: {name}")
            
            # Return the created object as a dict
            role = self.get_role(name)
            return role.dict() if role else {}
            
        except sqlite3.IntegrityError:
            raise ValueError(f"Role '{name}' already exists.")

    @service_endpoint(
        inputs={"name_or_id": "str"},
        outputs={"role": "Optional[RoleModel]"},
        description="Retrieves a role by Name or ID.",
        tags=["roles", "read"],
        side_effects=["db:read"]
    )
    def get_role(self, name_or_id: str) -> Optional[RoleModel]:
        """Retrieves a role by Name or ID."""
        with self._get_conn() as conn:
            # Try ID first
            row = conn.execute("SELECT * FROM roles WHERE id = ?", (name_or_id,)).fetchone()
            if not row:
                # Try Name
                row = conn.execute("SELECT * FROM roles WHERE name = ?", (name_or_id,)).fetchone()
            
            if not row: return None

            return RoleModel(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                system_prompt=row['system_prompt'],
                knowledge_bases=json.loads(row['knowledge_bases_json']),
                memory_policy=row['memory_policy'],
                # SQLite usually returns ISO string or similar for timestamps
                created_at=row['created_at'] 
            )

    @service_endpoint(
        inputs={},
        outputs={"roles": "List[Dict]"},
        description="Lists all available roles.",
        tags=["roles", "read"],
        side_effects=["db:read"]
    )
    def list_roles(self) -> List[Dict[str, Any]]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT id, name, description FROM roles").fetchall()
            return [dict(r) for r in rows]

    @service_endpoint(
        inputs={"name": "str"},
        outputs={},
        description="Deletes a role by name.",
        tags=["roles", "delete"],
        side_effects=["db:write"]
    )
    def delete_role(self, name: str):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM roles WHERE name = ?", (name,))
        logger.info(f"Deleted Role: {name}")


# --- Independent Test Block ---
if __name__ == "__main__":
    import os
    
    # Use a test DB file
    test_db = Path("test_roles.db")
    if test_db.exists(): 
        os.remove(test_db)
        
    logging.basicConfig(level=logging.INFO)
    
    mgr = RoleManagerMS({"db_path": test_db})
    print("Service ready:", mgr)
    
    # 1. Create
    mgr.create_role(
        name="SeniorDev", 
        system_prompt="You are a senior Python developer. Prefer Clean Code principles.",
        description="Expert coding assistant",
        kbs=["python_docs", "project_repo"]
    )
    
    # 2. Retrieve
    role = mgr.get_role("SeniorDev")
    if role:
        print(f"Role: {role.name}")
        print(f"Prompt: {role.system_prompt}")
        print(f"KBs: {role.knowledge_bases}")
    
    # Cleanup
    if test_db.exists(): 
        os.remove(test_db)
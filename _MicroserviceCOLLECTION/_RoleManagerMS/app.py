import sqlite3
import json
import uuid
import logging
import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION
# ==============================================================================
DB_PATH = Path("roles.db")
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("RoleManager")
# ==============================================================================

class Role(BaseModel):
    id: str
    name: str
    description: Optional[str] = ""
    system_prompt: str
    knowledge_bases: List[str] = []
    memory_policy: str = "scratchpad" # or 'auto_commit'
    created_at: datetime.datetime

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
self.db_path = self.config.get("db_path", DB_PATH)
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
    outputs={"role": "Role"},
    description="Creates a new Agent Persona.",
    tags=["roles", "create"],
    side_effects=["db:write"]
    )
    def create_role(self, name: str, system_prompt: str, description: str = "", kbs: List[str] = None) -> Role:
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
            log.info(f"Created Role: {name}")
            return self.get_role(name)
        except sqlite3.IntegrityError:
            raise ValueError(f"Role '{name}' already exists.")

    @service_endpoint(
    inputs={"name_or_id": "str"},
    outputs={"role": "Optional[Role]"},
    description="Retrieves a role by Name or ID.",
    tags=["roles", "read"]
    )
    def get_role(self, name_or_id: str) -> Optional[Role]:
    """Retrieves a role by Name or ID."""
        with self._get_conn() as conn:
            # Try ID first
            row = conn.execute("SELECT * FROM roles WHERE id = ?", (name_or_id,)).fetchone()
            if not row:
                # Try Name
                row = conn.execute("SELECT * FROM roles WHERE name = ?", (name_or_id,)).fetchone()
            
            if not row: return None

            return Role(
                id=row['id'],
                name=row['name'],
                description=row['description'],
                system_prompt=row['system_prompt'],
                knowledge_bases=json.loads(row['knowledge_bases_json']),
                memory_policy=row['memory_policy'],
                created_at=row['created_at'] # Adapter might need datetime.fromisoformat if stored as str
            )

    @service_endpoint(
    inputs={},
    outputs={"roles": "List[Dict]"},
    description="Lists all available roles.",
    tags=["roles", "read"]
    )
    def list_roles(self) -> List[Dict]:
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
        log.info(f"Deleted Role: {name}")

# --- Independent Test Block ---
if __name__ == "__main__":
import os
if DB_PATH.exists(): os.remove(DB_PATH)
    
mgr = RoleManagerMS()
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
    print(f"Role: {role.name}")
    print(f"Prompt: {role.system_prompt}")
    print(f"KBs: {role.knowledge_bases}")
    
    # Cleanup
    if DB_PATH.exists(): os.remove(DB_PATH)

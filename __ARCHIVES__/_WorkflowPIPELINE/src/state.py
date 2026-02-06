"""
Project: ARCHITECT
ROLE: State Authority & Pipeline Orchestrator
"""
import sqlite3
import os
import json
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

class Phase(Enum):
    SPLASH = auto()
    IDEATION = auto()     # Phase 1: Vision.md
    EXTRACTION = auto()   # Phase 2: Intent.json
    LOGIC = auto()        # Phase 2.5: Constraints.yaml
    INVENTORY = auto()    # Phase 3: Registry.yaml
    TOPOLOGY = auto()     # Phase 3.5: Map.json
    SYNTHESIS = auto()    # Phase 4: Component-by-Component Synthesis
    DONE = auto()

@dataclass
class ProjectState:
    project_id: str
    current_phase: Phase = Phase.IDEATION
    vision_text: str = ""
    intent_manifest: List[Dict] = field(default_factory=list)
    registry: Dict[str, Dict] = field(default_factory=dict)
    system_map: List[Dict] = field(default_factory=list)
    completed_components: List[str] = field(default_factory=list)

    @property
    def pending_components(self) -> List[str]:
        return [c for c in self.registry.keys() if c not in self.completed_components]

class AppState:
    def __init__(self, db_path="architect_projects.db"):
        self.db_path = db_path
        self.active_project: Optional[ProjectState] = None
        self.global_phase = Phase.SPLASH
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    phase TEXT,
                    vision TEXT,
                    registry_json TEXT,
                    completed_json TEXT
                )
            """)

    def list_projects(self) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT id, phase, vision FROM projects").fetchall()
            return [dict(r) for r in rows]

    def create_project(self, name: str):
        self.active_project = ProjectState(project_id=name)
        self.global_phase = Phase.IDEATION
        os.makedirs(f"projects/{name}", exist_ok=True)
        self.save_project()

    def load_project(self, project_id: str):
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if row:
                self.active_project = ProjectState(
                    project_id=row['id'],
                    current_phase=Phase[row['phase']],
                    vision_text=row['vision'],
                    registry=json.loads(row['registry_json'] or "{}"),
                    completed_components=json.loads(row['completed_json'] or "[]")
                )
                self.global_phase = self.active_project.current_phase

    def save_project(self):
        if not self.active_project: return
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO projects (id, phase, vision, registry_json, completed_json) VALUES (?, ?, ?, ?, ?)",
                (self.active_project.project_id, self.active_project.current_phase.name, 
                 self.active_project.vision_text, json.dumps(self.active_project.registry),
                 json.dumps(self.active_project.completed_components))
            )

    def transition_to(self, next_phase: Phase):
        self.global_phase = next_phase
        if self.active_project:
            self.active_project.current_phase = next_phase
            self.save_project()
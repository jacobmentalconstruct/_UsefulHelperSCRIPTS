"""
SERVICE_NAME: _ScratchpadMS
ENTRY_POINT: _ScratchpadMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib
EXTERNAL_DEPENDENCIES: pydantic
"""
import datetime
import logging
import sqlite3
import os
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from .microservice_std_lib import service_metadata, service_endpoint
from .base_service import BaseService

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger('Scratchpad')


class ScratchpadEntry(BaseModel):
    """A single entry in a scratchpad section."""
    id: int = 0
    scratchpad_name: str = ""
    section: str = "default"
    content: str
    author: str = "user"  # "user" | "ai"
    created_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.datetime.now().isoformat())


class ScratchpadInfo(BaseModel):
    """Metadata about a scratchpad."""
    name: str
    cell_id: Optional[str] = None
    entry_count: int = 0
    sections: List[str] = []
    created_at: str = ""
    updated_at: str = ""


@service_metadata(
    name='Scratchpad',
    version='1.0.0',
    description='Persistent collaborative notepad for co-authoring between user and AI.',
    tags=['scratchpad', 'notes', 'collaboration'],
    capabilities=['db:read', 'db:write'],
    side_effects=['db:write'],
    internal_dependencies=['base_service', 'microservice_std_lib'],
    external_dependencies=['pydantic']
)
class ScratchpadMS(BaseService):
    """
    The Notepad: A persistent, shared scratchpad system that user and AI can co-author.
    Backed by SQLite. Usable standalone (CLI/package) or wired into the Cell ecosystem.
    """

    def __init__(self, db_path: str = None, engine=None):
        """
        Args:
            db_path: Path to SQLite database. Defaults to _db/scratchpad.db relative to project root.
            engine: Optional IngestEngineMS instance for AI-powered operations.
        """
        super().__init__('Scratchpad')
        if db_path is None:
            project_root = os.path.abspath(os.getcwd())
            db_dir = os.path.join(project_root, "_db")
            os.makedirs(db_dir, exist_ok=True)
            db_path = os.path.join(db_dir, "scratchpad.db")
        self.db_path = db_path
        self.engine = engine
        self._init_db()

    def _init_db(self):
        """Creates the scratchpad schema if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scratchpads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    cell_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS scratchpad_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scratchpad_id INTEGER NOT NULL,
                    section TEXT DEFAULT 'default',
                    content TEXT NOT NULL,
                    author TEXT NOT NULL DEFAULT 'user',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (scratchpad_id) REFERENCES scratchpads(id) ON DELETE CASCADE
                );
            """)

    def _ensure_pad(self, name: str, cell_id: str = None) -> int:
        """Gets or creates a scratchpad by name. Returns the scratchpad row id."""
        now = datetime.datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT id FROM scratchpads WHERE name = ?", (name,)).fetchone()
            if row:
                return row[0]
            cursor = conn.execute(
                "INSERT INTO scratchpads (name, cell_id, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (name, cell_id, now, now)
            )
            return cursor.lastrowid

    # ─── CRUD ────────────────────────────────────────────────────────────

    @service_endpoint(
        inputs={'name': 'str', 'cell_id': 'str'},
        outputs={'info': 'ScratchpadInfo'},
        description='Creates a new named scratchpad (or returns existing).',
        tags=['scratchpad', 'create'],
        side_effects=['db:write']
    )
    def create(self, name: str, cell_id: str = None) -> ScratchpadInfo:
        """Creates a new named scratchpad. No-op if it already exists."""
        self._ensure_pad(name, cell_id)
        log.info(f"Scratchpad '{name}' ready.")
        return self._get_info(name)

    @service_endpoint(
        inputs={},
        outputs={'pads': 'List[ScratchpadInfo]'},
        description='Lists all scratchpads with metadata.',
        tags=['scratchpad', 'read']
    )
    def list_pads(self) -> List[ScratchpadInfo]:
        """Returns metadata for all scratchpads."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT name, cell_id, created_at, updated_at FROM scratchpads ORDER BY updated_at DESC"
            ).fetchall()
        result = []
        for name, cell_id, created, updated in rows:
            info = self._get_info(name)
            result.append(info)
        return result

    @service_endpoint(
        inputs={'name': 'str', 'content': 'str', 'author': 'str', 'section': 'str'},
        outputs={'entry': 'ScratchpadEntry'},
        description='Writes a new entry to a scratchpad. Auto-creates the pad if needed.',
        tags=['scratchpad', 'write'],
        side_effects=['db:write']
    )
    def write(self, name: str, content: str, author: str = "user", section: str = "default") -> ScratchpadEntry:
        """Appends an entry to a scratchpad. Creates the pad if it doesn't exist."""
        pad_id = self._ensure_pad(name)
        now = datetime.datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO scratchpad_entries (scratchpad_id, section, content, author, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pad_id, section, content, author, now, now)
            )
            conn.execute("UPDATE scratchpads SET updated_at = ? WHERE id = ?", (now, pad_id))
            entry_id = cursor.lastrowid
        log.info(f"[{author}] wrote to '{name}/{section}' ({len(content)} chars)")
        return ScratchpadEntry(
            id=entry_id, scratchpad_name=name, section=section,
            content=content, author=author, created_at=now, updated_at=now
        )

    @service_endpoint(
        inputs={'name': 'str', 'section': 'str'},
        outputs={'entries': 'List[ScratchpadEntry]'},
        description='Reads all entries from a scratchpad, optionally filtered by section.',
        tags=['scratchpad', 'read']
    )
    def read(self, name: str, section: str = None) -> List[ScratchpadEntry]:
        """Reads entries from a scratchpad."""
        with sqlite3.connect(self.db_path) as conn:
            pad_row = conn.execute("SELECT id FROM scratchpads WHERE name = ?", (name,)).fetchone()
            if not pad_row:
                return []
            pad_id = pad_row[0]
            if section:
                rows = conn.execute(
                    "SELECT id, section, content, author, created_at, updated_at "
                    "FROM scratchpad_entries WHERE scratchpad_id = ? AND section = ? ORDER BY id",
                    (pad_id, section)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, section, content, author, created_at, updated_at "
                    "FROM scratchpad_entries WHERE scratchpad_id = ? ORDER BY id",
                    (pad_id,)
                ).fetchall()
        return [
            ScratchpadEntry(
                id=r[0], scratchpad_name=name, section=r[1],
                content=r[2], author=r[3], created_at=r[4], updated_at=r[5]
            ) for r in rows
        ]

    @service_endpoint(
        inputs={'entry_id': 'int', 'content': 'str'},
        outputs={'entry': 'ScratchpadEntry'},
        description='Updates an existing entry in-place.',
        tags=['scratchpad', 'write'],
        side_effects=['db:write']
    )
    def update_entry(self, entry_id: int, content: str) -> Optional[ScratchpadEntry]:
        """Edits an existing entry's content."""
        now = datetime.datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE scratchpad_entries SET content = ?, updated_at = ? WHERE id = ?",
                (content, now, entry_id)
            )
            row = conn.execute(
                "SELECT e.id, e.section, e.content, e.author, e.created_at, e.updated_at, s.name "
                "FROM scratchpad_entries e JOIN scratchpads s ON e.scratchpad_id = s.id WHERE e.id = ?",
                (entry_id,)
            ).fetchone()
        if not row:
            return None
        return ScratchpadEntry(
            id=row[0], scratchpad_name=row[6], section=row[1],
            content=row[2], author=row[3], created_at=row[4], updated_at=row[5]
        )

    @service_endpoint(
        inputs={'entry_id': 'int'},
        outputs={'success': 'bool'},
        description='Deletes a single entry.',
        tags=['scratchpad', 'delete'],
        side_effects=['db:write']
    )
    def delete_entry(self, entry_id: int) -> bool:
        """Removes a single entry by ID."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("DELETE FROM scratchpad_entries WHERE id = ?", (entry_id,))
            return cursor.rowcount > 0

    @service_endpoint(
        inputs={'name': 'str', 'section': 'str'},
        outputs={'success': 'bool'},
        description='Clears all entries from a scratchpad (or just a section).',
        tags=['scratchpad', 'delete'],
        side_effects=['db:write']
    )
    def clear(self, name: str, section: str = None) -> bool:
        """Clears all entries from a scratchpad, or just a specific section."""
        with sqlite3.connect(self.db_path) as conn:
            pad_row = conn.execute("SELECT id FROM scratchpads WHERE name = ?", (name,)).fetchone()
            if not pad_row:
                return False
            pad_id = pad_row[0]
            if section:
                conn.execute(
                    "DELETE FROM scratchpad_entries WHERE scratchpad_id = ? AND section = ?",
                    (pad_id, section)
                )
            else:
                conn.execute("DELETE FROM scratchpad_entries WHERE scratchpad_id = ?", (pad_id,))
        log.info(f"Cleared '{name}'" + (f"/{section}" if section else ""))
        return True

    @service_endpoint(
        inputs={'name': 'str'},
        outputs={'sections': 'List[str]'},
        description='Lists distinct sections within a scratchpad.',
        tags=['scratchpad', 'read']
    )
    def get_sections(self, name: str) -> List[str]:
        """Returns the list of distinct section names in a scratchpad."""
        with sqlite3.connect(self.db_path) as conn:
            pad_row = conn.execute("SELECT id FROM scratchpads WHERE name = ?", (name,)).fetchone()
            if not pad_row:
                return []
            rows = conn.execute(
                "SELECT DISTINCT section FROM scratchpad_entries WHERE scratchpad_id = ? ORDER BY section",
                (pad_row[0],)
            ).fetchall()
        return [r[0] for r in rows]

    # ─── Text Helpers ────────────────────────────────────────────────────

    @service_endpoint(
        inputs={'name': 'str', 'section': 'str'},
        outputs={'text': 'str'},
        description='Returns concatenated plain text of all entries (for AI consumption).',
        tags=['scratchpad', 'read']
    )
    def read_full_text(self, name: str, section: str = None) -> str:
        """Returns all entries as a single concatenated string."""
        entries = self.read(name, section)
        if not entries:
            return ""
        parts = []
        for e in entries:
            parts.append(f"[{e.author.upper()}] {e.content}")
        return "\n\n".join(parts)

    # ─── AI Operations ───────────────────────────────────────────────────

    @service_endpoint(
        inputs={'name': 'str', 'instruction': 'str', 'model': 'str', 'section': 'str'},
        outputs={'entry': 'ScratchpadEntry'},
        description='Sends scratchpad content + instruction to AI, writes response back.',
        tags=['scratchpad', 'ai', 'write'],
        side_effects=['db:write', 'network:outbound']
    )
    def ai_process(self, name: str, instruction: str, model: str = None, section: str = None) -> ScratchpadEntry:
        """
        Sends the scratchpad content to the AI with an instruction,
        then writes the AI response back as a new entry.
        """
        if not self.engine:
            raise RuntimeError("No IngestEngine configured. AI operations require an engine instance.")

        # Gather existing content
        full_text = self.read_full_text(name, section)

        # Build prompt
        system = "You are a collaborative writing assistant. The user shares a scratchpad with you. Follow their instruction precisely."
        if full_text:
            prompt = f"### SCRATCHPAD CONTENT ###\n{full_text}\n\n### INSTRUCTION ###\n{instruction}"
        else:
            prompt = f"### INSTRUCTION ###\n{instruction}\n\n(The scratchpad is currently empty.)"

        # Resolve model
        if not model:
            models = self.engine.get_available_models()
            model = models[0] if models else "llama3.2"

        # Collect streamed response
        response_parts = []
        for token in self.engine.generate_stream(prompt=prompt, model=model, system=system):
            response_parts.append(token)
        response = "".join(response_parts)

        # Write AI response back to the scratchpad
        target_section = section or "default"
        return self.write(name, response, author="ai", section=target_section)

    @service_endpoint(
        inputs={'name': 'str', 'instruction': 'str', 'model': 'str', 'section': 'str'},
        outputs={'text': 'str'},
        description='Sends scratchpad content + instruction to AI, returns response WITHOUT writing to DB.',
        tags=['scratchpad', 'ai'],
        side_effects=['network:outbound']
    )
    def ai_draft(self, name: str, instruction: str, model: str = None, section: str = None) -> str:
        """
        Same as ai_process() but returns the AI text without persisting it.
        Used by the HITL diff system — the caller decides whether to accept.
        """
        if not self.engine:
            raise RuntimeError("No IngestEngine configured. AI operations require an engine instance.")

        full_text = self.read_full_text(name, section)

        system = "You are a collaborative writing assistant. The user shares a scratchpad with you. Follow their instruction precisely."
        if full_text:
            prompt = f"### SCRATCHPAD CONTENT ###\n{full_text}\n\n### INSTRUCTION ###\n{instruction}"
        else:
            prompt = f"### INSTRUCTION ###\n{instruction}\n\n(The scratchpad is currently empty.)"

        if not model:
            models = self.engine.get_available_models()
            model = models[0] if models else "llama3.2"

        response_parts = []
        for token in self.engine.generate_stream(prompt=prompt, model=model, system=system):
            response_parts.append(token)
        return "".join(response_parts)

    @service_endpoint(
        inputs={'name': 'str', 'content': 'str', 'author': 'str', 'section': 'str'},
        outputs={'success': 'bool'},
        description='Replaces all content in a section with new text (single entry overwrite).',
        tags=['scratchpad', 'write'],
        side_effects=['db:write']
    )
    def replace_content(self, name: str, content: str, author: str = "user", section: str = "default") -> bool:
        """
        Clears all entries in a section and writes a single replacement entry.
        Used by the standalone editor for full-document saves.
        """
        pad_id = self._ensure_pad(name)
        now = datetime.datetime.now().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "DELETE FROM scratchpad_entries WHERE scratchpad_id = ? AND section = ?",
                (pad_id, section)
            )
            conn.execute(
                "INSERT INTO scratchpad_entries (scratchpad_id, section, content, author, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (pad_id, section, content, author, now, now)
            )
            conn.execute("UPDATE scratchpads SET updated_at = ? WHERE id = ?", (now, pad_id))
        log.info(f"[{author}] replaced content in '{name}/{section}' ({len(content)} chars)")
        return True

    # ─── Internals ───────────────────────────────────────────────────────

    def _get_info(self, name: str) -> ScratchpadInfo:
        """Builds a ScratchpadInfo from the database."""
        with sqlite3.connect(self.db_path) as conn:
            pad = conn.execute(
                "SELECT name, cell_id, created_at, updated_at FROM scratchpads WHERE name = ?",
                (name,)
            ).fetchone()
            if not pad:
                return ScratchpadInfo(name=name)
            pad_id = conn.execute("SELECT id FROM scratchpads WHERE name = ?", (name,)).fetchone()[0]
            count = conn.execute(
                "SELECT COUNT(*) FROM scratchpad_entries WHERE scratchpad_id = ?", (pad_id,)
            ).fetchone()[0]
            sections = [r[0] for r in conn.execute(
                "SELECT DISTINCT section FROM scratchpad_entries WHERE scratchpad_id = ? ORDER BY section",
                (pad_id,)
            ).fetchall()]
        return ScratchpadInfo(
            name=pad[0], cell_id=pad[1], entry_count=count,
            sections=sections, created_at=pad[2], updated_at=pad[3]
        )

    def delete_pad(self, name: str) -> bool:
        """Deletes an entire scratchpad and all its entries."""
        with sqlite3.connect(self.db_path) as conn:
            pad_row = conn.execute("SELECT id FROM scratchpads WHERE name = ?", (name,)).fetchone()
            if not pad_row:
                return False
            conn.execute("DELETE FROM scratchpad_entries WHERE scratchpad_id = ?", (pad_row[0],))
            conn.execute("DELETE FROM scratchpads WHERE id = ?", (pad_row[0],))
        log.info(f"Deleted scratchpad '{name}'")
        return True


if __name__ == '__main__':
    print("--- Scratchpad Self-Test ---")
    import tempfile
    test_db = os.path.join(tempfile.gettempdir(), "scratchpad_test.db")
    pad = ScratchpadMS(db_path=test_db)

    pad.write("research", "First finding: microservices are cool.", author="user")
    pad.write("research", "Second finding: SQLite is reliable.", author="user")
    pad.write("research", "AI agrees with the above.", author="ai", section="analysis")

    entries = pad.read("research")
    print(f"Entries in 'research': {len(entries)}")
    for e in entries:
        print(f"  [{e.author}] {e.section}: {e.content[:60]}")

    sections = pad.get_sections("research")
    print(f"Sections: {sections}")

    full = pad.read_full_text("research")
    print(f"Full text length: {len(full)}")

    pads = pad.list_pads()
    print(f"Pads: {[p.name for p in pads]}")

    pad.clear("research", section="analysis")
    print(f"After clearing 'analysis': {len(pad.read('research'))} entries remain")

    pad.delete_pad("research")
    print(f"After delete: {len(pad.list_pads())} pads")

    os.remove(test_db)
    print("--- Self-Test Complete ---")

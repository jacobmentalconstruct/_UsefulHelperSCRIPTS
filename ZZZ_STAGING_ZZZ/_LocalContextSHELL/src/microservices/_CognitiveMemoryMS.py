"""
SERVICE_NAME: _CognitiveMemoryMS
ENTRY_POINT: _CognitiveMemoryMS.py
DEPENDENCIES: pip install pydantic
"""

# --- RUNTIME DEPENDENCY CHECK ---
import importlib.util
import sys

REQUIRED = ["pydantic"]
MISSING = []
for lib in REQUIRED:
    if importlib.util.find_spec(lib) is None:
        MISSING.append(lib)

if MISSING:
    print(f"MISSING DEPENDENCIES: {' '.join(MISSING)}")
    print("Please run: pip install pydantic")

import datetime
import json
import logging
import uuid
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, Field
from microservice_std_lib import service_metadata, service_endpoint
from base_service import BaseService

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Stage-1 Sessions (lightweight, filesystem-backed):
# - Each session writes to its own JSONL log under ./sessions/
# - A simple sessions index file tracks available sessions
SESSIONS_DIR = Path("sessions")
SESSIONS_INDEX_FILE = SESSIONS_DIR / "sessions_index.json"
DEFAULT_SESSION_NAME = "New Session"

# Backward-compat: if a legacy path is provided, we still support it,
# but by default we write to session logs.
DEFAULT_MEMORY_FILE = Path("working_memory.jsonl")

FLUSH_THRESHOLD = 5  # Number of turns before summarizing to Long Term Memory

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
log = logging.getLogger("CognitiveMem")

# ==============================================================================
# DATA MODELS
# ==============================================================================
class MemoryEntry(BaseModel):
    """Atomic unit of memory."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    role: str  # 'user', 'assistant', 'system', 'tool'
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

# ==============================================================================
# SERVICE DEFINITION
# ==============================================================================
@service_metadata(
    name="CognitiveMemory",
    version="1.0.0",
    description="Manages Short-Term (Working) Memory and orchestrates flushing to Long-Term Memory.",
    tags=["memory", "history", "context"],
    capabilities=["filesystem:read", "filesystem:write"],
    dependencies=["pydantic"],
    side_effects=["filesystem:write"]
)
class CognitiveMemoryMS(BaseService):
    """
    The Hippocampus: Manages Short-Term (Working) Memory and orchestrates 
    flushing to Long-Term Memory (Vector Store).
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__("CognitiveMemory")
        self.config = config or {}

        # Long-term flush hooks (optional)
        self.summarizer = self.config.get("summarizer_func")
        self.ingestor = self.config.get("long_term_ingest_func")

        # --- Session State ---
        self.sessions_dir = Path(self.config.get("sessions_dir", SESSIONS_DIR))
        self.sessions_index_file = Path(self.config.get("sessions_index_file", SESSIONS_INDEX_FILE))
        self.active_session_id: Optional[str] = None
        self.active_session_name: str = DEFAULT_SESSION_NAME

        # Legacy support: allow overriding persistence_path, but default is session-backed.
        self.file_path = Path(self.config.get("persistence_path", DEFAULT_MEMORY_FILE))

        # Ensure storage exists
        self._ensure_sessions_storage()

        # Working memory must exist BEFORE any session operations (new_session/set_active_session)
        # because those methods clear/reload it.
        self.working_memory: List[MemoryEntry] = []

        # Load session index and start a new session unless a session_id was provided.
        requested_session_id = self.config.get("active_session_id")
        if requested_session_id:
            self.set_active_session(str(requested_session_id))
        else:
            self.new_session(DEFAULT_SESSION_NAME)

        # Load whatever is currently active (new session will usually be empty)
        self._load_working_memory()

    # ==========================================================================
    # WORKING MEMORY OPERATIONS
    # ==========================================================================

    @service_endpoint(
        inputs={"role": "str", "content": "str", "metadata": "Dict"},
        outputs={"entry": "MemoryEntry"},
        description="Adds an item to working memory and persists it.",
        tags=["memory", "write"],
        side_effects=["filesystem:write"]
    )
    def add_entry(self, role: str, content: str, metadata: Dict = None) -> MemoryEntry:
        """Adds an item to working memory and persists it."""
        meta = metadata or {}
        # Hard-scope every entry to the active session
        if self.active_session_id:
            meta.setdefault("session_id", self.active_session_id)
            meta.setdefault("session_name", self.active_session_name)

        entry = MemoryEntry(role=role, content=content, metadata=meta)
        self.working_memory.append(entry)
        self._append_to_file(entry)
        log.info(f"Added memory: [{role}] {content[:30]}...")
        return entry

    # ======================================================================
    # SESSION OPERATIONS (Stage-1, filesystem-backed)
    # ======================================================================

    @service_endpoint(
        inputs={"name": "str"},
        outputs={"session_id": "str"},
        description="Creates a new session and sets it active.",
        tags=["memory", "session", "write"],
        side_effects=["filesystem:write"]
    )
    def new_session(self, name: str = DEFAULT_SESSION_NAME) -> str:
        session_id = str(uuid.uuid4())
        self.active_session_id = session_id
        self.active_session_name = name or DEFAULT_SESSION_NAME

        # Point persistence to this session file
        self.file_path = self._session_file_path(session_id)

        # Update index
        index = self._load_sessions_index()
        now = datetime.datetime.utcnow().isoformat()
        index[session_id] = {
            "id": session_id,
            "name": self.active_session_name,
            "created_at": now,
            "last_active_at": now
        }
        self._save_sessions_index(index)

        # Clear in-RAM working memory and create file if needed
        self.working_memory.clear()
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text("", encoding="utf-8")

        return session_id

    @service_endpoint(
        inputs={},
        outputs={"sessions": "Dict"},
        description="Lists known sessions from the sessions index.",
        tags=["memory", "session", "read"],
        side_effects=["filesystem:read"]
    )
    def list_sessions(self) -> Dict[str, Any]:
        return self._load_sessions_index()

    @service_endpoint(
        inputs={"session_id": "str"},
        outputs={"active_session_id": "str"},
        description="Sets the active session and reloads working memory from that session log.",
        tags=["memory", "session", "write"],
        side_effects=["filesystem:read", "filesystem:write"]
    )
    def set_active_session(self, session_id: str) -> str:
        session_id = str(session_id)
        index = self._load_sessions_index()
        if session_id not in index:
            # If unknown, create a minimal record and empty log.
            now = datetime.datetime.utcnow().isoformat()
            index[session_id] = {
                "id": session_id,
                "name": DEFAULT_SESSION_NAME,
                "created_at": now,
                "last_active_at": now
            }
            self._save_sessions_index(index)

        self.active_session_id = session_id
        self.active_session_name = index[session_id].get("name", DEFAULT_SESSION_NAME)
        self.file_path = self._session_file_path(session_id)

        # Touch and reload
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text("", encoding="utf-8")

        index[session_id]["last_active_at"] = datetime.datetime.utcnow().isoformat()
        self._save_sessions_index(index)

        self.working_memory.clear()
        self._load_working_memory()
        return session_id

    @service_endpoint(
        inputs={},
        outputs={"session_id": "str", "session_name": "str"},
        description="Returns the currently active session.",
        tags=["memory", "session", "read"],
        side_effects=[]
    )
    def get_active_session(self) -> Dict[str, str]:
        return {
            "session_id": self.active_session_id or "",
            "session_name": self.active_session_name or ""
        }

    @service_endpoint(
        inputs={"count": "int"},
        outputs={"removed": "int"},
        description="Removes the last N entries from the active session (stage-1 forget).",
        tags=["memory", "session", "forget"],
        side_effects=["filesystem:write"]
    )
    def forget_last_entries(self, count: int = 2) -> int:
        if count <= 0:
            return 0
        if not self.working_memory:
            return 0

        removed = min(count, len(self.working_memory))
        # Trim in-RAM
        self.working_memory = self.working_memory[:-removed]
        # Rewrite session file
        self._rewrite_session_file()
        return removed

    @service_endpoint(
        inputs={"limit": "int"},
        outputs={"context": "str"},
        description="Returns the most recent conversation history formatted for an LLM.",
        tags=["memory", "read", "llm"],
        side_effects=["filesystem:read"]
    )
    def get_context(self, limit: int = 10) -> str:
        """
        Returns the most recent conversation history formatted for an LLM.
        """
        recent = self.working_memory[-limit:]
        return "\n".join([f"{e.role.upper()}: {e.content}" for e in recent])

    def get_full_history(self) -> List[Dict]:
        """Returns the raw list of memory objects."""
        return [e.dict() for e in self.working_memory]

    # ==========================================================================
    # CONSOLIDATION (The "Sleep" Cycle)
    # ==========================================================================

    @service_endpoint(
        inputs={},
        outputs={},
        description="Signals that a turn is complete; checks if memory flush is needed.",
        tags=["memory", "maintenance"],
        side_effects=["filesystem:write"]
    )
    def commit_turn(self):
        """
        Signal that a "Turn" (User + AI response) is complete.
        Checks if memory is full and triggers a flush if needed.
        """
        if len(self.working_memory) >= FLUSH_THRESHOLD:
            self._flush_to_long_term()

    def _flush_to_long_term(self):
        """
        Compresses working memory into a summary and moves it to Long-Term storage.
        """
        if not self.summarizer or not self.ingestor:
            log.warning("Flush triggered but Summarizer/Ingestor not configured. Skipping.")
            return

        log.info("🌀 Flushing Working Memory to Long-Term Storage...")
        
        # 1. Combine Text
        full_text = "\n".join([f"{e.role}: {e.content}" for e in self.working_memory])
        
        # 2. Summarize
        try:
            summary = self.summarizer(full_text)
            log.info(f"Summary generated: {summary[:50]}...")
        except Exception as e:
            log.error(f"Summarization failed: {e}")
            return

        # 3. Ingest into Vector DB
        try:
            meta = {
                "source": "cognitive_memory_flush", 
                "date": datetime.datetime.utcnow().isoformat(),
                "original_entry_count": len(self.working_memory)
            }
            self.ingestor(summary, meta)
            log.info("✅ Saved to Long-Term Memory.")
        except Exception as e:
            log.error(f"Ingestion failed: {e}")
            return

        # 4. Clear Working Memory
        # For this pattern, we clear the 'Active' RAM, and rotate the log file.
        self.working_memory.clear()
        self._rotate_log_file()

    # ==========================================================================
    # PERSISTENCE HELPERS
    # ==========================================================================

    def _ensure_sessions_storage(self):
        """Ensures the sessions directory and sessions index exist."""
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        if not self.sessions_index_file.exists():
            self.sessions_index_file.write_text("{}", encoding="utf-8")

    def _load_sessions_index(self) -> Dict[str, Any]:
        try:
            raw = self.sessions_index_file.read_text(encoding="utf-8").strip() or "{}"
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            return {}
        except Exception:
            return {}

    def _save_sessions_index(self, index: Dict[str, Any]):
        try:
            self.sessions_index_file.write_text(json.dumps(index, indent=2), encoding="utf-8")
        except Exception as e:
            log.error(f"Failed to save sessions index: {e}")

    def _session_file_path(self, session_id: str) -> Path:
        return self.sessions_dir / f"session_{session_id}.jsonl"

    def _rewrite_session_file(self):
        """Rewrites the active session JSONL file from in-RAM working memory."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                for e in self.working_memory:
                    f.write(e.json() + "\n")
        except Exception as e:
            log.error(f"Failed to rewrite session file: {e}")

    def _load_working_memory(self):
        """Rehydrates memory from the JSONL file."""
        if not self.file_path.exists():
            return

        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        self.working_memory.append(MemoryEntry.parse_raw(line))
            log.info(f"Loaded {len(self.working_memory)} items from {self.file_path}")
        except Exception as e:
            log.error(f"Corrupt memory file: {e}")

    def _append_to_file(self, entry: MemoryEntry):
        """Appends a single entry to the JSONL log."""
        with open(self.file_path, 'a', encoding='utf-8') as f:
            f.write(entry.json() + "\n")

    def _rotate_log_file(self):
        """Renames the current log to an archive timestamp."""
        if self.file_path.exists():
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            archive_name = self.file_path.with_name(f"memory_archive_{timestamp}.jsonl")
            self.file_path.rename(archive_name)
            log.info(f"Rotated memory log to {archive_name}")


# ==============================================================================
# SELF-TEST / RUNNER
# ==============================================================================
if __name__ == "__main__":
    # 1. Setup Mock Dependencies
    def mock_summarizer(text):
        return f"SUMMARY OF {len(text)} CHARS: The user and AI discussed AI architecture."

    def mock_ingest(text, metadata):
        print(f"\n[VectorDB] Indexing: '{text}'\n[VectorDB] Meta: {metadata}")

    # 2. Initialize
    print("--- Initializing Cognitive Memory ---")
    mem = CognitiveMemoryMS({
        "summarizer_func": mock_summarizer,
        "long_term_ingest_func": mock_ingest
    })
    print(f"Service ready: {mem}")

    # 3. Simulate Conversation
    print("\n--- Simulating Conversation ---")
    mem.add_entry("user", "Hello, who are you?")
    mem.add_entry("assistant", "I am a Cognitive Agent.")
    mem.add_entry("user", "What is your memory capacity?")
    mem.add_entry("assistant", "I have a tiered memory system.")
    mem.add_entry("user", "That sounds complex.")

    print(f"\nCurrent Context:\n{mem.get_context()}")

    # 4. Trigger Flush (Threshold is 5)
    print("\n--- Triggering Memory Flush ---")
    mem.commit_turn() # Should trigger flush because count is 5

    print(f"\nWorking Memory after flush: {len(mem.working_memory)} items")

    # Cleanup
    if Path("working_memory.jsonl").exists():
        os.remove("working_memory.jsonl")
    # Clean up archives if any were made
    for p in Path(".").glob("memory_archive_*.jsonl"):
        os.remove(p)


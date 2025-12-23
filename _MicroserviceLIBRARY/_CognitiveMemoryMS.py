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
from microservice_std_lib import service_metadata, service_endpoint, BaseService

# ==============================================================================
# CONFIGURATION
# ==============================================================================
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
        self.file_path = Path(self.config.get("persistence_path", DEFAULT_MEMORY_FILE))
        self.summarizer = self.config.get("summarizer_func")
        self.ingestor = self.config.get("long_term_ingest_func")
        
        self.working_memory: List[MemoryEntry] = []
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
        entry = MemoryEntry(role=role, content=content, metadata=metadata or {})
        self.working_memory.append(entry)
        self._append_to_file(entry)
        log.info(f"Added memory: [{role}] {content[:30]}...")
        return entry

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
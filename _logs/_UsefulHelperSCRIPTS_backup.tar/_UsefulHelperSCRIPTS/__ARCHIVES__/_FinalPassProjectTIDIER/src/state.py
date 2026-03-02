"""
PROJECT: _UsefulHelperSCRIPTS - Project Tidier
ROLE: App Runtime State Authority (The Spine)
"""
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from enum import Enum, auto

class AppPhase(Enum):
    IDLE = auto()
    INGESTING = auto()  # Scanning/Chunking
    THINKING = auto()   # AI Processing
    REVIEWING = auto()  # Blocked at the Gate
    COMMITTING = auto() # Writing to disk
    DONE = auto()
    ERROR = auto()

@dataclass
class AppRuntimeState:
    """
    Central authoritative state for the application lifecycle.
    Observers (UI, Recorder, Telemetry) read from here.
    Orchestrators (Backend) write to here.
    """
    phase: AppPhase = AppPhase.IDLE
    engine_running: bool = False
    engine_blocked: bool = False
    pending_review: Optional[Dict[str, Any]] = None
    last_event: Optional[str] = None
    active_path: Optional[str] = None

    def set_phase(self, new_phase: AppPhase, event_origin: str = None):
        """Updates the application phase and manages internal flags."""
        self.phase = new_phase
        self.last_event = event_origin
        
        # Automatic flag management based on phase
        if new_phase == AppPhase.IDLE:
            self.engine_running = False
            self.engine_blocked = False
        elif new_phase == AppPhase.INGESTING:
            self.engine_running = True
            self.engine_blocked = False
        elif new_phase == AppPhase.REVIEWING:
            self.engine_blocked = True
        elif new_phase in [AppPhase.DONE, AppPhase.ERROR]:
            self.engine_running = False
            self.engine_blocked = False
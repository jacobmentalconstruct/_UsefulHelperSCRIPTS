"""
SERVICE_NAME: _TelemetryServiceMS
ROLE: Authoritative Session Journal (Task 3)
"""
import logging
import queue
import time
import datetime
from typing import Dict, Any, Optional, List
from microservice_std_lib import service_metadata, service_endpoint
from event_contract import summarize_event, normalize_error

logger = logging.getLogger('TelemetryService')

@service_metadata(
    name='TelemetryService', 
    version='2.0.0', 
    description='Authoritative Session Journal: Maintains a structured event buffer and state snapshot.', 
    tags=['utility', 'logging', 'telemetry'], 
    capabilities=['event-journaling', 'state-snapshotting']
)
class TelemetryServiceMS:
    def __init__(self, state, config: Optional[Dict[str, Any]]=None):
        self.state_authority = state # The AppRuntimeState object
        self.config = config or {}
        
        # 1. Authoritative Journal Storage
        self.event_buffer: List[Dict[str, Any]] = []
        self.buffer_limit = self.config.get('buffer_limit', 1000)
        
        # 2. Local State Snapshot (Enriched for UI consumption)
        self.snapshot = {
            "phase": "IDLE",
            "active_file": None,
            "waiting_for_review": False,
            "current_model": "unknown",
            "last_error": None,
            "counters": {"errors": 0, "commits": 0, "hunks": 0}
        }

    def track(self, event_name: str, payload: Any = None, source: str = "system"):
        """Records a structured event into the ring buffer."""
        try:
            timestamp = datetime.datetime.now().strftime("%H:%M:%S")
            
            # Normalize payload if it's an error
            safe_payload = payload
            if "error" in event_name:
                safe_payload = normalize_error(payload)
                self.snapshot["last_error"] = safe_payload.get("message")
            
            if event_name == "model_swapped":
                self.snapshot["current_model"] = str(payload)
            
            entry = {
                "ts": timestamp,
                "event": event_name,
                "source": source,
                "payload": self._sanitize_payload(safe_payload),
                "summary": self._generate_summary(event_name, safe_payload)
            }

        self.event_buffer.append(entry)
        if len(self.event_buffer) > self.buffer_limit:
            self.event_buffer.pop(0)

        # Update local counters based on event type
        self._update_counters(event_name)
        
        # Emit signal that telemetry has updated (for future UI refresh)
        # Note: We use a try/except in case the bus isn't available during tests
        try:
            if hasattr(self, 'bus'):
                self.bus.emit("telemetry_updated", self.get_snapshot())
        except:
            pass

    def _sanitize_payload(self, payload: Any) -> Any:
        """Ensures payload is safe for storage and serialization."""
        if isinstance(payload, (str, int, float, bool, type(None))):
            return payload
        if isinstance(payload, dict):
            return {k: str(v)[:100] for k, v in payload.items()} # Limit string size
        return str(payload)[:200]

    def _generate_summary(self, event: str, payload: Any) -> str:
        """Uses the central event contract to generate a summary."""
        try:
            return summarize_event(event, payload)
        except Exception as e:
            return f"Event: {event} (Summary Error: {e})"

    def _update_counters(self, event: str):
        if "error" in event: self.snapshot["counters"]["errors"] += 1
        if "commit_success" == event: self.snapshot["counters"]["commits"] += 1
        if "hunk_ready_for_review" == event: self.snapshot["counters"]["hunks"] += 1

    def get_snapshot(self) -> Dict[str, Any]:
        """Returns a combined view of the authority state and local counters."""
        return {
            "phase": self.state_authority.phase.name,
            "engine_blocked": self.state_authority.engine_blocked,
            "active_file": self.state_authority.pending_review.get('file') if self.state_authority.pending_review else None,
            "current_model": self.snapshot["current_model"],
            "last_error": self.snapshot["last_error"],
            "counters": self.snapshot["counters"]
        }

    def get_recent_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.event_buffer[-limit:]

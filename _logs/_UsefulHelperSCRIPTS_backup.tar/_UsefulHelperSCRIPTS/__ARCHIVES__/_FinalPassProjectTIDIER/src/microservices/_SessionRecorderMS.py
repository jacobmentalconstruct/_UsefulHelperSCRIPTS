"""
SERVICE_NAME: _SessionRecorderMS
ENTRY_POINT: _SessionRecorderMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib
EXTERNAL_DEPENDENCIES: None
"""
import os
import datetime
import json
from typing import Dict, Any, Optional
from base_service import BaseService
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
    name='SessionRecorder', 
    version='1.0.0', 
    description='The Black Box: Records all project tidying events to a persistent audit log.', 
    tags=['utility', 'logging', 'audit'], 
    capabilities=['filesystem:write'], 
    internal_dependencies=['base_service', 'microservice_std_lib'], 
    external_dependencies=[]
)
class SessionRecorderMS(BaseService):
    """
    The Black Box.
    Listens to the SignalBus and writes a chronological record of all actions to disk.
    """

    def __init__(self, state, config: Optional[Dict[str, Any]] = None):
        super().__init__('SessionRecorder')
        self.state = state
        self.config = config or {}
        
        # Set up the log directory
        self.logs_dir = self.config.get('logs_dir', 'tidy_logs')
        os.makedirs(self.logs_dir, exist_ok=True)
        
        # Create a unique filename for this session
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self.logs_dir, f"tidy_session_{timestamp}.log")
        
        self.log_info(f"Session Recorder initialized. Logging to: {self.log_file}")
        self._write_entry("SESSION_START", {"msg": "Project Tidier session initiated."})

    def _write_entry(self, event_type: str, data: Any):
        """Writes a structured, timestamped entry to the log file."""
        timestamp = datetime.datetime.now().isoformat()
        entry = {
            "timestamp": timestamp,
            "event": event_type,
            "data": data
        }
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            self.log_error(f"Failed to write to audit log: {e}")

    # --- Signal Handlers ---

    def on_scan_started(self, data: Dict[str, Any]):
        self._write_entry("SCAN_INITIATED", data)

    def on_hunk_detected(self, data: Dict[str, Any]):
        # Log that clutter was found, including the filename and hunk name
        log_payload = {
            "file": data.get("file"),
            "hunk": data.get("hunk_name"),
            "chars_before": len(data.get("before", "")),
            "chars_after": len(data.get("after", ""))
        }
        self._write_entry("CLUTTER_DETECTED", log_payload)

    def on_user_decision(self, approved: bool):
        status = "APPROVED" if approved else "SKIPPED"
        # Record decision alongside the current authoritative state phase
        log_payload = {
            "status": status,
            "phase_at_decision": self.state.phase.name,
            "file_affected": self.state.pending_review.get('file') if self.state.pending_review else None
        }
        self._write_entry("USER_DECISION", log_payload)

    def on_commit_success(self, file_path: str):
        self._write_entry("FILE_COMMITTED", {"path": file_path})

if __name__ == '__main__':
    # Test Harness
    recorder = SessionRecorderMS({'logs_dir': '_test_logs'})
    recorder.on_scan_started({"paths": ["C:/test/project"]})
    recorder.on_hunk_detected({"file": "test.py", "hunk_name": "def test()", "before": "...", "after": ".."})
    print(f"Test entries written to: {recorder.log_file}")

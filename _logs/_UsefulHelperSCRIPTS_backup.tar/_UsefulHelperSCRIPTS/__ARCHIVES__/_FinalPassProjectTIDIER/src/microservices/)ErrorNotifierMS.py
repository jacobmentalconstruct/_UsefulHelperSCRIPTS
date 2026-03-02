"""
SERVICE_NAME: _ErrorNotifierMS
ROLE: Reactive Error Dispatcher (Task 3)
"""
import logging
from typing import Dict, Any, Optional
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
    name='ErrorNotifier', 
    version='1.0.0', 
    description='Reactive service that normalizes and dispatches engine errors to UI/Logs.', 
    tags=['utility', 'error-handling'], 
    capabilities=['ui-notification'], 
    internal_dependencies=['microservice_std_lib']
)
class ErrorNotifierMS:
    def __init__(self, bus):
        self.bus = bus
        self.logger = logging.getLogger("ErrorNotifier")

    def on_engine_error(self, payload: Dict[str, Any]):
        """
        Subscribed handler for engine failures.
        Safely extracts error details and emits normalized UI/Logging events.
        """
        # 1. Safely extract message with fallback
        msg = payload.get('message') or payload.get('msg') or "Unknown Engine Error"
        file_ctx = f" in {payload['file']}" if 'file' in payload else ""
        hunk_ctx = f" (Hunk: {payload['hunk_name']})" if 'hunk_name' in payload else ""
        
        full_report = f"❌ ENGINE ERROR: {msg}{file_ctx}{hunk_ctx}"

        # 2. Dispatch to the UI via the Signal Bus
        # This keeps the notifier decoupled from the UI implementation details
        self.bus.emit("notify_error", {"message": full_report, "level": "ERROR"})
        
        # 3. Log internally for standard output
        self.logger.error(full_report)

    def on_commit_failed(self, payload: Dict[str, Any]):
        """Handles failures during file write operations."""
        file_path = payload.get('file', 'unknown file')
        error = payload.get('error', 'unknown write error')
        
        report = f"💾 COMMIT FAILED: Could not update {file_path}. Error: {error}"
        self.bus.emit("notify_error", {"message": report, "level": "CRITICAL"})

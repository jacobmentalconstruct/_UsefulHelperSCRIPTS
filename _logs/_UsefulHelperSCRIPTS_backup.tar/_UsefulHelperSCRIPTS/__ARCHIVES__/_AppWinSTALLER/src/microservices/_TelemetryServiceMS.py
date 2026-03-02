import logging
import queue
import time
from typing import Dict, Any, Optional

from microservice_std_lib import service_metadata, service_endpoint

logger = logging.getLogger("TelemetryService")

# ==============================================================================
# HELPER CLASS
# ==============================================================================

class QueueHandler(logging.Handler):
    """
    Custom logging handler that pushes log records into a thread-safe queue.
    """
    def __init__(self, log_queue: queue.Queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        # We format the record before putting it in the queue so the message field exists
        self.format(record)
        self.log_queue.put(record)

# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="TelemetryService",
    version="1.0.0",
    description="The Nervous System: Watches the thread-safe LogQueue and updates GUI components with real-time status.",
    tags=["utility", "logging", "telemetry"],
    capabilities=["log-redirection", "real-time-updates"]
)
class TelemetryServiceMS:
    """
    The Nervous System.
    Watches the thread-safe LogQueue and updates the GUI Panels.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        
        # Dependencies injected via config
        self.root = self.config.get("root")
        self.panels = self.config.get("panels")
        
        self.log_queue = queue.Queue()
        self.start_time = time.time()
        self._heartbeat_count = 0
        
        # We set up the global logging hook HERE, inside the service
        self._setup_logging_hook()

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float", "queue_depth": "int"},
        description="Standardized health check to verify the operational state of the telemetry pipeline.",
        tags=["diagnostic", "health"],
        side_effects=[]
    )
    def get_health(self) -> Dict[str, Any]:
        """Returns the operational status of the TelemetryServiceMS."""
        return {
            "status": "online",
            "uptime": time.time() - self.start_time,
            "queue_depth": self.log_queue.qsize()
        }

    def _setup_logging_hook(self):
        """Redirects Python's standard logging to our Queue."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Create our custom handler that feeds the queue
        q_handler = QueueHandler(self.log_queue)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        q_handler.setFormatter(formatter)
        root_logger.addHandler(q_handler)

    @service_endpoint(
        inputs={},
        outputs={},
        description="Initiates the telemetry service and begins the asynchronous GUI log-polling loop.",
        tags=["lifecycle", "event-loop"],
        mode="async",
        side_effects=["ui:update"]
    )
    def start(self):
        """Begins the GUI update loop."""
        logger.info("Telemetry Service starting...")
        self._poll_queue()

    @service_endpoint(
        inputs={},
        outputs={"alive": "bool", "heartbeat": "int"},
        description="Verifies that the GUI polling loop is actively processing the log queue.",
        tags=["diagnostic", "heartbeat"],
        side_effects=[]
    )
    def ping(self) -> Dict[str, Any]:
        """Allows an agent to verify the pulse of the UI loop."""
        return {"alive": True, "heartbeat": self._heartbeat_count}

    def _poll_queue(self):
        """The heartbeat that drains the queue into the GUI."""
        if not self.root or not self.panels:
            return

        self._heartbeat_count += 1
        try:
            while True:
                record = self.log_queue.get_nowait()
                # record.message is populated by QueueHandler calling format()
                msg = f"[{record.levelname}] {record.message}" 
                
                # Update the GUI
                if hasattr(self.panels, 'log'):
                    self.panels.log(msg)
                
        except queue.Empty:
            pass
        finally:
            # Check again in 100ms
            if hasattr(self.root, 'after'):
                self.root.after(100, self._poll_queue)


# --- Independent Test Block ---
if __name__ == "__main__":
    # Mock objects for independent test
    class MockRoot: 
        def after(self, ms, func): 
            # Simulate a loop schedule
            pass

    class MockPanels:
        def log(self, msg): 
            print(f"[UI LOG]: {msg}")
    
    # Initialize
    svc = TelemetryServiceMS({"root": MockRoot(), "panels": MockPanels()})
    print("Service ready:", svc)
    
    # Generate a log
    logger.info("Internal test message")
    
    # Manually trigger one poll cycle to verify it picks up the log
    svc._poll_queue()
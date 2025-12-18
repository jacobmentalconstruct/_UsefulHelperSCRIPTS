import logging
import queue
from .base_service import BaseService
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
    name="TelemetryService",
    version="1.0.0",
    description="The Nervous System: Watches the thread-safe LogQueue and updates GUI components with real-time status.",
    tags=["utility", "logging", "telemetry"],
    capabilities=["log-redirection", "real-time-updates"]
)
class TelemetryService(BaseService):
    """
    The Nervous System.
    Watches the thread-safe LogQueue and updates the GUI Panels.
    """
    def __init__(self, root, panels):
        super().__init__("TelemetryService")
        self.root = root
        self.panels = panels
        self.log_queue = queue.Queue()
        
        # We set up the global logging hook HERE, inside the service
        self._setup_logging_hook()

    def _setup_logging_hook(self):
        """Redirects Python's standard logging to our Queue."""
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        
        # Create our custom handler that feeds the queue
        q_handler = QueueHandler(self.log_queue)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        q_handler.setFormatter(formatter)
        logger.addHandler(q_handler)

    @service_endpoint(
        inputs={},
        outputs={},
        description="Initiates the telemetry service and begins the asynchronous GUI log-polling loop.",
        tags=["lifecycle", "event-loop"],
        mode="async"
    )
    def start(self):
        """Begins the GUI update loop."""
        self.log_info("Telemetry Service starting...")
        self._poll_queue()

    def _poll_queue(self):
        """The heartbeat that drains the queue into the GUI."""
        try:
            while True:
                record = self.log_queue.get_nowait()
                msg = f"[{record.levelname}] {record.message}" # Removed \n because .log() adds it
                
                # Update the GUI
                self.panels.log(msg)
                
        except queue.Empty:
            pass
        finally:
            # Check again in 100ms
            self.root.after(100, self._poll_queue)

# Helper Class for the Queue
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue

    def emit(self, record):
        self.format(record)
        self.log_queue.put(record)

    if __name__ == "__main__":
    # Mock objects for independent test
    class MockRoot: 
        def after(self, ms, func): print(f"Loop scheduled for {ms}ms")
    class MockPanels:
        def log(self, msg): print(f"UI LOG: {msg}")
    
    svc = TelemetryService(MockRoot(), MockPanels())
    print("Service ready:", svc._service_info["name"])
    svc.log_info("Internal test message")
    svc._poll_queue()



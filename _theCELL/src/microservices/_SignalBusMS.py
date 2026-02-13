"""
SERVICE_NAME: _SignalBusMS
ENTRY_POINT: _SignalBusMS.py
INTERNAL_DEPENDENCIES: base_service, microservice_std_lib
EXTERNAL_DEPENDENCIES: None
"""
import logging
import threading
from typing import Dict, List, Any, Optional, Callable
from .base_service import BaseService
from .microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
    name='SignalBus', 
    version='1.0.0', 
    description='The Spine: A central pub/sub event hub for decoupled communication between services.', 
    tags=['utility', 'events', 'communication'], 
    capabilities=['pub-sub', 'event-routing'], 
    internal_dependencies=['base_service', 'microservice_std_lib'], 
    external_dependencies=[]
)
class SignalBusMS(BaseService):
    """
    The Spine.
    Provides a thread-safe mechanism for services to subscribe to and emit named signals.
    """
    
    # --- Standard Event Contracts ---
    SIGNAL_PROCESS_START = "process_start"
    SIGNAL_PROCESS_COMPLETE = "process_complete"
    SIGNAL_SPAWN_REQUESTED = "cell_spawn_requested"
    SIGNAL_LOG_APPEND = "log_append"
    SIGNAL_ERROR = "notify_error"

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__('SignalBus')
        self.config = config or {}
        self._subscribers: Dict[str, List[Callable]] = {}
        self._lock = threading.RLock()

    @service_endpoint(
        inputs={'signal_name': 'str', 'callback': 'Callable'}, 
        outputs={}, 
        description='Registers a callback function to trigger when a specific signal is emitted.', 
        tags=['events', 'subscribe']
    )
    # ROLE: Registers a callback function to trigger when a specific signal is emitted.
    # INPUTS: {"callback": "Callable", "signal_name": "str"}
    # OUTPUTS: {}
    def subscribe(self, signal_name: str, callback: Callable):
        """Adds a listener for a specific signal."""
        with self._lock:
            if signal_name not in self._subscribers:
                self._subscribers[signal_name] = []
            if callback not in self._subscribers[signal_name]:
                self._subscribers[signal_name].append(callback)
                self.log_info(f"New subscriber for signal: {signal_name}")

    @service_endpoint(
        inputs={'signal_name': 'str', 'data': 'Any'}, 
        outputs={'delivered_to': 'int'}, 
        description='Broadcasts data to all subscribers of a specific signal.', 
        tags=['events', 'emit']
    )
    # ROLE: Broadcasts data to all subscribers of a specific signal.
    # INPUTS: {"data": "Any", "signal_name": "str"}
    # OUTPUTS: {"delivered_to": "int"}
    def emit(self, signal_name: str, data: Any = None) -> int:
        """Broadcasts a signal to all registered listeners."""
        count = 0
        with self._lock:
            listeners = self._subscribers.get(signal_name, []).copy()
        
        if listeners:
            self.log_info(f"Emitting signal: {signal_name}")
            for callback in listeners:
                try:
                    # Trigger the callback with the data payload
                    callback(data)
                    count += 1
                except Exception as e:
                    self.log_error(f"Error in signal '{signal_name}' callback: {e}")
        
        return count

    @service_endpoint(
        inputs={'signal_name': 'str', 'callback': 'Callable'}, 
        outputs={}, 
        description='Removes a previously registered callback.', 
        tags=['events', 'unsubscribe']
    )
    # ROLE: Removes a previously registered callback.
    # INPUTS: {"callback": "Callable", "signal_name": "str"}
    # OUTPUTS: {}
    def unsubscribe(self, signal_name: str, callback: Callable):
        """Removes a listener from a signal."""
        with self._lock:
            if signal_name in self._subscribers:
                try:
                    self._subscribers[signal_name].remove(callback)
                    self.log_info(f"Unsubscribed from signal: {signal_name}")
                except ValueError:
                    pass

if __name__ == '__main__':
    # Test Harness
    bus = SignalBusMS()
    
    def on_hunk_ready(data):
        print(f"UI received hunk: {data}")

    print("--- Testing SignalBusMS ---")
    bus.subscribe("hunk_processed", on_hunk_ready)
    
    # Simulate a backend event
    delivered = bus.emit("hunk_processed", {"file": "app.py", "lines": 50})
    print(f"Signal delivered to {delivered} listeners.")


import time
import threading
import enum
import queue
import logging
from typing import Dict, List, Any, Optional

# --- Import Microservices ---
# We assume these are available in the path as per your tree
from microservices._CartridgeServiceMS import CartridgeServiceMS
from microservices._IntakeServiceMS import IntakeServiceMS
from microservices._RefineryServiceMS import RefineryServiceMS
from microservices._NeuralServiceMS import NeuralServiceMS
from microservices._TelemetryServiceMS import TelemetryServiceMS

# --- State Machine Definitions ---
class ForgeState(enum.Enum):
    EMPTY = "EMPTY"                     # No cartridge loaded
    CARTRIDGE_SELECTED = "CARTRIDGE_SELECTED" # DB file valid
    SCANNING = "SCANNING"               # Scout is looking at files
    SCANNED = "SCANNED"                 # Tree built, waiting for selection
    INGESTING = "INGESTING"             # Copying raw data to DB
    INGESTED = "INGESTED"               # Raw data ready
    REFINING = "REFINING"               # Chunking/Embedding in progress
    READY = "READY"                     # Idle, ready for query/export
    ERROR = "ERROR"                     # Something broke
    CANCELLED = "CANCELLED"             # User stopped operation

class ForgeEvent:
    """Standardized Event Payload for the UI"""
    def __init__(self, event_type: str, data: Any = None):
        self.type = event_type
        self.data = data
        self.timestamp = time.time()

# --- The Orchestrator ---
class ForgeOrchestrator:
    """
    The Spine of the Factory.
    Owns sequencing, state, events, cancellation, and retries.
    Does NOT contain widget code.
    """
    
    def __init__(self, telemetry_svc: TelemetryServiceMS):
        self.telemetry = telemetry_svc
        self.logger = logging.getLogger("ForgeOrchestrator")
        
        # State
        self._state = ForgeState.EMPTY
        self._stop_event = threading.Event()
        self._current_plan: Optional[Dict] = None # The Registry/Plan
        
        # Services (Lazy loaded or Init here)
        self.cartridge: Optional[CartridgeServiceMS] = None
        self.intake: Optional[IntakeServiceMS] = None
        self.refinery: Optional[RefineryServiceMS] = None
        
        # We initialize Neural service immediately as it doesn't depend on a specific DB
        self.neural = NeuralServiceMS()

        # Emit initial state
        self._emit_state()

    # --- State Management ---
    
    def get_state(self) -> str:
        return self._state.value

    def _set_state(self, new_state: ForgeState):
        self._state = new_state
        self._emit_state()
        self.logger.info(f"State Transition -> {new_state.value}")

    def _emit_state(self):
        # We push a state change event to the log queue which Telemetry picks up
        # Ideally, Telemetry service might have a dedicated event bus, 
        # but for now we log it structurally.
        self.logger.info(f"STATE_CHANGED::{self._state.value}")

    # --- Public API (As defined in ORCHESTRATION_LAYER.md) ---

    def select_cartridge(self, db_path: str):
        """Initializes the Cartridge Service with a specific DB file."""
        try:
            self.logger.info(f"Selecting Cartridge: {db_path}")
            self.cartridge = CartridgeServiceMS(db_path)
            
            # Check if it's new or existing
            stats = self.cartridge.get_status_summary()
            
            # Init dependent services
            self.intake = IntakeServiceMS(self.cartridge)
            
            # Refinery needs Cartridge AND Neural
            self.refinery = RefineryServiceMS({
                "cartridge": self.cartridge,
                "neural": self.neural
            })
            
            self._set_state(ForgeState.CARTRIDGE_SELECTED)
            
            # If cartridge has data, we might auto-advance state
            if stats['files'] > 0:
                self._set_state(ForgeState.INGESTED)
            if stats['chunks'] > 0:
                self._set_state(ForgeState.READY)
                
            return stats
            
        except Exception as e:
            self.logger.error(f"Failed to load cartridge: {e}")
            self._set_state(ForgeState.ERROR)
            raise e

    def scan(self, source_path: str, web_depth: int = 0):
        """
        Phase 1: Analyze.
        Scans source, returns a tree, does NOT write to DB.
        """
        if self._state not in [ForgeState.CARTRIDGE_SELECTED, ForgeState.READY, ForgeState.SCANNED]:
            self.logger.warning("Invalid state for SCAN command.")
            return

        self._set_state(ForgeState.SCANNING)
        self._stop_event.clear()

        def _worker():
            try:
                self.logger.info(f"Scanning source: {source_path}")
                tree = self.intake.scan_path(source_path, web_depth)
                
                if self._stop_event.is_set():
                    self._set_state(ForgeState.CANCELLED)
                    return

                # Store the plan in memory (The Registry)
                self._current_plan = tree
                
                self.logger.info("Scan Complete. Waiting for user approval.")
                self._set_state(ForgeState.SCANNED)
                
                # Emit result for UI to render
                # In a real event bus, we'd emit the object. 
                # For now, the UI will likely pull `orchestrator.get_last_scan_tree()`
                
            except Exception as e:
                self.logger.error(f"Scan failed: {e}")
                self._set_state(ForgeState.ERROR)

        threading.Thread(target=_worker, daemon=True).start()

    def get_last_scan_tree(self):
        """UI calls this to render the tree after SCAN_COMPLETE."""
        return self._current_plan

    def ingest(self, selected_files: List[str], root_path: str):
        """
        Phase 2: Commit.
        Writes the user-approved list of files into the Cartridge (RAW storage).
        """
        if self._state != ForgeState.SCANNED:
            self.logger.warning("Must SCAN before INGEST.")
            return

        self._set_state(ForgeState.INGESTING)
        self._stop_event.clear()

        def _worker():
            try:
                self.logger.info(f"Ingesting {len(selected_files)} files...")
                stats = self.intake.ingest_selected(selected_files, root_path)
                
                if self._stop_event.is_set():
                    self._set_state(ForgeState.CANCELLED)
                    return

                self.logger.info(f"Ingest Complete. Stats: {stats}")
                self._set_state(ForgeState.INGESTED)
                
            except Exception as e:
                self.logger.error(f"Ingest failed: {e}")
                self._set_state(ForgeState.ERROR)

        threading.Thread(target=_worker, daemon=True).start()

    def refine_until_idle(self, batch_size=5):
        """
        Phase 3: Refine.
        Loops through pending files and processes them until done.
        """
        if self._state not in [ForgeState.INGESTED, ForgeState.READY]:
            self.logger.warning("Invalid state for REFINE command.")
            return

        self._set_state(ForgeState.REFINING)
        self._stop_event.clear()

        def _worker():
            total_processed = 0
            while not self._stop_event.is_set():
                try:
                    # 1. Process a batch
                    count = self.refinery.process_pending(batch_size=batch_size)
                    
                    if count == 0:
                        # Done!
                        self.logger.info(f"Refinery finished. Total processed: {total_processed}")
                        self._set_state(ForgeState.READY)
                        break
                    
                    total_processed += count
                    self.logger.info(f"Refined batch of {count}. Total so far: {total_processed}")
                    
                except Exception as e:
                    self.logger.error(f"Refinery error: {e}")
                    self._set_state(ForgeState.ERROR)
                    break
            
            if self._stop_event.is_set():
                self.logger.warning("Refinery CANCELLED by user.")
                self._set_state(ForgeState.CANCELLED)

        threading.Thread(target=_worker, daemon=True).start()

    def cancel(self):
        """Signals background threads to stop safely."""
        self.logger.warning("Cancellation requested...")
        self._stop_event.set()

    # --- Validation / Export ---

    def validate(self):
        """Runs the validation suite on the cartridge."""
        if not self.cartridge: return {}
        report = self.cartridge.validate_cartridge()
        self.logger.info(f"Validation Report: {report}")
        return report
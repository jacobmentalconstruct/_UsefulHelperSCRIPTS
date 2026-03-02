"""
PROJECT: _UsefulHelperSCRIPTS - Project Tidier
ROLE: Entry Point & Signal Bridge (The Ignition)
"""
import sys
import os
import logging
from pathlib import Path

# --- PATH INJECTION ---
# This allows microservices to find 'base_service' and each other
current_dir = Path(__file__).parent.resolve()
sys.path.insert(0, str(current_dir))                # Adds 'src'
sys.path.insert(0, str(current_dir / "microservices")) # Adds 'src/microservices'

# Standard Imports
from _SignalBusMS import SignalBusMS
from backend import ProjectTidierBackend
from ui import ProjectTidierUI
from _SessionRecorderMS import SessionRecorderMS
from _TelemetryServiceMS import TelemetryServiceMS
from _ErrorNotifierMS import ErrorNotifierMS
from _PromptComposerMS import PromptComposerMS
from _ConfigStoreMS import ConfigStoreMS
from _RulesEngineMS import RulesEngineMS
from state import AppRuntimeState

def main():
    # 1. Start the Signal Bus and Shared State
    bus = SignalBusMS()
    state = AppRuntimeState()

    # 2. Start the Auditor (The Black Box)
    recorder = SessionRecorderMS(state)

    # 3. Start Telemetry (The Nervous System)
    telemetry = TelemetryServiceMS(state)

    # 4. Start Persistence & Persona
    config_store = ConfigStoreMS()
    notifier = ErrorNotifierMS(bus)
    prompt_composer = PromptComposerMS()
    rules_engine = RulesEngineMS()

    # Restore saved persona and rules if present
    saved_rules = config_store.get("ruleset")
    if saved_rules: rules_engine.set_rules(saved_rules)
    saved_template = config_store.get("prompt_template")
    if saved_template:
        prompt_composer.set_template(saved_template)

    # 5. Instantiate the Pillars with State Access
    backend = ProjectTidierBackend(bus, state, prompt_composer, rules_engine)
    ui = ProjectTidierUI(bus, state, telemetry)

    # 3. Establish Explicit Wiring
    bus.subscribe("start_tidy_process", backend._handle_start_request)
    bus.subscribe("hunk_ready_for_review", ui.display_review_hunk)
    bus.subscribe("user_approve_hunk", backend._handle_user_decision)
    
    # Prompt & Persona Wiring
    bus.subscribe("prompt_template_updated", prompt_composer.set_template)
    bus.subscribe("prompt_template_updated", lambda d: config_store.set("prompt_template", d))
    bus.subscribe("model_swapped", lambda m: config_store.set("last_model", m))
    bus.subscribe("prompt_template_requested", lambda _: bus.emit("prompt_template_current", prompt_composer.get_template()))
    bus.subscribe("prompt_template_current", ui.load_prompt_template)
    
    # Rules Wiring
    bus.subscribe("rules_updated", rules_engine.set_rules)
    bus.subscribe("rules_updated", lambda d: config_store.set("ruleset", d))
    bus.subscribe("rules_requested", lambda _: bus.emit("rules_current", rules_engine.get_rules()))
    bus.subscribe("rules_current", ui.load_rules)
    bus.subscribe("rules_blocked_hunk", lambda d: telemetry.track("rules_blocked_hunk", d))

    # Telemetry Journaling (Authoritative Tracking)
    bus.subscribe("start_tidy_process", lambda data: telemetry.track("start_tidy_process", data))
    bus.subscribe("model_swapped", lambda data: telemetry.track("model_swapped", data))
    bus.subscribe("hunk_ready_for_review", lambda data: telemetry.track("hunk_ready_for_review", data))
    bus.subscribe("user_approve_hunk", lambda data: telemetry.track("user_approve_hunk", data))
    bus.subscribe("commit_success", lambda data: telemetry.track("commit_success", data))
    bus.subscribe("engine_error", lambda data: telemetry.track("engine_error", data))
    bus.subscribe("prompt_template_updated", lambda data: telemetry.track("prompt_template_updated", data))

    # Error & Notification Wiring
    bus.subscribe("engine_error", notifier.on_engine_error)
    bus.subscribe("commit_failed", notifier.on_commit_failed)
    bus.subscribe("notify_error", lambda d: ui.console.display_event({"ts": "ERROR", "summary": d["message"], "event": "error"}))

    # Trigger UI Refresh Loop
    ui.refresh_from_telemetry()
    
    # Push initial config state to listeners
    bus.emit("config_loaded", config_store.data)

    # Push initial config state to listeners
    bus.emit("config_loaded", config_store.data)

    # Auditor Subscriptions
    bus.subscribe("start_tidy_process", recorder.on_scan_started)
    bus.subscribe("hunk_ready_for_review", recorder.on_hunk_detected)
    bus.subscribe("user_approve_hunk", recorder.on_user_decision)
    bus.subscribe("commit_success", recorder.on_commit_success)

    # 4. Ignition
    print("Project Tidier Initialized. Launching UI...")
    ui.launch()

if __name__ == "__main__":
    main()














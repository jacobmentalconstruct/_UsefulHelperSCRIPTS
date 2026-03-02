"""
PROJECT: _UsefulHelperSCRIPTS - Project Tidier
ROLE: Event Normalization Helpers (Task 3.3)
"""
def summarize_event(event_name, payload) -> str:
    """Generates a consistent human-readable summary for any event."""
    if not payload: return f"Event: {event_name}"
    
    mapping = {
        "engine_error": lambda p: f"❌ {p.get('message', 'Unknown Error')}",
        "hunk_ready_for_review": lambda p: f"👀 Reviewing {p.get('file', 'file')}",
        "commit_success": lambda p: f"✅ Committed {p}",
        "start_tidy_process": lambda p: "🚀 Engine Started",
        "model_swapped": lambda p: f"🤖 Model -> {p}",
        "user_approve_hunk": lambda p: "👍 Approved" if p else "⏭️ Skipped",
        "rules_blocked_hunk": lambda p: f"🛡️ Rules Blocked: {p.get('reason')} ({p.get('file')})"
            }
    return mapping.get(event_name, lambda p: f"Event: {event_name}")(payload)

def normalize_error(payload) -> dict:
    """Ensures error payloads always contain critical fields."""
    if isinstance(payload, str): return {"message": payload}
    return {
        "message": payload.get("message") or payload.get("msg") or "Unknown error",
        "file": payload.get("file", "N/A"),
        "hunk_name": payload.get("hunk_name", "N/A")
    }

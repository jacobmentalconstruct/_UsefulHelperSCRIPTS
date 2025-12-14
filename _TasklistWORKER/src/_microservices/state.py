def new_state() -> dict:
    """Create a fresh state object for the Tasklist Chat Prototype.

    Structure notes:
      - chat: conversational inputs + last outputs
      - working: per-step artifacts (outputs, thought bubbles, errors)
      - outputs: final result produced by the tasklist runner
    """
    return {
        "chat": {
            "history": [],            # list of {"role": "user"|"assistant", "content": str}
            "last_user": "",          # last user message
            "last_response": ""       # last model output (string form)
        },
        "working": {
            "step_outputs": {},       # dict step_id -> output (text or parsed json)
            "thoughts": [],           # list of {step_id, name, summary}
            "notes": []               # list of {step_id, name, errors:[...]}
        },
        "outputs": {
            "final": ""              # final assistant message to display in chat
        }
    }


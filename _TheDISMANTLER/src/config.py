"""
AppConfig – Lightweight JSON-based user preferences persistence.
Stored in ~/.dismantler_prefs.json so preferences survive across runs.

Usage:
    import config
    show = config.get("show_console")     # read one key
    config.set_pref("show_console", False) # write one key
    prefs = config.load()                  # read all
    config.save(prefs)                     # write all
"""
import json
import os

# Stored in the user's home directory so it survives app reinstalls
_CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".dismantler_prefs.json")

# All available keys and their factory defaults
_DEFAULTS: dict = {
    "show_console": True,
}


def load() -> dict:
    """
    Load all preferences from disk.
    Returns a merged dict of saved values + any new default keys.
    Falls back to defaults silently on missing or corrupt file.
    """
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Merge: saved values override defaults; unknown saved keys are kept
        return {**_DEFAULTS, **data}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return dict(_DEFAULTS)


def save(prefs: dict) -> None:
    """Persist a full preferences dict to disk. Silently ignores write errors."""
    try:
        with open(_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(prefs, f, indent=2)
    except OSError:
        pass


def get(key: str):
    """Return the stored value for *key*, or its default if not set."""
    return load().get(key, _DEFAULTS.get(key))


def set_pref(key: str, value) -> None:
    """Update a single key and immediately persist."""
    prefs = load()
    prefs[key] = value
    save(prefs)

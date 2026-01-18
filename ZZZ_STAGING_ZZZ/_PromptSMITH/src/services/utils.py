# src/services/utils.py
import traceback
from functools import wraps
from tkinter import messagebox


def safe_ui_call(user_message: str):
    """
    Decorator for UI callbacks:
      - Shows a messagebox with full traceback on error.
      - Prevents hard crashes on malformed schema, DB lock errors, etc.
    """
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                return fn(*args, **kwargs)
            except Exception:
                tb = traceback.format_exc()
                messagebox.showerror("Error", f"{user_message}\n\n{tb}")
                return None
        return wrapper
    return decorator

"""
CancellationTokenMS
-------------------
Thread-safe cancellation token for long-running operations.

Responsibilities:
- Provide a shared cancellation state (set/cancel/reset)
- Provide polling-friendly predicate: token.is_cancelled()
- Provide optional "reason" string
- Provide a lightweight context manager for scoped cancellation reset

Non-goals:
- Threading orchestration (Backend orchestrator owns threads)
- Timeouts / scheduling
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock
from typing import Optional


@dataclass(frozen=True)
class CancelState:
    cancelled: bool
    reason: Optional[str] = None


class CancellationTokenMS:
    def __init__(self):
        self._event = Event()
        self._lock = Lock()
        self._reason: Optional[str] = None

    # -------------------------
    # Control
    # -------------------------

    def cancel(self, reason: Optional[str] = None) -> None:
        with self._lock:
            self._reason = reason
            self._event.set()

    def reset(self) -> None:
        with self._lock:
            self._reason = None
            self._event.clear()

    # -------------------------
    # Query
    # -------------------------

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    def reason(self) -> Optional[str]:
        with self._lock:
            return self._reason

    def snapshot(self) -> CancelState:
        with self._lock:
            return CancelState(cancelled=self._event.is_set(), reason=self._reason)

    # -------------------------
    # Convenience
    # -------------------------

    def predicate(self):
        """
        Return a no-arg callable usable as cancel() injection in services:
            cancel = token.predicate()
            if cancel(): ...
        """
        return self.is_cancelled

    def __enter__(self):
        self.reset()
        return self

    def __exit__(self, exc_type, exc, tb):
        # Do not auto-cancel; just leave state as-is.
        return False


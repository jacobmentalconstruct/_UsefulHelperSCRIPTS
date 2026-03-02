"""
ProgressEventBusMS
------------------
A tiny pub/sub event bus for progress + logging events.

Responsibilities:
- Allow microservices/orchestrators to publish progress events
- Allow UI layer to subscribe/unsubscribe handlers
- Keep it thread-safe enough for "publish from worker thread, handle on UI thread"
  (UI should marshal events to Tk via after(); this bus just delivers callbacks)

Event Model:
- Each event is a dict with at minimum:
    {"type": "...", "message": "...", "level": "info|warn|error", "meta": {...}}

Non-goals:
- Tkinter after() marshalling
- Persistent logging
- Complex routing / filtering (keep it minimal + deterministic)
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Dict, List, Optional


ProgressHandler = Callable[[Dict[str, Any]], None]


@dataclass(frozen=True)
class ProgressEvent:
    type: str
    message: str
    level: str = "info"
    meta: Dict[str, Any] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "level": self.level,
            "meta": dict(self.meta or {}),
        }


class ProgressEventBusMS:
    def __init__(self):
        self._lock = Lock()
        self._subs: List[ProgressHandler] = []

    # -------------------------
    # Subscribe / Unsubscribe
    # -------------------------

    def subscribe(self, handler: ProgressHandler) -> None:
        with self._lock:
            if handler not in self._subs:
                self._subs.append(handler)

    def unsubscribe(self, handler: ProgressHandler) -> None:
        with self._lock:
            if handler in self._subs:
                self._subs.remove(handler)

    def clear(self) -> None:
        with self._lock:
            self._subs.clear()

    # -------------------------
    # Publish
    # -------------------------

    def publish(self, event: Dict[str, Any]) -> None:
        """
        Publish a raw dict event. This makes the bus flexible.
        Handlers should be resilient to missing keys.
        """
        with self._lock:
            subs = list(self._subs)

        for h in subs:
            try:
                h(event)
            except Exception:
                # Bus is intentionally silent; logging belongs elsewhere.
                pass

    def emit(
        self,
        *,
        type: str,
        message: str,
        level: str = "info",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.publish(
            {
                "type": type,
                "message": message,
                "level": level,
                "meta": dict(meta or {}),
            }
        )

    # -------------------------
    # Convenience helpers
    # -------------------------

    def make_logger(self, prefix: str = "") -> Callable[[str], None]:
        """
        Returns a simple function you can pass as `log=` to other services:
            log = bus.make_logger("crawl")
            log("hello") -> emits {"type":"log", "message":"[crawl] hello", ...}
        """
        pfx = f"[{prefix}] " if prefix else ""

        def _log(msg: str) -> None:
            self.emit(type="log", message=pfx + str(msg), level="info")

        return _log


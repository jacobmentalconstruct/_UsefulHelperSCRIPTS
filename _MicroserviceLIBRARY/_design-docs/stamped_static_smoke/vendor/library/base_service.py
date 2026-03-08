"""
Compatibility base service used by legacy microservices.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


class BaseService:
    """
    Minimal compatibility base class for legacy microservices.
    """

    def __init__(self, service_name: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        self.service_name = service_name or self.__class__.__name__
        self.config = config or {}
        self.start_time = time.time()

    def configure(self, **kwargs: Any) -> Dict[str, Any]:
        self.config.update(kwargs)
        return dict(self.config)

    def get_health(self) -> Dict[str, Any]:
        return {
            "status": "online",
            "service": self.service_name,
            "uptime": time.time() - self.start_time,
        }


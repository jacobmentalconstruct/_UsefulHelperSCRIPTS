"""
ErrorNormalizerMS
-----------------
Normalize exceptions + error payloads into stable, UI-friendly strings/dicts.

Responsibilities:
- Convert exceptions (and arbitrary error-like objects) into:
    - short code (category)
    - human message
    - detail string (traceback optional)
- Provide deterministic formatting
- Optionally include traceback for logs, not for UI toast

Non-goals:
- Logging sink (ProgressEventBusMS can publish)
- Retrying logic
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple


@dataclass(frozen=True)
class NormalizedError:
    code: str
    message: str
    detail: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        out = {"code": self.code, "message": self.message}
        if self.detail:
            out["detail"] = self.detail
        return out


class ErrorNormalizerMS:
    def normalize(
        self,
        err: Any,
        *,
        include_traceback: bool = False,
        tb_limit: int = 20,
    ) -> NormalizedError:
        """
        Convert err into NormalizedError. Never raises.
        """
        if err is None:
            return NormalizedError(code="none", message="No error")

        # Already normalized
        if isinstance(err, NormalizedError):
            return err

        # String error
        if isinstance(err, str):
            return NormalizedError(code="error", message=err)

        # Exception
        if isinstance(err, BaseException):
            code = err.__class__.__name__
            msg = str(err) or code
            detail = None
            if include_traceback:
                detail = "".join(traceback.format_exception(type(err), err, err.__traceback__, limit=tb_limit)).strip()
            return NormalizedError(code=code, message=msg, detail=detail)

        # Dict-like error
        if isinstance(err, dict):
            code = str(err.get("code", "error"))
            msg = str(err.get("message", "Unknown error"))
            detail = err.get("detail", None)
            if detail is not None:
                detail = str(detail)
            return NormalizedError(code=code, message=msg, detail=detail)

        # Fallback
        return NormalizedError(code=err.__class__.__name__, message=str(err))


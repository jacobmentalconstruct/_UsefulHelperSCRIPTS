"""
InferenceResultValidatorMS
--------------------------
Validate and normalize LLM outputs produced for UnknownCase inference.

Responsibilities:
- Parse JSON safely (string -> dict)
- Validate schema:
    {
      "results": [
        {
          "case_id": str,
          "classification": oneof(...),
          "confidence": float [0..1],
          "extracted": {
            "widget_type": str|null,
            "parent": str|null,
            "event": str|null,
            "handler": str|null,
            "method": str|null
          },
          "notes": str
        }
      ]
    }
- Normalize types (confidence clamp, missing keys -> null/empty)
- Provide clear error info for UI/HITL display

Non-goals:
- Applying results to UiMap (orchestrator does that)
- Retrying prompts / repair (HitlDecisionRouterMS or orchestrator does that)
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# -------------------------
# Data Structures
# -------------------------

_ALLOWED_CLASSIFICATIONS = {
    "widget_ctor",
    "layout_call",
    "config_call",
    "bind_call",
    "menu_call",
    "callback_target",
    "window_call",
    "unknown",
}

_EXTRACTED_KEYS = {"widget_type", "parent", "event", "handler", "method"}


@dataclass(frozen=True)
class ValidationError:
    message: str
    detail: Optional[str] = None


@dataclass(frozen=True)
class ValidatedResult:
    case_id: str
    classification: str
    confidence: float
    extracted: Dict[str, Optional[str]]
    notes: str


@dataclass(frozen=True)
class ValidationOutcome:
    ok: bool
    results: List[ValidatedResult]
    errors: List[ValidationError]


# -------------------------
# Service
# -------------------------

class InferenceResultValidatorMS:
    def validate_json_text(self, text: str) -> ValidationOutcome:
        """
        Parse + validate. Never raises.
        """
        if text is None:
            return ValidationOutcome(ok=False, results=[], errors=[ValidationError("empty_text")])

        s = text.strip()
        if not s:
            return ValidationOutcome(ok=False, results=[], errors=[ValidationError("empty_text")])

        try:
            obj = json.loads(s)
        except Exception as e:
            return ValidationOutcome(ok=False, results=[], errors=[ValidationError("json_parse_error", detail=str(e))])

        return self.validate_obj(obj)

    def validate_obj(self, obj: Any) -> ValidationOutcome:
        errors: List[ValidationError] = []
        results: List[ValidatedResult] = []

        if not isinstance(obj, dict):
            return ValidationOutcome(ok=False, results=[], errors=[ValidationError("root_not_object")])

        res_list = obj.get("results", None)
        if not isinstance(res_list, list):
            return ValidationOutcome(ok=False, results=[], errors=[ValidationError("missing_or_invalid_results_list")])

        for i, item in enumerate(res_list):
            vr, item_errors = self._validate_item(item, idx=i)
            if item_errors:
                errors.extend(item_errors)
            if vr is not None:
                results.append(vr)

        ok = len(errors) == 0 and len(results) > 0
        if len(results) == 0 and len(errors) == 0:
            errors.append(ValidationError("no_results_returned"))
            ok = False

        return ValidationOutcome(ok=ok, results=results, errors=errors)

    # -------------------------
    # Internal validation
    # -------------------------

    def _validate_item(self, item: Any, idx: int) -> Tuple[Optional[ValidatedResult], List[ValidationError]]:
        errs: List[ValidationError] = []

        if not isinstance(item, dict):
            return None, [ValidationError("result_item_not_object", detail=f"index={idx}")]

        case_id = item.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            errs.append(ValidationError("invalid_case_id", detail=f"index={idx}"))

        classification = item.get("classification")
        if not isinstance(classification, str) or classification not in _ALLOWED_CLASSIFICATIONS:
            errs.append(ValidationError("invalid_classification", detail=f"index={idx} value={classification!r}"))

        confidence = item.get("confidence")
        conf_val: float = 0.0
        if isinstance(confidence, (int, float)):
            conf_val = float(confidence)
        else:
            errs.append(ValidationError("invalid_confidence_type", detail=f"index={idx}"))

        conf_val = self._clamp(conf_val, 0.0, 1.0)

        extracted = item.get("extracted", {})
        extracted_norm: Dict[str, Optional[str]] = {k: None for k in _EXTRACTED_KEYS}
        if extracted is None:
            extracted = {}
        if not isinstance(extracted, dict):
            errs.append(ValidationError("invalid_extracted_type", detail=f"index={idx}"))
            extracted = {}

        # normalize extracted keys
        for k in _EXTRACTED_KEYS:
            v = extracted.get(k, None)
            if v is None:
                extracted_norm[k] = None
            elif isinstance(v, str):
                extracted_norm[k] = v
            else:
                # Coerce non-strings to string only if it's safe-ish; otherwise null
                try:
                    extracted_norm[k] = str(v)
                except Exception:
                    extracted_norm[k] = None
                    errs.append(ValidationError("extracted_value_unstringifiable", detail=f"index={idx} key={k}"))

        notes = item.get("notes", "")
        if notes is None:
            notes = ""
        if not isinstance(notes, str):
            try:
                notes = str(notes)
            except Exception:
                notes = ""
                errs.append(ValidationError("invalid_notes_type", detail=f"index={idx}"))

        # If critical fields invalid, drop this result (but keep errs)
        if errs and (not isinstance(case_id, str) or not isinstance(classification, str)):
            return None, errs

        vr = ValidatedResult(
            case_id=case_id.strip(),
            classification=classification,
            confidence=conf_val,
            extracted=extracted_norm,
            notes=notes,
        )
        return vr, errs

    def _clamp(self, x: float, lo: float, hi: float) -> float:
        if x < lo:
            return lo
        if x > hi:
            return hi
        return x


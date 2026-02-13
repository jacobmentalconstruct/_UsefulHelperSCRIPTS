"""
HitlDecisionRouterMS
--------------------
Human-in-the-loop decision router for applying inference results.

Responsibilities:
- Take validated inference results and decide:
    - auto-apply (high confidence)
    - require human approval
    - reject / keep unknown
- Provide a deterministic decision plan for the UI orchestrator:
    - list of decisions with required UI actions

Non-goals:
- Rendering dialogs (UI orchestrator / HitlDialogMS)
- Applying changes to UiMap (backend orchestrator does that)
- Retrying LLM prompts (backend orchestrator decides)

Design:
- Decisions are policy-based and purely functional (no side effects).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


# -------------------------
# Data Structures
# -------------------------

@dataclass(frozen=True)
class HitlPolicy:
    """
    Policy thresholds:
    - auto_apply_at: confidence >= this -> auto apply
    - ask_user_at: confidence >= this -> ask user (approve/reject)
    - below ask_user_at -> reject (keep unknown)
    """
    auto_apply_at: float = 0.90
    ask_user_at: float = 0.60

    # If True, even high confidence requires user approval for these classifications.
    force_approval_for: List[str] = field(default_factory=lambda: ["callback_target"])


@dataclass(frozen=True)
class DecisionItem:
    case_id: str
    classification: str
    confidence: float
    action: str  # "auto_apply" | "ask_user" | "reject"
    extracted: Dict[str, Optional[str]]
    notes: str


@dataclass(frozen=True)
class DecisionPlan:
    items: List[DecisionItem]
    stats: Dict[str, int]


# -------------------------
# Service
# -------------------------

class HitlDecisionRouterMS:
    def __init__(self, policy: Optional[HitlPolicy] = None):
        self.policy = policy or HitlPolicy()

    def build_plan(self, validated_results: List[object]) -> DecisionPlan:
        """
        validated_results: duck-typed ValidatedResult:
            - case_id, classification, confidence, extracted, notes
        """
        items: List[DecisionItem] = []
        stats = {"auto_apply": 0, "ask_user": 0, "reject": 0}

        for r in validated_results:
            case_id = getattr(r, "case_id", "")
            classification = getattr(r, "classification", "unknown")
            confidence = float(getattr(r, "confidence", 0.0))
            extracted = getattr(r, "extracted", {}) or {}
            notes = getattr(r, "notes", "") or ""

            action = self._decide_action(classification, confidence)

            items.append(
                DecisionItem(
                    case_id=case_id,
                    classification=classification,
                    confidence=confidence,
                    action=action,
                    extracted=dict(extracted),
                    notes=notes,
                )
            )
            stats[action] += 1

        # Deterministic ordering: prioritize ask_user first, then auto_apply, then reject
        order = {"ask_user": 0, "auto_apply": 1, "reject": 2}
        items.sort(key=lambda it: (order.get(it.action, 9), it.case_id))

        return DecisionPlan(items=items, stats=stats)

    # -------------------------
    # Policy logic
    # -------------------------

    def _decide_action(self, classification: str, confidence: float) -> str:
        # Force approval for certain classes regardless of confidence
        if classification in set(self.policy.force_approval_for):
            return "ask_user" if confidence >= self.policy.ask_user_at else "reject"

        if confidence >= self.policy.auto_apply_at:
            return "auto_apply"
        if confidence >= self.policy.ask_user_at:
            return "ask_user"
        return "reject"


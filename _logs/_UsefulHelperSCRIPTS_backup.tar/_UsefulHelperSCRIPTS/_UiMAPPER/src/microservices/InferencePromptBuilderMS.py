"""
InferencePromptBuilderMS
------------------------
Build deterministic prompts for LLM inference over UnknownCase items.

Responsibilities:
- Convert UnknownCase + local context into a compact, structured prompt
- Provide a strict expected JSON response schema for downstream validation
- Support batching multiple UnknownCase items into one prompt

Non-goals:
- Calling the LLM (OllamaClientMS does that)
- Validating the LLM output (InferenceResultValidatorMS does that)
- UI/HITL decisions (HitlDecisionRouterMS / UI orchestrator does that)

Design:
- Always emit the same format for the same inputs (deterministic ordering)
- Keep prompts small by limiting snippet/context sizes
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


# -------------------------
# Config
# -------------------------

@dataclass
class InferencePromptConfig:
    max_snippet_chars: int = 1200
    max_context_kv_chars: int = 1200
    max_items_per_prompt: int = 10


# -------------------------
# Service
# -------------------------

class InferencePromptBuilderMS:
    def __init__(self, config: Optional[InferencePromptConfig] = None):
        self.config = config or InferencePromptConfig()

    def build_prompt(
        self,
        *,
        project_root: str,
        unknown_cases: List[object],
        goal: str = "Resolve unknown UI mapping cases conservatively.",
    ) -> str:
        """
        unknown_cases: duck-typed UnknownCase:
            - kind, detail, path, lineno, col, snippet, context (dict)
        """
        items = unknown_cases[: self.config.max_items_per_prompt]

        header = self._header(project_root=project_root, goal=goal)
        schema = self._response_schema()
        body = self._items_block(items)

        return "\n".join([header, schema, body]).strip() + "\n"

    # -------------------------
    # Prompt blocks
    # -------------------------

    def _header(self, *, project_root: str, goal: str) -> str:
        return (
            "You are a static-analysis assistant for a Tkinter UI mapper.\n"
            "Your job is to classify uncertain code patterns into safe, conservative interpretations.\n"
            "Only use information present in the provided case records.\n"
            "If you are not confident, return an 'unknown' classification.\n"
            "\n"
            f"ProjectRoot: {project_root}\n"
            f"Goal: {goal}\n"
        )

    def _response_schema(self) -> str:
        # Keep this concise but strict.
        return (
            "Return ONLY valid JSON matching this schema:\n"
            "{\n"
            '  "results": [\n'
            "    {\n"
            '      "case_id": "string",\n'
            '      "classification": "widget_ctor|layout_call|config_call|bind_call|menu_call|callback_target|window_call|unknown",\n'
            '      "confidence": 0.0,\n'
            '      "extracted": {\n'
            '        "widget_type": "string|null",\n'
            '        "parent": "string|null",\n'
            '        "event": "string|null",\n'
            '        "handler": "string|null",\n'
            '        "method": "string|null"\n'
            "      },\n"
            '      "notes": "string"\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "Rules:\n"
            "- confidence is 0.0 to 1.0\n"
            "- extracted values must be null if not applicable\n"
            "- never hallucinate file contents; rely on snippet/context only\n"
            "- be conservative: prefer 'unknown' over guessing\n"
        )

    def _items_block(self, items: List[object]) -> str:
        lines: List[str] = []
        lines.append("Cases:")
        for idx, uc in enumerate(items, start=1):
            lines.extend(self._render_case(idx, uc))
        return "\n".join(lines)

    def _render_case(self, idx: int, uc: object) -> List[str]:
        # stable case_id
        path = str(getattr(uc, "path", "<?>"))
        kind = str(getattr(uc, "kind", "<?>"))
        detail = str(getattr(uc, "detail", "<?>"))
        lineno = getattr(uc, "lineno", None)
        col = getattr(uc, "col", None)

        snippet = getattr(uc, "snippet", None)
        context = getattr(uc, "context", None) or {}

        case_id = f"case_{idx}"

        out: List[str] = []
        out.append(f"- case_id: {case_id}")
        out.append(f"  kind: {kind}")
        out.append(f"  where: {path}:{lineno if lineno is not None else '?'}:{col if col is not None else '?'}")
        out.append(f"  detail: {detail}")

        if snippet:
            out.append("  snippet: |")
            clipped = self._clip(str(snippet), self.config.max_snippet_chars)
            out.extend(self._indent_block(clipped, indent="    "))

        if context:
            out.append("  context:")
            ctx_text = self._render_context(context)
            out.extend(self._indent_block(ctx_text, indent="    "))

        return out

    # -------------------------
    # Utilities
    # -------------------------

    def _render_context(self, ctx: Dict[str, str]) -> str:
        # deterministic ordering
        items = sorted(((str(k), str(v)) for k, v in ctx.items()), key=lambda kv: kv[0].lower())
        parts: List[str] = []
        total = 0
        for k, v in items:
            line = f"{k}: {v}"
            parts.append(line)
            total += len(line)
            if total >= self.config.max_context_kv_chars:
                parts.append("... (context truncated)")
                break
        return "\n".join(parts)

    def _clip(self, s: str, limit: int) -> str:
        if len(s) <= limit:
            return s
        return s[:limit] + "\n... (truncated)"

    def _indent_block(self, s: str, indent: str) -> List[str]:
        return [indent + line for line in s.splitlines()]


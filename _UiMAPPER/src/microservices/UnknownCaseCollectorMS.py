"""
UnknownCaseCollectorMS
----------------------
Collect and normalize "unknown cases" encountered during UI/AST mapping.

Why:
- Many analysis steps are intentionally conservative.
- When we cannot confidently classify something (dynamic widget factory, lambda callback,
  indirect assignment, getattr, etc.), we emit an UnknownCase.
- This service centralizes:
    - creation helpers (consistent fields)
    - dedupe / grouping / ranking
    - export-friendly summaries for HITL + LLM prompting

Responsibilities:
- Provide methods to record unknown cases with stable keys
- Support deduping similar unknowns (same kind + same file + same line + same detail)
- Provide grouped views (by kind, by file)
- Provide "top unknowns" selection for LLM/HITL

Non-goals:
- Performing inference
- UI dialogs
- AST traversal (callers use this to record)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


# -------------------------
# Data Structures
# -------------------------

@dataclass(frozen=True)
class UnknownCase:
    kind: str
    detail: str
    path: Path
    lineno: Optional[int] = None
    col: Optional[int] = None
    snippet: Optional[str] = None

    # Optional context payloads (keep small; avoid megabyte dumps)
    context: Dict[str, str] = field(default_factory=dict)

    def key(self) -> Tuple[str, str, str, int, int]:
        """
        Stable dedupe key.
        """
        return (
            self.kind,
            self.detail.strip(),
            self.path.as_posix(),
            int(self.lineno or 0),
            int(self.col or 0),
        )


@dataclass
class UnknownSummary:
    kind: str
    count: int
    examples: List[UnknownCase] = field(default_factory=list)


# -------------------------
# Service
# -------------------------

class UnknownCaseCollectorMS:
    def __init__(self):
        self._by_key: Dict[Tuple[str, str, str, int, int], UnknownCase] = {}
        self._counts: Dict[Tuple[str, str, str, int, int], int] = {}

    # -------------------------
    # Record API
    # -------------------------

    def record(
        self,
        *,
        kind: str,
        detail: str,
        path: Path,
        lineno: Optional[int] = None,
        col: Optional[int] = None,
        snippet: Optional[str] = None,
        context: Optional[Dict[str, str]] = None,
    ) -> None:
        uc = UnknownCase(
            kind=kind,
            detail=detail,
            path=Path(path).resolve(),
            lineno=lineno,
            col=col,
            snippet=snippet,
            context=context or {},
        )
        k = uc.key()
        if k not in self._by_key:
            self._by_key[k] = uc
            self._counts[k] = 1
        else:
            self._counts[k] += 1

    # Convenience helpers

    def record_ast_node(
        self,
        *,
        kind: str,
        detail: str,
        path: Path,
        node: object,
        snippet: Optional[str] = None,
        context: Optional[Dict[str, str]] = None,
    ) -> None:
        lineno = getattr(node, "lineno", None)
        col = getattr(node, "col_offset", None)
        self.record(
            kind=kind,
            detail=detail,
            path=path,
            lineno=lineno,
            col=col,
            snippet=snippet,
            context=context,
        )

    # -------------------------
    # Retrieval
    # -------------------------

    def all_cases(self) -> List[UnknownCase]:
        return list(self._by_key.values())

    def count(self, case: UnknownCase) -> int:
        return self._counts.get(case.key(), 1)

    def clear(self) -> None:
        self._by_key.clear()
        self._counts.clear()

    # -------------------------
    # Grouping / Summaries
    # -------------------------

    def summarize_by_kind(self, max_examples_per_kind: int = 3) -> List[UnknownSummary]:
        buckets: Dict[str, List[UnknownCase]] = {}
        for uc in self._by_key.values():
            buckets.setdefault(uc.kind, []).append(uc)

        summaries: List[UnknownSummary] = []
        for kind, cases in buckets.items():
            # deterministic ordering: file/line then detail
            cases_sorted = sorted(
                cases,
                key=lambda c: (c.path.as_posix().lower(), int(c.lineno or 0), c.detail.lower()),
            )
            summaries.append(
                UnknownSummary(
                    kind=kind,
                    count=sum(self._counts[c.key()] for c in cases_sorted),
                    examples=cases_sorted[:max_examples_per_kind],
                )
            )

        # sort summaries by total count desc, then kind
        summaries.sort(key=lambda s: (-s.count, s.kind.lower()))
        return summaries

    def summarize_by_file(self, max_examples_per_file: int = 5) -> Dict[str, List[UnknownCase]]:
        buckets: Dict[str, List[UnknownCase]] = {}
        for uc in self._by_key.values():
            key = uc.path.as_posix()
            buckets.setdefault(key, []).append(uc)

        for k in list(buckets.keys()):
            buckets[k] = sorted(
                buckets[k],
                key=lambda c: (c.kind.lower(), int(c.lineno or 0), c.detail.lower()),
            )[:max_examples_per_file]

        return dict(sorted(buckets.items(), key=lambda kv: kv[0].lower()))

    # -------------------------
    # Selection for HITL/LLM
    # -------------------------

    def select_for_inference(
        self,
        *,
        max_items: int = 20,
        kind_priority: Optional[List[str]] = None,
    ) -> List[UnknownCase]:
        """
        Returns a prioritized list of unknown cases to send to an LLM/HITL.
        Strategy:
        - Prefer kinds listed in kind_priority (in order)
        - Otherwise, prefer cases with higher occurrence counts
        - Stable tie-break by file/line
        """
        kind_priority = kind_priority or []

        cases = list(self._by_key.values())

        def prio(uc: UnknownCase) -> Tuple[int, int, str, int]:
            # smaller kind_index is higher priority
            if uc.kind in kind_priority:
                kind_idx = kind_priority.index(uc.kind)
                kind_score = -1000 + kind_idx  # push ahead of all others
            else:
                kind_score = 0

            cnt = self._counts.get(uc.key(), 1)
            return (kind_score, -cnt, uc.path.as_posix().lower(), int(uc.lineno or 0))

        cases.sort(key=prio)
        return cases[:max_items]


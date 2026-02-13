"""
EntrypointFinderMS
------------------
Find likely entrypoint files in a Python project.

Responsibilities:
- Scan a list of Python files and identify candidates for "entrypoint"
- Provide deterministic scoring + reasons
- Support both script-style entrypoints and package entrypoints

Heuristics (scored):
- Contains `if __name__ == "__main__":`
- Imports `tkinter` / `ttk` and creates `tk.Tk()` or `tkinter.Tk()`
- Defines a `main()` function
- Filename hints: app.py, main.py, run.py, __main__.py
- Located near project root (shorter relative path)

Non-goals:
- AST-accurate program understanding (fast text scan)
- Executing code
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re


# -------------------------
# Data Structures
# -------------------------

@dataclass(frozen=True)
class EntrypointCandidate:
    path: Path
    score: int
    reasons: Tuple[str, ...]


@dataclass
class EntrypointFinderConfig:
    max_candidates: int = 20
    read_bytes_limit: int = 512_000  # 512KB per file (fast, safe default)

    # filename hints
    strong_names: Tuple[str, ...] = (
        "app.py",
        "main.py",
        "run.py",
        "__main__.py",
        "start.py",
        "launcher.py",
        "cli.py",
    )


# -------------------------
# Service
# -------------------------

class EntrypointFinderMS:
    def __init__(self, project_root: Path, config: Optional[EntrypointFinderConfig] = None):
        self.root = Path(project_root).resolve()
        self.config = config or EntrypointFinderConfig()

        self._re_main_guard = re.compile(r"""if\s+__name__\s*==\s*["']__main__["']\s*:""")
        self._re_def_main = re.compile(r"""^\s*def\s+main\s*\(""", re.MULTILINE)

        # Tk hints (simple text; AST service will do real mapping later)
        self._re_tk_import = re.compile(r"""^\s*(import\s+tkinter\b|from\s+tkinter\s+import\b)""", re.MULTILINE)
        self._re_tk_root = re.compile(r"""\b(tkinter\.)?Tk\s*\(""")
        self._re_ttk = re.compile(r"""\bttk\b""")

    # -------------------------
    # Public API
    # -------------------------

    def find_candidates(self, py_files: List[Path]) -> List[EntrypointCandidate]:
        """
        Returns ranked candidates (highest score first).
        """
        cands: List[EntrypointCandidate] = []

        for p in py_files:
            try:
                score, reasons = self._score_file(p)
            except Exception:
                # If unreadable, ignore
                continue

            if score > 0:
                cands.append(EntrypointCandidate(path=p, score=score, reasons=tuple(reasons)))

        # deterministic sort: score desc, then path
        cands.sort(key=lambda c: (-c.score, c.path.as_posix().lower()))
        return cands[: self.config.max_candidates]

    # -------------------------
    # Internals
    # -------------------------

    def _score_file(self, path: Path) -> Tuple[int, List[str]]:
        score = 0
        reasons: List[str] = []

        name = path.name.lower()

        if name in (n.lower() for n in self.config.strong_names):
            score += 25
            reasons.append(f"filename_hint:{name}")

        rel_depth = self._rel_depth(path)
        # closer to root gets more points
        depth_bonus = max(0, 10 - rel_depth)
        if depth_bonus:
            score += depth_bonus
            reasons.append(f"near_root:depth={rel_depth}")

        text = self._read_text_head(path)

        if self._re_main_guard.search(text):
            score += 40
            reasons.append("__main__guard")

        if self._re_def_main.search(text):
            score += 15
            reasons.append("defines_main()")

        tk_import = bool(self._re_tk_import.search(text))
        tk_root = bool(self._re_tk_root.search(text))
        if tk_import:
            score += 12
            reasons.append("imports_tkinter")
        if tk_root:
            score += 12
            reasons.append("creates_Tk()")

        if tk_import and tk_root:
            score += 10
            reasons.append("tkinter_entrypoint_signal")

        if self._re_ttk.search(text):
            score += 3
            reasons.append("mentions_ttk")

        # package-style entrypoint: package/__main__.py
        if name == "__main__.py":
            score += 30
            reasons.append("package___main__")

        return score, reasons

    def _rel_depth(self, path: Path) -> int:
        try:
            rel = path.resolve().relative_to(self.root)
            # depth = number of parents in rel (0 if in root)
            return len(rel.parts) - 1
        except Exception:
            return 99

    def _read_text_head(self, path: Path) -> str:
        """
        Reads up to read_bytes_limit bytes, decodes as utf-8 with replacement.
        """
        data = path.read_bytes()
        if len(data) > self.config.read_bytes_limit:
            data = data[: self.config.read_bytes_limit]
        return data.decode("utf-8", errors="replace")


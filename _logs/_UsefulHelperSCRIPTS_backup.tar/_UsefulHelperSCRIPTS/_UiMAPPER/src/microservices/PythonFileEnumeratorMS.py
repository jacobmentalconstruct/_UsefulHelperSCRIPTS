"""
PythonFileEnumeratorMS
----------------------
Filter + enumerate Python files from a ProjectCrawlMS stream.

Responsibilities:
- Consume CrawlEntry stream
- Emit only .py files (optionally include .pyw)
- Optionally exclude common virtualenv / cache dirs via fast heuristics
- Provide stable ordering

Non-goals:
- .gitignore parsing (use GitignoreFilterMS)
- AST parsing
- UI logic
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Iterable, List, Optional, Set, Tuple


# -------------------------
# Data Structures
# -------------------------

@dataclass
class PythonEnumConfig:
    include_pyw: bool = True
    stable_sort: bool = True

    # Fast path pruning based on path parts (not gitignore-accurate, just practical)
    exclude_dir_names: Set[str] = None

    def __post_init__(self) -> None:
        if self.exclude_dir_names is None:
            self.exclude_dir_names = {
                ".git",
                ".hg",
                ".svn",
                "__pycache__",
                ".mypy_cache",
                ".pytest_cache",
                ".ruff_cache",
                ".tox",
                ".nox",
                "venv",
                ".venv",
                "env",
                ".env",
                "node_modules",
                "dist",
                "build",
                ".idea",
                ".vscode",
            }


# -------------------------
# Service
# -------------------------

class PythonFileEnumeratorMS:
    """
    Emits absolute Paths for Python files from a crawl stream.

    Expected upstream:
        ProjectCrawlMS.crawl(...) yielding CrawlEntry(abs_path, rel_path, is_dir)

    Typical usage:
        entries = crawl.crawl(path_filters=[gitignore.predicate(), ...])
        py_files = PythonFileEnumeratorMS(cfg).enumerate(entries)
    """

    def __init__(self, config: Optional[PythonEnumConfig] = None):
        self.config = config or PythonEnumConfig()

    def enumerate(self, crawl_entries: Iterable[object]) -> List[Path]:
        """
        Returns a list (optionally stable-sorted) of Python file absolute paths.
        """
        out: List[Path] = []
        for entry in crawl_entries:
            # Duck-typed to avoid importing CrawlEntry directly
            abs_path: Path = entry.abs_path
            rel_path: Path = entry.rel_path
            is_dir: bool = entry.is_dir

            if is_dir:
                # Heuristic: if any part of rel path is an excluded dir, skip
                if self._contains_excluded_dir(rel_path):
                    continue
                continue

            if self._contains_excluded_dir(rel_path.parent):
                continue

            if self._is_python_file(abs_path):
                out.append(abs_path)

        if self.config.stable_sort:
            out.sort(key=lambda p: p.as_posix().lower())

        return out

    # -------------------------
    # Internals
    # -------------------------

    def _is_python_file(self, path: Path) -> bool:
        s = path.name.lower()
        if s.endswith(".py"):
            return True
        if self.config.include_pyw and s.endswith(".pyw"):
            return True
        return False

    def _contains_excluded_dir(self, rel: Path) -> bool:
        if rel is None:
            return False
        for part in rel.parts:
            if part in self.config.exclude_dir_names:
                return True
        return False


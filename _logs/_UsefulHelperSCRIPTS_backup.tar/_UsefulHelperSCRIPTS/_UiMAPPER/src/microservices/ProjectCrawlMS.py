"""
ProjectCrawlMS
--------------
Deterministic project filesystem crawler.

Responsibilities:
- Validate project root
- Walk directory tree in stable order
- Yield normalized relative/absolute paths
- Provide extension points for filter services (ignore rules, file-type filters)

Design notes:
- No UI
- No threading
- Pure IO + structure
- Orchestrator decides what to do with yielded paths
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Generator, Iterable, List, Optional


# -------------------------
# Data Structures
# -------------------------

@dataclass(frozen=True)
class CrawlEntry:
    abs_path: Path
    rel_path: Path
    is_dir: bool


@dataclass
class CrawlConfig:
    root: Path
    follow_symlinks: bool = False
    include_hidden: bool = False
    stable_sort: bool = True


# -------------------------
# Service
# -------------------------

class ProjectCrawlMS:
    """
    Core filesystem crawler.

    The service itself does NOT know about:
    - gitignore
    - file extensions
    - AST
    - UI

    It simply emits filesystem structure.

    Filtering is injected via:
        path_filters: Callable[[Path, bool], bool]
            (path, is_dir) -> keep?
    """

    def __init__(self, config: CrawlConfig):
        self.config = config
        self.root = config.root.resolve()

        self._validate_root()

    # -------------------------
    # Validation
    # -------------------------

    def _validate_root(self) -> None:
        if not self.root.exists():
            raise FileNotFoundError(f"Project root does not exist: {self.root}")
        if not self.root.is_dir():
            raise NotADirectoryError(f"Project root is not a directory: {self.root}")

    # -------------------------
    # Public API
    # -------------------------

    def crawl(
        self,
        path_filters: Optional[List[Callable[[Path, bool], bool]]] = None,
    ) -> Generator[CrawlEntry, None, None]:
        """
        Walk the filesystem from root and yield CrawlEntry objects.

        path_filters:
            List of predicates. If any returns False -> entry skipped.
            Signature: (abs_path: Path, is_dir: bool) -> bool
        """

        filters = path_filters or []

        for abs_dir, dirs, files in os.walk(
            self.root,
            followlinks=self.config.follow_symlinks,
        ):
            abs_dir_path = Path(abs_dir)

            # Stable ordering for deterministic mapping
            if self.config.stable_sort:
                dirs.sort()
                files.sort()

            # Emit directory itself
            rel_dir = abs_dir_path.relative_to(self.root)

            if self._passes_filters(abs_dir_path, True, filters):
                yield CrawlEntry(
                    abs_path=abs_dir_path,
                    rel_path=rel_dir,
                    is_dir=True,
                )

            # Control directory traversal (filter dirs in-place)
            dirs[:] = [
                d for d in dirs
                if self._dir_allowed(abs_dir_path / d, filters)
            ]

            # Emit files
            for file_name in files:
                abs_file = abs_dir_path / file_name

                if not self.config.include_hidden and file_name.startswith("."):
                    continue

                if self._passes_filters(abs_file, False, filters):
                    yield CrawlEntry(
                        abs_path=abs_file,
                        rel_path=abs_file.relative_to(self.root),
                        is_dir=False,
                    )

    # -------------------------
    # Internal helpers
    # -------------------------

    def _passes_filters(
        self,
        path: Path,
        is_dir: bool,
        filters: Iterable[Callable[[Path, bool], bool]],
    ) -> bool:
        for f in filters:
            if not f(path, is_dir):
                return False
        return True

    def _dir_allowed(
        self,
        path: Path,
        filters: Iterable[Callable[[Path, bool], bool]],
    ) -> bool:
        """
        Used to prune os.walk traversal.
        """
        if not self.config.include_hidden and path.name.startswith("."):
            return False

        for f in filters:
            if not f(path, True):
                return False

        return True

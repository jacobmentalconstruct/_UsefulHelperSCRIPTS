"""
GitignoreFilterMS
-----------------
Deterministic .gitignore-style path filter.

Responsibilities:
- Load ignore rules from:
    - <root>/.gitignore
    - <root>/.git/info/exclude (if present)
    - optional extra ignore files
- Evaluate paths (absolute) relative to root
- Support a practical subset of gitignore semantics:
    - blank lines + comments (#) ignored
    - negation rules via leading "!"
    - directory rules via trailing "/"
    - rooted patterns via leading "/"
    - glob wildcards: "*", "?", "[...]" (fnmatch semantics)
    - "**" treated as "match any path segments" (approx via fnmatch on normalized paths)

Non-goals:
- Full gitignore edge-case parity (this is "good enough" for project crawling).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Tuple
import fnmatch
import os


# -------------------------
# Data Structures
# -------------------------

@dataclass(frozen=True)
class GitignoreRule:
    raw: str
    is_negation: bool
    dir_only: bool
    rooted: bool
    pattern: str  # normalized for matching


# -------------------------
# Service
# -------------------------

class GitignoreFilterMS:
    """
    Produces a predicate usable by ProjectCrawlMS:

        keep = gitignore_filter.predicate()
        keep(abs_path: Path, is_dir: bool) -> bool

    Semantics:
    - If a rule matches -> toggles ignore state
        - normal rule => ignored = True
        - negation rule => ignored = False
    - Last matching rule wins (gitignore behavior)
    """

    def __init__(
        self,
        root: Path,
        extra_ignore_files: Optional[List[Path]] = None,
    ):
        self.root = Path(root).resolve()
        self.extra_ignore_files = extra_ignore_files or []

        self._rules: List[GitignoreRule] = []
        self._loaded_sources: List[Path] = []

    # -------------------------
    # Public API
    # -------------------------

    def load(self) -> None:
        """
        Load ignore rules from known locations + any extra ignore files.
        Safe to call multiple times; it replaces existing rules.
        """
        self._rules = []
        self._loaded_sources = []

        sources: List[Path] = []

        root_gitignore = self.root / ".gitignore"
        if root_gitignore.exists():
            sources.append(root_gitignore)

        git_info_exclude = self.root / ".git" / "info" / "exclude"
        if git_info_exclude.exists():
            sources.append(git_info_exclude)

        for p in self.extra_ignore_files:
            pp = Path(p).resolve()
            if pp.exists():
                sources.append(pp)

        for src in sources:
            self._loaded_sources.append(src)
            self._rules.extend(self._parse_file(src))

    def predicate(self) -> Callable[[Path, bool], bool]:
        """
        Returns a predicate function:
            (abs_path: Path, is_dir: bool) -> keep?
        """
        # Ensure loaded at least once (zero rules is fine)
        if not self._loaded_sources and not self._rules:
            self.load()

        def _keep(abs_path: Path, is_dir: bool) -> bool:
            return not self.is_ignored(abs_path, is_dir)

        return _keep

    def is_ignored(self, abs_path: Path, is_dir: bool) -> bool:
        """
        Returns True if gitignore rules ignore this path.
        """
        try:
            rel = Path(abs_path).resolve().relative_to(self.root)
        except Exception:
            # Path outside root: do not ignore by these rules
            return False

        rel_posix = rel.as_posix()

        ignored = False
        for rule in self._rules:
            if rule.dir_only and not is_dir:
                continue
            if self._rule_matches(rule, rel_posix, rel, is_dir):
                ignored = not rule.is_negation

        return ignored

    # -------------------------
    # Internals: parsing
    # -------------------------

    def _parse_file(self, path: Path) -> List[GitignoreRule]:
        rules: List[GitignoreRule] = []
        text = path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            rule = self._parse_line(line)
            if rule is not None:
                rules.append(rule)
        return rules

    def _parse_line(self, line: str) -> Optional[GitignoreRule]:
        s = line.strip("\n\r")

        # Skip blanks
        if not s.strip():
            return None

        # Skip comments (but allow escaped \#)
        stripped = s.lstrip()
        if stripped.startswith("#"):
            return None

        # Unescape leading "\#" (keep "#")
        if s.startswith(r"\#"):
            s = s[1:]

        is_negation = False
        if s.startswith("!"):
            is_negation = True
            s = s[1:]

        # After removing "!", empty means nothing
        if not s:
            return None

        dir_only = s.endswith("/")
        if dir_only:
            s = s[:-1]

        rooted = s.startswith("/")
        if rooted:
            s = s[1:]

        # Normalize to POSIX-ish matching.
        # Gitignore treats backslashes specially on Windows; we normalize to "/".
        pattern = s.replace("\\", "/")

        return GitignoreRule(
            raw=line,
            is_negation=is_negation,
            dir_only=dir_only,
            rooted=rooted,
            pattern=pattern,
        )

    # -------------------------
    # Internals: matching
    # -------------------------

    def _rule_matches(self, rule: GitignoreRule, rel_posix: str, rel_path: Path, is_dir: bool) -> bool:
        """
        A pragmatic matcher:
        - If rule contains "/" => match against full relative path (posix)
        - Else => match against basename in any directory (like gitignore)
        - If rule.rooted => anchor at repo root (i.e., compare from start)
        """
        pat = rule.pattern

        # Directory match: if rule matches a dir path, also match contents by prefix
        # (gitignore-style). We'll check both exact dir and prefix.
        if rule.dir_only:
            # If this is a dir, match itself; if it's a file (won't be here), ignore.
            # Also if a dir rule matches "a/b", it should ignore "a/b/**".
            if self._match_path(rule, rel_posix, pat):
                return True
            if rel_posix.startswith(pat.rstrip("/") + "/"):
                return True
            return False

        # If pattern has a "/" then treat as path-glob, else basename-glob
        if "/" in pat or rule.rooted:
            return self._match_path(rule, rel_posix, pat)

        # Basename-style: match on name at any depth
        name = rel_path.name
        return fnmatch.fnmatchcase(name, pat)

    def _match_path(self, rule: GitignoreRule, rel_posix: str, pat: str) -> bool:
        """
        Path matching:
        - If rooted: only match from root (we already have rel_posix)
        - Else:
            - If pat contains "/" we allow matching at any depth by trying:
                - exact full-path match
                - "**/pat" match
        """
        # Exact match
        if fnmatch.fnmatchcase(rel_posix, pat):
            return True

        if rule.rooted:
            return False

        # Allow match at any depth
        # e.g., pat "foo/bar.py" should match "x/y/foo/bar.py"
        if "/" in pat:
            deep_pat = f"**/{pat}"
            if fnmatch.fnmatchcase(rel_posix, deep_pat):
                return True

        return False


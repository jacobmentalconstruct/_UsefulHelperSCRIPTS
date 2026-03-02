"""
AstParseCacheMS
---------------
Parse Python files into AST with caching + stable error reporting.

Responsibilities:
- Parse file content to ast.AST
- Cache by (path, mtime_ns, size) to avoid re-parsing
- Provide structured parse results (success or error)
- Never raise on syntax errors; return them as structured data

Non-goals:
- Project walking (ProjectCrawlMS)
- File filtering (.py selection)
- UI mapping logic (AstUiMapMS)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple


# -------------------------
# Data Structures
# -------------------------

@dataclass(frozen=True)
class AstParseError:
    path: Path
    message: str
    lineno: Optional[int] = None
    col_offset: Optional[int] = None


@dataclass(frozen=True)
class AstParseResult:
    path: Path
    ok: bool
    tree: Optional[ast.AST] = None
    error: Optional[AstParseError] = None


@dataclass(frozen=True)
class _CacheKey:
    path: Path
    mtime_ns: int
    size: int


# -------------------------
# Service
# -------------------------

class AstParseCacheMS:
    """
    Usage:
        cache = AstParseCacheMS()
        res = cache.parse(path)
        if res.ok: use res.tree
        else: log res.error
    """

    def __init__(self):
        self._cache: Dict[_CacheKey, AstParseResult] = {}
        self._last_key_by_path: Dict[Path, _CacheKey] = {}

    def parse(self, path: Path) -> AstParseResult:
        p = Path(path).resolve()

        try:
            st = p.stat()
        except Exception as e:
            err = AstParseError(path=p, message=f"stat_failed: {e}")
            return AstParseResult(path=p, ok=False, error=err)

        key = _CacheKey(path=p, mtime_ns=st.st_mtime_ns, size=st.st_size)

        # If we previously cached a different version, remove it to keep cache small.
        prev_key = self._last_key_by_path.get(p)
        if prev_key is not None and prev_key != key:
            self._cache.pop(prev_key, None)

        self._last_key_by_path[p] = key

        cached = self._cache.get(key)
        if cached is not None:
            return cached

        result = self._parse_uncached(p)
        self._cache[key] = result
        return result

    def clear(self) -> None:
        self._cache.clear()
        self._last_key_by_path.clear()

    # -------------------------
    # Internal
    # -------------------------

    def _parse_uncached(self, path: Path) -> AstParseResult:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            err = AstParseError(path=path, message=f"read_failed: {e}")
            return AstParseResult(path=path, ok=False, error=err)

        try:
            tree = ast.parse(text, filename=str(path))
            return AstParseResult(path=path, ok=True, tree=tree)
        except SyntaxError as e:
            err = AstParseError(
                path=path,
                message=f"syntax_error: {e.msg}",
                lineno=getattr(e, "lineno", None),
                col_offset=getattr(e, "offset", None),
            )
            return AstParseResult(path=path, ok=False, error=err)
        except Exception as e:
            err = AstParseError(path=path, message=f"parse_failed: {e}")
            return AstParseResult(path=path, ok=False, error=err)


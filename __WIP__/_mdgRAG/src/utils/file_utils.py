"""
File Utilities — minimal safe file and path helpers.

Keep this module small. It exists to provide a few safe path operations
and prevent utility-dumping-ground drift. If a helper doesn't clearly
belong here, it belongs in the module that uses it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def ensure_directory(path: Path) -> Path:
    """
    Ensure a directory exists, creating it if necessary.

    Returns the path for chaining convenience.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path


def safe_resolve(path: str | Path) -> Path:
    """
    Resolve a path to its absolute, canonical form.

    Returns a fully resolved Path object.
    """
    return Path(path).resolve()


def has_extension(path: str | Path, *extensions: str) -> bool:
    """
    Check if a path has one of the given extensions.

    Extensions should include the dot (e.g., '.py', '.json').
    """
    suffix = Path(path).suffix.lower()
    return suffix in {ext.lower() for ext in extensions}

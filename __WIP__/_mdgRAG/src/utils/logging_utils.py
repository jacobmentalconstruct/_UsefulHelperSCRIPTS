"""
Logging Utilities — simple logger bootstrapping.

Provides a consistent logger factory to prevent ad-hoc print() sprawl.
All modules should use get_logger(__name__) instead of print().
"""

from __future__ import annotations

import logging
import sys


_configured = False


def _configure_root_logger() -> None:
    """Configure the root logger once on first use."""
    global _configured
    if _configured:
        return

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root = logging.getLogger("src")
    root.setLevel(logging.INFO)
    root.addHandler(handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """
    Get a named logger with consistent formatting.

    Usage:
        from src.utils.logging_utils import get_logger
        logger = get_logger(__name__)
        logger.info("message")
    """
    _configure_root_logger()
    return logging.getLogger(name)

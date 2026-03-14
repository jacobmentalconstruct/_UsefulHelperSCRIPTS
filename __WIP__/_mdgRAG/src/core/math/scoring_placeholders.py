"""
Scoring Placeholders — backward-compatible re-export shim.

Ownership: src/core/math/scoring_placeholders.py
    Originally Phase 1 stubs that raised NotImplementedError.
    Now re-exports real implementations from scoring.py.

    This module exists solely for backward compatibility. New code
    should import directly from src.core.math.scoring.

Legacy context:
    Phase 1 established this module with five placeholder stubs.
    Phase 5 replaced them with real algorithms in scoring.py.
    This file was preserved as a re-export shim so that any code
    importing from the old path continues to work.
"""

from src.core.math.scoring import (  # noqa: F401
    normalize_min_max,
    structural_score,
    semantic_score,
    gravity_score,
    spreading_activation,
)

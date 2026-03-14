"""
Extractor Placeholder — backward-compatible re-export shim.

Ownership: src/core/extraction/extractor_placeholder.py
    Originally Phase 1 stubs that raised NotImplementedError.
    Now re-exports real implementations from extractor.py.

    This module exists solely for backward compatibility. New code
    should import directly from src.core.extraction.extractor.

Legacy context:
    Phase 1 established this module with three placeholder stubs.
    Phase 6 replaced them with a real extraction algorithm in extractor.py.
    This file was preserved as a re-export shim so that any code
    importing from the old path continues to work.
"""

from src.core.extraction.extractor import (  # noqa: F401
    ExtractionConfig,
    extract_evidence_bag,
)

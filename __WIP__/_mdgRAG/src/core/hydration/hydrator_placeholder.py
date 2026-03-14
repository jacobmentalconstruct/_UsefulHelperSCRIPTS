"""
Hydrator Placeholder — backward-compatible re-export shim.

Ownership: src/core/hydration/hydrator_placeholder.py
    Originally Phase 1 stubs that raised NotImplementedError.
    Now re-exports real implementations from hydrator.py.

    This module exists solely for backward compatibility. New code
    should import directly from src.core.hydration.hydrator.

Legacy context:
    Phase 1 established this module with three placeholder stubs:
    hydrate_node_payloads(), translate_edges(), format_evidence_bundle().
    Phase 7 replaced them with real hydration in hydrator.py.
    This file was preserved as a re-export shim so that any code
    importing from the old path continues to work.
"""

from src.core.hydration.hydrator import (  # noqa: F401
    HydrationConfig,
    hydrate_evidence_bag,
    hydrate_node_payloads,
    translate_edges,
    format_evidence_bundle,
)

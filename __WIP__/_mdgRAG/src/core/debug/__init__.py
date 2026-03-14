# Debug — inspection and diagnostic helpers for development

from src.core.debug.score_dump import dump_virtual_scores  # noqa: F401
from src.core.debug.inspection import (  # noqa: F401
    dump_projection_summary,
    dump_fusion_result,
    dump_evidence_bag,
    dump_hydrated_bundle,
    inspect_pipeline_result,
)

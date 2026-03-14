# Math — scoring, normalization, and graph algorithms

from src.core.math.scoring import (  # noqa: F401
    normalize_min_max,
    structural_score,
    semantic_score,
    gravity_score,
    spreading_activation,
)

from src.core.math.friction import (  # noqa: F401
    detect_island_effect,
    detect_gravity_collapse,
    detect_normalization_extrema,
    detect_all_friction,
)

from src.core.math.annotator import (  # noqa: F401
    SCORE_ANNOTATION_KEY,
    annotate_scores,
    read_score_annotation,
)

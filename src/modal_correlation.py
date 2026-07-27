"""Public, reviewed modal-correlation API.

GeometryMatch contains NumPy arrays, so dataclass value equality is not meaningful and
can raise the ambiguous-array truth-value exception. Identity equality is the correct
semantics for candidate membership and caching.
"""

from modal_core import GeometryMatch

GeometryMatch.__eq__ = object.__eq__
GeometryMatch.__hash__ = object.__hash__

from reviewed_core import (  # noqa: E402,F401
    compare_modal_datasets,
    experimental_measurement_mask,
    frequency_error_percent,
    geometry_alignment_candidates,
)

__all__ = [
    "compare_modal_datasets",
    "experimental_measurement_mask",
    "frequency_error_percent",
    "geometry_alignment_candidates",
]

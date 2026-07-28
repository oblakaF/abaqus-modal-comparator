"""Public reviewed modal-correlation API.

The implementation lives in reviewed_core. GeometryMatch now uses identity equality
at its dataclass definition, so importing this facade has no global side effects.
"""

from reviewed_core import (
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

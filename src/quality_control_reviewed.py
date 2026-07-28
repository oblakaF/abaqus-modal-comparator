"""Stable quality-control entry point with no import-time global mutation."""

from quality_control import (
    _detect_rigid_modes,
    _rigid_body_residual_fraction,
    compare_modal_datasets_with_quality_control,
)

__all__ = [
    "compare_modal_datasets_with_quality_control",
    "_detect_rigid_modes",
    "_rigid_body_residual_fraction",
]

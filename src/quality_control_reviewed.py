"""Stable quality-control entry point bound to the reviewed correlation core."""

import quality_control as _quality_control
from modal_correlation import compare_modal_datasets

_quality_control.compare_modal_datasets = compare_modal_datasets

compare_modal_datasets_with_quality_control = (
    _quality_control.compare_modal_datasets_with_quality_control
)
_detect_rigid_modes = _quality_control._detect_rigid_modes

__all__ = [
    "compare_modal_datasets_with_quality_control",
    "_detect_rigid_modes",
]

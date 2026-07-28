from __future__ import annotations

import numpy as np

import advanced_metrics
from modal_scaling import unit_norm_aligned_columns


_INSTALLED = False


def _normalized_common_pair_data(result):
    if not result.pairs:
        raise ValueError("No verified pairs are available for AutoMAC or COMAC.")

    shape = result.pairs[0].abaqus_vector.shape
    common_mask = np.ones(shape, dtype=bool)
    for pair in result.pairs:
        if pair.abaqus_vector.shape != shape or pair.experimental_vector.shape != shape:
            raise ValueError("Verified pair vectors do not share a common measurement grid.")
        pair_mask = getattr(pair, "measured_dof_mask", np.ones(shape, dtype=bool))
        finite = (
            np.isfinite(pair.abaqus_vector.real)
            & np.isfinite(pair.abaqus_vector.imag)
            & np.isfinite(pair.experimental_vector.real)
            & np.isfinite(pair.experimental_vector.imag)
        )
        common_mask &= np.asarray(pair_mask, dtype=bool) & finite

    if not np.any(common_mask):
        raise ValueError("No common measured degrees of freedom exist across verified pairs.")

    abaqus_columns = []
    experimental_columns = []
    for pair in result.pairs:
        abaqus = np.asarray(pair.abaqus_vector, dtype=complex)[common_mask]
        experiment = np.asarray(pair.experimental_vector, dtype=complex)[common_mask]
        abaqus, experiment = unit_norm_aligned_columns(abaqus, experiment)
        abaqus_columns.append(abaqus)
        experimental_columns.append(experiment)

    return (
        np.column_stack(abaqus_columns),
        np.column_stack(experimental_columns),
        common_mask,
    )


def install_metrics_normalization() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    advanced_metrics._common_pair_data = _normalized_common_pair_data
    _INSTALLED = True

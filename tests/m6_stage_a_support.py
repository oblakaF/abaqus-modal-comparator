"""Synthetic Stage-A cases for the M6-B adapter tests (no Abaqus, no files, no real specimen).

The forward model is a verified ``StageAAffineBasis`` with diagonal K and M: three rigid DOFs (zero
stiffness) and n elastic DOFs with λ_i = a_i·D11 + b_i·D12 + c_i·D66. Each elastic mode is one
coordinate, so FE-to-FE tracking is exact, and the "experiment" is the same model at known truth
values. Units are SI (D in N·m).
"""

from __future__ import annotations

from dataclasses import replace
import math

import numpy as np
from scipy import sparse

from domain.experimental_qc import TrustedSuspensionThreshold
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.modal_input_source import ModalInputSource, ModalInputSourceClassification
from domain.stage_a_experiment import (
    ExcitationEvidence,
    ExcitationRoute,
    ExperimentalMode,
    FrozenModalSetIdentity,
    ObservationRole,
    SpecimenMeasurements,
    StageAExperimentalEvidence,
    StageAModalInput,
    StageAObservationRow,
    StageAPairingEvidence,
    ThicknessCharacterization,
    ThicknessPoint,
)
from services.identification_step import LMSettings, parameter_bounds
from services.matrix_model_service import AbaqusDof, StageAAffineBasis, StageAMatrixParameters
from services.stage_a_validation import (
    GOVERNED_NU12,
    StageAForwardModel,
    observation_term_ids,
    spec_provisional_setup_term,
)


RIGID = 3
REFERENCE = StageAMatrixParameters(0.34, GOVERNED_NU12 * 0.34, 0.040)
TRUTH = {"D11": 0.330, "D12": 0.0264, "D66": 0.0430}  # D12/D11 = 0.08 ≠ the governed 0.05
# λ_i coefficients (rad²/s² per N·m): bending-dominated, twist-dominated and mixed modes, ordered so
# that DOF order is frequency order at the reference and at the truth (FE mode i ↔ experimental mode i).
A = np.array([1.0e5, 0.2e5, 0.5e5, 1.5e5, 2.6e5, 4.0e5])
C = np.array([0.4e5, 7.0e5, 9.0e5, 6.0e5, 0.3e5, 1.0e5])
B_INDEPENDENT = np.array([0.0, 3.0e5, 0.0, 6.0e5, 9.0e5, 2.0e5])  # D12 separately visible: full rank
B_NONE = np.zeros(6)  # no D12 sensitivity: the full system is rank-deficient
LM_SETTINGS = LMSettings(mu_initial=1e-3, mu_decrease=10, max_step_attempts=3, solve_budget=20)  # D-034 values
BOUNDS = parameter_bounds([("D11", 0.10, 1.0), ("D12", 0.001, 0.09), ("D66", 0.01, 0.20)])
START = {"D11": 0.36, "D66": 0.038}
THICKNESS_MM = (0.448, 0.452, 0.455, 0.446, 0.450, 0.451, 0.449, 0.447, 0.453)
SHA = "0" * 63 + "1"


def basis(b=B_INDEPENDENT, c=C) -> StageAAffineBasis:
    n = len(A)
    stiffness = lambda values: sparse.diags(np.concatenate([np.zeros(RIGID), values]))  # noqa: E731
    reference = A * REFERENCE.D11 + b * REFERENCE.D12 + c * REFERENCE.D66
    return StageAAffineBasis(REFERENCE, stiffness(reference), (stiffness(A), stiffness(b), stiffness(c)),
                             sparse.identity(n + RIGID, format="csr"),
                             tuple(AbaqusDof(i + 1, 3) for i in range(n + RIGID)))


def forward(b=B_INDEPENDENT, attachment_g=2.0, c=C) -> StageAForwardModel:
    return StageAForwardModel("SYNTH-PLATE-AFFINE", basis(b, c), len(A), RIGID, attachment_g,
                              "synthetic diagonal affine Stage-A basis (tests only)")


def truth_frequencies(b=B_INDEPENDENT, truth=TRUTH, c=C) -> dict[int, float]:
    lam = A * truth["D11"] + b * truth["D12"] + c * truth["D66"]
    return {i + 1: math.sqrt(v) / (2.0 * math.pi) for i, v in enumerate(lam)}


def classification(source=ModalInputSource.CURVE_FITTED) -> ModalInputSourceClassification:
    return ModalInputSourceClassification(source, "synthetic", ())


def modal_input(frequencies, dataset_types=(55,), frozen=True, source=ModalInputSource.CURVE_FITTED):
    modes = tuple(ExperimentalMode(i, f) for i, f in sorted(frequencies.items()))
    identity = FrozenModalSetIdentity(SHA, "SYNTH/frozen-1", len(modes), "curve-fitted dataset 55",
                                      "synthetic frozen modal set") if frozen else None
    return StageAModalInput(tuple(dataset_types), classification(source), identity, modes)


def thickness(points=THICKNESS_MM, gauge=None) -> ThicknessCharacterization:
    return ThicknessCharacterization(tuple(ThicknessPoint(f"P{i + 1}", v) for i, v in enumerate(points)),
                                     "synthetic thickness map", gauge_uncertainty=gauge)


def excitation(attachment_g=2.0) -> ExcitationEvidence:
    return ExcitationEvidence(ExcitationRoute.CONTACT_ATTACHMENT, ("E1", "E2"), attachment_g, "synthetic balance")


def evidence(frequencies=None, **changes) -> StageAExperimentalEvidence:
    frequencies = truth_frequencies() if frequencies is None else frequencies
    base = StageAExperimentalEvidence(
        "SYNTH-PLATE-1", "RUN-A", modal_input(frequencies), thickness(), excitation(),
        TrustedSuspensionThreshold(5.0, "synthetic suspension record"),
        SpecimenMeasurements(79.6, 0.01, 350.0, 347.0, 0.5, "synthetic measurements"))
    return replace(base, **changes)


def baseline_fe_modes(b=B_INDEPENDENT, c=C) -> dict[int, int]:
    """Experimental mode i (elastic DOF i) → its FE mode number at the baseline (start) state, by shape."""
    state = forward(b, c=c).state(START["D11"], GOVERNED_NU12 * START["D11"], START["D66"])
    return {int(np.argmax(np.abs(shape))) - RIGID + 1: number for number, shape in zip(state.mode_numbers,
                                                                                       state.shapes)}


def pairing(families=None, holdout=(), clusters=(), mac=0.98, b=B_INDEPENDENT, c=C, **changes) -> StageAPairingEvidence:
    families = families or {1: "B", 2: "T", 3: "B", 4: "T", 5: "B", 6: "T"}
    fe = baseline_fe_modes(b, c)
    rows = tuple(StageAObservationRow(f"R{i}", i, fe[i], families[i],
                                      ObservationRole.HOLDOUT if i in holdout else ObservationRole.FIT, mac)
                 for i in range(1, len(A) + 1))
    base = StageAPairingEvidence(rows, tuple(clusters), STRICT_IDENTIFICATION_PAIRING.policy_id,
                                 "production_comparator", "f" * 64, False, "synthetic strict pairing")
    return replace(base, **changes)


def sigma(pair):
    return (spec_provisional_setup_term(observation_term_ids(pair)),)


def run(**overrides):
    from services.stage_a_validation import run_stage_a_validation

    pair = overrides.pop("pairing", None) or pairing()
    arguments = dict(evidence=evidence(), pairing=pair, forward=forward(), sigma=sigma(pair), start=START,
                     bounds=BOUNDS, lm_settings=LM_SETTINGS, case_label="synthetic Stage-A")
    arguments.update(overrides)
    return run_stage_a_validation(**arguments)

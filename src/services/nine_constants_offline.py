"""Nine-constant research diagnostic without Abaqus — research track NINE-EC (Phase G service).

The one service the CLI-free GUI view calls (no second scientific implementation in GUI code):

- ``offline_preview(inp, unv, ...)``: real files, no FE solve. Reads the material (explicit choice when several carry
  Engineering Constants), its admissibility, element formulation and orientation; the experimental modal sets (explicit
  choice when several); and, when a Quick Calibration ``result.json`` of the SAME INP / UNV / modal set is given, its
  frozen accepted observation rows. With n accepted rows the nine-column system has rank ≤ n, so nine constants are
  refused whenever n < 9 — no FE evaluation can change that. Without frozen rows every constant is NOT_EVALUATED: the
  sensitivities need FE evaluations, and a real Abaqus run needs HUMAN approval (never started here). A Quick
  Calibration ESTIMATE is shown only as a separate effective-model reference (question B), never as nine values.
- ``synthetic_demo(case)``: the synthetic block model (SYNTHETIC / TEST EVIDENCE), full engine path.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable, Optional

from domain.forward_model_manifest import EngineeringConstants
from domain.orthotropic_elasticity import NAMES

from .nine_constants_engine import (
    ConstantStatus,
    ObservationRow,
    Role,
    SP13_MEASURED_PROFILE,
    assess_identifiability,
    estimate_constants,
    plan_fe_evaluations,
)
from .nine_constants_inp import NineConstantsInputError, material_candidates, read_nine_constants_model
from .nine_constants_report import build_report
from .nine_constants_synthetic import perturbed_states, separated_modes, synthetic_experiment
from .orthotropic_block_model import BlockForwardModel, OrthotropicBlock

QUESTION = "RESEARCH_DIAGNOSTIC: nine independent orthotropic Engineering Constants (identifiability first)"
NO_FE = ("no FE sensitivity evaluation: the nine-constant sensitivities need Abaqus solves of this model "
         "(a real run requires HUMAN approval and is never started by this view)")


class OfflinePreviewChoiceRequired(ValueError):
    """A physically consequential choice is missing (material or modal set); the options are listed."""

    def __init__(self, field: str, options: list[str], message: str) -> None:
        super().__init__(message)
        self.field, self.options = field, options


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _frozen_rows(result: dict, inp_sha: str, unv_sha: str, modal_set: Optional[str]) -> list[ObservationRow]:
    inputs = result.get("inputs") or {}
    problems = []
    if inputs.get("model_inp_sha256") != inp_sha:
        problems.append("its model INP is not the selected INP (SHA-256)")
    if inputs.get("experiment_sha256") != unv_sha:
        problems.append("its experimental file is not the selected file (SHA-256)")
    if modal_set is not None and inputs.get("modal_set") not in (None, modal_set):
        problems.append(f"its modal set {inputs.get('modal_set')!r} is not {modal_set!r}")
    if problems:
        raise ValueError("the Quick Calibration result cannot be used: " + "; ".join(problems))
    rows = []
    for row in result.get("rows") or []:
        mac = row.get("pair_mac", row.get("mac"))
        if mac is None or mac < 0.8:
            raise ValueError(f"row {row['row_id']}: no strict accepted pair (MAC {mac}).")
        rows.append(ObservationRow(str(row["row_id"]), float(row["experimental_hz"]), int(row["baseline_fe_mode"]),
                                   f"UNCLASSIFIED:{row['row_id']}", Role.FIT, None))
    return rows


def _effective_reference(result: dict) -> Optional[dict]:
    if result.get("status") != "ESTIMATE":
        return {"source": "Quick Calibration", "status": result.get("status"),
                "statement": "no effective-model value (refused or diagnostic run)"}
    out = {"source": "Quick Calibration (question B: effective FE-model calibration)",
           "labels": ["EFFECTIVE_MODEL_CALIBRATION", "NOT_A_MATERIAL_PROPERTY"], "grade": result.get("overall_grade")}
    for name, estimate in (result.get("estimates") or {}).items():
        out[name] = {"multiplier": estimate.get("multiplier"), "band_percent": estimate.get("band_percent"),
                     "constants_scaled_together": sorted(estimate.get("constants") or {}),
                     "statement": "one common multiplier of the listed constants — NOT independent per-constant values"}
    return out


def offline_preview(inp_path: Path, unv_path: Path, material: Optional[str] = None, modal_set: Optional[str] = None,
                    quick_calibration_result: Optional[Path] = None,
                    discover: Optional[Callable] = None) -> dict:
    """The nine-row research diagnostic of real files without any FE solve (see module docstring)."""
    inp_path, unv_path = Path(inp_path), Path(unv_path)
    source = inp_path.read_bytes()
    inp_sha = hashlib.sha256(source).hexdigest()
    unv_sha = _sha256(unv_path)
    inputs = {"inp": str(inp_path), "inp_sha256": inp_sha, "experiment": str(unv_path), "experiment_sha256": unv_sha}
    candidates = material_candidates(source)
    try:
        model = read_nine_constants_model(source, material)
    except NineConstantsInputError as error:
        eligible = [c.name for c in candidates if c.eligible]
        if material is None and len(eligible) > 1:
            raise OfflinePreviewChoiceRequired("material", eligible, str(error)) from None
        return build_report(question=QUESTION, inputs=inputs, model=None, experiment=None, registration=None,
                            observations=[], assessment=None, estimation=None, fe_plan=None, fe_provenance=None,
                            effective_model_reference=None, refusals=[str(error)],
                            blanket_status=ConstantStatus.INVALID_OR_UNSUPPORTED_MODEL.value,
                            blanket_reason=str(error))
    model_record = model.to_dict()
    if not model.admissibility.admissible:
        reason = "input constants are not physically admissible: " + "; ".join(model.admissibility.violations)
        return build_report(question=QUESTION, inputs=inputs, model=model_record, experiment=None, registration=None,
                            observations=[], assessment=None, estimation=None, fe_plan=None, fe_provenance=None,
                            effective_model_reference=None, refusals=[reason],
                            blanket_status=ConstantStatus.INVALID_OR_UNSUPPORTED_MODEL.value, blanket_reason=reason)
    if discover is None:
        from .quick_calibration import discover_modal_sets as discover
    sets = list(discover(unv_path))
    experiment = {"modal_sets": [{"key": s.key, "label": s.label, "modes": s.mode_count} for s in sets]}
    chosen = None
    if modal_set is not None:
        chosen = next((s for s in sets if s.key == modal_set), None)
        if chosen is None:
            raise OfflinePreviewChoiceRequired("modal_set", [s.key for s in sets], f"modal set {modal_set!r} not found.")
    elif len(sets) == 1:
        chosen = sets[0]
    elif len(sets) > 1:
        raise OfflinePreviewChoiceRequired("modal_set", [s.key for s in sets],
                                           f"{len(sets)} modal sets in the experimental file: choose one.")
    experiment["selected_modal_set"] = None if chosen is None else chosen.key
    experiment["selected_mode_count"] = None if chosen is None else chosen.mode_count
    rows, reference, refusals, registration = [], None, [], None
    if quick_calibration_result is not None:
        result = json.loads(Path(quick_calibration_result).read_text(encoding="utf-8"))
        rows = _frozen_rows(result, inp_sha, unv_sha, None if chosen is None else chosen.key)
        reference = _effective_reference(result)
        registration = (result.get("registration") or {}).get("physical_registration")
        inputs["quick_calibration_result"] = str(quick_calibration_result)
    assessment = assess_identifiability(model.constants, rows if quick_calibration_result is not None else None, None,
                                        NAMES, (), formulation_use=model.formulation_use)
    if not rows:
        refusals.append(NO_FE + "; no frozen accepted observations are available either (a governed baseline "
                        "pairing needs an FE baseline)")
    plan = plan_fe_evaluations(9, profile=SP13_MEASURED_PROFILE)
    return build_report(question=QUESTION, inputs=inputs, model=model_record, experiment=experiment,
                        registration=registration, observations=rows, assessment=assessment, estimation=None,
                        fe_plan=plan, fe_provenance={"fe_evaluations_in_this_preview": 0,
                                                     "abaqus_started": False},
                        effective_model_reference=reference, refusals=refusals)


# ----------------------------------------------------------------------------- synthetic demonstrations

TRUTH = EngineeringConstants(E1=120000, E2=9000, E3=8500, nu12=0.30, nu13=0.32, nu23=0.45, G12=5000, G13=4800,
                             G23=3200)
START = EngineeringConstants(E1=115000, E2=9300, E3=8200, nu12=0.29, nu13=0.33, nu23=0.44, G12=5200, G13=4650,
                             G23=3300)
DEMO_POISSON_LIMIT = 0.05  # demonstration input: a caller-declared research limit (UNACCEPTED), shown in the record
SYNTHETIC_CASES = {
    "full": "thick block 26 × 12.6 × 8.8 mm, 27 separated FIT modes + 3 HOLDOUT, synthetic sd 0.03 % "
            "(all nine observable)",
    "two_rows": "thick block, only two accepted observations (rank ≤ 2: refusal)",
    "thin_plate": "thin plate 80 × 54 × 1.6 mm, 18 FIT + 2 HOLDOUT, sd 0.3 % (all nine asked: weak transverse "
                  "sensitivities)",
    "thin_plate_reduced": "the same thin plate, E3, ν13, ν23 declared FIXED (not identified); six constants asked",
}
REDUCED_FIXED = ("E3", "nu13", "nu23")


def synthetic_demo(case: str) -> dict:
    """A SYNTHETIC research run of the full engine path (no Abaqus); the report carries the synthetic label."""
    if case not in SYNTHETIC_CASES:
        raise ValueError(f"unknown synthetic case {case!r}.")
    fixed: tuple[str, ...] = ()
    if case.startswith("thin_plate"):
        forward = BlockForwardModel(OrthotropicBlock((40.0, 27.0, 0.8), 1.55e-9, order=10), 40)
        modes = separated_modes(forward, perturbed_states(START), 20)
        experiment = synthetic_experiment(forward, START, START, modes, 2, sd_ln=0.003, seed=1)
        if case == "thin_plate_reduced":
            fixed = REDUCED_FIXED
    else:
        forward = BlockForwardModel(OrthotropicBlock((13.0, 6.3, 4.4), 1.55e-9, order=10), 48)
        modes = separated_modes(forward, [TRUTH, START], 30 if case == "full" else 2)
        experiment = synthetic_experiment(forward, TRUTH, START, modes, 3 if case == "full" else 0,
                                          sd_ln=0.0003, noise_sd_ln=0.00015, seed=7)
    estimated = tuple(n for n in NAMES if n not in fixed)
    estimation = estimate_constants(forward, START, experiment.rows, estimated, fixed, evaluation_limit=200,
                                    poisson_sd_limit=DEMO_POISSON_LIMIT)
    synthetic = dict(experiment.to_dict(), case=case, description=SYNTHETIC_CASES[case],
                     forward=forward.identity(), research_poisson_sd_limit=DEMO_POISSON_LIMIT)
    return build_report(question=QUESTION + " — SYNTHETIC", inputs={"synthetic_case": case},
                        model={"material": "SYNTHETIC_ORTHOTROPIC", "model_kind": "3D_SOLID (synthetic block)",
                               "constants": START.to_dict(), "source_sha256": forward.block.geometry_id},
                        experiment={"synthetic_rows": len(experiment.rows)}, registration={"status": "SYNTHETIC"},
                        observations=list(experiment.rows), assessment=None, estimation=estimation,
                        fe_plan=plan_fe_evaluations(len(estimated)),
                        fe_provenance={"forward_evaluations": estimation.evaluations,
                                                                       "abaqus_started": False},
                        effective_model_reference=None, refusals=[], synthetic=synthetic)

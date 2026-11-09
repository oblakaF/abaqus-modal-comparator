"""MAT-3: what the Materials page's study section computes and shows, with no Qt.

This is an adapter. The only fitting is ``run_plate_inverse_study`` of ``services.plate_material_workflow``, the one workflow
over both forward backends, and nothing here changes its result. Every table is made from the saved form of a result, so a
fresh result and a reopened project are shown by the same code from the same values.

A study here is always a built-in SYNTHETIC software test: its observations are computed from known values by the functions
below, and no function here takes a file of measured data. Recovering known values tests the software. Real files are only
inspected on this page, and the workflow's own refusal is shown for them.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import math
from pathlib import Path
import tempfile
import threading
from typing import Any, Callable, Mapping, Optional

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
import numpy as np
from scipy import sparse

from domain.plate_inverse_problem import (
    FittedParameter,
    FrozenPlateObservation,
    InverseResourceBudget,
    ObservationRole,
    PlateInverseDeclaration,
    StudyIntent,
)
from domain.plate_material_problem import (
    CoordinateObservationSet,
    DofObservation,
    DofObservationSet,
    EvidenceKind,
    ExecutionStatus,
    ForwardBackendId,
    ObservationPoint,
    PlateForwardRefusal,
    PlateGeometry,
    QuantityEvidence,
    QuantitySource,
    ResourceLimits,
)
from services import materials_project as mp
from services.matrix_model_service import AbaqusDof, StageAAffineBasis, StageAMatrixParameters
from services.plate_forward_adapter import StageAMatrixForwardBackend, inspect_stage_a_package, write_stage_a_package
from services.plate_material_workflow import RITZ_PARAMETERS, STAGE_A_PARAMETERS, RitzInverseModel, run_plate_inverse_study
from services.plate_ritz_forward import RitzNumericalConfig, ritz_model_identity

RITZ = ForwardBackendId.KIRCHHOFF_RITZ_4D.value
STAGE_A = ForwardBackendId.STAGE_A_MATRIX_3D.value
BUILT_IN, SELECTED = "BUILT_IN", "SELECTED"
SYNTHETIC_SOURCE, REAL_SOURCE = "SYNTHETIC", "REAL"
SPECIMEN = "SYNTHETIC-NO-SPECIMEN"
REGISTRATION = "SYNTHETIC-REGISTRATION"
STAGE_MODEL = "SYNTHETIC-DIAGONAL-FIXTURE"
MODE_SOURCE = "curve-fitted modal dataset"
RITZ_PROVENANCE = "SYNTHETIC: observations computed by the Ritz solver at the known values; not a measurement"
STAGE_PROVENANCE = "SYNTHETIC: observations computed from a diagonal matrix fixture at the known values; not a measurement"
STATEMENT = ("SYNTHETIC software test. Recovering known values tests the software and says nothing about a real material. "
             "A diagnostic candidate is not a material property, a ply constant or a calibration.")
DASH = "—"
DERIVED = " (derived)"

METHOD_NAMES = {RITZ: "Ritz plate model", STAGE_A: "Stage A matrix model"}
RESULT_STATEMENT = ("These numbers come from a synthetic software test. They are not accepted material properties, ply "
                    "constants or a calibration.")
METHOD_TEXT = {
    RITZ: ("Thin-plate model computed in this program. Fits four stiffnesses: D11, D22, D66 and u (D12 = u*D22). "
           "No ODB, Abaqus or matrix file is needed."),
    STAGE_A: ("Uses a prepared matrix package. Fits three parameters: D, D66 and r (D22 = D11 = D, D12 = r*D). Without a "
              "compatible package it refuses: Abaqus is not started, and the other method is not used instead."),
}
APPLICABILITY = {
    RITZ: ("Scope: one flat, rectangular, free-free, homogeneous-equivalent orthotropic plate with known material axes: constant "
           "D, no bending-extension coupling, no D16 or D26, uniform mass. Shear, rotary inertia, suspension, prestress and "
           "non-uniformity are not in the model and are not checked here. Thinness alone does not prove the model applies."),
    STAGE_A: ("Scope: only the model and the parameter range stored in the package. The built-in package is a small diagonal "
              "test fixture, not a model of any plate. This method does not use geometry or mass."),
}
ROLE_LIMIT = {"log": "Model stiffness; not a ply constant",
              "linear": "Signed; no precision rule approved",
              "derived": "Derived; uncertainty not propagated"}
RUN_BLOCKED = "Real-data inverse execution: BLOCKED"
# ABM-UX5: what the page is doing, in plain words; every status code stays exact in the results and details
EXAMPLE_BANNER = {
    RITZ: "BUILT-IN SYNTHETIC EXAMPLE: it tests the Ritz method on known stiffnesses; it does not identify your material.",
    STAGE_A: ("BUILT-IN SYNTHETIC EXAMPLE: it tests the Stage A method on a compatible matrix package, not on a plate size "
              "and mass; it does not identify your material."),
}
REAL_BANNER = "Using: REAL FILES, view only. Identifying a real material is blocked on this page."
REAL_NEXT = ("What you can do with real data: the Research Tuning page explores a supported shell INP against fitted PolyMAX "
             "frequencies (research only, no material property). Analyze and MAC / Points compare FE and EXP shapes.")
GEOMETRY_WHY = "Plate of the synthetic example: it makes the example's frequencies; not your specimen"
PARAMETER_HELP = {
    RITZ: ("D11, D22: bending stiffness along a and along b. D66: twisting stiffness. D12 = u·D22 is derived (u has no "
           "unit). All in N·m. Known synthetic: the value that made the example's frequencies. Start: where the optimizer "
           "begins. Calculated: what the fit found. You do not need to calculate any of them to run the example."),
    STAGE_A: ("D = D11 = D22: bending stiffness. D66: twisting stiffness. D12 = r·D is derived (r has no unit). All in N·m. "
              "Known synthetic: the value that made the example's frequencies. Start: where the optimizer begins. "
              "Calculated: what the fit found. You do not need to calculate any of them to run the example."),
}
CONVERGENCE_MEANING = ("Converged means the optimizer settled on these numbers; it does not make them a verified material "
                       "property.")
CODE_MEANING = {
    "DIAGNOSTIC_OPTIMIZER_CANDIDATE": "DIAGNOSTIC_OPTIMIZER_CANDIDATE: numbers the optimizer found and checked, kept for diagnosis only.",
    "NOT_A_RELEASE_VALUE": "NOT_A_RELEASE_VALUE: must not be used as a material property.",
}
REAL_NOTE = ("Real files are only inspected here. No text, setting or saved file enables a fit on measured data, and these "
             "values are never used in the synthetic test.")
TERM_HELP = {
    "MAC": "MAC measures how similar two mode shapes are (0 to 1). Here it only checks that a mode is the same mode; no material value is fitted to MAC.",
    "HOLDOUT": "HOLDOUT modes are left out of the fit. They show whether the model predicts what it was not tuned to. FIT modes are the ones the fit uses.",
    "rank": "Rank: how many parameters these modes can determine independently. Condition number: how poorly the parameters are told apart.",
    "sigma": "Sigma: the stated error of ln(f) in one observation row. It sets the weight of that row in the fit.",
    "uncertainty": "Uncertainty: an estimate of the spread of the result. Only the available components are shown; missing ones are listed and never taken as zero.",
}
EXECUTION_TEXT = {"COMPLETED": "Completed", "CANCELLED": "Cancelled", "BUDGET_EXHAUSTED": "Stopped: limit reached",
                  "REFUSED": "Refused", "FAILED": "Failed"}
UNIT_TEXT = {"N*m": "N·m", "1": "dimensionless", "Hz": "Hz"}
EXPORT_SIZE = (1600, 900, 2.0)  # logical width and height, and scale: a saved plot is 3200 x 1800 pixels, whatever the screen
BASE_DPI = 100
_INK, _MUTED, _GRID = "#3e4c59", "#52606d", "#e4e7eb"
_FIRST, _SECOND, _HOLDOUT_BAND = "#2563eb", "#b45309", "#fdf3e7"
MAX_SOLVES_CAP, MAX_SECONDS_CAP = 5000, 1800
_RITZ_GRID = tuple((x * 7.0 / 15.0, y * 9.0 / 20.0) for x in (-1.0, -0.6, -0.2, 0.2, 0.6, 1.0) for y in (-1.0, -0.5, 0.0, 0.5, 1.0))

# The Stage-A test fixture: diagonal K and M with three rigid DOFs, so the exact solution is known in closed form.
_RIGID = 3
_REFERENCE = (0.34, 0.03, 0.040)
_A = np.array([1.0e5, 0.2e5, 0.5e5, 1.5e5, 2.6e5, 4.0e5, 3.3e5, 5.5e5, 6.5e5])
_B = np.array([0.0, 3.0e5, 0.0, 6.0e5, 9.0e5, 2.0e5, -5.0e5, 7.0e5, 1.0e5])
_C = np.array([0.4e5, 7.0e5, 9.0e5, 6.0e5, 0.3e5, 1.0e5, 12.0e5, 5.0e5, 16.0e5])
_ELASTIC_MASS = np.array([1.0, 1.1, 0.9, 1.2, 0.8, 1.05, 1.0, 0.95, 1.1])
_STAGE_DOMAIN = {"D11": (0.2, 0.6), "D12": (-0.1, 0.1), "D66": (0.02, 0.08)}
_STAGE_FIT, _STAGE_HOLDOUT = (0, 1, 2, 3, 4, 5, 6), (7,)


class FormProblem(ValueError):
    """The form cannot become a study; each item names one field."""

    def __init__(self, items) -> None:
        super().__init__("; ".join(items))
        self.items = tuple(items)


def default_form(backend: str = RITZ) -> dict:
    """The built-in example. The known values differ from the start values, so a fit has work to do."""
    if backend == RITZ:
        parameters = {"D11": ("12.0", "13.0", "6.0", "24.0"), "D22": ("7.0", "6.5", "3.5", "14.0"),
                      "D66": ("2.3", "2.5", "1.2", "4.6"), "u": ("0.15", "0.10", "-0.5", "0.5")}
    else:
        parameters = {"D": ("0.36", "0.34", "0.2", "0.6"), "D66": ("0.05", "0.046", "0.02", "0.08"),
                      "r": ("0.09", "0.05", "-0.16", "0.16")}
    return {"backend": backend,
            "geometry": {"a": "300", "b": "200", "length_unit": "mm", "mass_basis": "mass", "mass": "120", "mass_unit": "g",
                         "thickness": "2"},
            "parameters": {name: dict(zip(("truth", "start", "lower", "upper"), values)) for name, values in parameters.items()},
            "numerics": {"degree": "8", "mode_count": "14" if backend == RITZ else "9",
                         "observed_modes": "10" if backend == RITZ else "8", "holdout_modes": "2" if backend == RITZ else "1",
                         "sigma": "0.001"},
            "budget": {"max_solves": "900", "max_seconds": "60"},
            "package": {"source": BUILT_IN, "path": ""},
            "authorization_note": ""}


# ---------------------------------------------------------------------------------------------- the form


def _float(text: str, name: str, problems: list) -> float:
    try:
        value = float(str(text).strip().replace(",", "."))
    except ValueError:
        problems.append(f"{name}: enter a number")
        return math.nan
    if not math.isfinite(value):
        problems.append(f"{name}: enter a finite number")
    return value


def _whole(text: str, name: str, problems: list, low: int, high: int) -> int:
    try:
        value = int(str(text).strip())
    except ValueError:
        problems.append(f"{name}: enter a whole number")
        return low
    if not low <= value <= high:
        problems.append(f"{name}: {low} to {high}")
    return value


def geometry_of(form: Mapping) -> PlateGeometry:
    """Geometry in stated units, SI inside. Raises ``FormProblem``."""
    entered, problems = form["geometry"], []
    a, b = _float(entered["a"], "a", problems), _float(entered["b"], "b", problems)
    mass = _float(entered["mass"], "mass", problems)
    thickness = _float(entered["thickness"], "thickness", problems) if str(entered["thickness"]).strip() else None
    if problems:
        raise FormProblem(problems)
    names = ("a", "b", "mass") + (() if thickness is None else ("thickness",))
    evidence = tuple(QuantityEvidence(name, QuantitySource.SYNTHETIC, None, "declared for this SYNTHETIC test") for name in names)
    try:
        if entered["mass_basis"] == "surface":
            return PlateGeometry.from_units(a, b, entered["length_unit"], surface_mass_kg_m2=mass, thickness=thickness,
                                            evidence=evidence)
        return PlateGeometry.from_units(a, b, entered["length_unit"], mass=mass, mass_unit=entered["mass_unit"],
                                        thickness=thickness, evidence=evidence)
    except PlateForwardRefusal as refusal:
        raise FormProblem((refusal.reason,)) from refusal


def geometry_text(form: Mapping) -> str:
    """What the entered values mean in SI, or the problem with them."""
    try:
        geometry = geometry_of(form)
    except FormProblem as problem:
        return f"Not usable: {problem}"
    text = (f"a = {geometry.a_m:.6g} m, b = {geometry.b_m:.6g} m, surface mass = {geometry.surface_mass_kg_m2:.6g} kg/m²")
    if geometry.thickness_m is None:
        return text + ". No thickness: D is reported, and E and G stay missing."
    return (text + f", thickness = {geometry.thickness_m:.6g} m. Ratio min(a, b)/h = "
            f"{min(geometry.a_m, geometry.b_m) / geometry.thickness_m:.4g}; this does not prove thin-plate behaviour.")


@dataclass(frozen=True)
class Parsed:
    backend: str
    truth: Mapping[str, float]
    parameters: tuple
    degree: int
    mode_count: int
    observed_modes: int
    holdout_modes: int
    sigma: float
    max_solves: int
    max_seconds: float


def parse_form(form: Mapping) -> Parsed:
    """The numbers of a form. Raises ``FormProblem``; whether a study can run is left to the workflow."""
    problems: list = []
    backend = form["backend"]
    names = RITZ_PARAMETERS if backend == RITZ else STAGE_A_PARAMETERS
    if tuple(form["parameters"]) != tuple(names):
        raise FormProblem((f"this method fits exactly {', '.join(names)}",))
    truth, parameters = {}, []
    for name in names:
        entry = form["parameters"][name]
        truth[name] = _float(entry["truth"], f"{name} known value", problems)
        start = _float(entry["start"], f"{name} start", problems)
        lower = _float(entry["lower"], f"{name} lower bound", problems)
        upper = _float(entry["upper"], f"{name} upper bound", problems)
        parameters.append(FittedParameter(name, start, lower, upper))
    numerics, budget = form["numerics"], form["budget"]
    degree = _whole(numerics["degree"], "Basis degree", problems, 2, 31) if backend == RITZ else 0
    mode_count = _whole(numerics["mode_count"], "Solved modes", problems, 2, 64)
    observed = _whole(numerics["observed_modes"], "Observed modes", problems, 2, 64)
    holdout = _whole(numerics["holdout_modes"], "HOLDOUT modes", problems, 1, 64)
    sigma = _float(numerics["sigma"], "Sigma", problems)
    if math.isfinite(sigma) and sigma <= 0.0:
        problems.append("Sigma: must be positive")
    if holdout >= observed:
        problems.append("HOLDOUT modes: must be fewer than the observed modes")
    if observed >= mode_count:
        problems.append("Solved modes: must exceed the observed modes")
    solves = _whole(budget["max_solves"], "Solve limit", problems, 1, MAX_SOLVES_CAP)
    seconds = _float(budget["max_seconds"], "Time limit", problems)
    if math.isfinite(seconds) and not 0.0 < seconds <= MAX_SECONDS_CAP:
        problems.append(f"Time limit: above 0 and at most {MAX_SECONDS_CAP} s")
    if problems:
        raise FormProblem(problems)
    return Parsed(backend, truth, tuple(parameters), degree, mode_count, observed, holdout, sigma, solves, seconds)


def preflight(form: Mapping) -> tuple:
    """(rows, problems): the resources a run may use, checked against the limits before it can start."""
    limits = ResourceLimits()
    found: list = []
    parsed = None
    try:
        parsed = parse_form(form)
    except FormProblem as problem:
        found.extend(problem.items)
    if form["backend"] == RITZ:
        try:
            geometry_of(form)
        except FormProblem as problem:
            found.extend(problem.items)
    if found:
        return (), tuple(found)
    problems, rows = [], []
    if parsed.backend == RITZ:
        dofs = (parsed.degree + 1) ** 2
        memory = 8 * dofs * dofs * 8  # the five geometry matrices and three working matrices, dense
        rows.append(("Model size", f"{dofs} coefficients", f"at most {limits.max_dofs}", _state(dofs <= limits.max_dofs)))
        rows.append(("Estimated working memory", f"{memory / 2 ** 20:.1f} MiB", f"at most {limits.max_allocation_bytes / 2 ** 20:.0f} MiB",
                     _state(memory <= limits.max_allocation_bytes)))
        if dofs > limits.max_dofs:
            problems.append(f"Basis degree: {dofs} coefficients exceed the limit of {limits.max_dofs}")
        if memory > limits.max_allocation_bytes:
            problems.append("Basis degree: the estimated memory exceeds the limit")
    else:
        rows.append(("Package", "size checked when it is opened", f"at most {limits.max_package_file_bytes / 2 ** 20:.0f} MiB", "CHECKED WHEN OPENED"))
    rows.append(("Solve limit", str(parsed.max_solves), f"at most {MAX_SOLVES_CAP}", "OK"))
    rows.append(("Time limit", f"{parsed.max_seconds:g} s", f"at most {MAX_SECONDS_CAP} s", "OK"))
    return tuple(rows), tuple(problems)


def _state(good: bool) -> str:
    return "OK" if good else "OVER THE LIMIT"


# ---------------------------------------------------------------------------------------------- building a synthetic study


@dataclass(frozen=True)
class StudyRequest:
    declaration: PlateInverseDeclaration
    package: Optional[Path]
    known_values: Mapping[str, float]
    units: Mapping[str, str]
    provenance: Mapping[str, str]
    references: tuple


def _mac(left: np.ndarray, right: np.ndarray) -> float:
    return float(left @ right) ** 2 / float((left @ left) * (right @ right))


def _budget(parsed: Parsed) -> InverseResourceBudget:
    return InverseResourceBudget(parsed.max_solves, float(parsed.max_seconds), ResourceLimits())


def _ritz_request(form: Mapping, parsed: Parsed) -> StudyRequest:
    geometry = geometry_of(form)
    points = CoordinateObservationSet(REGISTRATION, tuple(
        ObservationPoint(f"p{index}", x * geometry.a_m, y * geometry.b_m) for index, (x, y) in enumerate(_RITZ_GRID)))
    config = RitzNumericalConfig(parsed.degree, parsed.degree, parsed.mode_count)
    budget = _budget(parsed)
    helper = PlateInverseDeclaration(
        "SYNTHETIC-HELPER", StudyIntent.SYNTHETIC_SOFTWARE_TEST, EvidenceKind.SYNTHETIC, ForwardBackendId.KIRCHHOFF_RITZ_4D, "",
        SPECIMEN, points, (), (), geometry=geometry, degree_x=parsed.degree, degree_y=parsed.degree,
        forward_mode_count=parsed.mode_count, provenance=RITZ_PROVENANCE, budget=budget)
    model = RitzInverseModel(helper)
    truth = model.solve(dict(parsed.truth))
    start = model.solve({item.name: item.start for item in parsed.parameters})
    rows = []
    holdout = set(range(parsed.observed_modes - parsed.holdout_modes + 1, parsed.observed_modes + 1))
    for mode in range(1, parsed.observed_modes + 1):  # the identity is frozen here, once, before the study starts
        scores = [_mac(truth.observed[:, mode - 1], start.observed[:, other]) for other in range(start.observed.shape[1])]
        rows.append(FrozenPlateObservation(
            f"row{mode}", mode, truth.frequencies_hz[mode - 1], int(np.argmax(scores)) + 1,
            ObservationRole.HOLDOUT if mode in holdout else ObservationRole.FIT, f"F{mode}", MODE_SOURCE,
            tuple(truth.observed[:, mode - 1]), None, parsed.sigma, False))
    declaration = PlateInverseDeclaration(
        "SYNTHETIC-RITZ-EXAMPLE", StudyIntent.SYNTHETIC_SOFTWARE_TEST, EvidenceKind.SYNTHETIC, ForwardBackendId.KIRCHHOFF_RITZ_4D,
        ritz_model_identity(geometry, config), SPECIMEN, points, tuple(rows), parsed.parameters, geometry=geometry,
        degree_x=parsed.degree, degree_y=parsed.degree, forward_mode_count=parsed.mode_count,
        execution_authorization=form["authorization_note"] or None, provenance=RITZ_PROVENANCE, budget=budget)
    known = dict(parsed.truth, D12=parsed.truth["u"] * parsed.truth["D22"])
    return StudyRequest(declaration, None, known, {"D11": "N*m", "D22": "N*m", "D12": "N*m", "D66": "N*m", "u": "1", "frequency": "Hz",
                                                   "length": "m (entered in " + form["geometry"]["length_unit"] + ")"},
                        {"source": "built-in SYNTHETIC example", "forward_model": ritz_model_identity(geometry, config)}, ())


def _stage_basis() -> StageAAffineBasis:
    def stiffness(values):
        return sparse.diags(np.concatenate([np.zeros(_RIGID), values]), format="csr")

    return StageAAffineBasis(
        StageAMatrixParameters(*_REFERENCE),
        stiffness(_A * _REFERENCE[0] + _B * _REFERENCE[1] + _C * _REFERENCE[2]),
        (stiffness(_A), stiffness(_B), stiffness(_C)),
        sparse.diags(np.concatenate([np.ones(_RIGID), _ELASTIC_MASS]), format="csr"),
        tuple(AbaqusDof(index + 1, 3) for index in range(_A.size + _RIGID)))


def write_synthetic_package(directory: Path) -> Path:
    """The explicitly SYNTHETIC test package of the Stage-A example, in a new folder."""
    return write_stage_a_package(
        _stage_basis(), directory, specimen_id=SPECIMEN, model_id=STAGE_MODEL, evidence_kind=EvidenceKind.SYNTHETIC,
        units="N-m-kg-s", validity_domain=_STAGE_DOMAIN, expected_rigid_body_modes=_RIGID,
        description="SYNTHETIC diagonal test fixture; not a model of any plate")


def _stage_lambda(point: Mapping[str, float]) -> np.ndarray:
    return (_A * point["D"] + _B * point["r"] * point["D"] + _C * point["D66"]) / _ELASTIC_MASS


def _stage_request(form: Mapping, parsed: Parsed, scratch: Path) -> StudyRequest:
    built_in = write_synthetic_package(scratch / "synthetic_package")
    backend = StageAMatrixForwardBackend.open(built_in, expected_specimen_id=SPECIMEN, expected_model_id=STAGE_MODEL)
    start_point = {item.name: item.start for item in parsed.parameters}
    truth_values, start_values = _stage_lambda(parsed.truth), _stage_lambda(start_point)
    if (truth_values <= 0.0).any() or (start_values <= 0.0).any():
        raise FormProblem(("These values make a fixture eigenvalue non-positive",))
    start_order, truth_order = list(np.argsort(start_values)), list(np.argsort(truth_values))
    rows = []
    for rank, dof in enumerate(truth_order, start=1):
        if int(dof) not in _STAGE_FIT + _STAGE_HOLDOUT:
            continue
        shape = np.zeros(_A.size)
        shape[dof] = 1.0 / math.sqrt(_ELASTIC_MASS[dof])
        rows.append(FrozenPlateObservation(
            f"dof{dof}", rank, math.sqrt(truth_values[dof]) / (2.0 * math.pi), start_order.index(dof) + 1,
            ObservationRole.HOLDOUT if int(dof) in _STAGE_HOLDOUT else ObservationRole.FIT, f"F{dof}", MODE_SOURCE,
            tuple(shape), None, parsed.sigma, False))
    observations = DofObservationSet(REGISTRATION, tuple(
        DofObservation(f"o{index + 1 + _RIGID}", index + 1 + _RIGID, 3) for index in range(_A.size)))
    declaration = PlateInverseDeclaration(
        "SYNTHETIC-STAGE-A-EXAMPLE", StudyIntent.SYNTHETIC_SOFTWARE_TEST, EvidenceKind.SYNTHETIC, ForwardBackendId.STAGE_A_MATRIX_3D,
        backend.model_identity, SPECIMEN, observations, tuple(rows), parsed.parameters, forward_mode_count=parsed.mode_count,
        stage_a_model_id=STAGE_MODEL, execution_authorization=form["authorization_note"] or None, provenance=STAGE_PROVENANCE,
        budget=_budget(parsed))
    entered = form["package"]
    if entered["source"] == BUILT_IN:
        package, references = built_in, ()
        source = "built-in SYNTHETIC test package, generated for this run and not kept"
    else:  # the workflow judges the chosen package against this declaration; nothing is substituted when it refuses
        package = Path(entered["path"]) if entered["path"] else None
        references = (("Matrix package", entered["path"]),) if entered["path"] else ()
        source = "the package chosen on the page"
    known = dict(parsed.truth, D12=parsed.truth["r"] * parsed.truth["D"])
    return StudyRequest(declaration, package, known, {"D": "N*m", "D12": "N*m", "D66": "N*m", "r": "1", "frequency": "Hz"},
                        {"source": source, "forward_model": backend.model_identity, "constraint": "D22 = D11"}, references)


def build_request(form: Mapping, scratch: Path) -> StudyRequest:
    """A deterministic SYNTHETIC declaration from the form. Raises ``FormProblem``; takes no measured data by design."""
    parsed = parse_form(form)
    try:
        return _ritz_request(form, parsed) if parsed.backend == RITZ else _stage_request(form, parsed, scratch)
    except PlateForwardRefusal as refusal:
        raise FormProblem((f"The known or start values cannot be solved: {refusal.reason}",)) from refusal


def prepare_rows(form: Mapping) -> tuple:
    """The declared observations and their registration, before any fit. Solves only the two states it needs."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        request = build_request(form, Path(scratch))
    return observation_rows(mp.declaration_document(request.declaration)), registration_text(mp.declaration_document(request.declaration))


def execute_study(form: Mapping, cancel_event: threading.Event, on_solve: Optional[Callable[[], None]] = None) -> dict:
    """Build and run one SYNTHETIC study through the shared workflow. Returns the Materials section of the result."""
    def cancel() -> bool:
        if on_solve is not None:
            on_solve()
        return cancel_event.is_set()

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as scratch:
        request = build_request(form, Path(scratch))
        result = run_plate_inverse_study(request.declaration, stage_a_package=request.package, cancel=cancel)
    return mp.materials_section(form, request.known_values, request.declaration, result, request.units, request.provenance,
                                request.references, STATEMENT)


def is_cancelled(section: Mapping) -> bool:
    return section["result"]["execution_status"] == ExecutionStatus.CANCELLED.value


# ---------------------------------------------------------------------------------------------- real files: view only


def real_data_gate(authorization_text: str = "") -> tuple:
    """The workflow's own answer for a study on measured data: (code, reason). It refuses before any model is opened."""
    point = CoordinateObservationSet("UNDECLARED", (ObservationPoint("none", 0.0, 0.0),))
    declaration = PlateInverseDeclaration(
        "REAL-DATA-GATE", StudyIntent.MATERIAL_IDENTIFICATION_RESEARCH, EvidenceKind.PHYSICAL, ForwardBackendId.KIRCHHOFF_RITZ_4D, "",
        "UNDECLARED", point, (), (), execution_authorization=authorization_text or None)
    result = run_plate_inverse_study(declaration)
    return result.refusal_code.value, result.refusal_reason


def real_data_rows(facts, registration: str, authorization_text: str = "") -> tuple:
    code, reason = real_data_gate(authorization_text)
    if facts is None:
        rows = [("Data read", "No file read"), ("Mode shapes", "Unknown"), ("Data type", "UNKNOWN")]
    else:
        rows = [("Data read", "Yes"), ("Mode shapes", facts.shapes or "Unknown"), ("Data type", facts.data_kind or "UNKNOWN")]
    return tuple(rows + [("Registration", registration), ("Source", "Real experiment, chosen by the user"),
                         ("Real-data inverse execution", "BLOCKED"), ("Workflow answer", f"{code}: {reason}")])


def package_facts(path) -> tuple:
    """Identity, ranges and readiness of a chosen package, without loading its matrices. Raises ``PlateForwardRefusal``."""
    found = inspect_stage_a_package(path)
    manifest = found.manifest
    domain = manifest["validity_domain"]
    synthetic = manifest["evidence_kind"] == EvidenceKind.SYNTHETIC.value
    rows = [("Model", str(manifest["model_id"])), ("Declared source", str(manifest["specimen_id"])),
            ("Evidence kind", str(manifest["evidence_kind"])), ("Units", str(manifest["units"])),
            ("Parameters", ", ".join(str(item) for item in manifest["parameter_names"])), ("Constraint", str(manifest["constraint"])),
            ("Mass behaviour", str(manifest["mass_slope"])), ("Rigid modes expected", str(manifest["expected_rigid_body_modes"]))]
    rows += [(f"Domain {name}", f"{domain[name][0]:g} to {domain[name][1]:g}") for name in sorted(domain)]
    rows += [("Matrix DOFs", str(found.dof_count)), ("Matrix file SHA-256", found.matrix_sha256),
             ("Readiness", "Readable. A study still has to match this package's identity."
              if synthetic else "Readable, view only: real-data inverse execution is BLOCKED.")]
    return tuple(rows)


# ---------------------------------------------------------------------------------------------- the tables


def _text(value: Any) -> str:
    value = mp.number(value)
    if value is None:
        return DASH
    if isinstance(value, bool):
        return "yes" if value else "no"
    return f"{value:.6g}" if isinstance(value, (int, float)) else str(value)


def _percent(ratio: Optional[float]) -> str:
    if ratio is None:
        return DASH
    return _signed_percent(100.0 * ratio)


def _signed_percent(value: float) -> str:
    """Four decimals; a value too small for them keeps its size and sign instead of reading "-0.0000"."""
    return f"{value:+.2e} %" if value != 0.0 and abs(value) < 5.0e-5 else f"{value:+.4f} %"


def status_rows(section: Mapping) -> tuple:
    result, declaration = section["result"], section["declaration"]
    rows = [("Study", declaration["intent"]), ("Evidence", result["evidence_kind"]), ("Method", result["backend_id"]),
            ("Execution status", result["execution_status"]), ("Numerical status", result["numerical_status"]),
            ("Scientific status", result["scientific_status"]), ("Release status", result["release_status"])]
    if result["refusal_code"]:
        rows.append(("Refusal", result["refusal_code"]))
    return tuple(rows) + tuple(("Unchanged", item) for item in result["restrictions_unchanged"])


def method_title(backend: str) -> str:
    return f"{METHOD_NAMES.get(backend, backend)} ({backend})"


def result_summary(section: Mapping) -> tuple:
    """The short answer shown first: (caption, text). Every sentence keeps the exact status code beside it."""
    result = section["result"]
    execution, numerical = result["execution_status"], result["numerical_status"]
    scientific, release = result["scientific_status"], result["release_status"]
    if numerical in ("CONVERGED", "CONVERGED_AT_BOUND"):
        converged = "Reached at a range bound" if numerical == "CONVERGED_AT_BOUND" else "Reached"
    else:
        converged = "Not reached"
    if result["refusal_code"]:
        checks = f"Refused: {result['refusal_code']} ({scientific})"
    elif scientific == "DIAGNOSTIC_OPTIMIZER_CANDIDATE":
        checks = f"Passed: diagnostic candidate only ({scientific})"
    else:
        checks = f"Not passed ({scientific})"
    if result["evidence_kind"] == "SYNTHETIC":
        meaning = f"Synthetic software test, not a material value ({section['declaration']['intent']}, {release})"
    else:
        meaning = f"No real material value is available ({release})"
    return (("Run", f"{EXECUTION_TEXT.get(execution, execution)} ({execution}), {result['solves']} solves"),
            ("Method", method_title(result["backend_id"])), ("Convergence", f"{converged} ({numerical})"),
            ("Scientific checks", checks), ("Meaning of the numbers", meaning))


def status_meaning(section: Mapping) -> str:
    """The result's codes in ordinary words; the codes themselves stay as recorded."""
    result = section["result"]
    parts = [CONVERGENCE_MEANING] + [CODE_MEANING[code] for code in (result["scientific_status"], result["release_status"])
                                     if code in CODE_MEANING]
    return " ".join(parts)


def cancelled_summary(backend: str) -> tuple:
    return (("Run", "Cancelled at a safe point (CANCELLED). No result of this run is shown."),
            ("Method", method_title(backend)), ("Convergence", "Not evaluated"), ("Scientific checks", "Not run"),
            ("Meaning of the numbers", "No numbers"))


def _unit(units: Mapping, name: str) -> str:
    unit = units.get(name)
    return f"{name}, {UNIT_TEXT.get(unit, unit)}" if unit else name


def summary_parameter_rows(section: Mapping) -> tuple:
    """Parameter, initial, calculated, known: the same values as ``parameter_rows``, with their unit."""
    units = section["units"]
    rows = []
    for row in parameter_rows(section):
        derived = row[0].endswith(DERIVED)
        name = row[0][:-len(DERIVED)] if derived else row[0]
        rows.append((_unit(units, name) + (DERIVED if derived else ""), row[1], row[2], row[3]))
    return tuple(rows)


def error_rows(section: Mapping) -> tuple:
    """(mode, role, before %, after %) of each frequency: signed, model against observation. None where it was not reached."""
    modes = {row["row_id"]: row["experimental_mode"] for row in section["declaration"]["rows"]}
    rows = []
    for row in section["result"]["frequencies"]:
        observed = mp.number(row["experimental_hz"])
        before, after = mp.number(row["initial_model_hz"]), mp.number(row["final_model_hz"])
        rows.append((modes.get(row["row_id"], row["row_id"]), row["role"],
                     None if before is None else 100.0 * (before / observed - 1.0),
                     None if after is None else 100.0 * (after / observed - 1.0)))
    return tuple(rows)


def summary_frequency_rows(section: Mapping) -> tuple:
    """The columns of ``frequency_rows`` a reader wants first; the row name and the tracked mode stay under Diagnostics."""
    return tuple((row[1], row[2], row[3], row[4], row[5], row[6], row[7]) for row in frequency_rows(section))


def holdout_summary(section: Mapping) -> str:
    rows = [row for row in error_rows(section) if row[1] == "HOLDOUT" and row[3] is not None]
    if not rows:
        return "HOLDOUT: no values after the fit."
    worst = max(abs(row[3]) for row in rows)
    named = ", ".join(f"mode {row[0]}: {_signed_percent(row[3])}" for row in rows)
    return f"HOLDOUT (modes left out of the fit): {named}. Largest absolute error: {_signed_percent(worst).lstrip('+')}."


def reason_text(section: Mapping) -> str:
    result = section["result"]
    lines = [f"{result['refusal_code']}: {result['refusal_reason']}"] if result["refusal_code"] else []
    if result["forward_refusal_code"]:
        lines.append(f"Forward model: {result['forward_refusal_code']}")
    return "\n".join(lines + list(result["scientific_reasons"]))


def observation_rows(declaration: Mapping) -> tuple:
    return tuple((row["row_id"], str(row["experimental_mode"]), _text(row["experimental_hz"]), str(row["model_mode"]), row["role"],
                  row["family"], row["mode_source"] or DASH, str(len(row["shape"])), "Usable: SYNTHETIC, frozen")
                 for row in declaration["rows"])


def registration_text(declaration: Mapping) -> str:
    seen = declaration["observation_set"]
    count = len(seen.get("points", seen.get("items", ())))
    what = "registered coordinates" if seen["kind"] == "COORDINATE" else "matrix DOFs"
    return (f"Registration {seen['registration_id']}: {count} {what}, stated by this synthetic test. "
            f"FIT and HOLDOUT are frozen before the run. MAC checks mode identity only and is not fitted.")


def parameter_rows(section: Mapping) -> tuple:
    result, declaration = section["result"], section["declaration"]
    known, units = section["known_values"], section["units"]
    sd = (result["uncertainty"] or {}).get("statistical_sd") or {}
    start = result["initial_parameters"] or {item["name"]: item["start"] for item in declaration["parameters"]}
    found = result["final_parameters"] or {}
    rows = []
    for name in (item["name"] for item in declaration["parameters"]):
        linear = name in ("u", "r")
        spread = f"{mp.number(sd[name]):.3g} ({'absolute' if linear else 'ln'})" if sd.get(name) is not None else DASH
        rows.append((name, _text(start.get(name)), _text(found.get(name)), _text(known.get(name)), units.get(name, DASH), spread,
                     ROLE_LIMIT["linear" if linear else "log"]))
    before, after = result["initial_stiffness"] or {}, result["final_stiffness"] or {}
    if "D12" in known:
        rows.append(("D12" + DERIVED, _text(before.get("D12")), _text(after.get("D12")), _text(known["D12"]), units.get("D12", DASH),
                     "not propagated", ROLE_LIMIT["derived"]))
    return tuple(rows)


def frequency_rows(section: Mapping) -> tuple:
    result = section["result"]
    frequencies = {row["row_id"]: row for row in result["frequencies"]}
    identity = {row["row_id"]: row for row in result["mode_identity"]}
    rows = []
    for row in section["declaration"]["rows"]:
        measured = mp.number(row["experimental_hz"])
        found, check = frequencies.get(row["row_id"]), identity.get(row["row_id"])
        before = None if found is None else mp.number(found["initial_model_hz"])
        after = None if found is None else mp.number(found["final_model_hz"])
        shape = "Not reached" if check is None else (
            f"Mode {check['initial_model_mode']} → {check['final_model_mode']}; MAC {_text(check['final_experimental_mac'])}")
        rows.append((row["row_id"], str(row["experimental_mode"]), row["role"], _text(measured), _text(before), _text(after),
                     _percent(None if before is None else before / measured - 1.0),
                     _percent(None if after is None else after / measured - 1.0), shape))
    return tuple(rows)


def iteration_rows(section: Mapping) -> tuple:
    return tuple((str(row["iteration"]), _text(row["mu"]), _text(row["objective_before"]), _text(row["trial_objective"]),
                  _text(row["accepted"]), row["note"]) for row in section["result"]["iterations"])


def identifiability_rows(section: Mapping) -> tuple:
    block = section["result"]["identifiability"]
    if block is None:
        return (("Rank and observability", "Not reached"),)
    rows = [("Status", block["status"]), ("Rank", f"{block['rank']} of {len(block['parameter_ids'])}"),
            ("Parameters", ", ".join(block["parameter_ids"])), ("Condition number", _text(block["condition_number"])),
            ("Singular values", ", ".join(_text(value) for value in block["singular_values"]))]
    rows += [(f"Projection q {name}", _text(value)) for name, value in block["projection_q"].items()]
    return tuple(rows)


def holdout_rows(section: Mapping) -> tuple:
    return tuple((row["term_id"], row["family"], _text(row["sigma_ln"]), _text(row["initial_log_ratio"]), _text(row["final_log_ratio"]),
                  _text(row["final_whitened"])) for row in section["result"]["holdout_residuals"])


def family_rows(section: Mapping) -> tuple:
    def estimate(values) -> str:
        return ", ".join(f"{name} {_text(value)}" for name, value in values.items()) if values else DASH

    return tuple((row["family"], row["status"], estimate(row["estimate"]), "; ".join(row["reasons"]) or DASH)
                 for row in section["result"]["leave_one_family_out"])


def convergence_rows(section: Mapping) -> tuple:
    result = section["result"]
    return (("Objective at the start", _text(result["initial_objective"])), ("Objective at the end", _text(result["final_objective"])),
            ("Iterations", str(len(result["iterations"]))), ("Forward solves", str(result["solves"])),
            ("Largest eigen residual seen", _text(result["max_eigen_residual_seen"])),
            ("Largest orthonormality error seen", _text(result["max_orthonormality_error_seen"])),
            ("Analytic against tracked sensitivities", _text(result["max_analytic_sensitivity_difference"])),
            ("Mode order changes", "; ".join(f"{left} and {right}" for left, right in result["order_changes"]) or "none"),
            ("Package statement", result["package_validation_status"]))


def uncertainty_rows(section: Mapping) -> tuple:
    block = section["result"]["uncertainty"]
    if block is None:
        return (("Uncertainty", "Not reached"),)
    rows = [("Residual pattern test", block["pattern_status"]), ("Birge adjustment", block["birge_status"])]
    rows += [("Available", item) for item in block["available_components"]]
    rows += [(f"Range {name}", f"{_text(low)} to {_text(high)}") for name, (low, high) in block["robustness_range"].items()]
    if block["robustness_range"]:
        rows.append(("Meaning of the ranges", block["robustness_note"]))
    return tuple(rows + [("Missing", item) for item in block["missing_components"]])


def conditional_rows(section: Mapping) -> tuple:
    values = section["result"]["conditional_effective_constants"]
    if not values:
        return ()
    return (("Meaning", CONDITIONAL_NOTE),) + tuple((name, _text(value)) for name, value in values.items())


CONDITIONAL_NOTE = "Of this model at this thickness; not ply properties, not accepted constants"
PARAMETER_HEADERS = ("Parameter", "Start", "Found (diagnostic)", "Known synthetic value", "Unit", "Statistical SD", "Interpretation limit")
FREQUENCY_HEADERS = ("Row", "Mode", "Role", "Synthetic observation, Hz", "Before fit, Hz", "After fit, Hz", "Error before",
                     "Error after", "Tracked mode, MAC (identity only)")
OBSERVATION_HEADERS = ("Row", "Mode", "Frequency, Hz", "Frozen model mode", "Role", "Family", "Source", "Shape values", "Status")
ITERATION_HEADERS = ("Iteration", "Damping", "Objective before", "Trial objective", "Accepted", "Note")
HOLDOUT_HEADERS = ("Term", "Family", "Sigma (ln)", "ln ratio before", "ln ratio after", "Whitened after")
FAMILY_HEADERS = ("Left out", "Status", "Estimate", "Reasons")
PREFLIGHT_HEADERS = ("Resource", "This run", "Limit", "State")
SUMMARY_PARAMETER_HEADERS = ("Parameter", "Start", "Calculated", "Known synthetic")
# Two-line headers keep the seven columns inside a 900-pixel window; no column is narrower than its text (D2).
SUMMARY_FREQUENCY_HEADERS = ("Mode", "Role", "Observed\n(Hz)", "Before fit\n(Hz)", "After fit\n(Hz)", "Error\nbefore", "Error\nafter")


# ---------------------------------------------------------------------------------------------- the two plots


def _figure(width: int, height: int, scale: float) -> Figure:
    """A figure of exactly this many logical pixels at this scale: text keeps its size, and sharpness follows the scale."""
    figure = Figure(figsize=(width / BASE_DPI, height / BASE_DPI), dpi=BASE_DPI * scale, layout="constrained", facecolor="#ffffff")
    return figure


def _png(figure: Figure) -> bytes:
    FigureCanvasAgg(figure)
    out = io.BytesIO()
    figure.savefig(out, format="png", dpi=figure.dpi)
    return out.getvalue()


def _style(axis, title: str, xlabel: str, ylabel: str) -> None:
    axis.set_title(title, fontsize=12, color=_INK, loc="left", fontweight="bold")
    axis.set_xlabel(xlabel, fontsize=11, color=_MUTED)
    axis.set_ylabel(ylabel, fontsize=11, color=_MUTED)
    axis.tick_params(labelsize=10, colors=_MUTED)
    axis.grid(True, axis="y", color=_GRID, linewidth=0.8)
    axis.set_axisbelow(True)
    for side in ("top", "right"):
        axis.spines[side].set_visible(False)


OBJECTIVE_TITLE = "Objective convergence (log scale)"
ERROR_TITLE = "Frequency error before and after the fit"


def objective_points(section: Mapping) -> tuple:
    """The objective at each accepted step and at the end; empty when it cannot be drawn on a log scale."""
    result = section["result"]
    points = [mp.number(row["objective_before"]) for row in result["iterations"] if row["accepted"]]
    if result["final_objective"] is not None:
        points.append(mp.number(result["final_objective"]))
    return tuple(points) if len(points) >= 2 and all(value > 0.0 for value in points) else ()


def objective_plot(section: Mapping, width: int = 1000, height: int = 480, scale: float = 1.0) -> Optional[bytes]:
    figure = objective_figure(section, width, height, scale)
    return None if figure is None else _png(figure)


def objective_figure(section: Mapping, width: int = 1000, height: int = 480, scale: float = 1.0) -> Optional[Figure]:
    points = objective_points(section)
    if not points:
        return None
    figure = _figure(width, height, scale)
    axis = figure.add_subplot(111)
    steps = range(len(points))
    axis.semilogy(steps, points, color=_FIRST, linewidth=2.0, marker="o", markersize=8)
    axis.xaxis.get_major_locator().set_params(integer=True)
    axis.margins(x=0.08, y=0.18)
    _style(axis, OBJECTIVE_TITLE, "Accepted step", "Objective")
    axis.grid(True, axis="x", color=_GRID, linewidth=0.8)
    for step, value, place in ((0, points[0], (10, 6)), (len(points) - 1, points[-1], (-10, -16))):  # off the falling line
        axis.annotate(f"{value:.4g}", (step, value), xytext=place, textcoords="offset points", fontsize=10, color=_INK,
                      ha="left" if step == 0 else "right")
    return figure


def _error_axis(axis, rows, column: int, title: str, labels: bool) -> None:
    from matplotlib.ticker import ScalarFormatter

    places = np.arange(len(rows))
    values = np.array([np.nan if row[column] is None else row[column] for row in rows], dtype=float)
    for index, row in enumerate(rows):
        if row[1] == "HOLDOUT":
            axis.axvspan(index - 0.5, index + 0.5, color=_HOLDOUT_BAND, zorder=0, linewidth=0)
    fit = np.array([row[1] != "HOLDOUT" for row in rows])
    axis.bar(places[fit], values[fit], width=0.62, color=_FIRST, zorder=2)
    axis.bar(places[~fit], values[~fit], width=0.62, color=_SECOND, hatch="//", edgecolor="#ffffff", linewidth=0, zorder=2)
    axis.axhline(0.0, color=_INK, linewidth=1.2, zorder=3)
    finite = values[np.isfinite(values)]
    reach = float(np.max(np.abs(finite))) if finite.size else 0.0
    if reach > 0.0:
        axis.set_ylim(-1.5 * reach, 1.5 * reach)  # the same reach both ways, so a sign reads at a glance
    formatter = ScalarFormatter(useMathText=True)
    formatter.set_powerlimits((-2, 3))
    axis.yaxis.set_major_formatter(formatter)
    axis.yaxis.get_offset_text().set_fontsize(10)
    _style(axis, title, "", "Error, %")
    if labels:
        for place, value in zip(places, values):
            if np.isfinite(value):
                axis.annotate(f"{value:+.3g}", (place, value), xytext=(0, 4 if value >= 0.0 else -4), textcoords="offset points",
                              ha="center", va="bottom" if value >= 0.0 else "top", fontsize=9, color=_INK, zorder=4)
    axis.set_xlim(-0.5, len(rows) - 0.5)
    axis.set_xticks(places, [str(row[0]) for row in rows])


def error_plot(section: Mapping, width: int = 1000, height: int = 620, scale: float = 1.0) -> Optional[bytes]:
    figure = error_figure(section, width, height, scale)
    return None if figure is None else _png(figure)


def error_figure(section: Mapping, width: int = 1000, height: int = 620, scale: float = 1.0) -> Optional[Figure]:
    """Signed frequency error before and after the fit, each on its own scale: a residual after the fit is far smaller than
    before it, and on one shared scale it could not be seen at all. Each panel states its own scale on its axis."""
    from matplotlib.patches import Patch

    rows = error_rows(section)
    if not rows:
        return None
    figure = _figure(width, height, scale)
    first, second = figure.subplots(2, 1, sharex=False)
    labels = width / len(rows) >= 68  # a label stays on when the bars leave room for it
    _error_axis(first, rows, 2, "Before the fit", labels)
    _error_axis(second, rows, 3, "After the fit (own scale)", labels)
    second.set_xlabel("Mode number", fontsize=11, color=_MUTED)
    figure.legend(handles=[Patch(color=_FIRST, label="FIT: used in the fit"),
                           Patch(facecolor=_SECOND, hatch="//", edgecolor="#ffffff", label="HOLDOUT: left out of the fit")],
                  loc="outside upper right", ncols=2, fontsize=10, frameon=False)
    return figure


__all__ = ["BUILT_IN", "RITZ", "SELECTED", "STAGE_A", "FormProblem", "build_request", "default_form", "execute_study",
           "preflight", "real_data_gate", "real_data_rows"]

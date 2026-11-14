"""ABM-SANDWICH-SP13-1: a first, constrained two-parameter engineering trial for the SP-13 sandwich panel.

What it does, offline and read-only:

- identifies the experimental file by content against the recorded series (the 28 October 2026 ROTATED PolyMAX set is the
  target; the September frozen dataset and every other recorded series are named and refused);
- identifies the loaded Abaqus input by content against the accepted SP-13 forward model, reads the face material's
  ``*Elastic, type=ENGINEERING CONSTANTS`` record with the forward builder's own locator and reads the eigenvalue table
  of the ``.dat`` beside it;
- takes the response of the FE frequencies to the face-sheet E (E1 = E2) and G12 from the accepted CARBON-5A +/-5 % states
  only: the pinned repository records and the validated shape packs, each FE mode followed FE-to-FE through all four
  states by the strict branch tracker. A mode whose branch is not resolved has no sensitivity; nothing is guessed;
- fits ln f = ln f0 + S_E ln(E / E0) + S_G12 ln(G12 / G0) to the measured frequencies under a correspondence the user
  states (experimental record -> FE mode), bounded to the +/-5 % interval the sensitivities were computed over.

What it is not: no Abaqus, no FE solve, no homogeneous-plate surrogate, no MAC, no pairing by frequency or shape, no core
or adhesive parameter, no material property and no calibration. The CARBON-5F core sensitivities are not read here. A
result is an exploratory input candidate for a manual Abaqus check under an UNVERIFIED mode correspondence.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import io
import math
from pathlib import Path
from typing import Callable, Mapping, Optional, Sequence

import numpy as np
from scipy.optimize import lsq_linear

from domain.experiment_fixture import (FixtureManifestError, FixtureSourceMismatchError, FixtureSourceUnavailableError,
                                       load_experiment_fixture_manifest)
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from services import archived_sensitivity_evidence as ase
from services.archived_baseline import record_hash
from services.branch_tracker import BranchTrackingRefusal, FEModalState, TrackingInputError, track_branches
from services.fe_shape_pack import ShapePackError, load_shape_pack, load_shape_pack_record
from services.forward_builder import (ForwardBuildError, load_bound_forward_model, locate_engineering_constants,
                                      split_inp_lines)
from services.research_frequency_tuning import TuningRefused, read_dat_frequencies

REPO_ROOT = Path(__file__).resolve().parents[2]

SPECIMEN = "SP13"
SPECIMEN_TEXT = "SP-13"
FORWARD_MANIFEST = "docs/auto_id/forward_models/SP13.physical.forward.json"
SHAPE_PACK_RECORDS = "docs/auto_id/fe_shapes"
SOURCE_PROVENANCE = "docs/experimental/new_exp_20261029/SOURCE_PROVENANCE.csv"
TARGET_SERIES = "NEXP29/SP-13/S261028-ROTATED"
TARGET_STATUS_PREFIX = "NEW_WORKING_SOURCE"
ARCHIVE_STORE = "carbon-project-archive"
PARAMETERS = ("E_in_plane_mpa", "G12_mpa")
PARAMETER_TEXT = {"E_in_plane_mpa": "E (E1 = E2)", "G12_mpa": "G12"}
RCOND = 1.0e-3  # the rank rule used throughout the project (SPEC section 10): singular values below rcond * largest
BOUND_TOLERANCE = 1.0e-12
ABAQUS_FIELD_CHARS = 20  # an Abaqus floating-point data item may use at most 20 characters
CONSTANT_NAMES = ("E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23")  # the ENGINEERING CONSTANTS order

LABEL = ("EXPLORATORY SANDWICH TRIAL — UNVERIFIED MODE CORRESPONDENCE — NOT A MATERIAL PROPERTY — NOT VALIDATED IN "
         "ABAQUS")
SCOPE = ("Two unknowns only: the effective face-sheet modulus E (E1 = E2) and G12. The core, the ties, the geometry, the "
         "densities, the Poisson ratios, E3, G13 and G23 stay at the values of the FE input.")
CORRESPONDENCE_WARNING = ("UNVERIFIED MODE CORRESPONDENCE: which FE mode each measured record is compared with is the "
                          "user's hypothesis. No physical registration applies to this series, no MAC is computed and "
                          "nothing is paired by frequency or by shape here.")
LIMITATIONS = (
    "Local response only: central differences over the accepted CARBON-5A +/-5 % states about E 52 000 / G12 4 500 MPa. "
    "Outside that interval the response is not described and nothing is extrapolated into a value.",
    "Valid only for this exact FE model (mesh, geometry, thicknesses, core, ties, mass, boundary conditions).",
    "A frequency difference is not a parameter change: with the core, the ties and the mass fixed, a face-sheet value that "
    "reduces the difference may compensate a model-form error (D-074 / D-075).",
    "D-077 NO_GLOBAL_PARAMETER_VALUE and M8 GATE NOT_MET are unchanged: no value here is a material property or a "
    "calibration, and production Auto-ID stays blocked.",
    "The September frozen dataset, the October ROTATED dataset and the other panels are different measurements; the "
    "historical synthetic-twin results are regression evidence, not values fitted to this file.",
)

FIT, HOLDOUT, EXCLUDED = "FIT", "HOLDOUT", "EXCLUDED"
ROLES = (FIT, HOLDOUT, EXCLUDED)

# experimental file
TARGET, OTHER_SERIES, NOT_RECORDED = "TARGET_SERIES", "OTHER_RECORDED_SERIES", "NOT_A_RECORDED_SERIES"
# sensitivity evidence
VERIFIED, MISSING, INCOMPATIBLE = ("FACE_SENSITIVITIES_VERIFIED", "FACE_SENSITIVITY_EVIDENCE_MISSING",
                                   "FACE_SENSITIVITY_EVIDENCE_INCOMPATIBLE")
# trial outcome
CANDIDATE = "NUMERICAL_CANDIDATE_WITHIN_VERIFIED_RANGE"
AT_LIMIT = "TRIAL_POINT_AT_VERIFIED_RANGE_LIMIT"
RANK_DEFICIENT = "NOT_IDENTIFIABLE_RANK_DEFICIENT"
REFUSED = "REFUSED"
NUMERICAL = (CANDIDATE, AT_LIMIT)
STATUS_TEXT = {
    CANDIDATE: "The bounded fit ends inside the +/-5 % interval of the verified sensitivities: a numerical candidate "
               "under the stated correspondence.",
    AT_LIMIT: "UNSUPPORTED EXTRAPOLATION: the measured frequencies ask for a change beyond the +/-5 % interval of the "
              "verified sensitivities. The values shown are the limit of that interval: a next trial point for a manual "
              "Abaqus run, NOT a fitted value.",
    RANK_DEFICIENT: "No value: the FIT records cannot separate E and G12 (rank below two parameters).",
    REFUSED: "No value: the request is not valid.",
}


class TrialCancelled(Exception):
    """The reading was cancelled; nothing of it is kept."""


def _check(cancel) -> None:
    if cancel is not None and cancel.is_set():
        raise TrialCancelled()


def _short(digest: object) -> str:
    return f"{str(digest)[:12]}…"


def full(value: float) -> str:
    """The shortest text that reads back as exactly this number."""
    return repr(float(value))


# ============================================================================================ experimental identity

@dataclass(frozen=True)
class ExperimentalIdentity:
    status: str
    series: str
    text: str

    @property
    def accepted(self) -> bool:
        return self.status == TARGET


def classify_experimental(sha256: str, size: int, *, repo_root: Path = REPO_ROOT) -> ExperimentalIdentity:
    """Which recorded measurement this content is. Only the SHA-256 decides; a file name never does."""
    sha256 = str(sha256).lower()
    try:
        with open(Path(repo_root) / SOURCE_PROVENANCE, newline="", encoding="utf-8") as stream:
            rows = [row for row in csv.DictReader(stream) if row.get("sha256", "").lower() == sha256]
    except OSError as error:
        return ExperimentalIdentity(NOT_RECORDED, "", f"The series record {SOURCE_PROVENANCE} is unavailable: {error}")
    for row in rows:
        described = (f"{row['specimen_id']}, series {row['series_id']} (session {row['session']}, acquired "
                     f"{row['acquired_psv_header']}): {row['source_status']}")
        if (row["series_id"] == TARGET_SERIES and row["source_status"].startswith(TARGET_STATUS_PREFIX)
                and int(row["size_bytes"]) == int(size)):
            return ExperimentalIdentity(TARGET, row["series_id"], described)
        return ExperimentalIdentity(OTHER_SERIES, row["series_id"],
                                    f"{described}. This trial is defined for {TARGET_SERIES} only.")
    try:
        fixtures = load_experiment_fixture_manifest(Path(repo_root) / ase.FIXTURE_MANIFEST).fixtures
    except (OSError, ValueError, KeyError):
        fixtures = ()
    for fixture in fixtures:
        if fixture.experimental_source.sha256 == sha256:
            return ExperimentalIdentity(
                OTHER_SERIES, fixture.fixture_id,
                f"the frozen dataset of the accepted fixture {fixture.fixture_id} ({fixture.experimental_source.file_name}, "
                f"experiment {fixture.experiment_id}). It keeps its own accepted records and is not refitted here; this "
                f"trial is defined for {TARGET_SERIES} only.")
    return ExperimentalIdentity(NOT_RECORDED, "", f"SHA-256 {_short(sha256)} is not a recorded measurement series; the "
                                f"panel cannot be established from a file name. This trial is defined for {TARGET_SERIES} "
                                "only.")


# ============================================================================================ the loaded FE model

@dataclass(frozen=True)
class FaceMaterial:
    name: str
    constants: Mapping[str, float]  # the nine Engineering Constants as read
    tokens: tuple  # the nine values as written, in record order
    row_lengths: tuple  # values on each data line
    material_line: int  # 1-based line numbers in the INP
    elastic_line: int
    data_lines: tuple


@dataclass(frozen=True)
class FeModel:
    inp_path: str
    sha256: str
    size: int
    accepted: bool  # the content is the accepted source input and its face record is the accepted baseline
    forward_model_id: str
    checks: tuple
    reasons: tuple
    material: Optional[FaceMaterial] = None  # set only when the face record was located in this file
    dat_path: Optional[str] = None
    dat_rows: tuple = ()  # (mode, Hz) of the .dat beside the INP, as printed


def _face_material(lines: list, name: str) -> FaceMaterial:
    record = locate_engineering_constants(lines, name)
    rows = [[token.strip() for token in lines[index].rstrip("\r\n").split(",")] for index in record.data_lines]
    tokens = tuple(rows[row][column] for row, column in record.positions)
    lengths = tuple(sum(1 for r, _c in record.positions if r == row) for row in range(len(rows)))
    values = {name_: float(getattr(record.values, name_)) for name_ in CONSTANT_NAMES}
    return FaceMaterial(record.material_name, values, tokens, tuple(n for n in lengths if n),
                        record.material_line + 1, record.elastic_line + 1,
                        tuple(index + 1 for index in record.data_lines))


def read_fe_model(inp_path, *, repo_root: Path = REPO_ROOT, cancel=None) -> FeModel:
    """Identify the INP by content against the accepted SP-13 forward model and read its face-material record.

    Never writes. A file that is not the accepted input is described and not used for a calculation."""
    path = Path(inp_path)
    checks, reasons = [], []
    try:
        identity = ase.fresh_content_identity(path, cancel)
    except ase.SensitivityCheckCancelled as error:
        raise TrialCancelled() from error
    except ase.AcceptedReferenceRefusal as error:
        return FeModel(str(path), "", 0, False, "", (), (str(error),))
    try:
        bound = load_bound_forward_model(Path(repo_root) / FORWARD_MANIFEST, Path(repo_root))
        jobs = ase._load_json(Path(repo_root), ase.ACCEPTED_FORWARD_JOBS)
        baseline_job = ase._candidate(jobs, ase.BASELINE_CANDIDATE).get("jobs", {}).get(SPECIMEN, {})
    except (OSError, ValueError, KeyError) as error:
        return FeModel(str(path), identity["sha256"], identity["size"], False, "", (),
                       (f"the accepted forward-model records are unavailable: {error}",))
    manifest = bound.manifest
    reference = manifest.model_input
    dat = path.with_suffix(".dat")
    dat_rows: tuple = ()
    if dat.is_file():
        try:
            dat_rows = tuple(read_dat_frequencies(dat))
        except (OSError, TuningRefused):
            dat_rows = ()
    common = dict(inp_path=str(path), sha256=identity["sha256"], size=identity["size"],
                  forward_model_id=manifest.forward_model_id, dat_path=str(dat) if dat_rows else None, dat_rows=dat_rows)
    if (identity["sha256"], identity["size"]) != (reference.sha256, reference.size_bytes):
        reasons.append(f"the INP SHA-256 {_short(identity['sha256'])} ({identity['size']} bytes) is not the accepted "
                       f"{SPECIMEN_TEXT} source input {reference.file_name} ({_short(reference.sha256)}, "
                       f"{reference.size_bytes} bytes). The face sensitivities belong to that FE model only.")
        return FeModel(accepted=False, checks=(), reasons=tuple(reasons), **common)
    checks.append(f"INP SHA-256 {_short(identity['sha256'])} = accepted source input {reference.file_name} of "
                  f"{manifest.forward_model_id}")
    _check(cancel)
    try:
        material = _face_material(split_inp_lines(path.read_bytes()), bound.material_name)
    except (OSError, ForwardBuildError) as error:
        reasons.append(f"the face material record could not be read: {error}")
        return FeModel(accepted=False, checks=tuple(checks), reasons=tuple(reasons), **common)
    _check(cancel)
    expected = {name: float(getattr(manifest.source_engineering_constants, name)) for name in CONSTANT_NAMES}
    if material.constants != expected:
        reasons.append(f"the *Elastic record of {material.name} is not the accepted source record "
                       + ", ".join(f"{name} {expected[name]:g}" for name in CONSTANT_NAMES) + ".")
    else:
        checks.append(f"face material {material.name}: *Elastic, type=ENGINEERING CONSTANTS at INP line "
                      f"{material.elastic_line}, nine values in the accepted order; E1 = E2 = {expected['E1']:g}, "
                      f"G12 = {expected['G12']:g} MPa as in the forward-model manifest")
    targets = manifest.parameterisation.parameter_targets
    if dict(targets) != {"E_in_plane_mpa": ("E1", "E2"), "G12_mpa": ("G12",)}:
        reasons.append("the forward model's parameterisation is not E_in_plane -> E1, E2 and G12 -> G12.")
    else:
        checks.append(f"parameter definitions ({manifest.parameterisation.parameterisation_id}): E_in_plane sets E1 and "
                      "E2 of this record, G12 sets G12; the other six constants are fixed")
    changed = tuple(int(n) for n in baseline_job.get("changed_lines_1based", ()))
    if changed != material.data_lines:
        reasons.append(f"the accepted baseline job changed INP lines {list(changed)}, not the data lines "
                       f"{list(material.data_lines)} of this record.")
    else:
        checks.append(f"the accepted CARBON-4C baseline job {_short(baseline_job.get('generated_inp_sha256'))} differs "
                      f"from this INP only in the data lines {', '.join(map(str, changed))} of this record, rendered at "
                      "the same values")
    return FeModel(accepted=not reasons, checks=tuple(checks), reasons=tuple(reasons), material=material, **common)


# ============================================================================================ face sensitivities

@dataclass(frozen=True)
class ModeSensitivity:
    fe_mode: int
    baseline_hz: float
    resolved: bool
    s_e: Optional[float] = None
    s_g12: Optional[float] = None
    one_sided: Mapping[str, float] = field(default_factory=dict)  # direction -> slope from the baseline to that state
    tracked: Mapping[str, tuple] = field(default_factory=dict)  # direction -> (FE mode, FE-to-FE MAC, Hz)
    reason: str = ""

    @property
    def asymmetry(self) -> Optional[float]:
        """Largest difference between the two one-sided slopes of a parameter: a curvature indicator."""
        if not self.resolved:
            return None
        return max(abs(self.one_sided[f"{p}+"] - self.one_sided[f"{p}-"]) for p in PARAMETERS)


@dataclass(frozen=True)
class FaceSensitivityEvidence:
    status: str
    reasons: tuple
    checks: tuple
    baseline: Mapping[str, float] = field(default_factory=dict)  # parameter -> baseline value (MPa)
    bounds: Mapping[str, tuple] = field(default_factory=dict)  # parameter -> (lowest, highest) of the archived states
    baseline_modes: tuple = ()  # (FE mode, Hz) of the accepted baseline record
    modes: tuple = ()  # ModeSensitivity of every baseline mode (only when the packs were verified)
    source: str = ""

    @property
    def usable(self) -> bool:
        return self.status == VERIFIED

    def mode(self, fe_mode: int) -> Optional[ModeSensitivity]:
        return next((item for item in self.modes if item.fe_mode == int(fe_mode)), None)


def _state(pack) -> FEModalState:
    shapes = np.asarray(pack.displacements, dtype=np.float64).reshape(len(pack.mode_numbers), -1)
    return FEModalState(pack.record.job_name, pack.record.fe_geometry_sha256, pack.record.node_set_sha256,
                        tuple(pack.mode_numbers), tuple(pack.frequencies_hz), shapes)


def sensitivities_from_states(baseline: FEModalState, states: Mapping[str, FEModalState],
                              factors: Mapping[str, tuple], policy=STRICT_IDENTIFICATION_PAIRING) -> tuple:
    """Central log-sensitivities of every baseline mode, each followed FE-to-FE into the four perturbed states.

    ``factors``: direction -> (parameter, factor), for example ``"G12_mpa+": ("G12_mpa", 1.05)``. A mode that is lost,
    ambiguous or claimed together with another mode in any state is not resolved and gets no sensitivity."""
    directions = [f"{parameter}{sign}" for parameter in PARAMETERS for sign in "+-"]
    if set(directions) != set(states) or set(directions) != set(factors):
        raise TrackingInputError("exactly the four states E+, E-, G12+ and G12- are required.")
    tracked: dict = {mode: {} for mode in baseline.mode_numbers}
    problems: dict = {mode: [] for mode in baseline.mode_numbers}
    for direction in directions:
        claimed: dict = {}
        for mode in baseline.mode_numbers:
            try:
                branch = track_branches(policy, baseline, states[direction], {f"FE{mode}": mode}).branches[0]
            except BranchTrackingRefusal as refusal:
                problems[mode].append(f"{direction}: {refusal.kind.value}")
                continue
            tracked[mode][direction] = (int(branch.candidate_mode), float(branch.mac), float(branch.candidate_hz))
            claimed.setdefault(int(branch.candidate_mode), []).append(mode)
        for candidate, owners in claimed.items():
            if len(owners) > 1:
                for mode in owners:
                    problems[mode].append(f"{direction}: FE {candidate} is claimed by baseline modes "
                                          f"{', '.join(map(str, owners))}")
    output = []
    for mode, hz in zip(baseline.mode_numbers, baseline.frequencies_hz):
        if problems[mode]:
            output.append(ModeSensitivity(int(mode), float(hz), False, tracked=dict(tracked[mode]),
                                          reason="branch not resolved in all four states (" + "; ".join(problems[mode])
                                                 + ")"))
            continue
        central, one_sided = {}, {}
        for parameter in PARAMETERS:
            plus, minus = f"{parameter}+", f"{parameter}-"
            step = math.log(factors[plus][1]) - math.log(factors[minus][1])
            central[parameter] = (math.log(tracked[mode][plus][2]) - math.log(tracked[mode][minus][2])) / step
            for direction in (plus, minus):
                one_sided[direction] = (math.log(tracked[mode][direction][2] / hz) / math.log(factors[direction][1]))
        output.append(ModeSensitivity(int(mode), float(hz), True, central["E_in_plane_mpa"], central["G12_mpa"],
                                      one_sided, dict(tracked[mode])))
    return tuple(output)


def archive_roots(folder=None, environ=None) -> dict:
    """Where the shape packs are: a folder the user named (the archive root, or its ``fe_shapes`` folder), otherwise
    the configured ``AUTO_ID_FIXTURE_ROOT_CARBON_PROJECT_ARCHIVE``. Every pack is verified by content wherever it is."""
    from domain.experiment_fixture import fixture_roots_from_environment

    if folder:
        folder = Path(folder)
        return {ARCHIVE_STORE: folder.parent if folder.name.lower() == "fe_shapes" else folder}
    roots = fixture_roots_from_environment(environ)
    return {ARCHIVE_STORE: roots[ARCHIVE_STORE]} if ARCHIVE_STORE in roots else {}


def load_face_sensitivities(roots: Optional[Mapping[str, Path]] = None, *, repo_root: Path = REPO_ROOT,
                            cancel=None) -> FaceSensitivityEvidence:
    """The accepted CARBON-5A face-sheet E / G12 response of the SP-13 FE model, verified end to end, or the reason
    it cannot be used. ``roots`` maps the store ``carbon-project-archive`` to its folder (see ``archive_roots``)."""
    repo_root = Path(repo_root)
    checks: list = []
    spec = next(item for item in ase.SPECIMENS if item.specimen == SPECIMEN)
    try:
        fixture = load_experiment_fixture_manifest(repo_root / ase.FIXTURE_MANIFEST).fixture(spec.fixture_id)
        baseline = ase._bound_baseline(spec, fixture, repo_root)
        perturbations = ase._perturbations(spec, baseline, ase._load_json(repo_root, ase.ACCEPTED_FORWARD_JOBS))
        bound = load_bound_forward_model(repo_root / FORWARD_MANIFEST, repo_root)
        if (ase._load_json(repo_root, baseline.forward_model_path).get("forward_model_id")
                != bound.manifest.forward_model_id):
            raise ase.AcceptedReferenceRefusal("the archived baseline is not bound to the SP-13 forward model.")
        names = {"BASELINE": baseline.generated_inp_sha256, **{key: sha for key, (_v, sha) in perturbations.items()}}
        records = {}
        for key, sha in names.items():
            record = load_shape_pack_record(repo_root / SHAPE_PACK_RECORDS / f"{SPECIMEN}_{sha[:16]}.shape-pack.json")
            if (record.generated_inp_sha256, record.specimen) != (sha, SPECIMEN):
                raise ase.AcceptedReferenceRefusal(f"shape-pack record {record.job_name} is not the accepted {key} job.")
            if record.fe_geometry_sha256 != baseline.fe_geometry_sha256:
                raise ase.AcceptedReferenceRefusal(f"shape-pack record {record.job_name} has another FE geometry.")
            records[key] = record
        base_record = records["BASELINE"]
        if any((r.node_set_sha256, r.mode_numbers) != (base_record.node_set_sha256, base_record.mode_numbers)
               for r in records.values()):
            raise ase.AcceptedReferenceRefusal("the five shape-pack records are not on one node set and mode range.")
        if base_record.odb.sha256 != baseline.odb.sha256 or [
                (m.number, m.frequency_hz) for m in baseline.fe_modes] != list(zip(base_record.mode_numbers,
                                                                                    base_record.frequencies_hz)):
            raise ase.AcceptedReferenceRefusal("the baseline shape-pack record is not the archived baseline's ODB and "
                                               "frequencies.")
        document = ase._load_json(repo_root, spec.reevaluation_path)
        if record_hash(document) != spec.reevaluation_hash:
            raise ase.AcceptedReferenceRefusal(f"{spec.reevaluation_path} differs from its pinned content.")
        physical = (document.get("results") or {}).get("PHYSICAL") or {}
    except (OSError, ValueError, KeyError, FixtureManifestError) as error:  # refusals and record errors are ValueErrors
        return FaceSensitivityEvidence(INCOMPATIBLE, (f"the accepted CARBON-5A records are not usable: {error}",),
                                       tuple(checks))
    values = {parameter: float(baseline.candidate[parameter]) for parameter in PARAMETERS}
    bounds = {parameter: (perturbations[f"{parameter}-"][0], perturbations[f"{parameter}+"][0]) for parameter in PARAMETERS}
    factors = {key: (ase.PERTURBATIONS[key][1], ase.PERTURBATIONS[key][2]) for key in perturbations}
    checks.append(f"accepted records pinned and mutually consistent: baseline {baseline.job_name} (E "
                  f"{values['E_in_plane_mpa']:g}, G12 {values['G12_mpa']:g} MPa), forward jobs "
                  f"{_short(ase.ACCEPTED_FORWARD_JOBS_HASH)}, CARBON-5A states "
                  + ", ".join(f"{ase.PERTURBATIONS[key][0].split()[-1]} {records[key].job_name}" for key in perturbations))
    checks.append(f"one FE geometry {_short(baseline.fe_geometry_sha256)} and one node set "
                  f"({base_record.node_set_count} nodes: {base_record.node_set_definition}) in all five states; FE "
                  f"modes {base_record.mode_numbers[0]}-{base_record.mode_numbers[-1]}")
    common = dict(baseline=values, bounds=bounds,
                  baseline_modes=tuple(zip(base_record.mode_numbers, base_record.frequencies_hz)),
                  source=f"{SHAPE_PACK_RECORDS}/{SPECIMEN}_*.shape-pack.json; store {ARCHIVE_STORE}: fe_shapes/*.npz")
    try:
        packs = {}
        for key, record in records.items():
            _check(cancel)
            packs[key] = load_shape_pack(record, roots or {})
    except FixtureSourceUnavailableError as error:
        return FaceSensitivityEvidence(MISSING, (
            f"the validated FE shape packs of the CARBON-5A states are not available: {error}",
            "Without them the FE-to-FE branch of each mode cannot be verified, so no sensitivity is issued and no "
            "response model is assumed. Name the folder of the carbon project archive (it holds fe_shapes).",),
            tuple(checks), **common)
    except (FixtureSourceMismatchError, ShapePackError, OSError, ValueError) as error:
        return FaceSensitivityEvidence(INCOMPATIBLE, (f"a shape pack does not match its pinned record: {error}",),
                                       tuple(checks), **common)
    checks.append("five shape packs verified against their records (file SHA-256, content hash, node set, modes and "
                  "frequencies)")
    _check(cancel)
    try:
        modes = sensitivities_from_states(_state(packs["BASELINE"]),
                                          {key: _state(packs[key]) for key in perturbations}, factors)
    except TrackingInputError as error:
        return FaceSensitivityEvidence(INCOMPATIBLE, (f"the FE states cannot be tracked: {error}",), tuple(checks),
                                       **common)
    resolved = [m for m in modes if m.resolved]
    checks.append(f"branch identity by FE-to-FE tracking (MAC >= {STRICT_IDENTIFICATION_PAIRING.tracking_minimum_mac:g}, "
                  f"unique) in E+, E-, G12+, G12-: resolved for FE "
                  + (", ".join(str(m.fe_mode) for m in resolved) or "no mode")
                  + ("" if len(resolved) == len(modes) else "; NOT resolved for FE "
                     + ", ".join(str(m.fe_mode) for m in modes if not m.resolved)))
    # the recomputed values must be the ones of the accepted strict freeze where that record holds them
    by_mode = {m.fe_mode: m for m in modes}
    for pair in physical.get("strict_pairs") or ():
        recorded = (physical.get("sensitivities") or {}).get(pair["row_id"])
        mine = by_mode.get(int(pair["fe_mode"]))
        if recorded is None:
            continue
        if (mine is None or not mine.resolved or not math.isclose(mine.s_e, recorded["S_E"], rel_tol=1e-9, abs_tol=1e-12)
                or not math.isclose(mine.s_g12, recorded["S_G12"], rel_tol=1e-9, abs_tol=1e-12)):
            return FaceSensitivityEvidence(INCOMPATIBLE, (
                f"the sensitivity of FE {pair['fe_mode']} does not reproduce the accepted strict freeze "
                f"({spec.reevaluation_path}, {pair['row_id']}).",), tuple(checks), **common)
        checks.append(f"FE {pair['fe_mode']}: S_E {mine.s_e:.6f}, S_G12 {mine.s_g12:.6f} reproduce the accepted strict "
                      f"freeze row {pair['row_id']}")
    if len(resolved) < 2:
        return FaceSensitivityEvidence(INCOMPATIBLE, ("fewer than two FE modes have a resolved branch.",), tuple(checks),
                                       modes=modes, **common)
    return FaceSensitivityEvidence(VERIFIED, (), tuple(checks), modes=modes, **common)


def model_binding(model: Optional[FeModel], evidence: Optional[FaceSensitivityEvidence]) -> tuple:
    """(usable, checks, reasons): whether the verified sensitivities belong to the loaded FE model."""
    if model is None or evidence is None:
        return False, (), ("the FE model and the sensitivity evidence were not read.",)
    checks, reasons = [], list(model.reasons)
    if not evidence.usable:
        reasons += list(evidence.reasons)
    if model.accepted and evidence.baseline:
        material = model.material.constants
        same = (material["E1"] == material["E2"] == evidence.baseline["E_in_plane_mpa"]
                and material["G12"] == evidence.baseline["G12_mpa"])
        if same:
            checks.append(f"baseline of the sensitivities = the loaded INP's own values: E1 = E2 = {material['E1']:g}, "
                          f"G12 = {material['G12']:g} MPa")
        else:
            reasons.append("the loaded INP's E1, E2, G12 are not the baseline the sensitivities were computed about.")
    if model.accepted and evidence.baseline_modes and model.dat_rows:
        printed = dict(model.dat_rows)
        differing = [mode for mode, hz in evidence.baseline_modes
                     if mode not in printed or not math.isclose(printed[mode], hz, rel_tol=1e-4)]
        if differing:
            reasons.append(f"the .dat beside the INP does not hold the accepted baseline frequencies of FE "
                           f"{', '.join(map(str, differing))} (to its printed precision).")
        else:
            checks.append(f"the .dat beside the INP prints the accepted baseline frequencies of all "
                          f"{len(evidence.baseline_modes)} elastic FE modes (to its five printed digits)")
    return bool(model.accepted and evidence.usable and len(reasons) == 0), tuple(checks), tuple(reasons)


def fe_frequencies(model: Optional[FeModel], evidence: Optional[FaceSensitivityEvidence]) -> tuple:
    """((FE mode, Hz), source text): the accepted baseline record for the accepted model, otherwise the .dat as printed."""
    if model is not None and model.accepted and evidence is not None and evidence.baseline_modes:
        return tuple(evidence.baseline_modes), "accepted CARBON-4C baseline record of this FE model (exact EIGFREQ)"
    if model is not None and model.dat_rows:
        return tuple(model.dat_rows), ".dat beside the INP, as printed (FE model not identified as the accepted one)"
    return (), "no FE frequencies"


# ============================================================================================ the trial

@dataclass(frozen=True)
class Hypothesis:
    key: str
    title: str
    pairs: tuple  # (experimental record, FE mode or None)

    def fe_mode(self, record: int) -> Optional[int]:
        return dict(self.pairs).get(int(record))


FREQUENCY_ORDER, DECLARED = "FREQUENCY_ORDER", "DECLARED"


def frequency_order_hypothesis(records: Sequence[tuple], fe_modes: Sequence[tuple]) -> Hypothesis:
    """The k-th measured record by frequency against the k-th elastic FE mode by frequency: a rank hypothesis, stated
    as such. It is not a pairing by closeness: no record is moved to a nearer FE mode."""
    ordered_fe = [mode for mode, _hz in sorted(fe_modes, key=lambda item: item[1])]
    ordered = sorted(records, key=lambda item: item[1])
    pairs = tuple((int(record), ordered_fe[index] if index < len(ordered_fe) else None)
                  for index, (record, _hz) in enumerate(ordered))
    return Hypothesis(FREQUENCY_ORDER, "Frequency rank: the k-th record against the k-th elastic FE mode",
                      tuple(sorted(pairs)))


def declared_hypothesis(records: Sequence[tuple], declared: Mapping[int, int]) -> Hypothesis:
    """The user's own table record -> FE mode. A record that is not named has no FE mode (it can only be EXCLUDED)."""
    known = {int(record) for record, _hz in records}
    unknown = sorted(set(declared) - known)
    if unknown:
        raise ValueError(f"Declared correspondence: record {unknown[0]} is not in the measured set.")
    return Hypothesis(DECLARED, "Declared by the user (record:FE mode)",
                      tuple((int(record), declared.get(int(record))) for record, _hz in sorted(records)))


@dataclass(frozen=True)
class TrialRow:
    record: int
    role: str
    fe_mode: Optional[int]
    experimental_hz: float
    baseline_hz: Optional[float]
    predicted_hz: Optional[float]
    before: Optional[float]  # (f_FE baseline - f_exp) / f_exp
    after: Optional[float]  # (f predicted - f_exp) / f_exp
    s_e: Optional[float]
    s_g12: Optional[float]
    note: str = ""


@dataclass(frozen=True)
class Outcome:
    hypothesis: Hypothesis
    status: str
    reasons: tuple
    values: Mapping[str, float] = field(default_factory=dict)  # E1, E2, G12 in MPa, when numerical
    change: Mapping[str, float] = field(default_factory=dict)  # parameter -> value / baseline - 1
    at_limit: tuple = ()  # parameters held at a limit of the verified interval
    unconstrained_change: Mapping[str, float] = field(default_factory=dict)  # the unbounded linear solution, as changes
    rows: tuple = ()
    fit_count: int = 0
    rank: int = 0
    singular_values: tuple = ()
    condition: Optional[float] = None
    weakest_direction: Mapping[str, float] = field(default_factory=dict)
    cost: Optional[float] = None  # half the sum of squared ln(f predicted / f exp) over FIT
    rms: Mapping[str, Optional[float]] = field(default_factory=dict)  # FIT_before, FIT_after, HOLDOUT_before, HOLDOUT_after
    warnings: tuple = ()

    @property
    def numerical(self) -> bool:
        return self.status in NUMERICAL


@dataclass(frozen=True)
class TrialResult:
    selected: Outcome
    alternatives: tuple  # the other stated hypotheses, calculated the same way; none is chosen
    competing: bool
    baseline: Mapping[str, float]
    bounds: Mapping[str, tuple]
    label: str = LABEL

    @property
    def status(self) -> str:
        return self.selected.status


def _rms(values) -> Optional[float]:
    values = [v for v in values if v is not None]
    return math.sqrt(sum(v * v for v in values) / len(values)) if values else None


def _solve(evidence: FaceSensitivityEvidence, records: Sequence[tuple], roles: Mapping[int, str],
           hypothesis: Hypothesis) -> Outcome:
    problems, rows, used = [], [], {}
    for record, hz in sorted(records):
        role = roles.get(int(record), FIT)
        fe_mode = hypothesis.fe_mode(record)
        if role not in ROLES:
            problems.append(f"record {record}: unknown role {role!r}.")
            continue
        sensitivity = None if fe_mode is None else evidence.mode(fe_mode)
        note = ""
        if role != EXCLUDED:
            if fe_mode is None:
                problems.append(f"record {record} ({role}) has no FE mode in this correspondence; state one or set the "
                                "record to EXCLUDED.")
            elif sensitivity is None:
                problems.append(f"record {record}: FE {fe_mode} is not a mode of the verified FE states.")
            elif fe_mode in used:
                problems.append(f"records {used[fe_mode]} and {record} are both compared with FE {fe_mode}.")
            else:
                used[fe_mode] = record
            if role == FIT and sensitivity is not None and not sensitivity.resolved:
                problems.append(f"record {record} (FIT) is compared with FE {fe_mode}, which has no verified sensitivity: "
                                f"{sensitivity.reason}. Set the record to HOLDOUT or EXCLUDED, or state another FE mode.")
        if sensitivity is not None and not sensitivity.resolved:
            note = "no verified sensitivity: not predicted"
        rows.append([int(record), role, fe_mode, float(hz), sensitivity, note])
    if problems:
        return Outcome(hypothesis, REFUSED, tuple(problems))

    fit = [row for row in rows if row[1] == FIT]
    jacobian = np.array([[row[4].s_e, row[4].s_g12] for row in fit], dtype=float).reshape(len(fit), 2)
    residual = np.array([math.log(row[3] / row[4].baseline_hz) for row in fit], dtype=float)
    singular = np.linalg.svd(jacobian, compute_uv=False) if len(fit) else np.zeros(0)
    rank = int(np.sum(singular > RCOND * singular[0])) if len(singular) and singular[0] > 0 else 0
    vt = np.linalg.svd(jacobian)[2] if len(fit) else np.eye(2)
    weakest = {PARAMETER_TEXT[p]: float(v) for p, v in zip(PARAMETERS, vt[-1])}
    lower = np.array([math.log(evidence.bounds[p][0] / evidence.baseline[p]) for p in PARAMETERS])
    upper = np.array([math.log(evidence.bounds[p][1] / evidence.baseline[p]) for p in PARAMETERS])
    diagnostics = dict(fit_count=len(fit), rank=rank, singular_values=tuple(float(s) for s in singular),
                       condition=float(singular[0] / singular[-1]) if rank == 2 else None, weakest_direction=weakest)

    def table(x) -> tuple:
        output = []
        for record, role, fe_mode, hz, sensitivity, note in rows:
            if sensitivity is None:
                output.append(TrialRow(record, role, fe_mode, hz, None, None, None, None, None, None,
                                       "no FE mode stated"))
                continue
            before = (sensitivity.baseline_hz - hz) / hz
            if not sensitivity.resolved or x is None:
                output.append(TrialRow(record, role, fe_mode, hz, sensitivity.baseline_hz, None, before, None,
                                       sensitivity.s_e, sensitivity.s_g12, note))
                continue
            predicted = sensitivity.baseline_hz * math.exp(sensitivity.s_e * x[0] + sensitivity.s_g12 * x[1])
            output.append(TrialRow(record, role, fe_mode, hz, sensitivity.baseline_hz, predicted, before,
                                   (predicted - hz) / hz, sensitivity.s_e, sensitivity.s_g12, note))
        return tuple(output)

    def rms_of(table_rows) -> dict:
        return {f"{role}_{when}": _rms([getattr(row, when) for row in table_rows if row.role == role])
                for role in (FIT, HOLDOUT) for when in ("before", "after")}

    if rank < 2:
        shown = table(None)
        reason = (f"rank {rank} < 2 parameters at rcond {RCOND:g}: {len(fit)} FIT record(s), singular values "
                  + (", ".join(f"{s:.4g}" for s in singular) or "none")
                  + (f"; the least determined combination is {weakest}" if len(fit) else "")
                  + ". A family of (E, G12) pairs fits equally; no single pair is issued.")
        return Outcome(hypothesis, RANK_DEFICIENT, (reason,), rows=shown, rms=rms_of(shown), **diagnostics)

    free = np.linalg.lstsq(jacobian, residual, rcond=None)[0]
    inside = bool(np.all(free >= lower - BOUND_TOLERANCE) and np.all(free <= upper + BOUND_TOLERANCE))
    if inside:
        x = np.clip(free, lower, upper)
    else:
        x = np.clip(lsq_linear(jacobian, residual, bounds=(lower, upper), method="bvls").x, lower, upper)
        for index in range(2):  # a value within the numerical tolerance of a limit is that limit
            for limit in (lower[index], upper[index]):
                if abs(x[index] - limit) <= 1e-10:
                    x[index] = limit
    at_limit = tuple(p for p, value, lo, hi in zip(PARAMETERS, x, lower, upper) if not inside and value in (lo, hi))
    values = {p: evidence.baseline[p] * math.exp(v) for p, v in zip(PARAMETERS, x)}
    for parameter in at_limit:  # exactly the archived state's value, not exp(log(...)) of it
        index = PARAMETERS.index(parameter)
        values[parameter] = evidence.bounds[parameter][0 if x[index] == lower[index] else 1]
    shown = table(x)
    after = np.array([math.log(row.predicted_hz / row.experimental_hz) for row in shown if row.role == FIT])
    warnings = [CORRESPONDENCE_WARNING]
    reasons = []
    unconstrained = {p: math.exp(v) - 1.0 for p, v in zip(PARAMETERS, free)}
    if not inside:
        reasons.append("the unbounded linear solution is " + ", ".join(
            f"{PARAMETER_TEXT[p]} {unconstrained[p]:+.1%}" for p in PARAMETERS)
            + f" from the baseline, outside the verified +/-5 % interval; it is NOT a value. Held at a limit: "
            + ", ".join(PARAMETER_TEXT[p] for p in at_limit) + ".")
        warnings.append("The values are the limit of the verified interval, not a minimum of the fit. After a manual "
                        "Abaqus check at this point, new FE sensitivities about it are needed to go further.")
    if len(fit) == 2:
        warnings.append("Two FIT records for two unknowns: the fit is exact by construction and has no residual check.")
    asymmetry = max((row[4].asymmetry or 0.0) for row in fit)
    warnings.append(f"Largest difference between the two one-sided slopes among the FIT modes: {asymmetry:.4f} "
                    "(a curvature indicator of the +/-5 % response).")
    return Outcome(hypothesis, CANDIDATE if inside else AT_LIMIT, tuple(reasons),
                   values={"E1": values["E_in_plane_mpa"], "E2": values["E_in_plane_mpa"], "G12": values["G12_mpa"]},
                   change={p: values[p] / evidence.baseline[p] - 1.0 for p in PARAMETERS}, at_limit=at_limit,
                   unconstrained_change=unconstrained, rows=shown, cost=0.5 * float(after @ after), rms=rms_of(shown),
                   warnings=tuple(warnings), **diagnostics)


def calculate(evidence: FaceSensitivityEvidence, records: Sequence[tuple], roles: Mapping[int, str],
              hypotheses: Sequence[Hypothesis], selected: str) -> TrialResult:
    """The bounded trial under the correspondence the user selected, and the same calculation under every other stated
    correspondence (none is chosen). ``records``: (record, Hz) of the measured, curve-fitted set, all of them: a record
    is never dropped or renumbered; its role says how it is used."""
    if not evidence.usable:
        raise ValueError("the face sensitivities are not verified: " + " ".join(evidence.reasons))
    keys = [h.key for h in hypotheses]
    if selected not in keys or len(set(keys)) != len(keys):
        raise ValueError("select one of the stated correspondences.")
    outcomes = {h.key: _solve(evidence, records, roles, h) for h in hypotheses}
    chosen = outcomes[selected]
    others = tuple(o for key, o in outcomes.items() if key != selected and o.hypothesis.pairs != chosen.hypothesis.pairs)
    competing = any(o.numerical and (not chosen.numerical or any(
        not math.isclose(o.values[k], chosen.values[k], rel_tol=1e-9) for k in ("E1", "G12"))) for o in others)
    return TrialResult(chosen, others, competing, dict(evidence.baseline), dict(evidence.bounds))


# ============================================================================================ export

def export_unavailable(result: Optional[TrialResult], model: Optional[FeModel]) -> str:
    """Why nothing can be written for Abaqus, or ""."""
    if result is None:
        return "Export for Abaqus: calculate the exploratory candidates first."
    if not result.selected.numerical:
        return f"Export for Abaqus: not available, the result holds no numerical value ({result.status})."
    if model is None or not model.accepted or model.material is None:
        return ("Export for Abaqus: not available, the face material record of the loaded INP is not verified, so no "
                "material lines are written.")
    return ""


def abaqus_lines(material: FaceMaterial, values: Mapping[str, float]) -> tuple:
    """The face material's ``*Elastic`` record with E1, E2 and G12 replaced: the INP's own order and line layout, the
    six other constants exactly as the INP writes them."""
    tokens = list(material.tokens)
    for name in ("E1", "E2", "G12"):
        text = full(values[name])
        if len(text) > ABAQUS_FIELD_CHARS:
            raise ValueError(f"{name} = {text} needs more than {ABAQUS_FIELD_CHARS} characters.")
        tokens[CONSTANT_NAMES.index(name)] = text
    lines, start = ["*Elastic, type=ENGINEERING CONSTANTS"], 0
    for index, count in enumerate(material.row_lengths):
        row = ", ".join(tokens[start:start + count])
        lines.append(row + ("," if index == len(material.row_lengths) - 1 and count < 8 else ""))
        start += count
    return tuple(lines)


def _pct(value: Optional[float]) -> str:
    return "" if value is None else f"{100.0 * value:+.4f}"


def _hz(value: Optional[float]) -> str:
    return "" if value is None else full(value)


def export_rows(result: TrialResult, model: FeModel, evidence: FaceSensitivityEvidence, experimental: Mapping) -> list:
    """(section, item, value, unit, note) rows: everything the files hold."""
    outcome, material = result.selected, model.material
    rows = [("status", "label", result.label, "", ""),
            ("status", "outcome", outcome.status, "", STATUS_TEXT[outcome.status]),
            ("status", "correspondence", outcome.hypothesis.title, "", CORRESPONDENCE_WARNING),
            ("status", "scope", SCOPE, "", "")]
    rows += [("status", "reason", text, "", "") for text in outcome.reasons]
    rows += [("status", "warning", text, "", "") for text in outcome.warnings[1:]]
    for name in CONSTANT_NAMES:
        fitted = name in ("E1", "E2", "G12")
        value = full(outcome.values[name]) if fitted else material.tokens[CONSTANT_NAMES.index(name)]
        origin = "exploratory trial value (E1 = E2)" if name in ("E1", "E2") else (
            "exploratory trial value" if fitted else f"fixed: as written in the INP for {material.name}")
        if fitted and (("E_in_plane_mpa" if name != "G12" else "G12_mpa") in outcome.at_limit):
            origin += "; LIMIT of the verified +/-5 % interval, not a fitted value"
        rows.append(("face material", name, value, "" if name.startswith("nu") else "MPa", origin))
    for parameter in PARAMETERS:
        rows.append(("change", PARAMETER_TEXT[parameter], _pct(outcome.change[parameter]), "%",
                     f"from the INP value {full(result.baseline[parameter])} MPa; verified interval "
                     f"{full(result.bounds[parameter][0])} to {full(result.bounds[parameter][1])} MPa"))
        rows.append(("change", f"{PARAMETER_TEXT[parameter]}, unbounded linear solution",
                     _pct(outcome.unconstrained_change[parameter]), "%",
                     "diagnostic only: NOT a value when it lies outside the verified interval"))
    rows += [("abaqus", f"line {index + 1}", line, "", f"face material {material.name} only; INP line "
              f"{material.elastic_line + index}") for index, line in enumerate(abaqus_lines(material, outcome.values))]
    for row in outcome.rows:
        rows.append(("frequencies", f"EXP record {row.record}", _hz(row.experimental_hz), "Hz",
                     f"role {row.role}; FE mode {row.fe_mode if row.fe_mode is not None else 'none'}; FE baseline "
                     f"{_hz(row.baseline_hz)} Hz; predicted {_hz(row.predicted_hz)} Hz; FE vs EXP before "
                     f"{_pct(row.before)} %; predicted vs EXP {_pct(row.after)} %; S_E "
                     f"{'' if row.s_e is None else full(row.s_e)}; S_G12 {'' if row.s_g12 is None else full(row.s_g12)}"
                     + (f"; {row.note}" if row.note else "")))
    for key, value in outcome.rms.items():
        role, when = key.split("_")
        rows.append(("fit", f"{role} residual RMS {when}", _pct(value), "%", "(f - f_exp) / f_exp"))
    rows.append(("fit", "cost", "" if outcome.cost is None else full(outcome.cost), "",
                 "half the sum of ln^2(f predicted / f exp) over FIT"))
    rows.append(("fit", "rank", str(outcome.rank), "", f"of 2 parameters at rcond {RCOND:g}; {outcome.fit_count} FIT records"))
    rows.append(("fit", "singular values", ", ".join(full(s) for s in outcome.singular_values), "", ""))
    rows.append(("fit", "condition number", "" if outcome.condition is None else full(outcome.condition), "", ""))
    for other in result.alternatives:
        text = (", ".join(f"{k} {full(other.values[k])} MPa" for k in ("E1", "G12")) if other.numerical else "no value")
        rows.append(("alternative correspondence (not selected)", other.hypothesis.title, other.status, "",
                     f"{text}; FIT RMS {_pct(other.rms.get('FIT_after'))} %. " + " ".join(other.reasons)))
    if result.competing:
        rows.append(("alternative correspondence (not selected)", "competing solutions", "YES", "",
                     "Another stated correspondence gives other values; frequency agreement does not decide between "
                     "them and none is chosen."))
    rows += [("limitation", str(index + 1), text, "", "") for index, text in enumerate(LIMITATIONS)]
    rows += [("source", "experimental file", str(experimental.get("path", "")), "",
              f"SHA-256 {experimental.get('sha256', '')}; modal set {experimental.get('set_title', '')}; "
              f"{experimental.get('identity', '')}"),
             ("source", "Abaqus input", model.inp_path, "", f"SHA-256 {model.sha256}; {model.forward_model_id}"),
             ("source", "sensitivities", evidence.source, "", "accepted CARBON-5A +/-5 % face-sheet states")]
    rows += [("check", str(index + 1), text, "", "") for index, text in enumerate(model.checks + evidence.checks)]
    return rows


def export_documents(result: TrialResult, model: FeModel, evidence: FaceSensitivityEvidence,
                     experimental: Mapping) -> dict:
    """{"txt", "csv"}: the candidate for a manual Abaqus entry. Raises ValueError when nothing may be written."""
    why = export_unavailable(result, model)
    if why:
        raise ValueError(why)
    rows = export_rows(result, model, evidence, experimental)
    outcome, material = result.selected, model.material
    text = [f"{SPECIMEN_TEXT} sandwich trial: face-sheet input candidate for a manual Abaqus check", "=" * 78, result.label,
            "", f"Outcome: {outcome.status}", STATUS_TEXT[outcome.status], *outcome.reasons, "",
            f"Correspondence: {outcome.hypothesis.title}", CORRESPONDENCE_WARNING, "", SCOPE, ""]
    text += [f"Face material {material.name} (the only material these lines belong to)", "-" * 78]
    text += [f"{item:<5} {value:>22} {unit:<4} {note}" for section, item, value, unit, note in rows
             if section == "face material"]
    text += ["", "Abaqus lines", "-" * 78,
             f"Replace the data lines {', '.join(map(str, material.data_lines))} of *Elastic (INP line "
             f"{material.elastic_line}) in material {material.name} of a COPY of the INP. Change nothing else: the core "
             "material, the ties, the densities and the geometry stay as they are.", ""]
    text += list(abaqus_lines(material, outcome.values))
    text += ["", "Change from the INP values", "-" * 78]
    text += [f"{item}: {value} %  ({note})" for section, item, value, _u, note in rows if section == "change"]
    text += ["", "Frequencies (Hz) and signed differences (%)", "-" * 78,
             f"{'EXP':>4} {'role':<9} {'FE':>4} {'EXP Hz':>20} {'FE baseline Hz':>20} {'predicted Hz':>20} "
             f"{'before %':>10} {'after %':>10}  note"]
    for row in outcome.rows:
        text.append(f"{row.record:>4} {row.role:<9} {('' if row.fe_mode is None else row.fe_mode):>4} "
                    f"{_hz(row.experimental_hz):>20} {_hz(row.baseline_hz):>20} {_hz(row.predicted_hz):>20} "
                    f"{_pct(row.before):>10} {_pct(row.after):>10}  {row.note}")
    text += ["", "Fit", "-" * 78] + [f"{item}: {value} {unit}  {note}".rstrip() for section, item, value, unit, note
                                     in rows if section == "fit"]
    text += ["", "Warnings", "-" * 78] + [f"- {w}" for w in outcome.warnings]
    if result.alternatives:
        text += ["", "Other stated correspondences (calculated the same way; none is chosen)", "-" * 78]
        text += [f"- {item}: {value}. {note}" for section, item, value, _u, note in rows
                 if section.startswith("alternative")]
    text += ["", "Limitations", "-" * 78] + [f"- {t}" for t in LIMITATIONS]
    text += ["", "Sources and checks", "-" * 78]
    text += [f"{item}: {value}  ({note})" for section, item, value, _u, note in rows if section == "source"]
    text += [f"- {value}" for section, _i, value, _u, _n in rows if section == "check"]
    stream = io.StringIO()
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerow(("section", "item", "value", "unit", "note"))
    writer.writerows(rows)
    return {"txt": "\n".join(text) + "\n", "csv": stream.getvalue()}


def write_export(documents: Mapping[str, str], folder, stamp: str, *, unchanged: Optional[Callable[[], str]] = None) -> tuple:
    """Write ``sp13_face_candidate_abaqus_<stamp>.txt`` and ``.csv`` into ``folder``; never replaces a file.
    ``unchanged()`` returns a reason when a source changed since the calculation: then nothing is written."""
    changed = unchanged() if unchanged is not None else ""
    if changed:
        raise ValueError(changed)
    folder = Path(folder)
    if not folder.is_dir():
        raise OSError(f"{folder} is not a folder.")
    targets = [folder / f"sp13_face_candidate_abaqus_{stamp}.{suffix}" for suffix in ("txt", "csv")]
    existing = [path.name for path in targets if path.exists()]
    if existing:
        raise OSError(f"{', '.join(existing)} already exists in {folder}; nothing was replaced.")
    for path, suffix in zip(targets, ("txt", "csv")):
        with open(path, "x", encoding="utf-8", newline="") as stream:
            stream.write(documents[suffix])
    return tuple(targets)


__all__ = ["AT_LIMIT", "CANDIDATE", "DECLARED", "EXCLUDED", "ExperimentalIdentity", "FIT", "FREQUENCY_ORDER",
           "FaceMaterial", "FaceSensitivityEvidence", "FeModel", "HOLDOUT", "Hypothesis", "INCOMPATIBLE", "LABEL",
           "MISSING", "ModeSensitivity", "Outcome", "RANK_DEFICIENT", "REFUSED", "ROLES", "TARGET", "TrialCancelled",
           "TrialResult", "TrialRow", "VERIFIED", "abaqus_lines", "archive_roots", "calculate", "classify_experimental",
           "declared_hypothesis", "export_documents", "export_unavailable", "fe_frequencies",
           "frequency_order_hypothesis", "load_face_sensitivities", "model_binding", "read_fe_model",
           "sensitivities_from_states", "write_export"]

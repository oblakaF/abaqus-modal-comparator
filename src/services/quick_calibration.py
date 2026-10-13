"""Quick effective-property calibration: Abaqus INP + Polytec / Testlab UNV-UFF → approximate constants.

This is an engineering calibration, not the governed Auto-ID material identification (SPEC v1.1/v1.2).
It answers one question: "which multiplier of the chosen elastic constants makes *this* FE model
reproduce the measured frequencies of *this* specimen, and how well constrained is that value?"
The answer is always labelled EFFECTIVE_MODEL_CALIBRATION / NOT_A_MATERIAL_PROPERTY.

Pipeline (one specimen):

1. read the experiment with the application's reader (dataset 55/2414 curve-fitted modes, or
   dataset 58 peak-derived modes, which are marked as rougher evidence);
2. solve the unchanged INP once and pair FE and experimental modes with the application's
   comparator (geometry-only registration; rigid modes removed by shape projection); only
   pairs with MAC >= 0.80 become observation rows, which are then frozen;
3. every candidate scales the chosen constants (for example E1 and E2 of the face material)
   by a multiplier k, is solved in Abaqus, and its modes are followed by FE-to-FE MAC >= 0.90
   against the baseline (branch loss stops the run; there is no re-pairing);
4. the bounded Levenberg-Marquardt of Auto-ID (``run_bounded_lm``) fits ln k to
   r_i = ln(f_FE,i / f_EXP,i) / σ, σ = 0.3 % (the SPEC provisional Σ_setup, whitening only);
5. at the optimum a fresh central-difference Jacobian gives the sensitivities, the statistical
   sd, a scatter-scaled sd, a linearised leave-one-mode-out range and the mode spread (how far
   apart the single modes are about the value); the reported band is the largest of them.

A value is shown only when the optimiser converged in the interior of the search bounds, the
branches stayed identified, every parameter is observable and there are more rows than
parameters.  Otherwise the result is REFUSED with the reason.  A shown value carries a grade:
GOOD (band <= 5 % and every mode within 5 %), APPROXIMATE (<= 10 %), or UNRELIABLE.

Abaqus access is injected (``solve`` and ``extract`` callables) so that the service is testable;
``AbaqusRunner`` is the real implementation used by the CLI and the window.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import shlex
import subprocess
import time
from typing import Callable, Mapping, Optional, Sequence

import numpy as np

from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from modal_core import ModalDataset, ModeShape

from .branch_tracker import BranchTrackingRefusal, FEModalState, track_branches
from .forward_builder import (
    ForwardBuildError,
    _data_lines,
    _line_ending,
    _parameters,
    _tokens,
    inp_keyword,
    material_block_bounds,
    split_inp_lines,
    join_inp_lines,
)
from .identification_step import LMSettings, LMStatus, StepError, parameter_bounds, run_bounded_lm


SCHEMA = "quick-calibration/v1"
LABEL = "EFFECTIVE_MODEL_CALIBRATION"
NOT_A_MATERIAL_PROPERTY = "NOT_A_MATERIAL_PROPERTY"
SIGMA_LN = 0.003  # SPEC §7 provisional Σ_setup; whitening only, never tuned
IDENTIFICATION_MAC = STRICT_IDENTIFICATION_PAIRING.minimum_mac  # 0.80
RANK_RCOND = 1.0e-3  # SPEC §10 practical rank tolerance
TRACKING_NODE_CAP = 20000  # FE-to-FE tracking uses the scanned surface, at most this many nodes
MINIMUM_SENSITIVITY = 0.02  # |d ln f / d ln k| below this on every row: the parameter is not observable
GOOD_LIMIT = 0.05
APPROXIMATE_LIMIT = 0.10
LM_MU_INITIAL = 1.0e-3
LM_MU_DECREASE = 10.0
LM_STEP_ATTEMPTS = 3

GRADE_GOOD = "GOOD"
GRADE_APPROXIMATE = "APPROXIMATE"
GRADE_UNRELIABLE = "UNRELIABLE"
STATUS_ESTIMATE = "ESTIMATE"
STATUS_REFUSED = "REFUSED"


class QuickCalibrationError(ValueError):
    """Inputs cannot be used as given; nothing is guessed."""

    def __init__(self, message: str, candidates: Sequence[Mapping] = ()) -> None:
        super().__init__(message)
        self.candidates = list(candidates)  # orientation candidates when the registration is ambiguous


def describe_orientation(candidate: Mapping) -> str:
    """'exp X = +FE X, exp Y = -FE Y, exp Z = -FE Z' from a geometry candidate's rotation (geometry only)."""
    rotation = np.asarray(candidate.get("rotation"), dtype=float)
    axes = "XYZ"
    parts = []
    for column in range(3):
        row = int(np.argmax(np.abs(rotation[:, column])))
        sign = "+" if rotation[row, column] >= 0 else "-"
        parts.append(f"exp {axes[column]} = {sign}FE {axes[row]}")
    return ", ".join(parts) + (" (mirrored)" if candidate.get("mirrored") else "")


# ----------------------------------------------------------------------------- configuration

@dataclass(frozen=True)
class ParameterSpec:
    """One fitted multiplier k applied to ``constants`` of ``material`` (k = 1 is the INP value)."""

    name: str
    material: str
    constants: tuple[str, ...]
    lower: float = 0.5
    upper: float = 2.0

    def __post_init__(self) -> None:
        if not self.name or not self.material or not self.constants:
            raise QuickCalibrationError("a parameter needs a name, a material and at least one constant.")
        if not (0.0 < self.lower < 1.0 < self.upper):
            raise QuickCalibrationError(f"{self.name}: bounds must satisfy 0 < lower < 1 < upper (multipliers).")
        object.__setattr__(self, "constants", tuple(c.strip().upper() for c in self.constants))


@dataclass(frozen=True)
class QuickCalibrationConfig:
    model_inp: Path
    experiment: Path
    parameters: tuple[ParameterSpec, ...]
    output_dir: Path
    abaqus_command: str = "abaqus"
    cpus: int = 1
    modal_set: Optional[str] = None
    experimental_modes: Optional[tuple[int, ...]] = None  # experimental mode numbers to use (default: all)
    min_experimental_hz: Optional[float] = None  # e.g. the suspension limit
    max_experimental_hz: Optional[float] = None
    fe_last_mode: Optional[int] = None  # default: the *Frequency eigenvalue count of the INP
    coordinate_scale: Optional[float] = None  # experiment → FE length factor; None = automatic
    orientation_candidate_id: Optional[str] = None  # needed only when the geometry is ambiguous
    solve_budget: int = 16  # LM evaluations (baseline and finite differences included)
    timeout_minutes: float = 120.0

    def __post_init__(self) -> None:
        if not self.parameters:
            raise QuickCalibrationError("at least one parameter is required.")
        names = [p.name for p in self.parameters]
        if len(set(names)) != len(names):
            raise QuickCalibrationError("parameter names must be unique.")
        seen = set()
        for p in self.parameters:
            for c in p.constants:
                key = (p.material.lower(), c)
                if key in seen:
                    raise QuickCalibrationError(f"{p.material}/{c} is assigned to two parameters.")
                seen.add(key)
        if self.cpus < 1 or self.solve_budget < 1 + 2 * len(self.parameters):
            raise QuickCalibrationError("cpus must be ≥ 1 and the solve budget ≥ 1 + 2·(number of parameters).")


def config_from_dict(data: Mapping, base_dir: Path = Path(".")) -> QuickCalibrationConfig:
    """Build a config from JSON-like data; relative paths are resolved against ``base_dir``."""

    known = {"model_inp", "experiment", "parameters", "output_dir", "abaqus_command", "cpus", "modal_set",
             "experimental_modes", "min_experimental_hz", "max_experimental_hz", "fe_last_mode", "coordinate_scale",
             "orientation_candidate_id", "solve_budget", "timeout_minutes", "comment"}
    unknown = set(data) - known
    if unknown:
        raise QuickCalibrationError(f"unknown configuration keys: {sorted(unknown)}")
    for key in ("model_inp", "experiment", "parameters", "output_dir"):
        if key not in data:
            raise QuickCalibrationError(f"missing configuration key {key!r}.")

    def path(value) -> Path:
        candidate = Path(str(value))
        return candidate if candidate.is_absolute() else (Path(base_dir) / candidate)

    parameters = []
    for item in data["parameters"]:
        constants = item.get("constants")
        if isinstance(constants, str):
            constants = [c for c in constants.replace(";", ",").split(",") if c.strip()]
        parameters.append(ParameterSpec(str(item.get("name", "")), str(item.get("material", "")),
                                        tuple(constants or ()), float(item.get("lower", 0.5)),
                                        float(item.get("upper", 2.0))))
    modes = data.get("experimental_modes")
    return QuickCalibrationConfig(
        model_inp=path(data["model_inp"]), experiment=path(data["experiment"]), parameters=tuple(parameters),
        output_dir=path(data["output_dir"]), abaqus_command=str(data.get("abaqus_command") or "abaqus"),
        cpus=int(data.get("cpus", 1)), modal_set=data.get("modal_set"),
        experimental_modes=None if modes is None else tuple(int(m) for m in modes),
        min_experimental_hz=_optional_float(data.get("min_experimental_hz")),
        max_experimental_hz=_optional_float(data.get("max_experimental_hz")),
        fe_last_mode=None if data.get("fe_last_mode") is None else int(data["fe_last_mode"]),
        coordinate_scale=_optional_float(data.get("coordinate_scale")),
        orientation_candidate_id=data.get("orientation_candidate_id"),
        solve_budget=int(data.get("solve_budget", 16)), timeout_minutes=float(data.get("timeout_minutes", 120.0)))


def load_config(path: Path) -> QuickCalibrationConfig:
    path = Path(path)
    with open(path, encoding="utf-8") as handle:
        return config_from_dict(json.load(handle), path.parent)


def config_template() -> dict:
    return {
        "comment": "Quick effective-property calibration. Paths are relative to this file. "
                   "Multipliers k scale the listed constants of the material (k = 1: INP value).",
        "model_inp": "SP13.inp",
        "experiment": "SP13_polymax.unv",
        "output_dir": "quick_calibration_SP13",
        "abaqus_command": "abaqus",
        "cpus": 4,
        "parameters": [{"name": "E_face", "material": "CFRP_Face", "constants": ["E1", "E2"],
                        "lower": 0.5, "upper": 2.0}],
        "min_experimental_hz": None,
        "max_experimental_hz": None,
        "experimental_modes": None,
        "modal_set": None,
        "fe_last_mode": None,
        "coordinate_scale": None,
        "orientation_candidate_id": None,
        "solve_budget": 16,
        "timeout_minutes": 120,
    }


def _optional_float(value) -> Optional[float]:
    return None if value is None else float(value)


# ----------------------------------------------------------------------------- INP *Elastic editing

ELASTIC_LAYOUTS = {
    "ISOTROPIC": ("E", "NU"),
    "ENGINEERING CONSTANTS": ("E1", "E2", "E3", "NU12", "NU13", "NU23", "G12", "G13", "G23"),
    "LAMINA": ("E1", "E2", "NU12", "G12", "G13", "G23"),
}


@dataclass(frozen=True)
class ElasticRecord:
    material: str
    elastic_type: str
    names: tuple[str, ...]
    values: tuple[float, ...]
    data_lines: tuple[int, ...]
    positions: tuple[tuple[int, int], ...]  # (data row, token column) of each value in ``names`` order

    def value(self, name: str) -> float:
        return self.values[self.names.index(name)]


def locate_elastic(lines: list[str], material: str) -> ElasticRecord:
    """The unique, temperature-independent *Elastic record of ``material`` (ISOTROPIC, ENGINEERING CONSTANTS or
    LAMINA).  Refuses anything it cannot rewrite safely instead of guessing."""

    try:
        start, end = material_block_bounds(lines, material)
    except ForwardBuildError as error:
        includes = any(inp_keyword(line) == "include" for line in lines)
        hint = " The INP uses *Include; give the file that contains the *Material block." if includes else ""
        raise QuickCalibrationError(f"{error}{hint}") from None
    elastic = [i for i in range(start + 1, end) if inp_keyword(lines[i]) == "elastic"]
    if len(elastic) != 1:
        raise QuickCalibrationError(f"material {material!r} must have exactly one *Elastic; found {len(elastic)}.")
    options = _parameters(lines[elastic[0]])
    if "dependencies" in options:
        raise QuickCalibrationError(f"material {material!r}: field-variable dependent *Elastic is not supported.")
    elastic_type = " ".join(options.get("type", "ISOTROPIC").upper().split())
    if elastic_type not in ELASTIC_LAYOUTS:
        raise QuickCalibrationError(f"material {material!r}: *Elastic type={elastic_type} is not supported "
                                    f"(supported: {', '.join(ELASTIC_LAYOUTS)}).")
    names = ELASTIC_LAYOUTS[elastic_type]
    data = _data_lines(lines, elastic[0])
    rows = [_tokens(lines[i]) for i in data]
    for row in rows:
        body = row[:-1] if row and row[-1] == "" else row
        if "" in body:
            raise QuickCalibrationError(f"material {material!r}: an empty field inside the *Elastic data "
                                        "(Abaqus reads it as 0); write every value explicitly.")
    positions = tuple((r, c) for r, row in enumerate(rows) for c, token in enumerate(row) if token)
    if len(positions) != len(names):
        raise QuickCalibrationError(
            f"material {material!r}: *Elastic type={elastic_type} must be one record of {len(names)} values "
            f"(no temperature column, no temperature dependence); found {len(positions)}.")
    try:
        values = tuple(float(rows[r][c].replace("D", "E").replace("d", "e")) for r, c in positions)
    except ValueError as error:
        raise QuickCalibrationError(f"material {material!r}: unreadable *Elastic value: {error}") from None
    return ElasticRecord(material, elastic_type, names, values, tuple(data), positions)


def _rewrite(lines: list[str], record: ElasticRecord, new_values: Mapping[str, float]) -> None:
    rows = [_tokens(lines[index]) for index in record.data_lines]
    for name, (row, column) in zip(record.names, record.positions):
        if name in new_values:
            rows[row][column] = repr(float(new_values[name]))
    for row, index in enumerate(record.data_lines):
        line = lines[index]
        values = [token for token in rows[row] if token]
        trailing_comma = "," if line.rstrip().endswith(",") else ""
        lines[index] = ", ".join(values) + trailing_comma + _line_ending(line)


class InpModel:
    """The reference INP and the located *Elastic records of every fitted parameter."""

    def __init__(self, source: bytes, parameters: Sequence[ParameterSpec]) -> None:
        self.source = source
        self.parameters = tuple(parameters)
        lines = split_inp_lines(source)
        self.records: dict[str, ElasticRecord] = {}
        for p in self.parameters:
            key = p.material.lower()
            if key not in self.records:
                self.records[key] = locate_elastic(lines, p.material)
            record = self.records[key]
            missing = [c for c in p.constants if c not in record.names]
            if missing:
                raise QuickCalibrationError(
                    f"{p.name}: material {p.material!r} (*Elastic type={record.elastic_type}) has no constant(s) "
                    f"{missing}; available: {list(record.names)}.")
            for c in p.constants:
                if record.value(c) <= 0:
                    raise QuickCalibrationError(f"{p.name}: {p.material}/{c} = {record.value(c)} is not positive.")
        self.eigenvalue_count = _eigenvalue_count(lines)

    def constants_for(self, multipliers: Mapping[str, float]) -> dict[str, dict[str, float]]:
        """material → {constant: value} for the given multipliers (only the fitted constants)."""
        out: dict[str, dict[str, float]] = {}
        for p in self.parameters:
            record = self.records[p.material.lower()]
            for c in p.constants:
                out.setdefault(p.material, {})[c] = record.value(c) * float(multipliers[p.name])
        return out

    def render(self, multipliers: Mapping[str, float], header: Sequence[str] = ()) -> bytes:
        lines = split_inp_lines(self.source)
        if all(float(multipliers[p.name]) == 1.0 for p in self.parameters) and not header:
            return self.source
        for material, values in self.constants_for(multipliers).items():
            _rewrite(lines, self.records[material.lower()], values)
        if header:
            ending = _line_ending(lines[0]) or "\n"
            lines = [f"** {text}{ending}" for text in header] + lines
        rendered = join_inp_lines(lines)
        check = split_inp_lines(rendered)
        for material, values in self.constants_for(multipliers).items():
            record = locate_elastic(check, material)
            for name, value in values.items():
                if not math.isclose(record.value(name), value, rel_tol=1e-12):
                    raise QuickCalibrationError(f"{material}/{name} was not written correctly.")
        return rendered


def _eigenvalue_count(lines: list[str]) -> Optional[int]:
    frequency = [i for i, line in enumerate(lines) if inp_keyword(line) == "frequency"]
    if len(frequency) != 1:
        raise QuickCalibrationError(f"the INP must contain exactly one *Frequency step; found {len(frequency)}.")
    data = _data_lines(lines, frequency[0])
    if not data:
        return None
    token = _tokens(lines[data[0]])[0]
    try:
        return int(token) if token else None
    except ValueError:
        return None


# ----------------------------------------------------------------------------- Abaqus access

SolveFunction = Callable[[Path, Path, str], Path]  # (inp in its job dir, job dir, job name) → ODB
ExtractFunction = Callable[[Path, Path, int], ModalDataset]  # (ODB, output dir, last mode) → FE modes


class AbaqusRunner:
    """Real Abaqus: one solve per job directory, then the application's ODB extraction script."""

    COMPLETED = "THE ANALYSIS HAS COMPLETED SUCCESSFULLY"

    def __init__(self, abaqus_command: str = "abaqus", cpus: int = 1, timeout_minutes: float = 120.0) -> None:
        self.abaqus_command = (abaqus_command or "abaqus").strip()
        self.cpus = int(cpus)
        self.timeout_seconds = int(timeout_minutes * 60)

    def _command(self, arguments: Sequence[str]):
        if os.name == "nt":
            executable = self.abaqus_command
            if " " in executable and not executable.startswith('"'):
                executable = f'"{executable}"'
            inner = " ".join([executable] + [subprocess.list2cmdline([a]) for a in arguments])
            return f'cmd.exe /d /s /c "{inner}"'  # a string: Popen must not re-quote it (audit V11)
        return shlex.split(self.abaqus_command) + list(arguments)

    def _run(self, command, directory: Path, log_path: Path) -> int:
        options = {"cwd": str(directory), "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            options["start_new_session"] = True
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            log.write(f"{command}\n")
            log.flush()
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, **options)
            try:
                return process.wait(timeout=self.timeout_seconds)
            except subprocess.TimeoutExpired:
                self._kill_tree(process)
                raise QuickCalibrationError(f"Abaqus exceeded {self.timeout_seconds // 60} min; the process tree "
                                            f"was stopped. Log: {log_path}") from None

    @staticmethod
    def _kill_tree(process: subprocess.Popen) -> None:
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=60)
            else:
                os.killpg(process.pid, 9)
        except Exception:  # noqa: BLE001 - best effort; the caller reports the timeout either way
            pass
        try:
            process.wait(timeout=30)
        except Exception:  # noqa: BLE001
            pass

    def solve(self, inp_path: Path, job_dir: Path, job_name: str) -> Path:
        arguments = [f"job={job_name}", f"input={Path(inp_path).name}", f"cpus={self.cpus}", "interactive",
                     "ask_delete=OFF"]
        code = self._run(self._command(arguments), job_dir, job_dir / "solve.log")
        sta, odb = job_dir / f"{job_name}.sta", job_dir / f"{job_name}.odb"
        sta_text = sta.read_text(encoding="utf-8", errors="replace") if sta.exists() else ""
        if code != 0 or self.COMPLETED not in sta_text or not odb.is_file():
            raise QuickCalibrationError(
                f"Abaqus job {job_name} did not complete (exit code {code}; see {job_dir / 'solve.log'} and "
                f"{job_name}.msg/.dat).")
        return odb

    def extract(self, odb_path: Path, output_dir: Path, last_mode: int) -> ModalDataset:
        import abaqus_bridge

        manifest = abaqus_bridge.run_abaqus_extraction(odb_path, output_dir, abaqus_command=self.abaqus_command,
                                                       start_mode=1, end_mode=int(last_mode),
                                                       timeout_seconds=self.timeout_seconds)
        return abaqus_bridge.load_extracted_odb(manifest)


# ----------------------------------------------------------------------------- FE states

@dataclass
class FEState:
    job_name: str
    dataset: Optional[ModalDataset]  # kept for the baseline only (the comparator needs every node)
    tracking: FEModalState


def _node_key(node_id) -> str:
    return str(node_id)


def _tracking_state(job_name: str, dataset: ModalDataset, node_order: Optional[Sequence[str]] = None) -> FEModalState:
    modes = dataset.sorted_modes()
    reference = modes[0]
    keys = [_node_key(n) for n in reference.node_ids]
    order = list(node_order) if node_order is not None else keys
    index = {k: i for i, k in enumerate(keys)}
    if not set(order) <= set(index):
        raise QuickCalibrationError(f"{job_name}: the FE node set differs from the baseline model.")
    rows = np.array([index[k] for k in order])
    shapes = []
    for mode in modes:
        if [_node_key(n) for n in mode.node_ids] != keys:
            raise QuickCalibrationError(f"{job_name}: modes are not given on one common node list.")
        shapes.append(np.real(np.asarray(mode.vectors))[rows].reshape(-1))
    node_hash = hashlib.sha256("\n".join(order).encode("utf-8")).hexdigest()
    geometry = np.round(np.asarray(reference.coordinates, dtype=float)[rows], 6)
    geometry_hash = hashlib.sha256(geometry.tobytes()).hexdigest()
    return FEModalState(job_name, geometry_hash, node_hash, tuple(int(m.number) for m in modes),
                        tuple(float(m.frequency_hz) for m in modes), np.vstack(shapes))


def _save_state(path: Path, dataset: ModalDataset, nodes: Optional[Sequence[str]] = None) -> None:
    """Cache the extracted modes; a candidate keeps only the tracking nodes (``nodes``), the baseline all."""
    modes = dataset.sorted_modes()
    keys = [_node_key(n) for n in modes[0].node_ids]
    if nodes is None:
        rows = np.arange(len(keys))
    else:
        index = {k: i for i, k in enumerate(keys)}
        rows = np.array([index[k] for k in nodes])
    np.savez_compressed(path, numbers=np.array([m.number for m in modes]),
                        frequencies=np.array([m.frequency_hz for m in modes]),
                        node_ids=np.array(keys)[rows],
                        coordinates=np.asarray(modes[0].coordinates)[rows],
                        vectors=np.stack([np.real(np.asarray(m.vectors))[rows] for m in modes]))


def _load_state(path: Path) -> ModalDataset:
    with np.load(path, allow_pickle=False) as data:
        node_ids = data["node_ids"].astype(object)
        modes = [ModeShape(int(n), float(f), node_ids, data["coordinates"], v)
                 for n, f, v in zip(data["numbers"], data["frequencies"], data["vectors"])]
    return ModalDataset("Abaqus ODB (cached)", path, modes)


# ----------------------------------------------------------------------------- experiment and baseline pairing

@dataclass(frozen=True)
class ObservationRow:
    row_id: str
    experimental_mode: int
    experimental_hz: float
    baseline_fe_mode: int
    baseline_fe_hz: float
    mac: float
    peak_derived: bool


def load_experiment(config: QuickCalibrationConfig) -> ModalDataset:
    import universal_reader  # resolved at call time: the application's installed (hardened, cached) reader

    if not Path(config.experiment).is_file():
        raise QuickCalibrationError(f"experiment file not found: {config.experiment}")
    dataset = universal_reader.load_universal_modal_file(Path(config.experiment), modal_set=config.modal_set)
    keep = []
    for mode in dataset.sorted_modes():
        if config.experimental_modes is not None and mode.number not in config.experimental_modes:
            continue
        if config.min_experimental_hz is not None and mode.frequency_hz < config.min_experimental_hz:
            continue
        if config.max_experimental_hz is not None and mode.frequency_hz > config.max_experimental_hz:
            continue
        keep.append(mode)
    if not keep:
        raise QuickCalibrationError("no experimental modes remain after the mode / frequency selection.")
    return ModalDataset(dataset.source_name, dataset.source_path, keep, dict(dataset.metadata), list(dataset.history))


def _is_peak_derived(mode: ModeShape) -> bool:
    return "peak" in str(mode.metadata.get("mode_source", "")).lower()


def pair_baseline(fe: ModalDataset, experiment: ModalDataset, config: QuickCalibrationConfig):
    """The application's comparison (geometry-only registration), then the strict MAC ≥ 0.80 row filter."""

    import modal_core
    from reviewed_core import GeometryOrientationAmbiguousError

    selection = None if config.orientation_candidate_id is None else {"candidate_id": config.orientation_candidate_id}
    try:
        comparison = modal_core.compare_modal_datasets(fe, experiment, coordinate_scale_override=config.coordinate_scale,
                                                       orientation_selection=selection)
    except GeometryOrientationAmbiguousError as error:
        options = "; ".join(f"{c.get('candidate_id')} [{describe_orientation(c)}]" for c in error.ambiguous_candidates)
        raise QuickCalibrationError(
            "The scan-to-model orientation is ambiguous from geometry alone (a symmetric panel). Confirm it from "
            "the photograph / corner marker (never from MAC) and set 'orientation_candidate_id' to one of: "
            + options, error.ambiguous_candidates) from None
    experimental = {m.number: m for m in experiment.sorted_modes()}
    rows, excluded = [], []
    for pair in sorted(comparison.pairs, key=lambda p: p.experimental_frequency_hz):
        info = {"experimental_mode": pair.experimental_mode, "fe_mode": pair.abaqus_mode,
                "experimental_hz": pair.experimental_frequency_hz, "fe_hz": pair.abaqus_frequency_hz,
                "mac": pair.mac}
        if pair.mac is None or not math.isfinite(pair.mac) or pair.mac < IDENTIFICATION_MAC:
            excluded.append(dict(info, reason=f"MAC < {IDENTIFICATION_MAC:g} (diagnostic only, not fitted)"))
            continue
        rows.append(ObservationRow(f"X{pair.experimental_mode}", int(pair.experimental_mode),
                                   float(pair.experimental_frequency_hz), int(pair.abaqus_mode),
                                   float(pair.abaqus_frequency_hz), float(pair.mac),
                                   _is_peak_derived(experimental[pair.experimental_mode])))
    unpaired = sorted(set(experimental) - {p.experimental_mode for p in comparison.pairs})
    geometry = comparison.geometry
    mapped = np.asarray(comparison.abaqus.sorted_modes()[0].node_ids)[np.asarray(geometry.experimental_to_abaqus)]
    registration = {
        "mapped_fe_node_count": int(len(set(_node_key(n) for n in mapped))),
        "orientation_source": comparison.metadata.get("orientation_source"),
        "coordinate_scale": float(geometry.coordinate_scale),
        "normalized_rms_distance": float(geometry.normalized_rms_distance),
        "matched_fraction": float(geometry.matched_fraction),
        "reflection": bool(np.linalg.det(geometry.rotation) < 0),
    }
    return tuple(rows), excluded, unpaired, list(comparison.warnings), registration, [_node_key(n) for n in mapped]


def tracking_nodes(fe: ModalDataset, mapped_ids: Sequence[str], cap: int = TRACKING_NODE_CAP) -> list[str]:
    """FE nodes of the scanned surface: the plane through the nodes the experimental points map to.

    Branch tracking compares FE shapes on these nodes only (all three components), which keeps every candidate
    state small even for a model with an explicit lattice core.  Deterministic; capped by a uniform stride.
    """
    reference = fe.sorted_modes()[0]
    keys = [_node_key(n) for n in reference.node_ids]
    coordinates = np.asarray(reference.coordinates, dtype=float)
    index = {k: i for i, k in enumerate(keys)}
    mapped = np.array(sorted({index[k] for k in mapped_ids if k in index}))
    if len(mapped) < 3:
        return keys[:: max(1, len(keys) // cap + 1)]
    points = coordinates[mapped]
    centre = points.mean(axis=0)
    _, singular, vt = np.linalg.svd(points - centre, full_matrices=False)
    normal = vt[-1]
    extent = float(np.linalg.norm(coordinates.max(axis=0) - coordinates.min(axis=0))) or 1.0
    residual = np.abs((points - centre) @ normal)
    tolerance = max(3.0 * float(residual.max()), 1.0e-6 * extent)
    on_surface = np.flatnonzero(np.abs((coordinates - centre) @ normal) <= tolerance)
    chosen = np.union1d(on_surface, mapped) if len(on_surface) >= len(mapped) else mapped
    if len(chosen) > cap:
        stride = int(math.ceil(len(chosen) / cap))
        chosen = np.union1d(chosen[::stride], mapped)
    return [keys[i] for i in chosen]


# ----------------------------------------------------------------------------- the calibration

ProgressFunction = Callable[[str], None]


@dataclass
class _Evaluation:
    multipliers: dict[str, float]
    job_name: str
    fe_hz: dict[str, float]
    tracking_mac: dict[str, float]
    residuals: list[float]


class QuickCalibration:
    def __init__(self, config: QuickCalibrationConfig, solve: SolveFunction, extract: ExtractFunction,
                 progress: Optional[ProgressFunction] = None) -> None:
        self.config = config
        self.solve, self.extract = solve, extract
        self.progress = progress or (lambda message: None)
        source = Path(config.model_inp)
        if not source.is_file():
            raise QuickCalibrationError(f"model INP not found: {source}")
        self.model = InpModel(source.read_bytes(), config.parameters)
        self.last_mode = config.fe_last_mode or self.model.eigenvalue_count or 60
        self.work = Path(config.output_dir) / "work"
        self.work.mkdir(parents=True, exist_ok=True)
        self.abaqus_solves = 0
        self.evaluations: list[_Evaluation] = []
        self._cache: dict[str, FEState] = {}
        self.rows: tuple[ObservationRow, ...] = ()
        self.reference: Optional[FEModalState] = None

    # -- FE states (content-addressed jobs; a rerun reuses finished jobs)
    def fe_state(self, multipliers: Mapping[str, float]) -> FEState:
        content = self.model.render(multipliers)
        digest = hashlib.sha256(content).hexdigest()
        job_name = f"qc_{digest[:12]}"
        if job_name in self._cache:
            return self._cache[job_name]
        job_dir = self.work / job_name
        cached = job_dir / "fe_modes.npz"
        if cached.is_file():
            dataset = _load_state(cached)
            self.progress(f"{job_name}: reused finished job ({self._describe(multipliers)})")
        else:
            job_dir.mkdir(parents=True, exist_ok=True)
            inp = job_dir / f"{job_name}.inp"
            inp.write_bytes(content)
            self.progress(f"{job_name}: Abaqus solve ({self._describe(multipliers)})")
            started = time.monotonic()
            odb = self.solve(inp, job_dir, job_name)
            self.abaqus_solves += 1
            self.progress(f"{job_name}: extracting modes 1-{self.last_mode} "
                          f"(solve took {time.monotonic() - started:.0f} s)")
            dataset = self.extract(Path(odb), job_dir / "extraction", self.last_mode)
            _save_state(cached, dataset, None if self.reference is None else self._node_order)
            dataset = _load_state(cached)
        order = None if self.reference is None else self._node_order
        state = FEState(job_name, dataset if self.reference is None else None,
                        _tracking_state(job_name, dataset, order))
        if self.reference is not None:  # candidates keep only their small tracking state in memory
            self._cache[job_name] = state
        return state

    def _describe(self, multipliers: Mapping[str, float]) -> str:
        return ", ".join(f"{name} k={value:.4f}" for name, value in multipliers.items())

    # -- one LM evaluation: candidate → tracked rows → whitened residuals
    def evaluate(self, multipliers: Mapping[str, float]) -> np.ndarray:
        multipliers = {k: float(v) for k, v in multipliers.items()}
        state = self.fe_state(multipliers)
        tracked = track_branches(STRICT_IDENTIFICATION_PAIRING, self.reference, state.tracking,
                                 {row.row_id: row.baseline_fe_mode for row in self.rows})
        fe_hz = {b.row_id: b.candidate_hz for b in tracked.branches}
        macs = {b.row_id: b.mac for b in tracked.branches}
        residuals = [math.log(fe_hz[row.row_id] / row.experimental_hz) / SIGMA_LN for row in self.rows]
        self.evaluations.append(_Evaluation(multipliers, state.job_name, fe_hz, macs, residuals))
        return np.asarray(residuals)

    def run(self) -> dict:
        config = self.config
        names = [p.name for p in config.parameters]
        start = {name: 1.0 for name in names}
        self.progress("reading the experiment")
        experiment = load_experiment(config)
        peak_modes = [m.number for m in experiment.sorted_modes() if _is_peak_derived(m)]

        baseline = self.fe_state(start)
        self.progress("pairing the baseline FE modes with the experiment")
        rows, excluded, unpaired, warnings, registration, mapped = pair_baseline(baseline.dataset, experiment, config)
        self.rows = rows
        self._node_order = tracking_nodes(baseline.dataset, mapped)
        registration["tracking_node_count"] = len(self._node_order)
        self.reference = _tracking_state(baseline.job_name, baseline.dataset, self._node_order)
        baseline.dataset = None
        base = {"schema": SCHEMA, "label": LABEL, "claim": NOT_A_MATERIAL_PROPERTY,
                "inputs": self._inputs(), "registration": registration, "comparison_warnings": warnings,
                "excluded_pairs": excluded, "unpaired_experimental_modes": unpaired,
                "experimental_source": experiment.source_name, "peak_derived_modes": peak_modes,
                "parameters": [asdict(p) for p in config.parameters], "sigma_ln": SIGMA_LN}
        if len(rows) < len(names) + 1:
            return self._refused(base, f"only {len(rows)} mode pair(s) with MAC ≥ {IDENTIFICATION_MAC:g}; at least "
                                       f"{len(names) + 1} are needed for {len(names)} parameter(s). Pairing uses the "
                                       "unchanged INP: if its frequencies are more than ~15 % off the experiment, "
                                       "start from closer constants; also check the orientation and the mode range.")
        self.progress(f"{len(rows)} observation rows frozen: " +
                      ", ".join(f"EXP {r.experimental_mode} {r.experimental_hz:.2f} Hz ↔ FE {r.baseline_fe_mode} "
                                f"{r.baseline_fe_hz:.2f} Hz (MAC {r.mac:.3f})" for r in rows))

        bounds = parameter_bounds([(p.name, p.lower, p.upper) for p in config.parameters])
        settings = LMSettings(mu_initial=LM_MU_INITIAL, mu_decrease=LM_MU_DECREASE,
                              max_step_attempts=LM_STEP_ATTEMPTS, solve_budget=config.solve_budget)
        try:
            lm = run_bounded_lm(self.evaluate, start, bounds, settings)
        except StepError as error:
            return self._refused(base, f"no step defined: {error} (a parameter does not change any paired "
                                       "frequency)")
        base["lm"] = {"status": lm.status.value, "iterations": lm.iterations, "evaluations": lm.solves,
                      "objective": None if math.isnan(lm.objective) else lm.objective,
                      "last_point": dict(lm.parameters), "refusal": lm.refusal,
                      "history": [asdict(h) for h in lm.history]}
        if lm.status is not LMStatus.CONVERGED:
            reason = {
                LMStatus.AT_BOUND: "the optimum lies on a search bound: the true multiplier is outside "
                                   "[lower, upper] or the model cannot reproduce the experiment with this parameter",
                LMStatus.REFUSED: f"mode identity lost while changing the parameter ({lm.refusal})",
                LMStatus.MAX_ITERATIONS: "not converged within 5 iterations",
                LMStatus.STEP_REJECTED: "no step decreased the misfit",
                LMStatus.SOLVE_BUDGET: "the solve budget was used up before convergence",
            }.get(lm.status, lm.status.value)
            return self._refused(base, reason)

        p_hat = dict(lm.parameters)
        self.progress("convergence reached; fresh sensitivities at the optimum")
        try:
            final = self.evaluate(p_hat)
            jacobian = self._central_jacobian(p_hat, names)
        except BranchTrackingRefusal as refusal:
            return self._refused(base, f"mode identity lost at the optimum ({refusal})")
        return self._result(base, p_hat, names, final, jacobian, peak_modes)

    def _central_jacobian(self, p_hat: Mapping[str, float], names: Sequence[str]) -> np.ndarray:
        h = 0.05
        columns = []
        for name in names:
            up, down = dict(p_hat), dict(p_hat)
            up[name], down[name] = p_hat[name] * (1 + h), p_hat[name] * (1 - h)
            columns.append((self.evaluate(up) - self.evaluate(down)) / (math.log(1 + h) - math.log(1 - h)))
        return np.column_stack(columns)

    # -- statistics and grading
    def _result(self, base: dict, p_hat: Mapping[str, float], names: Sequence[str], r: np.ndarray,
                jacobian: np.ndarray, peak_modes: Sequence[int]) -> dict:
        m, n = jacobian.shape
        sensitivities = jacobian * SIGMA_LN  # d ln f / d ln k
        refusals = []
        for j, name in enumerate(names):
            if np.max(np.abs(sensitivities[:, j])) < MINIMUM_SENSITIVITY:
                refusals.append(f"{name} is not observable: |d ln f / d ln k| < {MINIMUM_SENSITIVITY} on every row")
        singular = np.linalg.svd(jacobian, compute_uv=False)
        if singular[-1] <= RANK_RCOND * singular[0]:
            refusals.append("the parameters cannot be separated by these modes (rank-deficient sensitivities)")
        covariance = np.linalg.pinv(jacobian.T @ jacobian)
        statistical_sd = np.sqrt(np.maximum(np.diag(covariance), 0.0))
        chi2 = float(r @ r)
        dof = m - n
        scatter_factor = math.sqrt(max(1.0, chi2 / dof)) if dof > 0 else None
        scatter_sd = statistical_sd * (scatter_factor if scatter_factor is not None else float("nan"))
        # Mode spread: how far apart the modes are about the value, (SᵀS)⁻¹·Σ Δln f² (= scatter sd · √dof).
        # Under a model-form discrepancy this, not the sd of a mean, is the honest width of the answer.
        residual_ln = r * SIGMA_LN
        spread_sd = np.sqrt(np.maximum(np.diag(np.linalg.pinv(sensitivities.T @ sensitivities)), 0.0)
                            * float(residual_ln @ residual_ln))
        loo = self._leave_one_out(jacobian, r, names, p_hat)
        rows = self._row_table(p_hat, names, r, sensitivities)
        max_rel = max(abs(row["final_error_percent"]) for row in rows) / 100.0
        correlation = None
        if n > 1:
            d = np.sqrt(np.diag(covariance))
            correlation = (covariance / np.outer(d, d)).tolist()

        estimates = {}
        grades = []
        for j, name in enumerate(names):
            band_parts = [v for v in (scatter_sd[j], loo["half_range_ln"].get(name),
                                      spread_sd[j] if dof > 0 else None) if v is not None and math.isfinite(v)]
            band_ln = max(band_parts) if band_parts else float("nan")
            spec = self.config.parameters[j]
            reasons = []
            if not math.isfinite(band_ln):
                reasons.append("no uncertainty band (as many rows as parameters)")
            grade = _grade(band_ln, max_rel, m, n, bool(peak_modes), reasons)
            if correlation is not None:
                strongest = max(abs(correlation[j][k]) for k in range(n) if k != j)
                if strongest > 0.95:
                    grade = GRADE_UNRELIABLE
                    reasons.append(f"strongly correlated with another parameter (|ρ| = {strongest:.2f})")
            if n == 1:
                implied = [row["implied_multiplier"] for row in rows if row.get("implied_multiplier")]
                if len(implied) >= 2:
                    spread = 0.5 * (math.log(max(implied)) - math.log(min(implied)))
                    if spread > APPROXIMATE_LIMIT:
                        reasons.append(f"single modes ask for k from {min(implied):.3f} to {max(implied):.3f} "
                                       f"(±{(math.exp(spread) - 1) * 100:.0f} %): the model does not reproduce all "
                                       "modes with one value (model-form discrepancy)")
            grades.append(grade)
            k_hat = float(p_hat[name])
            record = self.model.records[spec.material.lower()]
            estimates[name] = {
                "multiplier": k_hat,
                "band_ln": band_ln,
                "band_percent": (math.exp(band_ln) - 1.0) * 100.0 if math.isfinite(band_ln) else None,
                "statistical_sd_ln": float(statistical_sd[j]),
                "scatter_scaled_sd_ln": None if scatter_factor is None else float(scatter_sd[j]),
                "mode_spread_ln": float(spread_sd[j]) if dof > 0 else None,
                "leave_one_out": {"min_multiplier": loo["min"].get(name), "max_multiplier": loo["max"].get(name),
                                  "half_range_ln": loo["half_range_ln"].get(name)},
                "grade": grade, "grade_reasons": reasons,
                "constants": {c: {"inp_value": record.value(c), "calibrated_value": record.value(c) * k_hat}
                              for c in spec.constants},
                "material": spec.material,
            }
        status = STATUS_REFUSED if refusals else STATUS_ESTIMATE
        result = dict(base, status=status, refusal_reasons=refusals,
                      estimates={} if refusals else estimates,
                      diagnostic_candidate=estimates if refusals else None,
                      overall_grade=None if refusals else _worst(grades),
                      statistics={"chi2": chi2, "dof": dof, "chi2_per_dof": chi2 / dof if dof > 0 else None,
                                  "scatter_factor": scatter_factor, "max_abs_relative_error": max_rel,
                                  "rms_relative_error": float(np.sqrt(np.mean(np.expm1(r * SIGMA_LN) ** 2))),
                                  "correlation": correlation, "singular_values": singular.tolist()},
                      rows=rows, leave_one_out_cases=loo["cases"],
                      abaqus_solves=self.abaqus_solves,
                      evaluations=[asdict(e) for e in self.evaluations])
        return result

    def _leave_one_out(self, jacobian: np.ndarray, r: np.ndarray, names: Sequence[str],
                       p_hat: Mapping[str, float]) -> dict:
        m, n = jacobian.shape
        cases, estimates = [], {name: [] for name in names}
        for i, row in enumerate(self.rows):
            keep = [k for k in range(m) if k != i]
            sub = jacobian[keep]
            if len(keep) < n or np.linalg.matrix_rank(sub, tol=RANK_RCOND * np.linalg.norm(sub, 2)) < n:
                cases.append({"removed": row.row_id, "status": "NOT_EVALUABLE"})
                continue
            shift = np.linalg.lstsq(sub, -r[keep], rcond=None)[0]
            values = {name: float(p_hat[name] * math.exp(shift[j])) for j, name in enumerate(names)}
            for name in names:
                estimates[name].append(values[name])
            cases.append({"removed": row.row_id, "status": "VALID", "multipliers": values})
        complete = all(c["status"] == "VALID" for c in cases) and m > n
        half = {name: (0.5 * (math.log(max(v)) - math.log(min(v))) if complete else None)
                for name, v in estimates.items()}
        return {"cases": cases, "half_range_ln": half,
                "min": {name: (min(v) if complete else None) for name, v in estimates.items()},
                "max": {name: (max(v) if complete else None) for name, v in estimates.items()}}

    def _row_table(self, p_hat: Mapping[str, float], names: Sequence[str], r: np.ndarray,
                   sensitivities: np.ndarray) -> list[dict]:
        final = next(e for e in reversed(self.evaluations)
                     if all(math.isclose(e.multipliers[k], p_hat[k], rel_tol=1e-12) for k in names))
        table = []
        for i, row in enumerate(self.rows):
            entry = {
                "row_id": row.row_id, "experimental_mode": row.experimental_mode,
                "experimental_hz": row.experimental_hz, "baseline_fe_mode": row.baseline_fe_mode,
                "baseline_fe_hz": row.baseline_fe_hz,
                "baseline_error_percent": (row.baseline_fe_hz / row.experimental_hz - 1.0) * 100.0,
                "final_fe_hz": final.fe_hz[row.row_id],
                "final_error_percent": (final.fe_hz[row.row_id] / row.experimental_hz - 1.0) * 100.0,
                "pair_mac": row.mac, "tracking_mac": final.tracking_mac[row.row_id],
                "peak_derived": row.peak_derived,
                "sensitivity": {name: float(sensitivities[i, j]) for j, name in enumerate(names)},
            }
            if len(names) == 1:  # the multiplier this mode alone would ask for (linearised)
                s = sensitivities[i, 0]
                entry["implied_multiplier"] = (float(p_hat[names[0]] * math.exp(-r[i] * SIGMA_LN / s))
                                               if abs(s) >= MINIMUM_SENSITIVITY else None)
            table.append(entry)
        return table

    def _refused(self, base: dict, reason: str) -> dict:
        return dict(base, status=STATUS_REFUSED, refusal_reasons=[reason], estimates={}, overall_grade=None,
                    abaqus_solves=self.abaqus_solves, evaluations=[asdict(e) for e in self.evaluations],
                    rows=[asdict(r) for r in self.rows])

    def _inputs(self) -> dict:
        config = self.config
        return {"model_inp": str(config.model_inp), "model_inp_sha256": hashlib.sha256(self.model.source).hexdigest(),
                "experiment": str(config.experiment),
                "experiment_sha256": _sha256_file(Path(config.experiment)),
                "modal_set": config.modal_set, "experimental_modes": config.experimental_modes,
                "min_experimental_hz": config.min_experimental_hz, "max_experimental_hz": config.max_experimental_hz,
                "fe_last_mode": self.last_mode, "coordinate_scale": config.coordinate_scale,
                "orientation_candidate_id": config.orientation_candidate_id,
                "elastic_records": {k: {"type": v.elastic_type, "values": dict(zip(v.names, v.values))}
                                    for k, v in self.model.records.items()}}


def _sha256_file(path: Path) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(1 << 24), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _grade(band_ln: float, max_rel: float, rows: int, parameters: int, peak_derived: bool,
           reasons: list[str]) -> str:
    if not math.isfinite(band_ln):
        return GRADE_UNRELIABLE
    if band_ln <= GOOD_LIMIT and max_rel <= GOOD_LIMIT and rows >= parameters + 2 and not peak_derived:
        return GRADE_GOOD
    if band_ln <= APPROXIMATE_LIMIT and max_rel <= APPROXIMATE_LIMIT:
        if peak_derived:
            reasons.append("experimental modes are FRF peak-derived (no curve fit): at best APPROXIMATE")
        if rows < parameters + 2:
            reasons.append("too few modes for a leave-one-out check of more than one mode: at best APPROXIMATE")
        return GRADE_APPROXIMATE
    if band_ln > APPROXIMATE_LIMIT:
        reasons.append(f"band ±{(math.exp(band_ln) - 1) * 100:.1f} % > {APPROXIMATE_LIMIT * 100:.0f} %: the "
                       "modes disagree about the value (model-form discrepancy)")
    if max_rel > APPROXIMATE_LIMIT:
        reasons.append(f"a mode still differs by {max_rel * 100:.1f} % after calibration")
    return GRADE_UNRELIABLE


def _worst(grades: Sequence[str]) -> str:
    order = [GRADE_GOOD, GRADE_APPROXIMATE, GRADE_UNRELIABLE]
    return max(grades, key=order.index)


# ----------------------------------------------------------------------------- outputs

def write_outputs(result: dict, config: QuickCalibrationConfig, model: InpModel) -> dict[str, Path]:
    out = Path(config.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {"result": out / "result.json", "report": out / "report.txt", "modes": out / "modes.csv"}
    paths["result"].write_text(json.dumps(result, indent=2, ensure_ascii=False, default=_json_default),
                               encoding="utf-8")
    paths["report"].write_text(render_report(result), encoding="utf-8")
    _write_modes_csv(paths["modes"], result)
    if result.get("status") == STATUS_ESTIMATE:
        multipliers = {name: e["multiplier"] for name, e in result["estimates"].items()}
        header = [f"QUICK CALIBRATION ({LABEL}, {NOT_A_MATERIAL_PROPERTY}; grade {result['overall_grade']})",
                  "Effective constants that make THIS FE model reproduce THIS specimen's measured modes.",
                  "Not transferable to another model or specimen without validation."]
        for name, e in result["estimates"].items():
            for constant, values in e["constants"].items():
                header.append(f"{e['material']}/{constant}: {values['inp_value']:g} -> "
                              f"{values['calibrated_value']:.6g} (k = {e['multiplier']:.4f}, "
                              f"band ±{e['band_percent']:.1f} %)")
        paths["calibrated_inp"] = out / f"{Path(config.model_inp).stem}_calibrated.inp"
        paths["calibrated_inp"].write_bytes(model.render(multipliers, header))
    return paths


def _json_default(value):
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (np.floating, np.integer)):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(type(value).__name__)


def _write_modes_csv(path: Path, result: dict) -> None:
    rows = result.get("rows") or []
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["row", "exp_mode", "exp_hz", "fe_mode", "fe_hz_start", "error_start_%", "fe_hz_final",
                         "error_final_%", "pair_MAC", "tracking_MAC", "peak_derived", "sensitivity",
                         "implied_multiplier"])
        for row in rows:
            writer.writerow([row.get("row_id"), row.get("experimental_mode"), _f(row.get("experimental_hz")),
                             row.get("baseline_fe_mode"), _f(row.get("baseline_fe_hz")),
                             _f(row.get("baseline_error_percent")), _f(row.get("final_fe_hz")),
                             _f(row.get("final_error_percent")), _f(row.get("pair_mac") or row.get("mac")),
                             _f(row.get("tracking_mac")), row.get("peak_derived"),
                             json.dumps(row.get("sensitivity")) if row.get("sensitivity") else "",
                             _f(row.get("implied_multiplier"))])


def _f(value) -> str:
    return "" if value is None else f"{value:.6g}"


def render_report(result: dict) -> str:
    lines = ["QUICK EFFECTIVE-PROPERTY CALIBRATION", "=" * 36,
             f"Label: {LABEL} / {NOT_A_MATERIAL_PROPERTY}",
             "Meaning: the constants that make this FE model reproduce this specimen's measured modes.",
             "", f"Model INP:   {result['inputs']['model_inp']}", f"Experiment:  {result['inputs']['experiment']}",
             f"Experimental source: {result.get('experimental_source')}"]
    if result.get("peak_derived_modes"):
        lines.append("WARNING: experimental modes are FRF peak-derived (dataset 58), not curve-fitted.")
    lines.append("")
    if result["status"] == STATUS_REFUSED:
        lines += ["RESULT: NO VALUE", *[f"  reason: {r}" for r in result["refusal_reasons"]]]
        candidate = result.get("diagnostic_candidate")
        if candidate:
            lines.append("  (optimiser candidate kept in result.json as a diagnostic only)")
    else:
        lines.append(f"RESULT: {result['overall_grade']}")
        for name, e in result["estimates"].items():
            loo = e["leave_one_out"]
            lines.append(f"  {name} ({e['material']}): k = {e['multiplier']:.4f}  band ±{e['band_percent']:.1f} %  "
                         f"[{e['grade']}]")
            for constant, values in e["constants"].items():
                lines.append(f"      {constant}: {values['inp_value']:g} -> {values['calibrated_value']:.6g}")
            if loo["min_multiplier"] is not None:
                lines.append(f"      leave-one-mode-out range of k: {loo['min_multiplier']:.4f} .. "
                             f"{loo['max_multiplier']:.4f}")
            for reason in e["grade_reasons"]:
                lines.append(f"      note: {reason}")
        stats = result["statistics"]
        lines.append(f"  max |frequency error| after calibration: {stats['max_abs_relative_error'] * 100:.2f} %  "
                     f"(rms {stats['rms_relative_error'] * 100:.2f} %)")
    lines += ["", "MODES (fitted rows)",
              f"{'row':>6} {'EXP':>4} {'f_exp Hz':>10} {'FE':>4} {'start %':>8} {'final %':>8} {'MAC':>6} "
              f"{'S':>7} {'k alone':>8}"]
    for row in result.get("rows") or []:
        s = row.get("sensitivity") or {}
        first = next(iter(s.values()), None)
        lines.append(f"{row['row_id']:>6} {row['experimental_mode']:>4} {row['experimental_hz']:>10.3f} "
                     f"{row['baseline_fe_mode']:>4} {_p(row.get('baseline_error_percent', _start(row))):>8} "
                     f"{_p(row.get('final_error_percent')):>8} {_p(row.get('pair_mac', row.get('mac')), 3):>6} "
                     f"{_p(first, 3):>7} {_p(row.get('implied_multiplier'), 4):>8}")
    if result.get("excluded_pairs"):
        lines += ["", "Paired but not fitted (MAC < 0.80):"]
        lines += [f"  EXP {p['experimental_mode']} {p['experimental_hz']:.2f} Hz <-> FE {p['fe_mode']} "
                  f"{p['fe_hz']:.2f} Hz, MAC {_p(p['mac'], 3)}" for p in result["excluded_pairs"]]
    if result.get("unpaired_experimental_modes"):
        lines.append(f"Unpaired experimental modes: {result['unpaired_experimental_modes']}")
    lines += ["", f"New Abaqus solves in this run: {result.get('abaqus_solves')} (finished jobs are reused)",
              "Band = max(scatter-scaled sd, half of the leave-one-mode-out range, mode spread); σ = 0.3 % per mode.",
              "Mode spread = how far apart the single modes are about the value (sensitivity-weighted).",
              "Grades: GOOD band ≤ 5 % and all modes ≤ 5 %; APPROXIMATE ≤ 10 %; otherwise UNRELIABLE.",
              "A large band means the modes disagree about the value: the model form (core, adhesive, thickness,",
              "boundary conditions) limits the calibration, not the optimiser."]
    return "\n".join(lines) + "\n"


def _start(row: dict) -> Optional[float]:
    if row.get("baseline_fe_hz") and row.get("experimental_hz"):
        return (row["baseline_fe_hz"] / row["experimental_hz"] - 1.0) * 100.0
    return None


def _p(value, digits: int = 2) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def run_quick_calibration(config: QuickCalibrationConfig, solve: Optional[SolveFunction] = None,
                          extract: Optional[ExtractFunction] = None,
                          progress: Optional[ProgressFunction] = None) -> tuple[dict, dict[str, Path]]:
    """Run the calibration and write result.json, report.txt, modes.csv (and the calibrated INP)."""

    if solve is None or extract is None:
        runner = AbaqusRunner(config.abaqus_command, config.cpus, config.timeout_minutes)
        solve = solve or runner.solve
        extract = extract or runner.extract
    calibration = QuickCalibration(config, solve, extract, progress)
    result = calibration.run()
    paths = write_outputs(result, config, calibration.model)
    return result, paths

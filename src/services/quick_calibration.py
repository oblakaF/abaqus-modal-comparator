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
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
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
from .owned_processes import ALIVE, GONE, OwnedProcessTree, process_state


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
BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
# Hard per-run cap on NEW Abaqus FE solve attempts (baseline, optimiser, final evaluation, sensitivities, anything
# else). Finished jobs reused from the cache do not count. 24 = 1 baseline + 16 optimiser evaluations (the default LM
# evaluation budget) + 2 central differences for each of up to 2 parameters + 3 spare. Never unlimited.
DEFAULT_MAX_NEW_FE_SOLVES = 24


class QuickCalibrationError(ValueError):
    """Inputs cannot be used as given; nothing is guessed."""

    def __init__(self, message: str, candidates: Sequence[Mapping] = ()) -> None:
        super().__init__(message)
        self.candidates = list(candidates)  # orientation candidates when the registration is ambiguous


class CalibrationCancelled(QuickCalibrationError):
    """Stopped by the user; every Abaqus process this session owned is confirmed terminated."""


class TerminationUnconfirmed(QuickCalibrationError):
    """An owned Abaqus process was asked to stop, but its termination could not be confirmed.

    ``still_running()`` re-checks the owned processes: a list (empty once they are confirmed gone), or ``None`` when
    there is no tracker or it cannot establish identities. Unknown is never "stopped": ``resolved()`` is True only
    for a confirmed empty list.
    """

    def __init__(self, message: str, check: Optional[Callable[[], Optional[list]]] = None) -> None:
        super().__init__(message)
        self._check = check

    def still_running(self) -> Optional[list]:
        if self._check is None:
            return None
        try:
            remaining = self._check()
        except Exception:  # noqa: BLE001 - a failing check is an unknown state
            return None
        return None if remaining is None else list(remaining)

    def resolved(self) -> bool:
        return self.still_running() == []


class FESolveBudgetExhausted(QuickCalibrationError):
    """The per-run cap on new Abaqus FE solves is reached; no further solve is started."""

    def __init__(self, limit: int, attempted: int, completed: int, stage: str) -> None:
        super().__init__(f"{BUDGET_EXHAUSTED}: the limit of {limit} new Abaqus FE solve(s) for this run is used up "
                         f"({attempted} attempted, {completed} completed); the next solve ({stage}) was not started. "
                         "No calibrated value is published.")
        self.limit, self.attempted, self.completed, self.stage = limit, attempted, completed, stage


def _max_new_fe_solves(value) -> int:
    """A finite positive integer; there is no unlimited setting."""
    if isinstance(value, bool) or value is None:
        raise QuickCalibrationError("max_new_fe_solves must be a finite positive integer (no unlimited execution).")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise QuickCalibrationError("max_new_fe_solves must be a finite positive integer.") from None
    if not number.is_integer() or number < 1:  # also refuses inf and nan
        raise QuickCalibrationError("max_new_fe_solves must be a finite positive integer (no unlimited execution).")
    return int(number)


class PreflightRefused(QuickCalibrationError):
    """The input preflight refused the run; no Abaqus solve was started."""

    def __init__(self, report) -> None:
        super().__init__("input preflight refused the run (no Abaqus solve was started): "
                         + " | ".join(report.refusals()))
        self.report = report


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
    max_new_fe_solves: int = DEFAULT_MAX_NEW_FE_SOLVES  # hard cap on NEW Abaqus solve attempts in the whole run
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
        object.__setattr__(self, "max_new_fe_solves", _max_new_fe_solves(self.max_new_fe_solves))


def config_from_dict(data: Mapping, base_dir: Path = Path(".")) -> QuickCalibrationConfig:
    """Build a config from JSON-like data; relative paths are resolved against ``base_dir``."""

    known = {"model_inp", "experiment", "parameters", "output_dir", "abaqus_command", "cpus", "modal_set",
             "experimental_modes", "min_experimental_hz", "max_experimental_hz", "fe_last_mode", "coordinate_scale",
             "orientation_candidate_id", "solve_budget", "max_new_fe_solves", "timeout_minutes", "comment"}
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
        solve_budget=int(data.get("solve_budget", 16)),
        max_new_fe_solves=_max_new_fe_solves(data["max_new_fe_solves"]) if "max_new_fe_solves" in data
        else DEFAULT_MAX_NEW_FE_SOLVES,
        timeout_minutes=float(data.get("timeout_minutes", 120.0)))


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
        "max_new_fe_solves": DEFAULT_MAX_NEW_FE_SOLVES,
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
    """Real Abaqus: one solve per job directory, then the application's ODB extraction script.

    Every process is owned by this session: ``cancel_event`` stops the running solve or extraction, and a stop is
    reported only after the owned process tree is confirmed terminated (``TerminationUnconfirmed`` otherwise).
    """

    COMPLETED = "THE ANALYSIS HAS COMPLETED SUCCESSFULLY"
    POLL_SECONDS = 0.5
    STOP_TIMEOUT_SECONDS = 60.0

    def __init__(self, abaqus_command: str = "abaqus", cpus: int = 1, timeout_minutes: float = 120.0,
                 cancel_event: Optional[threading.Event] = None, popen=subprocess.Popen,
                 tree_factory=OwnedProcessTree) -> None:
        self.abaqus_command = (abaqus_command or "abaqus").strip()
        self.cpus = int(cpus)
        self.timeout_seconds = max(1, int(timeout_minutes * 60))
        self.cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self._popen, self._tree_factory = popen, tree_factory

    def identity(self) -> dict:
        """Solver and extraction identity recorded with every job and compared before any reuse."""
        return {"solver": abaqus_identity(self.abaqus_command), "extraction": extraction_identity()}

    def _command(self, arguments: Sequence[str]):
        if os.name == "nt":
            executable = self.abaqus_command
            if " " in executable and not executable.startswith('"'):
                executable = f'"{executable}"'
            inner = " ".join([executable] + [subprocess.list2cmdline([a]) for a in arguments])
            return f'cmd.exe /d /s /c "{inner}"'  # a string: Popen must not re-quote it (audit V11)
        return shlex.split(self.abaqus_command) + list(arguments)

    def _run(self, command, directory: Path, log_path: Path) -> int:
        if self.cancel_event.is_set():
            raise CalibrationCancelled("stopped by the user before the Abaqus solve started.")
        options = {"cwd": str(directory), "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            options["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            options["start_new_session"] = True
        with open(log_path, "w", encoding="utf-8", errors="replace") as log:
            log.write(f"{command}\n")
            log.flush()
            process = self._popen(command, stdout=log, stderr=subprocess.STDOUT, **options)
            tree = self._tree_factory(process)
            started = time.monotonic()
            try:
                while True:
                    try:
                        return process.wait(timeout=self.POLL_SECONDS)
                    except subprocess.TimeoutExpired:
                        pass
                    tree.refresh()
                    if self.cancel_event.is_set():
                        self._stop(tree, "stopped by the user", log_path)
                    if time.monotonic() - started > self.timeout_seconds:
                        self._stop(tree, f"Abaqus exceeded {self.timeout_seconds // 60} min", log_path,
                                   timed_out=True)
            except QuickCalibrationError:
                raise  # _stop already terminated the tree and named the outcome
            except BaseException as error:  # Ctrl+C or any failure while the solve may still run
                if not tree.terminate(self.STOP_TIMEOUT_SECONDS):
                    raise TerminationUnconfirmed(
                        f"interrupted ({type(error).__name__}), but the termination of the owned Abaqus processes "
                        f"could not be confirmed (still running: {tree.describe()}). Treat the solve as running; "
                        f"check Task Manager before retrying. Log: {log_path}", tree.unconfirmed) from error
                raise

    def _stop(self, tree: OwnedProcessTree, reason: str, log_path: Path, timed_out: bool = False) -> None:
        """Terminate the owned tree and raise; the outcome names whether termination was confirmed."""
        if not tree.terminate(self.STOP_TIMEOUT_SECONDS):
            raise TerminationUnconfirmed(
                f"{reason}, but the termination of the owned Abaqus processes could not be confirmed (still "
                f"running: {tree.describe()}). Treat the solve as running; check Task Manager before retrying. "
                f"Log: {log_path}", tree.unconfirmed)
        if timed_out:
            raise QuickCalibrationError(f"{reason}; the owned process tree was terminated (confirmed). Log: {log_path}")
        raise CalibrationCancelled(f"{reason}; the owned Abaqus solve was terminated (confirmed).")

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

        if self.cancel_event.is_set():
            raise CalibrationCancelled("stopped by the user before the ODB extraction started.")
        # The extraction stops its own launcher and registered worker; this session also records every descendant
        # of the launcher while it runs, so that after a stop or failure nothing it started is left behind.
        owned: dict = {}
        watching = threading.Event()

        def remember(process) -> None:
            if process is not None and "tree" not in owned:
                owned["tree"] = self._tree_factory(process)

        def watch() -> None:
            while not watching.wait(self.POLL_SECONDS):
                if "tree" in owned:
                    owned["tree"].refresh()

        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        failure: Optional[BaseException] = None
        try:
            manifest = abaqus_bridge.run_abaqus_extraction(odb_path, output_dir, abaqus_command=self.abaqus_command,
                                                           start_mode=1, end_mode=int(last_mode),
                                                           timeout_seconds=self.timeout_seconds,
                                                           cancel_event=self.cancel_event, process_callback=remember)
        except abaqus_bridge.AbaqusExtractionError as error:
            failure = error
        except abaqus_bridge.AnalysisCancelled as error:
            failure = error
        except BaseException as error:  # Ctrl+C or any other failure while the extraction may still run
            failure = error
        finally:
            watching.set()
            watcher.join()
        if failure is None:
            return abaqus_bridge.load_extracted_odb(manifest)
        tree = owned.get("tree")
        if isinstance(failure, abaqus_bridge.ExtractionTerminationUnconfirmed):
            raise TerminationUnconfirmed(str(failure), None if tree is None else tree.unconfirmed) from None
        if tree is not None and not tree.terminate(self.STOP_TIMEOUT_SECONDS):
            raise TerminationUnconfirmed(
                f"{failure}; afterwards owned extraction processes could not be confirmed terminated (still running: "
                f"{tree.describe()}). Check Task Manager before retrying.", tree.unconfirmed) from failure
        if not isinstance(failure, (abaqus_bridge.AbaqusExtractionError, abaqus_bridge.AnalysisCancelled)):
            raise failure  # the owned processes are confirmed gone; the original interruption is kept
        if isinstance(failure, abaqus_bridge.AnalysisCancelled):
            raise CalibrationCancelled("stopped by the user; the owned ODB extraction was terminated "
                                       "(confirmed).") from None
        raise QuickCalibrationError(str(failure)) from None


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
    # Atomic: ``fe_modes.npz`` is the completed-job marker, so it appears only complete (temporary file, replace).
    handle, temporary = tempfile.mkstemp(prefix=".fe_modes.", suffix=".partial", dir=Path(path).parent)
    try:
        with os.fdopen(handle, "wb") as stream:
            np.savez_compressed(stream, numbers=np.array([m.number for m in modes]),
                                frequencies=np.array([m.frequency_hz for m in modes]),
                                node_ids=np.array(keys)[rows],
                                coordinates=np.asarray(modes[0].coordinates)[rows],
                                vectors=np.stack([np.real(np.asarray(m.vectors))[rows] for m in modes]))
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _load_state(path: Path) -> ModalDataset:
    with np.load(path, allow_pickle=False) as data:
        node_ids = data["node_ids"].astype(object)
        modes = [ModeShape(int(n), float(f), node_ids, data["coordinates"], v)
                 for n, f, v in zip(data["numbers"], data["frequencies"], data["vectors"])]
    return ModalDataset("Abaqus ODB (cached)", path, modes)


# ----------------------------------------------------------------------------- verified FE job cache

CACHE_SCHEMA = "quick-calibration/fe-job-provenance/v1"
PROVENANCE_FILE = "provenance.json"  # the completion marker: written atomically after solve, extraction and data
UNCONFIRMED_MARKER = "TERMINATION_UNCONFIRMED.json"
VERIFIED_REUSE = "VERIFIED_REUSE"
INVALIDATED = "INVALIDATED"
NEW_SOLVE = "NEW_SOLVE"
EXTRACT_SCRIPT = Path(__file__).resolve().parents[2] / "abaqus_scripts" / "extract_odb.py"
_SOLVER_VERSION = re.compile(r"Abaqus(?:/Standard)?\s+(?:3DEXPERIENCE\s+)?(R?\d{4}[A-Za-z0-9._-]*)")


def _file_fingerprint(path: Path) -> Optional[dict]:
    digest = _sha256_file(Path(path))
    if digest is None:
        return None
    return {"path": str(Path(path).resolve()), "sha256": digest, "size": Path(path).stat().st_size}


def _canonical_hash(record: Mapping) -> str:
    return hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def abaqus_identity(command: str) -> dict:
    """The Abaqus command and the content of the launcher it resolves to (None when it cannot be resolved)."""
    command = (command or "abaqus").strip()
    try:
        first = shlex.split(command, posix=os.name != "nt")[0].strip('"')
    except (ValueError, IndexError):
        first = command
    located = shutil.which(first) or (first if Path(first).is_file() else None)
    fingerprint = _file_fingerprint(Path(located)) if located else None
    return {"command": command, "executable": None if fingerprint is None else fingerprint["path"],
            "executable_sha256": None if fingerprint is None else fingerprint["sha256"]}


def extraction_identity() -> dict:
    return {"script": "abaqus_scripts/extract_odb.py", "script_sha256": _sha256_file(EXTRACT_SCRIPT),
            "start_mode": 1, "reader": "abaqus_bridge.load_extracted_odb"}


def input_file_fingerprints(source: bytes) -> list[dict]:
    """Every file read through INPUT= (nested included), with its content hash; refuses what cannot be read."""
    entries, seen = [], set()

    def walk(content: bytes, origin: str, depth: int) -> None:
        for number, keyword, value in inp_file_references(content):
            path = Path(value)
            if not path.is_absolute():
                raise QuickCalibrationError(f"{origin} line {number}: relative INPUT={value} cannot be verified.")
            fingerprint = _file_fingerprint(path)
            if fingerprint is None:
                raise QuickCalibrationError(f"{origin} line {number}: INPUT={value} cannot be read.")
            entries.append(dict(fingerprint, reference=f"{origin} line {number} (*{keyword})"))
            key = os.path.normcase(fingerprint["path"])
            if key not in seen and depth < _INCLUDE_DEPTH:
                seen.add(key)
                walk(path.read_bytes(), path.name, depth + 1)

    walk(source, "model INP", 0)
    return entries


def _node_set(node_ids: Sequence[str], kind: str) -> dict:
    ids = [_node_key(n) for n in node_ids]
    return {"kind": kind, "count": len(ids), "sha256": hashlib.sha256("\n".join(ids).encode("utf-8")).hexdigest()}


def _solver_version(job_dir: Path, job_name: str) -> Optional[str]:
    """The Abaqus release stated by the solved job itself (.dat / .msg header), when available."""
    for suffix in (".dat", ".msg"):
        try:
            with open(Path(job_dir) / f"{job_name}{suffix}", encoding="utf-8", errors="replace") as handle:
                match = _SOLVER_VERSION.search(handle.read(65536))
        except OSError:
            continue
        if match:
            return match.group(1)
    return None


def _identity_complete(value) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(item is not None for item in value.values())


def verify_job_cache(job_dir: Path, required: Mapping, required_nodes: Optional[Sequence[str]]):
    """(decision, reason, fingerprints, dataset): VERIFIED_REUSE only when the provenance record is intact, matches
    every current requirement, and the mode data is the recorded, complete data. Anything else fails closed."""
    job_dir = Path(job_dir)
    record_path, data_path = job_dir / PROVENANCE_FILE, job_dir / "fe_modes.npz"
    if not job_dir.exists():
        return NEW_SOLVE, "no finished job", {}, None
    if not record_path.is_file():
        reason = ("NOT VERIFIED: mode data without a provenance record (old cache or interrupted job)"
                  if data_path.exists() else "incomplete job without a provenance record (interrupted or failed)")
        return INVALIDATED, reason, {}, None
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return INVALIDATED, "provenance record unreadable", {}, None
    if not isinstance(record, dict) or record.get("schema") != CACHE_SCHEMA:
        return INVALIDATED, "provenance record of an unknown schema", {}, None
    if record.get("record_hash") != _canonical_hash({k: v for k, v in record.items() if k != "record_hash"}):
        return INVALIDATED, "provenance record corrupted (record hash mismatch)", {}, None
    prints = {"generated_inp_sha256": str(record.get("generated_inp_sha256"))[:16],
              "data_sha256": str((record.get("data") or {}).get("sha256"))[:16],
              "solver": _canonical_hash(record.get("solver") or {})[:12],
              "extraction": _canonical_hash(record.get("extraction") or {})[:12],
              "input_files": len(record.get("input_files") or [])}
    for key, label in (("generated_inp_sha256", "generated INP"), ("input_files", "INPUT= files"),
                       ("fe_last_mode", "requested FE modal range"), ("solver", "Abaqus executable/configuration"),
                       ("extraction", "extraction script/settings")):
        current = required.get(key)
        if current is None or (key in ("solver", "extraction") and not _identity_complete(current)):
            return INVALIDATED, f"{label}: current identity unavailable (fail closed)", prints, None
        if record.get(key) != current:
            return INVALIDATED, f"{label} changed", prints, None
    completion = record.get("completion") or {}
    if completion.get("solve") != "COMPLETED" or completion.get("extraction") != "VALID":
        return INVALIDATED, "the recorded solve or extraction is not complete", prints, None
    stored_nodes, needed = record.get("node_set") or {}, required.get("node_set")
    if needed is None and stored_nodes.get("kind") != "ALL":
        return INVALIDATED, "the baseline needs every FE node; the job holds a tracking subset", prints, None
    if needed is not None and stored_nodes.get("kind") != "ALL" and stored_nodes != needed:
        return INVALIDATED, "tracking-node subset changed", prints, None
    data = _file_fingerprint(data_path)
    if data is None:
        return INVALIDATED, "mode data missing", prints, None
    recorded_data = record.get("data") or {}
    if (data["sha256"], data["size"]) != (recorded_data.get("sha256"), recorded_data.get("size")):
        return INVALIDATED, "mode data corrupted or replaced (SHA-256 mismatch)", prints, None
    try:
        dataset = _load_state(data_path)
    except Exception:  # noqa: BLE001 - unreadable data is never reused
        return INVALIDATED, "mode data unreadable", prints, None
    modes = dataset.sorted_modes()
    ids = [_node_key(n) for n in modes[0].node_ids] if modes else []
    if [m.number for m in modes] != completion.get("mode_numbers") or \
            _node_set(ids, stored_nodes.get("kind", "?")) != stored_nodes:
        return INVALIDATED, "mode data does not match its provenance record", prints, None
    if needed is not None and stored_nodes.get("kind") == "ALL" and not set(required_nodes or ()) <= set(ids):
        return INVALIDATED, "tracking nodes missing from the stored full node set", prints, None
    return VERIFIED_REUSE, "provenance and mode data verified", prints, dataset


def _write_json_atomically(path: Path, value) -> None:
    handle, temporary = tempfile.mkstemp(prefix=f".{Path(path).name}.", suffix=".partial", dir=Path(path).parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _unconfirmed_processes_gone(job_dir: Path, state=process_state) -> tuple[bool, str]:
    """Whether every process recorded by an unconfirmed stop of this job is now confirmed gone."""
    try:
        marker = json.loads((Path(job_dir) / UNCONFIRMED_MARKER).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return False, "the unconfirmed-termination record cannot be read"
    processes = marker.get("processes") if isinstance(marker, dict) else None
    if processes is None:
        return False, "the processes of the stopped job are unknown"
    remaining = []
    for item in processes:
        status, created = state(int(item["pid"]))
        recorded = None if item.get("created") is None else tuple(item["created"])
        if status == GONE or (status == ALIVE and recorded is not None and created != recorded):
            continue  # gone (or its PID now belongs to another process)
        remaining.append(f"PID {item['pid']}")
    return not remaining, ", ".join(remaining)


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


@dataclass(frozen=True)
class ModalSetChoice:
    """One dataset-55 modal set of the experimental file (as the application's reader discovers it)."""

    key: str
    display_name: str
    processing_name: str
    mode_count: int

    @property
    def label(self) -> str:
        return f"{self.display_name} — {self.mode_count} modes"


def discover_modal_sets(path: Path) -> tuple[ModalSetChoice, ...]:
    import universal_reader  # resolved at call time: the application's installed reader

    return tuple(ModalSetChoice(item.key, item.display_name, item.processing_name, len(item.modes))
                 for item in universal_reader.discover_experimental_modal_sets(Path(path)))


def _modal_set_listing(choices: Sequence[ModalSetChoice]) -> str:
    return "; ".join(f"{c.label} (key {c.key!r})" for c in choices)


def resolve_modal_set(choices: Sequence[ModalSetChoice], requested: Optional[str]) -> Optional[ModalSetChoice]:
    """The explicitly requested modal set, matched by key first, then by a unique name; never the first set.

    A single available set is used as the only set; several sets need an explicit choice. ``None`` means the file
    has no dataset-55 modal set (the reader's dataset 2414 / 58 fallback).
    """
    requested = None if requested is None or not str(requested).strip() else str(requested).strip()
    if not choices:
        if requested is not None:
            raise QuickCalibrationError(f"modal set {requested!r} was requested, but the experimental file has no "
                                        "dataset-55 modal set.")
        return None
    if requested is None:
        if len(choices) == 1:
            return choices[0]
        raise QuickCalibrationError(f"the experimental file has {len(choices)} dataset-55 modal sets; select one "
                                    f"explicitly (none is chosen automatically): {_modal_set_listing(choices)}.")
    text = requested.casefold()
    by_key = [c for c in choices if c.key.casefold() == text]
    if len(by_key) == 1:
        return by_key[0]
    by_name = [c for c in choices if text in (c.display_name.casefold(), c.processing_name.casefold())]
    if len(by_name) == 1:
        return by_name[0]
    if by_name:
        raise QuickCalibrationError(f"modal set {requested!r} matches several sets; select it by key: "
                                    f"{_modal_set_listing(by_name)}.")
    raise QuickCalibrationError(f"modal set {requested!r} was not found; available: {_modal_set_listing(choices)}.")


def load_experiment(config: QuickCalibrationConfig) -> ModalDataset:
    import universal_reader  # resolved at call time: the application's installed (hardened, cached) reader

    if not Path(config.experiment).is_file():
        raise QuickCalibrationError(f"experiment file not found: {config.experiment}")
    chosen = resolve_modal_set(discover_modal_sets(Path(config.experiment)), config.modal_set)
    try:
        dataset = universal_reader.load_universal_modal_file(Path(config.experiment),
                                                             modal_set=None if chosen is None else chosen.key)
    except ValueError as error:
        raise QuickCalibrationError(f"the experimental file cannot be read: {error}") from None
    if chosen is not None and dataset.metadata.get("modal_set_key") != chosen.key:
        raise QuickCalibrationError(f"the reader loaded modal set {dataset.metadata.get('modal_set_key')!r}, not the "
                                    f"selected {chosen.key!r}.")
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


# ----------------------------------------------------------------------------- input preflight (no Abaqus)

CHECK_OK = "OK"
CHECK_INFO = "INFO"
CHECK_REFUSED = "REFUSED"
READY = "READY"
NOT_READY = "NOT_READY"
ORIENTATION_PENDING = (
    "checked from the baseline FE geometry after the single baseline solve and before any optimisation step; if it "
    "is ambiguous the run stops there and lists the candidates (choose one from the photograph / corner marker, "
    "never from MAC)")
_INCLUDE_DEPTH = 10


@dataclass(frozen=True)
class PreflightCheck:
    item: str
    status: str  # OK | INFO | REFUSED
    detail: str


@dataclass(frozen=True)
class PreflightReport:
    checks: tuple[PreflightCheck, ...]
    available_modal_sets: tuple[ModalSetChoice, ...]
    modal_set: Optional[ModalSetChoice]
    experimental_mode_count: Optional[int]
    baseline_job_dir: Optional[Path]

    @property
    def ready(self) -> bool:
        return not any(check.status == CHECK_REFUSED for check in self.checks)

    @property
    def status(self) -> str:
        return READY if self.ready else NOT_READY

    def refusals(self) -> list[str]:
        return [f"{check.item}: {check.detail}" for check in self.checks if check.status == CHECK_REFUSED]

    def summary(self) -> str:
        if self.ready:
            return (f"{READY}: inputs checked, no Abaqus run yet. Modal set: "
                    f"{self.modal_set.label if self.modal_set else 'no dataset-55 set (fallback)'}; "
                    f"{self.experimental_mode_count} experimental mode(s) used.")
        return f"{NOT_READY}: " + " | ".join(self.refusals())

    def lines(self) -> list[str]:
        return [self.summary(), ""] + [f"[{c.status:>7}] {c.item}: {c.detail}" for c in self.checks]

    def to_dict(self) -> dict:
        return {"status": self.status, "checks": [asdict(c) for c in self.checks],
                "available_modal_sets": [asdict(c) for c in self.available_modal_sets],
                "modal_set": None if self.modal_set is None else asdict(self.modal_set),
                "experimental_mode_count": self.experimental_mode_count,
                "baseline_job_dir": None if self.baseline_job_dir is None else str(self.baseline_job_dir)}


def inp_file_references(source: bytes) -> list[tuple[int, str, str]]:
    """(line number, keyword, INPUT= value) of every keyword line that reads another file (*Include and others)."""
    out = []
    for number, line in enumerate(split_inp_lines(source), start=1):
        keyword = inp_keyword(line)
        if keyword is None:
            continue
        value = _parameters(line).get("input")
        if value:
            out.append((number, keyword, value))
    return out


def check_inp_references(source: bytes, job_dir: Path) -> tuple[list[str], list[str]]:
    """(resolved, problems) for every file referenced by INPUT=, as Abaqus resolves it from ``job_dir``.

    Abaqus resolves a relative INPUT= path from the directory the job runs in, which is the newly generated job
    directory; a relative reference therefore never reaches the file next to the source INP. Absolute references
    must be readable files; their own references are checked the same way.
    """
    resolved, problems, seen = [], [], set()

    def walk(content: bytes, origin: str, depth: int) -> None:
        for number, keyword, value in inp_file_references(content):
            where = f"{origin} line {number} (*{keyword}, input={value})"
            path = Path(value)
            target = path if path.is_absolute() else Path(job_dir) / path
            if not path.is_absolute():
                problems.append(f"{where}: relative path; Abaqus would look for {target}, which the generated job "
                                "directory does not contain (use an absolute path or merge the file into the INP)")
                continue
            if not target.is_file():
                problems.append(f"{where}: {target} does not exist")
                continue
            try:
                data = target.read_bytes()
            except OSError as error:
                problems.append(f"{where}: {target} is not readable ({error})")
                continue
            resolved.append(f"{where} → {target}")
            key = os.path.normcase(str(target.resolve()))
            if key in seen or depth >= _INCLUDE_DEPTH:
                continue
            seen.add(key)
            walk(data, target.name, depth + 1)

    walk(source, "model INP", 0)
    return resolved, problems


def _job_name(content: bytes) -> str:
    return f"qc_{hashlib.sha256(content).hexdigest()[:12]}"


def preflight(config: QuickCalibrationConfig) -> PreflightReport:
    """Check every input that can be checked before an Abaqus solve; nothing is solved, written or guessed."""

    checks: list[PreflightCheck] = []

    def add(item: str, status: str, detail: str) -> None:
        checks.append(PreflightCheck(item, status, detail))

    source, job_dir = None, None
    inp = Path(config.model_inp)
    try:
        source = inp.read_bytes()
        add("Model INP", CHECK_OK, f"{inp} ({len(source):,} bytes, SHA-256 {hashlib.sha256(source).hexdigest()[:12]})")
    except OSError as error:
        add("Model INP", CHECK_REFUSED, f"{inp} cannot be read: {error}")
    if source is not None:
        try:
            model = InpModel(source, config.parameters)
        except (QuickCalibrationError, ForwardBuildError) as error:
            add("Material and elastic constants", CHECK_REFUSED, str(error))
        else:
            for p in config.parameters:
                record = model.records[p.material.lower()]
                values = ", ".join(f"{c} = {record.value(c):g}" for c in p.constants)
                add("Material and elastic constants", CHECK_OK,
                    f"{p.name}: {p.material} (*Elastic type={record.elastic_type}) {values}; multiplier bounds "
                    f"[{p.lower:g}, {p.upper:g}]")
            last = config.fe_last_mode or model.eigenvalue_count or 60
            add("FE modes extracted", CHECK_INFO, f"1-{last}")
        job_dir = Path(config.output_dir) / "work" / _job_name(source)
        resolved, problems = check_inp_references(source, job_dir)
        for problem in problems:
            add("INP file references", CHECK_REFUSED, problem)
        if not problems:
            add("INP file references", CHECK_OK, "; ".join(resolved) if resolved else
                "none (*Include / INPUT= not used)")

    choices: tuple[ModalSetChoice, ...] = ()
    chosen, count = None, None
    experiment = Path(config.experiment)
    if not experiment.is_file():
        add("Experimental file", CHECK_REFUSED, f"{experiment} does not exist")
    else:
        try:
            choices = discover_modal_sets(experiment)
        except Exception as error:  # noqa: BLE001 - any reader failure is a refusal with its reason
            add("Experimental file", CHECK_REFUSED, f"{experiment} cannot be read: {error}")
        else:
            add("Experimental file", CHECK_OK, f"{experiment} ({experiment.stat().st_size:,} bytes); dataset-55 modal "
                                               f"sets: {_modal_set_listing(choices) if choices else 'none'}")
            try:
                chosen = resolve_modal_set(choices, config.modal_set)
            except QuickCalibrationError as error:
                add("Experimental modal set", CHECK_REFUSED, str(error))
            else:
                add("Experimental modal set", CHECK_OK if chosen else CHECK_INFO,
                    f"{chosen.label} (key {chosen.key!r}, "
                    f"{'selected explicitly' if config.modal_set else 'the only set in the file'})" if chosen else
                    "no dataset-55 set: the reader's dataset 2414 / 58 fallback is used (peak-derived modes are "
                    "rougher evidence)")
                try:
                    dataset = load_experiment(replace(config, modal_set=None if chosen is None else chosen.key))
                except QuickCalibrationError as error:
                    add("Experimental modes", CHECK_REFUSED, str(error))
                else:
                    modes = dataset.sorted_modes()
                    count = len(modes)
                    add("Experimental modes", CHECK_OK,
                        f"{count} mode(s) used, {modes[0].frequency_hz:.2f}-{modes[-1].frequency_hz:.2f} Hz"
                        + (f" (of {chosen.mode_count} in the set)" if chosen and chosen.mode_count != count else ""))
    if config.orientation_candidate_id:
        add("Physical orientation", CHECK_INFO, f"selected by the user: {config.orientation_candidate_id}; it is "
                                                "applied only if it is a geometry candidate of the baseline model")
    else:
        add("Physical orientation", CHECK_INFO, "not selected: " + ORIENTATION_PENDING)
    add("Abaqus", CHECK_INFO, f"command {config.abaqus_command!r}, {config.cpus} CPU(s); at most "
                              f"{config.max_new_fe_solves} new FE solve(s) in this run (baseline, optimiser, final "
                              "evaluation and sensitivities; reused finished jobs do not count); optimiser evaluation "
                              f"budget {config.solve_budget} (separate); no solve has been started")
    minimum = 1 + 2 * len(config.parameters)
    if config.max_new_fe_solves < minimum:
        add("FE solve budget", CHECK_INFO, f"{config.max_new_fe_solves} new FE solve(s) are fewer than a complete run "
                                           f"needs without reusable jobs (at least {minimum}): unless finished jobs "
                                           "are reused, the run ends BUDGET_EXHAUSTED without a value")
    return PreflightReport(tuple(checks), choices, chosen, count, job_dir)


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
                 progress: Optional[ProgressFunction] = None, cancel: Optional[threading.Event] = None,
                 solver_identity: Optional[Mapping] = None) -> None:
        self.config = config
        self.solver_identity = dict(solver_identity or {})  # {"solver": ..., "extraction": ...}; empty: unknown
        self.process_state = process_state  # re-checks processes recorded by an unconfirmed stop
        self.cache_decisions: list[dict] = []
        self.solve, self.extract = solve, extract
        self.progress = progress or (lambda message: None)
        self.cancel = cancel if cancel is not None else threading.Event()
        source = Path(config.model_inp)
        if not source.is_file():
            raise QuickCalibrationError(f"model INP not found: {source}")
        self.model = InpModel(source.read_bytes(), config.parameters)
        try:
            self._input_files: Optional[list] = input_file_fingerprints(self.model.source)
        except QuickCalibrationError:
            self._input_files = None  # unverifiable: no job is reused (a solve then fails visibly)
        self.last_mode = config.fe_last_mode or self.model.eigenvalue_count or 60
        self.work = Path(config.output_dir) / "work"
        self.work.mkdir(parents=True, exist_ok=True)
        self.abaqus_solves = 0  # completed new solves (the solver returned)
        self.new_solve_attempts = 0  # attempted new solves, failures included (the hard budget counts these)
        self.cache_hits = 0
        self.solve_stages: list[str] = []  # the workflow stage of every attempted new solve
        self.stage = "baseline"
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
            self.cache_hits += 1
            self._decide(VERIFIED_REUSE, job_name, "verified or solved earlier in this run", {})
            return self._cache[job_name]
        job_dir = self.work / job_name
        cached = job_dir / "fe_modes.npz"
        self._refuse_unconfirmed(job_dir)  # never reused, deleted or overwritten while its processes may run
        required = self._requirements(digest)
        decision, reason, prints, dataset = verify_job_cache(job_dir, required, self._tracking_order())
        if decision == VERIFIED_REUSE:
            self.cache_hits += 1
            self._decide(VERIFIED_REUSE, job_name, reason, prints)
            self.progress(f"{job_name}: verified reuse of a finished job ({self._describe(multipliers)})")
        else:
            if decision == INVALIDATED:
                self._decide(INVALIDATED, job_name, reason, prints)
                self.progress(f"{job_name}: cached job not reused ({reason})")
            self._check_cancel()
            self._claim_new_solve()  # the hard per-run cap: refused here, before anything is started
            self._decide(NEW_SOLVE, job_name, f"new solve {self.new_solve_attempts}/{self.config.max_new_fe_solves} "
                                              f"({self.stage})", {"generated_inp_sha256": digest[:16]})
            self._clear_job(job_dir)  # an unverified job is replaced at the same path, never beside it
            job_dir.mkdir(parents=True, exist_ok=True)
            inp = job_dir / f"{job_name}.inp"
            inp.write_bytes(content)
            self.progress(f"{job_name}: Abaqus solve {self.new_solve_attempts}/{self.config.max_new_fe_solves} "
                          f"({self.stage}; {self._describe(multipliers)})")
            started = time.monotonic()
            try:
                odb = self.solve(inp, job_dir, job_name)
                self.abaqus_solves += 1
                self._check_cancel()
                self.progress(f"{job_name}: extracting modes 1-{self.last_mode} "
                              f"(solve took {time.monotonic() - started:.0f} s)")
                dataset = self.extract(Path(odb), job_dir / "extraction", self.last_mode)
                self._check_cancel()
                nodes = self._tracking_order()
                _save_state(cached, dataset, nodes)
                self._write_provenance(job_dir, job_name, required, nodes)
            except TerminationUnconfirmed as error:
                _mark_unconfirmed(job_dir, error)  # processes may still write: untouched, never reused or replaced
                raise
            except BaseException:
                try:  # a stopped or failed job leaves no partial cache (it never had a completion marker)
                    self._clear_job(job_dir)
                except QuickCalibrationError:
                    pass  # still in use: the next run clears it or refuses; the original outcome is reported
                raise
            dataset = _load_state(cached)
        order = None if self.reference is None else self._node_order
        state = FEState(job_name, dataset if self.reference is None else None,
                        _tracking_state(job_name, dataset, order))
        if self.reference is not None:  # candidates keep only their small tracking state in memory
            self._cache[job_name] = state
        return state

    def _tracking_order(self) -> Optional[list]:
        return None if self.reference is None else list(self._node_order)

    def _requirements(self, digest: str) -> dict:
        order = self._tracking_order()
        return {"generated_inp_sha256": digest, "input_files": self._input_files, "fe_last_mode": self.last_mode,
                "solver": self.solver_identity.get("solver"), "extraction": self.solver_identity.get("extraction"),
                "node_set": None if order is None else _node_set(order, "SUBSET")}

    def _write_provenance(self, job_dir: Path, job_name: str, required: Mapping, nodes: Optional[list]) -> None:
        """The completion marker, written atomically only after a complete solve, extraction and data write."""
        data = _file_fingerprint(job_dir / "fe_modes.npz")
        stored = _load_state(job_dir / "fe_modes.npz")
        modes = stored.sorted_modes()
        record = {"schema": CACHE_SCHEMA, "job_name": job_name,
                  "generated_inp_sha256": required["generated_inp_sha256"], "input_files": required["input_files"],
                  "fe_last_mode": required["fe_last_mode"], "solver": required["solver"],
                  "extraction": required["extraction"],
                  "node_set": _node_set(modes[0].node_ids, "ALL" if nodes is None else "SUBSET"),
                  "completion": {"solve": "COMPLETED", "extraction": "VALID",
                                 "solver_version": _solver_version(job_dir, job_name),
                                 "mode_numbers": [m.number for m in modes]},
                  "data": {"file": "fe_modes.npz", "sha256": data["sha256"], "size": data["size"]}}
        record["record_hash"] = _canonical_hash(record)
        _write_json_atomically(job_dir / PROVENANCE_FILE, record)

    def _decide(self, decision: str, job_name: str, reason: str, prints: Mapping) -> None:
        self.cache_decisions.append({"job_name": job_name, "decision": decision, "stage": self.stage,
                                     "reason": reason, "fingerprints": dict(prints)})

    def _refuse_unconfirmed(self, job_dir: Path) -> None:
        if not (job_dir / UNCONFIRMED_MARKER).exists():
            return
        gone, remaining = _unconfirmed_processes_gone(job_dir, self.process_state)
        if not gone:
            raise QuickCalibrationError(
                f"{job_dir}: an earlier stop of this job's Abaqus processes was not confirmed ({remaining}); the job "
                "is neither reused, deleted nor overwritten. Check Task Manager, then delete the folder manually.")

    def _clear_job(self, job_dir: Path) -> None:
        """Remove an unverified job folder; refused while an unconfirmed stop may still use it."""
        self._refuse_unconfirmed(job_dir)
        if not job_dir.exists():
            return
        try:
            shutil.rmtree(job_dir)
        except OSError as error:
            raise QuickCalibrationError(f"{job_dir} holds an unverified Abaqus job that cannot be removed ({error}); "
                                        "a process may still use it. Nothing was reused.") from None

    def _claim_new_solve(self) -> None:
        """Count one new FE solve attempt, or refuse it when the per-run cap is reached (failures count too)."""
        if self.new_solve_attempts >= self.config.max_new_fe_solves:
            raise FESolveBudgetExhausted(self.config.max_new_fe_solves, self.new_solve_attempts, self.abaqus_solves,
                                         self.stage)
        self.new_solve_attempts += 1
        self.solve_stages.append(self.stage)

    def budget_report(self) -> dict:
        return {"max_new_fe_solves": self.config.max_new_fe_solves, "attempted_new_solves": self.new_solve_attempts,
                "completed_new_solves": self.abaqus_solves, "reused_finished_jobs": self.cache_hits,
                "attempts_by_stage": {stage: self.solve_stages.count(stage) for stage in dict.fromkeys(
                    self.solve_stages)}}

    def _check_cancel(self) -> None:
        if self.cancel.is_set():
            raise CalibrationCancelled("stopped by the user; no Abaqus process was running.")

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
        """The calibration; a reached FE solve cap ends it as an explicit BUDGET_EXHAUSTED refusal (no value)."""
        self._base: Optional[dict] = None
        try:
            return self._workflow()
        except FESolveBudgetExhausted as exhausted:
            return self._budget_refused(exhausted)

    def _workflow(self) -> dict:
        config = self.config
        names = [p.name for p in config.parameters]
        start = {name: 1.0 for name in names}
        self.progress("reading the experiment")
        experiment = load_experiment(config)
        peak_modes = [m.number for m in experiment.sorted_modes() if _is_peak_derived(m)]

        self.stage = "baseline"
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
        self._base = base
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
        self.stage = "optimiser"
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
            self.stage = "final evaluation"
            final = self.evaluate(p_hat)
            self.stage = "sensitivities"
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
                      abaqus_solves=self.abaqus_solves, fe_solve_budget=self.budget_report(),
                      fe_job_cache=list(self.cache_decisions),
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
                    abaqus_solves=self.abaqus_solves, fe_solve_budget=self.budget_report(),
                    fe_job_cache=list(self.cache_decisions),
                    evaluations=[asdict(e) for e in self.evaluations], rows=[asdict(r) for r in self.rows])

    def _budget_refused(self, exhausted: FESolveBudgetExhausted) -> dict:
        """BUDGET_EXHAUSTED: the evidence is incomplete, so no optimiser point or calibrated value is published."""
        base = dict(self._base) if self._base is not None else {
            "schema": SCHEMA, "label": LABEL, "claim": NOT_A_MATERIAL_PROPERTY, "inputs": self._inputs(),
            "parameters": [asdict(p) for p in self.config.parameters], "sigma_ln": SIGMA_LN}
        if "lm" in base:  # the optimiser's point is not a value: withheld, only its progress is kept
            base["lm"] = {key: base["lm"][key] for key in ("status", "iterations", "evaluations")}
        result = self._refused(base, str(exhausted))
        result.update(refusal_code=BUDGET_EXHAUSTED, budget_exhausted_stage=exhausted.stage, diagnostic_candidate=None,
                      evaluations=[{"job_name": e.job_name} for e in self.evaluations],
                      rows=[asdict(r) for r in self.rows])
        return result

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


def _mark_unconfirmed(job_dir: Path, error: TerminationUnconfirmed) -> None:
    """Record, inside the job, which processes may still run (``None``: unknown); nothing else is touched."""
    remaining = error.still_running()
    processes = None if remaining is None else [
        {"pid": identity.pid, "created": None if identity.created is None else list(identity.created)}
        for identity in remaining]
    try:
        _write_json_atomically(Path(job_dir) / UNCONFIRMED_MARKER, {"reason": str(error), "processes": processes})
    except OSError:
        pass  # the job keeps no provenance record either way: it is never reused


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
    calibrated = out / f"{Path(config.model_inp).stem}_calibrated.inp"
    if result.get("status") != STATUS_ESTIMATE and calibrated.is_file():
        calibrated.unlink()  # a calibrated INP of an earlier run never stands beside a refusal
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
        code = f" ({result['refusal_code']})" if result.get("refusal_code") else ""
        lines += [f"RESULT: NO VALUE{code}", *[f"  reason: {r}" for r in result["refusal_reasons"]]]
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
    decisions = result.get("fe_job_cache") or []
    if decisions:
        lines += ["", "FE JOB CACHE (reuse only with verified provenance)"]
        for item in decisions:
            prints = ", ".join(f"{k} {v}" for k, v in (item.get("fingerprints") or {}).items())
            lines.append(f"  {item['decision']:<14} {item['job_name']} [{item['stage']}]: {item['reason']}"
                         + (f" ({prints})" if prints else ""))
    budget = result.get("fe_solve_budget") or {}
    lines += ["", f"New Abaqus FE solves in this run: {budget.get('attempted_new_solves')} attempted, "
                  f"{budget.get('completed_new_solves')} completed, limit {budget.get('max_new_fe_solves')} "
                  f"(finished jobs reused: {budget.get('reused_finished_jobs')})",
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
                          progress: Optional[ProgressFunction] = None,
                          cancel: Optional[threading.Event] = None,
                          runner: Optional[AbaqusRunner] = None,
                          solver_identity: Optional[Mapping] = None) -> tuple[dict, dict[str, Path]]:
    """Run the calibration and write result.json, report.txt, modes.csv (and the calibrated INP).

    The input preflight runs first; any refusal raises ``PreflightRefused`` before an Abaqus solve. ``cancel``
    stops the run: ``CalibrationCancelled`` after the owned processes are confirmed terminated, otherwise
    ``TerminationUnconfirmed``; nothing is written as a result and no partial job is reused.
    """
    cancel = cancel if cancel is not None else threading.Event()

    report = preflight(config)
    if not report.ready:
        raise PreflightRefused(report)
    config = replace(config, modal_set=None if report.modal_set is None else report.modal_set.key)
    if solve is None or extract is None:
        runner = runner or AbaqusRunner(config.abaqus_command, config.cpus, config.timeout_minutes, cancel)
        solve = solve or runner.solve
        extract = extract or runner.extract
    if solver_identity is None:  # the identity of the solver actually used (AbaqusRunner or an injected one)
        owner = runner if runner is not None else getattr(solve, "__self__", None)
        identify = getattr(owner, "identity", None)
        solver_identity = identify() if callable(identify) else None
    calibration = QuickCalibration(config, solve, extract, progress, cancel, solver_identity)
    result = calibration.run()
    result["preflight"] = report.to_dict()
    paths = write_outputs(result, config, calibration.model)
    return result, paths

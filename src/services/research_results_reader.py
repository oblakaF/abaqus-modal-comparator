"""PRIORITY-5A: read the archived PRIORITY-1–4 research results for the new interface (no Qt; RESEARCH_ONLY).

The results are archived research snapshots in the repository (``docs/research/...``). Each file is read only when its
SHA-256 is the one recorded here; a changed or damaged file refuses the whole snapshot with the reason, and nothing
is recomputed except the rank / condition of the published central-sensitivity table (an SVD of the numbers shown).
Statuses are shown exactly as published (CANDIDATE_ONLY, AMBIGUOUS_CLUSTER, NO_MATCH, FE_SHAPES_UNAVAILABLE); no
nearest FE frequency becomes a pair, and no research or hypothetical MAC is a confirmed MAC.

The optional local research record (``matching_record.json``) is read only when the user chooses it: its structure,
the matrix sizes, the mode numbers, the finiteness and the 0–1 range of every value and the SHA-256 of the
experimental sources are checked; any mismatch refuses the matrices (never replaced by other numbers).

Linking to the Workspace: the archived tables belong to the inputs of the research only. They are called verified
for the current Workspace inputs only when the experimental file read in the Workspace has the series' SHA-256 (and
the FE package's manifest has the research FE manifest's SHA-256, where one exists); otherwise the page says
ARCHIVED RESEARCH SNAPSHOT — NOT VERIFIED FOR CURRENT WORKSPACE INPUTS. Nothing is searched on any disk; no Abaqus,
solver, LM or Auto-ID is started.

Labels: RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY. M8 GATE NOT_MET, D-077
NO_GLOBAL_PARAMETER_VALUE, production Auto-ID BLOCKED and 261027 PHYSICAL_REGISTRATION_NOT_VERIFIED are unchanged.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
import hashlib
import io
import json
import math
from pathlib import Path
from typing import Optional

import numpy as np

REPO = Path(__file__).resolve().parents[2]
LABELS = ("RESEARCH_ONLY", "HYPOTHETICAL_PAIRING", "NOT_A_MATERIAL_PROPERTY")
NOT_VERIFIED_BANNER = "ARCHIVED RESEARCH SNAPSHOT — NOT VERIFIED FOR CURRENT WORKSPACE INPUTS"
VERIFIED_BANNER = "ARCHIVED RESEARCH SNAPSHOT — the Workspace inputs have the research inputs' SHA-256"
STATUSES = ("MATCH_CONFIRMED", "CANDIDATE_ONLY", "AMBIGUOUS_CLUSTER", "NO_MATCH", "FE_SHAPES_UNAVAILABLE")
MAX_RECORD_BYTES = 20 * 1024 * 1024
RCOND = 1e-3

# (published path, SHA-256 of the committed content with LF line ends, research commit) of every archived file: a
# Windows checkout writes CRLF, so the content is hashed with CRLF read as LF (the same digest on every platform)
SNAPSHOT_FILES = {
    "PLATE_MATCHING": ("docs/research/real_modal_matching_202610/PLATE_MODAL_MATCHING.csv",
                       "c9b1ea6e3c77d41b1ed91cb23ad45167e92253fdab20350036e66cd2c04f906e", "1dd29d5"),
    "SP13_MATCHING": ("docs/research/real_modal_matching_202610/SP13_MODAL_MATCHING.csv",
                      "b82dc6314df77b2dd18cf4ded8a162dbce310f0aec93b78b92ab10829ca50919", "1dd29d5"),
    "SP10_MATCHING": ("docs/research/real_modal_matching_202610/SP10_MODAL_MATCHING.csv",
                      "037c95a37ae6acac2e4451ad05056524cd2e6f0428011d65ba63364fc35690cc", "1dd29d5"),
    "SENSITIVITIES": ("docs/research/plate_s4_central/CENTRAL_SENSITIVITIES.csv",
                      "5cba4070ee7beb1e55b0ef61e95d33c115acc68e0be90a6c43d960d5687c7c4e", "e42649a"),
    "SCENARIOS": ("docs/research/plate_inverse_r1/PLATE_INVERSE_SCENARIOS.csv",
                  "8848bb9c0bd0eaee516d5bb196a8cf08d30b7bd6eb97328cafb9144fe6a01a4f", "77a57ae"),
    "FE_VS_LM": ("docs/research/plate_inverse_fe_r1/REAL_FE_VS_LM.csv",
                 "c1982d8178edc96ae65597f17fb2455bbcb38af5df30dd4a493ae41001a260fa", "f19fc93"),
    "FE_VS_EXPERIMENT": ("docs/research/plate_inverse_fe_r1/REAL_FE_VS_EXPERIMENT.csv",
                         "b75a85aa39f17b2105d5b045655754c16d50be45c79d5dae4e1d241faab18769", "f19fc93"),
    "FE_TRACKING": ("docs/research/plate_inverse_fe_r1/REAL_FE_BRANCH_TRACKING.csv",
                    "ef9c268db936b8e5f4b313c0f9c4460060394451085ebf3fbd452fb1e3c85559", "f19fc93"),
}


@dataclass(frozen=True)
class Specimen:
    key: str
    title: str
    series: str
    matching: str  # SNAPSHOT_FILES key
    modes: int
    experiment_sha256: str
    fe_manifest_sha256: Optional[str]
    mac_key: Optional[str]  # key of the matrix in the local record
    mac_basis: str


SPECIMENS = {
    "PLATE": Specimen("PLATE", "PLATE-300x300x1mm — 261027, 11 modes", "NEXP29/PLATE300-1MM/S261027-ROTATED",
                      "PLATE_MATCHING", 11, "76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d",
                      "354966dae2126d11610b9fdb56804006b56b40aea1cf7a180278ef375893b4c7", "plate_research_mac",
                      "RESEARCH MAC on the 261016 diagnostic reconstruction, carried by the DERIVED point map id k ↔ "
                      "id k — NOT a physical registration (261027 PHYSICAL_REGISTRATION_NOT_VERIFIED)"),
    "SP-13": Specimen("SP-13", "SP-13 — 261028, 12 modes", "NEXP29/SP-13/S261028-ROTATED", "SP13_MATCHING", 12,
                      "8abf951dba4b8a942922cb4af96074fc1ce8fce2a3f0de8ce082bc5820eeda10",
                      "91c360b4f603b3261bc5306051dbd15807996af4c40764168f69ceafbc285038", "sp13_hypothetical_mac",
                      "HYPOTHETICAL_SAME_POINTS: the SP-13 frozen registration of session 260910 a applied to 261028 "
                      "by point id — the same points are NOT confirmed for SP-13"),
    "SP-10": Specimen("SP-10", "SP-10 — 261029, 12 modes", "NEXP29/SP-10/S261029-ROTATED", "SP10_MATCHING", 12,
                      "432adf963085b012b07a6b235e1dde3c4df83ea87b85326497df0a89a9eeef1f", None, None,
                      "MAC NOT_AVAILABLE — FE shapes not extracted (no extracted SP-10 FE package)"),
}
MATCHING_COLUMNS = ("specimen", "series", "exp_no", "f_exp_hz", "fe_candidates", "nearest_fe", "f_fe_hz",
                    "df_percent", "mac_admissible", "research_mac", "shape", "cluster_or_permutation", "status",
                    "reason")


class SnapshotRefused(ValueError):
    """An archived research file is missing, changed or not of the published form; the reason is shown."""


class RecordRefused(ValueError):
    """The chosen local research record is not usable; its matrices are not shown."""


@dataclass(frozen=True)
class MatchingRow:
    exp_no: int
    f_exp_hz: float
    fe_candidates: str
    nearest_fe: str
    f_fe_hz: str
    df_percent: str
    research_mac: str
    cluster: str
    status: str
    reason: str
    mac_admissible: str

    @property
    def ambiguous(self) -> bool:
        return self.status == "AMBIGUOUS_CLUSTER" or self.cluster not in ("", "—")


@dataclass(frozen=True)
class SensitivityRow:
    term: str
    f0_hz: float
    s: dict  # E1 / E2 / G12 → float or None (a branch that lost identity has no central value)
    s_e: Optional[float]
    cluster: str
    tracking: str


@dataclass(frozen=True)
class Scenario:
    key: str
    pairs: str
    fitted: str
    status: str
    E1: float
    E2: float
    G12: float
    ratios: str
    beyond_linear_range: str
    rank: str
    note: str
    labels: str


@dataclass
class Snapshot:
    files: dict  # key → (path, sha256, commit)
    matching: dict  # specimen → [MatchingRow]
    sensitivities: list
    rank_full: dict
    rank_restricted: dict
    scenarios: list
    fe_vs_lm: list  # dict rows
    fe_vs_experiment: list
    tracking: list
    labels: tuple = LABELS
    notes: list = field(default_factory=list)


def _read(key: str, root: Path) -> list:
    relative, expected, _commit = SNAPSHOT_FILES[key]
    path = root / relative
    if not path.is_file():
        raise SnapshotRefused(f"{relative} is missing")
    data = path.read_bytes().replace(b"\r\n", b"\n")  # the committed (LF) form, whatever the checkout wrote
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise SnapshotRefused(f"{relative}: SHA-256 {digest[:12]}… is not the archived {expected[:12]}… — the file "
                              "changed, so the snapshot is not shown")
    try:
        return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))
    except (UnicodeDecodeError, csv.Error) as error:
        raise SnapshotRefused(f"{relative} cannot be read: {error}") from error


def _float(value, what):
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise SnapshotRefused(f"{what}: {value!r} is not a number") from None
    if not math.isfinite(number):
        raise SnapshotRefused(f"{what}: {value!r} is not finite")
    return number


def _svd(S: np.ndarray, names) -> dict:
    sv = np.linalg.svd(S, compute_uv=False)
    return {"parameters": list(names), "rank": int(np.sum(sv > RCOND * sv[0])), "condition": float(sv[0] / sv[-1]),
            "singular_values": [float(v) for v in sv], "terms": int(S.shape[0])}


def load_snapshot(root: Path = REPO) -> Snapshot:
    matching = {}
    for spec in SPECIMENS.values():
        rows = _read(spec.matching, root)
        if not rows or tuple(rows[0].keys()) != MATCHING_COLUMNS:
            raise SnapshotRefused(f"{SNAPSHOT_FILES[spec.matching][0]}: unexpected columns")
        if len(rows) != spec.modes:
            raise SnapshotRefused(f"{spec.key}: {len(rows)} rows, the series has {spec.modes} modes")
        out = []
        for r in rows:
            if r["status"] not in STATUSES:
                raise SnapshotRefused(f"{spec.key} EXP{r['exp_no']}: unknown status {r['status']!r}")
            if r["series"] != spec.series:
                raise SnapshotRefused(f"{spec.key}: series {r['series']!r} is not {spec.series!r}")
            out.append(MatchingRow(int(r["exp_no"]), _float(r["f_exp_hz"], "f_exp"), r["fe_candidates"],
                                   r["nearest_fe"], r["f_fe_hz"], r["df_percent"], r["research_mac"],
                                   r["cluster_or_permutation"], r["status"], r["reason"], r["mac_admissible"]))
        if [r.exp_no for r in out] != list(range(1, spec.modes + 1)):
            raise SnapshotRefused(f"{spec.key}: the experimental mode numbers are not 1–{spec.modes}")
        matching[spec.key] = out
    sens = []
    for r in _read("SENSITIVITIES", root):
        values = {p: (None if r[f"s_{p}"] in ("", None) else _float(r[f"s_{p}"], f"{r['term']} s_{p}"))
                  for p in ("E1", "E2", "G12")}
        tracking = "; ".join(f"{p}: {r[f'lin_{p}']}" for p in ("E1", "E2", "G12") if r[f"lin_{p}"] == "NOT_TRACKED")
        sens.append(SensitivityRow(r["term"], _float(r["f_baseline_hz"], r["term"]), values,
                                   None if r["s_E (E1=E2)"] in ("", None) else _float(r["s_E (E1=E2)"], r["term"]),
                                   r["cluster"], tracking or "tracked in all six ±5 % variants"))
    full = [x for x in sens if None not in x.s.values()]
    S3 = np.array([[x.s["E1"], x.s["E2"], x.s["G12"]] for x in full])
    rank_full = _svd(S3, ("E1", "E2", "G12"))
    rank_restricted = _svd(np.column_stack([S3[:, 0] + S3[:, 1], S3[:, 2]]), ("E (E1 = E2)", "G12"))
    scenarios = []
    for r in _read("SCENARIOS", root):
        scenarios.append(Scenario(r["scenario"], r["pairs"], r["fitted"], r["status"],
                                  _float(r["E1_MPa"], "E1"), _float(r["E2_MPa"], "E2"), _float(r["G12_MPa"], "G12"),
                                  r["ratios"], r["beyond_linear_range"], r["rank_E1_E2_G12"], r["note"], r["labels"]))
    if [s.key for s in scenarios] != ["S0", "H1", "H2"]:
        raise SnapshotRefused("the inverse scenarios are not S0, H1, H2")
    fe_vs_lm = _read("FE_VS_LM", root)
    fe_vs_exp = _read("FE_VS_EXPERIMENT", root)
    tracking = _read("FE_TRACKING", root)
    return Snapshot({k: v for k, v in SNAPSHOT_FILES.items()}, matching, sens, rank_full, rank_restricted, scenarios,
                    fe_vs_lm, fe_vs_exp, tracking)


def scenario_detail(snapshot: Snapshot, key: str) -> dict:
    """Rows of one scenario: every tracked FE branch (base, LM prediction, real Abaqus, δ, FE-to-FE MAC, status),
    the declared hypotheses and the diagnostic nearest-frequency residuals (never pairs)."""
    track = {(r["state"], r["branch"]): r for r in snapshot.tracking}
    branches = []
    for r in snapshot.fe_vs_lm:
        if r["state"] != key:
            continue
        term = r["fe_branch"]
        members = term.split("+")
        macs = [track.get((key, m), {}).get("fe_fe_mac_or_cos2", "") for m in members]
        statuses = {track.get((key, m), {}).get("status", "—") for m in members}
        status = ("geometric mean of the tracked FE15 and FE16 — a computed subspace value, not one mode"
                  if len(members) > 1 else "/".join(sorted(statuses)))
        perm = any(track.get((key, m), {}).get("permutation") for m in members)
        branches.append({"term": term, "f_baseline_hz": r["f_baseline_hz"], "f_lm_hz": r["f_lm_hz"],
                         "f_abaqus_hz": r["f_abaqus_hz"], "surrogate_error_percent": r["surrogate_error_percent"],
                         "fe_fe_mac": " / ".join(m for m in macs if m) or "—",
                         "status": status + (" (order changed)" if perm else "")})
    declared = [r for r in snapshot.fe_vs_experiment if r["state"] == key and r["kind"] == "DECLARED_HYPOTHESIS"]
    diagnostic = [r for r in snapshot.fe_vs_experiment if r["state"] == key and r["kind"] != "DECLARED_HYPOTHESIS"]
    return {"branches": branches, "declared": declared, "diagnostic": diagnostic,
            "scenario": next(s for s in snapshot.scenarios if s.key == key)}


# ----------------------------------------------------------------------------- the optional local research record

@dataclass(frozen=True)
class MacMatrix:
    specimen: str
    basis: str
    experimental: tuple  # (number, hz)
    fe_modes: tuple
    values: tuple  # rows of floats


@dataclass(frozen=True)
class LocalRecord:
    path: Path
    sha256: str
    matrices: dict  # specimen → MacMatrix
    checks: tuple


def load_local_record(path) -> LocalRecord:
    path = Path(path)
    if not path.is_file():
        raise RecordRefused(f"{path} is missing")
    if path.stat().st_size > MAX_RECORD_BYTES:
        raise RecordRefused(f"{path.name} is larger than {MAX_RECORD_BYTES // (1024 * 1024)} MB: not a research record")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    try:
        record = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise RecordRefused(f"{path.name} is not valid JSON: {error}") from error
    if not isinstance(record, dict) or not isinstance(record.get("experimental"), dict):
        raise RecordRefused(f"{path.name} is not a research matching record (no 'experimental' section)")
    checks = []
    for key, spec in SPECIMENS.items():
        source_key = {"PLATE": "PLATE", "SP-13": "SP13", "SP-10": "SP10"}[key]
        entry = record["experimental"].get(source_key)
        if not isinstance(entry, dict) or entry.get("sha256") != spec.experiment_sha256:
            raise RecordRefused(f"{key}: the record's experimental source SHA-256 "
                                f"{str((entry or {}).get('sha256'))[:12]}… is not the series' "
                                f"{spec.experiment_sha256[:12]}…")
        checks.append(f"{key}: experimental source SHA-256 {spec.experiment_sha256[:12]}… matches")
    matrices = {}
    for key, spec in SPECIMENS.items():
        if spec.mac_key is None:
            continue
        block = record.get(spec.mac_key)
        if not isinstance(block, dict):
            raise RecordRefused(f"{key}: the record has no '{spec.mac_key}' section")
        matrix, fe_modes = block.get("matrix"), block.get("fe_modes")
        frequencies = record["experimental"][{"PLATE": "PLATE", "SP-13": "SP13"}[key]].get("frequencies_hz")
        if not (isinstance(matrix, list) and isinstance(fe_modes, list) and isinstance(frequencies, list)):
            raise RecordRefused(f"{key}: matrix, FE mode list or experimental frequencies missing")
        if len(frequencies) != spec.modes or len(matrix) != spec.modes:
            raise RecordRefused(f"{key}: {len(matrix)} matrix rows for {spec.modes} experimental modes")
        if (not fe_modes or not all(isinstance(m, int) and m > 0 for m in fe_modes)
                or len(set(fe_modes)) != len(fe_modes)):
            raise RecordRefused(f"{key}: the FE mode numbers are not unique positive integers")
        rows = []
        for i, row in enumerate(matrix):
            if not isinstance(row, list) or len(row) != len(fe_modes):
                raise RecordRefused(f"{key}: row {i + 1} has not {len(fe_modes)} values")
            values = []
            for value in row:
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise RecordRefused(f"{key}: row {i + 1} holds a non-finite or non-numeric value")
                if not -1e-9 <= value <= 1 + 1e-9:
                    raise RecordRefused(f"{key}: row {i + 1} holds {value}, outside 0–1")
                values.append(float(value))
            rows.append(tuple(values))
        if not all(isinstance(f, (int, float)) and math.isfinite(f) and f > 0 for f in frequencies):
            raise RecordRefused(f"{key}: the experimental frequencies are not finite and positive")
        matrices[key] = MacMatrix(key, spec.mac_basis, tuple((k + 1, float(f)) for k, f in enumerate(frequencies)),
                                  tuple(fe_modes), tuple(rows))
        checks.append(f"{key}: {spec.modes} × {len(fe_modes)} matrix, values finite in 0–1")
    return LocalRecord(path, digest, matrices, tuple(checks))


# ----------------------------------------------------------------------------- the Workspace link

def workspace_link(specimen: str, experimental_identity, fe_identity) -> tuple:
    """(verified, text) — the snapshot is tied to the Workspace inputs only by their SHA-256.

    Both identities are needed: a specimen without a research FE package (SP-10) is never verified, even when the
    experimental file matches, because its FE identity cannot be confirmed.
    """
    spec = SPECIMENS[specimen]
    exp_sha = (experimental_identity or {}).get("sha256")
    fe_sha = (fe_identity or {}).get("sha256")
    reasons = []
    if exp_sha != spec.experiment_sha256:
        reasons.append("the experimental file read in the Workspace is " + (f"{exp_sha[:12]}…" if exp_sha else "none")
                       + f", not the series' {spec.experiment_sha256[:12]}…")
    elif not spec.fe_manifest_sha256:
        reasons.append(f"the experimental SHA-256 matches the series' {spec.experiment_sha256[:12]}…")
    if not spec.fe_manifest_sha256:
        reasons.append(f"the FE identity is not confirmed: {specimen} has no research FE package to compare with"
                       + (f" (the FE manifest read in the Workspace is {fe_sha[:12]}…)" if fe_sha else ""))
    elif fe_sha != spec.fe_manifest_sha256:
        reasons.append("the FE manifest read in the Workspace is " + (f"{fe_sha[:12]}…" if fe_sha else "none")
                       + f", not the research FE package's {spec.fe_manifest_sha256[:12]}…")
    if reasons:
        return False, NOT_VERIFIED_BANNER + ": " + "; ".join(reasons)
    return True, VERIFIED_BANNER


# ----------------------------------------------------------------------------- the current plate research snapshot
#
# PLATE-0875-CURRENT-RESEARCH-VIEW-01. The archived PRIORITY-1–4 plate tables above rest on scan-point positions that
# were found to be wrong along FE X (plate README §23). The results recomputed with the corrected, instrument-derived
# positions (§24–§26) are kept in one separate file. It is a display record: it is not registration evidence, not an
# identification input and not a pairing record, and nothing above reads it. It is shown only when its SHA-256 is the
# one recorded here AND its content is consistent with itself (every error, first-ranked mode and summary value is
# recomputed from the frequencies and matrices it holds); otherwise it is refused with the reason, never replaced.

PLATE_COMPARISON_FILE = ("docs/research/plate_only/plate_comparison_261027.json",
                         "dc2ac694322304890acd5c4de90548db20ffa5a875607d5fc87fd87235aa53e8")
PLATE_COMPARISON_SCHEMA = "research/plate-0875/comparison-snapshot/v1"
PLATE_COMPARISON_LABELS = ("RESEARCH_ONLY", "PHYSICAL_REGISTRATION_NOT_VERIFIED", "NOT_A_MATERIAL_PROPERTY",
                           "MODEL_FORM_HYPOTHESIS")
PLATE_MODELS = ("BASELINE", "THICKNESS_ONLY", "DIRECTIONAL_ONLY", "COMBINED")
PLATE_COMPARISON_SOURCES = ("results_24", "results_25", "results_26", "protocol_25", "protocol_26",
                            "corrected_reconstruction_27")
PLATE_FE_MODES = tuple(range(7, 21))
PLATE_MAC_LEVEL = 0.80  # the existing descriptive level of the research (never a pairing decision here)
PLATE_FREQUENCY_LEVEL = 5.0  # per cent; the existing descriptive level
HISTORICAL_PLATE_GEOMETRY = (
    "HISTORICAL — SUPERSEDED SCAN GEOMETRY. Computed with the 261016 diagnostic reconstruction W301xH300, whose "
    "scan window is 215.4 mm wide instead of 287.1 mm (a unit-conversion error, plate README §23): the point "
    "positions are wrong along FE X by up to 49.3 mm. Kept unchanged as the archived record; not a current result.")


class PlateComparisonRefused(ValueError):
    """The current plate research snapshot is missing, changed or inconsistent; it is not shown."""


@dataclass(frozen=True)
class PlateRecord:
    exp: int
    f_exp_hz: float
    corresponding_fe: int
    corresponding_hz: float
    frequency_error_pct: float
    mac_corresponding: float
    first_fe: int
    mac_first: float
    mac_range: tuple
    first_unchanged: str


@dataclass(frozen=True)
class PlateModel:
    key: str
    title: str
    origin: str
    readme: str
    inputs: dict
    identity: dict
    fe_hz: tuple
    records: tuple  # PlateRecord
    mac: tuple  # 11 rows × 14 values
    summary: dict


@dataclass(frozen=True)
class PlateComparison:
    path: str
    sha256: str
    labels: tuple
    status: dict
    specimen: dict
    geometry: dict
    exp_hz: tuple
    fe_modes: tuple
    correspondence: str
    models: dict  # key → PlateModel, in PLATE_MODELS order
    tracking: dict
    criteria: dict
    unresolved_records: tuple
    limitations: tuple
    sources: tuple
    documented_in: str


def _need(condition: bool, reason: str) -> None:
    if not condition:
        raise PlateComparisonRefused(reason)


def _number(value, what: str, low: Optional[float] = None, high: Optional[float] = None) -> float:
    _need(not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value),
          f"{what}: {value!r} is not a finite number")
    _need(low is None or value >= low, f"{what}: {value} is below {low}")
    _need(high is None or value <= high, f"{what}: {value} is above {high}")
    return float(value)


def _close(a: float, b: float, tolerance: float) -> bool:
    return abs(a - b) <= tolerance


def validate_plate_comparison(document, path: str = PLATE_COMPARISON_FILE[0], sha256: str = "") -> PlateComparison:
    """Check the structure and the internal consistency of a snapshot document; refuse with the reason."""
    _need(isinstance(document, dict), "the snapshot is not a JSON object")
    _need(document.get("schema") == PLATE_COMPARISON_SCHEMA, f"schema {document.get('schema')!r} is not "
                                                             f"{PLATE_COMPARISON_SCHEMA!r}")
    labels = document.get("labels")
    _need(isinstance(labels, list) and all(x in labels for x in PLATE_COMPARISON_LABELS),
          "the research labels " + " / ".join(PLATE_COMPARISON_LABELS) + " are not all present")
    status = document.get("status")
    _need(isinstance(status, dict) and "not registration evidence" in str(status.get("use"))
          and "not an identification input" in str(status.get("use")),
          "the snapshot does not state that it is neither registration evidence nor an identification input")
    _need(isinstance(status.get("gates"), list) and {"M8 GATE NOT_MET", "D-077 NO_GLOBAL_PARAMETER_VALUE",
                                                      "production Auto-ID BLOCKED"} <= set(status["gates"]),
          "the unchanged scientific gates are not stated")
    specimen = document.get("specimen")
    plate = SPECIMENS["PLATE"]
    _need(isinstance(specimen, dict) and specimen.get("key") == "PLATE" and specimen.get("series") == plate.series,
          "the snapshot is not of the series " + plate.series)
    _need(specimen.get("experiment_sha256") == plate.experiment_sha256,
          f"experimental source SHA-256 {str(specimen.get('experiment_sha256'))[:12]}… is not the series' "
          f"{plate.experiment_sha256[:12]}…")
    exp = (document.get("experiment") or {}).get("hz") if isinstance(document.get("experiment"), dict) else None
    _need(isinstance(exp, list) and len(exp) == plate.modes, f"the snapshot has not {plate.modes} experimental records")
    exp_hz = tuple(_number(f, f"EXP{i + 1} frequency", 1e-9) for i, f in enumerate(exp))
    _need(list(exp_hz) == sorted(exp_hz), "the experimental frequencies are not ascending")
    _need(document.get("fe_modes") == list(PLATE_FE_MODES), "the FE modes are not FE7–FE20")
    geometry = document.get("geometry")
    _need(isinstance(geometry, dict) and geometry.get("basis") == "CORRECTED_261016"
          and geometry.get("pixel_normalisation") == "instrument-metadata",
          "the scan geometry is not the corrected instrument-metadata reconstruction of session 261016")
    for key in ("window_mm", "plate_plan_mm"):
        _need(isinstance(geometry.get(key), list) and len(geometry[key]) == 2, f"geometry {key} is not two numbers")
    window = [_number(v, "scan window", 1e-9) for v in geometry["window_mm"]]
    plan = [_number(v, "plate plan", 1e-9) for v in geometry["plate_plan_mm"]]
    gaps = geometry.get("gaps_mm_left_right_bottom_top")
    _need(isinstance(gaps, list) and len(gaps) == 4, "the four gaps between the scan window and the plate edges are missing")
    gaps = [_number(v, "gap to the plate edge", 0.0) for v in gaps]
    _need(_close(gaps[0] + window[0] + gaps[1], plan[0], 1e-3) and _close(gaps[2] + window[1] + gaps[3], plan[1], 1e-3),
          "the scan window and its gaps do not add up to the plate plan")
    _need("CONDITIONAL" in str(geometry.get("transfer_261016_to_261027")),
          "the conditional transfer of the 261016 positions to 261027 is not stated")
    superseded = geometry.get("superseded")
    _need(isinstance(superseded, dict) and isinstance(superseded.get("window_mm"), list)
          and len(superseded["window_mm"]) == 2, "the superseded geometry is not named")
    _need(_number(superseded["window_mm"][0], "superseded window", 1e-9) < window[0],
          "the superseded window is not narrower than the corrected one")
    raw_models = document.get("models")
    _need(isinstance(raw_models, list) and [m.get("key") if isinstance(m, dict) else None for m in raw_models]
          == list(PLATE_MODELS), "the models are not " + ", ".join(PLATE_MODELS))
    models = {}
    for raw in raw_models:
        name = raw["key"]
        inputs, identity = raw.get("inputs"), raw.get("identity")
        _need(isinstance(inputs, dict) and isinstance(identity, dict), f"{name}: FE inputs or identity missing")
        for key in ("E1_MPa", "E2_MPa", "G12_MPa", "nu12", "density_t_per_mm3", "mass_g"):
            _number(inputs.get(key), f"{name} {key}", 1e-12)
        ends = inputs.get("thickness_mm_at_x0_x301")
        _need(isinstance(ends, list) and len(ends) == 2 and isinstance(inputs.get("thickness"), str),
              f"{name}: thickness not stated")
        [_number(v, f"{name} thickness", 1e-9) for v in ends]
        _need(isinstance(identity.get("inp_sha256"), str) and len(identity["inp_sha256"]) == 64,
              f"{name}: the FE input has no SHA-256")
        fe = raw.get("fe_hz")
        _need(isinstance(fe, list) and len(fe) == len(PLATE_FE_MODES), f"{name}: not 14 FE frequencies")
        fe_hz = tuple(_number(f, f"{name} FE frequency", 1e-9) for f in fe)
        _need(list(fe_hz) == sorted(fe_hz), f"{name}: the FE frequencies are not ascending")
        matrix = raw.get("mac")
        _need(isinstance(matrix, list) and len(matrix) == plate.modes, f"{name}: the MAC matrix has not 11 rows")
        mac = []
        for i, row in enumerate(matrix):
            _need(isinstance(row, list) and len(row) == len(PLATE_FE_MODES), f"{name}: MAC row {i + 1} has not 14 values")
            mac.append(tuple(_number(v, f"{name} MAC row {i + 1}", -1e-9, 1 + 1e-9) for v in row))
        rows = raw.get("records")
        _need(isinstance(rows, list) and len(rows) == plate.modes and all(isinstance(r, dict) for r in rows)
              and [r.get("exp") for r in rows] == list(range(1, plate.modes + 1)),
              f"{name}: the records are not EXP1–EXP{plate.modes}")
        records = []
        for i, r in enumerate(rows):
            what = f"{name} EXP{i + 1}"
            _need(r.get("corresponding_fe") in PLATE_FE_MODES and r.get("first_fe") in PLATE_FE_MODES,
                  f"{what}: FE mode outside FE7–FE20")
            jc, j1 = r["corresponding_fe"] - PLATE_FE_MODES[0], r["first_fe"] - PLATE_FE_MODES[0]
            hz = _number(r.get("corresponding_hz"), f"{what} FE frequency", 1e-9)
            _need(_close(hz, fe_hz[jc], 1e-9), f"{what}: the FE frequency is not that of FE{r['corresponding_fe']}")
            error = _number(r.get("frequency_error_pct"), f"{what} frequency error")
            _need(_close(error, 100.0 * (hz / exp_hz[i] - 1.0), 1e-5),
                  f"{what}: the frequency error {error} does not follow from the two frequencies")
            mac_c = _number(r.get("mac_corresponding"), f"{what} MAC", -1e-9, 1 + 1e-9)
            mac_1 = _number(r.get("mac_first"), f"{what} MAC", -1e-9, 1 + 1e-9)
            _need(_close(mac_c, mac[i][jc], 1e-9), f"{what}: the MAC of the corresponding mode is not the matrix value")
            _need(_close(mac_1, max(mac[i]), 1e-9) and _close(mac[i][j1], max(mac[i]), 1e-9),
                  f"{what}: FE{r['first_fe']} is not the first-ranked mode of the matrix row")
            span = r.get("mac_first_range_declared_scenarios")
            _need(isinstance(span, list) and len(span) == 2, f"{what}: scenario range missing")
            span = tuple(_number(v, f"{what} scenario range", -1e-9, 1 + 1e-9) for v in span)
            _need(span[0] <= span[1], f"{what}: scenario range reversed")
            records.append(PlateRecord(i + 1, exp_hz[i], r["corresponding_fe"], hz, error, mac_c, r["first_fe"], mac_1,
                                       span, str(r.get("first_unchanged_in_scenarios", ""))))
        summary = raw.get("summary")
        _need(isinstance(summary, dict), f"{name}: summary missing")
        errors = [abs(r.frequency_error_pct) for r in records]
        expected = {
            "records_mac_ge_0_80": [r.exp for r in records if r.mac_first >= PLATE_MAC_LEVEL],
            "records_mac_below_0_80": [r.exp for r in records if r.mac_first < PLATE_MAC_LEVEL],
            "records_outside_5_pct": [r.exp for r, e in zip(records, errors) if e > PLATE_FREQUENCY_LEVEL],
            "first_ranked_is_corresponding": sum(r.first_fe == r.corresponding_fe for r in records)}
        for key, value in expected.items():
            _need(summary.get(key) == value, f"{name}: summary {key} {summary.get(key)!r} does not follow from the "
                                             f"records ({value!r})")
        for key, value in (("mean_mac_first", sum(r.mac_first for r in records) / len(records)),
                           ("mean_abs_frequency_error_pct", sum(errors) / len(errors)),
                           ("max_abs_frequency_error_pct", max(errors))):
            _need(_close(_number(summary.get(key), f"{name} {key}"), value, 1e-5),
                  f"{name}: summary {key} does not follow from the records")
        models[name] = PlateModel(name, str(raw.get("title", name)), str(raw.get("origin", "")), str(raw.get("readme", "")),
                                  dict(inputs), dict(identity), fe_hz, tuple(records), tuple(mac), dict(summary))
    for name in ("BASELINE", "THICKNESS_ONLY"):
        _need(models[name].inputs["E2_MPa"] == models[name].inputs["E1_MPa"], f"{name}: E1 and E2 are not equal")
    for name in ("DIRECTIONAL_ONLY", "COMBINED"):
        _need(models[name].inputs["E2_MPa"] < models[name].inputs["E1_MPa"], f"{name}: E2 is not below E1")
    for name, uniform in (("BASELINE", True), ("DIRECTIONAL_ONLY", True), ("THICKNESS_ONLY", False), ("COMBINED", False)):
        ends = models[name].inputs["thickness_mm_at_x0_x301"]
        _need((ends[0] == ends[1]) is uniform, f"{name}: the thickness is not " + ("uniform" if uniform else "a gradient"))
    # what must stay visible: the unresolved records, the failed ±5 % criterion and the lost branches
    combined = models["COMBINED"].summary
    unresolved = document.get("unresolved_records")
    _need(unresolved == combined["records_mac_below_0_80"],
          f"unresolved records {unresolved!r} are not the combined model's records below {PLATE_MAC_LEVEL:.2f} "
          f"({combined['records_mac_below_0_80']!r})")
    criteria = document.get("criteria")
    _need(isinstance(criteria, dict) and isinstance(criteria.get("combined_model_readme_26"), dict)
          and isinstance(criteria.get("directional_test_readme_25"), dict), "the declared criteria are missing")
    b = criteria["combined_model_readme_26"].get("B_all_class_frequencies_within_5_pct")
    _need(isinstance(b, dict) and b.get("records_outside") == combined["records_outside_5_pct"]
          and b.get("verdict") == ("FAIL" if combined["records_outside_5_pct"] else "PASS"),
          "the ±5 % criterion of the combined model does not follow from its frequency errors")
    _need(all(v in ("PASS", "FAIL") for v in criteria["directional_test_readme_25"].values())
          and len(criteria["directional_test_readme_25"]) == 3, "the three criteria of the directional test are not stated")
    tracking = document.get("tracking")
    _need(isinstance(tracking, dict) and isinstance(tracking.get("rows"), list)
          and len(tracking["rows"]) == len(PLATE_FE_MODES), "the branch tracking has not 14 rows")
    level = _number(tracking.get("minimum_mac_for_tracked"), "tracking level", 0.0, 1.0)
    lost = []
    for r in tracking["rows"]:
        _need(isinstance(r, dict) and r.get("reference_fe") in PLATE_FE_MODES and r.get("target_fe") in PLATE_FE_MODES,
              "branch tracking: FE mode outside FE7–FE20")
        value = _number(r.get("mac"), "FE-to-FE MAC", -1e-9, 1 + 1e-9)
        _need(r.get("status") == ("TRACKED" if value >= level else "LOST"),
              f"branch FE{r['reference_fe']}: status {r.get('status')!r} does not follow from MAC {value}")
        if r["status"] == "LOST":
            lost.append(r["reference_fe"])
    _need(tracking.get("lost") == lost, "the list of lost branches does not follow from the tracking rows")
    _need(b.get("correspondence_not_confirmed_by_tracking")
          == [k for k in range(1, plate.modes + 1) if PLATE_FE_MODES[0] - 1 + k in lost],
          "the records whose correspondence is not confirmed by tracking do not follow from the lost branches")
    limitations = document.get("limitations")
    _need(isinstance(limitations, list) and limitations and all(isinstance(x, str) and x for x in limitations),
          "the limitations are missing")
    sources = document.get("sources")
    _need(isinstance(sources, list) and [s.get("name") if isinstance(s, dict) else None for s in sources]
          == list(PLATE_COMPARISON_SOURCES), "the sources are not " + ", ".join(PLATE_COMPARISON_SOURCES))
    for s in sources:
        _need(isinstance(s.get("sha256"), str) and len(s["sha256"]) == 64 and isinstance(s.get("path"), str),
              f"source {s.get('name')}: path or SHA-256 missing")
    _need(geometry.get("reconstruction_sha256") == sources[-1]["sha256"],
          "the corrected reconstruction named by the geometry is not the listed source")
    return PlateComparison(path, sha256, tuple(labels), dict(status), dict(specimen), dict(geometry), exp_hz,
                           PLATE_FE_MODES, str(document.get("correspondence", "")), models, dict(tracking),
                           dict(criteria), tuple(unresolved), tuple(limitations),
                           tuple((s["name"], s["path"], s["sha256"]) for s in sources),
                           str(document.get("documented_in", "")))


def load_plate_comparison(root: Path = REPO) -> PlateComparison:
    """Read the current plate research snapshot: only with the recorded SHA-256 and a consistent content."""
    relative, expected = PLATE_COMPARISON_FILE
    path = root / relative
    if not path.is_file():
        raise PlateComparisonRefused(f"{relative} is missing")
    if path.stat().st_size > MAX_RECORD_BYTES:
        raise PlateComparisonRefused(f"{relative} is larger than {MAX_RECORD_BYTES // (1024 * 1024)} MB")
    data = path.read_bytes().replace(b"\r\n", b"\n")  # the committed (LF) form, whatever the checkout wrote
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise PlateComparisonRefused(f"{relative}: SHA-256 {digest[:12]}… is not the recorded {expected[:12]}… — the "
                                     "file changed, so the snapshot is not shown")
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PlateComparisonRefused(f"{relative} is not valid JSON: {error}") from error
    return validate_plate_comparison(document, relative, digest)


__all__ = ["HISTORICAL_PLATE_GEOMETRY", "LABELS", "LocalRecord", "MacMatrix", "NOT_VERIFIED_BANNER",
           "PLATE_COMPARISON_FILE", "PLATE_COMPARISON_LABELS", "PLATE_COMPARISON_SOURCES", "PLATE_MODELS",
           "PlateComparison", "PlateComparisonRefused", "PlateModel", "PlateRecord", "RecordRefused", "SNAPSHOT_FILES",
           "SPECIMENS", "STATUSES", "Snapshot", "SnapshotRefused", "VERIFIED_BANNER", "load_local_record",
           "load_plate_comparison", "load_snapshot", "scenario_detail", "validate_plate_comparison", "workspace_link"]

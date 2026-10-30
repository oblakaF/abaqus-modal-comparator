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

# (published path, SHA-256, research commit) of every archived file the page reads
SNAPSHOT_FILES = {
    "PLATE_MATCHING": ("docs/research/real_modal_matching_202610/PLATE_MODAL_MATCHING.csv",
                       "4a335f1240e387e7459f5ad4abbcabc7ae80623eca31fbea397815b2fe781234", "1dd29d5"),
    "SP13_MATCHING": ("docs/research/real_modal_matching_202610/SP13_MODAL_MATCHING.csv",
                      "9b25517a41fcc5dfec9ebb84370c5b6ab52462e1c1746195c68ca73819182874", "1dd29d5"),
    "SP10_MATCHING": ("docs/research/real_modal_matching_202610/SP10_MODAL_MATCHING.csv",
                      "bf185280d7bae4f10584febbb071662ecec06e47fce05a949760da9ace775805", "1dd29d5"),
    "SENSITIVITIES": ("docs/research/plate_s4_central/CENTRAL_SENSITIVITIES.csv",
                      "50136be13b38021251feb9c8f4fb74cfb052801bbeeba99e9b7f3efd90864ee8", "e42649a"),
    "SCENARIOS": ("docs/research/plate_inverse_r1/PLATE_INVERSE_SCENARIOS.csv",
                  "57d5ab473b6b07dda8831087ef2568bedd6b28d3ba6b14cb3b5fab8928f28310", "77a57ae"),
    "FE_VS_LM": ("docs/research/plate_inverse_fe_r1/REAL_FE_VS_LM.csv",
                 "32e117317a85ac2b9aa5efb3a5963bfb49905249b3f44ffea7cc14b3cbc03882", "f19fc93"),
    "FE_VS_EXPERIMENT": ("docs/research/plate_inverse_fe_r1/REAL_FE_VS_EXPERIMENT.csv",
                         "2263e60c65dc71f147e8a5cdc67d79e8062fb48a58e326c09c14994fd6006dbb", "f19fc93"),
    "FE_TRACKING": ("docs/research/plate_inverse_fe_r1/REAL_FE_BRANCH_TRACKING.csv",
                    "6bae20208e599f88811f91653690048162c9ae75b682eba352f1568faafb48ec", "f19fc93"),
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
    data = path.read_bytes()
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
    """(verified, text) — the snapshot is tied to the Workspace inputs only by their SHA-256."""
    spec = SPECIMENS[specimen]
    exp_sha = (experimental_identity or {}).get("sha256")
    fe_sha = (fe_identity or {}).get("sha256")
    reasons = []
    if exp_sha != spec.experiment_sha256:
        reasons.append("the experimental file read in the Workspace is " + (f"{exp_sha[:12]}…" if exp_sha else "none")
                       + f", not the series' {spec.experiment_sha256[:12]}…")
    if spec.fe_manifest_sha256 and fe_sha != spec.fe_manifest_sha256:
        reasons.append("the FE manifest read in the Workspace is " + (f"{fe_sha[:12]}…" if fe_sha else "none")
                       + f", not the research FE package's {spec.fe_manifest_sha256[:12]}…")
    if reasons:
        return False, NOT_VERIFIED_BANNER + ": " + "; ".join(reasons)
    return True, VERIFIED_BANNER + (" (experimental file only: SP-10 has no FE package)" if not
                                    spec.fe_manifest_sha256 else "")


__all__ = ["LABELS", "LocalRecord", "MacMatrix", "NOT_VERIFIED_BANNER", "RecordRefused", "SNAPSHOT_FILES",
           "SPECIMENS", "STATUSES", "Snapshot", "SnapshotRefused", "VERIFIED_BANNER", "load_local_record",
           "load_snapshot", "scenario_detail", "workspace_link"]

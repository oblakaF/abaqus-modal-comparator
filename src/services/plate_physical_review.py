"""PRIORITY-9: the Physical Evidence Review of one single CFRP plate (no Qt; RESEARCH_ONLY).

A reproducible dossier of what is established, what is only supposed and what blocks a physical identification of
one plate. It joins the evidence and research the project already holds and checks their state; it creates nothing
scientific: no registration, no mode pair, no MAC, no FIT / HOLDOUT set, no fit and no material value.

Two profiles:

- ``M11-261027`` — the first real object: ``PLATE-300x300x1mm``, series ``NEXP29/PLATE300-1MM/S261027-ROTATED``,
  modal set ``Polymax_bravo``, FE model Abaqus M11 ``S4R_0875_BASELINE``. Its facts come from
  ``plate_registration_readiness.real_261027_evidence`` and ``CLOSING_EVIDENCE``, its test conditions from
  ``plate_study.EXPERIMENT_CONDITIONS``, its archived research (PRIORITY-1–4) from ``research_results_reader`` and
  the PRIORITY-2 files, each read only with its recorded SHA-256. The sources must be the recorded files: a foreign
  UNV or FE manifest refuses the review (``SOURCE_NOT_VERIFIED``).
- ``GENERIC`` — any other single plate, from a study of the Single-Plate Workbench (RC3-F2): its passport, linked
  files, registration evidence (``generic_plate_evidence``), diagnostics and imported sensitivity table. No M11
  identifier or archive enters it.

The dossier keeps two questions apart: what the FE model distinguishes mathematically (FE-only rank) and what the
confirmed experimental observations support (``NOT_ASSESSED — NO_ADMISSIBLE_MODAL_OBSERVATIONS`` while no registration
is accepted). Frequency proximity is diagnostic only; the PRIORITY-1 research MAC is shown only as
``RESEARCH_MAC_NOT_ADMISSIBLE``; S0 / H1 / H2 stay ``RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY``.
Every FE run in the plan is a declaration, never a run order: no Abaqus, solver, extraction, LM or Auto-ID is started.

``export_dossier`` writes the seven documents (and the machine-readable owner request) into a new folder inside a
folder the user chooses, outside the program tree, after the sources are confirmed on disk again; nothing is
overwritten. M8 GATE NOT_MET, D-077 NO_GLOBAL_PARAMETER_VALUE and production Auto-ID BLOCKED are unchanged.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from services import generic_plate_evidence as gev
from services import generic_plate_workbench as wb
from services import plate_registration_readiness as rr
from services import plate_study as ps
from services import plate_workbench as pw
from services import research_results_reader as rrr
from services.practical_identifiability import RCOND

SCHEMA = "amc/plate-physical-readiness/v1"
REPO = Path(__file__).resolve().parents[2]

# ----------------------------------------------------------------------------- states and labels
SOURCE_NOT_VERIFIED = "SOURCE_NOT_VERIFIED"
SOURCES_VERIFIED = "SOURCES_VERIFIED"
REGISTRATION_NOT_VERIFIED = rr.REGISTRATION_NOT_VERIFIED
EVIDENCE_COMPLETE_NOT_FROZEN = rr.COMPLETE
MODE_PAIRS_NOT_CONFIRMED = "MODE_PAIRS_NOT_CONFIRMED"
NOT_READY = "NOT_READY_FOR_IDENTIFICATION"
READY_FOR_OWNER_REVIEW = "READY_FOR_OWNER_REVIEW"
SYNTHETIC_ONLY = "SYNTHETIC_DEMONSTRATION_ONLY"
OWNER_REVIEW_NOTE = ("READY_FOR_OWNER_REVIEW means that the package for an owner decision is complete; it is not a "
                     "scientific acceptance, a registration or a permission to identify")
NOT_AVAILABLE = "NOT_AVAILABLE"
NOT_VERIFIED = "NOT_VERIFIED"
NOT_ASSESSED = "NOT_ASSESSED — NO_ADMISSIBLE_MODAL_OBSERVATIONS"
RESEARCH_MAC = "RESEARCH_MAC_NOT_ADMISSIBLE"
FE_ONLY = "FE_ONLY_MATHEMATICAL_OBSERVABILITY"
HYPOTHESIS_LABELS = "RESEARCH_ONLY / HYPOTHETICAL_PAIRING / NOT_A_MATERIAL_PROPERTY"
PROXIMITY_ONLY = wb.PROXIMITY_ONLY
PLAN_ONLY = ("PLAN ONLY — not a run order: no Abaqus, solver, extraction, LM or Auto-ID is authorised or started by "
             "this program")
AUTHORISATION = "NOT_GIVEN — a separate, explicit owner authorisation naming the job"
SCIENTIFIC_STATUS = wb.SCIENTIFIC_STATUS
LABELS = ("RESEARCH_ONLY", "NOT_A_MATERIAL_PROPERTY", "NO_REGISTRATION_CREATED", "NO_MAC_COMPUTED")
NOT_FROM_FREQUENCIES = "never derived from a measured or FE frequency"

# ----------------------------------------------------------------------------- source documents
EXPERIMENTAL = "experimental UNV"
FE_MANIFEST = "FE manifest.json"
FE_INP = "FE input (INP)"
SVD = "PSV project (.svd)"
OWNER_DOCUMENT = "owner-chosen document"
CLAIM_TYPES = ("the absolute scanned face", "the physical scan geometry (camera frame, scanner angles, scale)",
               "an FE landmark or a measured asymmetry", "the suspension points and bands",
               "the force sensor's place, mass and attachment", "the thickness of the plate (a map)", "other")
VERIFIED = "VERIFIED_SHA256"
FOREIGN = "FOREIGN — not the recorded source"
CHANGED = "CHANGED_SINCE_READ"
MISSING = "MISSING_ON_DISK"
RECORDED = "RECORDED_BY_SHA256 — interpretation NOT_CONFIRMED"
RECORDED_GENERIC = "RECORDED_BY_SHA256 (no archived reference)"


class ReviewRefused(ValueError):
    """The review is not built (``state`` says why: SOURCE_NOT_VERIFIED or another refusal)."""

    def __init__(self, message: str, state: str = SOURCE_NOT_VERIFIED):
        super().__init__(message)
        self.state = state


class ExportRefused(ValueError):
    """The dossier is not written; nothing was written."""


@dataclass(frozen=True)
class Profile:
    key: str
    specimen: str
    series: str
    modal_set: Optional[str]
    fe_model: str
    experimental_sha256: Optional[str]
    fe_manifest_sha256: Optional[str]
    inp_sha256: Optional[str]
    records: Optional[int]
    fe_elastic: Optional[int]
    archive: bool


_M11 = ps.PLATE_FE_FAMILY[0]
M11_261027 = Profile("M11-261027", ps.SPECIMEN, ps.SERIES, ps.WORKING_SET, f"Abaqus M11 {_M11.member_id}",
                     ps.WORKING_SOURCE_SHA256, _M11.manifest.sha256, _M11.inp.sha256, 11, 14, True)


@dataclass(frozen=True)
class SourceDocument:
    role: str
    path: str
    sha256: Optional[str]  # the identity read (Inspect file, or hashed when chosen)
    size: Optional[int]
    origin: str
    supports: str  # the kind of claim it may support (never its interpretation)
    on_disk_sha256: Optional[str] = None  # hashed again now (None: not re-read)


def hash_file(path) -> tuple:
    """(SHA-256, size) of a file read now, read-only; (None, None) when it cannot be read."""
    try:
        digest, size = hashlib.sha256(), 0
        with open(path, "rb") as stream:
            for chunk in iter(lambda: stream.read(1 << 20), b""):
                digest.update(chunk)
                size += len(chunk)
        return digest.hexdigest(), size
    except OSError:
        return None, None


def document(role: str, path, origin: str, supports: str, recorded_sha256: Optional[str] = None) -> SourceDocument:
    """A source document hashed now; ``recorded_sha256`` is the identity recorded when it was read, if any."""
    sha, size = hash_file(path)
    return SourceDocument(role, str(path), recorded_sha256 or sha, size, origin, supports, sha)


# ----------------------------------------------------------------------------- the archive of the M11 profile
# (path, SHA-256 of the committed LF content) of the archived files this review cites besides research_results_reader
ARCHIVE_FILES = {
    "S4_RUNS": ("docs/research/plate_s4_central/SOLVER_RUNS.csv",
                "9449807bb3ac6859ed5c8467c03b4d2257aa4f6bec549d49a88426120e93eb1a"),
    "S4_TRACKING": ("docs/research/plate_s4_central/BRANCH_TRACKING.csv",
                    "c021b311ed0271a57208fbc629c569c45eded06990f5d1b60552770d02e4dd92"),
    "S4_RESULTS": ("docs/research/plate_s4_central/RESULTS.md",
                   "22a6fa5e5f9a2819e39f4897340f325b0304fb080394ef88820cf887e10630cf"),
    "P1_SECANTS": ("docs/research/real_modal_matching_202610/PLATE_FE_SENSITIVITY.csv",
                   "4538ea35948455aaf2ccc45c83677d05ebef7943fe38ffd92cce98824e10f628"),
    "P1_RESULTS": ("docs/research/real_modal_matching_202610/RESULTS.md",
                   "730bf2ff1cfbb66b84183743216988d86d1e46586d926f064f3f3d4a69a59501"),
    "P4_RUNS": ("docs/research/plate_inverse_fe_r1/REAL_FE_SOLVER_RUNS.csv",
                "22ffe74ceebde9db3f778c5b0148854cbd7d7fed3a92df331d286f405a7f02d4"),
    "P4_RESULTS": ("docs/research/plate_inverse_fe_r1/RESULTS.md",
                   "de254ab8ea56838a5de1f4ecc97b5a263ea612dbeb9030f37d7380ec6cef8c38"),
    "P3_RESULTS": ("docs/research/plate_inverse_r1/PLATE_INVERSE_RESULTS.md",
                   "b8da5189a82c23f1a96e8a94eb1d74d661ea75db92b615e0e765f96ddcf6418c"),
    "RC1_RECORD": ("docs/research/plate_only/PLATE_WORKBENCH_RC1.md",
                   "ca1c8bb4065270555f08fc97b06713bf9d8064bb685ac34633806a2d322f76ca"),
}
# PRIORITY-2 §4 (S4 RESULTS.md): the close pairs examined by confirm_cluster over the six ±5 % variants
ARCHIVED_CLUSTERS = (("FE10 / FE11", "INDEPENDENT"), ("FE13 / FE14", "INDEPENDENT"),
                     ("FE15 / FE16", "CONFIRMED cluster (one term, mean ln f)"), ("FE17 / FE18", "INDEPENDENT"))


class ArchiveRefused(ValueError):
    """An archived file is missing or changed; the part of the review that needs it is NOT_AVAILABLE."""


def _archive_csv(key: str, root: Path) -> list:
    relative, expected = ARCHIVE_FILES[key]
    path = root.joinpath(*relative.split("/"))
    if not path.is_file():
        raise ArchiveRefused(f"{relative} is missing")
    data = path.read_bytes().replace(b"\r\n", b"\n")
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected:
        raise ArchiveRefused(f"{relative}: SHA-256 {digest[:12]}… is not the archived {expected[:12]}…")
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


def archive_check(root: Path = REPO) -> tuple:
    """(file, recorded SHA-256, state) of every archived file the review cites."""
    rows = []
    for key, (relative, expected) in ARCHIVE_FILES.items():
        path = root.joinpath(*relative.split("/"))
        if not path.is_file():
            rows.append((relative, expected, MISSING))
            continue
        digest = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        rows.append((relative, expected, VERIFIED if digest == expected else "CHANGED — not used"))
    for key, (relative, expected, _commit) in rrr.SNAPSHOT_FILES.items():
        rows.append((relative, expected, "read by research_results_reader with this SHA-256"))
    return tuple(rows)


# ----------------------------------------------------------------------------- the inputs of a review

@dataclass(frozen=True)
class ReviewInputs:
    profile: Profile
    documents: tuple  # SourceDocument
    kind: str = wb.PHYSICAL  # PHYSICAL or SYNTHETIC_DEMO (a synthetic demonstration study)
    modal_set: Optional[str] = None
    records: tuple = ()  # {"number", "hz", "admissible", "label"}
    fe_elastic: tuple = ()  # {"number", "hz"}
    fe_rigid: tuple = ()
    scan_points_m: tuple = ()
    measured_components: str = ""
    fe_extent_mm: Optional[tuple] = None
    facts: tuple = ()  # rr.Fact (M11) or gev.EvidenceFact (generic)
    applicability: tuple = ()  # (key, question, value, provenance, source, state)
    study: Any = None  # the generic study (GENERIC profile)
    extra: Mapping[str, Any] = field(default_factory=dict)


def _modes(rows) -> tuple:
    return tuple(sorted(({"number": int(r["number"]), "hz": float(r["hz"]), **{k: v for k, v in r.items()
                                                                                if k not in ("number", "hz")}}
                         for r in rows), key=lambda r: r["number"]))


# The test conditions of 261027 that decide the applicability of the free-free M11 model (group D of the owner's
# questions). They come from the owner, the laboratory note and the instrument; none is derived from a frequency.
APPLICABILITY_261027 = (
    ("suspension_points", "the actual attachment points of the two suspensions",
     "two upper points along the nodal line of the first mode; the exact points are not recorded", ps.LAB_RECORD,
     f"{ps.READ_ME[0]} ({ps.READ_ME[1][:12]}…)", "NOT_RECORDED"),
    ("suspension_bands", "the length and known characteristics of the two rubber bands and strings",
     "two rubber bands (owner, 2026-10-30); stiffness and lengths not recorded", ps.HUMAN_CONFIRMED,
     "owner, 2026-10-30; the laboratory note", "NOT_RECORDED"),
    ("force_sensor", "the place, mass and attachment of the force sensor",
     "a force reference channel exists (dataset 58 'Force * Velocity'); the point, mass and attachment are not "
     "recorded", ps.INSTRUMENT_RECORD, f"PSV export ({ps.AUXILIARY_FRF_SHA256[:12]}…)", "NOT_RECORDED"),
    ("thickness_map", "the real thickness of the plate, including a possible non-uniformity inside it",
     f"{ps._T['n']} perimeter readings {ps._T['min']:.2f}–{ps._T['max']:.2f} mm (2026-10-21); the interior is not "
     "measured; edge means differ by about 13 % (edge 2 against edge 4)", "MEASURED (perimeter only)",
     "M11 §8, §8.1 (plate_study.SPECIMEN_RECORD)", "NOT_MEASURED_INSIDE"),
)


def _experimental_identity_path(identity) -> str:
    return str((identity or {}).get("path") or "")


def inputs_from_workspace(fe_preview, fe_identity, experimental_preview, experimental_identity, set_index,
                          documents: Sequence[SourceDocument] = (), inp_path=None) -> ReviewInputs:
    """The M11-261027 review inputs from the files read in the Workspace. Refuses (``SOURCE_NOT_VERIFIED``) any
    other experimental file or FE manifest, a file changed on disk since it was read, or a missing modal set."""
    if experimental_preview is None or not experimental_identity:
        raise ReviewRefused("read the experimental file of PLATE 261027 on the Workspace page first")
    if fe_preview is None or not fe_identity:
        raise ReviewRefused("read the FE package of M11 on the Workspace page first")
    exp_sha, fe_sha = experimental_identity.get("sha256"), fe_identity.get("sha256")
    reasons = []
    if exp_sha != M11_261027.experimental_sha256:
        reasons.append(f"the experimental file ({str(exp_sha)[:12]}…, {ps.classify_source(exp_sha)}) is not the "
                       f"working source of {ps.SERIES} ({M11_261027.experimental_sha256[:12]}…)")
    if fe_sha != M11_261027.fe_manifest_sha256:
        reasons.append(f"the FE manifest ({str(fe_sha)[:12]}…) is not the M11 {_M11.member_id} manifest "
                       f"({M11_261027.fe_manifest_sha256[:12]}…)")
    if reasons:
        raise ReviewRefused("SOURCE_NOT_VERIFIED: " + "; ".join(reasons) + ". This review of the Workspace inputs is "
                            "the one of PLATE-300x300x1mm 261027 and M11; another plate is reviewed from its study "
                            "in B. New Single Plate.")
    exp_path = getattr(experimental_preview, "source_path", None) or _experimental_identity_path(experimental_identity)
    fe_path = getattr(fe_preview, "manifest_path", None) or _experimental_identity_path(fe_identity)
    docs = [document(EXPERIMENTAL, exp_path, "Workspace (Inspect file)", "the measured modal records and the scan "
                     "geometry (instrument record)", exp_sha),
            document(FE_MANIFEST, fe_path, "Workspace (Inspect file)", "the FE modes and geometry of M11", fe_sha)]
    if inp_path:
        docs.append(document(FE_INP, inp_path, "chosen by the user (hashed only, never run)",
                             "the FE model's input (geometry, material, no physical landmark)"))
    docs += list(documents)
    for d in docs[:2]:
        if d.on_disk_sha256 is None:
            raise ReviewRefused(f"SOURCE_NOT_VERIFIED: {d.role} {d.path} cannot be read on disk now")
        if d.on_disk_sha256 != d.sha256:
            raise ReviewRefused(f"SOURCE_NOT_VERIFIED: {d.role} {d.path} changed since it was read "
                                f"({d.sha256[:12]}… read, {d.on_disk_sha256[:12]}… now); Inspect it again")
    diagnostics = wb.diagnostics_from_previews(experimental_preview, set_index, fe_preview)
    dataset = experimental_preview.sets[set_index].dataset
    summary = ps.experimental_summary(dataset, exp_sha)
    components = summary.records[0].measured_components if summary.records else ""
    return ReviewInputs(M11_261027, tuple(docs), wb.PHYSICAL, diagnostics["modal_set"]["names"][0],
                        _modes(diagnostics["experimental"]), _modes(diagnostics["fe_elastic"]),
                        tuple(diagnostics["fe_rigid_excluded"]), tuple(map(tuple, diagnostics["scan_points_m"])),
                        components, tuple(diagnostics["fe_extent_mm"]) if diagnostics.get("fe_extent_mm") else None,
                        rr.real_261027_evidence(), APPLICABILITY_261027)


def inputs_from_study(study: wb.Study, documents: Sequence[SourceDocument] = ()) -> ReviewInputs:
    """The review inputs of any single plate from its Single-Plate Workbench study (no M11 identifier enters)."""
    p = study.passport
    specimen = p.physical_specimen_id or NOT_AVAILABLE
    if not p.physical_specimen_id:
        raise ReviewRefused("the study has no physical specimen identifier: apply the set-up in B. New Single Plate "
                            "first", "STUDY_NOT_READY")
    diagnostics = study.diagnostics or {}
    if not diagnostics:
        raise ReviewRefused("the study has no modal diagnostics: run them (or load the synthetic inputs) in B. New "
                            "Single Plate first", "STUDY_NOT_READY")
    profile = Profile("GENERIC", specimen, p.test_run_id or NOT_AVAILABLE,
                      (study.modal_set or diagnostics.get("modal_set") or {}).get("names", [None])[0]
                      if (study.modal_set or diagnostics.get("modal_set")) else None,
                      p.claim("fe_model_version").value or NOT_AVAILABLE, None, None, None, None, None, False)
    docs = []
    for role, name in (("experimental", EXPERIMENTAL), ("fe", FE_MANIFEST)):
        record = study.sources.get(role)
        if record is None:
            continue
        supports = "the modal records" if role == "experimental" else "the FE modes"
        if study.synthetic:  # a declared synthetic identity: there is no file to read
            docs.append(SourceDocument(name, "", record.sha256, record.size, f"synthetic declaration: {record.path}",
                                       supports))
            continue
        docs.append(document(name, record.path, "the study's linked source", supports, record.sha256))
    applicability = []
    for key, question in (("suspension", "the suspension points, bands and their characteristics"),
                          ("excitation", "the excitation: the force sensor's place, mass and attachment")):
        claim = p.claim(key)
        state = "RECORDED" if claim.value and claim.provenance in gev.INDEPENDENT else "NOT_RECORDED"
        applicability.append((key, question, claim.value or NOT_AVAILABLE, claim.provenance, claim.source or "—",
                              state))
    readings = len([r for r in p.thickness if r.thickness.value is not None])
    applicability.append(("thickness_map", "the real thickness of the plate, including a possible non-uniformity",
                          f"{readings} thickness readings in the passport", "passport", "the study's passport",
                          "RECORDED" if readings >= wb.MIN_THICKNESS_POINTS else "NOT_ENOUGH_READINGS"))
    return ReviewInputs(profile, tuple(docs) + tuple(documents), study.kind, profile.modal_set,
                        _modes(diagnostics.get("experimental", ())), _modes(diagnostics.get("fe_elastic", ())),
                        tuple(diagnostics.get("fe_rigid_excluded", ())),
                        tuple(map(tuple, diagnostics.get("scan_points_m", ()) or ())), "Z",
                        tuple(diagnostics["fe_extent_mm"]) if diagnostics.get("fe_extent_mm") else None,
                        tuple(study.evidence), tuple(applicability), study)


def with_document(inputs: ReviewInputs, doc: SourceDocument) -> ReviewInputs:
    """The same inputs with one more owner-chosen document (it is recorded, never interpreted)."""
    return replace(inputs, documents=inputs.documents + (doc,))


# ----------------------------------------------------------------------------- fingerprint and freshness

def _digest(data) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _fact_tuple(fact) -> list:
    return [fact.key, fact.value, fact.provenance, getattr(fact, "source", ""), list(getattr(fact, "derived_from", ()))]


def fingerprint(inputs: ReviewInputs) -> str:
    """SHA-256 of everything the dossier depends on: the profile, every document's identity, the modal set, the
    records and FE modes, the facts, the applicability facts and (generic) the passport and evidence."""
    data = {"profile": inputs.profile.key, "kind": inputs.kind, "specimen": inputs.profile.specimen,
            "documents": [[d.role, d.sha256, d.supports] for d in inputs.documents], "modal_set": inputs.modal_set,
            "records": [[r["number"], r["hz"]] for r in inputs.records],
            "fe": [[m["number"], m["hz"]] for m in inputs.fe_elastic],
            "facts": sorted(_fact_tuple(f) for f in inputs.facts), "applicability": [list(a) for a in
                                                                                    inputs.applicability]}
    if inputs.study is not None:
        data["passport"] = wb.passport_fingerprint(inputs.study.passport)
        data["evidence"] = wb.evidence_fingerprint(inputs.study)
        data["diagnostics"] = (inputs.study.diagnostics or {}).get("inputs")
    return _digest(data)


# ----------------------------------------------------------------------------- source audit

def audit_sources(inputs: ReviewInputs) -> tuple:
    """One row per document: role, path, SHA-256, size, origin, what it may support, the expected SHA-256 and the
    state. Loading a document never confirms its scientific interpretation."""
    profile, rows = inputs.profile, []
    expected = {EXPERIMENTAL: profile.experimental_sha256, FE_MANIFEST: profile.fe_manifest_sha256,
                FE_INP: profile.inp_sha256}
    present = {d.role for d in inputs.documents}
    for d in inputs.documents:
        want = expected.get(d.role)
        if inputs.kind == wb.SYNTHETIC_DEMO and not d.path:
            state = "SYNTHETIC_DECLARATION — no file"
        elif d.on_disk_sha256 is None and d.path:
            state = MISSING
        elif d.on_disk_sha256 is not None and d.on_disk_sha256 != d.sha256:
            state = CHANGED
        elif d.role == OWNER_DOCUMENT:
            state = RECORDED
        elif want is None:
            state = RECORDED_GENERIC
        else:
            state = VERIFIED if d.sha256 == want else FOREIGN
        rows.append({"role": d.role, "path": d.path, "sha256": d.sha256, "size": d.size, "origin": d.origin,
                     "supports": d.supports, "expected_sha256": want, "state": state})
    if profile.archive:
        if FE_INP not in present:
            rows.append({"role": FE_INP, "path": None, "sha256": None, "size": None, "origin": "—",
                         "supports": "the FE model's input", "expected_sha256": profile.inp_sha256,
                         "state": f"{NOT_AVAILABLE} (optional: hashed only when chosen)"})
        if SVD not in present:
            rows.append({"role": SVD, "path": None, "sha256": None, "size": None, "origin": "—",
                         "supports": "the camera frame and the physical scan geometry of 261027 "
                                     "(300by300_plate_only_1mm_ROTATED_261027.svd)", "expected_sha256": None,
                         "state": f"{NOT_AVAILABLE} (not delivered; not needed to view the existing diagnostics)"})
    for role in (EXPERIMENTAL, FE_MANIFEST):
        if role not in present and inputs.kind == wb.PHYSICAL:
            rows.append({"role": role, "path": None, "sha256": None, "size": None, "origin": "—", "supports": "—",
                         "expected_sha256": expected.get(role), "state": f"{NOT_AVAILABLE} (not linked)"})
    return tuple(rows)


def sources_state(audit: Sequence[Mapping[str, Any]], kind: str) -> str:
    if kind == wb.SYNTHETIC_DEMO:
        return "SYNTHETIC_INPUTS"
    required = [r for r in audit if r["role"] in (EXPERIMENTAL, FE_MANIFEST)]
    ok = (VERIFIED, RECORDED_GENERIC)
    bad = [r for r in audit if r["state"] in (FOREIGN, CHANGED, MISSING)]
    return SOURCES_VERIFIED if required and all(r["state"] in ok for r in required) and not bad else \
        SOURCE_NOT_VERIFIED


# ----------------------------------------------------------------------------- evidence chains A and B

_PSV = ("300by300_plate_only_1mm_ROTATED_261027.unv (PSV export)", ps.AUXILIARY_FRF_SHA256)
_UNV16, _UNV27 = rr.SERIES_LINK_INPUTS["reference"], rr.SERIES_LINK_INPUTS["series"]
_INP = (Path(_M11.inp.relative).name, _M11.inp.sha256)
FACT_FILES = {  # the files whose recorded SHA-256 a fact of 261027 rests on (no hash is invented for a statement)
    "scan_geometry_261016": (_UNV16,), "scan_geometry_261027": (_UNV27,), "point_map_261016_261027": (_UNV16, _UNV27),
    "scan_scale": (_PSV, ps.READ_ME), "measured_dof": (_PSV,), "rotation_reference": (ps.READ_ME, _UNV16, _UNV27),
    "fe_origin_corner": (_INP,), "fe_normal_face": (_INP,),
}
TOPICS_A = {"scanned_face": "the measured face (absolute)", "grid_plus_u_edge": "+u of the scan grid against edges 1–4",
            "grid_plus_v_edge": "+v of the scan grid against edges 1–4",
            "rotation_reference": "the turn and its physical reference",
            "scan_metric_geometry": "the metric geometry of the measured points",
            "scan_window_offsets_mm": "the position of the scan window on the plate", "scan_scale": "the scale",
            "measured_dof": "the measured DOF"}
TOPICS_B = {"fe_x_along_edges": "the physical direction of FE X", "fe_origin_corner": "the physical corner at FE (0, 0)",
            "fe_normal_face": "the face the shell normal (+Z) leaves"}
CHAIN_A = "A. scanner → physical plate"
CHAIN_B = "B. physical plate → FE model"
SUPPORTING = "supporting (relative facts and the 261016 reference)"
EVIDENCE_COLUMNS = ("chain", "topic", "fact", "value", "provenance", "source", "source_sha256", "dependencies",
                    "status", "blocking_reason")


def _text(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, Mapping):
        return ", ".join(f"{k} {v}" for k, v in value.items())
    if isinstance(value, (tuple, list)):
        return ", ".join(str(v) for v in value)
    return str(value)


def _sha_text(key: str) -> str:
    files = FACT_FILES.get(key)
    if not files:
        return f"{NOT_AVAILABLE} (a statement or report reference; no file hash is recorded)"
    return "; ".join(f"{name}: {sha}" for name, sha in files)


def _m11_evidence(inputs: ReviewInputs) -> tuple:
    readiness = rr.evaluate(inputs.facts, np.asarray(inputs.scan_points_m, dtype=float) if inputs.scan_points_m
                            else None, inputs.measured_components or "Z", inputs.fe_extent_mm)
    by_key = {f.key: f for f in inputs.facts}
    missing = dict(readiness.missing)
    rows = []
    for chain, topics in ((CHAIN_A, TOPICS_A), (CHAIN_B, TOPICS_B)):
        for key, topic in topics.items():
            fact = by_key.get(key)
            if fact is None:
                rows.append(dict(zip(EVIDENCE_COLUMNS, (chain, topic, key, "—", NOT_VERIFIED, "—", NOT_AVAILABLE,
                                                        "—", "OPEN", missing.get(key, "missing")))))
                continue
            status = "OPEN" if key in missing else "ESTABLISHED"
            rows.append(dict(zip(EVIDENCE_COLUMNS, (
                chain, topic, key, _text(fact.value), fact.provenance, fact.source, _sha_text(key),
                ", ".join(fact.derived_from) or "—", status, missing.get(key, "—")))))
    for fact in inputs.facts:
        if fact.key in TOPICS_A or fact.key in TOPICS_B:
            continue
        independent = rr._independent(fact, by_key)
        status = (f"SUPPORTING — {fact.provenance} from independent facts" if independent and
                  fact.provenance == rr.DERIVED else "SUPPORTING — independent" if independent else
                  f"SUPPORTING — {fact.provenance}: not evidence by itself")
        rows.append(dict(zip(EVIDENCE_COLUMNS, (SUPPORTING, "relative or reference fact", fact.key, _text(fact.value),
                                                fact.provenance, fact.source, _sha_text(fact.key),
                                                ", ".join(fact.derived_from) or "—", status, "—"))))
    link = rr.SERIES_LINK_261016_261027
    span = link["unv_grid_span_m"]["261027"]
    rows.append(dict(zip(EVIDENCE_COLUMNS, (
        CHAIN_A, "the UNV grid of 261027 (a representation)", "unv_grid_261027",
        f"{1000 * span[0]:.1f} × {1000 * span[1]:.1f} mm at z {link['unv_z_m']['261027']} m", ps.INSTRUMENT_RECORD,
        f"{_UNV27[0]}", f"{_UNV27[0]}: {_UNV27[1]}", "—", "REPRESENTATION — NOT the physical window",
        "the PSV UNV grid is a representation, not a physical calibration (M11 §15.4); it never closes "
        "scan_window_offsets_mm or scan_metric_geometry"))))
    rows.append(dict(zip(EVIDENCE_COLUMNS, (
        CHAIN_B, "the existing FE model geometry", "fe_model_geometry",
        "X 0–301, Y 0–300, Z 0 mm; S4R, 3 mm mesh; normal +Z; uniform h 0.875 mm", "ESTABLISHED_IN_THE_MODEL",
        f"{_INP[0]} and the R6 extraction", f"{_INP[0]}: {_INP[1]}; manifest.json: {_M11.manifest.sha256}", "—",
        "MODEL RECORD — not physical evidence", "the model has no physical landmark"))))
    edges = ps._T["side_means"]
    rows.append(dict(zip(EVIDENCE_COLUMNS, (
        CHAIN_B, "a measured geometric asymmetry that tells the orientations apart", "fe_measured_asymmetry",
        f"none in M11 (homogeneous, uniform thickness): candidates A–D are symmetry-equivalent; measured edge means "
        f"{min(edges.values()):.3f}–{max(edges.values()):.3f} mm exist only in the specimen record",
        NOT_AVAILABLE, "M11 §15.2; plate_study.SPECIMEN_RECORD", NOT_AVAILABLE, "—", "NOT_AVAILABLE",
        "no FE variant carries a measured asymmetry; A–D are not chosen by MAC, frequency or shape"))))
    return readiness, tuple(rows)


def _generic_evidence(inputs: ReviewInputs) -> tuple:
    study = inputs.study
    result = wb.evidence_result(study)
    by_key = {f.key: f for f in study.evidence}
    missing = dict(result.missing)
    rows = []
    for chain, keys in ((CHAIN_A, gev.SCAN_FACTS), (CHAIN_B, gev.FE_FACTS)):
        for key in keys:
            fact = by_key.get(key)
            status = "OPEN" if key in missing else "ESTABLISHED"
            rows.append(dict(zip(EVIDENCE_COLUMNS, (
                chain, gev.WHY.get(key, key), key, "—" if fact is None else gev.fact_text(key, fact.value),
                NOT_VERIFIED if fact is None else fact.provenance, "—" if fact is None else (fact.source or "—"),
                f"{NOT_AVAILABLE} (no file hash recorded with the fact)", "—" if fact is None else
                (", ".join(fact.derived_from) or "—"), status, missing.get(key, "—")))))
    return result, tuple(rows)


def open_facts(evidence_rows: Sequence[Mapping[str, Any]]) -> tuple:
    """The facts of chains A and B that are still open (in their order)."""
    return tuple(r["fact"] for r in evidence_rows if r["chain"] in (CHAIN_A, CHAIN_B) and r["status"] == "OPEN")


# ----------------------------------------------------------------------------- the owner's questions

QUESTION_COLUMNS = ("group", "id", "question", "closes", "acceptable_evidence", "answer", "answer_provenance",
                    "evidence_document", "evidence_document_sha256")
_M11_QUESTIONS = (
    ("A. The face of the plate", "A1",
     "Which absolute physical face of the plate faced the Polytec in the 261016 series: the face with the marking or "
     "the face without it?", ("scanned_face", "grid_plus_v_edge"),
     "one answer (marked / unmarked) with its source; the owner's same-face statement then carries it to 261027. "
     "'The same face as in 261016' is relative and does not answer it"),
    ("A. The face of the plate", "A2",
     "Which source document or confirmation establishes that face (for example a photograph of the mounted plate "
     "from the Polytec side with the marking visible, a laboratory record, the owner's own observation)?",
     ("scanned_face", "grid_plus_v_edge"), "the document is chosen in Source Audit; it is recorded by SHA-256 and its "
     "reading is confirmed by the owner"),
    ("B. The physical scan geometry", "B1",
     "Which of these existing materials is available: (a) the original 300by300_plate_only_1mm_ROTATED_261027.svd; "
     "(b) a PSV screenshot of 261016 with the points on the video frame; (c) the original scanner angles and the "
     "camera frame / scale; (d) other independently measured coordinates of the points?",
     ("scan_window_offsets_mm", "scan_metric_geometry"),
     "any one of (a)–(d); if none is available, both facts stay NOT_VERIFIED (the 277.7 × 277.0 mm UNV grid and the "
     "diagnostic 261016 reconstruction are never the physical window)"),
    ("C. The FE orientation", "C1",
     "Is there a measured physical landmark that ties FE (0, 0) to a specific corner of the plate?",
     ("fe_origin_corner", "fe_normal_face"), "a measured landmark recorded with its source"),
    ("C. The FE orientation", "C2",
     "If there is none: should a geometrically founded FE variant with a measured asymmetry (for example the measured "
     "edge thicknesses) be prepared? Naming a corner by agreement alone stays CONVENTION_ONLY and is never physical "
     "evidence.", ("fe_origin_corner", "fe_normal_face"),
     "an owner decision to prepare such a variant (its FE runs need their own authorisation)"),
)
_APPLICABILITY_GROUP = "D. The applicability of the model"


def owner_questions(inputs: ReviewInputs, evidence_rows) -> tuple:
    """One concrete question package from the open facts (a closed fact asks nothing). Every answer field is empty;
    no value is derived from a frequency."""
    still_open = set(open_facts(evidence_rows))
    out = []
    if inputs.profile.archive:
        for group, qid, text, closes, acceptable in _M11_QUESTIONS:
            if still_open & set(closes):
                out.append((group, qid, text, closes, acceptable))
    else:
        groups = {"scanned_face": "A. The face of the plate", "grid_plus_u_edge": "A. The face of the plate",
                  "grid_plus_v_edge": "A. The face of the plate",
                  "scan_window_offsets_mm": "B. The physical scan geometry",
                  "scan_scale": "B. The physical scan geometry",
                  "scan_metric_geometry": "B. The physical scan geometry", "measured_dof": "B. The physical scan "
                  "geometry", "fe_x_along_edges": "C. The FE orientation", "fe_origin_corner": "C. The FE orientation",
                  "fe_normal_face": "C. The FE orientation"}
        counters: dict = {}
        for key in [k for k in gev.FACT_KEYS if k in still_open]:
            group = groups[key]
            counters[group] = counters.get(group, 0) + 1
            out.append((group, f"{group[0]}{counters[group]}", f"What independent evidence establishes "
                        f"{gev.WHY[key]}? Which document or confirmation records it?", (key,),
                        "MEASURED, INSTRUMENT_RECORD or HUMAN_CONFIRMED evidence with its source; a convention, a "
                        "candidate or a derivation from frequencies never closes it"))
    number = 0
    for key, question, value, provenance, source, state in inputs.applicability:
        if state in ("RECORDED",):
            continue
        number += 1
        out.append((_APPLICABILITY_GROUP, f"D{number}", f"Please state {question}. Recorded now: {value}.", (key,),
                    f"a measurement or record with its source; {NOT_FROM_FREQUENCIES}"))
    return tuple(dict(zip(QUESTION_COLUMNS, (group, qid, text, list(closes), acceptable, None, None, None, None)))
                 for group, qid, text, closes, acceptable in out)


# ----------------------------------------------------------------------------- modal evidence

MODAL_COLUMNS = ("kind", "record", "frequency_hz", "fitted_set", "nearest", "difference_percent", "diagnostic",
                 "close_group", "research_mac", "archived_research_status", "pair", "history")


def _groups_of(groups) -> dict:
    return {member: "/".join(group) for group in groups for member in group}


def _s4_history() -> dict:
    """{branch: text} of the PRIORITY-2 tracking: lost branches and the permutations caught (archived)."""
    rows = _archive_csv("S4_TRACKING", REPO)
    lost, moved, cluster = {}, {}, {}
    for r in rows:
        if r["status"].startswith("BRANCH_LOSS"):
            lost.setdefault(r["branch"], []).append(r["variant"])
        if r.get("permutation") == "YES":
            moved.setdefault(r["branch"], []).append(f"{r['variant']} → {r['variant_modes']}")
        if r["status"] == "TRACKED_CLUSTER":
            cluster.setdefault(r["branch"], set()).add(r["variant_modes"])
    out = {}
    for branch in set(lost) | set(moved) | set(cluster):
        parts = [f"tracked only as the confirmed cluster term {', '.join(sorted(cluster[branch]))} (its members "
                 "exchange when E1 ≠ E2)"] if branch in cluster else []
        if branch in lost:
            parts.append("identity lost in " + ", ".join(lost[branch]))
        if branch in moved:
            parts.append("order exchanged: " + "; ".join(moved[branch]))
        out[branch] = "PRIORITY-2: " + "; ".join(parts)
    return out


def modal_evidence(inputs: ReviewInputs, snapshot: Optional[rrr.Snapshot]) -> dict:
    diagnostics = wb.modal_diagnostics(inputs.records, inputs.fe_elastic, inputs.fe_rigid, "review")
    exp_groups, fe_groups = _groups_of(diagnostics["experimental_close_groups"]), _groups_of(
        diagnostics["fe_close_groups"])
    archive_rows = {}
    if snapshot is not None and inputs.profile.archive:
        archive_rows = {r.exp_no: r for r in snapshot.matching["PLATE"]}
    history = {}
    if inputs.profile.archive:
        try:
            history = _s4_history()
        except ArchiveRefused as error:
            history = {"*": f"{NOT_AVAILABLE}: {error}"}
    fitted = (f"{inputs.modal_set} — fitted modal records" if inputs.modal_set else NOT_AVAILABLE)
    rows = []
    for p in diagnostics["proximity"]:
        record = next(r for r in inputs.records if r["number"] == p["exp"])
        archived = archive_rows.get(p["exp"])
        rows.append(dict(zip(MODAL_COLUMNS, (
            "EXP", f"EXP{p['exp']}", round(p["f_exp_hz"], 6),
            fitted + ("" if record.get("admissible", True) else " (record flagged provisional / ambiguous)"),
            f"FE{p['nearest'][0]} {p['nearest'][1]:.4f} Hz" if p["nearest"] else "—",
            round(p["nearest"][2], 3) if p["nearest"] else None, PROXIMITY_ONLY,
            exp_groups.get(f"EXP{p['exp']}", "—"),
            f"{archived.research_mac} — {RESEARCH_MAC}" if archived is not None and archived.research_mac else
            NOT_AVAILABLE, f"PRIORITY-1: {archived.status} (research; not a pair)" if archived is not None else
            NOT_AVAILABLE, "NONE — no admissible registration", "—"))))
    for m in inputs.fe_elastic:
        key = f"FE{m['number']}"
        rows.append(dict(zip(MODAL_COLUMNS, (
            "FE elastic", key, round(m["hz"], 6), inputs.profile.fe_model, "—", None, "FE frequency (no pair)",
            fe_groups.get(key, "—"), "—", "—", "NONE", history.get(key, "—")))))
    first_exp = inputs.records[0] if inputs.records else None
    first_fe = inputs.fe_elastic[0] if inputs.fe_elastic else None
    statements = [
        "No mode pair: no physical registration is accepted, so no EXP↔FE MAC is computed and no pair is formed.",
        "Frequency proximity never raises the status of a correspondence; the nearest FE frequency is diagnostic.",
        "FIT / HOLDOUT: none declared — no confirmed set exists, and none is formed automatically.",
        "Rigid-body FE modes are separated by the code's shape criterion: " + (", ".join(
            f"FE{n}" for n in inputs.fe_rigid) or "none") + ".",
    ]
    numbers = sorted([int(n) for n in inputs.fe_rigid] + [m["number"] for m in inputs.fe_elastic])
    if numbers:
        statements.append(f"FE modes in the data read: {len(numbers)} (FE{numbers[0]}–FE{numbers[-1]}); "
                          f"{len(inputs.fe_elastic)} elastic.")
    if first_exp and first_fe:
        statements.append(f"EXP{first_exp['number']} = {first_exp['hz']:.4f} Hz and FE{first_fe['number']} = "
                          f"{first_fe['hz']:.5f} Hz differ by {100 * (first_fe['hz'] / first_exp['hz'] - 1):+.2f} %: "
                          "FREQUENCY_ONLY_DIAGNOSTIC — not a confirmed pair.")
    if inputs.profile.archive:
        statements.append("The PRIORITY-1 research MAC rests on the 261016 diagnostic reconstruction carried by the "
                          f"DERIVED point map: it is shown only as {RESEARCH_MAC} and enters no identification.")
    return {"rows": rows, "experimental_records": len(inputs.records), "fe_elastic_modes": len(inputs.fe_elastic),
            "fe_rigid_excluded": list(inputs.fe_rigid), "fitted_set": fitted,
            "experimental_close_groups": diagnostics["experimental_close_groups"],
            "fe_close_groups": diagnostics["fe_close_groups"],
            "archived_clusters": [dict(zip(("pair", "status"), c)) for c in ARCHIVED_CLUSTERS]
            if inputs.profile.archive else [],
            "registration": f"NONE ACCEPTED — {REGISTRATION_NOT_VERIFIED}", "mac": "NOT_COMPUTED",
            "pairs": [], "fit_holdout": "NOT_DECLARED", "statements": statements}


# ----------------------------------------------------------------------------- observability

def _rank(matrix: np.ndarray, names) -> dict:
    sv = np.linalg.svd(matrix, compute_uv=False)
    return {"parameters": list(names), "rank": int(np.sum(sv > RCOND * sv[0])) if sv.size else 0,
            "condition": float(sv[0] / sv[-1]) if sv.size and sv[-1] > 0 else None,
            "singular_values": [float(v) for v in sv], "terms": int(matrix.shape[0])}


def observability(inputs: ReviewInputs, snapshot: Optional[rrr.Snapshot], fe_is_baseline: bool) -> dict:
    fe_only = []
    if inputs.profile.archive and snapshot is not None:
        source = "PRIORITY-2 central ±5 % sensitivities of M11 (six real Abaqus solves; the tracked terms)"
        for r in (snapshot.rank_full, snapshot.rank_restricted):
            fe_only.append({"parameters": " / ".join(r["parameters"]), "rank": r["rank"],
                            "of": len(r["parameters"]), "condition": round(r["condition"], 2), "terms": r["terms"],
                            "basis": source, "valid_for": f"{_M11.member_id} (free-free, h 0.875 mm) only"
                            + ("" if fe_is_baseline else " — NOT the current FE model: not applicable"),
                            "status": FE_ONLY if fe_is_baseline else f"{NOT_AVAILABLE} for the current FE model"})
    elif inputs.study is not None and inputs.study.sensitivities:
        from services import generic_plate_offline_study as off

        try:  # the offline study's own check: the table must be this study's FE model and specimen
            table = off.load_sensitivities(inputs.study.sensitivities["data"], inputs.study)
            names = list(table["parameters"])
            tracked = [r for r in table["rows"].values() if r["tracked"]]
            rank = _rank(np.array([[r["s"][n] for n in names] for r in tracked], dtype=float), names)
            fe_only.append({"parameters": " / ".join(names), "rank": rank["rank"], "of": len(names),
                            "condition": None if rank["condition"] is None else round(rank["condition"], 2),
                            "terms": rank["terms"], "basis": "the study's imported FE sensitivity table "
                            f"({table['sha256'][:12]}…, tracked rows)",
                            "valid_for": f"the FE model {str(table['fe_model'].get('name'))} only", "status": FE_ONLY})
        except (off.OfflineRefused, KeyError, TypeError, ValueError) as error:
            fe_only.append({"parameters": "—", "rank": None, "of": None, "condition": None, "terms": 0,
                            "basis": f"the imported table is refused ({error})", "valid_for": "—",
                            "status": NOT_AVAILABLE})
    statement = ("FE-only: the rank says which parameters the FE model distinguishes with the chosen modes. It does "
                 "not say that the experiment determines them.")
    experimental = {"status": NOT_ASSESSED,
                    "reason": "no accepted physical registration and no admissible mode pair: no physical uncertainty "
                              "of E or G12 is computed from an unconfirmed pair"}
    hypotheses = []
    if inputs.profile.archive and snapshot is not None:
        for s in snapshot.scenarios:
            hypotheses.append({"scenario": s.key, "E1_MPa": s.E1, "E2_MPa": s.E2, "G12_MPa": s.G12,
                               "assumed_pairs": s.pairs, "status": HYPOTHESIS_LABELS,
                               "note": "an archived hypothesis (PRIORITY-3 / -4); never a material property, never "
                                       "a target, never chosen"})
    return {"fe_only": fe_only, "fe_only_statement": statement if fe_only else
            f"{NOT_AVAILABLE}: no FE sensitivity table of this FE model", "experimental": experimental,
            "hypotheses": hypotheses}


# ----------------------------------------------------------------------------- reuse of the archived sensitivities

REUSE_COLUMNS = ("existing_result", "parameterisation", "fe_identity", "branch_tracking", "reuse_status", "reason")


def _tracking_summary(rows, variant: str) -> str:
    mine = [r for r in rows if r["variant"] == variant]
    lost = sorted({r["branch"] for r in mine if r["status"].startswith("BRANCH_LOSS")}, key=lambda b: int(b[2:]))
    moved = sorted({f"{r['branch']}→{r['variant_modes']}" for r in mine if r.get("permutation") == "YES"})
    tracked = len({r["branch"] for r in mine if r["status"] in ("TRACKED", "TRACKED_CLUSTER")})
    return (f"{tracked} of {len({r['branch'] for r in mine})} branches tracked at FE-to-FE MAC ≥ 0.90"
            + (f"; lost: {', '.join(lost)}" if lost else "") + (f"; order exchanged: {', '.join(moved)}" if moved
                                                                 else ""))


def sensitivity_reuse(inputs: ReviewInputs, fe_is_baseline: bool) -> tuple:
    if not inputs.profile.archive:
        study = inputs.study
        if study is not None and study.sensitivities:
            sha = (study.sensitivities or {}).get("file_sha256", "")
            return (dict(zip(REUSE_COLUMNS, (
                f"the study's imported sensitivity table ({sha[:12]}…)", "as declared in the table",
                "the FE model the table names", "as recorded in the table (not re-checked here)",
                "USED_ONLY_FOR_THE_FE_MODEL_IT_NAMES", "never carried to another FE model, suspension or thickness"))),)
        return (dict(zip(REUSE_COLUMNS, ("none", "—", "—", "—", NOT_AVAILABLE,
                                         "no archived FE sensitivity of this plate exists"))),)
    not_this = "" if fe_is_baseline else " — the current FE model is NOT M11 S4R_0875_BASELINE: not applicable"
    try:
        runs, tracking = _archive_csv("S4_RUNS", REPO), _archive_csv("S4_TRACKING", REPO)
    except ArchiveRefused as error:
        return (dict(zip(REUSE_COLUMNS, ("PRIORITY-2 S4 central ±5 %", "—", "—", "—", NOT_AVAILABLE, str(error)))),)
    out = []
    for r in runs:
        out.append(dict(zip(REUSE_COLUMNS, (
            f"PRIORITY-2 {r['job']} (exit {r['exit_code']}, completed {r['sta_completed']})",
            f"{r['parameter']} = {float(r['value']):g} MPa (one *Elastic field, ±5 % of the baseline)",
            f"baseline INP {_M11.inp.sha256[:12]}… → INP {r['inp_sha256'][:12]}…, ODB {r['odb_sha256'][:12]}…",
            _tracking_summary(tracking, r["job"]),
            ("REUSABLE — FE-only observability at the M11 free-free baseline" if fe_is_baseline else NOT_AVAILABLE)
            + not_this,
            "a central ±5 % derivative of this FE model; valid only for it (free-free, h 0.875 mm, 3 mm S4R): never "
            "carried to a model with the suspension, the force sensor or another thickness without new solves"))))
    out.append(dict(zip(REUSE_COLUMNS, (
        "s_E (E1 = E2) = s_E1 + s_E2 (PRIORITY-2 table)", "E1 = E2 scaled together",
        "the same six solves (no joint E1 = E2 ±5 % solve exists)", "the E1 and E2 jobs above",
        "CONDITIONAL — a superposition of separate perturbations, not an independently solved E1 = E2 perturbation"
        + not_this,
        "PRIORITY-4 real solves along E1 = E2 (H1, H2 at −22 / −25 %) agreed with the log-linear approximation to ≤ "
        "0.32 %; that is not a ±5 % central check at the baseline, so a joint ±5 % pair (2 solves) is needed unless "
        "the owner accepts the superposition"))))
    for member in ps.PLATE_FE_FAMILY[1:5]:
        out.append(dict(zip(REUSE_COLUMNS, (
            f"PRIORITY-1 secant {member.member_id}", f"{member.changed}: {member.description.split(': ')[-1]}",
            f"INP {member.inp.sha256[:12]}…, manifest {member.manifest.sha256[:12]}…" if member.manifest else
            f"INP {member.inp.sha256[:12]}…", "FE-to-FE tracking of PRIORITY-1 (PLATE_FE_SENSITIVITY.csv)",
            "NOT_REUSABLE as a central derivative",
            ("a secant over ×2 / ×3: far outside the linear range of G12" if member.changed == "G12" else
             "a secant over −10 %: not a central derivative at the baseline")
            + "; it never replaces the S4 central ±5 % values"))))
    try:
        p4 = _archive_csv("P4_RUNS", REPO)
    except ArchiveRefused:
        p4 = []
    for r in p4:
        out.append(dict(zip(REUSE_COLUMNS, (
            f"PRIORITY-4 real solve {r['job']}", f"{r['parameter']} = {r['value']} MPa",
            f"INP {r['inp_sha256'][:12]}…, ODB {r['odb_sha256'][:12]}…",
            "14 of 14 branches tracked at FE-to-FE MAC ≥ 0.90 (PRIORITY-4)",
            "VERIFICATION_RECORD_ONLY — not a sensitivity",
            f"a check of the approximation at a hypothetical point ({HYPOTHESIS_LABELS}); not a derivative at the "
            "baseline"))))
    out.append(dict(zip(REUSE_COLUMNS, (
        "±2.5 % linearity repeat", "E (E1 = E2), G12", "—", "—", f"{NOT_AVAILABLE} — never run",
        "SPEC §6 S4 asks for it; it is a future stage with its own authorisation"))))
    return tuple(out)


# ----------------------------------------------------------------------------- FE applicability

APPLICABILITY_COLUMNS = ("variant", "available_inputs", "missing_inputs", "existing_fe_assets", "future_runs",
                         "owner_authorisation", "scientific_purpose")


def _m11_assets(variant: str) -> str:
    if variant == "A":
        return (f"the M11 package (manifest {_M11.manifest.sha256[:12]}…, INP {_M11.inp.sha256[:12]}…, ODB "
                f"{_M11.odb.sha256[:12]}…)")
    if variant == "E":
        wedge = next(m for m in ps.PLATE_FE_FAMILY if m.member_id == "S4R_WEDGE")
        return (f"{wedge.member_id}: INP {wedge.inp.sha256[:12]}… and .dat {wedge.dat.sha256[:12]}… (frequencies "
                "only; no extracted shapes)")
    return "none"


def fe_applicability(inputs: ReviewInputs) -> dict:
    rows = []
    if inputs.profile.archive:
        for v in pw.APPLICABILITY_VARIANTS:
            rows.append(dict(zip(APPLICABILITY_COLUMNS, (
                f"{v['variant']}. {v['name']}", "; ".join(v["values"]["confirmed"]) or "—",
                "; ".join(v["values"]["assumptions"]) or "—", _m11_assets(v["variant"]),
                ", ".join(name for name, _setting in v["jobs"]) or "none (exists)",
                AUTHORISATION if v["jobs"] else "not needed (no run)",
                v["purpose"] + (" — history only" if v["role"] == "boundary-condition history" else "")))))
        jobs = [dict(job, authorisation=AUTHORISATION, run_order=False) for job in pw.applicability_jobs()]
    else:
        fe = next((d for d in inputs.documents if d.role == FE_MANIFEST), None)
        rows.append(dict(zip(APPLICABILITY_COLUMNS, (
            "A. the linked FE model", "the study's linked FE results" if fe else NOT_AVAILABLE, "—",
            f"manifest {fe.sha256[:12]}…" if fe and fe.sha256 else NOT_AVAILABLE, "none (exists)",
            "not needed (no run)", "the reference of the study"))))
        for key, question, value, provenance, source, state in inputs.applicability:
            rows.append(dict(zip(APPLICABILITY_COLUMNS, (
                f"{key}", f"{value} ({provenance})" if state == "RECORDED" else "—",
                "—" if state == "RECORDED" else f"{question} ({state})", "none",
                "not planned here: an FE variant needs its own declared inputs", AUTHORISATION,
                f"does {key.replace('_', ' ')} move the elastic FE modes?"))))
        jobs = []
    m11 = inputs.profile.archive
    stages = (
        {"stage": "1. FE applicability", "purpose": "does the test set-up (suspension, sensor, thickness) move the "
         "elastic FE modes?", "existing_results": "variant A (the M11 package)" if m11 else "the linked FE model",
         "new_fe_runs": "4 (B ×2, D, E) + 2 optional (C, history only)" if m11 else "to be declared",
         "prerequisites": "the suspension and sensor data (questions D), or a research range declared before the run",
         "authorisation": AUTHORISATION},
        {"stage": "2. E / G sensitivities", "purpose": "central ±5 % derivatives of the adopted FE model",
         "existing_results": "PRIORITY-2: E1, E2, G12 ±5 % at the M11 free-free baseline (6 solves; FE8 / FE9 / FE20 "
         "lost when E1 ≠ E2)" if m11 else "none",
         "new_fe_runs": "M11 free-free kept: G12 0 (reuse) + E (E1 = E2) 2 (or 0 if the owner accepts the "
                        "superposition); another adopted model (B / D / E): 4" if m11 else "4 (2 parameters × ±5 %)",
         "prerequisites": "the adopted FE model; for a fit also a frozen registration and confirmed pairs",
         "authorisation": AUTHORISATION},
        {"stage": "3. Linearity of the sensitivities", "purpose": "the ±2.5 % repeat (SPEC §6 S4)",
         "existing_results": "none (PRIORITY-4 checked the approximation far from the baseline, not ±2.5 %)" if m11
         else "none", "new_fe_runs": "4", "prerequisites": "stage 2", "authorisation": AUTHORISATION},
        {"stage": "4. Bounded fit (future)", "purpose": "a declared campaign (question, τ_mf, Σ, bounds) and the "
         "bounded LM with branch tracking", "existing_results": "S0 / H1 / H2 are hypotheses only" if m11 else "none",
         "new_fe_runs": "≤ 12", "prerequisites": "a frozen registration, confirmed pairs, FIT / HOLDOUT frozen before "
         "the fit, stages 2–3", "authorisation": AUTHORISATION},
        {"stage": "5. Check of the final FE model", "purpose": "one real solve of the final candidate with FE-to-FE "
         "tracking of every branch (as PRIORITY-4 did for S0 / H1 / H2)", "existing_results": "none",
         "new_fe_runs": "1 per final candidate", "prerequisites": "stage 4", "authorisation": AUTHORISATION},
    )
    return {"status": PLAN_ONLY, "variants": rows, "stages": list(stages), "jobs": jobs,
            "never": ["no INP is written with invented suspension or sensor characteristics",
                      "no value is fitted from 18.6307 or 33.4491 Hz" if m11 else "no value is fitted from a frequency",
                      "no plan here is a permission to run Abaqus"]}


# ----------------------------------------------------------------------------- the dossier

def build_review(inputs: ReviewInputs) -> dict:
    """The JSON-ready dossier of one plate (deterministic apart from ``created``)."""
    profile = inputs.profile
    audit = audit_sources(inputs)
    source_state = sources_state(audit, inputs.kind)
    if profile.archive:
        refused = [r for r in audit if r["role"] in (EXPERIMENTAL, FE_MANIFEST) and r["state"] != VERIFIED]
        if refused:
            raise ReviewRefused("SOURCE_NOT_VERIFIED: " + "; ".join(f"{r['role']}: {r['state']}" for r in refused))
        if inputs.modal_set != profile.modal_set or len(inputs.records) != profile.records:
            raise ReviewRefused(f"SOURCE_NOT_VERIFIED: the modal set must be {profile.modal_set} with "
                                f"{profile.records} records (read: {inputs.modal_set}, {len(inputs.records)})")
        if len(inputs.fe_elastic) != profile.fe_elastic:
            raise ReviewRefused(f"SOURCE_NOT_VERIFIED: M11 has {profile.fe_elastic} elastic modes FE7–FE20 (read "
                                f"{len(inputs.fe_elastic)})")
        readiness, evidence_rows = _m11_evidence(inputs)
        registration = readiness.status
        checks = [dict(zip(("check", "state", "detail"), c)) for c in readiness.checks]
        closing = [dict(zip(("facts", "evidence"), c)) for c in rr.CLOSING_EVIDENCE]
    else:
        result, evidence_rows = _generic_evidence(inputs)
        registration = result.status
        checks = [dict(zip(("check", "state", "detail"), c)) for c in result.checks]
        closing = []
    snapshot, snapshot_note = None, NOT_AVAILABLE
    if profile.archive:
        try:
            snapshot = rrr.load_snapshot(REPO)
            snapshot_note = "the PRIORITY-1–4 archive, each file read with its recorded SHA-256"
        except rrr.SnapshotRefused as error:
            snapshot_note = f"{NOT_AVAILABLE}: {error}"
    fe_doc = next((d for d in inputs.documents if d.role == FE_MANIFEST), None)
    inp_doc = next((d for d in inputs.documents if d.role == FE_INP), None)
    fe_is_baseline = bool(profile.archive and fe_doc and fe_doc.sha256 == _M11.manifest.sha256
                          and (inp_doc is None or inp_doc.sha256 == _M11.inp.sha256))
    questions = owner_questions(inputs, evidence_rows)
    modal = modal_evidence(inputs, snapshot)
    observe = observability(inputs, snapshot, fe_is_baseline)
    reuse = sensitivity_reuse(inputs, fe_is_baseline)
    applicability = fe_applicability(inputs)
    if inputs.kind == wb.SYNTHETIC_DEMO:
        review_state = SYNTHETIC_ONLY
    else:
        review_state = READY_FOR_OWNER_REVIEW if source_state == SOURCES_VERIFIED else SOURCE_NOT_VERIFIED
    states = {"sources": source_state, "registration": registration, "mode_pairs": MODE_PAIRS_NOT_CONFIRMED,
              "identification": NOT_READY, "review_package": review_state}
    identity = {"profile": profile.key, "specimen": profile.specimen, "series": profile.series,
                "modal_set": inputs.modal_set or NOT_AVAILABLE, "fe_model": profile.fe_model,
                "experimental_sha256": next((d.sha256 for d in inputs.documents if d.role == EXPERIMENTAL), None)
                or NOT_AVAILABLE, "fe_manifest_sha256": fe_doc.sha256 if fe_doc else NOT_AVAILABLE,
                "inp_sha256": inp_doc.sha256 if inp_doc else NOT_AVAILABLE, "kind": inputs.kind}
    record = {
        "schema": SCHEMA, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "labels": list(LABELS) + ([wb.SYNTHETIC_LABEL] if inputs.kind == wb.SYNTHETIC_DEMO else []),
        "identity": identity, "fingerprint": fingerprint(inputs), "states": states,
        "state_notes": [OWNER_REVIEW_NOTE, "No registration, mode pair, MAC, FIT / HOLDOUT set, fit or material value "
                        "is created by this review."],
        "scientific_status": SCIENTIFIC_STATUS,
        "sources": {"audit": list(audit), "state": source_state, "archive": snapshot_note,
                    "archive_files": [dict(zip(("file", "sha256", "state"), r)) for r in archive_check()]
                    if profile.archive else []},
        "evidence": {"registration": registration, "rows": list(evidence_rows), "open_facts": list(
            open_facts(evidence_rows)), "checks": checks, "closing_evidence": closing,
            "rules": ["MEASURED, INSTRUMENT_RECORD and HUMAN_CONFIRMED are independent evidence; DERIVED only when "
                      "everything it rests on is; CANDIDATE, CONVENTION_ONLY and NOT_VERIFIED never are",
                      "a relative fact (the same face, the same points) carries the reference series' evidence over "
                      "and never raises it",
                      "the UNV grid is a representation, not the physical window; a diagnostic reconstruction is not "
                      "a measured geometry; the candidates A–D are not physical facts"]},
        "test_conditions": ([c.__dict__ for c in ps.EXPERIMENT_CONDITIONS] if profile.archive else []),
        "not_established": list(ps.NOT_ESTABLISHED_BY_THE_CONDITIONS) if profile.archive else [],
        "applicability_facts": [dict(zip(("key", "question", "value", "provenance", "source", "state"), a))
                                for a in inputs.applicability],
        "owner_evidence_request": {"questions": list(questions),
                                   "instructions": "Answer each question with its source; leave a question empty when "
                                                   "nothing exists. No value is derived from a frequency."},
        "modal_evidence": modal, "observability": observe, "sensitivity_reuse": list(reuse),
        "fe_applicability_plan": applicability,
        "blocking": _blocking(states, evidence_rows, inputs),
    }
    return record


def _blocking(states, evidence_rows, inputs) -> list:
    out = []
    if states["sources"] == SOURCE_NOT_VERIFIED:
        out.append("the sources are not verified by SHA-256")
    for fact in open_facts(evidence_rows):
        out.append(f"open registration fact: {fact}")
    out.append("no accepted physical registration: no MAC, no mode pair, no FIT / HOLDOUT")
    for key, _question, _value, _provenance, _source, state in inputs.applicability:
        if state != "RECORDED":
            out.append(f"FE applicability: {key} {state}")
    out.append("M8 GATE NOT_MET; D-077 NO_GLOBAL_PARAMETER_VALUE; production Auto-ID BLOCKED")
    return out


def review_state(record: Mapping[str, Any], current_fingerprint: Optional[str]) -> str:
    """CURRENT when the dossier was built from the inputs present now, else STALE (never shown as current)."""
    return "CURRENT" if current_fingerprint and record.get("fingerprint") == current_fingerprint else "STALE"


# ----------------------------------------------------------------------------- export, save and reopen

def verify_on_disk(record: Mapping[str, Any]) -> list:
    """Every document of the dossier hashed again now: [(role, path, state)]; nothing is written."""
    out = []
    for row in record.get("sources", {}).get("audit", ()):
        path = row.get("path")
        if not path:
            continue
        sha, _size = hash_file(path)
        state = (MISSING if sha is None else VERIFIED if sha == row.get("sha256") else CHANGED)
        out.append((row["role"], path, state))
    return out


def reopened_state(record: Mapping[str, Any]) -> dict:
    """The state of a reopened dossier: the documents verified on disk now. A changed or missing experimental file or
    FE manifest makes it NOT_CURRENT (SOURCE_NOT_VERIFIED); the stored statuses are never trusted otherwise."""
    checks = verify_on_disk(record)
    required = [c for c in checks if c[0] in (EXPERIMENTAL, FE_MANIFEST)]
    bad = [c for c in checks if c[2] != VERIFIED]
    current = (record.get("identity", {}).get("kind") == wb.SYNTHETIC_DEMO or bool(required)) and not bad
    return {"checks": checks, "current": current,
            "state": "CURRENT" if current else f"NOT_CURRENT — {SOURCE_NOT_VERIFIED}",
            "reasons": [f"{role} {path}: {state}" for role, path, state in bad]}


def save_review(record: Mapping[str, Any], path) -> Path:
    path = Path(path)
    _atomic_write(path, json.dumps(record, indent=2, ensure_ascii=False, default=str))
    return path


def open_review(path) -> dict:
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ReviewRefused(f"{path} cannot be read as a review ({error})", "NOT_A_REVIEW") from error
    if not isinstance(record, dict) or record.get("schema") != SCHEMA:
        raise ReviewRefused(f"{path} is not a physical readiness review ({SCHEMA})", "NOT_A_REVIEW")
    return record


def _atomic_write(target: Path, text: str) -> None:
    handle, temporary = tempfile.mkstemp(prefix=".~review_", suffix=target.suffix, dir=target.parent)
    os.close(handle)
    try:
        Path(temporary).write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.remove(temporary)


def _csv_text(columns, rows) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow(["" if v is None else (", ".join(map(str, v)) if isinstance(v, (list, tuple)) else v)
                         for v in row])
    return buffer.getvalue()


_IDENTITY_COLUMNS = ("specimen", "series", "fe_model", "experimental_sha256", "fe_manifest_sha256")


def _identity_values(record) -> list:
    return [record["identity"].get(k) for k in _IDENTITY_COLUMNS]


def documents(record: Mapping[str, Any]) -> dict:
    """{file name: text} of the dossier's documents (the seven, and the machine-readable owner request)."""
    ident = _identity_values(record)
    evidence = _csv_text(_IDENTITY_COLUMNS + EVIDENCE_COLUMNS,
                         [ident + [r[c] for c in EVIDENCE_COLUMNS] for r in record["evidence"]["rows"]])
    modal = _csv_text(_IDENTITY_COLUMNS + MODAL_COLUMNS,
                      [ident + [r[c] for c in MODAL_COLUMNS] for r in record["modal_evidence"]["rows"]])
    reuse = _csv_text(_IDENTITY_COLUMNS + REUSE_COLUMNS,
                      [ident + [r[c] for c in REUSE_COLUMNS] for r in record["sensitivity_reuse"]])
    plan = {"schema": SCHEMA + "/fe-applicability-plan", "identity": record["identity"],
            "status": PLAN_ONLY, **record["fe_applicability_plan"]}
    request = {"schema": SCHEMA + "/owner-evidence-request", "identity": record["identity"],
               "states": record["states"], **record["owner_evidence_request"]}
    return {"physical_readiness.json": json.dumps(record, indent=2, ensure_ascii=False, default=str) + "\n",
            "evidence_matrix.csv": evidence, "modal_observations.csv": modal, "sensitivity_reuse.csv": reuse,
            "fe_applicability_plan.json": json.dumps(plan, indent=2, ensure_ascii=False, default=str) + "\n",
            "OWNER_EVIDENCE_REQUEST.md": owner_request_markdown(record),
            "PHYSICAL_READINESS_REPORT.md": report_markdown(record),
            "owner_evidence_request.json": json.dumps(request, indent=2, ensure_ascii=False, default=str) + "\n"}


REQUIRED_DOCUMENTS = ("physical_readiness.json", "evidence_matrix.csv", "modal_observations.csv",
                      "sensitivity_reuse.csv", "fe_applicability_plan.json", "OWNER_EVIDENCE_REQUEST.md",
                      "PHYSICAL_READINESS_REPORT.md")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def export_dossier(record: Mapping[str, Any], folder, current_fingerprint: Optional[str] = None) -> tuple:
    """Write the dossier into a new sub-folder of ``folder`` (atomic: a temporary folder renamed at the end; never
    overwritten). Refused, with nothing written, for a folder inside the program tree, a STALE dossier or a source that
    changed on disk."""
    folder = Path(folder)
    if not folder.is_dir():
        raise ExportRefused(f"{folder} is not an existing folder")
    if _inside(folder, REPO):
        raise ExportRefused(f"{folder} is inside the program folder {REPO}: choose a folder outside it")
    if current_fingerprint is not None and review_state(record, current_fingerprint) != "CURRENT":
        raise ExportRefused("the review was built for other inputs (STALE): build it again before exporting")
    bad = [c for c in verify_on_disk(record) if c[2] != VERIFIED]
    if bad:
        raise ExportRefused("a source changed or is missing on disk: " + "; ".join(f"{r} {p}: {s}" for r, p, s in bad))
    specimen = re.sub(r"[^A-Za-z0-9._-]+", "_", str(record["identity"].get("specimen") or "plate"))
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = folder / f"physical_readiness_{specimen}_{stamp}"
    index = 2
    while target.exists():
        target = folder / f"physical_readiness_{specimen}_{stamp}_{index}"
        index += 1
    temporary = Path(tempfile.mkdtemp(prefix=".~physical_readiness_", dir=folder))
    try:
        for name, text in documents(record).items():
            (temporary / name).write_text(text, encoding="utf-8", newline="\n")
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
    return tuple(sorted(target.iterdir()))


# ----------------------------------------------------------------------------- Markdown

def _md_table(columns, rows) -> list:
    def cell(value):
        text = "—" if value is None or value == "" else (", ".join(map(str, value)) if isinstance(value, (list, tuple))
                                                         else str(value))
        return text.replace("|", "/").replace("\n", " ")
    return ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)] + [
        "| " + " | ".join(cell(v) for v in row) + " |" for row in rows]


def _identity_lines(record) -> list:
    i = record["identity"]
    return [f"- Specimen: {i['specimen']}", f"- Series: {i['series']}", f"- Modal set: {i['modal_set']}",
            f"- FE model: {i['fe_model']}", f"- Experimental SHA-256: {i['experimental_sha256']}",
            f"- FE manifest SHA-256: {i['fe_manifest_sha256']}", f"- INP SHA-256: {i['inp_sha256']}",
            f"- Review fingerprint: {record['fingerprint']}"]


def owner_request_markdown(record: Mapping[str, Any]) -> str:
    lines = [f"# Owner evidence request — {record['identity']['specimen']}", ""] + _identity_lines(record) + [
        "", "States: " + " · ".join(record["states"].values()), "",
        record["owner_evidence_request"]["instructions"], ""]
    group = None
    for q in record["owner_evidence_request"]["questions"]:
        if q["group"] != group:
            group = q["group"]
            lines += [f"## {group}", ""]
        lines += [f"### {q['id']}. {q['question']}", "", f"- Closes: {', '.join(q['closes'])}",
                  f"- Acceptable evidence: {q['acceptable_evidence']}", "- Answer: ", "- Source of the answer: ",
                  "- Evidence document (path and SHA-256): ", ""]
    if not record["owner_evidence_request"]["questions"]:
        lines.append("No open question: every fact is closed by independent evidence (not a frozen registration).")
    return "\n".join(lines) + "\n"


def report_markdown(record: Mapping[str, Any]) -> str:
    states = record["states"]
    lines = [f"# Physical readiness report — {record['identity']['specimen']}", "",
             "Labels: " + " / ".join(record["labels"]), "", *_identity_lines(record), "",
             "## States", ""] + [f"- {k}: **{v}**" for k, v in states.items()] + [
        "", *[f"- {n}" for n in record["state_notes"]], "", f"Scientific status: {record['scientific_status']}", "",
        "## 1. Sources", ""]
    lines += _md_table(("Role", "Path", "SHA-256", "Size", "Origin", "May support", "State"),
                       [(r["role"], r["path"], r["sha256"], r["size"], r["origin"], r["supports"], r["state"])
                        for r in record["sources"]["audit"]])
    lines += ["", f"Archive: {record['sources']['archive']}", "", "## 2. Evidence A / B", "",
              f"Registration: **{record['evidence']['registration']}**. Open facts: "
              + (", ".join(record["evidence"]["open_facts"]) or "none"), ""]
    lines += _md_table(("Chain", "Fact", "Value", "Provenance", "Status", "Blocking reason"),
                       [(r["chain"], r["fact"], r["value"], r["provenance"], r["status"], r["blocking_reason"])
                        for r in record["evidence"]["rows"]])
    lines += [""] + [f"- {rule}" for rule in record["evidence"]["rules"]]
    if record["evidence"]["closing_evidence"]:
        lines += ["", "What would close the open facts (existing records):", ""] + [
            f"- {c['facts']}: {c['evidence']}" for c in record["evidence"]["closing_evidence"]]
    if record["test_conditions"]:
        lines += ["", "## Test conditions (261016 history, 261027 primary)", ""]
        lines += _md_table(("Series", "Item", "Value", "Provenance", "Source"),
                           [(c["series"], c["item"], c["value"], c["provenance"], c["source"])
                            for c in record["test_conditions"]])
        lines += ["", "Not established by the conditions:", ""] + [f"- {x}" for x in record["not_established"]]
    lines += ["", "## 3. Owner questions", "", f"{len(record['owner_evidence_request']['questions'])} questions: see "
              "OWNER_EVIDENCE_REQUEST.md (answer fields empty).", ""]
    lines += [f"- {q['id']} ({q['group']}): {q['question']}" for q in record["owner_evidence_request"]["questions"]]
    modal = record["modal_evidence"]
    lines += ["", "## 4. Modal evidence", "", f"- Experimental records: {modal['experimental_records']} "
              f"({modal['fitted_set']})", f"- Elastic FE modes: {modal['fe_elastic_modes']}; rigid-body excluded: "
              + (", ".join(f"FE{n}" for n in modal["fe_rigid_excluded"]) or "none"),
              f"- Registration: {modal['registration']}; MAC: {modal['mac']}; pairs: none; FIT / HOLDOUT: "
              f"{modal['fit_holdout']}", ""] + [f"- {s}" for s in modal["statements"]] + [""]
    lines += _md_table(("Kind", "Record", "Hz", "Nearest", "Δf %", "Diagnostic", "Close group", "Research MAC",
                        "Pair", "History"),
                       [(r["kind"], r["record"], r["frequency_hz"], r["nearest"], r["difference_percent"],
                         r["diagnostic"], r["close_group"], r["research_mac"], r["pair"], r["history"])
                        for r in modal["rows"]])
    observe = record["observability"]
    lines += ["", "## 5. Observability", "", observe["fe_only_statement"], ""]
    if observe["fe_only"]:
        lines += _md_table(("Parameters", "Rank", "Of", "Condition", "Terms", "Status", "Valid for"),
                           [(r["parameters"], r["rank"], r["of"], r["condition"], r["terms"], r["status"],
                             r["valid_for"]) for r in observe["fe_only"]])
    lines += ["", f"Experimental identifiability: **{observe['experimental']['status']}** — "
              f"{observe['experimental']['reason']}.", ""]
    if observe["hypotheses"]:
        lines += _md_table(("Scenario", "E1 MPa", "E2 MPa", "G12 MPa", "Assumed pairs", "Status"),
                           [(h["scenario"], h["E1_MPa"], h["E2_MPa"], h["G12_MPa"], h["assumed_pairs"], h["status"])
                            for h in observe["hypotheses"]])
    lines += ["", "## 6. Reuse of the archived sensitivities", ""]
    lines += _md_table(("Existing result", "Parameterisation", "FE identity", "Branch tracking", "Reuse status",
                        "Reason"), [tuple(r[c] for c in REUSE_COLUMNS) for r in record["sensitivity_reuse"]])
    plan = record["fe_applicability_plan"]
    lines += ["", f"## 7. FE applicability — {plan['status']}", ""]
    lines += _md_table(("Variant", "Available inputs", "Missing inputs", "Existing FE assets", "Future runs",
                        "Owner authorisation", "Purpose"),
                       [tuple(r[c] for c in APPLICABILITY_COLUMNS) for r in plan["variants"]])
    lines += [""]
    lines += _md_table(("Stage", "Purpose", "Existing results", "New FE runs", "Prerequisites", "Authorisation"),
                       [(s["stage"], s["purpose"], s["existing_results"], s["new_fe_runs"], s["prerequisites"],
                         s["authorisation"]) for s in plan["stages"]])
    lines += ["", "## 8. What blocks a physical identification", ""] + [f"- {b}" for b in record["blocking"]]
    return "\n".join(lines) + "\n"


__all__ = [name for name in dir() if not name.startswith("_") and name not in (
    "annotations", "csv", "dataclass", "datetime", "field", "hashlib", "io", "json", "math", "np", "os", "re",
    "replace", "shutil", "tempfile", "timezone", "Any", "Mapping", "Optional", "Path", "Sequence")]

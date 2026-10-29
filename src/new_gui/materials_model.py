"""NEW-GUI.6: the project's existing material evidence, read-only and classified, with no Qt.

This module reads committed project records only and computes nothing: no Auto-ID, no identification, no fit, no
uncertainty and no verdict is run. It never derives a material constant from a frequency. Every value shown is a
value of a record, with the record's own status, and is placed in one of three classes that are never mixed:

- **MATERIAL_IDENTIFICATION** — the governed answer to the material-identification question (SPEC v1.2 §1 A). The
  only governed records are the M7 campaign of the SP-02 / SP-13 family: each parameter's M5 verdict
  (``m5_verdict.verdicts`` of the result records) and the formal output of the D-076 correction (D-077):
  ``NO_GLOBAL_PARAMETER_VALUE``. No material value is identified, so none is shown in this class.
- **Specimen engineering calibration** — a released model-specific calibration (SPEC v1.2 §3a). Its class name is
  the campaign schema's own question name (``domain.campaign_definition.SCIENTIFIC_QUESTIONS``); it is not repeated
  here, and no calibration gate or output service is imported. The committed records are searched for the
  calibration record's schema; none exists, so the class is ``NOT_AVAILABLE``.
- **MODEL_INPUT / DIAGNOSTIC_ESTIMATE** — the governed FE models' ``*Elastic, ENGINEERING CONSTANTS`` (the source
  constants pinned to their INP SHA-256) and the historical diagnostic estimates of M7 (the RUN_A optimizer candidate,
  the RUN_B compensation test, the D-076 per-specimen diagnostics), each with its labels
  (``NOT_A_MATERIAL_PROPERTY``, ``NOT_A_RELEASE_VALUE``, ...). They are inputs or diagnostics, never accepted
  material constants.

The integrity of the M7 result records is checked against the canonical content hashes pinned by the D-076 record
(``domain.identification_run.canonical_hash``); a record that does not match is shown as NOT VERIFIED and its values
are not shown.

``current_relevance`` says what applies to the data read in the workspace (NEW-GUI.6-F1). A governed material record
belongs to its own forward model: the M7 records name, per specimen, the FE input (INP file and SHA-256) of their
forward-model manifest. A verified archived registration proves only the FE geometry identity, the experimental source
and the modal set; another FE model with the same mesh (other materials, other INP) passes it too. The read FE package
records no content identity of its ODB or INP, and neither geometry, MAC nor frequency proximity proves an FE model's
identity. So no material record is attributed to the read data: the answer is always NOT_AVAILABLE. When the verified
fixture is one the M7 records use, the historical M7 / D-077 result is named with its own provenance (its forward
model and FE input), explicitly not as a result of the read FE model. D-077, its formal refusal and the historical
diagnostic values are shown unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from domain.campaign_definition import MATERIAL_IDENTIFICATION, SCIENTIFIC_QUESTIONS

REPO_ROOT = Path(__file__).resolve().parents[2]
CORRECTION = "docs/auto_id/audit_corrections/M7_FAMILY_CONSISTENCY_CORRECTION.json"
PER_SPECIMEN = "docs/auto_id/audit_corrections/M7_PER_SPECIMEN_DIAGNOSTICS.json"
CAMPAIGNS = {"RUN_A": "docs/auto_id/campaigns/M7_RUN_A.campaign.json",
             "RUN_B": "docs/auto_id/campaigns/M7_RUN_B.campaign.json"}
CALIBRATION_SCHEMA_PREFIX = "auto-id/specimen-engineering-calibration/"
RECORDS_ROOT = "docs/auto_id"

# the second scientific question of the campaign schema (SPEC v1.2 §1 B), named by its owner
SPECIMEN_CALIBRATION = next(question for question in SCIENTIFIC_QUESTIONS if question != MATERIAL_IDENTIFICATION)
MODEL_INPUT = "MODEL_INPUT"
DIAGNOSTIC_ESTIMATE = "DIAGNOSTIC_ESTIMATE"
CLASSES = (MATERIAL_IDENTIFICATION, SPECIMEN_CALIBRATION, MODEL_INPUT, DIAGNOSTIC_ESTIMATE)
CLASS_TITLE = {
    MATERIAL_IDENTIFICATION: "Material identification (governed verdicts)",
    SPECIMEN_CALIBRATION: "Specimen engineering calibration",
    MODEL_INPUT: "Model input (FE material constants)",
    DIAGNOSTIC_ESTIMATE: "Diagnostic and historical estimates",
}
CLASS_NOTE = {
    MATERIAL_IDENTIFICATION: ("A material property is output only when the material-identification evidence "
                              "supports it (SPEC v1.2 §1 A). A refusal is a valid scientific result."),
    SPECIMEN_CALIBRATION: ("An effective parameter of one FE model of one specimen (SPEC v1.2 §3a): "
                           "NOT_A_MATERIAL_PROPERTY, NOT_TRANSFERABLE_WITHOUT_VALIDATION."),
    MODEL_INPUT: ("The constants the governed FE models were built with. They are inputs of the FE model, not "
                  "identified or validated material properties."),
    DIAGNOSTIC_ESTIMATE: ("Optimizer candidates and per-specimen estimates kept as diagnostics. None is a material "
                          "property or a release value, and none applies to other data."),
}
NOT_AVAILABLE = "NOT_AVAILABLE"
NO_GLOBAL_VALUE = "NO_GLOBAL_PARAMETER_VALUE"
NO_VALUE = "no value (refusal)"
UNITS = {"E_in_plane_mpa": "MPa", "G12_mpa": "MPa"}
CONSTANT_UNITS = {"E": "MPa", "G": "MPa", "n": "—"}
HEADERS = ("Parameter", "Value", "Unit", "Role", "Status / verdict", "Reason", "Uncertainty", "Model form",
           "Bound to", "Source")
ACCURACY_NOTE = ("The owner's engineering wish of about ±10 % does not change the governed rules: the IDENTIFIED / "
                 "WIDE / NOT_IDENTIFIABLE limits, the M8 block and D-077 are unchanged, and no value is produced from "
                 "a single frequency.")


@dataclass(frozen=True)
class EvidenceRow:
    klass: str
    parameter: str
    value: str
    unit: str
    role: str
    status: str
    reason: str
    uncertainty: str
    model_form: str
    bound_to: str
    source: str

    def cells(self) -> tuple:
        return (self.parameter, self.value, self.unit, self.role, self.status, self.reason, self.uncertainty,
                self.model_form, self.bound_to, self.source)


@dataclass(frozen=True)
class MaterialsView:
    rows: tuple
    formal_output: str
    fixtures: tuple  # archived fixture ids the governed M7 records are bound to
    problems: tuple  # records that could not be read or verified (their values are not shown)
    notes: tuple
    fixture_models: tuple = ()  # (fixture id, its M7 forward model and FE input), the records' own provenance

    def of(self, klass: str) -> tuple:
        return tuple(row for row in self.rows if row.klass == klass)


def _read(root: Path, relative: str) -> tuple[Any, str]:
    path = root / relative
    data = path.read_bytes()
    return json.loads(data.decode("utf-8")), hashlib.sha256(data).hexdigest()


def _source(relative: str, sha: str) -> str:
    return f"{relative} (file SHA-256 {sha[:12]}…)"


def _number(value) -> str:
    try:
        return f"{float(value):.6g}"
    except (TypeError, ValueError):
        return "—"


def _ln_sd(value) -> str:
    return "not available" if value is None else f"{float(value):.4g} (ln)"


def _model_form(robustness) -> str:
    if not isinstance(robustness, dict) or robustness.get("range_percent_of_p_hat") is None:
        return "not available"
    return f"LOO range {float(robustness['range_percent_of_p_hat']):.3g} % of p̂"


def _campaign_bindings(root: Path, run: str) -> tuple[str, tuple, tuple]:
    """'SP02 (SP02/bravo-1-physical, FE INP SP02_Modal_V02.inp 574ae78a…); ...', the fixture ids and, per fixture, its
    forward model and FE input."""
    from domain.campaign_definition import load_campaign_definition
    from domain.forward_model_manifest import load_forward_model_manifest

    raw, _ = _read(root, CAMPAIGNS[run])
    load_campaign_definition(root / CAMPAIGNS[run])  # the governed loader validates the definition
    parts, fixtures, models = [], [], []
    for member in raw.get("specimens") or ():
        manifest = load_forward_model_manifest(root / member["forward_model"])
        inp = manifest.model_input
        fixtures.append(str(member["fixture_id"]))
        parts.append(f"{member['label']} ({member['fixture_id']}; FE input {inp.file_name} {inp.sha256[:8]}…)")
        models.append((str(member["fixture_id"]), f"forward model {manifest.forward_model_id} "
                                                  f"({member['forward_model']}), FE input {inp.file_name} SHA-256 "
                                                  f"{inp.sha256[:12]}…"))
    return "; ".join(parts), tuple(fixtures), tuple(models)


def _verdict_rows(result: dict, run: str, bound: str, source: str, klass: str, formal: str) -> list:
    rows = []
    for parameter, verdict in sorted(((result.get("m5_verdict") or {}).get("verdicts") or {}).items()):
        reasons = "; ".join(str(r) for r in verdict.get("reasons") or ()) or "—"
        status = str(verdict.get("verdict"))
        if klass == MATERIAL_IDENTIFICATION and formal:
            status = f"{status}; formal output {formal}"
        rows.append(EvidenceRow(
            klass, parameter, NO_VALUE if verdict.get("reported_value") is None else _number(verdict["reported_value"]),
            UNITS.get(parameter, "—"), f"fitted parameter of M7 {run}", status, reasons,
            f"statistical sd {_ln_sd(verdict.get('statistical_sd_ln'))}; Birge-adjusted sd "
            f"{_ln_sd(verdict.get('birge_adjusted_sd_ln'))}; conservative {_ln_sd(verdict.get('conservative_ln'))}",
            _model_form(verdict.get("model_form_robustness")), bound, source))
    return rows


def _calibration_records(root: Path) -> list:
    """Committed JSON records whose schema is the specimen-engineering-calibration record's (relative paths)."""
    found = []
    for path in sorted((root / RECORDS_ROOT).rglob("*.json")):
        try:
            schema = json.loads(path.read_text(encoding="utf-8")).get("schema")
        except (OSError, ValueError, AttributeError):
            continue
        if isinstance(schema, str) and schema.startswith(CALIBRATION_SCHEMA_PREFIX):
            found.append(path.relative_to(root).as_posix())
    return found


def load_material_evidence(repo_root: Optional[Path] = None) -> MaterialsView:
    """Read and classify the committed material records; nothing is computed or written."""
    from domain.identification_run import canonical_hash

    root = REPO_ROOT if repo_root is None else Path(repo_root)
    rows, problems, fixtures, models, formal = [], [], (), (), NOT_AVAILABLE
    try:
        correction, correction_sha = _read(root, CORRECTION)
        interpretation = correction["corrected_interpretation"]
        formal = NO_GLOBAL_VALUE if str(interpretation["formal_output"]).startswith("NO GLOBAL PARAMETER VALUE") \
            else str(interpretation["formal_output"])
    except (OSError, ValueError, KeyError, TypeError) as error:
        correction, correction_sha, interpretation = None, "", {}
        problems.append(f"{CORRECTION}: not readable ({error}); no governed material result is shown.")
    results = {}
    if correction is not None:
        for run, key in (("RUN_A", "run_a"), ("RUN_B", "run_b")):
            entry = correction[key]
            relative = entry["result_record"]["path"]
            try:
                result, sha = _read(root, relative)
                if canonical_hash(result) != entry["result_record"]["canonical_content_sha256"]:
                    problems.append(f"{relative}: content does not match the hash pinned by {CORRECTION}; NOT "
                                    "VERIFIED, its values are not shown.")
                    continue
                bound, run_fixtures, run_models = _campaign_bindings(root, run)
            except (OSError, ValueError, KeyError, TypeError) as error:
                problems.append(f"{relative}: not readable ({error}).")
                continue
            results[run] = (result, sha, relative, bound, entry)
            fixtures = tuple(dict.fromkeys(fixtures + run_fixtures))
            models = tuple(dict.fromkeys(models + run_models))
    if "RUN_A" in results:  # the governed material-identification question (SPEC v1.2 §11: RUN_B is diagnostic)
        result, sha, relative, bound, entry = results["RUN_A"]
        family = entry["family_consistency"]
        rows += _verdict_rows(result, "RUN_A", bound, _source(relative, sha), MATERIAL_IDENTIFICATION, formal)
        rows.append(EvidenceRow(
            MATERIAL_IDENTIFICATION, "SP-02 / SP-13 family", NO_VALUE, "—", "family consistency (SPEC §13)",
            f"{entry['verdict']}; formal output {formal}",
            "; ".join(str(r) for r in interpretation.get("reasons") or ()) + (
                f"; Δχ² {float(family['delta_chi2']):.1f} (dof {family['delta_dof']})"
                if family.get("delta_chi2") is not None else ""),
            "—", "—", bound, _source(CORRECTION, correction_sha) + " (D-076, D-077)"))
    calibrations = _calibration_records(root)
    rows.append(EvidenceRow(
        SPECIMEN_CALIBRATION, "any", "—", "—", "—", NOT_AVAILABLE if not calibrations else "RECORD PRESENT",
        "no released specimen engineering calibration record exists in the project records" if not calibrations
        else "a calibration record exists; this view does not present it (open it with the Auto-ID tools): "
        + ", ".join(calibrations), "—", "—", "—",
        f"{RECORDS_ROOT}/**/*.json searched for the schema {CALIBRATION_SCHEMA_PREFIX}*"))
    rows += _model_inputs(root, problems)
    rows += _diagnostics(root, results, interpretation, correction_sha, problems)
    notes = (ACCURACY_NOTE,
             "Records are related to the read data only through the archived fixture the registration service "
             "verified; never by a name, a file name or a frequency.")
    return MaterialsView(rows=tuple(rows), formal_output=formal, fixtures=fixtures, fixture_models=models,
                         problems=tuple(problems),
                         notes=notes)


def _model_inputs(root: Path, problems: list) -> list:
    from domain.forward_model_manifest import load_forward_model_manifest

    rows, seen = [], set()
    for run in ("RUN_A",):
        try:
            raw, _ = _read(root, CAMPAIGNS[run])
        except (OSError, ValueError) as error:
            problems.append(f"{CAMPAIGNS[run]}: not readable ({error}).")
            return rows
        for member in raw.get("specimens") or ():
            relative = member["forward_model"]
            if relative in seen:
                continue
            seen.add(relative)
            try:
                manifest = load_forward_model_manifest(root / relative)
                _, sha = _read(root, relative)
            except (OSError, ValueError, KeyError, TypeError) as error:
                problems.append(f"{relative}: not readable ({error}).")
                continue
            inp = manifest.model_input
            bound = (f"{member['label']} FE model {manifest.forward_model_id} (input {inp.file_name}, SHA-256 "
                     f"{inp.sha256[:12]}…)")
            for name, value in manifest.source_engineering_constants.to_dict().items():
                rows.append(EvidenceRow(
                    MODEL_INPUT, name, _number(value), CONSTANT_UNITS.get(name[0], "—"),
                    f"*Elastic, ENGINEERING CONSTANTS ({manifest.material_role})", "MODEL_INPUT",
                    "the constant the FE model was built with; not identified, not validated", "—", "—", bound,
                    _source(relative, sha)))
    return rows


def _diagnostics(root: Path, results: dict, interpretation: dict, correction_sha: str, problems: list) -> list:
    rows = []
    if "RUN_A" in results and interpretation.get("historical_run_a_optimizer_candidate_mpa") is not None:
        bound = results["RUN_A"][3]
        rows.append(EvidenceRow(
            DIAGNOSTIC_ESTIMATE, "E_in_plane_mpa", _number(interpretation["historical_run_a_optimizer_candidate_mpa"]),
            "MPa", str(interpretation.get("label")), "DIAGNOSTIC_ONLY",
            "is not: " + ", ".join(str(item) for item in interpretation.get("is_not") or ()), "—", "—", bound,
            _source(CORRECTION, correction_sha)))
    if "RUN_B" in results:
        result, sha, relative, bound, _entry = results["RUN_B"]
        for parameter, verdict in sorted(((result.get("m5_verdict") or {}).get("verdicts") or {}).items()):
            rows.append(EvidenceRow(
                DIAGNOSTIC_ESTIMATE, parameter, _number(verdict.get("fitted_estimate")), UNITS.get(parameter, "—"),
                f"RUN_B {(result.get('engineering') or {}).get('estimate')} (diagnostic only, SPEC v1.2 §11)",
                f"{verdict.get('verdict')}; {result.get('material_claim')}",
                "; ".join(str(r) for r in verdict.get("reasons") or ()) or "—",
                f"statistical sd {_ln_sd(verdict.get('statistical_sd_ln'))}",
                _model_form(verdict.get("model_form_robustness")), bound, _source(relative, sha)))
    try:
        record, sha = _read(root, PER_SPECIMEN)
    except (OSError, ValueError) as error:
        problems.append(f"{PER_SPECIMEN}: not readable ({error}).")
        return rows
    labels = ", ".join(str(label) for label in record.get("labels") or ())
    for case, data in sorted(((record.get("run_a_per_specimen_estimates") or {}).get("cases") or {}).items()):
        if isinstance(data, dict) and data.get("estimate_mpa") is not None:
            rows.append(EvidenceRow(
                DIAGNOSTIC_ESTIMATE, "E_in_plane_mpa", _number(data["estimate_mpa"]), "MPa",
                f"RUN_A per-specimen linearised estimate: {case}", labels,
                "linearised about the historical RUN_A candidate; an approximation, not an FE optimum", "—", "—",
                ", ".join(str(row) for row in data.get("rows") or ()), _source(PER_SPECIMEN, sha)))
    for specimen, data in sorted((record.get("run_b_per_specimen") or {}).items()):
        estimate = data.get("estimate_mpa") if isinstance(data, dict) else None
        if isinstance(estimate, dict):
            for parameter, value in sorted(estimate.items()):
                rows.append(EvidenceRow(
                    DIAGNOSTIC_ESTIMATE, parameter, _number(value), UNITS.get(parameter, "—"),
                    f"RUN_B per-specimen estimate: {specimen}", labels, "rank {0}, dof {1}".format(
                        data.get("rank"), data.get("dof")), "—", "—", ", ".join(data.get("rows") or ()),
                    _source(PER_SPECIMEN, sha)))
        elif isinstance(data, dict):
            rows.append(EvidenceRow(
                DIAGNOSTIC_ESTIMATE, "E_in_plane_mpa, G12_mpa", "—", "MPa", f"RUN_B per-specimen: {specimen}",
                str(data.get("status")), str(data.get("note", "—")), "—", "—", ", ".join(data.get("rows") or ()),
                _source(PER_SPECIMEN, sha)))
    return rows


@dataclass(frozen=True)
class Relevance:
    status: str
    text: str
    historical: str = ""  # the historical record of the verified fixture, with its own provenance (never the read data's)


NOT_BOUND = ("The read FE package records no content identity of its ODB or INP, and neither the FE geometry, the "
             "experimental source, MAC nor frequency proximity proves that the read FE results are a governed record's "
             "forward model. No material record is attributed to the read data.")


def current_relevance(view: MaterialsView, verified_fixture: Optional[str], data_read: bool) -> Relevance:
    """What the material records say about the data read now, related only through a verified archived fixture."""
    if not data_read:
        return Relevance(NOT_AVAILABLE, "No FE and experimental data are read in the workspace.")
    if verified_fixture is None:
        return Relevance(NOT_AVAILABLE, (
            "No material evidence is bound to the read data: no archived physical registration has been verified for "
            "them (Analysis > Check reference registration). Archived results of other measurements are not "
            "transferred to them by name, file name or frequency, and no material value is derived from the "
            "frequencies."))
    if verified_fixture in view.fixtures:
        models = "; ".join(model for fixture, model in view.fixture_models if fixture == verified_fixture)
        return Relevance(NOT_AVAILABLE, (
            f"The archived registration {verified_fixture} applies to the read data's FE geometry, experimental source "
            f"and modal set only. {NOT_BOUND}"), historical=(
            f"Historical record, with its own provenance and not a result of the read FE model: the governed M7 "
            f"campaign of the SP-02 / SP-13 family used the fixture {verified_fixture} with its {models}. Its "
            f"material-identification result is {view.formal_output} (D-077): no material value is identified."))
    return Relevance(NOT_AVAILABLE, (
        f"The archived registration {verified_fixture} applies to the read data's FE geometry, experimental source and "
        f"modal set only, and no governed material record uses it. {NOT_BOUND}"))


__all__ = ["CLASSES", "CLASS_NOTE", "CLASS_TITLE", "EvidenceRow", "HEADERS", "MaterialsView", "Relevance",
           "current_relevance", "load_material_evidence"]

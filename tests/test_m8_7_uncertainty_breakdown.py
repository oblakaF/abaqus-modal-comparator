"""M8.7 — read-only uncertainty and evidence-source breakdown on the Data Readiness Check (recorded evidence only).

The breakdown is read from the shared backend's ``ScientificReadiness`` record shown under the current selection (M8.2
/ M8.3 / M8.4 protections) and, for material identification, from the backend's formal campaign report of the current
typed evaluation (M8.6 binding).  It computes nothing.  Synthetic runs use the M4.6 fake solver; RUN_A / RUN_B are read
store-gated.
"""

from __future__ import annotations

import ast
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import CampaignDefinitionError, parse_campaign_definition  # noqa: E402
from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from services import stored_run_evidence as adapter  # noqa: E402
from services.auto_id_wizard import uncertainty_breakdown  # noqa: E402
from services.campaign_scientific_backend import judge_campaign_run  # noqa: E402
from services.identification_campaign_run import CampaignRun  # noqa: E402
from test_v12_i1_campaign_question import calibration_definition  # noqa: E402
import test_v12_i6_backend_integration as backend_tests  # noqa: E402
from test_v12_i6_backend_integration import rechain  # noqa: E402

CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RUN_A, RUN_B = CAMPAIGNS / "M7_RUN_A.campaign.json", CAMPAIGNS / "M7_RUN_B.campaign.json"
COVARIANCE = "A · Covariance basis"
STATISTICAL = "B · Statistical uncertainty"
BIRGE = "C · Birge adjustment"
MODEL_FORM = "D · Model-form robustness"
CONSERVATIVE = "E · Conservative calibration uncertainty"
TAU = "F · τ_mf"
SOURCES = "Sources / provenance"
UNCERTAINTY_SECTIONS = (COVARIANCE, STATISTICAL, BIRGE, MODEL_FORM, CONSERVATIVE)


def _journal(run_root: Path) -> Path:
    found = list(Path(run_root).glob("campaign/*/journal.json"))
    assert len(found) == 1, found
    return found[0]


def _tree(path: Path) -> list[str]:
    return sorted(p.relative_to(path).as_posix() for p in Path(path).rglob("*"))


def table(rows) -> dict:
    """{(section, item): recorded} of breakdown rows."""
    return {(section, item): value for section, item, value in rows}


def store_of(run) -> Path:
    return run.campaign.run_dir.parent.parent.parent / "data" / "store"


class _Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base = backend_tests._Runs.run_of("base")
        cls.imprecise = backend_tests._Runs.run_of("imprecise")
        cls.one_family = backend_tests._Runs.run_of("one_family")
        cls.rank = backend_tests._Runs.run_of("rank")

    def readiness(self, run):
        return judge_campaign_run(run.definition, [run.item], run.evidence)

    def rows(self, run) -> dict:
        return table(uncertainty_breakdown(self.readiness(run).to_dict()))

    def material(self, shift=1.0):
        return backend_tests.MaterialPathTests.material_run(self, (0.02, shift))

    def material_readiness(self, shift=1.0):
        run = self.material(shift)
        return judge_campaign_run(run.definition, run.specimens, run.evidence)

    def application(self, record=None):
        from test_material_identification_ui import _ApplicationHarness

        application = _ApplicationHarness()._application()
        if record is not None:
            application.scientific_readiness_record = record
        application._refresh_material_identification_pages()
        return application

    def definition_file(self, definition) -> Path:
        folder = Path(tempfile.mkdtemp(prefix="m8_7_def_"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        path = folder / "campaign.campaign.json"
        path.write_text(json.dumps(definition.canonical), encoding="utf-8")
        return path

    def copy_run(self, run) -> Path:
        target = Path(tempfile.mkdtemp(prefix="m8_7_run_"))
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        shutil.copytree(run.campaign.run_dir.parent.parent, target / "runs")
        return target / "runs"

    def patched(self, run):
        specimens = tuple(getattr(run, "specimens", None) or (run.item,))
        return (mock.patch.object(adapter, "campaign_specimens", return_value=specimens),
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment",
                           return_value={"synthetic": store_of(run)}))

    def gui(self, function, application, run, *args):
        first, second = self.patched(run)
        with first, second:
            function(application, *args)

    def evaluated(self, run=None, root=None):
        import material_identification_ui as ui

        run = run or self.base
        root = root or self.copy_run(run)
        application = self.application()
        ui.load_auto_id_source(application, "family", str(self.definition_file(run.definition)))
        self.gui(ui.select_auto_id_run, application, run, str(_journal(root)))
        self.gui(ui.evaluate_auto_id_run, application, run)
        return application, root

    @staticmethod
    def shown(application) -> dict:
        widget = application.material_uncertainty_breakdown_table
        return table(widget.items[key] for key in widget.get_children())

    def assert_cleared(self, application):
        self.assertEqual(self.shown(application), {})
        self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"],
                         "NOT_EVALUATED_FOR_SELECTION")


# ----------------------------------------------------------------------------- covariance 1-4, 13

class CovarianceTests(_Fixture):
    def test_01_complete_measured_covariance_is_not_exposed_by_accepted_records(self):
        # Gap: an accepted campaign definition can only declare Σ_meas NOT_AVAILABLE (D-069), so no accepted record
        # carries a complete measured covariance; the breakdown never presents one.
        data = calibration_definition()
        data["sigma"]["measurement"] = {"status": "MEASURED", "source": "invented"}
        with self.assertRaises(CampaignDefinitionError):
            parse_campaign_definition(data)
        for rows in (self.rows(self.base), table(uncertainty_breakdown(self.material_readiness().to_dict()))):
            self.assertTrue(rows[(COVARIANCE, "Complete / conditional")].startswith("CONDITIONAL"))
            self.assertNotIn("COMPLETE", rows[(COVARIANCE, "Complete / conditional")])
        record = self.readiness(self.base).to_dict()
        complete = dict(record, uncertainty_basis={"basis": "COVARIANCE_COMPONENTS_COMPLETE_AND_MEASURED",
                                                   "conditional_on_available_covariance": False,
                                                   "covariance_components": {"sigma_setup": "MEASURED",
                                                                             "sigma_meas": "MEASURED"}})
        self.assertEqual(table(uncertainty_breakdown(complete))[(COVARIANCE, "Complete / conditional")],
                         "COMPLETE (as recorded: all covariance components measured)")
        unknown = dict(record, uncertainty_basis={"basis": "SOMETHING_ELSE", "covariance_components": {}})
        self.assertTrue(table(uncertainty_breakdown(unknown))[(COVARIANCE, "Complete / conditional")]
                        .startswith("NOT_AVAILABLE — the record states no recognised basis"))

    def test_02_conditional_covariance_basis(self):
        rows = self.rows(self.base)
        self.assertEqual(rows[(COVARIANCE, "Recorded basis")], "UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE")
        self.assertEqual(rows[(COVARIANCE, "Complete / conditional")],
                         "CONDITIONAL on the available covariance components — not a complete measured uncertainty")
        self.assertIn("not a complete experimental uncertainty", rows[(COVARIANCE, "Recorded statement")])
        self.assertIn("(conditional on the available covariance)", rows[(BIRGE, "birge_adjusted_sd · E_in_plane_mpa")])

    def test_03_missing_sigma_meas_is_not_available_never_zero(self):
        rows = self.rows(self.base)
        self.assertEqual(rows[(COVARIANCE, "Σ_meas status")], "NOT_AVAILABLE")
        self.assertEqual(rows[(COVARIANCE, "Missing components")], "sigma_meas (NOT_AVAILABLE, never zero)")
        record = self.readiness(self.base).to_dict()
        partial = dict(record, uncertainty_basis={"basis": "UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE",
                                                  "covariance_components": {"sigma_setup": "PROVISIONAL"}})
        self.assertEqual(table(uncertainty_breakdown(partial))[(COVARIANCE, "Σ_meas status")],
                         "NOT_AVAILABLE — not recorded")
        for (section, _), value in rows.items():
            if section in UNCERTAINTY_SECTIONS:
                self.assertNotRegex(value, r"^0(\.0)?( |$)")

    def test_04_provisional_sigma_setup(self):
        rows = self.rows(self.base)
        self.assertEqual(rows[(COVARIANCE, "Σ_setup status")], "PROVISIONAL")
        self.assertEqual(rows[(COVARIANCE, "Provisional components")], "sigma_setup")
        readiness = self.material_readiness()
        rows = table(uncertainty_breakdown(readiness.to_dict(), readiness.material_report))
        self.assertIn("sd_ln 0.003 PROVISIONAL; source: SPEC §7 provisional", rows[(COVARIANCE,
                                                                                     "Σ_setup (campaign report)")])
        self.assertIn("NOT_AVAILABLE; source:", rows[(COVARIANCE, "Σ_meas (campaign report)")])

    def test_13_tau_mf_never_enters_covariance_or_uncertainty(self):
        record = self.readiness(self.base).to_dict()
        rows = table(uncertainty_breakdown(record))
        self.assertEqual(rows[(TAU, "τ_mf")], "0.02 — acceptance tolerance on |Δ ln f| only")
        self.assertIn("ACCEPTANCE_TOLERANCE", rows[(TAU, "Recorded role")])
        self.assertIn("never part of Σ", rows[(TAU, "Separation")])
        self.assertEqual(rows[(CONSERVATIVE, "τ_mf in the envelope (recorded)")], "False")
        changed = copy.deepcopy(record)
        changed["tau_mf"] = 0.05
        changed["calibration"]["tau_mf"]["value"] = 0.05
        other = table(uncertainty_breakdown(changed))
        for key, value in rows.items():
            if key[0] in UNCERTAINTY_SECTIONS:
                self.assertEqual(other[key], value, key)  # no uncertainty depends on τ_mf
                self.assertNotIn("τ_mf", key[1] + value if key[0] != CONSERVATIVE else value)
        self.assertEqual(set(record["uncertainty_basis"]["covariance_components"]), {"sigma_setup", "sigma_meas"})


# ----------------------------------------------------------------------------- statistical / Birge 5-7

class StatisticalBirgeTests(_Fixture):
    def test_05_recorded_statistical_sd(self):
        readiness = self.material_readiness()
        verdict = readiness.material_report["m5_verdict"]["verdicts"]["E_in_plane_mpa"]
        rows = table(uncertainty_breakdown(readiness.to_dict(), readiness.material_report))
        self.assertEqual(rows[(STATISTICAL, "statistical_sd · E_in_plane_mpa")],
                         f"{verdict['statistical_sd_ln']!r} ln p (conditional on the available covariance)")
        external = table(uncertainty_breakdown(readiness.to_dict()))  # the stored record alone holds no M5 evidence
        self.assertIn("held only by the current typed evaluation", external[(STATISTICAL, "statistical_sd")])
        # audit V2: the calibration output record now carries the statistical_sd the gate judged (recorded value)
        record = self.readiness(self.base).calibration_record
        value = record.statistical_sd["statistical_sd_ln"]["E_in_plane_mpa"]
        self.assertEqual(record.statistical_sd["status"], "AVAILABLE")
        self.assertEqual(self.rows(self.base)[(STATISTICAL, "statistical_sd · E_in_plane_mpa")],
                         f"{value!r} ln p (conditional on the available covariance)")

    def test_06_birge_available(self):
        readiness = self.readiness(self.base)
        value = readiness.calibration_record.precision["parameters"]["E_in_plane_mpa"]["birge_adjusted_sd_ln"]
        rows = table(uncertainty_breakdown(readiness.to_dict()))
        self.assertEqual(rows[(BIRGE, "birge_adjusted_sd · E_in_plane_mpa")],
                         f"{value!r} ln p (conditional on the available covariance); AVAILABLE")
        material = self.material_readiness()
        verdict = material.material_report["m5_verdict"]["verdicts"]["E_in_plane_mpa"]
        rows = table(uncertainty_breakdown(material.to_dict(), material.material_report))
        self.assertTrue(rows[(BIRGE, "birge_adjusted_sd · E_in_plane_mpa")].startswith(
            repr(verdict["birge_adjusted_sd_ln"])))

    def test_07_birge_not_available_is_never_generated(self):
        readiness = self.readiness(self.rank)
        parameters = readiness.calibration_record.precision["parameters"]
        self.assertTrue(all(p["birge_adjusted_sd_ln"] is None for p in parameters.values()))
        rows = table(uncertainty_breakdown(readiness.to_dict()))
        for name in ("E_in_plane_mpa", "G12_mpa"):
            self.assertEqual(rows[(BIRGE, f"birge_adjusted_sd · {name}")],
                             "NOT_AVAILABLE — birge_adjusted_sd not available (REFUSED_STATISTICAL)")
            self.assertTrue(rows[(CONSERVATIVE, f"conservative_uncertainty · {name}")].startswith("NOT_AVAILABLE"))


# ----------------------------------------------------------------------------- model form 8-10, precision 11-12

class ModelFormPrecisionTests(_Fixture):
    def test_08_complete_loo(self):
        readiness = self.material_readiness()
        rows = table(uncertainty_breakdown(readiness.to_dict(), readiness.material_report))
        self.assertEqual(rows[(MODEL_FORM, "Leave-one-family-out status")], "AVAILABLE_COMPLETE_LOO")
        self.assertEqual(rows[(MODEL_FORM, "Label")], "MODEL_DEPENDENCE_DIAGNOSTIC")
        self.assertEqual((rows[(MODEL_FORM, "Case FAM-12")], rows[(MODEL_FORM, "Case FAM-B1")]), ("VALID", "VALID"))
        self.assertIn("not a confidence interval", rows[(MODEL_FORM, "Interpretation (recorded)")])
        calibration = self.rows(self.base)  # audit V2: the recorded leave-one-FIT-family-out status
        self.assertEqual(calibration[(MODEL_FORM, "Leave-one-FIT-family-out status")], "AVAILABLE_COMPLETE_LOO")
        self.assertEqual(calibration[(MODEL_FORM, "Leave-one-FIT-family-out")], "COMPLETE (recorded AVAILABLE_COMPLETE_LOO)")

    def test_09_incomplete_loo_has_no_fabricated_interval(self):
        readiness = self.readiness(self.one_family)
        self.assertIsNone(readiness.calibration_record.precision["parameters"]["E_in_plane_mpa"]
                          ["model_form_half_range_ln"])
        rows = table(uncertainty_breakdown(readiness.to_dict()))
        self.assertTrue(rows[(MODEL_FORM, "Leave-one-FIT-family-out")].startswith(
            "INCOMPLETE (recorded refusal LOO_INCOMPLETE): leave-one-FIT-family-out refused for ['FAM-A1']"))
        self.assertEqual(rows[(MODEL_FORM, "model_form_half_range · E_in_plane_mpa")],
                         "NOT_AVAILABLE — incomplete leave-one-FIT-family-out: no model-form interval")
        self.assertTrue(rows[(CONSERVATIVE, "conservative_uncertainty · E_in_plane_mpa")].startswith(
            "NOT_AVAILABLE — E_in_plane_mpa: conservative_uncertainty undefined (complete leave-one-FIT-family-out "
            "required); recorded decision REFUSED"))
        # a material report with an incomplete set: no number from the campaign report or from the M5 verdict
        material = self.material_readiness()
        report = copy.deepcopy(material.material_report)
        report["model_form_robustness"]["status"] = "UNAVAILABLE_INCOMPLETE_LOO"
        rows = table(uncertainty_breakdown(material.to_dict(), report))
        self.assertTrue(rows[(MODEL_FORM, "half_range · E_in_plane_mpa (campaign report)")].startswith("NOT_AVAILABLE"))
        self.assertTrue(rows[(MODEL_FORM, "half_range · E_in_plane_mpa (M5 verdict)")].startswith(
            "NOT_AVAILABLE — incomplete leave-one-family-out: the M5 number covers the valid cases only"))

    def test_10_recorded_model_form_half_range(self):
        readiness = self.material_readiness(1.12)
        report = readiness.material_report
        recorded = report["model_form_robustness"]["parameters"]["E_in_plane_mpa"]["half_range_ln"]
        rows = table(uncertainty_breakdown(readiness.to_dict(), report))
        self.assertEqual(rows[(MODEL_FORM, "half_range · E_in_plane_mpa (campaign report)")],
                         f"{recorded!r} ln p (MODEL_DEPENDENCE_DIAGNOSTIC)")
        calibration = self.readiness(self.base)
        half = calibration.calibration_record.precision["parameters"]["E_in_plane_mpa"]["model_form_half_range_ln"]
        self.assertTrue(table(uncertainty_breakdown(calibration.to_dict()))[
            (MODEL_FORM, "model_form_half_range · E_in_plane_mpa")].startswith(f"{half!r} ln p (half-range"))

    def test_11_conservative_calibration_uncertainty(self):
        readiness = self.readiness(self.base)
        precision = readiness.calibration_record.precision
        rows = table(uncertainty_breakdown(readiness.to_dict()))
        value = precision["parameters"]["E_in_plane_mpa"]["conservative_uncertainty_ln"]
        self.assertEqual(rows[(CONSERVATIVE, "conservative_uncertainty · E_in_plane_mpa")],
                         f"{value!r} ln p; recorded decision PASS")
        self.assertEqual(rows[(CONSERVATIVE, "Recorded envelope")],
                         "max(birge_adjusted_sd_ln, 0.5 * (max_shift_ln - min_shift_ln)) in ln p")
        material = self.material_readiness()
        rows = table(uncertainty_breakdown(material.to_dict(), material.material_report))
        self.assertTrue(rows[(CONSERVATIVE, "Calibration precision gate")].startswith("not applicable"))

    def test_12_precision_pass_and_refused(self):
        passed = self.rows(self.base)
        refused_readiness = self.readiness(self.imprecise)
        refused = table(uncertainty_breakdown(refused_readiness.to_dict()))
        self.assertEqual(passed[(CONSERVATIVE, "SPEC v1.2 precision ceiling (recorded)")], "0.08 in ln p")
        self.assertEqual(refused[(CONSERVATIVE, "SPEC v1.2 precision ceiling (recorded)")], "0.08 in ln p")
        self.assertTrue(passed[(CONSERVATIVE, "conservative_uncertainty · E_in_plane_mpa")].endswith("decision PASS"))
        value = refused_readiness.calibration_record.precision["parameters"]["E_in_plane_mpa"][
            "conservative_uncertainty_ln"]
        self.assertGreater(value, 0.08)
        self.assertEqual(refused[(CONSERVATIVE, "conservative_uncertainty · E_in_plane_mpa")],
                         f"{value!r} ln p; recorded decision REFUSED")
        self.assertIn("CONSERVATIVE_ABOVE_CEILING", refused[("Status", "Refusal")])


# ----------------------------------------------------------------------------- questions 14-19

class QuestionTests(_Fixture):
    def test_16_synthetic_calibration_released(self):
        rows = self.rows(self.base)
        self.assertEqual(rows[("Status", "Evidence role")],
                         "released specimen calibration record — readiness evidence only, NOT AUTHORISED FOR PRODUCTION")
        self.assertTrue(rows[(SOURCES, "Solver profile · A")].startswith("SYA/fake (hash "))
        self.assertIn("not a claim of a physical Abaqus solve", rows[(SOURCES, "Solver profile · A")])
        self.assertIn("NO_HUMAN_AUTHORISED_PRODUCTION_CALIBRATION_RUN", rows[(SOURCES, "Physical calibration status")])
        self.assertTrue(rows[(SOURCES, "Production execution")].startswith("NOT_AUTHORISED"))
        record = self.readiness(self.base).to_dict()
        released = record["released_calibration_parameters"]["E_in_plane_mpa"]["value"]
        self.assertEqual(rows[("Calibration parameters", "Fitted (released)")],
                         f"E_in_plane_mpa = {released!r} MPa (MODEL_CALIBRATION_PARAMETER)")
        self.assertIn("FIXED_BY_CAMPAIGN_DEFINITION", rows[("Calibration parameters", "Fixed · G12_mpa")])
        self.assertIn("no fitted uncertainty", rows[("Calibration parameters", "Fixed · G12_mpa")])
        self.assertEqual(rows[(SOURCES, "Run hash")], record["campaign"]["run_hash"])
        self.assertEqual(rows[(SOURCES, "Calibration gate record hash")], record["calibration"]["gate_record_hash"])

    def test_17_calibration_refused(self):
        rows = self.rows(self.imprecise)
        self.assertTrue(rows[("Status", "Evidence role")].startswith("REFUSED — every quantity below is supporting"))
        self.assertTrue(rows[(BIRGE, "birge_adjusted_sd · E_in_plane_mpa")].endswith(
            "supporting / diagnostic evidence only (REFUSED); AVAILABLE"))
        self.assertNotIn(("Calibration parameters", "Fitted (released)"), rows)
        self.assertIn("DIAGNOSTIC_OPTIMIZER_CANDIDATE, NOT_A_RELEASE_VALUE",
                      rows[("Calibration parameters", "Fitted (diagnostic only, not released)")])

    def test_18_scientific_not_ready(self):
        root = self.copy_run(self.base)
        for pipeline in root.glob("specimens/*/*/*/journal.json"):
            pipeline.unlink()
        application, _ = self.evaluated(root=root)
        self.assertEqual(application.scientific_readiness_record["status"], "NOT_READY")
        rows = self.shown(application)
        self.assertTrue(rows[("Status", "Missing / invalid evidence")].startswith("LM_HISTORY_MISSING"))
        self.assertTrue(rows[(COVARIANCE, "Covariance basis")].startswith("NOT_AVAILABLE"))
        self.assertTrue(rows[(STATISTICAL, "statistical_sd · fitted parameters")].startswith("NOT_AVAILABLE"))
        self.assertTrue(rows[(BIRGE, "birge_adjusted_sd")].startswith("NOT_AVAILABLE"))
        self.assertEqual(rows[(SOURCES, "LM provenance")], "NOT_AVAILABLE — not verified")
        self.assertTrue(rows[(SOURCES, "FE sources")].startswith("NOT_AVAILABLE"))
        self.assertTrue(rows[(SOURCES, "Solver profile · A")].startswith("SYA/fake"))  # source facts kept
        self.assertIn(application.scientific_readiness_record["campaign"]["campaign_hash"], rows[(SOURCES, "Campaign")])

    def test_19_confirmed_cluster_refusal(self):
        readiness = backend_tests.ClusterReadinessTests(
            "test_a_confirmed_cluster_is_a_readiness_refusal_without_member_matching").journal_declared_cluster()
        rows = table(uncertainty_breakdown(readiness.to_dict()))
        self.assertTrue(any(value.startswith("CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE") for (section, _), value
                            in rows.items() if section == "Status"))
        self.assertNotIn(("Calibration parameters", "Fitted (released)"), rows)

    def test_material_values_released_and_section_13_fail(self):
        released = self.material_readiness()
        rows = table(uncertainty_breakdown(released.to_dict(), released.material_report))
        self.assertEqual(rows[("Material identification", "Formal output")], "VALUES_RELEASED")
        self.assertIn("effective material-model values", rows[("Material identification", "Formally released")])
        failed = self.material_readiness(1.12)
        rows = table(uncertainty_breakdown(failed.to_dict(), failed.material_report))
        self.assertEqual(rows[("Material identification", "SPEC §13 family consistency")],
                         "FAIL — decisive: no global material property")
        self.assertNotIn(("Material identification", "Formally released"), rows)
        self.assertIn("NOT_A_RELEASE_VALUE", rows[("Material identification",
                                                   "Optimizer candidate (diagnostic only, not released)")])


class ArchivedBreakdownTests(unittest.TestCase):
    def setUp(self):
        self.roots = fixture_roots_from_environment()
        if not {"m7-run-a", "m7-run-b", "snadwich", "carbon-project-archive"} <= set(self.roots):
            self.skipTest("data stores m7-run-a / m7-run-b / snadwich / carbon-project-archive not configured")

    def breakdown(self, campaign: Path, store: str) -> dict:
        from test_material_identification_ui import _ApplicationHarness
        import material_identification_ui as ui

        application = _ApplicationHarness()._application()
        ui.load_auto_id_source(application, "family", str(campaign))
        ui.select_auto_id_run(application, str(_journal(Path(self.roots[store]))))
        ui.evaluate_auto_id_run(application)
        return table(ui.uncertainty_breakdown_view(application))

    def test_14_run_a_section_13_refusal(self):
        rows = self.breakdown(RUN_A, "m7-run-a")
        self.assertEqual(rows[("Status", "Backend status")], "REFUSED")
        self.assertEqual(rows[("Material identification", "SPEC §13 family consistency")],
                         "FAIL — decisive: no global material property")
        self.assertEqual(rows[("Material identification", "Formal output")], "NO_GLOBAL_PARAMETER_VALUE")
        self.assertEqual(rows[(BIRGE, "birge_adjusted_sd · E_in_plane_mpa")],
                         "NOT_AVAILABLE — BIRGE_UNAVAILABLE: birge_adjusted_sd not available (BLOCKED_PATTERN); "
                         "model form")
        self.assertIn("supporting / diagnostic evidence only (REFUSED)",
                      rows[(STATISTICAL, "statistical_sd · E_in_plane_mpa")])
        self.assertEqual(rows[(TAU, "τ_mf")], "not declared (none inferred)")
        self.assertIn("archived-validated-pack", rows[(SOURCES, "FE sources · SP02")])
        self.assertTrue(rows[(SOURCES, "Solver profile · SP02")].startswith("SP02/abaqus-2024/v1"))

    def test_15_run_b_diagnostic_only(self):
        rows = self.breakdown(RUN_B, "m7-run-b")
        self.assertEqual(rows[(MODEL_FORM, "Leave-one-family-out status")], "UNAVAILABLE_INCOMPLETE_LOO")
        for name in ("E_in_plane_mpa", "G12_mpa"):
            self.assertTrue(rows[(MODEL_FORM, f"half_range · {name} (M5 verdict)")].startswith("NOT_AVAILABLE"))
            self.assertTrue(rows[(MODEL_FORM, f"half_range · {name} (campaign report)")].startswith("NOT_AVAILABLE"))
        self.assertEqual(rows[("Material identification", "Optimizer candidate (diagnostic only, not released)")],
                         "E_in_plane_mpa = 50886.241471158406, G12_mpa = 6872.052773289999 "
                         "[DIAGNOSTIC_OPTIMIZER_CANDIDATE, NOT_A_RELEASE_VALUE]")
        self.assertNotIn(("Material identification", "Formally released"), rows)


# ----------------------------------------------------------------------------- selection / freshness 20-24

class FreshnessTests(_Fixture):
    def test_20_switching_campaign_or_run_clears_the_breakdown(self):
        import material_identification_ui as ui

        application, _ = self.evaluated()
        self.assertIn((CONSERVATIVE, "conservative_uncertainty · E_in_plane_mpa"), self.shown(application))
        self.gui(ui.select_auto_id_run, application, self.base, str(_journal(self.copy_run(self.base))))
        self.assert_cleared(application)
        application, _ = self.evaluated()
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assert_cleared(application)

    def test_21_refresh_after_journal_change_clears_the_breakdown(self):
        import material_identification_ui as ui

        application, root = self.evaluated()
        self.gui(ui.refresh_auto_id_progress, application, self.base)
        self.assertTrue(self.shown(application))
        pipeline = next(root.glob("specimens/*/*/*/journal.json"))
        document = json.loads(pipeline.read_text(encoding="utf-8"))
        pipeline.write_text(json.dumps(rechain(dict(document, entries=document["entries"]
                                                     + [copy.deepcopy(document["entries"][-1])]))), encoding="utf-8")
        self.gui(ui.refresh_auto_id_progress, application, self.base)
        self.assert_cleared(application)

    def test_22_reopen_clears_the_breakdown(self):
        import material_identification_ui as ui

        application, _ = self.evaluated(self.imprecise)
        self.assertTrue(self.shown(application))
        self.gui(ui.reopen_auto_id_run, application, self.imprecise)
        self.assert_cleared(application)

    def test_23_external_stored_record_with_partial_fields(self):
        import material_identification_ui as ui

        record = copy.deepcopy(self.readiness(self.base).to_dict())
        record["uncertainty_basis"] = None
        record["calibration"].pop("precision")
        application = self.application(record)  # no selection: the record's own identity
        rows = self.shown(application)
        self.assertEqual(rows[(COVARIANCE, "Covariance basis")], "NOT_AVAILABLE — no uncertainty basis in this record")
        self.assertEqual(rows[(CONSERVATIVE, "conservative_uncertainty")],
                         "NOT_AVAILABLE — no calibration output record (not evaluated)")
        self.assertEqual(rows, table(uncertainty_breakdown(record)))
        material = self.material_readiness()
        application = self.application(material.to_dict())
        rows = self.shown(application)
        self.assertIn("held only by the current typed evaluation", rows[(STATISTICAL, "statistical_sd")])
        self.assertIn("held only by the current typed evaluation", rows[(MODEL_FORM, "Leave-one-family-out")])
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assert_cleared(application)

    def test_24_fake_gui_harness_uses_the_typed_report_of_the_current_evaluation_only(self):
        import material_identification_ui as ui

        material = self.material()
        application, _ = self.evaluated(material)
        record = application.scientific_readiness_record
        self.assertEqual(record["status"], "MATERIAL_VALUES_RELEASED")
        rows = self.shown(application)
        report = application.auto_id_active_typed[1].readiness.material_report
        verdict = report["m5_verdict"]["verdicts"]["E_in_plane_mpa"]
        self.assertTrue(rows[(STATISTICAL, "statistical_sd · E_in_plane_mpa")].startswith(
            repr(verdict["statistical_sd_ln"])))
        self.assertEqual(rows, table(uncertainty_breakdown(record, report)))
        active, evaluation = application.auto_id_active_typed
        application.auto_id_active_typed = (tuple(list(active)), evaluation)  # not bound to the active evaluation
        application._refresh_material_identification_pages()
        rows = self.shown(application)
        self.assertIn("held only by the current typed evaluation", rows[(STATISTICAL, "statistical_sd")])
        self.assertNotIn((STATISTICAL, "statistical_sd · E_in_plane_mpa"), rows)
        calibration, _ = self.evaluated()
        self.assertEqual(self.shown(calibration),
                         table(uncertainty_breakdown(calibration.scientific_readiness_record)))
        self.assertEqual(self.shown(calibration), table(ui.uncertainty_breakdown_view(calibration)))


# ----------------------------------------------------------------------------- real Tk 25, safety 26

class RealTkBreakdownTests(_Fixture):
    def test_25_real_gui_breakdown_follows_the_selection(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.addCleanup(root.destroy)
        root.withdraw()
        import main
        import material_identification_ui as ui
        import ui_workflow

        disabled = {"autosave_enabled": False, "restore_on_startup": False, "show_recovery_notice": False}
        with mock.patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), \
                mock.patch.object(ui_workflow, "discover_abaqus_installations", return_value=()):
            application = main.app.ModalComparatorApp(root)
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.gui(ui.select_auto_id_run, application, self.base, str(_journal(self.copy_run(self.base))))
        self.gui(ui.evaluate_auto_id_run, application, self.base)
        root.update_idletasks()
        widget = application.material_uncertainty_breakdown_table
        shown = {tuple(widget.item(k, "values"))[:2] for k in widget.get_children()}
        self.assertIn((CONSERVATIVE, "conservative_uncertainty · E_in_plane_mpa"), shown)
        self.assertIn((TAU, "τ_mf"), shown)
        ui.load_auto_id_source(application, "family", str(RUN_A))
        root.update_idletasks()
        self.assertEqual(application.material_uncertainty_breakdown_table.get_children(), ())


class SafetyTests(_Fixture):
    def test_26_no_solver_execution_or_file_writes(self):
        import material_identification_ui as ui
        from services import identification_campaign_run as campaign_module
        from services import identification_step, shape_extraction

        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        root = self.copy_run(self.base)
        watched = (store_of(self.base), ROOT / "docs" / "auto_id", root)
        before = [_tree(path) for path in watched]
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse), \
                mock.patch.object(campaign_module, "prepare_run_manifest", refuse), \
                mock.patch.object(campaign_module, "extract_archived_odbs", refuse), \
                mock.patch.object(shape_extraction, "extract_shape_pack", refuse), \
                mock.patch.object(CampaignRun, "__init__", refuse), mock.patch.object(CampaignRun, "run", refuse):
            application, _ = self.evaluated(root=root)
            with mock.patch.object(Path, "write_text", refuse), mock.patch.object(Path, "write_bytes", refuse):
                rows = ui.uncertainty_breakdown_view(application)
                application._refresh_material_identification_pages()
        refuse.assert_not_called()
        self.assertTrue(rows)
        self.assertEqual([_tree(path) for path in watched], before)
        tree = ast.parse((ROOT / "src" / "services" / "auto_id_wizard.py").read_text(encoding="utf-8"))
        functions = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
        calls = set()
        for name in ("uncertainty_breakdown", "_recorded", "_number", "_missing", "_exact", "_gate_details",
                     "_mapping"):
            calls |= {getattr(n.func, "id", getattr(n.func, "attr", None)) for n in ast.walk(functions[name])
                      if isinstance(n, ast.Call)}
        self.assertLessEqual(calls, {"isinstance", "str", "get", "join", "append", "len", "tuple", "sorted", "items",
                                     "add", "_mapping", "_missing", "_recorded", "_number", "_exact", "_gate_details",
                                     "repr", "float", "startswith", "list"})  # reads and formats only


def tearDownModule():
    backend_tests.tearDownModule()
    directory = backend_tests.MaterialPathTests._directory
    if directory is not None:
        directory.cleanup()
        backend_tests.MaterialPathTests._directory = None
        backend_tests.MaterialPathTests._runs = {}


if __name__ == "__main__":
    unittest.main()

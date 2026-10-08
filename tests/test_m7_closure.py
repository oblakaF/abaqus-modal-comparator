"""M7 closure (D-075): model_form_robustness reporting and the closure record (no Abaqus here).

M5 takes the model_form_robustness range over the VALID leave-one-family-out cases only, so an incomplete set
can show 0.0.  The campaign report must never read that number as zero model-form uncertainty: an incomplete
or single-case set is UNAVAILABLE_INCOMPLETE_LOO with no number; only a complete set gives a range, labelled
MODEL_DEPENDENCE_DIAGNOSTIC.  M5 itself is unchanged.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services.identification_campaign_run import (
    LOO_COMPLETE,
    LOO_INCOMPLETE,
    LOO_NOT_EVALUATED,
    MODEL_DEPENDENCE_DIAGNOSTIC,
    model_form_robustness_reporting,
)
from services.identification_uncertainty import residual_terms
from services.model_form_robustness import linearised_model_form_robustness
from services.practical_identifiability import (
    ObservationCovariance,
    ParameterDefinition,
    ParameterRole,
    assemble_system,
    build_sensitivity_matrix,
    diagonal_component,
)


CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
FAMILIES = {"SP02:R1": "Px:E|Py:E|nx:0|ny:2", "SP02:R2": "Px:O|Py:E|nx:1|ny:2", "SP13:R1": "Px:O|Py:E|nx:1|ny:2"}


def _load(name: str) -> dict:
    return json.loads((CAMPAIGNS / name).read_text(encoding="utf-8"))


def _numbers(value) -> list:
    if isinstance(value, dict):
        return [n for v in value.values() for n in _numbers(v)]
    if isinstance(value, list):
        return [n for v in value for n in _numbers(v)]
    return [value] if isinstance(value, (int, float)) and not isinstance(value, bool) else []


class IncompleteLooRegressionTests(unittest.TestCase):
    """The RUN_B situation through the real M5 code: rank-deficient family removal + one valid case."""

    def setUp(self):
        record = _load("M7_RUN_B.result.json")
        sensitivity = record["m5_diagnostics"]["jacobian"]["sensitivity_S"]
        terms = list(sensitivity)
        names = ("E_in_plane_mpa", "G12_mpa")
        matrix = build_sensitivity_matrix(sensitivity, terms, [], tuple(ParameterDefinition(n, ParameterRole.GLOBAL)
                                                                         for n in names), {n: "test" for n in names})
        system = assemble_system(matrix, ObservationCovariance(matrix.term_ids, (diagonal_component(
            "sigma_setup", matrix.term_ids, {t: 0.003 for t in matrix.term_ids}, True, "test"),)), ())
        final = record["campaign_evaluations"][-1]
        self.m5 = linearised_model_form_robustness(system, residual_terms(terms, [], final["residuals"], FAMILIES),
                                                   record["parameters"]).to_dict()

    def test_m5_is_unchanged_and_shows_a_zero_range(self):
        self.assertFalse(self.m5["supports_green"])
        self.assertEqual([c["status"] for c in self.m5["cases"]], ["VALID", "REFUSED_RANK_DEFICIENT"])
        for item in self.m5["parameters"].values():
            self.assertEqual((item["range"], item["half_range"]), (0.0, 0.0))  # over the single valid case

    def test_incomplete_loo_is_never_zero_model_form_uncertainty(self):
        reporting = model_form_robustness_reporting(self.m5)
        self.assertEqual(reporting["status"], LOO_INCOMPLETE)
        self.assertIsNone(reporting["label"])
        self.assertIsNone(reporting["parameters"])
        numbers = _numbers({k: v for k, v in reporting.items() if k != "cases"})
        self.assertEqual(numbers, [])  # no range, half-range or replacement value at all
        self.assertTrue(any("not evidence of robustness" in r for r in reporting["reasons"]))

    def test_the_committed_run_b_record_reads_the_same(self):
        committed = _load("M7_RUN_B.result.json")["m5_diagnostics"]["robustness"]
        self.assertEqual(model_form_robustness_reporting(committed)["status"], LOO_INCOMPLETE)


class ReportingRuleTests(unittest.TestCase):
    def setUp(self):
        self.complete = _load("M7_RUN_A.result.json")["m5_diagnostics"]["robustness"]

    def test_complete_set_is_a_model_dependence_diagnostic(self):
        reporting = model_form_robustness_reporting(self.complete)
        self.assertEqual((reporting["status"], reporting["label"]), (LOO_COMPLETE, MODEL_DEPENDENCE_DIAGNOSTIC))
        e_in = reporting["parameters"]["E_in_plane_mpa"]
        self.assertAlmostEqual(e_in["min_estimate"], 50794.8252244, places=3)
        self.assertAlmostEqual(e_in["max_estimate"], 60348.4171294, places=3)
        self.assertTrue(any("not a confidence interval" in r for r in reporting["reasons"]))

    def test_any_refused_case_blocks_the_range(self):
        refused = copy.deepcopy(self.complete)
        refused["cases"][1].update(status="REFUSED_RANK_DEFICIENT", shift_ln=None, estimate=None)
        refused["refused_families"] = [refused["cases"][1]["family"]]
        refused["supports_green"] = False
        reporting = model_form_robustness_reporting(refused)
        self.assertEqual(reporting["status"], LOO_INCOMPLETE)
        self.assertIsNone(reporting["parameters"])

    def test_a_single_valid_case_is_not_a_range(self):
        single = copy.deepcopy(self.complete)
        single["cases"] = single["cases"][:1]
        self.assertEqual(model_form_robustness_reporting(single)["status"], LOO_INCOMPLETE)

    def test_no_record_is_not_evaluated(self):
        reporting = model_form_robustness_reporting(None)
        self.assertEqual((reporting["status"], reporting["parameters"]), (LOO_NOT_EVALUATED, None))


class ClosureRecordTests(unittest.TestCase):
    def setUp(self):
        self.closure = _load("M7_CLOSURE.json")
        self.a = _load("M7_RUN_A.result.json")
        self.b = _load("M7_RUN_B.result.json")

    def test_binds_the_accepted_result_records(self):
        for key, name in (("run_a", "M7_RUN_A.result.json"), ("run_b", "M7_RUN_B.result.json")):
            with self.subTest(run=key):
                digest = hashlib.sha256((CAMPAIGNS / name).read_bytes()).hexdigest()
                self.assertEqual(self.closure[key]["result_record"]["sha256"], digest)
        self.assertEqual(self.closure["decision"].split()[0], "D-075")
        self.assertEqual(self.closure["abaqus_after_run_b"], 0)

    def test_run_a_release_statement(self):
        run_a = self.closure["run_a"]
        self.assertEqual(run_a["E_in_plane_mpa"], self.a["parameters"]["E_in_plane_mpa"])
        self.assertEqual((run_a["label"], run_a["qualifier"]), ("EFFECTIVE_MODEL_PARAMETER_ESTIMATE",
                                                                 "not externally validated"))
        self.assertEqual(run_a["m5_verdict"], {"E_in_plane_mpa": "NOT_IDENTIFIABLE"})
        self.assertTrue(run_a["engineering_use"]["all_fit_and_holdout_within_10_percent"])
        self.assertEqual(run_a["model_form_robustness"],
                         model_form_robustness_reporting(self.a["m5_diagnostics"]["robustness"]))

    def test_run_b_is_diagnostic_only(self):
        run_b = self.closure["run_b"]
        self.assertEqual(run_b["status"], "ACCEPTED_DIAGNOSTIC_ONLY")
        self.assertEqual(run_b["parameter_roles"]["G12_mpa"], "COMPENSATION_DIAGNOSTIC_NOT_MATERIAL_PROPERTY")
        self.assertTrue(run_b["not_for_material_property_tables"])
        self.assertEqual(run_b["model_form_robustness"]["status"], LOO_INCOMPLETE)
        self.assertEqual(set(run_b["m5_verdict"].values()), {"NOT_IDENTIFIABLE"})

    def test_family_discrepancy_is_recomputed_from_the_rows(self):
        for run, record in (("RUN_A", self.a), ("RUN_B", self.b)):
            errors = {x["term_id"]: x["relative_error"] for x in record["engineering"]["rows"]}
            gaps = list(self.closure["family_discrepancy_percentage_points"][run].values())
            with self.subTest(run=run):
                self.assertAlmostEqual(gaps[0], 100.0 * (errors["SP02:R2"] - errors["SP13:R1"]), places=12)
                self.assertAlmostEqual(gaps[1], 100.0 * (errors["SP02:R3"] - errors["SP13:R2"]), places=12)


if __name__ == "__main__":
    unittest.main()

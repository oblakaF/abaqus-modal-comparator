"""M7b corrective diagnostics (D-076; external audit iteration 2: K1, K2, K3). No Abaqus anywhere.

- SPEC §13 family consistency (pure, linearised; χ² and parametric bootstrap);
- the frozen RUN_A / RUN_B records evaluated by it, and the corrective records that state the result;
- per-specimen diagnostics, excluded-mode diagnostics, per-specimen agreement (reporting only);
- additive physical-measurement records beside the unchanged passports.
"""

from __future__ import annotations

import ast
import copy
import json
import math
from pathlib import Path
import sys
import unittest
from unittest import mock

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import (
    CORRECTIVE_FAMILY_CONSISTENCY_POLICY,
    CampaignDefinitionError,
    load_campaign_definition,
    parse_campaign_definition,
)
from domain.experiment_fixture import fixture_roots_from_environment
from m7b_support import assert_records_close
from domain.identification_run import canonical_hash
from domain.physical_measurements import (
    PhysicalMeasurementsError,
    load_physical_measurements,
    parse_physical_measurements,
)
from domain.specimen_manifest import load_specimen_manifest
from services.family_consistency import (
    CHI2_CONDITIONS,
    FamilyConsistencyInputError,
    FamilyConsistencyStatus,
    family_consistency,
)
from services.identification_campaign_run import campaign_family_consistency


CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
CORRECTIONS = ROOT / "docs" / "auto_id" / "audit_corrections"
SPECIMENS = ROOT / "docs" / "auto_id" / "specimens"
ALL_CONDITIONS = {name: True for name in CHI2_CONDITIONS}
RUN_A_HISTORICAL_SHA = "82501b35c4effc0f"  # canonical content hash prefix of the frozen RUN_A record (D-075)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _synthetic(offset_b: float, seed: int = 7):
    """Two specimens, three rows each, one parameter; specimen B shifted by ``offset_b`` in ln E."""
    rng = np.random.default_rng(seed)
    jac = np.array([[160.0], [120.0], [90.0], [150.0], [110.0], [80.0]])
    truth = np.array([0.0, 0.0, 0.0, offset_b, offset_b, offset_b])
    residuals = -(jac[:, 0] * truth) + rng.standard_normal(6)  # whitened residuals at the shared optimum
    terms = ["A:R1", "A:R2", "A:R3", "B:R1", "B:R2", "B:R3"]
    return terms, {t: t[0] for t in terms}, residuals, jac


def _run(terms, specimen_of, residuals, jac, parameters=("E",), conditions=None, samples=2000, seed=11):
    return family_consistency(terms, specimen_of, residuals, jac, list(parameters), {p: 50000.0 for p in parameters},
                              chi2_conditions=conditions or ALL_CONDITIONS, sigma={"setup": {"sd_ln": 0.003}},
                              bootstrap_samples=samples, bootstrap_seed=seed)


class FamilyConsistencyTests(unittest.TestCase):
    def test_synthetic_shared_family_passes(self):
        result = _run(*_synthetic(0.0))
        self.assertEqual(result.status, FamilyConsistencyStatus.PASS)
        self.assertEqual((result.delta_dof, result.path), (1, "CHI2"))
        self.assertGreater(result.p_chi2, 0.01)
        self.assertGreater(result.bootstrap_p, 0.01)

    def test_synthetic_incompatible_specimens_fail(self):
        result = _run(*_synthetic(0.10))  # B wants E 10 % (ln) higher
        self.assertEqual(result.status, FamilyConsistencyStatus.FAIL)
        self.assertLess(result.p_chi2, 1e-10)
        estimates = {s: v["estimate"]["E"] for s, v in result.separate_model["specimens"].items()}
        self.assertLess(estimates["A"], estimates["B"])

    def test_rank_deficient_separate_fit_is_refused(self):
        terms = ["A:R1", "A:R2", "B:R1"]
        jac = np.array([[160.0, 1.0], [120.0, 50.0], [120.0, 50.0]])
        result = _run(terms, {t: t[0] for t in terms}, [1.0, -2.0, 3.0], jac, parameters=("E", "G"))
        self.assertEqual(result.status, FamilyConsistencyStatus.NOT_EVALUABLE_RANK_DEFICIENT)
        self.assertIsNone(result.p_chi2)
        self.assertIsNone(result.bootstrap_p)
        self.assertIsNone(result.delta_chi2)
        self.assertTrue(any("specimen B" in r for r in result.reasons))

    def test_two_parameter_dof_and_bootstrap_path_when_chi2_conditions_fail(self):
        rng = np.random.default_rng(3)
        jac = rng.normal(size=(8, 2)) * 100
        terms = [f"{s}:R{i}" for s in "AB" for i in range(4)]
        conditions = dict(ALL_CONDITIONS, interior_optimum=False)
        result = _run(terms, {t: t[0] for t in terms}, rng.standard_normal(8), jac, ("E", "G"), conditions)
        self.assertEqual(result.delta_dof, 2)
        self.assertEqual(result.path, "BOOTSTRAP")
        self.assertTrue(any("bootstrap is decisive" in r for r in result.reasons))

    def test_row_order_does_not_change_the_result(self):
        terms, owner, residuals, jac = _synthetic(0.05)
        first = _run(terms, owner, residuals, jac).to_dict()
        order = [4, 0, 5, 2, 1, 3]
        second = _run([terms[i] for i in order], owner, residuals[order], jac[order]).to_dict()
        self.assertEqual(first, second)

    def test_bootstrap_is_deterministic_and_needs_2000_samples(self):
        args = _synthetic(0.0)
        self.assertEqual(_run(*args, seed=5).bootstrap_p, _run(*args, seed=5).bootstrap_p)
        with self.assertRaises(FamilyConsistencyInputError):
            _run(*args, samples=1999)


class RunAFrozenEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.record = _load(CAMPAIGNS / "M7_RUN_A.result.json")
        self.definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_A.campaign.json")
        self.result = campaign_family_consistency(
            self.definition, self.record["m5_diagnostics"]["jacobian"]["whitened"],
            self.record["campaign_evaluations"][-1], {"parameters": self.record["parameters"]}, True)

    def test_frozen_run_a_fails_spec_13(self):
        self.assertEqual(self.result["status"], "FAIL")
        self.assertEqual(self.result["path"], "CHI2")

    def test_run_a_reproduces_the_audit_reconstruction(self):
        # Audit iteration 2: Δχ² ≈ 748.9, Δdof 1 at Σ 0.3 %.  The admissible local models built from the journal
        # spread 745.8–747.3 (M7_FAMILY_CONSISTENCY_CORRECTION.json); a 1 % tolerance covers that spread and the
        # audit's own linearisation / rounding, while a different residual definition (716 or 774) would fail.
        self.assertEqual(self.result["delta_dof"], 1)
        self.assertLess(abs(self.result["delta_chi2"] / 748.9 - 1.0), 0.01)
        self.assertLess(self.result["log10_p_chi2"], -100)

    def test_bootstrap_strongly_rejects(self):
        policy = CORRECTIVE_FAMILY_CONSISTENCY_POLICY
        self.assertEqual((self.result["bootstrap_samples"], self.result["bootstrap_seed"]),
                         (policy.bootstrap_samples, policy.bootstrap_seed))
        self.assertAlmostEqual(self.result["bootstrap_p"], 1.0 / (policy.bootstrap_samples + 1), places=15)

    def test_sigma_meas_stays_not_available(self):
        sigma = self.result["sigma"]
        self.assertEqual(sigma["measurement"]["status"], "NOT_AVAILABLE")
        self.assertFalse(sigma["measurement"]["in_whitening"])
        self.assertNotIn("sd_ln", sigma["measurement"])
        self.assertEqual((sigma["setup"]["sd_ln"], sigma["setup"]["status"]), (0.003, "PROVISIONAL"))
        with self.assertRaises(CampaignDefinitionError):
            self.definition.sigma.measurement_sd_ln()  # no value, never zero
        for row in self.record["engineering"]["rows"]:  # the whitening is Σ_setup alone
            self.assertAlmostEqual(row["whitened_residual"], math.log1p(row["relative_error"]) / 0.003, places=9)

    def test_corrective_record_states_this_result(self):
        correction = _load(CORRECTIONS / "M7_FAMILY_CONSISTENCY_CORRECTION.json")
        assert_records_close(self, json.loads(json.dumps(self.result)), correction["run_a"]["family_consistency"])
        self.assertEqual(correction["run_a"]["verdict"], "FAIL")
        self.assertTrue(correction["run_a"]["result_record"]["canonical_content_sha256"].startswith(RUN_A_HISTORICAL_SHA))
        self.assertEqual(correction["run_a"]["result_record"]["canonical_content_sha256"], canonical_hash(self.record))
        interpretation = correction["corrected_interpretation"]
        self.assertEqual(interpretation["label"], "HISTORICAL_RUN_A_OPTIMIZER_CANDIDATE")
        self.assertEqual(interpretation["historical_run_a_optimizer_candidate_mpa"],
                         self.record["parameters"]["E_in_plane_mpa"])  # still visible, not deleted
        self.assertIn("NO GLOBAL PARAMETER VALUE", interpretation["formal_output"])

    def test_run_b_is_not_evaluable(self):
        record = _load(CAMPAIGNS / "M7_RUN_B.result.json")
        definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_B.campaign.json")
        result = campaign_family_consistency(definition, record["m5_diagnostics"]["jacobian"]["whitened"],
                                             record["campaign_evaluations"][-1], {"parameters": record["parameters"]},
                                             True)
        self.assertEqual(result["status"], "NOT_EVALUABLE_RANK_DEFICIENT")
        self.assertIsNone(result["p_chi2"])
        correction = _load(CORRECTIONS / "M7_FAMILY_CONSISTENCY_CORRECTION.json")
        assert_records_close(self, json.loads(json.dumps(result)), correction["run_b"]["family_consistency"])


class PerSpecimenDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.diagnostics = _load(CORRECTIONS / "M7_PER_SPECIMEN_DIAGNOSTICS.json")
        self.cases = self.diagnostics["run_a_per_specimen_estimates"]["cases"]

    def test_estimates_are_diagnostic_and_reproduce_the_audit(self):
        for name, case in self.cases.items():
            with self.subTest(case=name):
                self.assertEqual(case["labels"], ["DIAGNOSTIC_ONLY", "NOT_A_MATERIAL_PROPERTY", "NOT_A_RELEASE_VALUE"])
                self.assertLess(abs(case["difference_from_audit_percent"]), 1.0)
                self.assertEqual(case["rank"], 1)

    def test_fit_row_estimates_agree_with_the_family_consistency_separate_fits(self):
        correction = _load(CORRECTIONS / "M7_FAMILY_CONSISTENCY_CORRECTION.json")
        separate = correction["run_a"]["family_consistency"]["separate_model"]["specimens"]
        check = self.diagnostics["run_a_per_specimen_estimates"]["cross_check_with_M5_jacobian"]
        self.assertAlmostEqual(check["SP02 FIT rows, M5 Jacobian"]["estimate_mpa"],
                               separate["SP02"]["estimate"]["E_in_plane_mpa"], places=6)
        self.assertAlmostEqual(check["SP13 FIT row, M5 Jacobian"]["estimate_mpa"],
                               separate["SP13"]["estimate"]["E_in_plane_mpa"], places=6)

    def test_sp13_governed_rows_disagree(self):
        rows = self.diagnostics["run_a_per_specimen_estimates"]["sp13_rows_disagree"]
        r1, r2 = [v for k, v in rows.items() if k.startswith("R")]
        self.assertGreater(abs(r1 / r2 - 1.0), 0.10)
        self.assertGreater(rows["both rows chi2 (1 dof)"], 100.0)

    def test_per_specimen_agreement_shows_sp02_worsened(self):
        agreement = self.diagnostics["run_a_per_specimen_agreement"]["specimens"]
        self.assertEqual((agreement["SP02"]["change"], agreement["SP13"]["change"]), ("WORSENED", "IMPROVED"))
        record = _load(CAMPAIGNS / "M7_RUN_A.result.json")
        self.assertTrue(record["engineering"]["improved_or_consistent"])  # the old global flag hid this

    def test_torsional_mode_1_is_a_diagnostic_row_and_never_fitted(self):
        excluded = self.diagnostics["excluded_mode_diagnostics"]
        expected = {"SP02": (0.897, -0.158), "SP13": (0.987, -0.284)}
        definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_A.campaign.json")
        for label, (mac, error) in expected.items():
            rows = excluded["specimens"][label]
            with self.subTest(specimen=label):
                self.assertEqual([r["experimental_mode"] for r in rows], [1])
                row = rows[0]
                self.assertAlmostEqual(row["mac"], mac, places=3)
                self.assertAlmostEqual(row["signed_frequency_error"], error, places=3)
                self.assertGreaterEqual(row["mac"], excluded["minimum_mac"])
                self.assertEqual(row["role"], "DIAGNOSTIC_ONLY_NOT_FITTED")
                self.assertTrue(row["torsion_dominated"])
                spec = next(s for s in definition.specimens if s.label == label)
                self.assertNotIn(1, [r.experimental_mode for r in spec.rows])  # not in the objective


class UncertaintyBasisTests(unittest.TestCase):
    """Audit J5: statistical_sd is conditional on the available covariance and must not look complete."""

    def test_sd_is_reported_as_conditional_while_sigma_meas_is_not_available(self):
        from dataclasses import replace
        from services.identification_campaign_run import uncertainty_basis

        for name in ("M7_RUN_A.campaign.json", "M7_RUN_B.campaign.json"):
            definition = load_campaign_definition(CAMPAIGNS / name)
            basis = uncertainty_basis(definition)
            with self.subTest(campaign=name):
                self.assertEqual(basis["statistical_sd_status"], "CONDITIONAL_ON_AVAILABLE_COVARIANCE")
                self.assertEqual(basis["covariance_components"], {"sigma_setup": "PROVISIONAL",
                                                                  "sigma_meas": "NOT_AVAILABLE"})
                self.assertIn("not a complete measured uncertainty", basis["statement"])
        measured = replace(definition, sigma=replace(definition.sigma, setup_status="MEASURED",
                                                     measurement_status="MEASURED"))
        self.assertEqual(uncertainty_basis(measured)["statistical_sd_status"], "COMPLETE_MEASURED_COVARIANCE")


class CampaignPolicyTests(unittest.TestCase):
    def test_policy_is_identity_bound_only_when_declared(self):
        data = _load(CAMPAIGNS / "M7_RUN_A.campaign.json")
        historical = parse_campaign_definition(data)
        self.assertIsNone(historical.family_consistency_policy)
        self.assertEqual(historical.campaign_hash,
                         "0a21ad0567901034b521b822b52f0c29944e96394f3692e1a8ebcd7ccd8d2ccf")  # unchanged
        bound = parse_campaign_definition(dict(data, family_consistency={"bootstrap_samples": 4000,
                                                                         "bootstrap_seed": 1}))
        self.assertNotEqual(bound.campaign_hash, historical.campaign_hash)
        with self.assertRaises(CampaignDefinitionError):
            parse_campaign_definition(dict(data, family_consistency={"bootstrap_samples": 500, "bootstrap_seed": 1}))


class PhysicalMeasurementsTests(unittest.TestCase):
    def test_records_bind_the_unchanged_passports(self):
        for label in ("SP02", "SP13"):
            record = load_physical_measurements(SPECIMENS / f"{label}.physical-measurements.json")
            passport = load_specimen_manifest(ROOT / record.passport_path)
            forward = _load(ROOT / f"docs/auto_id/forward_models/{label}.physical.forward.json")
            with self.subTest(specimen=label):
                self.assertEqual(record.passport_manifest_hash, passport.manifest_hash)
                self.assertEqual(record.passport_manifest_hash, forward["specimen_passport"]["manifest_hash"])
                self.assertEqual(record.physical_specimen_id, str(passport.physical_specimen_id))
                self.assertTrue(all(m.uncertainty.status != "MEASURED_SD" and m.uncertainty.sd is None
                                    for m in record.measurements))  # no invented uncertainty
                faces = record.values("face_thickness_mm")
                self.assertEqual(set(faces), {"top_face", "bottom_face"})
                self.assertTrue(all("NOT MET" in m.spec_requirement for m in record.measurements
                                    if m.quantity == "face_thickness_mm"))
        sp13 = load_physical_measurements(SPECIMENS / "SP13.physical-measurements.json")
        self.assertEqual(sp13.values("face_thickness_mm")["top_face"], (0.425,))
        sp02 = load_physical_measurements(SPECIMENS / "SP02.physical-measurements.json")
        self.assertEqual(sp02.values("face_thickness_mm")["top_face"], (0.45,))

    def test_resolution_is_never_an_uncertainty(self):
        data = _load(SPECIMENS / "SP02.physical-measurements.json")
        bad = copy.deepcopy(data)
        bad["measurements"][0]["uncertainty"]["sd"] = 0.5  # e.g. half a 1 mm ruler graduation
        with self.assertRaises(PhysicalMeasurementsError):
            parse_physical_measurements(bad)
        bad = copy.deepcopy(data)
        bad["measurements"][0]["uncertainty"] = {"status": "MEASURED_SD", "sd": None, "basis": "x"}
        with self.assertRaises(PhysicalMeasurementsError):
            parse_physical_measurements(bad)

    def test_source_lines_are_in_the_pinned_spec_files(self):
        roots = fixture_roots_from_environment()
        if "snadwich" not in roots:
            self.skipTest("data store 'snadwich' not configured")
        from domain.experiment_fixture import resolve_external_file

        for label in ("SP02", "SP13"):
            record = load_physical_measurements(SPECIMENS / f"{label}.physical-measurements.json")
            text = resolve_external_file(record.sources["spec_txt"], roots).read_text(encoding="utf-8")
            for m in record.measurements:
                with self.subTest(specimen=label, quantity=m.quantity, component=m.component):
                    self.assertIn(m.source_text, text)


class NoAbaqusTests(unittest.TestCase):
    def test_analyses_start_no_process(self):
        refuse = mock.Mock(side_effect=AssertionError("a process was started"))
        with mock.patch("subprocess.Popen", refuse), mock.patch("subprocess.run", refuse), \
                mock.patch("os.system", refuse):
            RunAFrozenEvidenceTests("test_frozen_run_a_fails_spec_13").setUp()
            _run(*_synthetic(0.1))
            for label in ("SP02", "SP13"):
                load_physical_measurements(SPECIMENS / f"{label}.physical-measurements.json")
        refuse.assert_not_called()
        for module in ("services/family_consistency.py", "services/campaign_diagnostics.py",
                       "domain/physical_measurements.py"):
            tree = ast.parse((ROOT / "src" / module).read_text(encoding="utf-8"))
            imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
            imported |= {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
            with self.subTest(module=module):
                self.assertFalse({"subprocess", "forward_solver", "shape_extraction", "identification_pipeline"}
                                 & {m.split(".")[-1] for m in imported})


class StoreBackendTests(unittest.TestCase):
    def test_live_excluded_mode_diagnostics_equal_the_record(self):
        roots = fixture_roots_from_environment()
        missing = sorted({"snadwich", "carbon-project-archive"} - set(roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        from domain.experiment_fixture import load_experiment_fixture_manifest
        from services.identification_campaign_run import prepare_campaign_specimens

        definition = load_campaign_definition(CAMPAIGNS / "M7_RUN_A.campaign.json")
        fixtures = load_experiment_fixture_manifest(ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json")
        specimens = prepare_campaign_specimens(definition, ROOT, fixtures, roots)
        record = _load(CORRECTIONS / "M7_PER_SPECIMEN_DIAGNOSTICS.json")["excluded_mode_diagnostics"]["specimens"]
        for item in specimens:
            with self.subTest(specimen=item.label):
                live = [(r["experimental_mode"], r["best_fe_mode"], round(r["mac"], 12), r["fe_family"])
                        for r in item.excluded_diagnostics]
                stored = [(r["experimental_mode"], r["best_fe_mode"], round(r["mac"], 12), r["fe_family"])
                          for r in record[item.label]]
                self.assertEqual(live, stored)


if __name__ == "__main__":
    unittest.main()

"""M6-B: Stage-A → M5 validation adapter (synthetic; no Abaqus, no M3, no real specimen).

Numbered cases follow the SUPERVISOR M6-B test list (M6_DECISION_RECORD.md §13).
"""

from __future__ import annotations

import ast
from dataclasses import replace
import inspect
import math
from pathlib import Path
import statistics
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import m6_stage_a_support as s  # noqa: E402
from domain.acquisition_linkage import SetupRepeatClassification, SetupRepeatEligibility  # noqa: E402
from domain.modal_input_source import ModalInputSource, classify_modal_dataset  # noqa: E402
from domain.stage_a_experiment import (  # noqa: E402
    ExcitationEvidence,
    ExcitationRoute,
    GaugeUncertainty,
    RefusalCode,
    StageAExperimentalEvidence,
    StageAInputRefusal,
)
from services import stage_a_validation as adapter  # noqa: E402
from services.identification_verdict import VerdictContext  # noqa: E402
from services.practical_identifiability import CovarianceComponent  # noqa: E402
from services.stage_a_validation import (  # noqa: E402
    D12Status,
    ResultContext,
    SigmaKind,
    StageASigmaTerm,
    StageAValidationError,
    ValidationStatus,
    run_stage_a_validation,
    stage_a_repeat_comparison_inputs,
)

FIXED_TRUTH = dict(s.TRUTH, D12=s.GOVERNED_NU12 * s.TRUTH["D11"])
MODULES = ("src/services/stage_a_validation.py", "src/domain/stage_a_experiment.py")


def fixed_path_run(**overrides):
    """No D12 sensitivity (b = 0): the full system is rank-deficient and D12 cannot be identified."""
    arguments = dict(forward=s.forward(s.B_NONE), pairing=s.pairing(b=s.B_NONE),
                     evidence=s.evidence(s.truth_frequencies(s.B_NONE, FIXED_TRUTH)))
    arguments.update(overrides)
    return s.run(**arguments)


def refusal_codes(**overrides) -> set[RefusalCode]:
    try:
        s.run(**overrides)
    except StageAInputRefusal as refusal:
        return set(refusal.codes)
    raise AssertionError("expected StageAInputRefusal")


class RecoveryAndD12Tests(unittest.TestCase):
    def test_01_synthetic_d11_d66_recovery(self):
        for report, truth in ((s.run(), s.TRUTH), (fixed_path_run(), FIXED_TRUTH)):
            with self.subTest(fitted=report.fitted_parameters):
                self.assertIs(report.status, ValidationStatus.ESTIMATE_REPORTED)
                for name in ("D11", "D66"):
                    self.assertAlmostEqual(report.estimates[name] / truth[name], 1.0, delta=1e-4)
                    self.assertLess(abs(math.log(report.estimates[name] / truth[name])),
                                    report.statistical_sd_ln[name])

    def test_02_d12_full_rank_case_is_fitted(self):
        report = s.run()
        self.assertEqual(report.d12["status"], D12Status.FITTED.value)
        self.assertEqual(report.fitted_parameters, ("D11", "D12", "D66"))
        self.assertEqual(report.d12["full_system_at_start"]["status"], "FULL_RANK")
        self.assertEqual(report.d12["full_system_at_p_hat"]["status"], "FULL_RANK")
        self.assertAlmostEqual(report.estimates["D12"] / s.TRUTH["D12"], 1.0, delta=1e-3)
        self.assertAlmostEqual(report.nu12_used, s.TRUTH["D12"] / s.TRUTH["D11"], delta=1e-4)  # not the 0.05 line

    def test_03_d12_rank_deficient_uses_governed_fixed_path_only(self):
        report = fixed_path_run()
        self.assertEqual(report.d12["full_system_at_start"]["status"], "RANK_DEFICIENT")
        self.assertEqual(report.d12["status"], D12Status.NOT_IDENTIFIED.value)
        self.assertEqual(report.fitted_parameters, ("D11", "D66"))
        self.assertNotIn("D12", report.estimates)
        self.assertNotIn("D12", report.statistical_sd_ln)
        self.assertEqual(report.nu12_used, 0.05)
        self.assertIn("D12 not identified: governed fixed ν12 = 0.05 used (D-051)", report.open_conditions)

    def test_04_no_pseudo_inverse(self):
        boom = mock.Mock(side_effect=AssertionError("pseudo-inverse used"))
        with mock.patch("numpy.linalg.pinv", boom), mock.patch("scipy.linalg.pinv", boom):
            fixed_path_run()
            s.run()
        boom.assert_not_called()
        for module in MODULES:
            self.assertNotIn("pinv", (ROOT / module).read_text(encoding="utf-8"))

    def test_05_no_scientific_override_and_required_rank_is_a_hard_refusal(self):
        names = set(inspect.signature(run_stage_a_validation).parameters)
        self.assertEqual(names, {"evidence", "pairing", "forward", "sigma", "start", "bounds", "lm_settings",
                                 "case_label"})
        with self.assertRaises(TypeError):
            s.run(override=True)
        # No D66 sensitivity: even the governed (D11, D66) system is rank-deficient → REFUSED, no estimate.
        zero = np.zeros(6)
        report = s.run(forward=s.forward(s.B_NONE, c=zero), pairing=s.pairing(b=s.B_NONE, c=zero),
                       evidence=s.evidence(s.truth_frequencies(s.B_NONE, FIXED_TRUTH, c=zero)))
        self.assertIs(report.status, ValidationStatus.REFUSED)
        self.assertIsNone(report.estimates)
        self.assertIsNone(report.derived)
        self.assertTrue(report.refusal_reasons)


class ThicknessTests(unittest.TestCase):
    def test_06_e_and_g12_scale_as_t_to_the_minus_three(self):
        base = s.run()
        k = 1.1
        scaled = s.run(evidence=s.evidence(thickness=s.thickness(tuple(v * k for v in s.THICKNESS_MM))))
        for name in ("E_flex_mpa", "G12_flex_mpa"):
            self.assertEqual(base.derived[name].thickness_exponent, -3)
            self.assertAlmostEqual(scaled.derived[name].value_mpa / base.derived[name].value_mpa, k ** -3, places=9)
        mean = statistics.fmean(s.THICKNESS_MM)
        d11, d12, d66 = (base.estimates[p] for p in ("D11", "D12", "D66"))
        nu, t = d12 / d11, mean / 1000.0
        self.assertAlmostEqual(base.derived["E_flex_mpa"].value_mpa, 12 * d11 * (1 - nu * nu) / t ** 3 / 1e6, places=6)
        self.assertAlmostEqual(base.derived["G12_flex_mpa"].value_mpa, 12 * d66 / t ** 3 / 1e6, places=6)

    def test_06b_matches_the_existing_stage_a_flexural_formula(self):
        from services.uncertainty_service import apparent_flexural_properties  # legacy formula, cross-check only

        report = s.run()
        legacy = apparent_flexural_properties(report.estimates["D11"], report.estimates["D12"],
                                              report.estimates["D66"], report.thickness_mean_mm / 1000.0)
        self.assertAlmostEqual(report.derived["E_flex_mpa"].value_mpa, legacy.E_flex / 1e6, places=6)
        self.assertAlmostEqual(report.derived["G12_flex_mpa"].value_mpa, legacy.G12_flex / 1e6, places=6)

    def test_07_spatial_scatter_is_the_sample_sd_not_divided_by_sqrt_n(self):
        report = s.run()
        mean, sd = statistics.fmean(s.THICKNESS_MM), statistics.stdev(s.THICKNESS_MM)
        spatial = report.derived["E_flex_mpa"].thickness_spatial_sd_ln
        self.assertAlmostEqual(spatial, 3 * sd / mean, places=12)
        self.assertGreater(spatial, 2.5 * 3 * sd / mean / math.sqrt(len(s.THICKNESS_MM)))
        doubled = s.run(evidence=s.evidence(thickness=s.thickness(s.THICKNESS_MM + tuple(
            v + 1e-9 for v in s.THICKNESS_MM))))  # 18 points of the same plate: the scatter does not shrink
        self.assertAlmostEqual(doubled.derived["E_flex_mpa"].thickness_spatial_sd_ln / spatial, 1.0, delta=0.07)

    def test_08_gauge_uncertainty_is_a_separate_component(self):
        without = s.run()
        gauge = GaugeUncertainty(0.002, "synthetic gauge calibration")
        with_gauge = s.run(evidence=s.evidence(thickness=s.thickness(gauge=gauge)))
        mean = statistics.fmean(s.THICKNESS_MM)
        for name in ("E_flex_mpa", "G12_flex_mpa"):
            a, b = without.derived[name], with_gauge.derived[name]
            self.assertIsNone(a.thickness_gauge_sd_ln)
            self.assertAlmostEqual(b.thickness_gauge_sd_ln, 3 * 0.002 / mean, places=12)
            self.assertAlmostEqual(b.thickness_spatial_sd_ln, a.thickness_spatial_sd_ln, places=15)
            self.assertAlmostEqual(b.statistical_sd_ln_with_thickness, math.sqrt(
                b.frequency_statistical_sd_ln ** 2 + b.thickness_spatial_sd_ln ** 2 + b.thickness_gauge_sd_ln ** 2),
                places=12)
        self.assertTrue(any("gauge uncertainty not supplied" in c for c in without.open_conditions))
        resolution_only = s.run(evidence=s.evidence(thickness=replace(s.thickness(), gauge_resolution_mm=0.001)))
        self.assertIsNone(resolution_only.derived["E_flex_mpa"].thickness_gauge_sd_ln)  # never invented


class InputRefusalTests(unittest.TestCase):
    def test_09_frf_only_input_is_refused(self):
        frf = SimpleNamespace(modes=[SimpleNamespace(number=i, metadata={"dataset_type": 58}) for i in (1, 2)],
                              metadata={"dataset_type": 58})
        classification = classify_modal_dataset(frf)  # the M1.1 policy itself
        self.assertIs(classification.source, ModalInputSource.PEAK_DERIVED)
        frequencies = s.truth_frequencies()
        modal = replace(s.modal_input(frequencies, dataset_types=(58,)), source_classification=classification)
        codes = refusal_codes(evidence=s.evidence(modal_input=modal))
        self.assertIn(RefusalCode.FRF_ONLY_INPUT, codes)
        self.assertIn(RefusalCode.NOT_CURVE_FITTED, codes)

    def test_10_missing_frozen_modal_set_is_refused(self):
        modal = s.modal_input(s.truth_frequencies(), frozen=False)
        self.assertIn(RefusalCode.MISSING_FROZEN_MODAL_SET, refusal_codes(evidence=s.evidence(modal_input=modal)))
        self.assertIn(RefusalCode.MISSING_FROZEN_MODAL_SET, refusal_codes(evidence=s.evidence(modal_input=None)))

    def test_11_fewer_than_nine_thickness_points_are_refused(self):
        eight = s.thickness(s.THICKNESS_MM[:8])
        self.assertIn(RefusalCode.INSUFFICIENT_THICKNESS_POINTS, refusal_codes(evidence=s.evidence(thickness=eight)))
        self.assertIn(RefusalCode.MISSING_THICKNESS, refusal_codes(evidence=s.evidence(thickness=None)))

    def test_12_missing_attachment_or_non_contact_evidence_is_refused(self):
        cases = {
            RefusalCode.MISSING_ATTACHMENT_MASS: ExcitationEvidence(ExcitationRoute.CONTACT_ATTACHMENT, ("E1", "E2")),
            RefusalCode.NON_CONTACT_ROUTE_NOT_APPROVED: ExcitationEvidence(ExcitationRoute.NON_CONTACT, ("E1", "E2")),
            RefusalCode.INSUFFICIENT_EXCITATION_LOCATIONS: replace(s.excitation(), locations=("E1",)),
            RefusalCode.MISSING_EXCITATION_EVIDENCE: None,
        }
        for code, excitation in cases.items():
            with self.subTest(code=code):
                self.assertIn(code, refusal_codes(evidence=s.evidence(excitation=excitation)))
        # Recorded but not in the model: refused.
        self.assertIn(RefusalCode.ATTACHMENT_MASS_NOT_MODELLED, refusal_codes(forward=s.forward(attachment_g=1.5)))
        # An approved non-contact route with no modelled attachment is admitted.
        approved = ExcitationEvidence(ExcitationRoute.NON_CONTACT, ("E1", "E2"), non_contact_approval="DECISION-X")
        report = s.run(evidence=s.evidence(excitation=approved), forward=s.forward(attachment_g=None))
        self.assertIs(report.status, ValidationStatus.ESTIMATE_REPORTED)

    def test_13_missing_suspension_evidence_is_refused(self):
        self.assertIn(RefusalCode.MISSING_SUSPENSION, refusal_codes(evidence=s.evidence(suspension=None)))
        high = replace(s.evidence().suspension, suspension_max_hz=31.0)  # mode 1 (29.7 Hz) lies below
        self.assertIn(RefusalCode.MODE_BELOW_SUSPENSION, refusal_codes(evidence=s.evidence(suspension=high)))

    def test_all_gaps_are_listed_together(self):
        empty = StageAExperimentalEvidence("SYNTH-PLATE-1", "RUN-A", None, None, None, None, None)
        codes = refusal_codes(evidence=empty, pairing=s.pairing(registration_hash=None))
        self.assertTrue({RefusalCode.MISSING_FROZEN_MODAL_SET, RefusalCode.MISSING_THICKNESS,
                         RefusalCode.MISSING_EXCITATION_EVIDENCE, RefusalCode.MISSING_SUSPENSION,
                         RefusalCode.MISSING_SPECIMEN_MEASUREMENTS, RefusalCode.MISSING_GEOMETRY_CALIBRATION} <= codes)
        self.assertFalse(issubclass(StageAInputRefusal, (ValueError, RuntimeError)))


class LegacyRuleTests(unittest.TestCase):
    def test_14_mode_one_is_not_excluded(self):
        base = s.run()
        frequencies = s.truth_frequencies()
        frequencies[1] *= 1.01
        shifted = s.run(evidence=s.evidence(frequencies))
        self.assertNotAlmostEqual(shifted.estimates["D11"], base.estimates["D11"], places=4)  # mode 1 is a fit term
        for module in MODULES:
            text = (ROOT / module).read_text(encoding="utf-8")
            self.assertNotIn("excluded_experimental_mode_ids", text)
            self.assertNotIn("probable suspension", text)

    def test_15_legacy_condition_number_thresholds_are_not_applied(self):
        b = s.B_INDEPENDENT * 0.02
        report = s.run(forward=s.forward(b), pairing=s.pairing(b=b), evidence=s.evidence(s.truth_frequencies(b)))
        self.assertGreater(report.rank_diagnostics["condition_number_diagnostic"], 100.0)  # legacy warning level
        self.assertEqual(report.d12["status"], D12Status.FITTED.value)  # decided by rcond 1e-3 alone
        self.assertIs(report.status, ValidationStatus.ESTIMATE_REPORTED)
        for module in MODULES:
            text = (ROOT / module).read_text(encoding="utf-8")
            for token in ("condition_warning_threshold", "collinearity_warning_threshold", "conditioning_override"):
                self.assertNotIn(token, text)

    def test_16_legacy_fixed_pair_fallback_is_not_used(self):
        legacy = s.pairing(pairing_source="fixed_pair_synthetic_fallback")
        self.assertIn(RefusalCode.FIXED_PAIR_FALLBACK, refusal_codes(pairing=legacy))
        loose = s.pairing(policy_id="some/other-policy")
        self.assertIn(RefusalCode.NON_STRICT_PAIRING_POLICY, refusal_codes(pairing=loose))
        text = (ROOT / "src/services/stage_a_validation.py").read_text(encoding="utf-8")
        self.assertNotIn("allow_fixed_pair_fallback", text)
        self.assertNotIn("PairingProviderMode", text)


class ContextTests(unittest.TestCase):
    def test_17_stage_a_validation_reports_estimate_and_labelled_uncertainty(self):
        report = s.run()
        self.assertIs(report.context, ResultContext.STAGE_A_VALIDATION)
        self.assertIs(report.status, ValidationStatus.ESTIMATE_REPORTED)
        self.assertEqual(set(report.statistical_sd_ln), {"D11", "D12", "D66"})
        self.assertEqual(report.birge["status"], "AVAILABLE")
        self.assertTrue(report.model_form_robustness["supports_green"])
        self.assertIn("not 1 sigma", report.model_form_robustness["note"])
        derived = report.derived["G12_flex_mpa"].to_dict()
        for label in ("frequency_statistical_sd_ln", "frequency_birge_adjusted_sd_ln", "thickness_spatial_sd_ln",
                      "thickness_gauge_sd_ln", "statistical_sd_ln_with_thickness",
                      "model_form_robustness_half_range_ln"):
            self.assertIn(label, derived)
        self.assertIn("PROVISIONAL input Σ:Sigma_setup: final M6 acceptance requires measured M6.2 evidence",
                      report.open_conditions)
        self.assertIn("Sigma_meas NOT_AVAILABLE (not invented; D-053)", report.open_conditions)

    def test_18_no_production_identified_while_family_consistency_is_not_available(self):
        report = s.run()  # every other guard passes on noise-free synthetic data
        verdicts = report.production_verdict["verdicts"]
        self.assertEqual(report.production_verdict["context"], VerdictContext.PRODUCTION.value)
        self.assertEqual(report.production_verdict["guards"]["family_consistency"], "NOT_AVAILABLE")
        for parameter, record in verdicts.items():
            self.assertEqual(record["verdict"], "NOT_IDENTIFIABLE", parameter)
            self.assertIsNone(record["reported_value"])
            self.assertTrue(any(r.startswith("FAMILY_CONSISTENCY") for r in record["reasons"]))
        self.assertFalse(report.production_identified)
        self.assertNotIn(report.status.value, ("IDENTIFIED", "WIDE"))
        self.assertEqual([c.value for c in ResultContext], ["STAGE_A_VALIDATION"])
        self.assertEqual({c.value for c in VerdictContext}, {"SYNTHETIC_GATE", "PRODUCTION"})  # M5 enum unchanged

    def test_19_deterministic_provenance_and_hashes(self):
        first, second = s.run(), s.run()
        self.assertEqual(first.record_hash, second.record_hash)
        self.assertEqual(first.input_hashes, second.input_hashes)
        self.assertEqual(s.forward().identity_hash, s.forward().identity_hash)
        self.assertNotEqual(s.forward().identity_hash, s.forward(attachment_g=1.5).identity_hash)
        changed = s.run(evidence=s.evidence(thickness=s.thickness(s.THICKNESS_MM[:-1] + (0.454,))))
        self.assertNotEqual(changed.input_hashes["evidence"], first.input_hashes["evidence"])
        self.assertNotEqual(changed.record_hash, first.record_hash)
        self.assertEqual(len(first.record_hash), 64)

    def test_20_no_abaqus_or_m3_execution_dependency(self):
        forbidden = ("subprocess", "abaqus_bridge", "forward_builder", "forward_solver", "shared_carbon_forward",
                     "identification_pipeline", "shape_extraction", "stage_a_identification_service",
                     "inverse_solver", "uncertainty_service", "sensitivity_service", "identifiability_service")
        allowed_matrix_names = {"MatrixModelError", "StageAAffineBasis", "StageAMatrixParameters",
                                "solve_generalized_eigenproblem"}
        for module in MODULES:
            text = (ROOT / module).read_text(encoding="utf-8")
            tree = ast.parse(text)
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                    if node.module.endswith("matrix_model_service"):
                        self.assertLessEqual({a.name for a in node.names}, allowed_matrix_names)
                elif isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                for name in names:
                    for item in forbidden:
                        self.assertFalse(name == item or name.endswith("." + item), f"{module} imports {name}")
            for literal in ("SP-11", "SP11", "Snadwich", "D:\\", "carbon_project_archive"):
                self.assertNotIn(literal, text)
        guard = mock.Mock(side_effect=AssertionError("external process started"))
        with mock.patch.object(subprocess, "Popen", guard), mock.patch.object(subprocess, "run", guard), \
                mock.patch("services.matrix_model_service.run_abaqus_matrix_job", guard):
            self.assertIs(s.run().status, ValidationStatus.ESTIMATE_REPORTED)
        guard.assert_not_called()


class ObservationStructureTests(unittest.TestCase):
    def test_confirmed_cluster_is_one_fit_term_and_holdouts_stay_out_of_the_fit(self):
        pair = s.pairing(clusters=(("R1", "R2"),), holdout=(6,))
        self.assertEqual(pair.fit_term_ids, ("R3", "R4", "R5", "C(R1+R2)"))
        report = s.run(pairing=pair)
        self.assertIs(report.status, ValidationStatus.ESTIMATE_REPORTED)
        self.assertEqual(report.birge["dof"], 4 - 3)
        for name in ("D11", "D66"):  # within the SPEC §8 stop rule (step < 0.2·sd), i.e. well inside 1σ
            self.assertLess(abs(math.log(report.estimates[name] / s.TRUTH[name])), report.statistical_sd_ln[name])

    def test_systematic_family_error_is_reported_not_hidden(self):
        frequencies = s.truth_frequencies()
        for mode in (2, 4, 6):  # family "T", all shifted the same way by far more than 2σ
            frequencies[mode] *= 1.03
        report = s.run(evidence=s.evidence(frequencies))
        self.assertIs(report.status, ValidationStatus.ESTIMATE_REPORTED)
        self.assertNotEqual(report.birge["status"], "AVAILABLE")
        self.assertTrue(any(c.startswith("residual-pattern test FAIL") for c in report.open_conditions))
        self.assertTrue(all(v["verdict"] == "NOT_IDENTIFIABLE" for v in report.production_verdict["verdicts"].values()))

    def test_branch_tracking_refusal_is_a_refused_report_not_a_re_pairing(self):
        from services.branch_tracker import BranchTrackingRefusal, RefusalKind

        lost = mock.Mock(side_effect=BranchTrackingRefusal(RefusalKind.BRANCH_LOSS, ("R3: synthetic loss",)))
        with mock.patch.object(adapter, "track_branches", lost):
            report = s.run()
        self.assertIs(report.status, ValidationStatus.REFUSED)
        self.assertIsNone(report.estimates)
        self.assertIn("BRANCH_LOSS", report.refusal_reasons[0])
        self.assertIn("no re-pairing", report.refusal_reasons[0])

    def test_sigma_kinds_cannot_be_relabelled(self):
        pair = s.pairing()
        setup = s.sigma(pair)[0].component
        with self.assertRaises(StageAValidationError):
            StageASigmaTerm(SigmaKind.MEASUREMENT, setup)  # setup scatter named as Σ_meas
        meas = CovarianceComponent("Sigma_meas", setup.matrix, False, "synthetic modal-fit uncertainty")
        report = s.run(sigma=(StageASigmaTerm(SigmaKind.MEASUREMENT, meas), s.sigma(pair)[0]))
        self.assertNotIn("Sigma_meas NOT_AVAILABLE (not invented; D-053)", report.open_conditions)
        with self.assertRaises(StageAValidationError):
            s.run(sigma=())


class RepeatInterfaceTests(unittest.TestCase):
    def test_m62_comparison_inputs_are_thickness_free_and_have_no_rule_yet(self):
        original = s.run()
        frequencies = {k: v * 1.002 for k, v in s.truth_frequencies().items()}
        repeat = s.run(evidence=s.evidence(frequencies, test_run_id="RUN-B"))
        eligible = SetupRepeatClassification(SetupRepeatEligibility.FREQUENCY_AND_SHAPE, ("synthetic remount",),
                                             "RUN-A", "RUN-B")
        thickness_hash = s.thickness().record_hash
        inputs = stage_a_repeat_comparison_inputs(original, repeat, eligible, (thickness_hash, thickness_hash))
        self.assertEqual(inputs.status, "AGREEMENT_RULE_PENDING_M6_2_DECISION")
        self.assertEqual(inputs.shared_thickness_record, thickness_hash)
        self.assertAlmostEqual(inputs.ln_difference["D11"], math.log(repeat.estimates["D11"] /
                                                                     original.estimates["D11"]), places=12)
        self.assertFalse(hasattr(inputs, "agrees"))
        undocumented = replace(eligible, eligibility=SetupRepeatEligibility.INSUFFICIENTLY_DOCUMENTED)
        with self.assertRaises(StageAValidationError):
            stage_a_repeat_comparison_inputs(original, repeat, undocumented, (thickness_hash, thickness_hash))


if __name__ == "__main__":
    unittest.main()

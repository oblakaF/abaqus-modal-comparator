"""ABM-AUD-6: input uncertainty, sensitivity, the research summary and its export, for the registered Ritz estimate.

Synthetic data only, from the independent free-plate solution of ``test_abm_aud5_ritz_estimation`` (never the program's
Ritz service). What is checked against an independent statement:

* thickness at a held measured mass: the frequencies fix D / (surface mass), so D does not move and E goes as h^-3;
* thickness at a held volume density: the mass grows with h, so D goes as h and E as h^-2;
* mass: every D and E is proportional to it;
* length and width: enlarging both by one factor s at a held mass is a similar plate with surface mass / s^2 and
  frequencies ~ sqrt(D / mu) / a^2, so D goes as s^2: the length and width exponents of every D must add up to 2.

The exact cases are checked by running the ordinary estimation with the changed input (not the uncertainty service) and
comparing with the power law; the uncertainty service must then report the same numbers. Tolerances: the fits recover
the independent values within 2e-4 (see the ABM-AUD-5 tests); a central difference with a 1 % step has a truncation
error of order 1e-4 in an exponent, so exponents are compared within 0.02.
"""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import test_abm_aud5_ritz_estimation as t5  # noqa: E402

from new_gui import analyze_model as am  # noqa: E402
from new_gui import research_tuning_model as rm  # noqa: E402
from services import registered_ritz_estimation as rre  # noqa: E402
from services import registered_ritz_uncertainty as rru  # noqa: E402
from services import research_frequency_stability as rfs  # noqa: E402
from services import research_frequency_tuning as rft  # noqa: E402

RECOVERY = t5.RECOVERY
EXPONENT = 0.02
RANGES = {"length": (319.5, 320.5), "thickness": (0.85, 0.90), "mass": (119.4, 120.6), "nu12": (0.03, 0.08)}


class _Estimate(t5._Rectangle):
    """The orthotropic 320 x 240 mm plate of ABM-AUD-5 with its supported estimate, and one uncertainty assessment."""

    _made: dict = {}  # computed once for the module: every class below reads the same estimate and assessment

    @classmethod
    def setUpClass(cls):
        made = _Estimate._made
        if not made:
            super().setUpClass()
            fit = t5.request(cls.rset)
            made.update(truth=cls.truth, rset=cls.rset, plate=cls.plate, result=cls.result, block=cls.block,
                        review=cls.review, fit=fit, nominal=rru.quantities(cls.result, cls.plate),
                        uncertainty=rru.run_uncertainty(cls.rset, cls.plate, fit, cls.review, cls.result, RANGES))
        for name, value in made.items():
            setattr(cls, name, value)

    def refit(self, **changes):
        """The ordinary estimation with a changed declared plate (not the uncertainty service)."""
        changed = replace(self.plate, **changes)
        result, _block = rre.run_estimation(self.rset, changed, self.fit, rre.shape_review(self.rset, changed))
        self.assertEqual(result.status, rft.SUPPORTED, result.reasons)
        return rru.quantities(result, changed)

    def sensitivity(self, name, assumption=None):
        return next(row for row in self.uncertainty["sensitivity"]
                    if row["input"] == name and (assumption is None or row["assumption"] == assumption))

    def ranged(self, name, bound, assumption=None):
        return next(row for row in self.uncertainty["ranges"] if row["input"] == name and row["bound"] == bound
                    and (assumption is None or row["assumption"] == assumption))


class ExactScalingTests(_Estimate):
    def test_thickness_at_a_held_measured_mass(self):
        """E ~ h^-3 and D unchanged: the ordinary estimation with another thickness, against the power law."""
        factor = 0.90 / t5.THICKNESS
        values = self.refit(thickness_mm=0.90)
        for name in ("D11", "D22", "D66"):
            self.assertAlmostEqual(values[name] / self.nominal[name], 1.0, delta=1.0e-6, msg=name)
        for name in ("E_x", "E_y", "G12"):
            self.assertAlmostEqual(values[name] / self.nominal[name], factor ** -3, delta=1.0e-6, msg=name)
        row = self.ranged("thickness", "high", rru.MASS_HELD)
        self.assertEqual(row["method"], rru.EXACT)
        for name in rru.QUANTITIES:  # and the uncertainty service reports those very numbers
            self.assertAlmostEqual(row["values"][name] / values[name], 1.0, delta=1.0e-6, msg=name)
        self.assertEqual(self.sensitivity("thickness", rru.MASS_HELD)["exponents"],
                         {"D11": 0.0, "D22": 0.0, "D66": 0.0, "E_x": -3.0, "E_y": -3.0, "G12": -3.0})
        # against the independent truth itself: the data were made with h = 0.875 mm and E1 = 62 GPa
        self.assertAlmostEqual(values["E_x"] / (self.TRUTH[0] * factor ** -3), 1.0, delta=RECOVERY)

    def test_thickness_at_a_held_volume_density(self):
        """E ~ h^-2 and D ~ h: the estimation with another thickness and the mass that the same density gives."""
        factor = 0.90 / t5.THICKNESS
        values = self.refit(thickness_mm=0.90, mass_g=t5.MASS * factor)
        for name in ("D11", "D22", "D66"):
            self.assertAlmostEqual(values[name] / self.nominal[name], factor, delta=1.0e-6, msg=name)
        for name in ("E_x", "E_y", "G12"):
            self.assertAlmostEqual(values[name] / self.nominal[name], factor ** -2, delta=1.0e-6, msg=name)
        row = self.ranged("thickness", "high", rru.DENSITY_HELD)
        for name in rru.QUANTITIES:
            self.assertAlmostEqual(row["values"][name] / values[name], 1.0, delta=1.0e-6, msg=name)
        self.assertEqual(self.sensitivity("thickness", rru.DENSITY_HELD)["exponents"]["E_x"], -2.0)
        self.assertEqual(self.sensitivity("thickness", rru.DENSITY_HELD)["exponents"]["D11"], 1.0)

    def test_the_two_thickness_assumptions_are_kept_apart(self):
        held = {row["assumption"] for row in self.uncertainty["sensitivity"] if row["input"] == "thickness"}
        self.assertEqual(held, {rru.MASS_HELD, rru.DENSITY_HELD})
        mass, density = (self.ranged("thickness", "low", a)["change"]["E_x"] for a in (rru.MASS_HELD, rru.DENSITY_HELD))
        self.assertAlmostEqual(mass, (0.85 / t5.THICKNESS) ** -3 - 1.0, delta=1.0e-9)
        self.assertAlmostEqual(density, (0.85 / t5.THICKNESS) ** -2 - 1.0, delta=1.0e-9)
        self.assertGreater(mass, density)  # they are different numbers, and both are shown
        envelopes = [e for e in self.uncertainty["envelope"] if e["input"] == "thickness"]
        self.assertEqual(len(envelopes), 2)  # one per assumption, never merged

    def test_the_mass_scales_every_stiffness_and_modulus(self):
        values = self.refit(mass_g=120.6)
        for name in rru.QUANTITIES:
            self.assertAlmostEqual(values[name] / self.nominal[name], 120.6 / t5.MASS, delta=1.0e-6, msg=name)
            self.assertAlmostEqual(self.ranged("mass", "high")["values"][name] / values[name], 1.0, delta=1.0e-6)
        self.assertEqual(set(self.sensitivity("mass")["exponents"].values()), {1.0})


class DimensionAndPoissonTests(_Estimate):
    def test_length_and_width_exponents_obey_the_similar_plate_law(self):
        """Both dimensions enlarged by s at a held mass: D ~ s^2 for every stiffness, so the two exponents add up to 2;
        E follows D because the thickness is held."""
        length, width = self.sensitivity("length"), self.sensitivity("width")
        self.assertEqual((length["status"], width["status"]), (rru.ASSESSED, rru.ASSESSED))
        for name in rru.QUANTITIES:
            self.assertAlmostEqual(length["exponents"][name] + width["exponents"][name], 2.0, delta=EXPONENT, msg=name)
        # the bending stiffness along a direction is governed by that direction's length: ~ +3 and ~ -1
        self.assertAlmostEqual(length["exponents"]["D11"], 3.0, delta=0.1)
        self.assertAlmostEqual(width["exponents"]["D11"], -1.0, delta=0.1)
        self.assertAlmostEqual(width["exponents"]["D22"], 3.0, delta=0.1)

    def test_a_length_range_is_the_estimate_at_its_two_ends(self):
        values = self.refit(length_mm=320.5)
        row = self.ranged("length", "high")
        self.assertEqual(row["method"], rru.REFIT)
        for name in rru.QUANTITIES:
            self.assertAlmostEqual(row["values"][name] / values[name], 1.0, delta=1.0e-9, msg=name)
        predicted = (320.5 / 320.0) ** self.sensitivity("length")["exponents"]["D11"] - 1.0
        self.assertAlmostEqual(row["change"]["D11"], predicted, delta=2.0e-4)  # the local exponent predicts the end

    def test_nu12_moves_the_estimates_little_and_d12_follows_it(self):
        row = self.sensitivity("nu12")
        self.assertEqual(row["status"], rru.ASSESSED)
        self.assertLess(max(abs(v) for v in row["exponents"].values()), 0.05)
        values = self.refit(nu12=0.08)
        high = self.ranged("nu12", "high")
        for name in rru.QUANTITIES:
            self.assertAlmostEqual(high["values"][name] / values[name], 1.0, delta=1.0e-9, msg=name)
        result, block = rre.run_estimation(self.rset, replace(self.plate, nu12=0.08), self.fit,
                                           rre.shape_review(self.rset, replace(self.plate, nu12=0.08)))
        stiffness = block["stiffness"]["values"]
        self.assertAlmostEqual(stiffness["D12"] / stiffness["D22"], 0.08, delta=1.0e-12)  # the fixed relation


class RangesAndStatusTests(_Estimate):
    def test_an_unstated_range_is_not_assessed_and_nothing_is_invented(self):
        inputs = {item["input"]: item for item in self.uncertainty["inputs"]}
        self.assertEqual((inputs["width"]["status"], inputs["width"]["low"], inputs["width"]["high"]),
                         (rru.NOT_ASSESSED, None, None))
        self.assertFalse([row for row in self.uncertainty["ranges"] if row["input"] == "width"])
        self.assertEqual(inputs["mass"]["status"], rru.ASSESSED)
        self.assertEqual((inputs["mass"]["category"], inputs["nu12"]["category"]), (rre.MEASURED, rre.DECLARED))
        nothing = rru.run_uncertainty(self.rset, self.plate, self.fit, self.review, self.result, {})
        self.assertEqual({item["status"] for item in nothing["inputs"]}, {rru.NOT_ASSESSED})
        self.assertEqual((nothing["ranges"], nothing["envelope"]), ([], []))
        self.assertEqual(len(nothing["sensitivity"]), 6)  # the sensitivities need no range
        self.assertIn("No input range was stated", rm.uncertainty_text(nothing))

    def test_ranges_are_validated(self):
        cases = (({"mass": (121.0, 122.0)}, "does not hold the entered value 120"),
                 ({"length": (321.0, 319.0)}, "must run from a lower to a higher value"),
                 ({"thickness": (-0.1, 0.9)}, "must be positive"),
                 ({"nu12": (0.0, 1.5)}, "is not admissible"),
                 ({"density": (1.0, 2.0)}, "There is no input 'density'"),
                 ({"width": (float("nan"), 241.0)}, "is not finite"))
        for ranges, words in cases:
            with self.assertRaises(rre.EstimationRefused, msg=ranges) as refused:
                rru.run_uncertainty(self.rset, self.plate, self.fit, self.review, self.result, ranges)
            self.assertIn(words, str(refused.exception))
        ranges, problems = rm.parse_ranges({"low_mass": "119", "high_mass": "", "low_width": "a", "high_width": "b"}, self.plate)
        self.assertEqual(ranges, {})
        self.assertIn("Mass: enter both the lowest and the highest value, or neither.", problems)
        self.assertIn("Width b: 'a' to 'b' is not a range of two numbers.", problems)
        self.assertEqual(rm.parse_ranges({"low_mass": "119,5", "high_mass": "120.5"}, self.plate), ({"mass": (119.5, 120.5)}, []))

    def test_ranges_are_one_input_at_a_time_and_not_an_accuracy(self):
        text = rm.uncertainty_text(self.uncertainty)
        self.assertIn("not statistical confidence intervals", text)
        self.assertIn("not combined into one accuracy", text)
        self.assertIn("No range stated for: Width b (NOT_ASSESSED)", text)
        self.assertIn("E goes as h^-3 with the measured mass held, as h^-2 if the density were held instead", text)
        self.assertEqual(len(self.uncertainty["not_quantified"]), 4)
        self.assertIn("suspension", self.uncertainty["not_quantified"][0])
        self.assertIn("none is inferred from the frequencies", self.uncertainty["not_quantified"][0])
        self.assertIn("Model form", self.uncertainty["not_quantified"][1])
        self.assertNotIn("accuracy_percent", json.dumps(self.uncertainty))
        for envelope in self.uncertainty["envelope"]:
            self.assertIn(envelope["input"], RANGES)  # one input each; there is no combined entry

    def test_the_refits_keep_the_records_roles_and_correspondence(self):
        calls = []
        real = rre.run_estimation

        def recording(rset, plate, request, review=None, cancel=None, progress=None):
            calls.append((rset.identity, tuple((o.record, o.role, o.surrogate_rank) for o in request.observations),
                          request.parameterization, plate.reference))
            return real(rset, plate, request, review, cancel, progress)

        with mock.patch.object(rre, "run_estimation", recording):
            rru.run_uncertainty(self.rset, self.plate, self.fit, self.review, self.result, {"nu12": (0.04, 0.06)})
        self.assertEqual(len(calls), 8)  # six for the sensitivities, two for the range
        expected = (self.rset.identity, tuple((o.record, o.role, o.surrogate_rank) for o in self.fit.observations),
                    self.fit.parameterization, self.plate.reference)
        self.assertEqual(set(calls), {expected})
        self.assertEqual(expected[1][0], (1, rft.FIT, 1))  # record 1 is in every refit, as fitted

    def test_a_range_end_that_cannot_hold_the_scan_is_said_not_hidden(self):
        """A length whose low end is shorter than the measured grid: that end is NOT_ASSESSED with the reason."""
        outcome = rru.run_uncertainty(self.rset, self.plate, self.fit, self.review, self.result, {"length": (200.0, 321.0)})
        low = next(row for row in outcome["ranges"] if row["input"] == "length" and row["bound"] == "low")
        self.assertEqual((low["status"], low["values"]), (rru.NOT_ASSESSED, None))
        self.assertIn("lie outside the entered 200 x 240 mm rectangle", low["reason"])
        self.assertEqual([e for e in outcome["envelope"] if e["input"] == "length"], [])
        self.assertIn("NOT_ASSESSED: ", rm.uncertainty_range_rows(outcome)[0][3])

    def test_no_estimate_means_nothing_to_assess(self):
        without = replace(self.result, status=rft.NOT_IDENTIFIABLE)
        with self.assertRaises(rre.EstimationRefused) as refused:
            rru.run_uncertainty(self.rset, self.plate, self.fit, self.review, without, RANGES)
        self.assertIn("There is no estimate to assess: the optimizer status is NOT_IDENTIFIABLE", str(refused.exception))

    def test_cancelling_gives_no_result(self):
        cancel = threading.Event()
        cancel.set()
        self.assertIsNone(rru.run_uncertainty(self.rset, self.plate, self.fit, self.review, self.result, RANGES, cancel))


class SummaryTests(_Estimate):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        tracked = rre.tracked_request(cls.rset, cls.plate, cls.fit, cls.review)
        cls.stability = rfs.run_stability(rre.plate_inputs(cls.plate), tracked, cls.result)
        cls.rows = dict(rm.summary_rows(cls.result, cls.block, cls.stability, cls.uncertainty))

    def test_the_ten_points_are_there_in_order(self):
        self.assertEqual(list(self.rows), ["1. Experimental source", "2. Registration", "3. Mode correspondence and MAC",
                                           "4. FIT / HOLDOUT residuals", "5. Convergence and identifiability",
                                           "6. Bending stiffness (conditional)", "7. Engineering constants (conditional)",
                                           "8. Input uncertainty and sensitivity", "9. Assumptions and limitations",
                                           "10. Scientific status"])

    def test_source_registration_and_identities(self):
        self.assertIn("synthetic scan.unv, SHA-256 " + "ab" * 32, self.rows["1. Experimental source"])
        self.assertIn("records 1 (", self.rows["1. Experimental source"])  # the original record numbers, the first too
        self.assertIn("USER_CONFIRMED_REGISTRATION, hash " + "9f" * 32, self.rows["2. Registration"])
        self.assertIn("confirmed by A. Tester", self.rows["2. Registration"])
        self.assertIn("not an independent proof", self.rows["2. Registration"])
        self.assertIn("FE / EXP pairs of the comparison: 10, MAC 0.990 to 0.990", self.rows["3. Mode correspondence and MAC"])
        self.assertIn("it identifies no material", self.rows["3. Mode correspondence and MAC"])

    def test_fit_and_holdout_are_stated_apart(self):
        text = self.rows["4. FIT / HOLDOUT residuals"]
        self.assertIn("FIT: FIT_WITHIN_DIAGNOSTIC_THRESHOLD", text)
        self.assertIn("over records 1, 2, 3, 4, 5, 6, 7, 8.", text)
        self.assertIn("HOLDOUT (not fitted): HOLDOUT_WITHIN_WARNING_LEVEL", text)
        self.assertIn("over records 9, 10.", text)

    def test_the_numbers_are_the_results_own(self):
        d11, d22, _d12, d66 = t5.stiffness(*self.TRUTH)
        text = self.rows["6. Bending stiffness (conditional)"]
        for value in (d11, d22, d66):
            self.assertIn(f"{value:.4f}"[:5], text)  # the known answer, to the printed digits
        self.assertIn("D12 is the fixed relation nu12 x D22, not an estimate", text)
        self.assertIn("CONDITIONAL RESEARCH ESTIMATE", self.rows["7. Engineering constants (conditional)"])
        self.assertIn("E1 (material axis 1, along length a): 62000 MPa", self.rows["7. Engineering constants (conditional)"])
        self.assertIn("practical rank 3 of 3", self.rows["5. Convergence and identifiability"])
        self.assertIn("1 minimum/minima reached", self.rows["5. Convergence and identifiability"])
        self.assertIn(f"Leave-one-out: {rfs.STABLE} (", self.rows["5. Convergence and identifiability"])

    def test_uncertainty_limitations_and_status(self):
        text = self.rows["8. Input uncertainty and sensitivity"]
        self.assertIn("Mass 120 (MEASURED)", text)
        self.assertIn("nu12 0.05 (DECLARED ASSUMPTION)", text)
        self.assertIn("Thickness over its stated range (the measured mass is held", text)
        self.assertIn("free on all edges", self.rows["9. Assumptions and limitations"])
        self.assertIn("Model form", self.rows["9. Assumptions and limitations"])
        status = self.rows["10. Scientific status"]
        self.assertIn("NUMERICALLY SUPPORTED RESEARCH ESTIMATE", status)
        self.assertIn("Physical validity: NOT ESTABLISHED", status)
        self.assertIn("no production status is changed", status)

    def test_what_was_not_assessed_is_said(self):
        rows = dict(rm.summary_rows(self.result, self.block))
        self.assertIn("Leave-one-out stability: NOT_ASSESSED", rows["5. Convergence and identifiability"])
        self.assertIn("NOT_ASSESSED: the sensitivity and the stated ranges were not calculated",
                      rows["8. Input uncertainty and sensitivity"])

    def test_an_unstable_refit_is_named_unstable(self):
        unstable = json.loads(json.dumps(self.stability))
        unstable["assessment"]["numerical_stability"]["verdict"] = rfs.UNSTABLE
        rows = dict(rm.summary_rows(self.result, self.block, unstable))
        self.assertIn(f"Leave-one-out: {rfs.UNSTABLE}", rows["5. Convergence and identifiability"])

    def test_a_converged_high_misfit_is_diagnostic_in_every_line(self):
        import numpy as np

        frequencies = np.array(self.truth.hz[:10])
        frequencies[9] *= 1.2  # the fit converges; the prediction of the record it did not use fails
        result, block, _review = t5.estimate(t5.measured_set(self.LENGTH, self.WIDTH, self.truth, frequencies=frequencies),
                                             self.plate)
        rows = dict(rm.summary_rows(result, block))
        self.assertIn("HOLDOUT_DISAGREES", rows["4. FIT / HOLDOUT residuals"])
        self.assertIn("DIAGNOSTIC ONLY", rows["6. Bending stiffness (conditional)"])
        self.assertIn("DIAGNOSTIC ONLY", rows["7. Engineering constants (conditional)"])
        self.assertIn("DIAGNOSTIC ONLY", rows["10. Scientific status"])
        self.assertNotIn("E1 (material axis 1", rows["7. Engineering constants (conditional)"])
        frequencies = np.array(self.truth.hz[:10])
        frequencies[3] *= 1.12
        result, block, _review = t5.estimate(t5.measured_set(self.LENGTH, self.WIDTH, self.truth, frequencies=frequencies),
                                             self.plate)
        rows = dict(rm.summary_rows(result, block))
        self.assertIn("HIGH_MISFIT", rows["4. FIT / HOLDOUT residuals"])
        self.assertNotIn("NUMERICALLY SUPPORTED", rows["10. Scientific status"])

    def test_unidentifiable_parameters_give_no_numbers(self):
        result = replace(self.result, status=rft.NOT_IDENTIFIABLE, reasons=["Practical rank 2 of 3."], practical_rank=2)
        block = rre.complete(json.loads(json.dumps(self.block)), result)
        rows = dict(rm.summary_rows(result, block))
        self.assertIn("No estimate", rows["6. Bending stiffness (conditional)"])
        self.assertIn("none given", rows["7. Engineering constants (conditional)"])
        self.assertIn("practical rank 2 of 3", rows["5. Convergence and identifiability"])
        self.assertIn("NO ESTIMATE", rows["10. Scientific status"])

    def test_exchanged_axes_are_two_alternatives_and_neither_is_chosen(self):
        mirror = [{"values": {"E1": 62000.0, "E2": 44000.0, "G12": 4600.0}, "cost": 1.0e-12},
                  {"values": {"E1": 44000.0, "E2": 62000.0, "G12": 4600.0}, "cost": 1.1e-12}]
        result = replace(self.result, status=rft.MIRROR, minima=mirror)
        block = rre.complete(json.loads(json.dumps(self.block)), result)
        rows = dict(rm.summary_rows(result, block))
        self.assertIn("Two alternatives, neither chosen: alternative A:", rows["6. Bending stiffness (conditional)"])
        self.assertIn("alternative B:", rows["6. Bending stiffness (conditional)"])
        constants = rows["7. Engineering constants (conditional)"]
        self.assertIn("E_stiff (direction not identifiable): 62000 MPa", constants)
        self.assertNotIn("E1 (", constants)
        self.assertIn("axis ambiguity, neither chosen", rows["5. Convergence and identifiability"])
        outcome = rru.run_uncertainty(self.rset, self.plate, self.fit, self.review, result, {})
        self.assertIn("the exchanged alternative is as likely by these frequencies", outcome["axis_note"])

    def test_the_readable_summary_holds_the_points_and_the_tables(self):
        text = rm.summary_text(self.result, self.block, self.stability, self.uncertainty)
        for words in ("RESEARCH SUMMARY", rre.LABEL, "1. Experimental source", "10. Scientific status",
                      "Frequencies: FIT and HOLDOUT", "Bending stiffness", "Engineering constants",
                      "Fixed correspondence against the reviewed shapes", "Inputs and their stated ranges",
                      "Local sensitivity of the estimates", "Estimates at the ends of the stated ranges",
                      "Leave one FIT record out", "Not quantified", "releases no material property"):
            self.assertIn(words, text)
        self.assertNotIn("Rendered from the saved result", text)
        self.assertIn("Rendered from the saved result old.json", rm.summary_text(self.result, self.block, saved_from="old.json"))
        self.assertTrue(text.isascii() or "—" in text or "…" in text or "²" in text)  # plain text, readable anywhere
        self.assertLess(max(len(line) for line in text.splitlines() if not line.startswith("    ")), 2000)


class SavedTests(_Estimate):
    def exported(self, uncertainty=True):
        import tempfile

        block = dict(self.block, uncertainty=self.uncertainty) if uncertainty else self.block
        path = Path(tempfile.mkdtemp()) / "estimate.json"
        rft.write_export(rre.export_document(self.result, block), path)
        return path

    def test_the_uncertainty_part_is_saved_and_comes_back_as_it_was(self):
        path = self.exported()
        with mock.patch.object(rre, "run_estimation", side_effect=AssertionError("refitted")), \
                mock.patch.object(rru, "run_uncertainty", side_effect=AssertionError("assessed again")):
            result, _stability, block = rm.open_saved_registered(path)
        self.assertEqual(block["uncertainty"], self.uncertainty)
        self.assertEqual(rm.summary_rows(result, block, None, block["uncertainty"]),
                         rm.summary_rows(self.result, self.block, None, self.uncertainty))
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["registered_estimation"]["uncertainty"]["schema"], rru.SCHEMA)
        self.assertEqual(document["registered_estimation"]["records"][0][0], 1)
        self.assertEqual(document["registered_estimation"]["plate"]["categories"][3], rre.MEASURED)

    def test_a_result_saved_before_this_task_still_opens(self):
        """No uncertainty part (the ABM-AUD-5 form): it opens, and the summary says what was not assessed."""
        path = self.exported(uncertainty=False)
        self.assertNotIn("uncertainty", json.loads(path.read_text(encoding="utf-8"))["registered_estimation"])
        result, _stability, block = rm.open_saved_registered(path)
        self.assertIsNone(block.get("uncertainty"))
        rows = dict(rm.summary_rows(result, block))
        self.assertIn("NOT_ASSESSED", rows["8. Input uncertainty and sensitivity"])
        self.assertIn("NUMERICALLY SUPPORTED RESEARCH ESTIMATE", rows["10. Scientific status"])

    def test_a_damaged_or_foreign_uncertainty_part_is_refused(self):
        path = self.exported()
        document = json.loads(path.read_text(encoding="utf-8"))
        for change in (lambda u: u.update(schema="other/1"), lambda u: u.pop("sensitivity"),
                       lambda u: u["inputs"][0].pop("nominal")):
            damaged = json.loads(json.dumps(document))
            change(damaged["registered_estimation"]["uncertainty"])
            path.write_text(json.dumps(damaged), encoding="utf-8")
            with self.assertRaises(rft.TuningRefused):
                rm.open_saved_registered(path)

    def test_a_file_cannot_raise_the_status_through_the_summary(self):
        path = self.exported()
        document = json.loads(path.read_text(encoding="utf-8"))
        document["rows"][0]["ln_after"] = 0.2  # a FIT residual of 20 %: the saved verdict no longer follows
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(rft.TuningRefused) as refused:
            rm.open_saved_registered(path)
        self.assertIn("does not follow from its own residuals", str(refused.exception))


class PageTests(t5._Page):
    """The page, on the ABM-AUD-5 fixture (a confirmed registration, a comparison, the square plate, E1 = E2)."""

    def estimated(self):
        _window, analyze, panel = self.tuning()
        panel.use_registered()
        self.declare(panel, material_axis=rre.AXIS_LENGTH, axis_evidence="layup record L-3")
        self.reviewed(panel)
        self.roles(panel)
        self.fitted(panel)
        return analyze, panel

    def assessed(self, panel):
        self.assertTrue(panel.run_uncertainty(), panel.message.text())
        self.wait_tuning(panel)
        self.assertIsNotNone(panel.uncertainty, panel.message.text())

    def test_ranges_assessment_summary_and_both_exports(self):
        _analyze, panel = self.estimated()
        summary = dict(panel.summary_points())
        self.assertEqual(len(summary), 10)
        self.assertIn("NOT_ASSESSED", summary["8. Input uncertainty and sensitivity"])
        self.assertIn("turned scan.unv", summary["1. Experimental source"])
        self.assertIn("NOT_ASSESSED", panel.uncertainty_note.text())
        self.assertTrue(panel.uncertainty_button.isEnabled())
        self.assertEqual(panel.reg_ranges["low_mass"].text(), "")  # no range is prefilled
        panel.set_ranges(low_mass=119.4, high_mass=120.6, low_thickness=0.85, high_thickness=0.9)
        self.assessed(panel)
        inputs = {row[0]: row for row in self.cells(panel, "reg_unc_inputs")}
        self.assertEqual(inputs["Mass"][1:], ["120 g", rre.MEASURED, "119.4 to 120.6 g", rru.ASSESSED])
        self.assertEqual(inputs["Width b"][3:], ["not stated", rru.NOT_ASSESSED])
        self.assertEqual(inputs["nu12"][2], rre.DECLARED)
        sensitivity = self.cells(panel, "reg_unc_sensitivity")
        thickness = [row for row in sensitivity if row[0] == "Thickness"]
        self.assertEqual([row[6] for row in thickness], ["-3.000", "-2.000"])  # E along x: mass held, density held
        self.assertEqual([row[3] for row in thickness], ["+0.000", "+1.000"])  # D11
        ranges = self.cells(panel, "reg_unc_ranges")
        low = next(row for row in ranges if row[0].startswith("Thickness low") and row[1] == rru.MASS_HELD)
        self.assertEqual(low[6], f"{(0.85 / t5.THICKNESS) ** -3 - 1.0:+.2%}")
        summary = dict(panel.summary_points())
        self.assertIn("Mass over its stated range", summary["8. Input uncertainty and sensitivity"])
        self.assertIn("No range stated for: Length a, Width b, nu12 (NOT_ASSESSED)", summary["8. Input uncertainty and sensitivity"])

        exported, readable = self.root / "estimate.json", self.root / "summary.txt"
        self.assertTrue(panel.export(str(exported)), panel.message.text())
        self.assertTrue(panel.export_summary(str(readable)), panel.message.text())
        text = readable.read_text(encoding="utf-8")
        self.assertIn("RESEARCH SUMMARY", text)
        self.assertIn("Estimates at the ends of the stated ranges", text)
        self.assertNotIn("Rendered from the saved result", text)
        keys = ("reg_unc_inputs", "reg_unc_sensitivity", "reg_unc_ranges", "reg_stiffness", "reg_constants")
        before = {key: self.cells(panel, key) for key in keys}
        shown = panel.summary_points()
        self.assertTrue(all(body.wordWrap() for _head, body in panel.summary_labels))  # sentences, read in full
        with mock.patch.object(rft, "run_tuning", side_effect=AssertionError("refitted")), \
                mock.patch.object(rru, "run_uncertainty", side_effect=AssertionError("assessed again")), \
                mock.patch.object(am, "confirm_sources", side_effect=AssertionError("a saved result reads no source")):
            self.assertTrue(panel.open_result(str(exported)), panel.message.text())
            self.assertEqual({key: self.cells(panel, key) for key in keys}, before)
            self.assertEqual(panel.summary_points(), shown)
            again = self.root / "summary of the saved result.txt"
            self.assertTrue(panel.export_summary(str(again)))  # a saved result can be rendered, and says what it is
        saved = again.read_text(encoding="utf-8")
        self.assertIn("Rendered from the saved result estimate.json", saved)
        notice = saved.split("\n\n")[1]  # the one paragraph a rendering of a snapshot adds
        self.assertIn("historical snapshot", notice)
        self.assertEqual(saved.replace(notice + "\n\n", "", 1), text)  # everything else is the same text
        self.assertFalse(panel.uncertainty_button.isEnabled())  # nothing of a snapshot is recalculated
        self.assertFalse(panel.export_button.isEnabled())
        self.assertTrue(panel.summary_button.isEnabled())

    def test_changed_ranges_and_inputs_never_leave_an_old_assessment(self):
        _analyze, panel = self.estimated()
        panel.set_ranges(low_mass=119.4, high_mass=120.6)
        self.assessed(panel)
        self.assertIn("reg_unc_ranges", panel._tables)
        panel.set_ranges(high_mass=121.0)  # another range: the assessment is dropped, the fit stays
        self.app.processEvents()
        self.assertIsNone(panel.uncertainty)
        self.assertNotIn("reg_unc_ranges", panel._tables)
        self.assertIsNotNone(panel.result)
        self.assertIn("NOT_ASSESSED", dict(panel.summary_points())["8. Input uncertainty and sensitivity"])
        panel.set_ranges(low_mass=120.5)  # a range that does not hold the entered mass
        self.app.processEvents()
        self.assertIn("does not hold the entered value 120", panel.ranges_check.text())
        self.assertFalse(panel.run_uncertainty())
        self.assertIn("Not assessed", panel.message.text())
        panel.set_ranges(low_mass=119.4)
        self.assessed(panel)
        panel.reg_fields["thickness"].setText("0.9")  # an input of the fit: everything of the old result goes
        self.app.processEvents()
        self.assertIsNone(panel.result)
        self.assertIsNone(panel.uncertainty)
        self.assertNotIn("reg_summary", panel._tables)
        self.assertFalse(panel.summary_button.isEnabled())

    def test_a_changed_source_file_stops_the_assessment(self):
        analyze, panel = self.estimated()
        path = Path(analyze.inputs.full_experimental.source_path)
        path.write_text(path.read_text() + "\n", encoding="utf-8")
        self.assertTrue(panel.run_uncertainty())
        self.wait_tuning(panel)
        self.assertIsNone(panel.uncertainty)
        self.assertIn("a source file changed after the comparison", panel.message.text())

    def test_an_assessment_can_be_cancelled(self):
        _analyze, panel = self.estimated()
        gate = threading.Event()
        real = rru.run_uncertainty

        def slow(*args, **kwargs):
            gate.wait(20.0)
            return real(*args, **kwargs)

        with mock.patch.object(rru, "run_uncertainty", slow):
            self.assertTrue(panel.run_uncertainty())
            self.assertTrue(panel.cancel_button.isEnabled())
            self.assertTrue(panel.cancel())
            gate.set()
            self.wait_tuning(panel)
        self.assertIsNone(panel.uncertainty)
        self.assertEqual(panel.state.text(), "Assessment cancelled. No uncertainty result.")
        self.assertIsNotNone(panel.result)  # the estimate itself stays


if __name__ == "__main__":
    unittest.main()

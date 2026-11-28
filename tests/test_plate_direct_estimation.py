"""PLATE-DIRECT-ESTIMATION-01: the standalone rectangular plate route (no Abaqus, no INP, no ODB, no registration).

Synthetic plates only. The "measured" frequencies are those of the Kirchhoff-Ritz free plate at KNOWN constants, written
as curve-fitted records; the route gets the frequencies and the entered plate, nothing else. What is checked:

* the known stiffnesses of an isotropic and of an orthotropic plate are among the minima the fit reaches, the lowest one;
* a frequency-only result is never presented as a verified or supported estimate, and several minima are never reduced
  to one answer;
* D does not depend on the thickness and follows the mass; the moduli follow thickness^-3 (and the stated range);
* an ambiguous or wrong correspondence is said, not hidden; the lowest record is never dropped by the program;
* invalid inputs and FRF peak files are refused before anything is solved;
* a result is saved, opened and exported, and a file cannot raise its own status;
* the page runs the whole workflow in the real window.
"""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from plate_forward_support import AbaqusForbiddenMixin  # noqa: E402
from services import registered_ritz_estimation as rre  # noqa: E402
from services import registered_ritz_uncertainty as rru  # noqa: E402
from services import research_frequency_tuning as rft  # noqa: E402
from services import standalone_plate_estimation as spe  # noqa: E402

CATEGORIES = (rre.MEASURED, rre.MEASURED, rre.MEASURED, rre.MEASURED, rre.DECLARED)
ISOTROPIC = (70000.0, 70000.0, 26923.0)  # MPa: E, E, G = E / (2 (1 + 0.3))
ORTHOTROPIC = (30000.0, 20000.0, 9000.0)


def declared(length=300.0, width=200.0, thickness=2.0, mass=190.0, nu12=0.3, **changes) -> rre.Plate:
    values = dict(categories=CATEGORIES, inputs_source="synthetic measurement sheet", reference=spe.NEUTRAL_REFERENCE)
    values.update(changes)
    return rre.Plate(length, width, thickness, mass, nu12, **values)


def spectrum(plate: rre.Plate, constants, count=10) -> list:
    """The free-plate frequencies of KNOWN constants: the synthetic measurement."""
    return [float(v) for v in rft.Surrogate(rre.plate_inputs(plate), 14, count + 4).frequencies(*constants)[:count]]


def measured(frequencies, name="plate.unv") -> spe.PlateModalSet:
    return spe.modal_set(experimental_file=name, experimental_sha256="0" * 64, modal_set_title="synthetic PolyMAX",
                         records=[(number, hz) for number, hz in enumerate(frequencies, start=1)])


def request(pset, form=rft.TIED, holdout=(9, 10), excluded=(), declared_ranks=None, **settings) -> rft.TuningRequest:
    observations = rft.observations_by_rank(pset.records, holdout=holdout, excluded=excluded, declared=declared_ranks)
    return rft.TuningRequest(observations, form, rft.DECLARED if declared_ranks else rft.RANK_ORDER, **settings)


def stiffness(constants, plate):
    d = rft.bending_stiffness(constants[0], constants[1], plate.nu12, constants[2], plate.thickness_mm)
    return {"D11": d.D11, "D22": d.D22, "D66": d.D66}


class _Solved(AbaqusForbiddenMixin, unittest.TestCase):
    """One isotropic and one orthotropic fit, shared by the tests that only read them."""

    @classmethod
    def setUpClass(cls):
        cls.iso_plate = declared()
        cls.iso_set = measured(spectrum(cls.iso_plate, ISOTROPIC))
        cls.iso_request = request(cls.iso_set)
        cls.iso_result, cls.iso_block = spe.run_estimation(cls.iso_set, cls.iso_plate, cls.iso_request,
                                                           ranges={"thickness": (1.9, 2.1)})
        cls.ortho_plate = declared(400.0, 250.0)
        cls.ortho_set = measured(spectrum(cls.ortho_plate, ORTHOTROPIC))
        cls.ortho_request = request(cls.ortho_set, rft.FREE)
        cls.ortho_result, cls.ortho_block = spe.run_estimation(cls.ortho_set, cls.ortho_plate, cls.ortho_request)


class KnownStiffnessTests(_Solved):
    def test_the_isotropic_stiffnesses_are_the_lowest_minimum(self):
        truth = stiffness(ISOTROPIC, self.iso_plate)
        found = self.iso_block["stiffness"]["alternatives"][0] if self.iso_block["stiffness"]["alternatives"] else \
            self.iso_block["stiffness"]["values"]
        for name, value in truth.items():
            self.assertAlmostEqual(found[name] / value, 1.0, places=6, msg=name)
        lowest = self.iso_block["minima"][0]
        self.assertAlmostEqual(lowest["E1"] / ISOTROPIC[0], 1.0, places=6)
        self.assertAlmostEqual(lowest["G12"] / ISOTROPIC[2], 1.0, places=6)
        self.assertLess(lowest["fit_rms_ln"], 1.0e-8)
        self.assertLess(lowest["holdout_rms_ln"], 1.0e-8)  # the two records that took no part in the fit

    def test_the_orthotropic_stiffnesses_are_the_lowest_minimum(self):
        truth = stiffness(ORTHOTROPIC, self.ortho_plate)
        alternatives = self.ortho_block["stiffness"]["alternatives"]
        found = alternatives[0] if alternatives else self.ortho_block["stiffness"]["values"]
        for name, value in truth.items():
            self.assertAlmostEqual(found[name] / value, 1.0, places=5, msg=name)
        self.assertGreater(found["D11"], found["D22"])  # the stiff direction is along x = the length, as built
        self.assertEqual(self.ortho_block["stiffness"]["frame"], {"x": "length a", "y": "width b"})

    def test_d_is_primary_and_the_moduli_are_named_by_plate_edges_only(self):
        for block in (self.iso_block, self.ortho_block):
            constants = block["constants"]
            self.assertEqual(constants["kind"], spe.PLATE_AXIS_VALUES)
            names = " ".join(name for name, _value in constants["rows"])
            self.assertNotIn("E1", names)
            self.assertNotIn("material axis", names)
            self.assertIn("no material axis 1 is named", " ".join(constants["reasons"]))
            self.assertEqual(constants["axis_evidence"], "")
        self.assertIn("Ex (along x = length a)", " ".join(name for name, _v in self.ortho_block["constants"]["rows"]))
        self.assertIn("Ey (along y = width b)", " ".join(name for name, _v in self.ortho_block["constants"]["rows"]))
        self.assertIn("Gxy", " ".join(name for name, _v in self.ortho_block["constants"]["rows"]))

    def test_a_frequency_only_result_is_never_a_verified_or_supported_estimate(self):
        for result, block in ((self.iso_result, self.iso_block), (self.ortho_result, self.ortho_block)):
            verdict = block["presentation"]["verdict"]
            self.assertIn(verdict, (spe.FREQUENCY_ONLY, spe.COMPETING))
            self.assertNotEqual(verdict, rre.SUPPORTED_ESTIMATE)
            self.assertEqual(block["presentation"]["reasons"][0], spe.NO_MAPPING)
            self.assertEqual(block["label"], spe.LABEL)
            self.assertEqual(block["correspondence"]["kind"], rre.RANK_HYPOTHESIS)
            self.assertEqual(block["registration"], {})
            self.assertEqual(result.label, rft.RESULT_LABEL)
            statements = {row[0]: row for row in block["statements"]}
            self.assertEqual(statements["7. Physical validity"][1], rft.NOT_ESTABLISHED)
            self.assertEqual(statements["5. Modal correspondence and ambiguity"][1], rre.RANK_HYPOTHESIS)
            included = [o.record for o in rft.observations_by_rank(block["records"], holdout=(9, 10))]
            self.assertEqual(block["identities"]["unresolved_records"], included)  # every identity stays unresolved

    def test_several_minima_are_all_listed_and_none_is_chosen(self):
        """The tuning service's own rule: different starts ending at different minima give no single candidate."""
        for result, block in ((self.iso_result, self.iso_block), (self.ortho_result, self.ortho_block)):
            self.assertEqual(len(block["minima"]), len(result.minima))
            if len(result.minima) > 1 and result.status == rft.STARTS_DISAGREE:
                self.assertEqual(block["presentation"]["verdict"], spe.COMPETING)
                self.assertFalse(block["presentation"]["numerically_consistent"])
                self.assertEqual(len(block["stiffness"]["alternatives"]), len(result.minima))
                self.assertIsNone(result.candidate)  # the tuning service issues none; this route adds none
                costs = [row["cost"] for row in block["minima"]]
                self.assertEqual(costs, sorted(costs))
                self.assertIn("none is chosen", " ".join(block["presentation"]["reasons"]))
        self.assertEqual(self.iso_result.status, rft.STARTS_DISAGREE)  # the situation these plates are in

    def test_rank_and_residuals_are_reported(self):
        statements = {row[0]: row for row in self.ortho_block["statements"]}
        self.assertEqual(statements["2. Parameter identifiability (rank)"][1], "practical rank 3 of 3")
        self.assertIn("condition number", statements["2. Parameter identifiability (rank)"][2])
        self.assertEqual(statements["3. FIT spectral residuals"][1], rft.FIT_WITHIN)
        self.assertEqual(statements["4. HOLDOUT predictive residuals"][1], rft.HOLDOUT_WITHIN)
        self.assertEqual(self.ortho_result.practical_rank, 3)
        self.assertEqual([row["role"] for row in self.ortho_result.rows].count(rft.HOLDOUT), 2)


class ScalingTests(_Solved):
    def test_d_does_not_depend_on_the_thickness_and_the_moduli_go_as_its_inverse_cube(self):
        thick = replace(self.iso_plate, thickness_mm=2.5)  # the same measured frequencies, another declared thickness
        _result, block = spe.run_estimation(self.iso_set, thick, self.iso_request)
        before, after = self.iso_block["stiffness"]["alternatives"][0], block["stiffness"]["alternatives"][0]
        for name in ("D11", "D22", "D66"):
            self.assertAlmostEqual(after[name] / before[name], 1.0, places=6, msg=name)
        self.assertAlmostEqual(block["minima"][0]["E1"] / self.iso_block["minima"][0]["E1"], (2.5 / 2.0) ** -3, places=6)
        self.assertAlmostEqual(block["minima"][0]["G12"] / self.iso_block["minima"][0]["G12"], (2.5 / 2.0) ** -3, places=6)

    def test_d_and_the_moduli_follow_the_mass(self):
        heavy = replace(self.iso_plate, mass_g=190.0 * 1.2)
        _result, block = spe.run_estimation(self.iso_set, heavy, self.iso_request)
        before, after = self.iso_block["stiffness"]["alternatives"][0], block["stiffness"]["alternatives"][0]
        for name in ("D11", "D22", "D66"):
            self.assertAlmostEqual(after[name] / before[name], 1.2, places=6, msg=name)
        self.assertAlmostEqual(block["minima"][0]["E1"] / self.iso_block["minima"][0]["E1"], 1.2, places=6)

    def test_the_stated_thickness_range_gives_the_moduli_at_its_two_ends(self):
        constants = self.iso_block["constants"]
        self.assertEqual(constants["thickness_range_mm"], [1.9, 2.1])
        self.assertEqual(len(constants["thickness_rows"]), len(constants["rows"]))
        for (name, value), (same, low, high) in zip(constants["rows"], constants["thickness_rows"]):
            self.assertEqual(name, same)
            self.assertAlmostEqual(low, value * (2.1 / 2.0) ** -3, places=6)
            self.assertAlmostEqual(high, value * (1.9 / 2.0) ** -3, places=6)
            self.assertLess(low, value)
            self.assertGreater(high, value)
        self.assertEqual(self.ortho_block["constants"]["thickness_rows"], [])  # no range stated: none is invented
        self.assertIn("No thickness range was stated", self.ortho_block["constants"]["thickness_note"])

    def test_a_thickness_range_that_does_not_hold_the_entered_value_is_refused(self):
        with self.assertRaises(rre.EstimationRefused) as refused:
            spe.run_estimation(self.iso_set, self.iso_plate, self.iso_request, ranges={"thickness": (2.1, 2.3)})
        self.assertIn("does not hold the entered value", str(refused.exception))

    def test_the_input_assessment_refits_through_this_routes_own_fit(self):
        """The uncertainty service's hook: every refit is the standalone fit of the changed plate, never the registered one."""
        calls = []
        single = replace(self.iso_result, status=rft.SUPPORTED)  # stands for a result with one estimate

        def estimate(plate, same_request, cancel, progress):
            calls.append(plate)
            self.assertIs(same_request, self.iso_request)
            return single, self.iso_block

        found = rru.run_uncertainty(self.iso_set, self.iso_plate, self.iso_request, None, single,
                                    {"thickness": (1.9, 2.1), "length": (299.0, 301.0)}, estimate=estimate)
        self.assertEqual(found["refits"], len(calls))
        self.assertGreaterEqual(len(calls), 8)  # length, width, nu12 by -/+ 1 % and the two ends of the length range
        self.assertEqual({plate.thickness_mm for plate in calls}, {2.0})  # the thickness is exact scaling, not a refit
        exact = {(row["input"], row["assumption"]): row["exponents"] for row in found["sensitivity"] if row["method"] == rru.EXACT}
        self.assertEqual(exact[("thickness", rru.MASS_HELD)]["E_x"], -3.0)
        self.assertEqual(exact[("thickness", rru.MASS_HELD)]["D11"], 0.0)
        self.assertEqual(found["set_identity"], self.iso_set.identity)

    def test_the_input_assessment_needs_one_estimate(self):
        with self.assertRaises(rre.EstimationRefused) as refused:
            spe.run_uncertainty(self.iso_set, self.iso_plate, self.iso_request, self.iso_result, {})
        self.assertIn("There is no estimate to assess", str(refused.exception))


class CorrespondenceTests(_Solved):
    def test_the_lowest_record_is_never_dropped_by_the_program(self):
        observations = self.iso_request.observations
        self.assertEqual(observations[0].role, rft.FIT)
        self.assertEqual(observations[0].surrogate_rank, 1)
        self.assertEqual(self.iso_block["identities"]["lowest_measured_role"], rft.FIT)
        self.assertEqual(self.iso_result.first_mode_check["lowest_measured_role"], rft.FIT)

    def test_excluding_the_lowest_record_is_the_users_act_and_is_said(self):
        excluded = request(self.iso_set, excluded=(1,))
        self.assertEqual({o.record: o.surrogate_rank for o in excluded.observations if o.record == 2}, {2: 2})  # not renumbered
        result, block = spe.run_estimation(self.iso_set, self.iso_plate, excluded)
        self.assertEqual(block["identities"]["lowest_measured_role"], rft.EXCLUDED)
        self.assertIn("EXCLUDED by the user; it was not discarded by the program", " ".join(block["identities"]["ambiguity"]))
        self.assertIn("is EXCLUDED by the user", " ".join(result.warnings))
        self.assertEqual(block["identities"]["rows"][0]["status"], "EXCLUDED_BY_THE_USER")
        self.assertIn(1, result.correspondence["unmatched_ranks"])

    def test_one_rank_for_two_records_is_refused_before_anything_is_solved(self):
        solves = []
        ambiguous = request(self.iso_set, declared_ranks={3: 4})  # records 3 and 4 both at rank 4
        with self.assertRaises(rft.TuningRefused) as refused:
            spe.run_estimation(self.iso_set, self.iso_plate, ambiguous, progress=solves.append)
        self.assertIn("rank 4 is assigned to records 3, 4", str(refused.exception))
        self.assertEqual(solves, [])

    def test_a_wrong_hypothesis_is_shown_as_unresolved_ambiguity_not_as_an_estimate(self):
        """Records 3 and 4 exchanged on purpose: the fit cannot know, and the result does not pretend to."""
        exchanged = request(self.iso_set, declared_ranks={3: 4, 4: 3})
        result, block = spe.run_estimation(self.iso_set, self.iso_plate, exchanged)
        self.assertNotEqual(block["presentation"]["verdict"], rre.SUPPORTED_ESTIMATE)
        self.assertGreater(result.rms_fit_after, 1.0e-3)  # the exact spectrum is no longer reproduced
        rows = {row["record"]: row for row in block["identities"]["rows"]}
        self.assertEqual((rows[3]["rank"], rows[4]["rank"]), (4, 3))
        self.assertEqual((rows[3]["nearest_rank"], rows[4]["nearest_rank"]), (3, 4))
        self.assertIn("nearer in frequency to another Ritz rank", " ".join(block["identities"]["ambiguity"]))
        self.assertIn("Declared by the user: record 3 -> rank 4", " ".join(result.correspondence["notes"]))

    def test_a_plate_whose_lowest_minimum_is_not_the_truth_is_still_only_competing_hypotheses(self):
        """A low shear modulus: the frequency-only fit ends away from the known constants. Nothing verifies it."""
        plate = declared()
        pset = measured(spectrum(plate, (60000.0, 40000.0, 5000.0), 14))
        result, block = spe.run_estimation(pset, plate, request(pset, rft.FREE, holdout=(13, 14)))
        self.assertEqual(block["presentation"]["verdict"], spe.COMPETING)
        self.assertGreater(len(block["minima"]), 1)
        self.assertGreater(abs(block["minima"][0]["G12"] / 5000.0 - 1.0), 0.5)  # not the known value
        self.assertIsNone(result.candidate)
        self.assertFalse(block["presentation"]["numerically_consistent"])
        self.assertTrue(block["identities"]["ambiguity"])


class RefusalTests(AbaqusForbiddenMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.plate = declared()
        self.pset = measured([100.0, 150.0, 300.0, 350.0, 400.0, 480.0, 600.0, 700.0, 850.0, 960.0])

    def refused(self, plate=None, req=None, **kw) -> str:
        solves = []
        with self.assertRaises(rft.TuningRefused) as refused:
            spe.run_estimation(self.pset, plate or self.plate, req or request(self.pset), progress=solves.append, **kw)
        self.assertEqual(solves, [], "refused before anything is solved")
        return str(refused.exception)

    def test_invalid_plate_inputs(self):
        self.assertIn("Thickness must be a positive number", self.refused(replace(self.plate, thickness_mm=0.0)))
        self.assertIn("Mass must be a positive number", self.refused(replace(self.plate, mass_g=-1.0)))
        self.assertIn("Length must be a positive number", self.refused(replace(self.plate, length_mm=float("nan"))))
        self.assertIn("Width must be a positive number", self.refused(replace(self.plate, width_mm=float("inf"))))
        self.assertIn("not admissible", self.refused(replace(self.plate, nu12=1.2)))
        self.assertIn("State where the dimensions", self.refused(replace(self.plate, inputs_source="  ")))
        self.assertIn("State for each of length", self.refused(replace(self.plate, categories=())))

    def test_no_value_from_an_fe_model_and_no_material_axis(self):
        fe = (rre.IMPORTED_FE,) + CATEGORIES[1:]
        self.assertIn("There is no FE model in the standalone route", self.refused(replace(self.plate, categories=fe)))
        named = replace(self.plate, material_axis=rre.AXIS_LENGTH, material_axis_evidence="layup record")
        self.assertIn("names no material axis", self.refused(named))

    def test_too_few_fit_records_and_a_bad_search_range(self):
        few = request(self.pset, rft.FREE, holdout=(4, 5, 6, 7, 8, 9, 10))
        self.assertIn("3 FIT frequencies cannot determine 3 parameters", self.refused(req=few))
        self.assertIn("search range factor must exceed 1", self.refused(req=request(self.pset, search_factor=1.0)))
        tied = replace(self.plate, reference=(50000.0, 30000.0, 5000.0))
        self.assertIn("needs equal reference E1 and E2", self.refused(tied))

    def test_the_correspondence_must_name_the_records_of_the_set(self):
        other = measured([100.0, 150.0, 300.0, 350.0, 400.0])
        self.assertIn("does not name exactly the records", self.refused(req=request(other, holdout=())))

    def test_invalid_modal_sets(self):
        for records, text in (([], "holds no curve-fitted record"), ([(1, 100.0), (1, 200.0)], "more than once"),
                              ([(1, 0.0), (2, 200.0)], "no positive, finite frequency"),
                              ([(1, float("nan"))], "no positive, finite frequency")):
            with self.assertRaises(rre.EstimationRefused) as refused:
                spe.modal_set(experimental_file="x.unv", experimental_sha256="0" * 64, records=records)
            self.assertIn(text, str(refused.exception))
        with self.assertRaises(rre.EstimationRefused) as refused:
            spe.modal_set(experimental_file="x.unv", experimental_sha256="", records=[(1, 100.0)])
        self.assertIn("no content identity", str(refused.exception))

    def test_a_search_into_inadmissible_values_is_a_refusal_with_its_remedy(self):
        plate = declared(300.0, 300.0)
        pset = measured(spectrum(plate, (60000.0, 30000.0, 12000.0)))
        with self.assertRaises(rre.EstimationRefused) as refused:
            spe.run_estimation(pset, plate, request(pset, rft.FREE))
        self.assertEqual(refused.exception.code, rre.MODEL_REFUSED)
        self.assertIn("Use a smaller search range factor", str(refused.exception))

    def test_cancelling_gives_no_result(self):
        cancel = threading.Event()
        cancel.set()
        result, block = spe.run_estimation(self.pset, self.plate, request(self.pset), cancel=cancel)
        self.assertEqual(result.status, rft.CANCELLED)
        self.assertIsNone(block)


class SavedResultTests(_Solved):
    def document(self, block=None) -> dict:
        return json.loads(json.dumps(spe.export_document(self.iso_result, block or self.iso_block), default=str))

    def test_a_saved_result_opens_as_it_was_saved(self):
        document = self.document()
        self.assertIsNone(document["abaqus_elastic_candidate"])  # there is no INP whose *Elastic could be rewritten
        self.assertIn("No INP", document["abaqus_elastic_candidate_withheld"])
        self.assertIn(spe.LABEL, document["statement"])
        self.assertIsNone(rre.block_from_export(document, self.iso_result))  # it is not a registered result
        result = rft.result_from_export(document)
        block = spe.block_from_export(document, result)
        for key in ("presentation", "stiffness", "constants", "statements", "identities", "minima", "plate", "records"):
            self.assertEqual(block[key], self.iso_block[key], key)

    def test_a_file_cannot_raise_its_own_status(self):
        document = self.document()
        part = document[spe.EXPORT_KEY]
        part["presentation"] = {"verdict": rre.SUPPORTED_ESTIMATE, "reasons": [], "numerically_consistent": True}
        part["correspondence"]["statement"] = "verified by shape"
        part["constants"]["rows"] = [["E1 (material axis 1)", 1.0]]
        block = spe.block_from_export(document, rft.result_from_export(document))
        self.assertEqual(block["presentation"], self.iso_block["presentation"])
        self.assertEqual(block["correspondence"]["statement"], spe.CORRESPONDENCE_STATEMENT)
        self.assertEqual(block["constants"], self.iso_block["constants"])

    def test_damaged_or_foreign_parts_are_refused(self):
        result = self.iso_result
        for change, text in ((lambda part: part.update(schema="standalone-plate-estimation/0"), "another version"),
                             (lambda part: part.update(label="VERIFIED"), "another version"),
                             (lambda part: part.pop("identities"), "incomplete"),
                             (lambda part: part.update(minima=[]), "does not list the minima"),
                             (lambda part: part["correspondence"].update(kind=rre.SHAPE_REVIEWED), "cannot have"),
                             (lambda part: part["plate"].update(thickness_mm=-2.0), "not admissible"),
                             (lambda part: part.update(thickness_range_mm=[3.0, 4.0]), "does not hold the entered value"),
                             (lambda part: part["identities"].update(rows=[{}]), "damaged")):
            document = self.document()
            change(document[spe.EXPORT_KEY])
            with self.assertRaises(rft.TuningRefused) as refused:
                spe.block_from_export(document, result)
            self.assertIn(text, str(refused.exception))
        self.assertIsNone(spe.block_from_export({"schema": rft.SCHEMA}, result))  # an export of another route


# ================================================================================================ the page


def write_modal_file(path: Path, frequencies) -> Path:
    """A PolyMAX-like UNV (dataset 15 + 55) with the given frequencies. The shapes are arbitrary: the route never reads them."""
    import pyuff

    path = Path(path)
    if path.exists():
        path.unlink()
    xs, ys = np.meshgrid(np.linspace(0.0, 0.3, 5), np.linspace(0.0, 0.2, 4))
    x, y = xs.ravel(), ys.ravel()
    n = len(x)
    nodes = np.arange(1, n + 1)
    uff = pyuff.UFF(str(path))
    uff.write_sets(pyuff.prepare_15(node_nums=nodes, def_cs=np.zeros(n, dtype=int), disp_cs=np.zeros(n, dtype=int),
                                    color=np.ones(n, dtype=int), x=x, y=y, z=np.zeros(n)), "add")
    for k, f in enumerate(frequencies):
        w = 2 * np.pi * f
        values = np.cos((k + 1) * 7.0 * x) * np.exp(1j * 0.3)
        uff.write_sets(pyuff.prepare_55(id1="PolyMAX", id2="synthetic", id3="x", id4="x", id5="x", model_type=1,
                                        analysis_type=3, data_ch=2, spec_data_type=11, data_type=5, n_data_per_node=3,
                                        load_case=1, mode_n=k + 1, eig=-0.003 * w + 1j * w, modal_a=1 + 0j, modal_b=1 + 0j,
                                        node_nums=nodes, r1=np.zeros(n, complex), r2=np.zeros(n, complex), r3=values,
                                        return_full_dict=True), "add")
    text = path.read_text()
    path.write_text(text.replace("        11         5         6", "        11         5         3"))
    return path


class PageTests(AbaqusForbiddenMixin, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication

        cls.app = QApplication.instance() or QApplication([])
        cls.folder = Path(tempfile.mkdtemp())
        cls.frequencies = spectrum(declared(), ISOTROPIC)
        cls.unv = write_modal_file(cls.folder / "plate.unv", cls.frequencies)

    def panel(self, confirm=True, size=(1366, 768)):
        from new_gui import production_window as pw

        window = pw.ProductionWindow()
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        window.resize(*size)
        window.show()
        window.show_page(pw.TUNING_PAGE)
        self.app.processEvents()
        panel = window.research_tuning
        self.asked = []
        panel._ask_confirm = lambda title, text: self.asked.append(text) or confirm
        self.addCleanup(panel.shutdown)
        self.window = window
        return panel

    def wait(self, panel, limit=240.0):
        end = time.monotonic() + limit
        while panel.busy() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()

    def entered(self, panel, unv=None, **values):
        self.assertTrue(panel.choose_plate_file(str(unv or self.unv)))
        self.wait(panel)
        fields = dict(length=300, width=200, thickness=2, mass=190, nu12=0.3, source="measurement sheet 1",
                      categories=dict(zip(rre.INPUT_NAMES, CATEGORIES)))
        fields.update(values)
        panel.set_plate(**fields)
        self.app.processEvents()
        return panel

    def solved(self, panel):
        panel.reg_fixed.setChecked(True)
        self.assertTrue(panel.run(), panel.message.text())
        self.wait(panel)
        self.assertIsNotNone(panel.result, panel.message.text())
        return panel

    def test_a_modal_file_and_an_entered_plate_are_enough(self):
        panel = self.entered(self.panel())
        self.assertTrue(panel.standalone)
        self.assertEqual(panel.paths, {"inp": "", "unv": "", "odb": ""})  # no INP, no ODB
        self.assertIn("10 curve-fitted records", panel.standalone_state.text())
        self.assertTrue(panel.registered_form.isVisible())
        self.assertIs(panel.registered_form.parentWidget(), panel.plate_button.parentWidget())  # in the standalone card
        for widget in (panel.take_fe_button, panel.reg_linked, panel.reg_material_axis, panel.review_button,
                       panel.reg_axes["length_axis"], panel.reg_fields["axis_evidence"]):
            self.assertFalse(widget.isVisible(), widget.objectName())  # nothing of an FE frame or a shape review
        for choice in panel.reg_categories.values():
            self.assertEqual([b.text() for b in choice.buttons if b.isVisible()], ["Measured", "Declared"])
        self.assertEqual(panel.registered_check.text(), "")  # the reference constants are optional here
        self.assertEqual(panel.roles()[1], rft.FIT)  # the lowest record is in the fit by default
        self.assertEqual(panel.run_button.text(), "Run research fit...")
        cells = dict(panel.table_cells("standalone_identity"))
        self.assertEqual(cells["FE model, registration"], "none")
        self.assertIn("not used", cells["Mode shapes and point positions"])

    def test_the_hypothesis_must_be_fixed_and_confirmed_before_a_fit(self):
        panel = self.entered(self.panel(confirm=False))
        self.assertFalse(panel.run())
        self.assertIn("correspondence is not fixed", panel.message.text())
        panel.reg_fixed.setChecked(True)
        panel.set_role(8, rft.HOLDOUT)  # a later change of a role withdraws the fixing
        self.assertFalse(panel.reg_fixed.isChecked())
        panel.reg_fixed.setChecked(True)
        self.assertFalse(panel.run())  # the confirmation was declined
        self.assertIsNone(panel.result)
        self.assertEqual(len(self.asked), 1)
        text = self.asked[0]
        self.assertIn("FE model: none. Registration: none. No mode shape is compared.", text)
        self.assertIn("record 1 (", text)
        self.assertIn("Lowest measured record 1: FIT.", text)
        self.assertIn("record 8 (", text)
        self.assertIn("UNVERIFIED frequency-rank hypothesis", text)
        self.assertIn("frequency-only diagnostic hypothesis", text)

    def test_the_result_shows_d_first_then_conditional_moduli_ambiguity_and_unresolved_identities(self):
        panel = self.entered(self.panel())
        panel.set_ranges(low_thickness=1.9, high_thickness=2.1)
        self.solved(panel)
        self.assertTrue(panel.results_card.isVisible())
        self.assertIn("FREQUENCY-ONLY", panel.presentation.text())
        self.assertIn(spe.LABEL, panel.presentation.text())
        self.assertEqual(panel.presentation.property("state"), "blocked")  # never the success colour
        self.assertEqual(panel.status.property("state"), "blocked")
        self.assertIn("NOT ESTABLISHED", panel.validity.text())
        truth = stiffness(ISOTROPIC, declared())
        cells = panel.table_cells("reg_stiffness")
        self.assertIn("D11", cells[0][0])
        self.assertAlmostEqual(float(cells[0][1]), truth["D11"], places=3)
        self.assertAlmostEqual(float(cells[2][1]), truth["D66"], places=3)
        self.assertTrue(all("FREQUENCY-ONLY" in row[2] for row in cells))
        constants = panel.table_cells("reg_constants")
        self.assertIn("Ex = Ey", constants[0][0])
        self.assertTrue(constants[0][1].startswith("70000 MPa"))
        self.assertTrue(any("over the stated thickness 1.9 to 2.1 mm" in row[0] for row in constants))
        self.assertIn("no material axis 1 is named", panel.constants_note.text())
        self.assertEqual(len(panel.table_cells("plate_minima")), len(panel.result.minima))
        identities = panel.table_cells("plate_identities")
        self.assertEqual(len(identities), 10)
        self.assertTrue(all(row[6] == "UNRESOLVED (frequency rank only)" for row in identities))
        self.assertIn("UNRESOLVED", panel.identity_statement.text())
        self.assertTrue(panel.identity_statement.isVisible())
        self.assertFalse(panel.branch_statement.isVisible())  # the registered route's shape tables are not offered
        statements = dict((row[0], row[1]) for row in panel.table_cells("reg_statements"))
        self.assertEqual(statements["7. Physical validity"], rft.NOT_ESTABLISHED)
        self.assertEqual(statements["2. Parameter identifiability (rank)"], "practical rank 2 of 2")
        self.assertFalse(panel.abaqus_button.isEnabled())  # there is no INP to write a candidate for
        if panel.block["presentation"]["verdict"] == spe.COMPETING:
            self.assertFalse(panel.uncertainty_button.isEnabled())
            self.assertIn("needs ONE estimate", panel.uncertainty_note.text())
        points = dict(panel.summary_points())
        self.assertIn("NONE. Standalone plate", points["2. Registration"])
        self.assertIn("UNRESOLVED", points["3. Mode correspondence and ambiguity"])

    def test_a_changed_thickness_range_updates_the_moduli_without_a_refit(self):
        panel = self.solved(self.entered(self.panel()))
        result = panel.result
        self.assertFalse(any("over the stated thickness" in row[0] for row in panel.table_cells("reg_constants")))
        panel.set_ranges(low_thickness=1.8, high_thickness=2.2)
        self.app.processEvents()
        self.assertIs(panel.result, result)  # the fit itself is untouched
        rows = [row for row in panel.table_cells("reg_constants") if "over the stated thickness 1.8 to 2.2 mm" in row[0]]
        self.assertTrue(rows)
        low = 70000.0 * (2.2 / 2.0) ** -3
        self.assertTrue(rows[0][1].startswith(f"{low:.0f} to "), rows[0][1])
        panel.set_ranges(low_thickness="", high_thickness="")
        self.assertFalse(any("over the stated thickness" in row[0] for row in panel.table_cells("reg_constants")))

    def test_a_changed_input_clears_the_result(self):
        panel = self.solved(self.entered(self.panel()))
        panel.set_plate(mass=200)
        self.assertIsNone(panel.result)
        self.assertFalse(panel.reg_fixed.isChecked() and panel.results_card.isVisible())

    def test_save_open_and_export(self):
        panel = self.solved(self.entered(self.panel()))
        saved, summary = self.folder / "plate_result.json", self.folder / "plate_summary.txt"
        self.assertTrue(panel.export(str(saved)))
        self.assertIn("Exported", panel.export_note.text())
        self.assertTrue(panel.export_summary(str(summary)))
        text = summary.read_text(encoding="utf-8")
        self.assertIn("RESEARCH SUMMARY - standalone plate", text)
        self.assertIn(spe.LABEL, text)
        self.assertIn("Mode identities: every one unresolved", text)
        self.assertIn("Minima reached from the starts", text)
        self.assertNotIn("Fixed branches", text)
        live = (panel.table_cells("reg_stiffness"), panel.table_cells("reg_constants"), panel.table_cells("plate_minima"),
                panel.table_cells("plate_identities"), panel.presentation.text())
        document = json.loads(saved.read_text(encoding="utf-8"))
        self.assertIn(spe.EXPORT_KEY, document)
        self.assertEqual(document["sources"]["inp"], "")
        other = self.panel()
        self.assertTrue(other.open_result(str(saved)), other.message.text())
        self.assertEqual((other.table_cells("reg_stiffness"), other.table_cells("reg_constants"),
                          other.table_cells("plate_minima"), other.table_cells("plate_identities"),
                          other.presentation.text()), live)
        self.assertIn("SAVED RESULT", other.saved_note.text())
        self.assertIn("was not re-read", other.saved_note.text())
        self.assertFalse(other.standalone)  # a saved result is not a live plate: nothing can be refitted from it
        self.assertFalse(other.export_button.isEnabled())
        self.assertFalse(other.stability_button.isEnabled())
        self.assertTrue(other.export_summary(str(self.folder / "again.txt")))
        self.assertIn("Rendered from the saved result plate_result.json", (self.folder / "again.txt").read_text(encoding="utf-8"))

    def test_frf_peak_records_are_refused(self):
        import frf_unv_support as F
        from new_gui import research_tuning_model as rm

        peaks = F.write_frf_only(self.folder / "peaks.unv")
        with self.assertRaises(rm.ReadFailed) as refused:
            rm.read_standalone(peaks, threading.Event())
        self.assertIn("FRF peak records are never used as modes", str(refused.exception))
        panel = self.panel()
        self.assertTrue(panel.choose_plate_file(str(peaks)))
        self.wait(panel)
        self.assertFalse(panel.standalone)
        self.assertIsNone(panel.registered)
        self.assertIn("FRF peak records are never used as modes", panel.standalone_state.text())
        self.assertFalse(panel.registered_form.isVisible())
        self.assertFalse(panel.run_button.isEnabled())

    def test_invalid_entries_are_said_and_never_run(self):
        panel = self.entered(self.panel(), thickness="-2")
        self.assertIn("Thickness must be a positive number", panel.registered_check.text())
        panel.reg_fixed.setChecked(True)
        self.assertFalse(panel.run())
        self.assertIn("Not started", panel.message.text())
        panel.set_plate(thickness=2, source="")
        self.assertIn("State where the dimensions", panel.registered_check.text())
        panel.set_plate(source="sheet", E1="50000")  # one reference constant alone is not a reference
        self.assertIn("Reference E2 is not entered", panel.registered_check.text())
        panel.set_plate(E1="")
        panel.set_ranges(low_thickness=2.1, high_thickness=2.3)
        panel.reg_fixed.setChecked(True)
        self.assertFalse(panel.run())
        self.assertIn("does not hold the entered value", panel.message.text())
        self.assertEqual(self.asked, [])
        self.assertIsNone(panel.result)

    def test_a_file_changed_after_it_was_read_is_refused(self):
        unv = write_modal_file(self.folder / "changing.unv", self.frequencies)
        panel = self.entered(self.panel(), unv=unv)
        write_modal_file(unv, [f * 1.01 for f in self.frequencies])
        panel.reg_fixed.setChecked(True)
        self.assertTrue(panel.run())
        self.wait(panel)
        self.assertIsNone(panel.result)
        self.assertIn("changed on disk", panel.message.text())

    def test_the_routes_do_not_mix(self):
        panel = self.solved(self.entered(self.panel()))
        panel.choose_file("unv", str(self.folder / "other.unv"))  # the INP route's file: the standalone plate is released
        self.assertFalse(panel.standalone)
        self.assertIsNone(panel.registered)
        self.assertIsNone(panel.result)
        self.assertIn("Released", panel.standalone_state.text())
        self.assertFalse(panel.registered_form.isVisible())
        self.entered(panel)  # and back: the INP route's files are released
        self.assertEqual(panel.paths["unv"], "")
        self.assertTrue(panel.standalone)
        panel.analysis_changed()  # a change on Analyze does not concern a standalone plate
        self.assertTrue(panel.standalone)
        self.assertFalse(panel.review_shapes())  # no shape review exists here
        self.assertFalse(panel.take_fe_dimensions())

    def test_the_page_does_not_scroll_sideways_with_the_standalone_form(self):
        """At the usual 1366 x 768. (At 900 px the record grid of section 2, 792 px wide for every route of this page,
        scrolls the page sideways once records are shown; that is not specific to the standalone plate.)"""
        from PySide6.QtWidgets import QScrollArea

        empty = self.panel(size=(900, 680))  # before a file is read the new card fits the narrow window too
        self.assertEqual(self.window.stack.currentWidget().horizontalScrollBar().maximum(), 0)
        self.assertTrue(empty.plate_button.isVisibleTo(self.window))
        panel = self.solved(self.entered(self.panel()))
        self.app.processEvents()
        area = self.window.stack.currentWidget()
        self.assertIsInstance(area, QScrollArea)
        self.assertEqual(area.horizontalScrollBar().maximum(), 0)
        self.assertTrue(panel.plate_button.isVisibleTo(self.window))


if __name__ == "__main__":
    unittest.main()

"""MAT-3: the Materials page's study section, on deterministic SYNTHETIC cases. Qt ``offscreen``, direct widget calls only.

Recovering known values tests the software. It is not experimental material validation.
"""

from __future__ import annotations

import copy
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock
import zipfile

for _name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[_name] = "1"
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
REAL_POPEN = __import__("subprocess").Popen  # _Files forbids any process; one test here starts its own, deliberately
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import test_universal_two_file_analysis as base
import test_working_draft_r2_project as r2

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QObject, QTimer

from domain.plate_inverse_problem import MaterialReleaseRefusal, PlateInverseResult
from domain.plate_material_problem import EvidenceKind, identity_hash
from new_gui import materials_study_model as sm
from new_gui import materials_study_panel as sp
from new_gui import production_window as pw
from new_gui.workspace_state import EXPERIMENTAL
from services import analysis_project as ap
from services import materials_project as mp
from services import plate_material_workflow as workflow

TOLERANCE = 1.0e-3  # relative recovery of a known value, declared before the first run of these tests
CANDIDATE, NOT_A_RELEASE = "DIAGNOSTIC_OPTIMIZER_CANDIDATE", "NOT_A_RELEASE_VALUE"
SECTION = {}


def study(backend=sm.RITZ):
    if backend not in SECTION:  # each default study runs once in this process; the tests only read it
        SECTION[backend] = sm.execute_study(sm.default_form(backend), threading.Event())
    return copy.deepcopy(SECTION[backend])


def stage_form(path="", source=sm.SELECTED):
    form = sm.default_form(sm.STAGE_A)
    form["package"] = {"source": source, "path": str(path)}
    return form


class _Files(unittest.TestCase):
    def setUp(self):
        holder = tempfile.TemporaryDirectory()
        self.addCleanup(holder.cleanup)
        self.root = Path(holder.name)
        patcher = mock.patch("subprocess.Popen", side_effect=AssertionError("no process in these tests"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def written(self, document, name="tampered.mcproj", schema=ap.SCHEMA_V2) -> Path:
        path = self.root / name
        path.write_bytes(ap.project_bytes(document, {}, schema))
        return path

    def refused(self, document, code=ap.INVALID):
        with self.assertRaises(ap.ProjectRefused) as caught:
            mp.read_materials_project(self.written(document))
        self.assertEqual(caught.exception.code, code, str(caught.exception))


class TwoMethods(_Files):
    def test_ritz_runs_with_no_odb_and_recovers_the_known_values(self):
        section = study(sm.RITZ)
        result = section["result"]
        self.assertEqual(result["scientific_status"], CANDIDATE)
        self.assertEqual(result["release_status"], NOT_A_RELEASE)
        self.assertEqual(section["declaration"]["intent"], "SYNTHETIC_SOFTWARE_TEST")
        self.assertEqual(section["references"], [])
        for name, known in {"D11": 12.0, "D22": 7.0, "D66": 2.3, "u": 0.15}.items():
            self.assertNotEqual(section["input"]["parameters"][name]["start"], section["input"]["parameters"][name]["truth"])
            self.assertLess(abs(result["final_parameters"][name] / known - 1.0), 2.0e-3 if name == "u" else TOLERANCE, name)

    def test_stage_a_runs_on_its_synthetic_package_with_d22_equal_d11(self):
        section = study(sm.STAGE_A)
        result = section["result"]
        self.assertEqual(result["scientific_status"], CANDIDATE)
        for name, known in {"D": 0.36, "D66": 0.05, "r": 0.09}.items():
            self.assertLess(abs(result["final_parameters"][name] / known - 1.0), TOLERANCE, name)
        self.assertEqual(result["final_stiffness"]["D11"], result["final_stiffness"]["D22"])
        self.assertEqual(section["provenance"]["constraint"], "D22 = D11")

    def test_each_method_calls_the_shared_workflow_once(self):
        for backend in (sm.RITZ, sm.STAGE_A):
            with self.subTest(backend=backend), mock.patch.object(sm, "run_plate_inverse_study",
                                                                  wraps=workflow.run_plate_inverse_study) as called:
                section = sm.execute_study(sm.default_form(backend), threading.Event())
                self.assertEqual(called.call_count, 1)
                self.assertEqual(called.call_args.args[0].backend_id.value, backend)
                self.assertGreater(section["result"]["solves"], 10)

    def test_the_same_form_gives_the_same_declaration_and_result(self):
        first, second = study(sm.STAGE_A), sm.execute_study(sm.default_form(sm.STAGE_A), threading.Event())
        self.assertEqual(first["declaration_hash"], second["declaration_hash"])
        self.assertEqual(first["result_hash"], second["result_hash"])

    def test_the_tables_hold_the_computed_values(self):
        with tempfile.TemporaryDirectory() as scratch:
            request = sm.build_request(sm.default_form(sm.RITZ), Path(scratch))
            direct = workflow.run_plate_inverse_study(request.declaration)
        section = study(sm.RITZ)
        self.assertEqual(direct.result_hash, section["result_hash"])
        rows = {row[0]: row for row in sm.parameter_rows(section)}
        for name, value in direct.final_parameters.items():
            self.assertEqual(rows[name][2], f"{value:.6g}")
        self.assertEqual(rows["D12 (derived)"][2], f"{direct.final_stiffness['D12']:.6g}")
        self.assertEqual(rows["D11"][3], "12")
        table = sm.frequency_rows(section)
        self.assertEqual(len(table), len(direct.frequencies))
        for row, found in zip(table, direct.frequencies):
            self.assertEqual(row[0], found.row_id)
            self.assertEqual(row[2], found.role.value)
            self.assertEqual(row[3], f"{found.experimental_hz:.6g}")
            self.assertEqual(row[4], f"{found.initial_model_hz:.6g}")
            self.assertEqual(row[5], f"{found.final_model_hz:.6g}")
            self.assertEqual(row[7], f"{100.0 * (found.final_model_hz / found.experimental_hz - 1.0):+.4f} %")
        self.assertEqual({row[2] for row in table}, {"FIT", "HOLDOUT"})
        self.assertEqual(len(sm.iteration_rows(section)), len(direct.iterations))
        self.assertEqual(dict(sm.identifiability_rows(section))["Rank"], "4 of 4")
        self.assertEqual(len(sm.holdout_rows(section)), 2)
        self.assertEqual(len(sm.family_rows(section)), 8)
        self.assertEqual(dict(sm.convergence_rows(section))["Forward solves"], str(direct.solves))
        self.assertTrue(any("Sigma_meas NOT_AVAILABLE" in row[1] for row in sm.uncertainty_rows(section)))
        self.assertTrue(sm.objective_plot(section).startswith(b"\x89PNG"))
        self.assertTrue(sm.error_plot(section).startswith(b"\x89PNG"))

    def test_units_and_surface_mass_reach_the_model(self):
        in_metres = sm.default_form(sm.RITZ)
        in_metres["geometry"].update(a="0.3", b="0.2", length_unit="m", mass="0.12", mass_unit="kg", thickness="0.002")
        left, right = sm.geometry_of(sm.default_form(sm.RITZ)), sm.geometry_of(in_metres)
        self.assertAlmostEqual(left.a_m, right.a_m)
        self.assertAlmostEqual(left.surface_mass_kg_m2, 2.0)
        self.assertAlmostEqual(right.surface_mass_kg_m2, 2.0)
        surface = sm.default_form(sm.RITZ)
        surface["geometry"].update(mass_basis="surface", mass="2.0", thickness="")
        geometry = sm.geometry_of(surface)
        self.assertEqual(geometry.surface_mass_kg_m2, 2.0)
        self.assertIsNone(geometry.thickness_m)
        self.assertIn("E and G stay missing", sm.geometry_text(surface))
        self.assertIn("does not prove", sm.geometry_text(sm.default_form(sm.RITZ)))

    def test_a_form_that_is_not_numbers_is_refused_by_field(self):
        form = sm.default_form(sm.RITZ)
        form["geometry"]["a"] = "wide"
        form["parameters"]["D11"]["start"] = "?"
        form["numerics"]["holdout_modes"] = "99"
        _rows, problems = sm.preflight(form)
        for word in ("a:", "D11 start", "HOLDOUT"):
            self.assertTrue(any(word in text for text in problems), word)

    def test_the_resource_limits_are_checked_before_a_start(self):
        form = sm.default_form(sm.RITZ)
        self.assertEqual(sm.preflight(form)[1], ())
        form["numerics"]["degree"] = "40"
        self.assertTrue(sm.preflight(form)[1])
        form = sm.default_form(sm.RITZ)
        form["budget"]["max_solves"] = str(sm.MAX_SOLVES_CAP + 1)
        self.assertTrue(sm.preflight(form)[1])
        form = sm.default_form(sm.RITZ)
        form["budget"]["max_seconds"] = "0"
        self.assertTrue(sm.preflight(form)[1])

    def test_a_small_budget_gives_the_real_stop_and_no_candidate(self):
        form = sm.default_form(sm.RITZ)
        form["budget"]["max_solves"] = "12"
        result = sm.execute_study(form, threading.Event())["result"]
        self.assertEqual(result["execution_status"], "BUDGET_EXHAUSTED")
        self.assertNotEqual(result["scientific_status"], CANDIDATE)

    def test_a_square_plate_at_the_symmetric_point_gets_the_workflows_refusal(self):
        form = sm.default_form(sm.RITZ)
        form["geometry"].update(a="300", b="300")
        form["parameters"]["D11"]["start"] = form["parameters"]["D22"]["start"] = "6.5"
        result = sm.execute_study(form, threading.Event())["result"]
        self.assertEqual(result["refusal_code"], "UNRESOLVED_MODAL_CLUSTER")
        self.assertIsNone(result["final_parameters"])


class WrongPackages(_Files):
    def assert_refused(self, form):
        section = sm.execute_study(form, threading.Event())
        result = section["result"]
        self.assertEqual(result["backend_id"], sm.STAGE_A)  # no fallback to the other method
        self.assertEqual(result["refusal_code"], "PACKAGE_REFUSED", result["refusal_reason"])
        self.assertEqual(result["scientific_status"], "NO_RESULT")
        self.assertIsNone(result["final_parameters"])
        self.assertEqual(result["solves"], 0)
        return section

    def test_no_package(self):
        section = self.assert_refused(stage_form(""))
        self.assertEqual(section["result"]["forward_refusal_code"], "PACKAGE_MISSING")

    def test_a_missing_folder(self):
        self.assert_refused(stage_form(self.root / "nothing here"))

    def test_another_model(self):
        path = sm.write_stage_a_package(sm._stage_basis(), self.root / "other", specimen_id=sm.SPECIMEN, model_id="ANOTHER-MODEL",
                                        evidence_kind=EvidenceKind.SYNTHETIC, units="N-m-kg-s", validity_domain=sm._STAGE_DOMAIN,
                                        expected_rigid_body_modes=3, description="SYNTHETIC")
        self.assertEqual(self.assert_refused(stage_form(path))["result"]["forward_refusal_code"], "PACKAGE_WRONG_MODEL")

    def test_a_damaged_package(self):
        path = sm.write_synthetic_package(self.root / "good")
        next(path.glob("*.npz")).write_bytes(b"damaged")
        self.assertEqual(self.assert_refused(stage_form(path))["result"]["forward_refusal_code"], "PACKAGE_CORRUPT")

    def test_a_package_stating_physical_evidence_is_refused_and_named_view_only(self):
        path = sm.write_stage_a_package(sm._stage_basis(), self.root / "phys", specimen_id=sm.SPECIMEN, model_id=sm.STAGE_MODEL,
                                        evidence_kind=EvidenceKind.PHYSICAL, units="N-m-kg-s", validity_domain=sm._STAGE_DOMAIN,
                                        expected_rigid_body_modes=3, description="stated as physical")
        result = sm.execute_study(stage_form(path), threading.Event())["result"]
        self.assertEqual(result["refusal_code"], "EVIDENCE_KIND_MISMATCH")
        self.assertIsNone(result["final_parameters"])
        self.assertIn("BLOCKED", dict(sm.package_facts(path))["Readiness"])

    def test_a_good_package_shows_its_identity_and_ranges_without_loading_matrices(self):
        path = sm.write_synthetic_package(self.root / "good")
        with mock.patch("numpy.load", side_effect=AssertionError("no matrix is loaded to show the facts")):
            facts = dict(sm.package_facts(path))
        self.assertEqual(facts["Model"], sm.STAGE_MODEL)
        self.assertEqual(facts["Evidence kind"], "SYNTHETIC")
        self.assertEqual(facts["Constraint"], "D22=D11")
        self.assertEqual(facts["Domain D66"], "0.02 to 0.08")
        self.assertEqual(sm.execute_study(stage_form(path), threading.Event())["result"]["scientific_status"], CANDIDATE)


class RealDataStaysBlocked(_Files):
    TEXTS = ("", "AUTHORIZED", "execution_authorization=true", "Owner approved real data run", "SYNTHETIC")

    def test_any_authorization_text_gets_the_workflows_refusal_and_opens_no_model(self):
        with mock.patch.object(workflow, "RitzInverseModel", side_effect=AssertionError("no model is opened")):
            for text in self.TEXTS:
                with self.subTest(text=text):
                    code, reason = sm.real_data_gate(text)
                    self.assertEqual(code, "NOT_AUTHORIZED")
                    self.assertIn("SYNTHETIC", reason)

    def test_nothing_that_builds_a_study_takes_measured_data(self):
        for function in (sm.build_request, sm.execute_study, sm.prepare_rows):
            names = set(inspect.signature(function).parameters)
            self.assertLessEqual(names, {"form", "scratch", "cancel_event", "on_solve"}, function.__name__)
        self.assertEqual(sm.default_form()["package"]["path"], "")

    def test_a_form_never_names_an_experimental_file(self):
        form = sm.default_form(sm.RITZ)
        for key in ("geometry", "parameters", "numerics", "budget", "package"):
            self.assertNotIn("unv", json.dumps(form[key]).lower())


class ReleaseStaysRefused(_Files):
    def test_the_release_is_refused_for_a_candidate_and_no_other_status_exists(self):
        section = study(sm.RITZ)
        self.assertEqual(section["result"]["scientific_status"], CANDIDATE)
        result = mock.Mock(spec=PlateInverseResult)
        result.scientific_status, result.release_status = mock.Mock(value=CANDIDATE), mock.Mock(value=NOT_A_RELEASE)
        with self.assertRaises(MaterialReleaseRefusal):
            workflow.release_material_property(result)
        self.assertEqual(section["result"]["restrictions_unchanged"],
                         ["M8 GATE NOT_MET", "D-077 NO_GLOBAL_PARAMETER_VALUE", "production Auto-ID BLOCKED"])
        self.assertIn("not a material property", sm.STATEMENT)

    def test_the_interpretation_limits_are_on_every_parameter_row(self):
        for row in sm.parameter_rows(study(sm.RITZ)):
            self.assertTrue(row[6])
        self.assertIn("not ply properties", dict(sm.conditional_rows(study(sm.RITZ)))["Meaning"])


class ProjectFormat(_Files):
    def good(self, backend=sm.RITZ) -> dict:
        return mp.materials_document(study(backend), "test program")

    def test_a_study_comes_back_exactly(self):
        for backend in (sm.RITZ, sm.STAGE_A):
            with self.subTest(backend=backend):
                document = self.good(backend)
                path = mp.write_materials_project(document, self.root / f"{backend}.mcproj")
                self.assertEqual(ap.project_schema(path), ap.SCHEMA_V2)
                again = mp.read_materials_project(path)
                self.assertEqual(again["materials"], json.loads(json.dumps(document["materials"])))
                for table in (sm.parameter_rows, sm.frequency_rows, sm.iteration_rows, sm.identifiability_rows, sm.holdout_rows,
                              sm.family_rows, sm.convergence_rows, sm.uncertainty_rows, sm.status_rows):
                    self.assertEqual(table(again["materials"]), table(document["materials"]))
                self.assertEqual(mp.result_hash_of(again["materials"]["result"]), document["materials"]["result_hash"])

    def test_it_stores_the_identity_units_refusal_and_provenance(self):
        refused = sm.execute_study(stage_form(""), threading.Event())
        section = mp.read_materials_project(mp.write_materials_project(mp.materials_document(refused, "x"), self.root / "r.mcproj"))["materials"]
        self.assertEqual(section["backend_id"], sm.STAGE_A)
        self.assertEqual(section["result"]["refusal_code"], "PACKAGE_REFUSED")
        self.assertEqual(section["units"]["D"], "N*m")
        self.assertIn("source", section["provenance"])
        self.assertEqual(sm.status_rows(section)[7], ("Refusal", "PACKAGE_REFUSED"))

    def test_non_finite_numbers_keep_their_value_in_strict_json(self):
        self.assertEqual(mp.to_json(float("inf")), {"non_finite": "inf"})
        self.assertEqual(mp.from_json({"non_finite": "-inf"}), float("-inf"))
        document = self.good()
        document["materials"]["result"]["identifiability"]["condition_number"] = {"non_finite": "inf"}
        self.refused(document)  # the hash no longer fits: an edited value is seen

    def test_a_file_cannot_raise_its_status(self):
        def changed(edit):
            document = self.good()
            edit(document["materials"])
            return document

        def release(section):
            section["result"]["release_status"] = "RELEASED"

        def evidence(section):
            section["result"]["evidence_kind"] = "PHYSICAL"

        def intent(section):
            section["declaration"]["intent"] = "MATERIAL_IDENTIFICATION_RESEARCH"

        def kind(section):
            section["study_kind"] = "MATERIAL_IDENTIFICATION_RESEARCH"

        def restrictions(section):
            section["result"]["restrictions_unchanged"] = []

        def study_name(section):
            section["declaration"]["study_id"] = "SP13-REAL"

        def scientific(section):
            section["result"]["scientific_status"] = "ACCEPTED_MATERIAL_PROPERTY"

        def unknown(section):
            section["accepted_value"] = 1.0

        def extra_result(section):
            section["result"]["release_value"] = 1.0

        for edit in (release, evidence, intent, kind, restrictions, study_name, scientific, unknown, extra_result):
            with self.subTest(edit=edit.__name__):
                self.refused(changed(edit))

    def test_a_refusal_rewritten_with_consistent_hashes_cannot_become_a_candidate(self):
        document = mp.materials_document(sm.execute_study(stage_form(""), threading.Event()), "x")
        section = document["materials"]
        section["result"]["scientific_status"] = CANDIDATE
        section["result_hash"] = mp.result_hash_of(section["result"])
        self.refused(document)
        section["result"]["refusal_code"] = None
        section["result"]["numerical_status"] = "CONVERGED"
        section["result"]["execution_status"] = "COMPLETED"
        section["result"]["final_parameters"] = {"D": 0.36, "D66": 0.05, "r": 0.09}
        section["result_hash"] = mp.result_hash_of(section["result"])
        self.refused(document)  # no rank, pattern or family evidence stands behind it

    def test_damage_and_other_contents_are_refused(self):
        path = mp.write_materials_project(self.good(), self.root / "good.mcproj")
        with zipfile.ZipFile(path) as archive:
            members = {name: archive.read(name) for name in archive.namelist()}
        members[ap.PROJECT] = members[ap.PROJECT].replace(b"CONVERGED", b"CONVERGEX", 1)
        bad = self.root / "bad.mcproj"
        with zipfile.ZipFile(bad, "w") as archive:
            for key, value in members.items():
                archive.writestr(key, value)
        with self.assertRaises(ap.ProjectRefused) as caught:
            mp.read_materials_project(bad)
        self.assertEqual(caught.exception.code, ap.DAMAGED)
        junk = self.root / "junk.mcproj"
        junk.write_bytes(b"not a zip")
        with self.assertRaises(ap.ProjectRefused) as caught:
            mp.read_materials_project(junk)
        self.assertEqual(caught.exception.code, ap.NOT_A_PROJECT)
        self.assertIsNone(ap.project_schema(junk))
        with self.assertRaises(ap.ProjectRefused):
            mp.write_materials_project(self.good(), self.root / "wrong.txt")

    def test_each_version_refuses_the_other_by_name(self):
        path = mp.write_materials_project(self.good(), self.root / "v2.mcproj")
        with self.assertRaises(ap.ProjectRefused) as caught:
            ap.read_project(path)
        self.assertEqual(caught.exception.code, ap.OTHER_VERSION)
        self.assertEqual(ap.SCHEMA, "universal/analysis-project/v1")
        v1 = self.good()
        v1["schema"] = ap.SCHEMA
        with self.assertRaises(ap.ProjectRefused) as caught:
            mp.read_materials_project(self.written(v1, "v1.mcproj", ap.SCHEMA))
        self.assertEqual(caught.exception.code, ap.OTHER_VERSION)

    def test_a_failed_write_leaves_the_old_file_and_no_temporary(self):
        target = mp.write_materials_project(self.good(), self.root / "kept.mcproj")
        before = target.read_bytes()
        broken = self.good()
        broken["materials"]["result"]["release_status"] = "RELEASED"
        with self.assertRaises(ap.ProjectRefused):
            mp.write_materials_project(broken, target)
        cancelled = threading.Event()
        cancelled.set()
        with self.assertRaises(ap.ProjectRefused):
            mp.write_materials_project(self.good(), target, cancelled)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual([item.name for item in self.root.iterdir()], ["kept.mcproj"])

    def test_it_never_overwrites_a_path_it_names(self):
        source = self.root / "source.mcproj"
        source.write_bytes(b"a file the page named")
        document = self.good()
        document["materials"]["references"] = [{"role": "Matrix package", "path": str(source), "state": mp.NOT_OPENED}]
        with self.assertRaises(ap.ProjectRefused):
            mp.write_materials_project(document, source)
        self.assertEqual(source.read_bytes(), b"a file the page named")

    def test_a_saved_reference_must_stay_plain_unopened_text(self):
        document = self.good()
        document["materials"]["references"] = [{"role": "UNV", "path": "x.unv", "state": "VERIFIED"}]
        self.refused(document)

    def test_the_hash_is_of_the_saved_form(self):
        section = study(sm.RITZ)
        self.assertEqual(identity_hash(mp.from_json(section["declaration"])), section["declaration_hash"])


class _Page(r2._Project):
    def page(self):
        window = self.window()
        window.resize(900, 680)
        window.show_page(pw.MATERIALS_PAGE)
        self.app.processEvents()
        return window, window.materials_workspace.study

    def run_it(self, study_panel):
        study_panel.run_button.click()
        self.wait(study_panel)


class Page(_Page):
    def test_the_sections_and_their_defaults(self):
        window, panel = self.page()
        self.assertEqual(panel.backend, sm.RITZ)
        self.assertTrue(panel.run_button.isEnabled())
        self.assertFalse(panel.cancel_button.isEnabled())
        self.assertFalse(panel.save_button.isEnabled())
        self.assertEqual(panel.badge.text(), sp.NOT_RUN)
        self.assertIn("No ODB, Abaqus or matrix file is needed", panel.method_text.text())
        self.assertIn("suspension", panel.scope_text.text())
        self.assertEqual(window.materials.table.item(0, 1).text(), "Not identified")  # the material status stays apart

    def test_ritz_from_the_button_to_the_tables(self):
        window, panel = self.page()
        with mock.patch.object(sm, "run_plate_inverse_study", wraps=workflow.run_plate_inverse_study) as called:
            self.run_it(panel)
        self.assertEqual(called.call_count, 1)
        self.assertEqual(panel.message.text(), "")
        section = panel.record["materials"]
        self.assertEqual(panel.badge.text(), f"{CANDIDATE} | {NOT_A_RELEASE}")
        self.assertEqual(panel.badge.property("state"), "chosen")  # never the green of a verified result
        self.assertEqual(panel.table_cells("parameters"), [list(row) for row in sm.parameter_rows(section)])
        self.assertEqual(panel.table_cells("frequencies"), [list(row) for row in sm.frequency_rows(section)])
        statuses = dict(panel.table_cells("status"))
        self.assertEqual(statuses["Scientific status"], CANDIDATE)
        self.assertEqual(statuses["Release status"], NOT_A_RELEASE)
        self.assertEqual(statuses["Numerical status"], "CONVERGED")
        self.assertEqual(statuses["Study"], "SYNTHETIC_SOFTWARE_TEST")
        self.assertEqual(len(panel.table_cells("observations")), 10)
        self.assertTrue(panel.save_button.isEnabled())
        self.assertFalse(panel.objective_view.isHidden())
        self.assertFalse(panel.error_view.isHidden())
        self.assertEqual(window.materials.table.item(0, 1).text(), "Not identified")
        self.app.processEvents()
        self.assertEqual(window.stack.currentWidget().horizontalScrollBar().maximum(), 0)

    def test_stage_a_from_the_method_choice(self):
        _window, panel = self.page()
        panel.method_combo.setCurrentIndex(panel.method_combo.findData(sm.STAGE_A))
        self.assertIn("Available", panel.availability.text())
        self.assertFalse(panel.package_row.isHidden())
        self.assertFalse(panel.a_field.isEnabled())
        self.assertEqual(set(panel.form()["parameters"]), {"D", "D66", "r"})
        self.run_it(panel)
        section = panel.record["materials"]
        self.assertEqual(section["backend_id"], sm.STAGE_A)
        self.assertEqual(section["result"]["scientific_status"], CANDIDATE)
        self.assertEqual(panel.table_cells("parameters")[0][0], "D")

    def test_no_package_and_a_wrong_package_show_the_refusal(self):
        _window, panel = self.page()
        panel.method_combo.setCurrentIndex(panel.method_combo.findData(sm.STAGE_A))
        panel.package_source.setCurrentIndex(panel.package_source.findData(sm.SELECTED))
        self.assertIn("Not available", panel.availability.text())
        self.run_it(panel)
        self.assertIn("PACKAGE_REFUSED", panel.reasons.text())
        self.assertEqual(panel.badge.property("state"), "blocked")
        self.assertEqual(panel.table_cells("parameters")[0][2], sm.DASH)
        self.assertTrue(panel.choose_package(str(self.root / "no such package")))
        self.wait(panel)
        self.assertIn("cannot be used", panel.package_note.text())
        self.run_it(panel)
        self.assertIn("PACKAGE_REFUSED", panel.reasons.text())
        self.assertEqual(panel.record["materials"]["result"]["backend_id"], sm.STAGE_A)

    def test_a_chosen_package_shows_its_facts(self):
        _window, panel = self.page()
        panel.method_combo.setCurrentIndex(panel.method_combo.findData(sm.STAGE_A))
        path = sm.write_synthetic_package(self.root / "chosen")
        self.assertTrue(panel.choose_package(str(path)))
        self.wait(panel)
        self.assertEqual(dict(panel.table_cells("package"))["Model"], sm.STAGE_MODEL)
        self.run_it(panel)
        self.assertEqual(panel.record["materials"]["result"]["scientific_status"], CANDIDATE)
        self.assertEqual(panel.record["materials"]["references"][0]["path"], str(path))

    def test_a_bad_form_blocks_run_and_says_why(self):
        _window, panel = self.page()
        panel.a_field.setText("wide")
        self.assertFalse(panel.run_button.isEnabled())
        self.assertIn("a:", panel.message.text())
        self.assertFalse(panel.run())
        panel.a_field.setText("300")
        self.assertTrue(panel.run_button.isEnabled())
        self.assertEqual(panel.message.text(), "")

    def test_prepare_shows_the_observations_without_a_fit(self):
        _window, panel = self.page()
        with mock.patch.object(sm, "run_plate_inverse_study", side_effect=AssertionError("prepare does not fit")):
            self.assertTrue(panel.prepare())
            self.wait(panel)
        rows = panel.table_cells("observations")
        self.assertEqual(len(rows), 10)
        self.assertEqual([row[4] for row in rows].count("HOLDOUT"), 2)
        self.assertIn("SYNTHETIC-REGISTRATION", panel.observation_note.text())
        self.assertIsNone(panel.record)


class _Gate:
    """Holds the worker before its first solve until the test lets it go, so each step below is certain."""

    def __init__(self):
        self.reached, self.go = threading.Event(), threading.Event()
        self.real = workflow.run_plate_inverse_study

    def __call__(self, declaration, **options):
        cancel = options["cancel"]

        def held():
            self.reached.set()
            self.go.wait(20.0)
            return cancel()

        return self.real(declaration, **dict(options, cancel=held))


class RunControl(_Page):
    def holding(self, panel):
        gate = _Gate()
        patcher = mock.patch.object(sm, "run_plate_inverse_study", gate)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(gate.go.set)
        panel.run_button.click()
        self.assertTrue(gate.reached.wait(20.0))
        self.app.processEvents()
        return gate, patcher

    def test_cancel_shows_no_result_and_a_second_run_works(self):
        _window, panel = self.page()
        gate, patcher = self.holding(panel)
        self.assertFalse(panel.run_button.isEnabled())
        self.assertTrue(panel.cancel_button.isEnabled())
        panel.cancel_button.click()
        gate.go.set()
        self.wait(panel)
        self.assertEqual(sp.CANCELLED_TEXT, panel.run_state.text())
        self.assertEqual(panel.badge.text(), "CANCELLED")
        self.assertIsNone(panel.record)
        self.assertFalse(panel.save_button.isEnabled())
        self.assertNotIn("parameters", panel._tables)
        patcher.stop()
        self.addCleanup(patcher.start)
        self.run_it(panel)
        self.assertEqual(panel.record["materials"]["result"]["scientific_status"], CANDIDATE)

    def test_a_cancelled_run_leaves_a_saved_result_untouched(self):
        _window, panel = self.page()
        self.run_it(panel)
        path = self.root / "kept.mcproj"
        self.assertTrue(panel.save_results(str(path)))
        self.wait(panel)
        before = path.read_bytes()
        gate, _patcher = self.holding(panel)
        panel.cancel()
        gate.go.set()
        self.wait(panel)
        self.assertEqual(path.read_bytes(), before)

    def test_only_one_run_at_a_time(self):
        _window, panel = self.page()
        gate, _patcher = self.holding(panel)
        self.assertTrue(panel.busy())
        for attempt in (panel.run, panel.prepare, panel.open_results):
            self.assertFalse(attempt() if attempt != panel.open_results else attempt(str(self.root / "x.mcproj")))
        self.assertEqual(sum(thread.name.startswith("new-gui-materials-study") for thread in threading.enumerate()), 1)
        panel.cancel()
        gate.go.set()
        self.wait(panel)

    def test_an_outcome_of_an_abandoned_run_is_not_shown(self):
        _window, panel = self.page()
        gate, _patcher = self.holding(panel)
        token = panel._token
        with mock.patch.object(panel, "_show_section", side_effect=AssertionError("not current")):
            panel.shutdown(0.0)
            gate.go.set()
            panel._thread.join(20.0)
            self.app.processEvents()
        self.assertGreater(panel._token, token)
        self.assertIsNone(panel.record)

    def test_the_window_closes_during_a_run_and_the_worker_ends(self):
        window, panel = self.page()
        gate, _patcher = self.holding(panel)
        thread = panel._thread
        threading.Timer(0.05, gate.go.set).start()
        window.close()
        thread.join(20.0)
        self.assertFalse(thread.is_alive())
        self.assertIsNone(panel.record)

    @staticmethod
    def delete_what_earlier_tests_left():
        """ABM-AUD-5-F1. The tests of this suite schedule their windows with deleteLater() and run processEvents(), which
        does not delete them; a QEventLoop.exec() does, all at once. Without this the first nested loop of the process
        would spend its time deleting the windows of every earlier test. It is called before this test builds its own
        page and before any worker runs, so it takes nothing away from what is measured."""
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    def timer_beats(self):
        """The times of the 5 ms timer beats seen by a nested event loop: it ends after the sixth beat or after 10 s."""
        beats = []
        loop = QEventLoop()
        ticking, limit = QTimer(), QTimer()
        self.addCleanup(ticking.stop)
        self.addCleanup(limit.stop)

        def beat():
            beats.append(time.monotonic())
            if len(beats) > 5:
                loop.quit()

        ticking.setInterval(5)
        ticking.timeout.connect(beat)
        limit.setSingleShot(True)
        limit.timeout.connect(loop.quit)
        limit.start(10000)  # bounded, and shorter than the gate's own limit
        ticking.start()
        loop.exec()
        ticking.stop()
        limit.stop()
        return beats

    @staticmethod
    def largest_gap(beats) -> float:
        return max(right - left for left, right in zip(beats, beats[1:]))

    def slow_backlog(self, seconds: float):
        """A controlled backlog: one object scheduled for deletion whose deletion takes ``seconds`` of the GUI thread.
        Returns the list that receives the time of its deletion."""
        deleted = []
        leftover = QObject()

        def slow(*_args):
            time.sleep(seconds)
            deleted.append(time.monotonic())

        leftover.destroyed.connect(slow)
        leftover.deleteLater()
        self.app.processEvents()  # as the fixtures do: this does not run a deferred deletion
        self.assertEqual(deleted, [])
        return deleted

    def test_a_backlog_of_deletions_would_hold_the_nested_loop(self):
        """The interference itself, on a controlled backlog: left alone, the deletion runs inside the loop that measures."""
        self.delete_what_earlier_tests_left()  # only the controlled backlog below is left for the loop
        deleted = self.slow_backlog(2.5)
        started = time.monotonic()
        beats = self.timer_beats()
        self.assertEqual(len(deleted), 1)
        self.assertGreater(len(beats), 5)
        self.assertGreater(deleted[0], started)  # it was deleted by the measuring loop
        self.assertGreater(beats[0] - started, 2.0)  # which the deletion held before its first beat

    def test_the_backlog_is_deleted_before_the_measurement_begins(self):
        deleted = self.slow_backlog(2.5)
        self.delete_what_earlier_tests_left()
        self.assertEqual(len(deleted), 1)  # gone before anything is measured
        started = time.monotonic()
        beats = self.timer_beats()
        self.assertGreater(len(beats), 5)
        self.assertLess(beats[0] - started, 2.0)
        self.assertLess(self.largest_gap(beats), 2.0)

    def test_a_blocked_interface_is_still_detected(self):
        """The measurement keeps its teeth: a GUI thread that is blocked while the beats run shows a gap over the limit,
        with or without the cleanup before it."""
        self.delete_what_earlier_tests_left()
        QTimer.singleShot(20, lambda: time.sleep(2.5))  # the interface blocked for 2.5 s in the middle of the beats
        beats = self.timer_beats()
        self.assertGreater(len(beats), 5)
        self.assertGreaterEqual(self.largest_gap(beats), 2.0)  # the original test's limit would be broken

    def test_the_interface_keeps_running_and_results_reach_widgets_on_its_thread(self):
        self.delete_what_earlier_tests_left()  # ABM-AUD-5-F1: before the page exists and before the worker starts
        _window, panel = self.page()
        seen = []
        original = panel._show_section

        def show(*args):
            seen.append(threading.current_thread() is threading.main_thread())
            original(*args)

        with mock.patch.object(panel, "_show_section", show):
            gate, _patcher = self.holding(panel)  # the worker stays unfinished until the test lets it go
            beats = self.timer_beats()
            self.assertGreater(len(beats), 5)  # all of these came while the work was certainly not finished
            self.assertLess(max(right - left for left, right in zip(beats, beats[1:])), 2.0)
            self.assertFalse(gate.go.is_set())
            self.assertTrue(panel._thread.is_alive())
            self.assertEqual(panel._active, sp.RUNNING)
            self.assertEqual(seen, [])
            self.assertIsNone(panel.record)
            gate.go.set()
            self.wait(panel)
        self.assertEqual(seen, [True])
        self.assertGreater(panel.solves_done, 10)


class RealSource(_Page):
    def real(self, panel):
        panel.source_combo.setCurrentIndex(panel.source_combo.findData(sm.REAL_SOURCE))

    def test_run_stays_blocked_whatever_the_note_says(self):
        _window, panel = self.page()
        self.real(panel)
        self.assertFalse(panel.blocked.isHidden())
        with mock.patch.object(sm, "execute_study", side_effect=AssertionError("no run")), \
                mock.patch.object(sm, "build_request", side_effect=AssertionError("no study is built")):
            for text in RealDataStaysBlocked.TEXTS:
                with self.subTest(text=text):
                    panel.note_field.setText(text)
                    self.assertFalse(panel.run_button.isEnabled())
                    self.assertFalse(panel.prepare_button.isEnabled())
                    self.assertFalse(panel.run())
                    self.assertFalse(panel.prepare())
                    self.assertFalse(panel.busy())
                    self.assertIn("BLOCKED", panel.message.text())
                    self.assertIn("NOT_AUTHORIZED", panel.message.text())
                    self.assertEqual(dict(panel.table_cells("real"))["Real-data inverse execution"], "BLOCKED")
        self.assertIsNone(panel.record)

    def test_the_file_facts_are_shown_and_used_for_nothing(self):
        window, panel = self.page()
        self.real(panel)
        self.assertEqual(dict(panel.table_cells("real"))["Data read"], "No file read")
        workspace = window.materials_workspace
        self.assertTrue(workspace.choose_file(EXPERIMENTAL, str(self.unv(base.plate_nodes()))))
        self.assertTrue(window.wait_for_reads())
        rows = dict(panel.table_cells("real"))
        self.assertEqual(rows["Data read"], "Yes")
        self.assertIn("Present", rows["Mode shapes"])
        self.assertIn("Absent", rows["Registration"])
        self.assertEqual(rows["Source"], "Real experiment, chosen by the user")
        self.assertIn(rows["Data type"], ("Fitted modes", "FRF peaks: not fitted modes", "UNKNOWN"))
        self.assertFalse(panel.run())

    def test_a_real_file_on_the_page_does_not_enter_a_synthetic_test(self):
        window, panel = self.page()
        self.run_it(panel)
        clean = panel.record["materials"]
        workspace = window.materials_workspace
        self.assertTrue(workspace.choose_file(EXPERIMENTAL, str(self.unv(base.plate_nodes()))))
        self.assertTrue(window.wait_for_reads())
        self.run_it(panel)
        section = panel.record["materials"]
        self.assertEqual(section["declaration_hash"], clean["declaration_hash"])
        self.assertEqual(section["result_hash"], clean["result_hash"])
        self.assertEqual(section["references"], [])
        self.assertNotIn("unv", json.dumps(section).lower())


class SaveAndOpen(_Page):
    TABLES = ("status", "parameters", "frequencies", "iterations", "identifiability", "holdout", "families", "convergence",
              "uncertainty", "conditional", "observations")

    def shown(self, panel):
        return {key: panel.table_cells(key) for key in self.TABLES}

    def saved_study(self, backend=sm.RITZ):
        _window, panel = self.page()
        if backend != sm.RITZ:
            panel.method_combo.setCurrentIndex(panel.method_combo.findData(backend))
        self.run_it(panel)
        path = self.root / "study.mcproj"
        self.assertTrue(panel.save_results(str(path)))
        self.wait(panel)
        self.assertTrue(path.is_file(), panel.message.text())
        return panel, path

    def test_open_shows_the_same_tables_and_computes_nothing(self):
        for backend in (sm.RITZ, sm.STAGE_A):
            with self.subTest(backend=backend):
                first, path = self.saved_study(backend)
                before, form = self.shown(first), first.form()
                _window, panel = self.page()
                with mock.patch.object(sm, "run_plate_inverse_study", side_effect=AssertionError("no calculation")), \
                        mock.patch.object(sm, "execute_study", side_effect=AssertionError("no calculation")), \
                        mock.patch.object(sm, "build_request", side_effect=AssertionError("no calculation")):
                    self.assertTrue(panel.open_results(str(path)))
                    self.wait(panel)
                self.assertEqual(panel.message.text(), "")
                self.assertEqual(self.shown(panel), before)
                self.assertEqual(panel.form(), form)
                self.assertIn("SAVED RESULT", panel.origin_note.text())
                self.assertEqual(panel.badge.property("state"), "chosen")
                self.assertTrue(panel.changed_note.isHidden())
                path.unlink()

    def test_open_opens_no_path_named_in_the_project(self):
        document = mp.materials_document(sm.execute_study(stage_form(self.root / "nowhere"), threading.Event()), "x")
        path = mp.write_materials_project(document, self.root / "named.mcproj")
        _window, panel = self.page()
        with mock.patch.object(sm, "inspect_stage_a_package", side_effect=AssertionError("no package is opened")), \
                mock.patch.object(sm.StageAMatrixForwardBackend, "open", side_effect=AssertionError("no package is opened")):
            self.assertTrue(panel.open_results(str(path)))
            self.wait(panel)
        self.assertEqual(panel.package_field.text(), str(self.root / "nowhere"))
        self.assertIn("PACKAGE_REFUSED", panel.reasons.text())

    def test_saving_again_keeps_the_time_of_the_results(self):
        first, path = self.saved_study()
        saved_at = mp.read_materials_project(path)["saved_at"]
        _window, panel = self.page()
        panel.open_results(str(path))
        self.wait(panel)
        with mock.patch.object(mp, "_now", return_value="2099-01-01T00:00:00+00:00"):
            self.assertTrue(panel.save_results(str(self.root / "again.mcproj")))
            self.wait(panel)
        again = mp.read_materials_project(self.root / "again.mcproj")
        self.assertEqual(again["saved_at"], saved_at)
        self.assertEqual(again["written_at"], "2099-01-01T00:00:00+00:00")
        self.assertEqual(again["materials"], mp.read_materials_project(path)["materials"])

    def test_a_damaged_file_is_refused_and_what_was_shown_stays(self):
        first, path = self.saved_study()
        before = self.shown(first)
        damaged = self.root / "damaged.mcproj"
        damaged.write_bytes(b"not a project")
        self.assertTrue(first.open_results(str(damaged)))
        self.wait(first)
        self.assertIn("Not opened", first.message.text())
        self.assertEqual(self.shown(first), before)

    def test_a_changed_form_is_flagged_and_the_next_run_is_fresh(self):
        panel, _path = self.saved_study()
        self.assertTrue(panel.changed_note.isHidden())
        panel.mass_field.setText("130")
        self.assertFalse(panel.changed_note.isHidden())
        self.run_it(panel)
        self.assertTrue(panel.changed_note.isHidden())
        self.assertEqual(panel.origin_note.text(), sp.FRESH_TEXT)

    def test_the_file_menu_gives_a_v2_project_to_this_page_and_analyze_stays_as_it_was(self):
        _first, path = self.saved_study()
        window, _panel = self.page()
        analyze = window.analyze
        with mock.patch.object(analyze, "_project_step", side_effect=AssertionError("Analyze does not read it")):
            self.assertTrue(analyze.open_project(str(path)))
        self.wait(window.materials_workspace.study)
        self.assertEqual(window.stack.currentIndex(), pw.MATERIALS_PAGE)
        self.assertIsNone(analyze.snapshot)
        self.assertIn("SAVED RESULT", window.materials_workspace.study.origin_note.text())

    def test_an_old_project_still_opens_on_analyze_unchanged(self):
        window, panel = self.analysed()
        self.wait(panel)
        self.saved(panel)
        self.assertEqual(ap.project_schema(self.project), ap.SCHEMA)
        document_before = ap.read_project(self.project)[0]
        window, again = self.reopened()
        self.assertIsNotNone(again.snapshot)
        self.assertEqual(again.snapshot.document, document_before)
        self.assertEqual(ap.read_project(self.project)[0]["schema"], "universal/analysis-project/v1")
        study_panel = window.materials_workspace.study
        self.assertIsNone(study_panel.record)  # an old project holds no Materials result
        self.assertTrue(study_panel.open_results(str(self.project)))
        self.wait(study_panel)
        self.assertIn("Not opened", study_panel.message.text())


if __name__ == "__main__":
    unittest.main()

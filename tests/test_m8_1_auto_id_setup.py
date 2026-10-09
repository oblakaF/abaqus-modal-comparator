"""M8.1 Auto-ID specimen / family setup wizard (factual loading only; no Abaqus, no identification).

The wizard loads governed records through the backend parsers and shows facts and gaps.  It decides nothing
scientific, judges no readiness (the V12-I6 backend does), fabricates no value and writes nothing.  Service tests are
headless; the GUI is tested on the existing fake-widget harness and, where Tk is available, on the real application.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError
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

from domain.campaign_definition import (  # noqa: E402
    CAMPAIGN_SCHEMA_V1_2,
    MATERIAL_IDENTIFICATION,
    SPECIMEN_ENGINEERING_CALIBRATION,
    load_campaign_definition,
)
from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING  # noqa: E402
from domain.specimen_manifest import load_specimen_manifest  # noqa: E402
from services.auto_id_wizard import (  # noqa: E402
    FamilyPreparation,
    ItemStatus,
    SpecimenPreparation,
    WizardInputError,
    locate_passport,
    prepare_family,
    prepare_specimen_folder,
    prepare_specimen_passport,
    preparation_rows,
    wizard_rows,
    wizard_summary,
)
from services.forward_builder import load_bound_forward_model  # noqa: E402


SPECIMENS = ROOT / "docs" / "auto_id" / "specimens"
CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
PHYSICAL = SPECIMENS / "SP13.physical.specimen.json"
LEGACY = SPECIMENS / "SP13.specimen.json"
RUN_A = CAMPAIGNS / "M7_RUN_A.campaign.json"
RUN_B = CAMPAIGNS / "M7_RUN_B.campaign.json"
RUN_A_CAMPAIGN_HASH = "0a21ad0567901034b521b822b52f0c29944e96394f3692e1a8ebcd7ccd8d2ccf"


def _item(preparation, label, section=None):
    matches = [i for i in preparation.items if i.label == label and (section is None or i.section == section)]
    if len(matches) != 1:
        raise AssertionError(f"{label!r}: {len(matches)} rows")
    return matches[0]


def _tree(path: Path) -> list[str]:
    return sorted(p.relative_to(path).as_posix() for p in path.rglob("*"))


class _Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m8_1_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def package(self, passport: Path | None = PHYSICAL, name: str = "specimen.json",
                extra=("model.inp", "modes.unv", "frf.unv", "photo.jpg", "reference.odb")) -> Path:
        folder = self.tmp / "specimen"
        folder.mkdir(exist_ok=True)
        if passport is not None:
            shutil.copyfile(passport, folder / name)
        for file_name in extra:
            (folder / file_name).write_bytes(b"x" * 7)
        return folder

    def campaign(self, change, name="variant.campaign.json") -> Path:
        data = json.loads(RUN_A.read_text(encoding="utf-8"))
        change(data)
        path = self.tmp / name
        path.write_text(json.dumps(data), encoding="utf-8")
        return path


def v12(data, question=MATERIAL_IDENTIFICATION, tau=0.02):
    data.update(schema=CAMPAIGN_SCHEMA_V1_2, scientific_question=question, tau_mf=tau)
    if question == SPECIMEN_ENGINEERING_CALIBRATION:
        data["specimens"] = data["specimens"][:1]


# ----------------------------------------------------------------------------- A: one specimen folder

class SpecimenFolderTests(_Tmp):
    def test_valid_specimen_folder_loads_the_governed_passport(self):
        preparation = prepare_specimen_folder(self.package(), ROOT, roots=None)
        self.assertIsInstance(preparation, SpecimenPreparation)
        self.assertTrue(preparation.loaded)
        self.assertEqual(preparation.passport, load_specimen_manifest(PHYSICAL))  # the governed domain object
        self.assertEqual(preparation.fixture.fixture_id, "SP13/best-physical")
        kinds = sorted(f.kind for f in preparation.folder_files)
        self.assertEqual(kinds, ["model_input", "odb", "photo", "specimen_passport", "universal_file",
                                 "universal_file"])
        local = [i for i in preparation.items if i.section == "Specimen folder"]
        self.assertEqual(len(local), 5)  # listed only, never used instead of the pinned references
        self.assertTrue(all(i.status is ItemStatus.INFO and "never an unpinned local file" in i.detail for i in local))

    def test_identity_measurements_registration_and_references_are_displayed(self):
        preparation = prepare_specimen_folder(self.package(), ROOT, roots=None)
        governed = load_specimen_manifest(PHYSICAL)
        expected = {"Family": "CFRP-T300-plain-0.45-oldstock", "Design": "SP-13", "Physical specimen": "SP-13",
                    "Test run": str(governed.test_run_id), "Specimen type": "sandwich",
                    "Materials (face / core / adhesive roles)": "core: PLA_Basic_Core, face: CFRP_Face",
                    "Geometry calibration basis": "scan_to_panel_edges", "Registration basis": "PHYSICAL",
                    "Orientation reference": "panel_edges", "Calibration uncertainty": "AVAILABLE",
                    "Experiment fixture": "SP13/best-physical", "Identify": "default"}
        for label, value in expected.items():
            with self.subTest(label=label):
                item = _item(preparation, label)
                self.assertEqual((item.value, item.status), (value, ItemStatus.PRESENT))
        self.assertEqual(_item(preparation, "Passport").detail.split(";")[1].strip(),
                         f"manifest hash {governed.manifest_hash}")
        for label in ("Modes (curve-fitted modal set)", "FE model input", "Reference ODB", "FE geometry file"):
            with self.subTest(reference=label):  # stores not checked: never presented as verified
                item = _item(preparation, label)
                self.assertEqual(item.status, ItemStatus.INFO)
                self.assertIn("SHA-256 not verified", item.detail)
        self.assertIn("registration hash", _item(preparation, "Frozen registration").detail)

    def test_missing_physical_measurements_keep_the_passport_reason(self):
        preparation = prepare_specimen_folder(self.package(), ROOT, roots=None)
        governed = load_specimen_manifest(PHYSICAL)
        for label, field in (("Face thickness", "face_thickness_mm"), ("Core height", "core_height_mm"),
                             ("Suspension limit", "suspension_max_hz"), ("Plan dimensions", "plan_mm")):
            with self.subTest(label=label):
                item = _item(preparation, label)
                self.assertEqual((item.value, item.status, item.detail),
                                 ("", ItemStatus.UNAVAILABLE, governed.unavailable[field]))
                self.assertIn(item, preparation.gaps)

    def test_missing_or_ambiguous_passport(self):
        empty = prepare_specimen_folder(self.package(None), ROOT, roots=None)
        self.assertFalse(empty.loaded)
        self.assertEqual(_item(empty, "Passport").status, ItemStatus.MISSING)
        self.assertIn("not loaded", wizard_summary(empty))
        folder = self.package(PHYSICAL, "a.specimen.json", extra=())
        self.package(LEGACY, "b.specimen.json", extra=())
        with self.assertRaisesRegex(WizardInputError, "several specimen passports"):
            locate_passport(folder)
        ambiguous = prepare_specimen_folder(folder, ROOT, roots=None)  # never chosen for the user
        self.assertFalse(ambiguous.loaded)
        self.assertEqual(_item(ambiguous, "Passport").status, ItemStatus.MISSING)
        self.assertIn("several specimen passports", _item(ambiguous, "Passport").detail)

    def test_invalid_folder_and_invalid_json_do_not_crash(self):
        missing = prepare_specimen_folder(self.tmp / "does-not-exist", ROOT, roots=None)
        self.assertEqual(_item(missing, "Passport").status, ItemStatus.MISSING)
        folder = self.package(None, extra=())
        (folder / "specimen.json").write_text("{not json", encoding="utf-8")
        broken = prepare_specimen_folder(folder, ROOT, roots=None)
        self.assertFalse(broken.loaded)
        self.assertEqual(_item(broken, "Passport").status, ItemStatus.INVALID)

    def test_invalid_governed_identity_is_refused_not_guessed(self):
        data = json.loads(PHYSICAL.read_text(encoding="utf-8"))
        del data["test_run_id"]
        folder = self.package(None, extra=())
        (folder / "specimen.json").write_text(json.dumps(data), encoding="utf-8")
        preparation = prepare_specimen_folder(folder, ROOT, roots=None)
        self.assertFalse(preparation.loaded)
        passport = _item(preparation, "Passport")
        self.assertEqual(passport.status, ItemStatus.INVALID)
        self.assertIn("test_run_id", passport.detail)
        self.assertFalse(any(i.label == "Test run" for i in preparation.items))

    def test_passport_and_fixture_identity_mismatch_is_shown(self):
        data = json.loads(PHYSICAL.read_text(encoding="utf-8"))
        data["physical_specimen_id"] = "SP-99"  # the linked fixture records SP-13
        folder = self.package(None, extra=())
        (folder / "specimen.json").write_text(json.dumps(data), encoding="utf-8")
        preparation = prepare_specimen_folder(folder, ROOT, roots=None)
        self.assertTrue(preparation.loaded)
        item = _item(preparation, "Physical specimen (fixture)")
        self.assertEqual((item.value, item.status), ("SP-13", ItemStatus.MISMATCH))
        self.assertIn("SP-99", item.detail)
        self.assertIn(item, preparation.gaps)

    def test_unrecorded_physical_specimen_and_missing_registration_evidence(self):
        preparation = prepare_specimen_folder(self.package(LEGACY), ROOT, roots=None)
        governed = load_specimen_manifest(LEGACY)
        item = _item(preparation, "Physical specimen")
        self.assertEqual((item.value, item.status, item.detail),
                         ("", ItemStatus.UNAVAILABLE, governed.unavailable["physical_specimen_id"]))
        basis = _item(preparation, "Registration basis")
        self.assertEqual((basis.value, basis.status), ("LEGACY_REPLAY", ItemStatus.MISSING))
        self.assertIn(basis, preparation.gaps)

    def test_unavailable_store_size_mismatch_and_size_only_presence(self):
        folder = self.package()
        unconfigured = prepare_specimen_folder(folder, ROOT, roots={})
        self.assertEqual(_item(unconfigured, "FE geometry file").status, ItemStatus.NOT_CONFIGURED)
        store = self.tmp / "store"
        reference = load_specimen_manifest(PHYSICAL).fe_reference.geometry_file
        geometry = store.joinpath(*reference.location.relative_path.split("/"))
        geometry.parent.mkdir(parents=True)
        geometry.write_bytes(b"wrong size")
        mismatch = prepare_specimen_folder(folder, ROOT, roots={reference.location.store: store})
        self.assertEqual(_item(mismatch, "FE geometry file").status, ItemStatus.MISMATCH)
        geometry.write_bytes(b"y" * reference.size_bytes)  # the pinned size, not the pinned content
        sized = prepare_specimen_folder(folder, ROOT, roots={reference.location.store: store})
        item = _item(sized, "FE geometry file")
        self.assertEqual(item.status, ItemStatus.PRESENT_SHA256_NOT_VERIFIED)  # never plain PRESENT / READY
        self.assertIn("SHA-256 NOT verified", item.detail)
        self.assertIn("SHA-256 not verified", wizard_summary(sized))
        geometry.unlink()
        absent = prepare_specimen_folder(folder, ROOT, roots={reference.location.store: store})
        self.assertEqual(_item(absent, "FE geometry file").status, ItemStatus.NOT_FOUND)


# ----------------------------------------------------------------------------- B: family / campaign definition

class FamilyTests(_Tmp):
    def test_family_lists_every_specimen_with_its_governed_identity(self):
        preparation = prepare_family(RUN_A, ROOT, roots=None)
        definition = load_campaign_definition(RUN_A)
        self.assertIsInstance(preparation, FamilyPreparation)
        self.assertEqual(preparation.definition, definition)  # the same domain definition as the CLI path
        self.assertEqual(preparation.definition.campaign_hash, RUN_A_CAMPAIGN_HASH)
        self.assertEqual([(s.label, s.fixture_id, s.fit_rows, s.holdout_rows) for s in preparation.specimens],
                         [(s.label, s.fixture_id, s.fit_rows, s.holdout_rows) for s in definition.specimens])
        for wizard, spec in zip(preparation.specimens, definition.specimens):
            model = load_bound_forward_model(ROOT / spec.forward_model, ROOT)
            with self.subTest(specimen=spec.label):
                self.assertEqual(wizard.preparation.passport.manifest_hash, model.passport.manifest_hash)
                self.assertEqual(_item(wizard.preparation, "Experiment fixture").value, spec.fixture_id)
                forward = _item(wizard.preparation, "Forward model")
                self.assertEqual((forward.value, forward.status),
                                 (model.manifest.forward_model_id, ItemStatus.PRESENT))
                self.assertIn(model.manifest.manifest_hash, forward.detail)
                self.assertEqual(_item(wizard.preparation, "Pinned model input (INP)").value,
                                 model.manifest.model_input.file_name)
                self.assertEqual(_item(wizard.preparation, "Registration (forward model vs fixture)").status,
                                 ItemStatus.PRESENT)
                self.assertEqual(_item(wizard.preparation, "FIT rows").value, ", ".join(spec.fit_rows))
                self.assertEqual(_item(wizard.preparation, "HOLDOUT rows").value, ", ".join(spec.holdout_rows))
        self.assertTrue(all(i.status is ItemStatus.PRESENT for i in preparation.items if i.section == "Specimens"))

    def test_multiple_specimens_are_all_presented(self):
        preparation = prepare_family(RUN_B, ROOT, roots=None)
        rows = preparation_rows(preparation)
        labels = [s.label for s in preparation.specimens]
        self.assertGreaterEqual(len(labels), 2)
        for label in labels:
            with self.subTest(specimen=label):
                own = [r for r in rows if r[0].startswith(f"{label} · ")]
                specimen = next(s for s in preparation.specimens if s.label == label)
                self.assertEqual(len(own), len(specimen.preparation.items))
        self.assertEqual(len(rows), len(preparation.items) + sum(len(s.preparation.items)
                                                                 for s in preparation.specimens))
        self.assertTrue(all(len(r) == 5 for r in rows))  # section, item, value, status, provenance

    def test_linked_fixture_mismatch_is_shown(self):
        def swap(data):
            a, b = data["specimens"][0], data["specimens"][1]
            a["fixture_id"], b["fixture_id"] = b["fixture_id"], a["fixture_id"]

        preparation = prepare_family(self.campaign(swap), ROOT, roots=None)
        self.assertIsNotNone(preparation.definition)
        specimens = [i for i in preparation.items if i.section == "Specimens"]
        self.assertTrue(specimens)
        self.assertTrue(all(i.status is ItemStatus.MISMATCH for i in specimens))
        self.assertTrue(all("the passport links fixture" in i.detail for i in specimens))
        self.assertTrue(set(specimens) <= set(preparation.gaps))

    def test_invalid_campaign_and_invalid_json_are_reported_not_repaired(self):
        broken = prepare_family(self.campaign(lambda d: d.update(fitted_parameters=["E_in_plane_mpa", "unknown"])),
                                ROOT, roots=None)
        self.assertIsNone(broken.definition)
        self.assertEqual(broken.items[0].status, ItemStatus.INVALID)
        self.assertIn("not loaded", wizard_summary(broken))
        garbage = self.tmp / "garbage.campaign.json"
        garbage.write_text("[1, 2", encoding="utf-8")
        self.assertEqual(prepare_family(garbage, ROOT, roots=None).items[0].status, ItemStatus.INVALID)
        self.assertEqual(prepare_family(self.tmp / "absent.campaign.json", ROOT, roots=None).items[0].status,
                         ItemStatus.INVALID)


# ----------------------------------------------------------------------------- SPEC v1.2 question and τ_mf

class ScientificQuestionTests(_Tmp):
    def rows(self, preparation, section="Scientific question"):
        return {i.label: i for i in preparation.items if i.section == section}

    def test_undeclared_question_and_tau_are_never_inferred(self):
        for path in (RUN_A, RUN_B):
            with self.subTest(campaign=path.name):
                preparation = prepare_family(path, ROOT, roots=None)
                rows = self.rows(preparation)
                self.assertEqual((rows["Declared question"].value, rows["Declared question"].status),
                                 ("", ItemStatus.NOT_DECLARED))
                self.assertEqual((rows["τ_mf"].value, rows["τ_mf"].status), ("", ItemStatus.NOT_DECLARED))
                text = json.dumps(preparation_rows(preparation))
                for value in (MATERIAL_IDENTIFICATION, SPECIMEN_ENGINEERING_CALIBRATION, "0.02"):
                    self.assertNotIn(value, text)  # no fabricated question or τ_mf

    def test_declared_material_question_and_tau_are_shown_as_declared(self):
        preparation = prepare_family(self.campaign(lambda d: v12(d, MATERIAL_IDENTIFICATION, 0.015)), ROOT, roots=None)
        rows = self.rows(preparation)
        self.assertEqual((rows["Declared question"].value, rows["Declared question"].status),
                         (MATERIAL_IDENTIFICATION, ItemStatus.PRESENT))
        self.assertIn("never turned into a specimen calibration", rows["Declared question"].detail)
        self.assertEqual((rows["τ_mf"].value, rows["τ_mf"].status), ("0.015", ItemStatus.PRESENT))
        self.assertIn("never an uncertainty", rows["τ_mf"].detail)
        # No calibration is created from a material campaign
        self.assertEqual(preparation.definition.scientific_question, MATERIAL_IDENTIFICATION)
        self.assertNotIn(SPECIMEN_ENGINEERING_CALIBRATION, json.dumps(preparation_rows(preparation)))

    def test_declared_calibration_question_is_shown_with_execution_blocked(self):
        preparation = prepare_family(self.campaign(lambda d: v12(d, SPECIMEN_ENGINEERING_CALIBRATION, 0.02)), ROOT,
                                     roots=None)
        rows = self.rows(preparation)
        self.assertEqual(rows["Declared question"].value, SPECIMEN_ENGINEERING_CALIBRATION)
        self.assertIn("BLOCKED / NOT_AUTHORISED", rows["Declared question"].detail)
        self.assertEqual(rows["τ_mf"].value, "0.02")
        self.assertEqual(len(preparation.specimens), 1)

    def test_no_material_to_calibration_fallback(self):
        for path in (RUN_A, self.campaign(lambda d: v12(d, MATERIAL_IDENTIFICATION, 0.02), "m.campaign.json")):
            with self.subTest(campaign=path.name):
                preparation = prepare_family(path, ROOT, roots=None)
                self.assertNotEqual(preparation.definition.scientific_question, SPECIMEN_ENGINEERING_CALIBRATION)
                self.assertEqual(preparation.definition, load_campaign_definition(path))  # never rewritten
                self.assertNotIn(SPECIMEN_ENGINEERING_CALIBRATION, json.dumps(preparation_rows(preparation)))
                self.assertNotIn("READY", wizard_summary(preparation).replace("readiness", ""))


# ----------------------------------------------------------------------------- safety: no science, no execution, no writes

class SafetyTests(_Tmp):
    MODULES = (ROOT / "src" / "services" / "auto_id_wizard.py",)
    FORBIDDEN_IMPORTS = ("identification_pairing_policy", "identification_pairing", "identification_pipeline",
                         "identification_step", "identification_verdict", "identification_campaign_run",
                         "identification_objective", "branch_tracker", "baseline_freeze", "forward_solver",
                         "shape_extraction", "physical_registration", "subprocess", "modal_family_classifier",
                         "campaign_scientific_backend", "campaign_lm_provenance", "specimen_calibration_gate",
                         "specimen_calibration_output", "candidate_evaluation_evidence", "practical_identifiability",
                         "inverse_solver", "modal_core")

    def test_the_wizard_imports_no_scientific_or_execution_module_and_mutates_nothing(self):
        before = copy.deepcopy(STRICT_IDENTIFICATION_PAIRING)
        folder = prepare_specimen_folder(SPECIMENS, ROOT, roots=None)  # several passports: refused, not chosen
        family = prepare_family(RUN_B, ROOT, roots=None)
        self.assertEqual(STRICT_IDENTIFICATION_PAIRING, before)
        with self.assertRaises(FrozenInstanceError):
            family.definition = None
        with self.assertRaises(FrozenInstanceError):
            folder.items[0].status = ItemStatus.PRESENT
        for module in self.MODULES:
            tree = ast.parse(module.read_text(encoding="utf-8"))
            imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            imported |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
            with self.subTest(module=module.name):
                self.assertFalse([m for m in imported if m.split(".")[-1] in self.FORBIDDEN_IMPORTS])
                for node in ast.walk(tree):
                    if isinstance(node, ast.Attribute):
                        self.assertNotIn(node.attr, ("write_text", "write_bytes", "mkdir", "unlink", "rename",
                                                     "replace", "touch"))
                    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "open":
                        self.fail("the wizard opens a file directly")

    def test_no_solver_optimisation_or_file_write_when_loading(self):
        from services import identification_step

        folder = self.package()
        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        before_repo = _tree(ROOT / "docs" / "auto_id")
        before_tmp = _tree(self.tmp)
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), mock.patch.object(identification_step, "run_bounded_lm",
                                                                           refuse):
            prepare_specimen_folder(folder, ROOT, roots=fixture_roots_from_environment())
            prepare_specimen_folder(SPECIMENS, ROOT, roots=fixture_roots_from_environment())
            prepare_specimen_passport(PHYSICAL, ROOT, roots=fixture_roots_from_environment())
            for path in (RUN_A, RUN_B, self.campaign(lambda d: v12(d, SPECIMEN_ENGINEERING_CALIBRATION, 0.02))):
                preparation = prepare_family(path, ROOT, roots=fixture_roots_from_environment())
                preparation_rows(preparation)
                wizard_rows(preparation.items)
                wizard_summary(preparation)
        refuse.assert_not_called()
        self.assertEqual(_tree(ROOT / "docs" / "auto_id"), before_repo)
        before_tmp.append("variant.campaign.json")
        self.assertEqual(_tree(self.tmp), sorted(before_tmp))

    def test_store_gated_family_freezes_through_the_backend_unchanged(self):
        """READ-ONLY (store-gated): the wizard's definition is the one the backend prepares (no Abaqus)."""
        roots = fixture_roots_from_environment()
        missing = sorted({"snadwich", "carbon-project-archive"} - set(roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        from domain.experiment_fixture import load_experiment_fixture_manifest
        from services.identification_campaign_run import prepare_campaign_specimens

        preparation = prepare_family(RUN_A, ROOT, roots=roots)
        fixtures = load_experiment_fixture_manifest(ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json")
        specimens = prepare_campaign_specimens(preparation.definition, ROOT, fixtures, roots)
        self.assertEqual([(s.label, tuple(s.fit_rows), tuple(s.holdout_rows)) for s in specimens],
                         [(s.label, s.fit_rows, s.holdout_rows) for s in preparation.specimens])
        for wizard in preparation.specimens:
            for label in ("Modes (curve-fitted modal set)", "FE model input", "FE geometry file",
                          "Pinned model input (INP)"):
                with self.subTest(specimen=wizard.label, item=label):
                    self.assertEqual(_item(wizard.preparation, label).status, ItemStatus.PRESENT_SHA256_NOT_VERIFIED)


# ----------------------------------------------------------------------------- GUI (existing Effective Material Identification tab)

class SetupPageTests(_Tmp):
    def application(self):
        from test_material_identification_ui import _ApplicationHarness

        return _ApplicationHarness()._application()

    def rows(self, application):
        return tuple(application.material_auto_id_table.items.values())

    def test_page_is_part_of_the_existing_workflow_with_an_explicit_empty_state(self):
        from ui_policy import MATERIAL_IDENTIFICATION_STEP_LABELS

        application = self.application()
        self.assertEqual(MATERIAL_IDENTIFICATION_STEP_LABELS[0], "0. Auto-ID Setup")
        self.assertEqual(len(application.material_identification_pages), 9)
        self.assertIn("2. Data Readiness Check", application.material_identification_pages)
        self.assertEqual(application.material_auto_id_summary_label.kwargs["text"], "Nothing selected.")
        self.assertEqual(self.rows(application), ())

    def test_loading_a_family_and_a_specimen_folder(self):
        import material_identification_ui as ui

        application = self.application()
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assertEqual(self.rows(application), preparation_rows(prepare_family(
            RUN_A, ROOT, fixture_roots_from_environment())))
        summary = application.material_auto_id_summary_label.kwargs["text"]
        self.assertIn("M7.1/RUN_A/SP02+SP13", summary)
        self.assertIn("not a scientific readiness judgement", summary)
        ui.load_auto_id_source(application, "specimen", str(self.package()))
        self.assertTrue(any(r[1] == "Test run" for r in self.rows(application)))
        self.assertIn("specimen:", application.material_auto_id_source_label.kwargs["text"])

    def test_bad_selections_are_shown_without_crashing(self):
        import material_identification_ui as ui

        application = self.application()
        ui.load_auto_id_source(application, "specimen", str(self.tmp / "absent"))
        self.assertEqual(self.rows(application)[0][3], "MISSING")
        ui.load_auto_id_source(application, "family", str(self.tmp / "absent.campaign.json"))
        self.assertEqual(self.rows(application)[0][3], "INVALID")
        with mock.patch("services.auto_id_wizard.prepare_family", side_effect=RuntimeError("unexpected")):
            ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assertIn("could not be loaded: unexpected", application.material_auto_id_summary_label.kwargs["text"])
        self.assertEqual(self.rows(application), ())

    def test_browse_buttons_use_the_file_dialogs_only(self):
        import material_identification_ui as ui

        application = self.application()
        page = application.material_identification_pages["0. Auto-ID Setup"]
        buttons = {}

        def collect(widget):
            if "command" in widget.kwargs and widget.kwargs.get("text"):
                buttons[widget.kwargs.get("text")] = widget.kwargs["command"]
            for child in widget.children:
                collect(child)

        collect(page)
        self.assertEqual(sorted(buttons), ["Select family / campaign definition...", "Select specimen folder..."])
        with mock.patch.object(ui.filedialog, "askopenfilename", return_value=str(RUN_B)):
            buttons["Select family / campaign definition..."]()
        self.assertIn("RUN_B", application.material_auto_id_summary_label.kwargs["text"])
        with mock.patch.object(ui.filedialog, "askdirectory", return_value=""):  # cancelled: nothing changes
            buttons["Select specimen folder..."]()
        self.assertIn("RUN_B", application.material_auto_id_summary_label.kwargs["text"])

    def test_the_v12_i6_scientific_readiness_presentation_is_preserved(self):
        import material_identification_ui as ui

        application = self.application()
        record = {"schema": "auto-id/v12-scientific-readiness/v1", "status": "NOT_READY",
                  "scientific_question": None, "tau_mf": None, "campaign": {"campaign_id": "X"},
                  "refusal_reasons": [{"code": "LM_HISTORY_MISSING", "detail": "no journal"}], "evidence": {},
                  "uncertainty_basis": None, "diagnostic_candidate": None, "calibration": None,
                  "released_calibration_parameters": None, "material_formal_output": None,
                  "material_family_consistency": None, "material_claim": None, "inp_fragment_available": False,
                  "production_execution": "NOT_AUTHORISED", "production_calibration": None}
        application.scientific_readiness_record = record
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assertIs(application.scientific_readiness_record, record)  # the wizard never sets readiness
        application._refresh_material_identification_pages()
        scientific = dict(application.material_scientific_readiness_table.items.values())
        self.assertEqual(scientific["Readiness"], "NOT_READY")
        self.assertIn("LM_HISTORY_MISSING", scientific["Refusal reasons"])
        self.assertEqual(application.material_scientific_readiness_status_label.kwargs["text"], "NOT_READY")
        source = (ROOT / "src" / "material_identification_ui.py").read_text(encoding="utf-8")
        self.assertNotIn("judge_campaign_run", source)  # the GUI judges nothing; readiness stays in the backend

    def test_setup_status_never_claims_scientific_readiness(self):
        import material_identification_ui as ui

        application = self.application()
        for kind, path in (("family", RUN_A), ("family", RUN_B), ("specimen", self.package())):
            ui.load_auto_id_source(application, kind, str(path))
            statuses = {r[3] for r in self.rows(application)}
            self.assertNotIn("READY", statuses)
            self.assertNotIn("READY", application.material_auto_id_summary_label.kwargs["text"]
                             .replace("readiness", ""))


class RealTkSetupPageTests(unittest.TestCase):
    """The real application (Tk), where a display is available."""

    @classmethod
    def setUpClass(cls):
        try:
            import tkinter as tk

            cls.root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            raise unittest.SkipTest(f"Tk is unavailable: {error}")
        cls.root.withdraw()
        import main
        import ui_workflow

        disabled = {"autosave_enabled": False, "restore_on_startup": False, "show_recovery_notice": False}
        with mock.patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), \
                mock.patch.object(ui_workflow, "discover_abaqus_installations", return_value=()):
            cls.application = main.app.ModalComparatorApp(cls.root)
        cls.root.update_idletasks()

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "root"):
            cls.root.destroy()

    def test_real_page_loads_a_family_without_running_anything(self):
        import material_identification_ui as ui

        application = self.application
        notebook = application.material_identification_notebook
        labels = [notebook.tab(tab, "text") for tab in notebook.tabs()]
        self.assertEqual(labels[0], "0. Auto-ID Setup")
        self.assertIn("2. Data Readiness Check", labels)
        refuse = mock.Mock(side_effect=AssertionError("process"))
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse):
            ui.load_auto_id_source(application, "family", str(RUN_A))
            self.root.update_idletasks()
        refuse.assert_not_called()
        table = application.material_auto_id_table
        self.assertEqual(len(table.get_children()), len(preparation_rows(application.auto_id_preparation)))
        self.assertIn("M7.1/RUN_A/SP02+SP13", application.material_auto_id_summary_label.cget("text"))
        self.assertTrue(application.material_scientific_readiness_table.winfo_exists())  # the I6 page is intact


if __name__ == "__main__":
    unittest.main()

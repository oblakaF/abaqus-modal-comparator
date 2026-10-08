"""M8.1 Auto-ID specimen / family wizard (no Abaqus, no identification).

The wizard loads governed records through the backend parsers, reports facts and gaps, and decides nothing
scientific.  Headless tests cover the service; the Tk page test skips without a display.
"""

from __future__ import annotations

import ast
import copy
from dataclasses import FrozenInstanceError
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.campaign_definition import load_campaign_definition
from domain.experiment_fixture import fixture_roots_from_environment
from domain.identification_pairing_policy import STRICT_IDENTIFICATION_PAIRING
from domain.specimen_manifest import load_specimen_manifest
from services.auto_id_wizard import (
    FamilyPreparation,
    ItemStatus,
    SpecimenPreparation,
    WizardInputError,
    locate_passport,
    prepare_family,
    prepare_specimen_folder,
    prepare_specimen_passport,
    wizard_rows,
    wizard_summary,
)
from services.forward_builder import load_bound_forward_model


SPECIMENS = ROOT / "docs" / "auto_id" / "specimens"
CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
PHYSICAL = SPECIMENS / "SP13.physical.specimen.json"
LEGACY = SPECIMENS / "SP13.specimen.json"


def _item(preparation, label):
    matches = [i for i in preparation.items if i.label == label]
    if len(matches) != 1:
        raise AssertionError(f"{label!r}: {len(matches)} rows")
    return matches[0]


class _Folder(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="m8_wizard_"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def package(self, passport: Path | None = PHYSICAL, name: str = "specimen.json", extra=("model.inp", "modes.unv",
                                                                                            "frf.unv", "photo.jpg",
                                                                                            "reference.odb")):
        if passport is not None:
            shutil.copyfile(passport, self.tmp / name)
        for file_name in extra:
            (self.tmp / file_name).write_bytes(b"x" * 7)
        return self.tmp


class SpecimenFolderTests(_Folder):
    def test_valid_specimen_package_loads(self):
        preparation = prepare_specimen_folder(self.package(), ROOT, roots=None)
        self.assertIsInstance(preparation, SpecimenPreparation)
        self.assertTrue(preparation.loaded)
        self.assertEqual(preparation.passport_path.name, "specimen.json")
        kinds = sorted(f.kind for f in preparation.folder_files)
        self.assertEqual(kinds, ["model_input", "odb", "photo", "specimen_passport", "universal_file",
                                 "universal_file"])
        local = [i for i in preparation.items if i.section == "Specimen folder"]
        self.assertEqual(len(local), 5)
        self.assertTrue(all(i.status is ItemStatus.INFO and "never an unpinned local file" in i.detail for i in local))
        self.assertEqual(preparation.fixture.fixture_id, "SP13/best-physical")

    def test_existing_passport_values_populate_the_fields(self):
        preparation = prepare_specimen_folder(self.package(), ROOT, roots=None)
        governed = load_specimen_manifest(PHYSICAL)
        self.assertEqual(preparation.passport.manifest_hash, governed.manifest_hash)  # the same domain object
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
        self.assertIn("re_suspension of SP13_500by500_Glue420_Auxetic_newSP01_260909",
                      _item(preparation, "Remount linkage").value)

    def test_unavailable_physical_values_keep_the_passport_reason(self):
        preparation = prepare_specimen_folder(self.package(), ROOT, roots=None)
        governed = load_specimen_manifest(PHYSICAL)
        for label, field in (("Face thickness", "face_thickness_mm"), ("Core height", "core_height_mm"),
                             ("Suspension limit", "suspension_max_hz"), ("Plan dimensions", "plan_mm")):
            with self.subTest(label=label):
                item = _item(preparation, label)
                self.assertEqual((item.value, item.status, item.detail),
                                 ("", ItemStatus.UNAVAILABLE, governed.unavailable[field]))

    def test_missing_required_identity_is_displayed_not_guessed(self):
        data = json.loads(PHYSICAL.read_text(encoding="utf-8"))
        del data["test_run_id"]
        folder = self.package(None)
        (folder / "specimen.json").write_text(json.dumps(data), encoding="utf-8")
        preparation = prepare_specimen_folder(folder, ROOT, roots=None)
        self.assertFalse(preparation.loaded)
        passport = _item(preparation, "Passport")
        self.assertEqual(passport.status, ItemStatus.INVALID)
        self.assertIn("test_run_id", passport.detail)
        self.assertFalse(any(i.label == "Test run" for i in preparation.items))
        self.assertIn("not loaded", wizard_summary(preparation))

    def test_unrecorded_physical_specimen_is_shown_as_unavailable(self):
        preparation = prepare_specimen_folder(self.package(LEGACY), ROOT, roots=None)
        governed = load_specimen_manifest(LEGACY)
        item = _item(preparation, "Physical specimen")
        self.assertEqual((item.value, item.status, item.detail),
                         ("", ItemStatus.UNAVAILABLE, governed.unavailable["physical_specimen_id"]))

    def test_missing_physical_registration_evidence_is_displayed(self):
        preparation = prepare_specimen_folder(self.package(LEGACY), ROOT, roots=None)
        basis = _item(preparation, "Registration basis")
        self.assertEqual((basis.value, basis.status), ("LEGACY_REPLAY", ItemStatus.MISSING))
        self.assertIn("physical registration reference", basis.detail)
        self.assertIn(basis, preparation.gaps)
        self.assertEqual(_item(preparation, "Geometry calibration basis").value, "documented_centered_alignment")

    def test_folder_without_or_with_several_passports(self):
        empty = prepare_specimen_folder(self.package(None), ROOT, roots=None)
        self.assertEqual(_item(empty, "Passport").status, ItemStatus.MISSING)
        self.package(PHYSICAL, "a.specimen.json")
        self.package(LEGACY, "b.specimen.json")
        with self.assertRaisesRegex(WizardInputError, "several specimen passports"):
            locate_passport(self.tmp)
        self.assertEqual(_item(prepare_specimen_folder(self.tmp, ROOT, roots=None), "Passport").status,
                         ItemStatus.MISSING)

    def test_pinned_files_are_checked_against_the_configured_stores_only(self):
        folder = self.package()
        unconfigured = prepare_specimen_folder(folder, ROOT, roots={})
        self.assertEqual(_item(unconfigured, "FE geometry file").status, ItemStatus.NOT_CONFIGURED)
        store = self.tmp / "store"
        geometry = store / "fe_geometry" / "SP13_fe_geometry.csv"
        geometry.parent.mkdir(parents=True)
        geometry.write_bytes(b"wrong size")
        mismatch = prepare_specimen_folder(folder, ROOT, roots={"carbon-project-archive": store})
        self.assertEqual(_item(mismatch, "FE geometry file").status, ItemStatus.MISMATCH)
        geometry.unlink()
        absent = prepare_specimen_folder(folder, ROOT, roots={"carbon-project-archive": store})
        self.assertEqual(_item(absent, "FE geometry file").status, ItemStatus.NOT_FOUND)


class FamilyTests(unittest.TestCase):
    def test_family_selection_preserves_specimen_identities(self):
        path = CAMPAIGNS / "M7_RUN_A.campaign.json"
        preparation = prepare_family(path, ROOT, roots=None)
        definition = load_campaign_definition(path)
        self.assertIsInstance(preparation, FamilyPreparation)
        self.assertEqual([(s.label, s.fixture_id, s.fit_rows, s.holdout_rows) for s in preparation.specimens],
                         [(s.label, s.fixture_id, s.fit_rows, s.holdout_rows) for s in definition.specimens])
        for wizard, spec in zip(preparation.specimens, definition.specimens):
            backend = load_bound_forward_model(ROOT / spec.forward_model, ROOT).passport  # the backend's path
            with self.subTest(specimen=spec.label):
                self.assertEqual(wizard.preparation.passport.manifest_hash, backend.manifest_hash)
                self.assertEqual((wizard.preparation.passport.physical_specimen_id, wizard.preparation.passport.test_run_id),
                                 (backend.physical_specimen_id, backend.test_run_id))
                self.assertEqual(_item(wizard.preparation, "Experiment fixture").value, spec.fixture_id)
        self.assertTrue(all(i.status is ItemStatus.PRESENT for i in preparation.items if i.section == "Specimens"))

    def test_wizard_produces_the_same_domain_definition_as_the_cli_path(self):
        for name in ("M7_RUN_A.campaign.json", "M7_RUN_B.campaign.json"):
            with self.subTest(campaign=name):
                preparation = prepare_family(CAMPAIGNS / name, ROOT, roots=None)
                direct = load_campaign_definition(CAMPAIGNS / name)  # what tools/m7_campaign.py loads
                self.assertEqual(preparation.definition.campaign_hash, direct.campaign_hash)
                self.assertEqual(preparation.definition, direct)
        specimen = prepare_specimen_passport(PHYSICAL, ROOT, roots=None)
        self.assertEqual(specimen.passport, load_specimen_manifest(PHYSICAL))

    def test_invalid_campaign_is_reported_not_repaired(self):
        tmp = Path(tempfile.mkdtemp(prefix="m8_campaign_"))
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        data = json.loads((CAMPAIGNS / "M7_RUN_A.campaign.json").read_text(encoding="utf-8"))
        data["fitted_parameters"] = ["E_in_plane_mpa", "unknown"]
        broken = tmp / "broken.campaign.json"
        broken.write_text(json.dumps(data), encoding="utf-8")
        preparation = prepare_family(broken, ROOT, roots=None)
        self.assertIsNone(preparation.definition)
        self.assertEqual(preparation.items[0].status, ItemStatus.INVALID)
        self.assertIn("not loaded", wizard_summary(preparation))


class NoScienceInTheWizardTests(unittest.TestCase):
    MODULES = (ROOT / "src" / "services" / "auto_id_wizard.py", ROOT / "src" / "auto_id_wizard_ui.py")
    FORBIDDEN_IMPORTS = ("identification_pairing_policy", "identification_pairing", "identification_pipeline",
                         "identification_step", "identification_verdict", "identification_campaign_run",
                         "identification_objective", "branch_tracker", "baseline_freeze", "forward_solver",
                         "shape_extraction", "physical_registration", "subprocess", "modal_family_classifier")

    def test_wizard_cannot_mutate_pairing_or_thresholds(self):
        before = copy.deepcopy(STRICT_IDENTIFICATION_PAIRING)
        folder = prepare_specimen_folder(SPECIMENS, ROOT, roots=None)  # several passports: refused, not chosen
        family = prepare_family(CAMPAIGNS / "M7_RUN_B.campaign.json", ROOT, roots=None)
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
                writes = [node for node in ast.walk(tree) if isinstance(node, (ast.Assign, ast.AugAssign))
                          for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
                          if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
                          and target.value.id not in ("app", "self")]
                self.assertEqual(writes, [])

    def test_no_identification_or_abaqus_runs_when_the_wizard_opens_or_completes(self):
        refuse = mock.Mock(side_effect=AssertionError("a process was started"))
        with mock.patch("subprocess.Popen", refuse), mock.patch("subprocess.run", refuse), \
                mock.patch("os.system", refuse):
            prepare_specimen_folder(SPECIMENS, ROOT, roots=fixture_roots_from_environment())
            prepare_specimen_passport(PHYSICAL, ROOT, roots=fixture_roots_from_environment())
            for name in ("M7_RUN_A.campaign.json", "M7_RUN_B.campaign.json"):
                preparation = prepare_family(CAMPAIGNS / name, ROOT, roots=fixture_roots_from_environment())
                wizard_rows(preparation.items)
                wizard_summary(preparation)
        refuse.assert_not_called()


class StoreBackendTests(unittest.TestCase):
    def test_wizard_definition_freezes_through_the_backend(self):
        roots = fixture_roots_from_environment()
        missing = sorted({"snadwich", "carbon-project-archive"} - set(roots))
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        from domain.experiment_fixture import load_experiment_fixture_manifest
        from services.identification_campaign_run import prepare_campaign_specimens

        preparation = prepare_family(CAMPAIGNS / "M7_RUN_A.campaign.json", ROOT, roots=roots)
        fixtures = load_experiment_fixture_manifest(ROOT / "docs/auto_id/fixtures/real_experiment_fixtures.json")
        specimens = prepare_campaign_specimens(preparation.definition, ROOT, fixtures, roots)  # no Abaqus
        self.assertEqual([(s.label, tuple(s.fit_rows), tuple(s.holdout_rows)) for s in specimens],
                         [(s.label, s.fit_rows, s.holdout_rows) for s in preparation.specimens])
        for wizard in preparation.specimens:
            with self.subTest(specimen=wizard.label):
                for label in ("Modes (curve-fitted modal set)", "FE model input", "FE geometry file"):
                    self.assertEqual(_item(wizard.preparation, label).status, ItemStatus.PRESENT)


class SetupPageTests(unittest.TestCase):
    def test_page_renders_a_preparation_without_running_anything(self):
        try:
            import tkinter as tk
            root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.addCleanup(root.destroy)
        root.withdraw()
        from types import SimpleNamespace
        from tkinter import ttk
        import auto_id_wizard_ui as ui

        app = SimpleNamespace()
        page = ttk.Frame(root)
        ui.build_auto_id_setup_page(app, page)
        app.auto_id_source_kind.set("family")
        app.auto_id_source_path.set(str(CAMPAIGNS / "M7_RUN_A.campaign.json"))
        with mock.patch("subprocess.Popen", side_effect=AssertionError("process")):
            ui._load(app)
        self.assertIn("M7.1/RUN_A/SP02+SP13", app.auto_id_summary.get())
        self.assertEqual(len(app.auto_id_table.get_children()), len(app.auto_id_preparation.items))
        app.auto_id_specimen_choice.set("SP13")
        ui._show(app)
        self.assertEqual(len(app.auto_id_table.get_children()), len(app.auto_id_preparation.specimens[1].preparation.items))


if __name__ == "__main__":
    unittest.main()

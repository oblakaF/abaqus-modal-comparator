"""M8.6 — read-only Engineering Constants and calibration material preview (typed backend evaluation only).

The preview is built from the exact typed ``ScientificReadiness`` returned by the shared backend for the current
evaluation and the SHA-256-verified source INP bytes of that same evaluation, through the accepted constants and
I4 / I5 fragment services.  Synthetic runs use the M4.6 fake solver; nothing is executed or written.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
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

from domain.campaign_definition import parse_campaign_definition  # noqa: E402
from domain.forward_model_manifest import EngineeringConstants  # noqa: E402
from services import calibration_material_preview as preview_module  # noqa: E402
from services import stored_run_evidence as adapter  # noqa: E402
from services.calibration_material_preview import (  # noqa: E402
    ConstantOrigin,
    PreviewState,
    calibration_material_preview,
)
from services.campaign_scientific_backend import judge_campaign_run  # noqa: E402
from services.identification_campaign_run import CampaignRun  # noqa: E402
from services.specimen_calibration_output import (  # noqa: E402
    calibration_material_name,
    governed_engineering_constants,
    render_calibration_inp_fragment,
)
from test_m7_campaign import synthetic_specimen  # noqa: E402
from test_v12_i1_campaign_question import calibration_definition  # noqa: E402
from test_v12_i6_backend_integration import rechain  # noqa: E402
from v12_i6_support import calibration_run  # noqa: E402

CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
RUN_A = CAMPAIGNS / "M7_RUN_A.campaign.json"
NOT_AVAILABLE = "NOT_AVAILABLE_FOR_SELECTION"
ORDER = ("E1", "E2", "E3", "nu12", "nu13", "nu23", "G12", "G13", "G23")
UNITS = ("MPa", "MPa", "MPa", "1", "1", "1", "MPa", "MPa", "MPa")


def _journal(run_root: Path) -> Path:
    found = list(Path(run_root).glob("campaign/*/journal.json"))
    assert len(found) == 1, found
    return found[0]


def _tree(path: Path) -> list[str]:
    return sorted(p.relative_to(path).as_posix() for p in Path(path).rglob("*"))


class _Fixture(unittest.TestCase):
    _directory = None

    @classmethod
    def setUpClass(cls):
        if _Fixture._directory is not None:
            return
        _Fixture._directory = tempfile.TemporaryDirectory()
        tmp = Path(_Fixture._directory.name)
        definition = parse_campaign_definition(calibration_definition())
        item, store = synthetic_specimen(definition, "A", tmp / "base" / "data")
        _Fixture.base = calibration_run(tmp / "base", definition=definition, item=item)
        _Fixture.store = store
        data = calibration_definition()
        data["sigma"]["setup"]["sd_ln"] = 0.2
        imprecise = parse_campaign_definition(data)
        item_b, store_b = synthetic_specimen(imprecise, "A", tmp / "imprecise" / "data")
        _Fixture.imprecise = calibration_run(tmp / "imprecise", definition=imprecise, item=item_b)
        _Fixture.imprecise_store = store_b

    def readiness(self, run=None):
        run = run or self.base
        return judge_campaign_run(run.definition, [run.item], run.evidence)

    def source(self, run=None) -> bytes:
        return (run or self.base).evidence.source_inps["A"]

    def application(self, record=None):
        from test_material_identification_ui import _ApplicationHarness

        application = _ApplicationHarness()._application()
        if record is not None:
            application.scientific_readiness_record = record
        application._refresh_material_identification_pages()
        return application

    def definition_file(self, definition) -> Path:
        folder = Path(tempfile.mkdtemp(prefix="m8_6_def_"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        path = folder / "campaign.campaign.json"
        path.write_text(json.dumps(definition.canonical), encoding="utf-8")
        return path

    def copy_run(self, run) -> Path:
        target = Path(tempfile.mkdtemp(prefix="m8_6_run_"))
        self.addCleanup(shutil.rmtree, target, ignore_errors=True)
        shutil.copytree(run.campaign.run_dir.parent.parent, target / "runs")
        return target / "runs"

    def patched(self, run):
        store = self.imprecise_store if run is self.imprecise else self.store
        return (mock.patch.object(adapter, "campaign_specimens", return_value=(run.item,)),
                mock.patch("domain.experiment_fixture.fixture_roots_from_environment",
                           return_value={"synthetic": store}))

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
    def text(application) -> str:
        return application.material_calibration_preview_label.kwargs["text"]

    @staticmethod
    def rows(table) -> list[tuple]:
        return [tuple(table.items[key]) for key in table.get_children()]

    def assert_hidden(self, application):
        text = self.text(application)
        self.assertIn(f"Calibration material preview: {NOT_AVAILABLE}", text)
        self.assertEqual(self.rows(application.material_calibration_constants_table), [])
        self.assertEqual(self.rows(application.material_calibration_fragment_table), [])
        for stale in ("CAL_", "E_in_plane_mpa", "SYA/fake", "Labels:"):
            self.assertNotIn(stale, text)

    def assert_available(self, application):
        self.assertIn("Calibration material preview: PREVIEW_AVAILABLE", self.text(application))
        self.assertEqual(len(self.rows(application.material_calibration_constants_table)), 9)


def tearDownModule():
    if _Fixture._directory is not None:
        _Fixture._directory.cleanup()
        _Fixture._directory = None


# ----------------------------------------------------------------------------- constants 1-3

class ConstantsTests(_Fixture):
    def test_01_nine_constants_come_from_the_accepted_service(self):
        readiness = self.readiness()
        governed = governed_engineering_constants(readiness.calibration_record)
        preview = calibration_material_preview(readiness, {"A": self.source()})
        self.assertIs(preview.state, PreviewState.AVAILABLE)
        self.assertEqual({r.name: r.value for r in preview.constants}, {n: c.value for n, c in governed.items()})
        self.assertEqual({r.name: r.provenance for r in preview.constants},
                         {n: c.provenance for n, c in governed.items()})
        released = readiness.calibration_record.calibration_parameters["E_in_plane_mpa"]["value"]
        self.assertEqual(preview.constants[0].value, released)  # exact, never rounded
        application, _ = self.evaluated()
        table = self.rows(application.material_calibration_constants_table)
        self.assertEqual([row[1] for row in table], [repr(governed[name].value) for name in ORDER])
        self.assertNotIn(0.0, [r.value for r in preview.constants])

    def test_02_order_and_units(self):
        preview = calibration_material_preview(self.readiness(), {"A": self.source()})
        self.assertEqual(tuple(r.name for r in preview.constants), ORDER)
        self.assertEqual(ORDER, EngineeringConstants.names())
        self.assertEqual(tuple(r.unit for r in preview.constants), UNITS)
        application, _ = self.evaluated()
        table = self.rows(application.material_calibration_constants_table)
        self.assertEqual(tuple(row[0] for row in table), ORDER)
        self.assertEqual(tuple(row[2] for row in table), UNITS)

    def test_03_provenance_of_variable_and_fixed_constants(self):
        preview = calibration_material_preview(self.readiness(), {"A": self.source()})
        origin = {r.name: (r.origin, r.provenance) for r in preview.constants}
        for name in ("E1", "E2"):
            self.assertEqual(origin[name], (ConstantOrigin.RELEASED_CALIBRATION_PARAMETER,
                                            "released calibration parameter E_in_plane_mpa"))
        self.assertEqual(origin["G12"], (ConstantOrigin.FIXED_CAMPAIGN_PARAMETER,
                                         "campaign definition fixed parameter G12_mpa"))
        for name in ("E3", "nu12", "nu13", "nu23", "G13", "G23"):
            self.assertEqual(origin[name], (ConstantOrigin.PARAMETERISATION_FIXED_CONSTANT,
                                            "carbon-property-set/v1 fixed constant (SPEC §5.2)"))
        application, _ = self.evaluated()
        table = {row[0]: row[3:] for row in self.rows(application.material_calibration_constants_table)}
        self.assertEqual(table["G12"], ("FIXED_CAMPAIGN_PARAMETER", "campaign definition fixed parameter G12_mpa"))


# ----------------------------------------------------------------------------- fragment 4-10

class FragmentTests(_Fixture):
    def test_04_exact_match_with_the_accepted_fragment(self):
        readiness = self.readiness()
        record = readiness.calibration_record
        expected = render_calibration_inp_fragment(record, governed_engineering_constants(record), self.source())
        preview = calibration_material_preview(readiness, {"A": self.source()})
        self.assertEqual(preview.fragment, expected)
        application, _ = self.evaluated()
        lines = [row[0] for row in self.rows(application.material_calibration_fragment_table)]
        self.assertEqual(lines, expected.content.splitlines())

    def test_05_source_sha256_is_verified(self):
        readiness = self.readiness()
        preview = calibration_material_preview(readiness, {"A": self.source()})
        digest = hashlib.sha256(self.source()).hexdigest()
        self.assertEqual(digest, readiness.calibration_record.identity["inp_sha256"])
        self.assertEqual(preview.fragment.source_inp_sha256, digest)
        application, _ = self.evaluated()
        self.assertIn(f"Source INP SHA-256 (verified): {digest}", self.text(application))

    def test_06_source_mismatch_refuses(self):
        readiness = self.readiness()
        for sources in ({"A": self.source() + b"** changed\n"}, {"A": self.source(self.imprecise)[:-1]}, {}, {"B": b""},
                        {"A": "text"}):
            preview = calibration_material_preview(readiness, sources)
            self.assertIs(preview.state, PreviewState.REFUSED, sources.keys())
            self.assertEqual((preview.constants, preview.fragment), ((), None))
        import material_identification_ui as ui

        application, _ = self.evaluated()
        active, evaluation = application.auto_id_active_typed
        application.auto_id_active_typed = (active, dataclasses.replace(
            evaluation, source_inps={"A": self.source() + b"** changed\n"}))
        application._refresh_material_identification_pages()
        self.assertIn("PREVIEW_REFUSED", self.text(application))
        self.assertIn("SHA-256", self.text(application))
        self.assertEqual(ui.calibration_preview_view(application)["constants"], ())
        self.assertEqual(self.rows(application.material_calibration_fragment_table), [])

    def test_07_unknown_or_incomplete_constants_refuse(self):
        readiness = self.readiness()
        governed = governed_engineering_constants(readiness.calibration_record)
        incomplete = {k: v for k, v in governed.items() if k != "G23"}
        unknown = dict(governed, E3=dataclasses.replace(governed["E3"], provenance="guessed default"))
        reordered = dict(reversed(list(governed.items())))
        for constants in (incomplete, unknown, reordered):
            with mock.patch.object(preview_module, "released_engineering_constants", return_value=constants):
                preview = calibration_material_preview(readiness, {"A": self.source()})
            self.assertIs(preview.state, PreviewState.REFUSED)
            self.assertEqual((preview.constants, preview.fragment), ((), None))
        record = readiness.calibration_record
        wrong_unit = dataclasses.replace(record, calibration_parameters={
            "E_in_plane_mpa": dict(record.calibration_parameters["E_in_plane_mpa"], unit="GPa")})
        preview = calibration_material_preview(dataclasses.replace(readiness, calibration_record=wrong_unit),
                                               {"A": self.source()})
        self.assertIs(preview.state, PreviewState.REFUSED)
        self.assertIn("unit", preview.reason)

    def test_08_unsupported_material_options_refuse(self):
        readiness = self.readiness()
        source = self.source().decode("latin-1")
        after = "*Material, name=Core_PLA"  # the material that follows the production CFRP_Face block
        self.assertEqual(source.count(after), 1)
        changed = source.replace(after, "*Plastic\n 100., 0.\n" + after).encode("latin-1")
        record = readiness.calibration_record
        bound = dataclasses.replace(record, identity=dict(record.identity,
                                                          inp_sha256=hashlib.sha256(changed).hexdigest()))
        preview = calibration_material_preview(dataclasses.replace(readiness, calibration_record=bound),
                                               {"A": changed})
        self.assertIs(preview.state, PreviewState.REFUSED)
        self.assertIn("*plastic", preview.reason.lower())
        self.assertEqual((preview.constants, preview.fragment), ((), None))

    def test_09_production_material_is_unchanged(self):
        readiness = self.readiness()
        source = bytes(self.source())
        sources = {"A": source}
        preview = calibration_material_preview(readiness, sources)
        production = readiness.calibration_record.identity["forward_model"]["production_material_name"]
        self.assertEqual(preview.production_material_name, production)
        self.assertEqual(sources["A"], source)
        self.assertEqual(hashlib.sha256(sources["A"]).hexdigest(), preview.fragment.source_inp_sha256)
        self.assertNotIn(f"*Material, name={production}", preview.fragment.content)
        self.assertEqual(preview.source_material_keywords, ("*Material", "*Density", "*Elastic"))
        application, _ = self.evaluated()
        self.assertIn(f"Production material: {production} (unchanged; never overwritten)", self.text(application))

    def test_10_cal_material_is_created_in_memory_only(self):
        readiness = self.readiness()
        preview = calibration_material_preview(readiness, {"A": self.source()})
        name = calibration_material_name(readiness.calibration_record)
        self.assertTrue(name.startswith("CAL_A_"))
        self.assertEqual(preview.fragment.material_name, name)
        self.assertIn(f"*Material, name={name}", preview.fragment.content)
        self.assertIsInstance(preview.fragment.content, str)
        application, _ = self.evaluated()
        self.assertIn(f"Calibration material (in memory only): {name}", self.text(application))


# ----------------------------------------------------------------------------- release gate 11-14, 18

class ReleaseGateTests(_Fixture):
    def test_11_refused_gives_no_fragment(self):
        readiness = self.readiness(self.imprecise)
        self.assertEqual(readiness.status.value, "REFUSED")
        preview = calibration_material_preview(readiness, {"A": self.source(self.imprecise)})
        self.assertIs(preview.state, PreviewState.NOT_AVAILABLE_FOR_SELECTION)
        self.assertEqual((preview.constants, preview.fragment), ((), None))
        application, _ = self.evaluated(self.imprecise)
        self.assertEqual(application.scientific_readiness_record["status"], "REFUSED")
        self.assert_hidden(application)
        self.assertIn("backend status REFUSED", self.text(application))

    def test_12_not_ready_gives_no_fragment(self):
        root = self.copy_run(self.base)
        for pipeline in root.glob("specimens/*/*/*/journal.json"):
            pipeline.unlink()
        application, _ = self.evaluated(root=root)
        self.assertEqual(application.scientific_readiness_record["status"], "NOT_READY")
        self.assert_hidden(application)
        self.assertIn("backend status NOT_READY", self.text(application))

    def test_13_material_identification_never_becomes_a_calibration(self):
        from test_v12_i6_backend_integration import MaterialPathTests

        material = MaterialPathTests.material_run(self, (0.02, 1.0))
        readiness = judge_campaign_run(material.definition, material.specimens, material.evidence)
        self.assertEqual(readiness.status.value, "MATERIAL_VALUES_RELEASED")
        preview = calibration_material_preview(readiness, dict(material.evidence.source_inps))
        self.assertIs(preview.state, PreviewState.NOT_AVAILABLE_FOR_SELECTION)
        self.assertIn("never turned into a specimen calibration", preview.reason)
        self.assertEqual((preview.constants, preview.fragment), ((), None))
        forced = dataclasses.replace(readiness, status=type(readiness.status).RELEASED)  # no calibration record
        self.assertIs(calibration_material_preview(forced, {}).state, PreviewState.NOT_AVAILABLE_FOR_SELECTION)
        application = self.application(readiness.to_dict())
        self.assert_hidden(application)

    def test_14_cluster_refuses(self):
        from test_v12_i6_backend_integration import ClusterReadinessTests

        readiness = ClusterReadinessTests(
            "test_a_confirmed_cluster_is_a_readiness_refusal_without_member_matching").journal_declared_cluster()
        self.assertIn("CLUSTER_MEMBER_EVIDENCE_NOT_AVAILABLE", readiness.refusal_codes)
        preview = calibration_material_preview(readiness, {"A": self.source()})
        self.assertIs(preview.state, PreviewState.NOT_AVAILABLE_FOR_SELECTION)
        self.assertEqual((preview.constants, preview.fragment), ((), None))

    def test_18_synthetic_release_is_labelled_non_production(self):
        application, _ = self.evaluated()
        text = self.text(application)
        for label in ("SPECIMEN_ENGINEERING_CALIBRATION", "NOT_A_MATERIAL_PROPERTY",
                      "NOT_TRANSFERABLE_WITHOUT_VALIDATION", "NOT AUTHORISED FOR PRODUCTION",
                      "SYNTHETIC / TEST EVIDENCE"):
            self.assertIn(label, text)
        self.assertIn("Solver profiles: A: SYA/fake.", text)
        self.assertIn("never an accepted physical calibration", text)
        self.assertIn("NO_HUMAN_AUTHORISED_PRODUCTION_CALIBRATION_RUN", text)
        self.assertIn("Production execution: NOT_AUTHORISED", text)
        self.assertNotIn("accepted physical evidence", text)
        fragment = "\n".join(row[0] for row in self.rows(application.material_calibration_fragment_table))
        for label in ("SPECIMEN_ENGINEERING_CALIBRATION", "NOT_A_MATERIAL_PROPERTY",
                      "NOT_TRANSFERABLE_WITHOUT_VALIDATION"):
            self.assertIn(f"** {label}", fragment)


# ----------------------------------------------------------------------------- selection / freshness 15-17, 19

class FreshnessTests(_Fixture):
    def test_15_selection_switch_hides_the_preview(self):
        import material_identification_ui as ui

        application, _ = self.evaluated()
        self.assert_available(application)
        self.gui(ui.select_auto_id_run, application, self.base, str(_journal(self.copy_run(self.base))))
        self.assert_hidden(application)
        application, _ = self.evaluated()
        ui.load_auto_id_source(application, "family", str(RUN_A))
        self.assert_hidden(application)
        application, _ = self.evaluated()
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.assert_hidden(application)  # the same campaign hash alone is not the active evaluation
        application, _ = self.evaluated()
        application.auto_id_preparation = None  # the selection no longer matches, even with the run state intact
        application._refresh_material_identification_pages()
        self.assert_hidden(application)

    def test_16_evidence_modification_hides_the_preview(self):
        import material_identification_ui as ui

        application, root = self.evaluated()
        self.gui(ui.refresh_auto_id_progress, application, self.base)  # unchanged: still current
        self.assert_available(application)
        pipeline = next(root.glob("specimens/*/*/*/journal.json"))
        document = json.loads(pipeline.read_text(encoding="utf-8"))
        pipeline.write_text(json.dumps(rechain(dict(document, entries=document["entries"]
                                                     + [copy.deepcopy(document["entries"][-1])]))), encoding="utf-8")
        self.gui(ui.refresh_auto_id_progress, application, self.base)
        self.assert_hidden(application)
        self.assertIsNone(application.auto_id_active_typed)

    def test_17_reopen_hides_the_preview(self):
        import material_identification_ui as ui

        application, _ = self.evaluated()
        self.assert_available(application)
        self.gui(ui.reopen_auto_id_run, application, self.base)
        self.assert_hidden(application)
        self.gui(ui.evaluate_auto_id_run, application, self.base)  # a new evaluation is current again
        self.assert_available(application)

    def test_19_fake_gui_harness_requires_the_typed_active_evaluation(self):
        import material_identification_ui as ui

        record = self.readiness().to_dict()
        application = self.application(record)  # external display-only RELEASED record
        self.assertIn("Backend status: RELEASED",
                      application.material_scientific_readiness_summary_label.kwargs["text"])
        self.assert_hidden(application)
        ui.load_auto_id_source(application, "family", str(self.definition_file(self.base.definition)))
        self.assertIn("Backend status: RELEASED",
                      application.material_scientific_readiness_summary_label.kwargs["text"])
        self.assert_hidden(application)  # matched campaign hash, but no typed evaluation
        application, _ = self.evaluated()
        self.assert_available(application)
        active, evaluation = application.auto_id_active_typed
        copied = tuple(list(active))  # an equal tuple that is not the active evaluation object
        self.assertIsNot(copied, active)
        application.auto_id_active_typed = (copied, evaluation)
        application._refresh_material_identification_pages()
        self.assert_hidden(application)
        application.auto_id_active_typed = (active, evaluation)
        application.scientific_readiness_record["status"] = "RELEASED "  # the display dict no longer the typed one
        application._refresh_material_identification_pages()
        self.assertNotIn("PREVIEW_AVAILABLE", self.text(application))
        self.assertEqual(self.rows(application.material_calibration_fragment_table), [])


# ----------------------------------------------------------------------------- real Tk 20, safety 21

class RealTkPreviewTests(_Fixture):
    def test_20_real_gui_preview_follows_the_selection(self):
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
        self.assertIn("PREVIEW_AVAILABLE", application.material_calibration_preview_label.cget("text"))
        table = application.material_calibration_constants_table
        self.assertEqual([table.item(k, "values")[0] for k in table.get_children()], list(ORDER))
        self.assertGreater(len(application.material_calibration_fragment_table.get_children()), 20)
        ui.load_auto_id_source(application, "family", str(RUN_A))
        root.update_idletasks()
        self.assertIn(NOT_AVAILABLE, application.material_calibration_preview_label.cget("text"))
        self.assertEqual(application.material_calibration_constants_table.get_children(), ())
        self.assertEqual(application.material_calibration_fragment_table.get_children(), ())


class SafetyTests(_Fixture):
    def test_21_no_abaqus_subprocess_or_file_writes(self):
        import material_identification_ui as ui
        from services import identification_campaign_run as campaign_module
        from services import identification_step, shape_extraction

        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        root = self.copy_run(self.base)
        stores = (self.store, ROOT / "docs" / "auto_id", root)
        before = [_tree(path) for path in stores]
        source = self.store / "models" / "SYA.inp"
        source_bytes = source.read_bytes()
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse), \
                mock.patch.object(campaign_module, "prepare_run_manifest", refuse), \
                mock.patch.object(campaign_module, "extract_archived_odbs", refuse), \
                mock.patch.object(shape_extraction, "extract_shape_pack", refuse), \
                mock.patch.object(CampaignRun, "__init__", refuse), mock.patch.object(CampaignRun, "run", refuse):
            application, _ = self.evaluated(root=root)
            with mock.patch.object(Path, "write_text", refuse), mock.patch.object(Path, "write_bytes", refuse), \
                    mock.patch.object(Path, "open", refuse):
                view = ui.calibration_preview_view(application)
                application._refresh_material_identification_pages()
        refuse.assert_not_called()
        self.assertEqual(view["state"], "PREVIEW_AVAILABLE")
        self.assertEqual([_tree(path) for path in stores], before)
        self.assertEqual(source.read_bytes(), source_bytes)
        text = (ROOT / "src" / "services" / "calibration_material_preview.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "write_text", "write_bytes", "open(", "os.system", "require_executable",
                          "judge_campaign_run", "render_calibration_inp_fragment", "governed_engineering_constants",
                          "tau_mf", "SPECIMEN_ENGINEERING_CALIBRATION"):
            self.assertNotIn(forbidden, text)
        gui = (ROOT / "src" / "material_identification_ui.py").read_text(encoding="utf-8")
        for forbidden in ("released_inp_fragment", "released_engineering_constants", "render_calibration_inp_fragment",
                          "ScientificReadiness("):
            self.assertNotIn(forbidden, gui)


if __name__ == "__main__":
    unittest.main()

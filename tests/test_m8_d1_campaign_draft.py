"""M8-D1 — Create Campaign Draft in the Auto-ID Setup page (preparation only; no run, no authorisation).

The draft collects governed specimen inputs and the explicit scientific question and τ_mf, lists every missing
required campaign input and previews the intended v1.2 definition. It is a separate document (never a campaign
definition), validated only by the campaign-definition domain rules, and written only on an explicit Save As outside
the protected folders. Nothing here runs Abaqus, FE or LM.
"""

from __future__ import annotations

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
    CampaignDefinitionError,
    load_campaign_definition,
    parse_campaign_definition,
    require_specimen_count,
)
from domain.identification_run import canonical_hash  # noqa: E402
from services.auto_id_wizard import load_fixtures  # noqa: E402
from services.campaign_draft import (  # noqa: E402
    DRAFT_SCHEMA,
    CampaignDraft,
    CampaignDraftError,
    DraftIncomplete,
    check_draft_destination,
    governed_specimen_input,
    write_draft,
)

FORWARD = ROOT / "docs" / "auto_id" / "forward_models"
CAMPAIGNS = ROOT / "docs" / "auto_id" / "campaigns"
MATERIAL, CALIBRATION = "MATERIAL_IDENTIFICATION", "SPECIMEN_ENGINEERING_CALIBRATION"
HISTORICAL_FILES = {  # canonical content hashes (unchanged since M7 / V12-I7)
    "M7_RUN_A.campaign.json": "0a21ad0567901034b521b822b52f0c29944e96394f3692e1a8ebcd7ccd8d2ccf",
    "M7_RUN_A.result.json": "82501b35c4effc0fd829d40d6e3aaef105d5a70cc8e8a3b0ba306b9caa66c5c2",
    "M7_RUN_B.campaign.json": "7c1f5db24fa9c4f4e90c82ca802c6dae22cbe5c7ec9e2989e63e439f678540e5",
    "M7_RUN_B.result.json": "8a9264eca72827889042fb5430ed057f9d44ebb9305d0b10db9c28d433a2b2de",
}
CAMPAIGN_HASHES = {"M7_RUN_A": "0a21ad0567901034b521b822b52f0c29944e96394f3692e1a8ebcd7ccd8d2ccf",
                   "M7_RUN_B": "7c1f5db24fa9c4f4e90c82ca802c6dae22cbe5c7ec9e2989e63e439f678540e5"}
DRAFT_BUTTONS = ("Create Campaign Draft...", "Add governed specimen input...", "Remove all specimens",
                 "Discard draft", "Question: MATERIAL_IDENTIFICATION", "Question: SPECIMEN_ENGINEERING_CALIBRATION",
                 "Declare τ_mf...", "Save Campaign Draft As...")


def _tree(path: Path) -> list[tuple[str, int]]:
    return sorted((p.relative_to(path).as_posix(), p.stat().st_size) for p in Path(path).rglob("*") if p.is_file())


class _Draft(unittest.TestCase):
    fixtures = None

    @classmethod
    def setUpClass(cls):
        cls.fixtures = load_fixtures(ROOT)

    def specimen(self, name):
        return governed_specimen_input(FORWARD / name, ROOT, self.fixtures)

    def physical_pair(self):
        return (CampaignDraft().with_specimen(self.specimen("SP02.physical.forward.json"))
                .with_specimen(self.specimen("SP13.physical.forward.json")))

    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix="m8_d1_out_"))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)


# ----------------------------------------------------------------------------- 1 governed input preparation

class GovernedInputTests(_Draft):
    def test_governed_specimen_inputs_are_shown_as_recorded(self):
        sp02, sp13 = self.specimen("SP02.physical.forward.json"), self.specimen("SP13.physical.forward.json")
        self.assertEqual((sp02.label, sp02.fixture_id, sp02.physical_specimen_id, sp02.registration_basis),
                         ("SP02", "SP02/bravo-1-physical", "SP-02", "PHYSICAL"))
        self.assertEqual((sp13.label, sp13.fixture_id, sp13.physical_specimen_id, sp13.registration_basis),
                         ("SP13", "SP13/best-physical", "SP-13", "PHYSICAL"))
        self.assertEqual(sp02.forward_model, "docs/auto_id/forward_models/SP02.physical.forward.json")
        self.assertEqual(sp02.passport, "docs/auto_id/specimens/SP02.physical.specimen.json")
        legacy = self.specimen("SP02.forward.json")  # the historical chain is shown as recorded, never relabelled
        self.assertEqual((legacy.fixture_id, legacy.registration_basis), ("SP02/bravo-1", "LEGACY_REPLAY"))

    def test_intended_definition_matches_the_governed_run_a_identities(self):
        draft = self.physical_pair().with_question(MATERIAL).with_tau_mf("0.02")
        intended = draft.intended_definition()
        run_a = json.loads((CAMPAIGNS / "M7_RUN_A.campaign.json").read_text(encoding="utf-8"))
        self.assertEqual(intended["specimens"], [{k: s[k] for k in ("label", "fixture_id", "forward_model")}
                                                for s in run_a["specimens"]])
        self.assertEqual(intended["schema"], "auto-id/identification-campaign/v1.2")
        self.assertNotIn("rows", json.dumps(intended))  # no pairing or FIT / HOLDOUT is chosen
        # the preview's own fields are accepted by the governed parser once the remaining inputs are declared
        completed = {**{k: v for k, v in run_a.items() if k not in intended}, **intended,
                     "specimens": [{**s, **i} for s, i in zip(run_a["specimens"], intended["specimens"])]}
        definition = parse_campaign_definition(completed)
        self.assertEqual((definition.scientific_question, definition.tau_mf), (MATERIAL, 0.02))
        self.assertEqual([s.fixture_id for s in definition.specimens], ["SP02/bravo-1-physical", "SP13/best-physical"])

    def test_non_governed_inputs_are_refused(self):
        outside = self.out / "SP02.physical.forward.json"
        shutil.copy(FORWARD / "SP02.physical.forward.json", outside)
        for path, text in ((outside, "not inside the repository"),
                           (CAMPAIGNS / "M7_RUN_A.campaign.json", "docs/auto_id/forward_models/ only"),
                           (FORWARD / "missing.forward.json", "refused by the governed forward-model binder")):
            with self.subTest(path=path.name), self.assertRaises(CampaignDraftError) as caught:
                governed_specimen_input(path, ROOT, self.fixtures)
            self.assertIn(text, str(caught.exception))
        draft = CampaignDraft().with_specimen(self.specimen("SP02.physical.forward.json"))
        with self.assertRaises(CampaignDraftError):  # the same input twice
            draft.with_specimen(self.specimen("SP02.physical.forward.json"))


    def test_only_the_governed_forward_model_directory_is_accepted(self):
        # PR #67 review 3: a *.forward.json elsewhere in the repository is never a governed specimen input
        source = (FORWARD / "SP02.physical.forward.json").read_bytes()
        repo = self.out / "repo"
        for relative in ("docs/auto_id/campaigns/SP02.physical.forward.json", "docs/auto_id/SP02.physical.forward.json",
                         "SP02.physical.forward.json", "docs/auto_id/forward_models/old/SP02.physical.forward.json"):
            path = repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(source)
            with self.subTest(path=relative), self.assertRaises(CampaignDraftError) as caught:
                governed_specimen_input(path, repo, self.fixtures)
            self.assertIn("docs/auto_id/forward_models/ only", str(caught.exception))
        inside = repo / "docs" / "auto_id" / "forward_models" / "SP02.physical.forward.json"
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.write_bytes(source)
        with self.assertRaises(CampaignDraftError) as caught:  # the location passes; the binder still decides
            governed_specimen_input(inside, repo, self.fixtures)
        self.assertIn("refused by the governed forward-model binder", str(caught.exception))

    def test_fixture_catalogue_is_required(self):
        # PR #67 review 1: fail-closed; never bound without the validated governed fixture catalogue
        with self.assertRaises(CampaignDraftError) as caught:
            governed_specimen_input(FORWARD / "SP02.physical.forward.json", ROOT, None)
        self.assertIn("experiment-fixture catalogue", str(caught.exception))


# ----------------------------------------------------------------------------- 2 missing input refusal

class MissingInputTests(_Draft):
    def test_an_empty_draft_lists_every_gap_and_cannot_be_finalised(self):
        gaps = {g.field: g.reason for g in CampaignDraft().gaps()}
        for field in ("scientific_question", "tau_mf", "specimens", "run_type", "fitted_parameters", "sigma", "lm",
                      "abaqus_solve_budget", "decision", "archive_reuse", "run_b_gate", "provenance", "campaign_id"):
            self.assertIn(field, gaps)
        with self.assertRaises(DraftIncomplete) as caught:
            CampaignDraft().finalise()
        self.assertEqual(len(caught.exception.gaps), len(gaps))

    def test_specimen_rows_and_evidence_are_never_chosen(self):
        gaps = {g.field for g in self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02).gaps()}
        for index in (0, 1):
            for key in ("rows", "registration_evidence", "solver_profile", "baseline_shape_pack", "archived_baseline"):
                self.assertIn(f"specimens[{index}].{key}", gaps)
        self.assertNotIn("specimens", gaps)  # two specimens satisfy the material-identification count

    def test_specimen_count_follows_the_domain_rule(self):
        one = CampaignDraft().with_specimen(self.specimen("SP13.physical.forward.json"))
        for draft, question in ((one, MATERIAL), (self.physical_pair(), CALIBRATION)):
            with self.subTest(question=question):
                count_gap = {g.field: g.reason for g in draft.with_question(question).gaps()}["specimens"]
                with self.assertRaises(CampaignDefinitionError) as caught:
                    require_specimen_count(question, len(draft.specimens))
                self.assertEqual(count_gap, str(caught.exception))
        self.assertNotIn("specimens", {g.field for g in one.with_question(CALIBRATION).gaps()})
        no_question = {g.field: g.reason for g in one.gaps()}
        self.assertIn("follows the declared question", no_question["specimens"])

    def test_duplicate_specimen_identity_is_never_a_valid_selection(self):
        # PR #67 review 2: SP02.forward.json and SP02.physical.forward.json are different files with one label SP02
        from domain.campaign_definition import require_unique_specimens

        draft = (CampaignDraft().with_specimen(self.specimen("SP02.forward.json"))
                 .with_specimen(self.specimen("SP02.physical.forward.json")).with_question(MATERIAL).with_tau_mf(0.02))
        self.assertEqual([s.label for s in draft.specimens], ["SP02", "SP02"])
        gaps = [g.reason for g in draft.gaps() if g.field == "specimens"]
        with self.assertRaises(CampaignDefinitionError) as caught:
            require_unique_specimens(["SP02", "SP02"], [s.fixture_id for s in draft.specimens])
        self.assertEqual(gaps, [f"{caught.exception} (SP02, SP02)"])
        with self.assertRaises(DraftIncomplete):
            draft.finalise()
        run_a = json.loads((CAMPAIGNS / "M7_RUN_A.campaign.json").read_text(encoding="utf-8"))
        twins = [dict(s, label="SP02") for s in run_a["specimens"]]
        with self.assertRaises(CampaignDefinitionError) as parsed:  # the same production rule in the parser
            parse_campaign_definition(dict(run_a, specimens=twins))
        self.assertEqual(str(parsed.exception), str(caught.exception))
        self.assertNotIn("specimens", {g.field for g in self.physical_pair().with_question(MATERIAL).gaps()})

    def test_the_domain_rule_is_unchanged_inside_the_parser(self):
        run_a = json.loads((CAMPAIGNS / "M7_RUN_A.campaign.json").read_text(encoding="utf-8"))
        for specimens in (run_a["specimens"][:1], "not a list"):
            with self.subTest(specimens=str(specimens)[:20]), self.assertRaises(CampaignDefinitionError) as caught:
                parse_campaign_definition(dict(run_a, specimens=specimens))
            self.assertEqual(str(caught.exception), "specimens: a campaign needs at least two specimens.")


# ----------------------------------------------------------------------------- 3 question and τ_mf

class DeclarationTests(_Draft):
    def test_nothing_is_preselected(self):
        draft = CampaignDraft()
        self.assertIsNone(draft.scientific_question)
        self.assertIsNone(draft.tau_mf)
        self.assertEqual(set(draft.intended_definition()), {"schema", "specimens"})

    def test_question_and_tau_mf_use_the_domain_validation(self):
        draft = self.physical_pair()
        self.assertEqual(draft.with_question(CALIBRATION).scientific_question, CALIBRATION)
        for value, expected in (("0.02", 0.02), (0.005, 0.005), (" 0.01 ", 0.01)):
            self.assertEqual(draft.with_tau_mf(value).tau_mf, expected)
        for bad in ("SOMETHING_ELSE", None, "material_identification"):
            with self.subTest(question=bad), self.assertRaises(CampaignDraftError) as caught:
                draft.with_question(bad)
            self.assertIn("scientific_question", str(caught.exception))
        for bad in ("0.05", 0.0, -0.01, "abc", True, float("nan"), "", None):
            with self.subTest(tau=bad), self.assertRaises(CampaignDraftError) as caught:
                draft.with_tau_mf(bad)
            self.assertIn("tau_mf", str(caught.exception))
        switched = draft.with_question(MATERIAL).with_question(CALIBRATION)
        self.assertEqual(switched.specimens, draft.specimens)  # a question change never touches the specimens


# ----------------------------------------------------------------------------- 4 save / cancel, 5 protected writes

class SaveTests(_Draft):
    def test_draft_document_is_deterministic_and_never_a_campaign_definition(self):
        draft = self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02)
        first = write_draft(draft, self.out / "draft.json", (ROOT,))
        data = first.read_bytes()
        self.assertEqual(write_draft(draft, self.out / "draft.json", (ROOT,)).read_bytes(), data)  # earlier draft
        document = json.loads(data)
        self.assertEqual(document["schema"], DRAFT_SCHEMA)
        self.assertEqual(document["status"], "INCOMPLETE")
        self.assertIn("DRAFT_NOT_A_CAMPAIGN_DEFINITION", document["labels"])
        self.assertEqual(document["production_calibration_execution"], "BLOCKED / NOT_AUTHORISED")
        self.assertTrue(document["missing_required_inputs"])
        for volatile in ("timestamp", "created_at", "uuid"):
            self.assertNotIn(volatile, data.decode("utf-8").lower())
        with self.assertRaises(CampaignDefinitionError):  # a saved draft is never loaded as a campaign
            load_campaign_definition(first)
        self.assertEqual([p.name for p in self.out.iterdir()], ["draft.json"])  # no temporary file is left

    def test_protected_and_unsafe_destinations_are_refused(self):
        draft = CampaignDraft()
        other = self.out / "other.json"
        other.write_text('{"schema": "something-else"}', encoding="utf-8")
        store = self.out / "store"
        store.mkdir()
        cases = ((ROOT / "docs" / "auto_id" / "draft.json", (ROOT,), "protected"),
                 (store / "draft.json", (ROOT, store), "protected"),
                 (self.out / "new.campaign.json", (ROOT,), "campaign-definition name"),
                 (self.out / "draft.txt", (ROOT,), ".json"),
                 (other, (ROOT,), "never overwritten"),
                 (self.out / "absent" / "draft.json", (ROOT,), "does not exist"),
                 (self.out / "draft.json", (ROOT, None), "could not be determined"),
                 ("", (ROOT,), "no destination"))
        for destination, roots, text in cases:
            with self.subTest(destination=str(destination)), self.assertRaises(CampaignDraftError) as caught:
                write_draft(draft, destination, roots)
            self.assertIn(text, str(caught.exception))
        self.assertEqual(json.loads(other.read_text(encoding="utf-8")), {"schema": "something-else"})
        self.assertEqual(sorted(p.name for p in self.out.iterdir()), ["other.json", "store"])
        self.assertEqual(check_draft_destination(self.out / "ok.json", (ROOT,)), (self.out / "ok.json").resolve())

    def test_failed_write_leaves_nothing(self):
        with mock.patch("services.campaign_draft.os.replace", side_effect=OSError("disk full")), \
                self.assertRaises(CampaignDraftError):
            write_draft(CampaignDraft(), self.out / "draft.json", (ROOT,))
        self.assertEqual(list(self.out.iterdir()), [])


# ----------------------------------------------------------------------------- GUI (fake harness and real Tk)

class GuiTests(_Draft):
    def application(self):
        from test_material_identification_ui import _ApplicationHarness

        application = _ApplicationHarness()._application()
        application._refresh_material_identification_pages()
        return application

    @staticmethod
    def buttons(application):
        found = {}

        def collect(widget):
            if "command" in widget.kwargs and widget.kwargs.get("text"):
                found[widget.kwargs["text"]] = widget.kwargs["command"]
            for child in widget.children:
                collect(child)

        collect(application.material_identification_pages["0. Auto-ID Setup"])
        return found

    def test_fake_gui_draft_workflow_save_and_cancel(self):
        import material_identification_ui as ui

        application = self.application()
        buttons = self.buttons(application)
        for label in DRAFT_BUTTONS:
            self.assertIn(label, buttons)
        self.assertEqual(application.material_auto_id_draft_label.kwargs["text"], ui.AUTO_ID_NO_DRAFT)
        buttons["Question: MATERIAL_IDENTIFICATION"]()  # nothing to change without a draft
        self.assertIn("Create Campaign Draft... first", application.material_auto_id_draft_label.kwargs["text"])
        buttons["Create Campaign Draft..."]()
        for name in ("SP02.physical.forward.json", "SP13.physical.forward.json"):
            with mock.patch.object(ui.filedialog, "askopenfilename", return_value=str(FORWARD / name)):
                buttons["Add governed specimen input..."]()
        before = application.auto_id_draft
        with mock.patch("services.auto_id_wizard.load_fixtures", side_effect=OSError("catalogue unreadable")),                 mock.patch.object(ui.filedialog, "askopenfilename",
                                  return_value=str(FORWARD / "SP02.forward.json")):
            buttons["Add governed specimen input..."]()  # PR #67 review 1: refused, never bound without fixtures
        self.assertIs(application.auto_id_draft, before)
        self.assertIn("fixture catalogue could not be loaded", application.material_auto_id_draft_label.kwargs["text"])
        buttons["Question: MATERIAL_IDENTIFICATION"]()
        with mock.patch.object(ui.simpledialog, "askstring", return_value="0.5"):  # refused, draft unchanged
            buttons["Declare τ_mf..."]()
        self.assertIn("Not changed", application.material_auto_id_draft_label.kwargs["text"])
        with mock.patch.object(ui.simpledialog, "askstring", return_value="0.02"):
            buttons["Declare τ_mf..."]()
        rows = list(application.material_auto_id_draft_table.items.values())
        self.assertIn(("Declared", "Scientific question", MATERIAL, "PRESENT"), rows)
        self.assertIn(("Declared", "τ_mf", "0.02", "PRESENT"), rows)
        self.assertEqual([r[1] for r in rows if r[0] == "Specimens"], ["SP02", "SP13"])
        self.assertIn(("Missing required inputs", "specimens[0].rows"), [r[:2] for r in rows])
        self.assertTrue(application.material_auto_id_draft_finalisation_label.kwargs["text"].startswith(
            "Finalisation refused"))
        preview = json.loads(application.material_auto_id_draft_preview_label.kwargs["text"])
        self.assertEqual(preview["scientific_question"], MATERIAL)
        with mock.patch.object(ui.filedialog, "asksaveasfilename", return_value=""):  # cancelled
            buttons["Save Campaign Draft As..."]()
        self.assertEqual(list(self.out.iterdir()), [])
        self.assertIn("Save cancelled", application.material_auto_id_draft_label.kwargs["text"])
        target = self.out / "draft.json"
        with mock.patch.object(ui.filedialog, "asksaveasfilename", return_value=str(target)):
            buttons["Save Campaign Draft As..."]()
        self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["schema"], DRAFT_SCHEMA)
        self.assertIn("not a campaign definition", application.material_auto_id_draft_label.kwargs["text"])
        with mock.patch.object(ui.filedialog, "asksaveasfilename",
                               return_value=str(ROOT / "docs" / "auto_id" / "draft.json")):
            buttons["Save Campaign Draft As..."]()  # repository: refused
        self.assertIn("Not saved", application.material_auto_id_draft_label.kwargs["text"])
        self.assertFalse((ROOT / "docs" / "auto_id" / "draft.json").exists())
        buttons["Discard draft"]()
        self.assertIsNone(application.auto_id_draft)
        self.assertEqual(application.material_auto_id_draft_table.items, {})
        self.assertIsNone(getattr(application, "auto_id_preparation", None))  # the selection is untouched

    def test_real_tk_draft(self):
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
        ui.create_campaign_draft(application)
        ui.add_draft_specimen(application, FORWARD / "SP13.physical.forward.json")
        ui.declare_draft_question(application, CALIBRATION)
        ui.declare_draft_tolerance(application, "0.02")
        root.update_idletasks()
        table = application.material_auto_id_draft_table
        items = [tuple(table.item(k, "values")) for k in table.get_children()]
        self.assertIn(("Declared", "Scientific question", CALIBRATION, "PRESENT"), items)
        self.assertNotIn("specimens", [str(i[1]) for i in items])  # exactly one specimen for a calibration
        path = ui.save_campaign_draft(application, self.out / "tk.json")
        self.assertIsNotNone(path)
        self.assertEqual(json.loads(Path(path).read_text(encoding="utf-8"))["declared"]["scientific_question"],
                         CALIBRATION)


# ----------------------------------------------------------------------------- 6 safety and historical records

class SafetyTests(_Draft):
    def test_no_run_no_solver_no_protected_writes(self):
        import material_identification_ui as ui
        from services import identification_step

        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        watched = (ROOT / "docs", ROOT / "src")
        before = [_tree(path) for path in watched]
        application = GuiTests.application(self)
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse):
            ui.create_campaign_draft(application)
            ui.add_draft_specimen(application, FORWARD / "SP02.physical.forward.json")
            ui.add_draft_specimen(application, FORWARD / "SP13.physical.forward.json")
            ui.declare_draft_question(application, MATERIAL)
            ui.declare_draft_tolerance(application, "0.01")
            ui.save_campaign_draft(application, self.out / "draft.json")
            ui.save_campaign_draft(application, ROOT / "docs" / "auto_id" / "campaigns" / "draft.json")
        refuse.assert_not_called()
        self.assertEqual([_tree(path) for path in watched], before)
        source = (ROOT / "src" / "services" / "campaign_draft.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "require_executable", "run_bounded_lm", "CampaignRun", "judge_campaign_run",
                          "datetime", "time.time", "import uuid", "import random"):
            self.assertNotIn(forbidden, source)

    def test_historical_m7_records_unchanged(self):
        for name, expected in HISTORICAL_FILES.items():
            with self.subTest(record=name):
                self.assertEqual(canonical_hash(json.loads((CAMPAIGNS / name).read_text(encoding="utf-8"))), expected)
        for name, expected in CAMPAIGN_HASHES.items():
            with self.subTest(campaign=name):
                self.assertEqual(load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json").campaign_hash, expected)


if __name__ == "__main__":
    unittest.main()

"""M8-D2a — Reopen a saved campaign draft in the Auto-ID Setup GUI.

Only ``auto-id/campaign-draft/v1`` documents are opened. The draft is rebuilt from its explicit declarations (domain
validation) and its specimen selections (the governed binder against the current records); any stored identity or
pinned hash that differs, any missing or invalid reference and any conflicting preview is refused and never
substituted. The stored status, missing inputs and preview are recomputed, never trusted. On cancel or refusal the
current draft is unchanged. Nothing here runs Abaqus, FE or LM.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from services.campaign_draft import (  # noqa: E402
    DRAFT_SCHEMA,
    CampaignDraft,
    CampaignDraftError,
    draft_from_document,
    load_draft,
    write_draft,
)
import test_m8_d1_campaign_draft as d1  # noqa: E402

FORWARD, CAMPAIGNS = d1.FORWARD, d1.CAMPAIGNS
MATERIAL, CALIBRATION = d1.MATERIAL, d1.CALIBRATION


class _Reopen(d1._Draft):
    def saved(self, draft=None, name="draft.json") -> Path:
        draft = draft or self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02)
        return write_draft(draft, self.out / name, (ROOT,))

    def document(self, path=None) -> dict:
        return json.loads((path or self.saved()).read_text(encoding="utf-8"))

    def refused(self, document, text):
        with self.assertRaises(CampaignDraftError) as caught:
            draft_from_document(document, ROOT, self.fixtures)
        self.assertIn(text, str(caught.exception))
        return caught.exception


# ----------------------------------------------------------------------------- save, reopen, save again

class RoundTripTests(_Reopen):
    def test_save_reopen_and_save_again(self):
        original = self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02)
        path = self.saved(original)
        reopened = load_draft(path, ROOT, self.fixtures)
        self.assertEqual(reopened, original)
        self.assertEqual(reopened.document_bytes(), path.read_bytes())  # deterministic round trip
        changed = (reopened.without_specimens().with_specimen(self.specimen("SP13.physical.forward.json"))
                   .with_question(CALIBRATION).with_tau_mf("0.01"))
        write_draft(changed, path, (ROOT,))  # an earlier draft may be replaced
        again = load_draft(path, ROOT, self.fixtures)
        self.assertEqual(again, changed)
        self.assertEqual([s.label for s in again.specimens], ["SP13"])
        self.assertEqual((again.scientific_question, again.tau_mf), (CALIBRATION, 0.01))

    def test_declarations_and_specimens_are_restored_exactly(self):
        for draft in (CampaignDraft(), CampaignDraft().with_question(CALIBRATION),
                      CampaignDraft().with_tau_mf(0.005),
                      self.physical_pair(), self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02)):
            with self.subTest(declared=(draft.scientific_question, draft.tau_mf, len(draft.specimens))):
                reopened = load_draft(self.saved(draft), ROOT, self.fixtures)
                self.assertEqual(reopened.scientific_question, draft.scientific_question)
                self.assertEqual(reopened.tau_mf, draft.tau_mf)
                self.assertEqual(reopened.specimens, draft.specimens)

    def test_stored_status_and_gaps_are_recomputed_never_trusted(self):
        document = self.document()
        document["status"] = "COMPLETE_NOT_FINALISED"
        document["missing_required_inputs"] = []
        draft = draft_from_document(document, ROOT, self.fixtures)
        self.assertTrue(draft.gaps())
        self.assertEqual(draft.document()["status"], "INCOMPLETE")


# ----------------------------------------------------------------------------- refusals

class RefusalTests(_Reopen):
    def test_only_the_draft_schema_is_opened(self):
        run_a = json.loads((CAMPAIGNS / "M7_RUN_A.campaign.json").read_text(encoding="utf-8"))
        self.refused(run_a, "only auto-id/campaign-draft/v1")
        for change, text in ((lambda d: d.update(schema="auto-id/campaign-draft/v5"), "only auto-id/campaign-draft/v1"),
                             (lambda d: d.update(extra=1), "unknown ['extra']"),
                             (lambda d: d.pop("declared"), "missing ['declared']"),
                             (lambda d: d.update(labels=["DRAFT_NOT_A_CAMPAIGN_DEFINITION"]), "labels"),
                             (lambda d: d.update(authorisation="AUTHORISED by D-999"), "authorisation"),
                             (lambda d: d.update(production_calibration_execution="AUTHORISED"), "production"),
                             (lambda d: d.update(kind="CAMPAIGN_DEFINITION"), "kind")):
            document = self.document()
            change(document)
            with self.subTest(text=text):
                self.refused(document, text)
        for value in ([], "text", None):
            with self.subTest(document=value):
                self.refused(value, "not a campaign draft")
        broken = self.out / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        with self.assertRaises(CampaignDraftError):
            load_draft(broken, ROOT, self.fixtures)

    def test_declarations_use_the_domain_validation(self):
        for declared, text in (({"scientific_question": "SOMETHING_ELSE", "tau_mf": 0.02}, "scientific_question"),
                               ({"scientific_question": MATERIAL, "tau_mf": 0.5}, "tau_mf"),
                               ({"scientific_question": MATERIAL, "tau_mf": "0.02"}, "tau_mf must be a number"),
                               ({"scientific_question": MATERIAL, "tau_mf": True}, "tau_mf"),
                               ({"scientific_question": MATERIAL}, "'declared' must state")):
            document = self.document()
            # a v2 draft also declares campaign_id / run_type, a v4 draft also not_fitted (null: not declared)
            unset = {"campaign_id": None, "run_type": None,
                     "not_fitted": {"t_face": None, "k_core": None, "k_int": None}}
            document["declared"] = dict(declared, **unset) if "tau_mf" in declared else declared
            with self.subTest(declared=declared):
                self.refused(document, text)

    def test_tampered_identities_and_hashes_are_refused(self):
        for field, value in (("forward_manifest_hash", "0" * 64), ("passport_manifest_hash", "1" * 64),
                             ("registration_hash", "2" * 64), ("fixture_id", "SP02/bravo-1"), ("label", "SP99"),
                             ("physical_specimen_id", "SP-13"), ("registration_basis", "LEGACY_REPLAY"),
                             ("forward_model_id", "other"), ("test_run_id", "other"),
                             ("passport", "docs/auto_id/specimens/SP02.specimen.json")):
            document = self.document()
            document["specimen_identities"][0][field] = value
            with self.subTest(field=field):
                error = self.refused(document, "differ(s) from the current governed records")
                self.assertIn(field, str(error))
        document = self.document()
        document["specimen_identities"][0].pop("registration_hash")
        self.refused(document, "malformed specimen identity")

    def test_a_conflicting_preview_is_refused(self):
        document = self.document()
        document["intended_campaign_definition"]["specimens"].reverse()
        self.refused(document, "conflicting draft")
        document = self.document()
        document["intended_campaign_definition"]["tau_mf"] = 0.01
        self.refused(document, "conflicting draft")

    def test_missing_or_ungoverned_sources_are_refused_never_substituted(self):
        for reference, text in (("docs/auto_id/forward_models/SP99.physical.forward.json", "refused by the governed"),
                                ("docs/auto_id/campaigns/M7_RUN_A.campaign.json", "forward_models/ only"),
                                ("../outside/SP02.physical.forward.json", "SP02.physical.forward.json"),
                                (str(FORWARD / "SP02.physical.forward.json"), "repository-relative POSIX path"),
                                ("docs\\auto_id\\forward_models\\SP02.physical.forward.json", "POSIX path")):
            document = self.document()
            document["specimen_identities"][0]["forward_model"] = reference
            with self.subTest(reference=reference):
                self.refused(document, text)
        document = self.document()  # the same selection twice is refused, as when adding it
        document["specimen_identities"][1] = copy.deepcopy(document["specimen_identities"][0])
        self.refused(document, "already in the draft")
        with self.assertRaises(CampaignDraftError) as caught:  # no fixture catalogue: refused, never unchecked
            draft_from_document(self.document(), ROOT, None)
        self.assertIn("experiment-fixture catalogue", str(caught.exception))


# ----------------------------------------------------------------------------- GUI

class GuiTests(_Reopen):
    def test_open_cancel_and_refusal_preserve_the_current_draft(self):
        import material_identification_ui as ui

        application = d1.GuiTests.application(self)
        buttons = d1.GuiTests.buttons(application)
        self.assertIn(ui.AUTO_ID_DRAFT_OPEN_LABEL, buttons)
        path = self.saved()
        ui.create_campaign_draft(application)
        ui.add_draft_specimen(application, FORWARD / "SP13.physical.forward.json")
        current = application.auto_id_draft
        with mock.patch.object(ui.filedialog, "askopenfilename", return_value=""):
            buttons[ui.AUTO_ID_DRAFT_OPEN_LABEL]()
        self.assertIs(application.auto_id_draft, current)
        self.assertIn("Open cancelled", application.material_auto_id_draft_label.kwargs["text"])
        tampered = self.document(path)
        tampered["specimen_identities"][0]["registration_hash"] = "3" * 64
        bad = self.out / "tampered.json"
        bad.write_text(json.dumps(tampered), encoding="utf-8")
        for refused in (bad, CAMPAIGNS / "M7_RUN_A.campaign.json"):
            with mock.patch.object(ui.filedialog, "askopenfilename", return_value=str(refused)):
                buttons[ui.AUTO_ID_DRAFT_OPEN_LABEL]()
            self.assertIs(application.auto_id_draft, current)
            self.assertIn("Not opened", application.material_auto_id_draft_label.kwargs["text"])
        with mock.patch("services.auto_id_wizard.load_fixtures", side_effect=OSError("catalogue unreadable")):
            ui.open_campaign_draft(application, path)  # fail-closed
        self.assertIs(application.auto_id_draft, current)
        with mock.patch.object(ui.filedialog, "askopenfilename", return_value=str(path)):
            buttons[ui.AUTO_ID_DRAFT_OPEN_LABEL]()
        self.assertIsNot(application.auto_id_draft, current)
        self.assertIn("Reopened", application.material_auto_id_draft_label.kwargs["text"])
        rows = list(application.material_auto_id_draft_table.items.values())
        self.assertIn(("Declared", "Scientific question", MATERIAL, "PRESENT"), rows)
        self.assertEqual([r[1] for r in rows if r[0] == "Specimens"], ["SP02", "SP13"])
        self.assertTrue(application.material_auto_id_draft_finalisation_label.kwargs["text"].startswith(
            "Finalisation refused"))
        self.assertEqual(json.loads(application.material_auto_id_draft_preview_label.kwargs["text"])["tau_mf"], 0.02)
        ui.declare_draft_question(application, CALIBRATION)  # modify the reopened draft and save it again
        again = ui.save_campaign_draft(application, path)
        self.assertEqual(json.loads(Path(again).read_text(encoding="utf-8"))["declared"]["scientific_question"],
                         CALIBRATION)

    def test_real_tk_reopen(self):
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
        ui.open_campaign_draft(application, self.saved())
        root.update_idletasks()
        table = application.material_auto_id_draft_table
        items = [tuple(str(v) for v in table.item(k, "values")) for k in table.get_children()]
        self.assertIn(("Declared", "Scientific question", MATERIAL, "PRESENT"), items)
        self.assertEqual([i[1] for i in items if i[0] == "Specimens"], ["SP02", "SP13"])


# ----------------------------------------------------------------------------- safety

class SafetyTests(_Reopen):
    def test_no_run_no_solver_no_protected_writes(self):
        import material_identification_ui as ui
        from services import identification_step

        path = self.saved()
        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        watched = (ROOT / "docs", ROOT / "src")
        before = [d1._tree(p) for p in watched]
        application = d1.GuiTests.application(self)
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse):
            ui.open_campaign_draft(application, path)
            ui.save_campaign_draft(application, path)
            ui.save_campaign_draft(application, ROOT / "docs" / "auto_id" / "draft.json")  # refused
        refuse.assert_not_called()
        self.assertEqual([d1._tree(p) for p in watched], before)
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema"], DRAFT_SCHEMA)
        source = (ROOT / "src" / "services" / "campaign_draft.py").read_text(encoding="utf-8")
        for forbidden in ("subprocess", "require_executable", "run_bounded_lm", "judge_campaign_run"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()

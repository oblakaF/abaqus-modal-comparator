"""M8-D2c — explicit campaign_id and run_type in the campaign draft (domain validation; no defaults; no authorisation).

Both fields are declared explicitly, validated by the production campaign-definition rules, shown in the draft table and
preview, persisted in the versioned draft format ``auto-id/campaign-draft/v2`` and restored on reopen. A ``v1`` draft
(which declares neither) still opens exactly as written. RUN_B grants no execution authorisation: its ``run_b_gate``
stays a missing, SUPERVISOR-gated input. Nothing here runs Abaqus, FE or LM.
"""

from __future__ import annotations

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

from domain.campaign_definition import (  # noqa: E402
    CampaignDefinitionError,
    RunGateRefusal,
    load_campaign_definition,
    parse_campaign_definition,
)
from services.campaign_draft import (  # noqa: E402
    DRAFT_SCHEMA,
    DRAFT_SCHEMA_V1,
    RUN_B_NOT_AUTHORISED,
    CampaignDraft,
    CampaignDraftError,
    DraftIncomplete,
    draft_from_document,
    load_draft,
    write_draft,
)
import test_m8_d1_campaign_draft as d1  # noqa: E402

FORWARD, CAMPAIGNS, MATERIAL = d1.FORWARD, d1.CAMPAIGNS, d1.MATERIAL
RUN_A_FILE = json.loads((CAMPAIGNS / "M7_RUN_A.campaign.json").read_text(encoding="utf-8"))


def domain_message(field, value):
    with unittest.TestCase().assertRaises(CampaignDefinitionError) as caught:
        parse_campaign_definition(dict(RUN_A_FILE, **{field: value}))
    return str(caught.exception)


class _Identity(d1._Draft):
    def full(self):
        return (self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02)
                .with_campaign_id("M8/D2c+draft_1.a-b").with_run_type("RUN_A"))


# ----------------------------------------------------------------------------- declarations

class DeclarationTests(_Identity):
    def test_valid_and_invalid_campaign_id_use_the_domain_rule(self):
        for value in ("M8/D2c+draft_1.a-b", "RUN_A_SP02", "x"):
            self.assertEqual(CampaignDraft().with_campaign_id(value).campaign_id, value)
        for value in ("", "   ", " lead", "trail ", "bad id", "-start", "é", "a\\b", None, 5, ["x"]):
            with self.subTest(value=value), self.assertRaises(CampaignDraftError) as caught:
                CampaignDraft().with_campaign_id(value)
            self.assertEqual(str(caught.exception), domain_message("campaign_id", value))

    def test_explicit_run_a_or_run_b_only(self):
        for value in ("RUN_A", "RUN_B"):
            self.assertEqual(CampaignDraft().with_run_type(value).run_type, value)
        for value in ("RUN_C", "run_a", "", None, ["RUN_A"], 1):
            with self.subTest(value=value), self.assertRaises(CampaignDraftError) as caught:
                CampaignDraft().with_run_type(value)
            self.assertEqual(str(caught.exception), domain_message("run_type", value))

    def test_no_defaults_and_gaps_recomputed(self):
        draft = self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02)
        self.assertIsNone(draft.campaign_id)
        self.assertIsNone(draft.run_type)
        self.assertNotIn("campaign_id", draft.intended_definition())
        self.assertNotIn("run_type", draft.intended_definition())
        before = {g.field for g in draft.gaps()}
        self.assertTrue({"campaign_id", "run_type"} <= before)
        after = {g.field for g in draft.with_campaign_id("X1").with_run_type("RUN_A").gaps()}
        self.assertEqual(before - after, {"campaign_id", "run_type"})  # nothing else is filled in
        intended = self.full().intended_definition()
        self.assertEqual((intended["campaign_id"], intended["run_type"]), ("M8/D2c+draft_1.a-b", "RUN_A"))
        for absent in ("fitted_parameters", "run_b_gate", "bounds", "sigma", "lm", "abaqus_solve_budget"):
            self.assertNotIn(absent, intended)

    def test_run_b_grants_no_authorisation(self):
        draft = self.full().with_run_type("RUN_B")
        gaps = {g.field: g.reason for g in draft.gaps()}
        self.assertEqual(gaps["run_b_gate"], RUN_B_NOT_AUTHORISED)
        self.assertNotIn("run_b_gate", draft.intended_definition())
        self.assertNotEqual({g.field: g.reason for g in self.full().gaps()}["run_b_gate"], RUN_B_NOT_AUTHORISED)
        with self.assertRaises(DraftIncomplete):
            draft.finalise()
        run_b = load_campaign_definition(CAMPAIGNS / "M7_RUN_B.campaign.json")  # the domain gate is unchanged
        ungated = parse_campaign_definition(dict(json.loads((CAMPAIGNS / "M7_RUN_B.campaign.json").read_text(
            encoding="utf-8")), run_b_gate=None))
        with self.assertRaises(RunGateRefusal):
            ungated.require_executable()
        self.assertEqual(run_b.campaign_hash, d1.CAMPAIGN_HASHES["M7_RUN_B"])


# ----------------------------------------------------------------------------- persistence and compatibility

class PersistenceTests(_Identity):
    def test_save_reopen_round_trip(self):
        draft = self.full()
        path = write_draft(draft, self.out / "draft.json", (ROOT,))
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], DRAFT_SCHEMA)
        self.assertEqual(document["schema"], "auto-id/campaign-draft/v5")  # M8 existing data: saved as v5; v2 still opens
        self.assertEqual(document["declared"]["campaign_id"], "M8/D2c+draft_1.a-b")
        self.assertEqual(document["declared"]["run_type"], "RUN_A")
        reopened = load_draft(path, ROOT, self.fixtures)
        self.assertEqual(reopened, draft)
        self.assertEqual(reopened.document_bytes(), path.read_bytes())
        changed = reopened.with_run_type("RUN_B").with_campaign_id("other")
        write_draft(changed, path, (ROOT,))
        self.assertEqual(load_draft(path, ROOT, self.fixtures), changed)

    def v1_document(self, draft):
        document = draft.document()
        document["schema"] = DRAFT_SCHEMA_V1
        document["declared"] = {k: document["declared"][k] for k in ("scientific_question", "tau_mf")}
        document.pop("specimen_records")  # M8-D2d: v1 / v2 drafts have no bound records
        document.pop("specimen_observations")  # v1 - v4 drafts bind no observations
        return document

    def test_v1_drafts_open_as_written(self):
        draft = self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02)
        path = self.out / "old.json"
        data = (json.dumps(self.v1_document(draft), indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
        path.write_bytes(data)
        reopened = load_draft(path, ROOT, self.fixtures)
        self.assertEqual(reopened, draft)
        self.assertIsNone(reopened.campaign_id)  # never inferred from a v1 file
        self.assertIsNone(reopened.run_type)
        self.assertEqual(path.read_bytes(), data)  # opening never rewrites the file
        write_draft(reopened.with_run_type("RUN_A"), path, (ROOT,))  # an explicit save writes v2
        self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema"], DRAFT_SCHEMA)

    def test_declared_keys_must_match_the_draft_version(self):
        v1 = self.v1_document(self.physical_pair())
        v1["declared"]["campaign_id"] = "X1"  # a v1 file cannot carry the v2 fields
        with self.assertRaises(CampaignDraftError) as caught:
            draft_from_document(v1, ROOT, self.fixtures)
        self.assertIn("auto-id/campaign-draft/v1", str(caught.exception))
        v2 = self.full().document()
        v2["declared"].pop("run_type")
        with self.assertRaises(CampaignDraftError):
            draft_from_document(v2, ROOT, self.fixtures)
        for field, value in (("campaign_id", "bad id"), ("run_type", "RUN_C")):
            document = self.full().document()
            document["declared"][field] = value
            document["intended_campaign_definition"][field] = value
            with self.subTest(field=field), self.assertRaises(CampaignDraftError) as caught:
                draft_from_document(document, ROOT, self.fixtures)
            self.assertEqual(str(caught.exception), domain_message(field, value))
        document = self.full().document()
        document["intended_campaign_definition"]["run_type"] = "RUN_B"  # preview conflicts with the declaration
        with self.assertRaises(CampaignDraftError) as caught:
            draft_from_document(document, ROOT, self.fixtures)
        self.assertIn("conflicting draft", str(caught.exception))


# ----------------------------------------------------------------------------- GUI

class GuiTests(_Identity):
    def test_declare_show_and_preserve_on_invalid_input(self):
        import material_identification_ui as ui

        application = d1.GuiTests.application(self)
        buttons = d1.GuiTests.buttons(application)
        for label in ("Declare campaign_id...", "Run type: RUN_A", "Run type: RUN_B"):
            self.assertIn(label, buttons)
        buttons["Run type: RUN_A"]()  # no draft yet
        self.assertIn("Create Campaign Draft... first", application.material_auto_id_draft_label.kwargs["text"])
        ui.create_campaign_draft(application)
        rows = dict(((r[0], r[1]), r[3]) for r in application.material_auto_id_draft_table.items.values())
        self.assertEqual(rows[("Declared", "Campaign id")], "NOT_DECLARED")
        self.assertEqual(rows[("Declared", "Run type")], "NOT_DECLARED")
        with mock.patch.object(ui.simpledialog, "askstring", return_value="M8/D2c"):
            buttons["Declare campaign_id..."]()
        buttons["Run type: RUN_B"]()
        ui.add_draft_specimen(application, FORWARD / "SP02.physical.forward.json")
        with mock.patch("domain.experiment_fixture.fixture_roots_from_environment", return_value={}):
            ui.check_campaign_draft_inputs(application)
        current = application.auto_id_draft
        for invalid in (lambda: ui.declare_draft_campaign_id(application, "bad id"),
                        lambda: ui.declare_draft_run_type(application, "RUN_C")):
            invalid()
            self.assertIs(application.auto_id_draft, current)  # the prior state is preserved
            self.assertIn("Not changed", application.material_auto_id_draft_label.kwargs["text"])
            self.assertTrue(application.material_auto_id_draft_check_table.items)  # the check stays current
        with mock.patch.object(ui.simpledialog, "askstring", return_value=None):  # cancelled
            buttons["Declare campaign_id..."]()
        self.assertIs(application.auto_id_draft, current)
        items = list(application.material_auto_id_draft_table.items.values())
        self.assertIn(("Declared", "Campaign id", "M8/D2c", "PRESENT"), items)
        run_type = next(r for r in items if r[1] == "Run type")
        self.assertTrue(run_type[2].startswith("RUN_B — ") and "authorises nothing" in run_type[2])
        gaps = {r[1]: r[2] for r in items if r[0] == "Missing required inputs"}
        self.assertEqual(gaps["run_b_gate"], RUN_B_NOT_AUTHORISED)
        self.assertNotIn("campaign_id", gaps)
        preview = json.loads(application.material_auto_id_draft_preview_label.kwargs["text"])
        self.assertEqual((preview["campaign_id"], preview["run_type"]), ("M8/D2c", "RUN_B"))
        path = ui.save_campaign_draft(application, self.out / "gui.json")
        ui.discard_campaign_draft(application)
        ui.open_campaign_draft(application, path)
        self.assertEqual((application.auto_id_draft.campaign_id, application.auto_id_draft.run_type),
                         ("M8/D2c", "RUN_B"))

    def test_real_tk(self):
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
        ui.declare_draft_campaign_id(application, "TK_1")
        ui.declare_draft_run_type(application, "RUN_A")
        root.update_idletasks()
        table = application.material_auto_id_draft_table
        items = [tuple(str(v) for v in table.item(k, "values")) for k in table.get_children()]
        self.assertIn(("Declared", "Campaign id", "TK_1", "PRESENT"), items)
        self.assertIn(("Declared", "Run type", "RUN_A", "PRESENT"), items)


# ----------------------------------------------------------------------------- safety

class SafetyTests(_Identity):
    def test_no_execution_no_protected_writes_and_m7_unchanged(self):
        import material_identification_ui as ui
        from services import identification_step

        refuse = mock.Mock(side_effect=AssertionError("forbidden call"))
        watched = (ROOT / "docs", ROOT / "src")
        before = [d1._tree(p) for p in watched]
        application = d1.GuiTests.application(self)
        with mock.patch.object(subprocess, "Popen", refuse), mock.patch.object(subprocess, "run", refuse), \
                mock.patch.object(os, "system", refuse), \
                mock.patch.object(identification_step, "run_bounded_lm", refuse):
            ui.create_campaign_draft(application)
            ui.declare_draft_campaign_id(application, "SAFE_1")
            ui.declare_draft_run_type(application, "RUN_B")
            ui.save_campaign_draft(application, self.out / "draft.json")
            ui.save_campaign_draft(application, ROOT / "docs" / "auto_id" / "draft.json")  # refused
        refuse.assert_not_called()
        self.assertEqual([d1._tree(p) for p in watched], before)
        for name, expected in d1.CAMPAIGN_HASHES.items():
            self.assertEqual(load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json").campaign_hash, expected)


if __name__ == "__main__":
    unittest.main()

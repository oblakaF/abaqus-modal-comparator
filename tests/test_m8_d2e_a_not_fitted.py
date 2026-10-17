"""M8-D2e-A — Declare Not-Fitted Parameters in the campaign draft (no default; k_int OFF only).

not_fitted.t_face and not_fitted.k_core take the user's own non-empty description, recorded as written; not_fitted.k_int
is an explicit selection whose only accepted value is OFF (ENABLED, unknown values and ambiguous text are refused). OFF
is written into the intended definition as fixed text. The declaration enables no unsupported scientific
configuration: the campaign parser, the holdout policy and the production holdout path are unchanged. Saved as
auto-id/campaign-draft/v4 and re-validated on reopening; v1 / v2 / v3 drafts open with nothing declared. No FIT /
HOLDOUT rows, no run, no Abaqus.
"""

from __future__ import annotations

import inspect
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

from domain.campaign_definition import load_campaign_definition, parse_campaign_definition  # noqa: E402
from services.campaign_draft import (  # noqa: E402
    DRAFT_SCHEMA,
    DRAFT_SCHEMA_V1,
    DRAFT_SCHEMA_V2,
    DRAFT_SCHEMA_V3,
    K_INT_NOTE,
    K_INT_OFF_DEFINITION,
    NOT_FITTED_KEYS,
    CampaignDraft,
    CampaignDraftError,
    DraftIncomplete,
    draft_from_document,
    draft_rows,
    load_draft,
    write_draft,
)
import test_m8_d1_campaign_draft as d1  # noqa: E402

FORWARD, CAMPAIGNS, MATERIAL = d1.FORWARD, d1.CAMPAIGNS, d1.MATERIAL
RUN_A = json.loads((CAMPAIGNS / "M7_RUN_A.campaign.json").read_text(encoding="utf-8"))
T_FACE = "NOT_FITTED: nominal FE geometry (user description for this test)"
K_CORE = "NOT_FITTED: the existing INP core constants (user description for this test)"
GAPS = {f"not_fitted.{key}" for key in NOT_FITTED_KEYS}


class _NotFitted(d1._Draft):
    def declared(self, draft=None):
        draft = self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02) if draft is None else draft
        return draft.with_not_fitted("t_face", T_FACE).with_not_fitted("k_core", K_CORE).with_not_fitted("k_int", "OFF")


# ----------------------------------------------------------------------------- no default

class NoDefaultTests(_NotFitted):
    def test_nothing_is_declared_by_default(self):
        draft = CampaignDraft()
        self.assertEqual(draft.not_fitted(), {"t_face": None, "k_core": None, "k_int": None})  # no implicit k_int
        gaps = {g.field: g.reason for g in draft.gaps()}
        self.assertTrue(GAPS <= set(gaps))
        self.assertNotIn("not_fitted", gaps)  # one gap per entry, not a generic one
        self.assertIn("select OFF explicitly (no default)", gaps["not_fitted.k_int"])
        self.assertNotIn("not_fitted", draft.intended_definition())
        self.assertEqual(draft.document()["declared"]["not_fitted"], {"t_face": None, "k_core": None, "k_int": None})
        with self.assertRaises(DraftIncomplete):
            draft.finalise()

    def test_missing_inputs_are_recomputed_after_each_declaration(self):
        draft = self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02)
        before = {g.field for g in draft.gaps()}
        for key, value in (("t_face", T_FACE), ("k_core", K_CORE), ("k_int", "OFF")):
            after_draft = draft.with_not_fitted(key, value)
            after = {g.field for g in after_draft.gaps()}
            self.assertEqual(before - after, {f"not_fitted.{key}"})  # nothing else is filled in
            self.assertEqual(after - before, set())
            draft, before = after_draft, after
        self.assertFalse(GAPS & before)
        self.assertTrue({"specimens[0].rows", "fitted_parameters", "sigma", "lm"} <= before)  # rows stay missing
        with self.assertRaises(DraftIncomplete):
            draft.finalise()


# ----------------------------------------------------------------------------- k_int

class KIntTests(_NotFitted):
    def test_off_is_accepted_and_represented_deterministically(self):
        draft = CampaignDraft().with_not_fitted("k_int", "OFF")
        self.assertEqual(draft.not_fitted_k_int, "OFF")
        self.assertEqual(draft.intended_definition()["not_fitted"], {"k_int": K_INT_OFF_DEFINITION})
        self.assertEqual(K_INT_OFF_DEFINITION, RUN_A["not_fitted"]["k_int"])  # cross-check with the accepted wording
        self.assertEqual(draft.document()["declared"]["not_fitted"]["k_int"], "OFF")
        self.assertIn("enables no unsupported scientific configuration", K_INT_NOTE)
        row = [r for r in draft_rows(draft) if r[1] == "Not fitted: k_int"]
        self.assertEqual(row, [("Declared", "Not fitted: k_int", f"OFF — {K_INT_NOTE}", "PRESENT")])

    def test_enabled_is_refused_and_the_draft_is_unchanged(self):
        draft = CampaignDraft()
        with self.assertRaises(CampaignDraftError) as caught:
            draft.with_not_fitted("k_int", "ENABLED")
        self.assertIn("ENABLED is not supported", str(caught.exception))
        self.assertIsNone(draft.not_fitted_k_int)
        off = draft.with_not_fitted("k_int", "OFF")
        with self.assertRaises(CampaignDraftError):
            off.with_not_fitted("k_int", "ENABLED")  # never replaces an earlier OFF
        self.assertEqual(off.not_fitted_k_int, "OFF")

    def test_unknown_and_ambiguous_values_are_refused(self):
        draft = CampaignDraft()
        for value in ("off", "Off", " OFF", "OFF ", "OFF: disabled", "DISABLED", "enabled", "", None, True, False, 0,
                      ["OFF"], K_INT_OFF_DEFINITION):
            with self.subTest(value=value), self.assertRaises(CampaignDraftError) as caught:
                draft.with_not_fitted("k_int", value)
            self.assertIn("the only accepted selection is OFF", str(caught.exception))
        self.assertEqual(draft, CampaignDraft())


# ----------------------------------------------------------------------------- t_face / k_core descriptions

class DescriptionTests(_NotFitted):
    def test_descriptions_are_recorded_as_written(self):
        draft = self.declared()
        self.assertEqual(draft.intended_definition()["not_fitted"],
                         {"t_face": T_FACE, "k_core": K_CORE, "k_int": K_INT_OFF_DEFINITION})
        self.assertEqual(draft.document()["declared"]["not_fitted"],
                         {"t_face": T_FACE, "k_core": K_CORE, "k_int": "OFF"})
        rows = draft_rows(draft)
        self.assertIn(("Declared", "Not fitted: t_face", T_FACE, "PRESENT"), rows)
        self.assertIn(("Declared", "Not fitted: k_core", K_CORE, "PRESENT"), rows)

    def test_invalid_descriptions_and_keys_are_refused_and_the_draft_is_unchanged(self):
        draft = CampaignDraft().with_not_fitted("t_face", T_FACE)
        for key in ("t_face", "k_core"):
            for value in ("", "   ", " text", "text ", None, 5, ["text"]):
                with self.subTest(key=key, value=value), self.assertRaises(CampaignDraftError):
                    draft.with_not_fitted(key, value)
        for key in ("G12", "k_int_enabled", "not_fitted.t_face", None):
            with self.subTest(key=key), self.assertRaises(CampaignDraftError):
                draft.with_not_fitted(key, "OFF")
        self.assertEqual(draft.not_fitted(), {"t_face": T_FACE, "k_core": None, "k_int": None})

    def test_the_declarations_are_accepted_by_the_unchanged_parser(self):
        draft = self.declared()
        intended = draft.intended_definition()
        completed = {**{k: v for k, v in RUN_A.items() if k not in intended}, **intended,
                     "specimens": [{**s, **i} for s, i in zip(RUN_A["specimens"], intended["specimens"])]}
        definition = parse_campaign_definition(completed)
        self.assertEqual(dict(definition.not_fitted), intended["not_fitted"])
        same = self.declared(self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02))
        self.assertEqual(same.document_bytes(), draft.document_bytes())  # deterministic
        reordered = (self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02).with_not_fitted("k_int", "OFF")
                     .with_not_fitted("k_core", K_CORE).with_not_fitted("t_face", T_FACE))
        self.assertEqual(reordered.document_bytes(), draft.document_bytes())


# ----------------------------------------------------------------------------- persistence and compatibility

class PersistenceTests(_NotFitted):
    def test_v4_save_and_reopen(self):
        draft = self.declared().with_campaign_id("M8/D2e-A").with_run_type("RUN_A")
        path = write_draft(draft, self.out / "draft.json", (ROOT,))
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "auto-id/campaign-draft/v4")
        self.assertEqual(DRAFT_SCHEMA, "auto-id/campaign-draft/v4")
        reopened = load_draft(path, ROOT, self.fixtures)
        self.assertEqual(reopened, draft)
        self.assertEqual(reopened.document_bytes(), path.read_bytes())
        partial = CampaignDraft().with_not_fitted("k_int", "OFF")
        write_draft(partial, path, (ROOT,))
        self.assertEqual(load_draft(path, ROOT, self.fixtures), partial)

    def test_reopen_revalidates_the_declarations(self):
        document = self.declared().document()
        for change, text in (
                (lambda d: d["declared"]["not_fitted"].update(k_int="ENABLED"), "ENABLED is not supported"),
                (lambda d: d["declared"]["not_fitted"].update(k_int="off"), "unknown or ambiguous"),
                (lambda d: d["declared"]["not_fitted"].update(t_face=" padded"), "not_fitted.t_face"),
                (lambda d: d["declared"]["not_fitted"].pop("k_core"), "must state exactly"),
                (lambda d: d["declared"]["not_fitted"].update(k_int_enabled=False), "must state exactly"),
                (lambda d: d["declared"].update(not_fitted="OFF"), "must state exactly"),
                (lambda d: d["declared"].pop("not_fitted"), "must state exactly"),
                (lambda d: d["intended_campaign_definition"]["not_fitted"].update(k_int="ON"), "conflicting draft"),
        ):
            tampered = json.loads(json.dumps(document))
            change(tampered)
            with self.subTest(text=text), self.assertRaises(CampaignDraftError) as caught:
                draft_from_document(tampered, ROOT, self.fixtures)
            self.assertIn(text, str(caught.exception))
        self.assertEqual(draft_from_document(document, ROOT, self.fixtures), self.declared())

    def test_v1_v2_v3_drafts_open_with_nothing_declared(self):
        draft = self.physical_pair().with_question(MATERIAL).with_tau_mf(0.02)
        for schema in (DRAFT_SCHEMA_V1, DRAFT_SCHEMA_V2, DRAFT_SCHEMA_V3):
            with self.subTest(schema=schema):
                document = draft.document()
                document["schema"] = schema
                document["declared"].pop("not_fitted")
                if schema != DRAFT_SCHEMA_V3:
                    document.pop("specimen_records")
                if schema == DRAFT_SCHEMA_V1:
                    document["declared"] = {k: document["declared"][k] for k in ("scientific_question", "tau_mf")}
                path = self.out / f"{schema.rsplit('/', 1)[1]}.json"
                data = (json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode()
                path.write_bytes(data)
                reopened = load_draft(path, ROOT, self.fixtures)
                self.assertEqual(reopened, draft)
                self.assertEqual(reopened.not_fitted(), {"t_face": None, "k_core": None, "k_int": None})  # not inferred
                self.assertEqual(path.read_bytes(), data)  # opening never rewrites the file
                carrying = json.loads(json.dumps(document))
                carrying["declared"]["not_fitted"] = {"t_face": None, "k_core": None, "k_int": "OFF"}
                with self.assertRaises(CampaignDraftError):
                    draft_from_document(carrying, ROOT, self.fixtures)  # an older version cannot carry them
                write_draft(reopened.with_not_fitted("k_int", "OFF"), path, (ROOT,))  # an explicit save writes v4
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["schema"], DRAFT_SCHEMA)


# ----------------------------------------------------------------------------- production unchanged

class ProductionUnchangedTests(_NotFitted):
    def test_parser_holdout_policy_and_production_path_are_unchanged(self):
        from services import identification_campaign_run, modal_family_classifier

        source = inspect.getsource(identification_campaign_run.prepare_campaign_specimen)
        self.assertIn("for r in rows], False)", source)  # the production holdout path still passes False
        self.assertEqual(list(inspect.signature(modal_family_classifier.select_holdouts).parameters),
                         ["rows", "k_int_enabled"])
        for name, expected in d1.CAMPAIGN_HASHES.items():
            self.assertEqual(load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json").campaign_hash, expected)
        draft_source = (ROOT / "src" / "services" / "campaign_draft.py").read_text(encoding="utf-8")
        for forbidden in ("select_holdouts", "k_int_enabled", "subprocess", "require_executable"):
            self.assertNotIn(forbidden, draft_source)


# ----------------------------------------------------------------------------- GUI

class GuiTests(_NotFitted):
    LABELS = ("Declare not_fitted.t_face...", "Declare not_fitted.k_core...", "k_int: OFF")

    def test_fake_gui_declarations(self):
        import material_identification_ui as ui

        application = d1.GuiTests.application(self)
        buttons = d1.GuiTests.buttons(application)
        for label in self.LABELS:
            self.assertIn(label, buttons)
        self.assertFalse([label for label in buttons if "ENABLED" in label])  # never offered
        buttons["k_int: OFF"]()  # no draft yet
        self.assertIn("Create Campaign Draft... first", application.material_auto_id_draft_label.kwargs["text"])
        ui.create_campaign_draft(application)
        rows = list(application.material_auto_id_draft_table.items.values())
        for key in NOT_FITTED_KEYS:
            self.assertIn(("Declared", f"Not fitted: {key}", "", "NOT_DECLARED"), rows)
            self.assertIn(("Missing required inputs", f"not_fitted.{key}"), [r[:2] for r in rows])
        with mock.patch.object(ui.simpledialog, "askstring", return_value=None):  # cancelled
            buttons["Declare not_fitted.t_face..."]()
        self.assertIsNone(application.auto_id_draft.not_fitted_t_face)
        with mock.patch.object(ui.simpledialog, "askstring", return_value="  "):  # refused, unchanged
            buttons["Declare not_fitted.t_face..."]()
        self.assertIn("Not changed", application.material_auto_id_draft_label.kwargs["text"])
        self.assertIsNone(application.auto_id_draft.not_fitted_t_face)
        for label, text in ((self.LABELS[0], T_FACE), (self.LABELS[1], K_CORE)):
            with mock.patch.object(ui.simpledialog, "askstring", return_value=text):
                buttons[label]()
        buttons["k_int: OFF"]()
        message = application.material_auto_id_draft_label.kwargs["text"]
        self.assertIn("Declared not_fitted.k_int OFF", message)
        self.assertIn("enables no unsupported scientific configuration", message)
        before = application.auto_id_draft
        ui.declare_draft_not_fitted(application, "k_int", "ENABLED")
        self.assertIs(application.auto_id_draft, before)
        self.assertIn("ENABLED is not supported", application.material_auto_id_draft_label.kwargs["text"])
        rows = list(application.material_auto_id_draft_table.items.values())
        self.assertIn(("Declared", "Not fitted: t_face", T_FACE, "PRESENT"), rows)
        self.assertNotIn("not_fitted.k_int", [r[1] for r in rows if r[0] == "Missing required inputs"])
        preview = json.loads(application.material_auto_id_draft_preview_label.kwargs["text"])
        self.assertEqual(preview["not_fitted"], {"t_face": T_FACE, "k_core": K_CORE, "k_int": K_INT_OFF_DEFINITION})
        path = ui.save_campaign_draft(application, self.out / "gui.json")
        ui.discard_campaign_draft(application)
        ui.open_campaign_draft(application, path)
        self.assertEqual(application.auto_id_draft.not_fitted(), {"t_face": T_FACE, "k_core": K_CORE, "k_int": "OFF"})

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
        ui.declare_draft_not_fitted(application, "t_face", T_FACE)
        ui.declare_draft_not_fitted(application, "k_int", "OFF")
        root.update_idletasks()
        table = application.material_auto_id_draft_table
        items = [tuple(str(v) for v in table.item(k, "values")) for k in table.get_children()]
        declared = {row[1]: row[3] for row in items if row[0] == "Declared" and row[1].startswith("Not fitted")}
        self.assertEqual(declared, {"Not fitted: t_face": "PRESENT", "Not fitted: k_core": "NOT_DECLARED",
                                    "Not fitted: k_int": "PRESENT"})
        self.assertIn("enables no unsupported scientific configuration",
                      application.material_auto_id_draft_label.cget("text"))


# ----------------------------------------------------------------------------- safety

class SafetyTests(_NotFitted):
    def test_no_execution_no_repository_writes_and_m7_unchanged(self):
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
            ui.add_draft_specimen(application, FORWARD / "SP02.physical.forward.json")
            ui.declare_draft_not_fitted(application, "k_int", "OFF")
            ui.declare_draft_not_fitted(application, "k_core", K_CORE)
            ui.save_campaign_draft(application, self.out / "draft.json")
        refuse.assert_not_called()
        self.assertEqual([d1._tree(p) for p in watched], before)
        for name, expected in d1.CAMPAIGN_HASHES.items():
            self.assertEqual(load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json").campaign_hash, expected)


if __name__ == "__main__":
    unittest.main()

"""M8-D2b — Check Draft Inputs: factual availability of every selected specimen's inputs (never a readiness verdict).

Each selected specimen is re-verified against the current governed records and its passport and fixture are run
through the existing M8.1 wizard checks. External files keep their factual statuses (PRESENT_SHA256_NOT_VERIFIED,
NOT_CONFIGURED, NOT_FOUND, MISMATCH); recorded physical-data gaps stay UNAVAILABLE / MISSING. A changed identity or an
unavailable fixture catalogue is a refusal; nothing is substituted. Results belong to the exact draft checked.
Nothing here runs Abaqus, FE or LM.
"""

from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.experiment_fixture import fixture_roots_from_environment  # noqa: E402
from services.campaign_draft import CampaignDraft, check_draft_inputs  # noqa: E402
import test_m8_d1_campaign_draft as d1  # noqa: E402

FORWARD = d1.FORWARD
MATERIAL = d1.MATERIAL
FILE_ITEMS = ("Modes (curve-fitted modal set)", "FE model input", "Reference ODB", "FE geometry file")
FACTUAL = {"PRESENT_SHA256_NOT_VERIFIED", "NOT_CONFIGURED", "NOT_FOUND", "MISMATCH"}


def by_specimen(result, name):
    return [row for row in result.rows if row[0] == name]


def file_rows(result, name):
    return {row[2].split(":")[0]: row for row in by_specimen(result, name) if row[2].split(":")[0] in FILE_ITEMS}


class _Check(d1._Draft):
    def check(self, draft=None, roots=None, fixtures="default"):
        draft = draft or self.physical_pair().with_question(MATERIAL)
        return check_draft_inputs(draft, ROOT, self.fixtures if fixtures == "default" else fixtures,
                                  {} if roots is None else roots)


# ----------------------------------------------------------------------------- governed inputs, stores, files

class AvailabilityTests(_Check):
    def test_sp02_sp13_governed_inputs_without_stores(self):
        result = self.check()
        self.assertEqual(result.refusals, ())
        self.assertEqual(sorted({row[0] for row in result.rows}), ["SP02", "SP13"])
        for name in ("SP02", "SP13"):
            rows = by_specimen(result, name)
            self.assertEqual(rows[0][1:4], ("Identity", f"Governed specimen input docs/auto_id/forward_models/"
                                                        f"{name}.physical.forward.json", "PRESENT"))
            self.assertIn("re-verified against the current governed records", rows[0][4])
            files = file_rows(result, name)
            self.assertEqual(set(files), set(FILE_ITEMS))
            for row in files.values():  # a missing store is never presented as available
                self.assertEqual(row[3], "NOT_CONFIGURED")
            gaps = {row[2]: row[3] for row in rows if row[1] == "Physical measurements"}
            self.assertEqual(gaps["Face thickness"], "UNAVAILABLE")  # recorded gaps shown, never filled
            self.assertEqual(gaps["Suspension limit"], "UNAVAILABLE")
            self.assertIn("Modal set: Best" if name == "SP13" else "Modal set: Bravo (1)", [r[2] for r in rows])
        sp02 = {row[2].split(":")[0]: row[3] for row in by_specimen(result, "SP02")}
        self.assertEqual(sp02["Test run (fixture)"], "MISMATCH")  # the recorded discrepancy is shown as is
        sp13 = {row[2].split(":")[0]: row[3] for row in by_specimen(result, "SP13")}
        self.assertEqual(sp13["Unresolved"], "MISSING")
        statuses = {row[3] for row in result.rows}
        self.assertNotIn("READY", " ".join(statuses))
        self.assertIn("not a scientific readiness verdict", result.summary())

    def test_missing_and_size_mismatched_files_and_size_only_presence(self):
        stores = self.out / "stores"
        roots = {"snadwich": stores / "snadwich", "carbon-project-archive": stores / "archive"}
        for root in roots.values():
            root.mkdir(parents=True)
        files = file_rows(self.check(roots=roots), "SP13")
        for row in files.values():
            self.assertEqual(row[3], "NOT_FOUND")
        reference = self.fixtures.fixture("SP13/best-physical").experimental_source
        target = roots["snadwich"].joinpath(*Path(reference.location.relative_path).parts)
        target.parent.mkdir(parents=True)
        target.write_bytes(b"not the pinned file")
        self.assertEqual(file_rows(self.check(roots=roots), "SP13")["Modes (curve-fitted modal set)"][3], "MISMATCH")
        with open(target, "r+b") as handle:  # the pinned size, wrong content: presence is never scientific readiness
            handle.truncate(reference.size_bytes)
        row = file_rows(self.check(roots=roots), "SP13")["Modes (curve-fitted modal set)"]
        self.assertEqual(row[3], "PRESENT_SHA256_NOT_VERIFIED")
        self.assertIn("SHA-256 NOT verified", row[4])

    def test_configured_real_stores_stay_sha256_not_verified(self):
        roots = fixture_roots_from_environment()
        if not {"snadwich", "carbon-project-archive"} <= set(roots):
            self.skipTest("data stores snadwich / carbon-project-archive not configured")
        result = self.check(roots=roots)
        for name in ("SP02", "SP13"):
            for row in file_rows(result, name).values():
                self.assertEqual(row[3], "PRESENT_SHA256_NOT_VERIFIED")


# ----------------------------------------------------------------------------- refusals

class RefusalTests(_Check):
    def test_fixture_catalogue_or_roots_unavailable(self):
        result = self.check(fixtures=None)
        self.assertEqual(result.rows, ())
        self.assertIn("experiment-fixture catalogue", result.summary())
        result = check_draft_inputs(self.physical_pair(), ROOT, self.fixtures, None)
        self.assertEqual(result.rows, ())
        self.assertIn("data-store roots", result.summary())
        self.assertIn("selects no specimen", check_draft_inputs(CampaignDraft(), ROOT, self.fixtures, {}).summary())

    def test_changed_or_missing_identity_is_refused_never_substituted(self):
        sp02, sp13 = self.specimen("SP02.physical.forward.json"), self.specimen("SP13.physical.forward.json")
        for field, value in (("registration_hash", "0" * 64), ("passport_manifest_hash", "1" * 64),
                             ("fixture_id", "SP02/bravo-1")):
            changed = replace(sp02, **{field: value})
            draft = CampaignDraft(specimens=(changed, sp13))
            result = self.check(draft)
            with self.subTest(field=field):
                rows = by_specimen(result, "SP02")
                self.assertEqual(len(rows), 1)  # nothing else is checked for the changed selection
                self.assertEqual(rows[0][3], "MISMATCH")
                self.assertIn(field, rows[0][4])
                self.assertIn("never substituted", rows[0][4])
                self.assertGreater(len(by_specimen(result, "SP13")), 1)  # the unchanged specimen is still checked
        missing = replace(sp02, forward_model="docs/auto_id/forward_models/SP99.physical.forward.json")
        rows = by_specimen(self.check(CampaignDraft(specimens=(missing,))), "SP02")
        self.assertEqual([r[3] for r in rows], ["INVALID"])


# ----------------------------------------------------------------------------- GUI

class GuiTests(_Check):
    def application(self):
        return d1.GuiTests.application(self)

    def test_check_on_request_and_invalidation(self):
        import material_identification_ui as ui

        application = self.application()
        buttons = d1.GuiTests.buttons(application)
        self.assertIn(ui.AUTO_ID_DRAFT_CHECK_LABEL, buttons)
        buttons[ui.AUTO_ID_DRAFT_CHECK_LABEL]()  # no draft
        self.assertEqual(application.material_auto_id_draft_check_table.items, {})
        ui.create_campaign_draft(application)
        ui.add_draft_specimen(application, FORWARD / "SP02.physical.forward.json")
        ui.add_draft_specimen(application, FORWARD / "SP13.physical.forward.json")
        self.assertEqual(application.material_auto_id_draft_check_label.kwargs["text"], ui.AUTO_ID_DRAFT_NOT_CHECKED)
        with mock.patch("domain.experiment_fixture.fixture_roots_from_environment", return_value={}):
            buttons[ui.AUTO_ID_DRAFT_CHECK_LABEL]()
        rows = list(application.material_auto_id_draft_check_table.items.values())
        self.assertTrue(any(r[0] == "SP13" and r[3] == "NOT_CONFIGURED" for r in rows))
        self.assertIn("Checked 2 specimen(s)", application.material_auto_id_draft_check_label.kwargs["text"])
        self.assertIsNone(getattr(application, "scientific_readiness_record", None))  # never a readiness verdict
        ui.declare_draft_tolerance(application, "0.5")  # refused: the draft is unchanged, the check stays current
        self.assertTrue(application.material_auto_id_draft_check_table.items)
        path = ui.save_campaign_draft(application, self.out / "draft.json")
        self.assertTrue(application.material_auto_id_draft_check_table.items)  # saving does not change the draft
        for change in (lambda: ui.declare_draft_question(application, MATERIAL),
                       lambda: ui.open_campaign_draft(application, path),
                       lambda: ui.clear_draft_specimens(application),
                       lambda: ui.discard_campaign_draft(application)):
            ui.open_campaign_draft(application, path)  # a draft with both specimens before every change
            with mock.patch("domain.experiment_fixture.fixture_roots_from_environment", return_value={}):
                ui.check_campaign_draft_inputs(application)
            self.assertTrue(application.material_auto_id_draft_check_table.items)
            change()
            self.assertEqual(application.material_auto_id_draft_check_table.items, {})
            self.assertEqual(application.material_auto_id_draft_check_label.kwargs["text"],
                             ui.AUTO_ID_DRAFT_NOT_CHECKED)

    def test_catalogue_failure_is_reported_in_the_gui(self):
        import material_identification_ui as ui

        application = self.application()
        ui.create_campaign_draft(application)
        ui.add_draft_specimen(application, FORWARD / "SP02.physical.forward.json")
        draft = application.auto_id_draft
        with mock.patch("services.auto_id_wizard.load_fixtures", side_effect=OSError("catalogue unreadable")):
            ui.check_campaign_draft_inputs(application)
        self.assertIs(application.auto_id_draft, draft)
        self.assertEqual(application.material_auto_id_draft_check_table.items, {})
        self.assertIn("Input check refused", application.material_auto_id_draft_check_label.kwargs["text"])
        with mock.patch("domain.experiment_fixture.fixture_roots_from_environment", side_effect=RuntimeError("x")):
            ui.check_campaign_draft_inputs(application)
        self.assertIn("data-store roots", application.material_auto_id_draft_check_label.kwargs["text"])

    def test_real_tk_check(self):
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
        with mock.patch("domain.experiment_fixture.fixture_roots_from_environment", return_value={}):
            ui.check_campaign_draft_inputs(application)
        root.update_idletasks()
        table = application.material_auto_id_draft_check_table
        items = [tuple(str(v) for v in table.item(k, "values")) for k in table.get_children()]
        self.assertTrue(items)
        self.assertEqual({i[0] for i in items}, {"SP13"})
        self.assertIn("NOT_CONFIGURED", {i[3] for i in items})


# ----------------------------------------------------------------------------- safety

class SafetyTests(_Check):
    def test_no_execution_and_no_protected_writes(self):
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
            ui.add_draft_specimen(application, FORWARD / "SP13.physical.forward.json")
            ui.check_campaign_draft_inputs(application)
            self.check()
        refuse.assert_not_called()
        self.assertEqual([d1._tree(p) for p in watched], before)
        self.assertEqual(list(self.out.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

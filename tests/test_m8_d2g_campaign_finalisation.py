"""M8-D2g — Finalise & Export Campaign Definition and Pre-run Validation (records only; nothing is run or authorised).

A complete v6 draft is re-verified (rebuilt from its document against the current governed records), finalised by
the governed parser and saved atomically, outside the repository and data stores, as exactly the definition the parser
accepted; the file is re-read by load_campaign_definition with the same campaign hash. Pre-run Validation shows six
separate sections; nothing becomes a PASS and execution is never authorised. No Abaqus, FE or LM.
"""

from __future__ import annotations

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
sys.path.insert(0, str(ROOT / "tests"))

from domain.campaign_definition import CAMPAIGN_KEYS, load_campaign_definition  # noqa: E402
from domain.experiment_fixture import FixtureSourceMismatchError, fixture_roots_from_environment  # noqa: E402
from services import prerun_validation as prerun_module  # noqa: E402
from services.auto_id_wizard import load_fixtures  # noqa: E402
from services.campaign_configuration import copy_reference_texts, declare_configuration, reference_configuration  # noqa: E402
from services.campaign_draft import (  # noqa: E402
    CampaignDraft,
    CampaignDraftError,
    DraftIncomplete,
    bind_draft_observations,
    bind_specimen_records,
    governed_specimen_input,
    load_draft,
)
from services.campaign_finalisation import (  # noqa: E402
    EXPORT_PROTOCOL_SCHEMA,
    check_definition_destination,
    export_campaign_definition,
    finalise_campaign,
)
from services.prerun_validation import NOT_AUTHORISED, OVERALL, SECTIONS, prerun_validation  # noqa: E402
import test_m8_d2f_campaign_configuration as d2f  # noqa: E402

SP02, SP13, MATERIAL, CALIBRATION = d2f.SP02, d2f.SP13, d2f.MATERIAL, d2f.CALIBRATION
REFERENCE = reference_configuration(ROOT)
NEVER = ("PASS", "PASSED", "IDENTIFIED", "RELEASED", "AUTHORISED", "EXECUTED", "ACCEPTED_CALIBRATION")


def complete_draft(root, fixtures, forward_models=(SP02, SP13), question=MATERIAL, run_type="RUN_A",
                   decision="SUPERVISOR M8-D2g test decision", run_b_gate=True, budget=True):
    draft = (CampaignDraft().with_question(question).with_run_type(run_type).with_tau_mf(0.01)
             .with_campaign_id("M8/D2g/test"))
    for forward_model in forward_models:
        draft = draft.with_specimen(governed_specimen_input(Path(root) / forward_model, root, fixtures))
    draft, _ = bind_specimen_records(draft, root, fixtures)
    draft, _ = bind_draft_observations(draft, root, fixtures)
    for key, value in (("t_face", "nominal FE geometry"), ("k_core", "INP core constants"), ("k_int", "OFF")):
        draft = draft.with_not_fitted(key, value)
    for group in ("material", "uncertainty", "algorithm") + (("budget",) if budget else ()):
        draft = declare_configuration(draft, group, copy_reference_texts(group, REFERENCE), root, "copied (test)")
    draft = declare_configuration(draft, "provenance", {"decision": decision, "provenance": "test"}, root,
                                  "declared by the user")
    return draft.with_run_b_gate_none() if run_b_gate and run_type == "RUN_A" else draft


class _Finalisation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixtures = load_fixtures(ROOT)

    def setUp(self):
        self.out = Path(tempfile.mkdtemp(prefix="m8_d2g_out_"))
        self.addCleanup(shutil.rmtree, self.out, ignore_errors=True)

    def temporary_repository(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="m8_d2g_repo_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        shutil.copytree(ROOT / "docs", root / "docs")
        return root

    def exported(self, **kwargs):
        draft = complete_draft(ROOT, self.fixtures, **kwargs)
        finalised = finalise_campaign(draft, ROOT, self.fixtures)
        result = export_campaign_definition(draft, self.out / "test.campaign.json", ROOT, self.fixtures, (ROOT,),
                                            finalised.campaign_hash)
        return draft, finalised, result


# ----------------------------------------------------------------------------- finalise and export


class ExportTests(_Finalisation):
    def test_sp02_plus_sp13_is_finalised_saved_and_reread_with_the_same_hash(self):
        draft, finalised, result = self.exported()
        self.assertEqual(result.campaign_hash, finalised.campaign_hash)
        self.assertEqual(result.reloaded_hash, finalised.campaign_hash)
        loaded = load_campaign_definition(result.path)
        self.assertEqual(loaded.campaign_hash, draft.finalise().campaign_hash)
        data = json.loads(result.path.read_text(encoding="utf-8"))
        self.assertEqual(data, finalised.data)  # exactly what the parser accepted
        self.assertEqual(set(data), set(CAMPAIGN_KEYS) | {"scientific_question", "tau_mf"})  # no extra field
        protocol = json.loads(result.protocol_path.read_text(encoding="utf-8"))
        self.assertEqual(protocol["schema"], EXPORT_PROTOCOL_SCHEMA)
        self.assertIn("NOT_GOVERNED_EVIDENCE", protocol["labels"])
        self.assertIn("AUTHORISES_NOTHING", protocol["labels"])
        self.assertIn("not an execution authorisation", result.summary())
        with self.assertRaisesRegex(CampaignDraftError, "not a campaign draft"):
            load_draft(result.path, ROOT, self.fixtures)  # a definition is never a draft, nor the reverse

    def test_incomplete_drafts_are_never_finalised(self):
        for kwargs, missing in ((dict(forward_models=(SP13,), question=CALIBRATION, budget=False),
                                 ["abaqus_solve_budget", "archive_reuse"]),
                                (dict(forward_models=(SP02,), question=CALIBRATION, budget=False),
                                 ["abaqus_solve_budget", "archive_reuse"]),
                                (dict(run_type="RUN_B", budget=True), ["fixed_parameters"])):
            with self.subTest(kwargs=kwargs):
                if kwargs.get("run_type") == "RUN_B":
                    with self.assertRaises(CampaignDraftError):  # RUN_A settings do not hold for RUN_B
                        complete_draft(ROOT, self.fixtures, **kwargs)
                    draft = complete_draft(ROOT, self.fixtures, run_type="RUN_A", run_b_gate=False)
                    draft = draft.without_configuration("material").with_run_type("RUN_B")
                    missing = ["bounds", "engineering_plausibility", "fitted_parameters", "fixed_parameters",
                               "parameterisation", "run_b_gate", "start"]
                else:
                    draft = complete_draft(ROOT, self.fixtures, **kwargs)
                with self.assertRaises(DraftIncomplete) as caught:
                    finalise_campaign(draft, ROOT, self.fixtures)
                self.assertEqual(sorted(g.field for g in caught.exception.gaps), sorted(missing))

    def test_a_draft_whose_material_parameters_were_cleared_still_reopens(self):
        """Regression (found in D2g): an archive plan that cannot be checked yet (no parameterisation) is a pending
        input, not a mismatch — the saved draft reopens; declaring the budget first is still refused."""
        from services.campaign_draft import write_draft

        draft = complete_draft(ROOT, self.fixtures).without_configuration("material")
        path = write_draft(draft, self.out / "cleared.json", (ROOT,))
        self.assertEqual(load_draft(path, ROOT, self.fixtures), draft)
        with self.assertRaisesRegex(CampaignDraftError, "declare the material parameters"):
            declare_configuration(draft.without_configuration("budget"), "budget",
                                  copy_reference_texts("budget", REFERENCE), ROOT, "test")

    def test_destinations(self):
        draft = complete_draft(ROOT, self.fixtures)
        expected = finalise_campaign(draft, ROOT, self.fixtures).campaign_hash
        for destination, text in ((ROOT / "docs" / "x.campaign.json", "inside the protected"),
                                  (self.out / "x.txt", "a .json document"),
                                  ("", "no destination"),
                                  (self.out / "missing" / "x.json", "does not exist")):
            with self.subTest(destination=destination), self.assertRaisesRegex(CampaignDraftError, text):
                export_campaign_definition(draft, destination, ROOT, self.fixtures, (ROOT,), expected)
        other = self.out / "other.json"
        other.write_text('{"note": "not a definition"}', encoding="utf-8")
        with self.assertRaisesRegex(CampaignDraftError, "never overwritten"):
            export_campaign_definition(draft, other, ROOT, self.fixtures, (ROOT,), expected, overwrite=True)
        target = self.out / "test.campaign.json"
        export_campaign_definition(draft, target, ROOT, self.fixtures, (ROOT,), expected)
        with self.assertRaisesRegex(CampaignDraftError, "explicit confirmation"):
            export_campaign_definition(draft, target, ROOT, self.fixtures, (ROOT,), expected)
        self.assertEqual(export_campaign_definition(draft, target, ROOT, self.fixtures, (ROOT,), expected,
                                                    overwrite=True).reloaded_hash, expected)
        with self.assertRaisesRegex(CampaignDraftError, "protected root could not be determined"):
            check_definition_destination(self.out / "y.json", (None,))

    def test_a_write_error_publishes_nothing(self):
        draft = complete_draft(ROOT, self.fixtures)
        expected = finalise_campaign(draft, ROOT, self.fixtures).campaign_hash
        target = self.out / "locked.campaign.json"
        with mock.patch("services.campaign_finalisation.os.replace", side_effect=PermissionError("locked")):
            with self.assertRaisesRegex(CampaignDraftError, "locked"):
                export_campaign_definition(draft, target, ROOT, self.fixtures, (ROOT,), expected)
        self.assertFalse(target.exists())
        self.assertEqual([p.name for p in self.out.iterdir()], [])  # no partial file left

    def test_data_changed_between_the_check_and_the_save_writes_nothing(self):
        draft = complete_draft(ROOT, self.fixtures)
        with self.assertRaisesRegex(CampaignDraftError, "changed since it was checked"):
            export_campaign_definition(draft, self.out / "a.campaign.json", ROOT, self.fixtures, (ROOT,), "0" * 64)
        root = self.temporary_repository()
        fixtures = load_fixtures(root)
        draft = complete_draft(root, fixtures)
        expected = finalise_campaign(draft, root, fixtures).campaign_hash
        freeze = root / "docs/auto_id/registration_evidence/SP02_registration_reevaluation.json"
        data = json.loads(freeze.read_text(encoding="utf-8"))
        data["results"]["PHYSICAL"]["holdouts"]["holdout_row_ids"] = ["R2"]  # frozen observations changed
        freeze.write_text(json.dumps(data, indent=2), encoding="utf-8")
        with self.assertRaisesRegex(CampaignDraftError, "never substituted"):
            export_campaign_definition(draft, self.out / "b.campaign.json", root, fixtures, (root,), expected)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_a_substituted_registration_is_refused(self):
        root = self.temporary_repository()
        fixtures = load_fixtures(root)
        draft = complete_draft(root, fixtures)
        evidence = root / "docs/auto_id/registration_evidence/SP13_registration_uncertainty.json"
        data = json.loads(evidence.read_text(encoding="utf-8"))
        data["registration_limited"] = True
        evidence.write_text(json.dumps(data, indent=2), encoding="utf-8")
        with self.assertRaises(CampaignDraftError):
            finalise_campaign(draft, root, fixtures)


# ----------------------------------------------------------------------------- pre-run validation


class PrerunTests(_Finalisation):
    def roots(self):
        try:
            return fixture_roots_from_environment()
        except Exception:  # noqa: BLE001
            return None

    def test_sections_of_the_exported_sp02_plus_sp13_definition(self):
        _, finalised, result = self.exported(decision="AUTHORISED: run it now (SUPERVISOR)")
        validation = prerun_validation(result.path, ROOT, self.fixtures, self.roots())
        self.assertEqual(tuple(validation.sections), SECTIONS)
        self.assertEqual(validation.campaign_hash, finalised.campaign_hash)
        self.assertEqual(validation.sections["Definition"], "FORMALLY_VALID")
        self.assertIn(validation.sections["Sources"], ("SHA256_VERIFIED", "NOT_VERIFIED"))
        if self.roots() and "snadwich" in self.roots() and "carbon-project-archive" in self.roots():
            self.assertEqual(validation.sections["Sources"], "SHA256_VERIFIED")
        self.assertEqual(validation.sections["Observations"], "COUNT_CONDITIONS_MET")
        self.assertEqual(validation.sections["Numerical evidence"], "NOT_ASSESSED")
        self.assertEqual(validation.sections["Scientific readiness"], "NOT_EVALUATED")
        self.assertEqual(validation.sections["Execution authorisation"], NOT_AUTHORISED)  # despite the decision text
        self.assertEqual(validation.overall, OVERALL)
        for row in validation.rows:
            self.assertNotIn(row[3], NEVER)
        self.assertIn("NO_GLOBAL_PARAMETER_VALUE", " ".join(r[2] for r in validation.rows))

    def test_files_that_are_not_valid_v1_2_definitions(self):
        broken = self.out / "broken.campaign.json"
        broken.write_text("{ not json", encoding="utf-8")
        validation = prerun_validation(broken, ROOT, self.fixtures, None)
        self.assertEqual(validation.sections["Definition"], "INVALID")
        self.assertEqual(validation.sections["Execution authorisation"], NOT_AUTHORISED)
        historical = prerun_validation(d2f.CAMPAIGNS / "M7_RUN_A.campaign.json", ROOT, self.fixtures, None)
        self.assertEqual(historical.sections["Definition"], "HISTORICAL_V1_SCHEMA")
        self.assertEqual(historical.sections["Sources"], "MISMATCH")

    def test_an_edited_definition_is_not_reproduced_by_the_governed_records(self):
        _, _, result = self.exported()
        data = json.loads(result.path.read_text(encoding="utf-8"))
        for name, change, text in (
                ("promoted_holdout", lambda d: d["specimens"][0]["rows"][2].update(role="FIT"), "specimens"),
                ("other_registration", lambda d: d["specimens"][0].update(
                    registration_evidence=d["specimens"][1]["registration_evidence"]), "specimens"),
                ("legacy_forward_model", lambda d: d["specimens"][0].update(
                    forward_model="docs/auto_id/forward_models/SP02.forward.json"), "")):
            edited = json.loads(json.dumps(data))
            change(edited)
            path = self.out / f"{name}.campaign.json"
            path.write_text(json.dumps(edited, indent=2), encoding="utf-8")
            with self.subTest(name=name):
                validation = prerun_validation(path, ROOT, self.fixtures, None)
                self.assertEqual(validation.sections["Definition"], "FORMALLY_VALID")  # the parser alone accepts it
                self.assertEqual(validation.sections["Sources"], "MISMATCH")
                self.assertIn(text, " ".join(r[2] for r in validation.rows if r[0] == "Sources"))
                self.assertEqual(validation.sections["Observations"], "NOT_EVALUATED")

    def test_a_source_file_with_another_sha_is_a_mismatch(self):
        _, _, result = self.exported()
        with mock.patch.object(prerun_module, "resolve_external_file",
                               side_effect=FixtureSourceMismatchError("SHA-256 differs from the pin")):
            validation = prerun_validation(result.path, ROOT, self.fixtures, {"snadwich": self.out,
                                                                              "carbon-project-archive": self.out})
        self.assertEqual(validation.sections["Sources"], "MISMATCH")
        self.assertTrue(any(r[3] == "MISMATCH" and "SHA-256 differs" in r[2] for r in validation.rows))
        unconfigured = prerun_validation(result.path, ROOT, self.fixtures, None)
        self.assertEqual(unconfigured.sections["Sources"], "NOT_VERIFIED")


# ----------------------------------------------------------------------------- GUI


class GuiTests(_Finalisation):
    def test_finalise_export_and_prerun_through_the_setup_page(self):
        import material_identification_ui as ui
        import test_m8_d1_campaign_draft as d1

        application = d1.GuiTests.application(self)
        buttons = d1.GuiTests.buttons(application)
        for label in ("Finalise & Export Campaign Definition...", "Pre-run Validation..."):
            self.assertIn(label, buttons)
        buttons["Finalise & Export Campaign Definition..."]()  # no draft yet
        self.assertIn("Create Campaign Draft... first", application.material_auto_id_export_label.kwargs["text"])
        application.auto_id_draft = complete_draft(ROOT, self.fixtures, budget=False)
        ui.finalise_and_export_campaign(application, destination=str(self.out / "x.campaign.json"))
        self.assertIn("Not finalised: 2 required campaign input(s) missing",
                      application.material_auto_id_export_label.kwargs["text"])
        application.auto_id_draft = complete_draft(ROOT, self.fixtures)
        with mock.patch.object(ui.filedialog, "asksaveasfilename", return_value=""):
            ui.finalise_and_export_campaign(application)
        self.assertIn("Export cancelled: nothing written", application.material_auto_id_export_label.kwargs["text"])
        self.assertEqual(list(self.out.iterdir()), [])
        target = self.out / "sp02_sp13.campaign.json"
        result = ui.finalise_and_export_campaign(application, destination=str(target))
        self.assertTrue(target.exists() and result.reloaded_hash == result.campaign_hash)
        self.assertIn(result.campaign_hash, application.material_auto_id_export_label.kwargs["text"])
        ui.finalise_and_export_campaign(application, destination=str(target), confirm_overwrite=lambda path: False)
        self.assertIn("not replaced", application.material_auto_id_export_label.kwargs["text"])
        ui.run_prerun_validation(application, path=str(target))
        rows = list(application.material_auto_id_prerun_table.items.values())
        self.assertEqual({r[0] for r in rows}, set(SECTIONS))
        self.assertIn(OVERALL, application.material_auto_id_prerun_label.kwargs["text"])
        with mock.patch.object(ui.filedialog, "askopenfilename", return_value=""):
            ui.run_prerun_validation(application)
        self.assertIn("cancelled", application.material_auto_id_prerun_label.kwargs["text"])


if __name__ == "__main__":
    unittest.main()

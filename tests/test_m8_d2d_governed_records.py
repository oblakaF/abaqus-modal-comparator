"""M8-D2d — Bind Governed Specimen Records: the four governed records of each draft specimen, bound atomically.

A specimen's solver_profile, archived_baseline, baseline_shape_pack and registration_evidence are bound only when every
one has exactly one compatible governed record (production loaders and identity checks); otherwise nothing of that
specimen is bound and the reasons are reported. Never FIT / HOLDOUT rows, parameters, covariance, tolerances or solver
settings, never a readiness verdict, never Abaqus. Saved as auto-id/campaign-draft/v3 and re-verified on reopening;
v1 / v2 drafts open with nothing bound.
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

from domain.campaign_definition import load_campaign_definition  # noqa: E402
from services.archived_baseline import record_hash  # noqa: E402
from services.auto_id_wizard import load_fixtures  # noqa: E402
from services.campaign_draft import (  # noqa: E402
    DRAFT_SCHEMA,
    DRAFT_SCHEMA_V1,
    DRAFT_SCHEMA_V2,
    CampaignDraft,
    CampaignDraftError,
    DraftIncomplete,
    bind_specimen_records,
    draft_from_document,
    governed_specimen_input,
    load_draft,
    write_draft,
)
from services.governed_specimen_records import BOUND, FIELDS, REFUSED, bind_governed_specimen_records  # noqa: E402
import test_m8_d1_campaign_draft as d1  # noqa: E402

FORWARD, CAMPAIGNS, CALIBRATION = d1.FORWARD, d1.CAMPAIGNS, d1.CALIBRATION
SP02 = "docs/auto_id/forward_models/SP02.physical.forward.json"
SP13 = "docs/auto_id/forward_models/SP13.physical.forward.json"
RUN_A = {s["forward_model"]: s for s in json.loads((CAMPAIGNS / "M7_RUN_A.campaign.json").read_text(encoding="utf-8"))
         ["specimens"]}


class _Records(d1._Draft):
    def bound_pair(self):
        draft = self.physical_pair().with_question(CALIBRATION).with_tau_mf(0.02)
        bound, outcomes = bind_specimen_records(draft, ROOT, self.fixtures)
        self.assertEqual([o.status for o in outcomes], [BOUND, BOUND])
        return bound

    def temporary_repository(self) -> Path:
        """A copy of the governed records (docs/) to alter; the repository itself is never written."""
        root = Path(tempfile.mkdtemp(prefix="m8_d2d_repo_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        shutil.copytree(ROOT / "docs", root / "docs")
        return root

    @staticmethod
    def edit_json(path: Path, change) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        change(data)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ----------------------------------------------------------------------------- the accepted references

class ReferenceTests(_Records):
    def test_sp02_and_sp13_bind_exactly_the_accepted_run_a_records(self):
        for forward_model in (SP02, SP13):
            with self.subTest(forward_model=forward_model):
                binding = bind_governed_specimen_records(forward_model, ROOT, self.fixtures)
                self.assertEqual(binding.status, BOUND, binding.reasons)
                self.assertEqual(binding.records.paths(), {name: RUN_A[forward_model][name] for name in FIELDS})
                for name in FIELDS:
                    record = getattr(binding.records, name)
                    self.assertEqual(record.canonical_sha256,
                                     record_hash(json.loads((ROOT / record.path).read_text(encoding="utf-8"))))
                    self.assertEqual(dict(binding.candidates)[name], (record.path,))  # exactly one candidate

    def test_the_draft_binds_only_the_four_records(self):
        draft = self.physical_pair().with_question(CALIBRATION).with_tau_mf(0.02)
        before = {g.field for g in draft.gaps()}
        bound = self.bound_pair()
        after = {g.field for g in bound.gaps()}
        expected = {f"specimens[{i}].{name}" for i in (0, 1) for name in FIELDS}
        self.assertEqual(before - after, expected)  # only the four records, for both specimens
        self.assertTrue({"specimens[0].rows", "specimens[1].rows", "sigma", "bounds", "lm", "fitted_parameters",
                         "start", "abaqus_solve_budget"} <= after)  # rows, parameters, Σ, settings stay missing
        with self.assertRaises(DraftIncomplete):
            bound.finalise()
        for item in bound.intended_definition()["specimens"]:
            self.assertEqual({k: item[k] for k in FIELDS}, {k: RUN_A[item["forward_model"]][k] for k in FIELDS})
            self.assertNotIn("rows", item)
        document = bound.document()
        self.assertEqual((document["schema"], document["status"]), (DRAFT_SCHEMA, "INCOMPLETE"))
        self.assertIn("AUTHORISES_NOTHING", document["labels"])

    def test_a_refused_specimen_is_left_unchanged(self):
        draft = (CampaignDraft().with_specimen(governed_specimen_input(FORWARD / "SP02.forward.json", ROOT,
                                                                        self.fixtures))
                 .with_specimen(self.specimen("SP13.physical.forward.json")))
        bound, outcomes = bind_specimen_records(draft, ROOT, self.fixtures)
        status = {o.forward_model: o for o in outcomes}
        legacy = status["docs/auto_id/forward_models/SP02.forward.json"]
        self.assertEqual(legacy.status, REFUSED)  # its registration has no registration evidence: nothing bound
        self.assertIn("registration_evidence: no compatible record", "; ".join(legacy.reasons))
        self.assertIsNone(bound.specimen_records("docs/auto_id/forward_models/SP02.forward.json"))
        self.assertEqual(status[SP13].status, BOUND)
        self.assertIsNotNone(bound.specimen_records(SP13))


# ----------------------------------------------------------------------------- refusals on altered governed records

class RefusalTests(_Records):
    def assertRefused(self, root: Path, forward_model: str, text: str):
        fixtures = load_fixtures(root)
        binding = bind_governed_specimen_records(forward_model, root, fixtures)
        self.assertEqual(binding.status, REFUSED)
        self.assertIsNone(binding.records)  # atomic: nothing of the specimen is bound
        self.assertIn(text, "; ".join(binding.reasons))
        draft = CampaignDraft().with_specimen(governed_specimen_input(root / forward_model, root, fixtures))
        unchanged, _ = bind_specimen_records(draft, root, fixtures)
        self.assertEqual(unchanged, draft)
        return binding

    def test_zero_compatible_records(self):
        root = self.temporary_repository()
        (root / "docs/auto_id/solver_profiles/SP02.json").unlink()
        self.assertRefused(root, SP02, "solver_profile: no compatible record")

    def test_several_compatible_records_are_never_chosen(self):
        root = self.temporary_repository()
        profiles = root / "docs/auto_id/solver_profiles"
        shutil.copyfile(profiles / "SP02.json", profiles / "A_SP02.json")
        binding = self.assertRefused(root, SP02, "solver_profile: 2 compatible records")
        self.assertEqual(len(dict(binding.candidates)["solver_profile"]), 2)
        self.assertIn("none is chosen", "; ".join(binding.reasons))

    def test_incompatible_solver_profile(self):
        root = self.temporary_repository()
        self.edit_json(root / "docs/auto_id/solver_profiles/SP02.json", lambda d: d.update(job_prefix="SP99"))
        self.assertRefused(root, SP02, "['job_prefix'] differ")

    def test_incompatible_archived_baseline(self):
        root = self.temporary_repository()
        self.edit_json(root / "docs/auto_id/baselines/SP02.carbon4c-baseline.json",
                       lambda d: d["odb"].update(sha256="0" * 64))
        self.assertRefused(root, SP02, "fixture_odb")

    def test_changed_accepted_jobs_accept_no_generated_inp(self):
        root = self.temporary_repository()
        self.edit_json(root / "docs/auto_id/forward_models/accepted_forward_jobs.json",
                       lambda d: d["candidates"][0]["jobs"]["SP02"].update(generated_inp_sha256="1" * 64))
        self.assertRefused(root, SP02, "accepted_forward_jobs.json differs from its pinned content")

    def test_incompatible_registration_evidence(self):
        root = self.temporary_repository()
        self.edit_json(root / "docs/auto_id/registration_evidence/SP02_registration_uncertainty.json",
                       lambda d: d.update(registration_hash="2" * 64))
        self.assertRefused(root, SP02, "registration_evidence: no compatible record")

    def test_a_non_baseline_pack_is_never_a_candidate(self):
        root = self.temporary_repository()
        source = root / "docs/auto_id/fe_shapes/SP02_f3e592281bebce66.shape-pack.json"
        copy = root / "docs/auto_id/fe_shapes/A_SP02_copy.shape-pack.json"
        shutil.copyfile(source, copy)
        self.edit_json(copy, lambda d: d.update(state="E_PLUS"))
        binding = bind_governed_specimen_records(SP02, root, load_fixtures(root))
        self.assertEqual(binding.status, BOUND, binding.reasons)
        self.assertEqual(binding.records.baseline_shape_pack.path,
                         "docs/auto_id/fe_shapes/SP02_f3e592281bebce66.shape-pack.json")


# ----------------------------------------------------------------------------- persistence and compatibility

class PersistenceTests(_Records):
    def test_v3_save_and_reopen(self):
        bound = self.bound_pair().with_campaign_id("M8/D2d").with_run_type("RUN_A")
        path = write_draft(bound, self.out / "draft.json", (ROOT,))
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["schema"], "auto-id/campaign-draft/v3")
        self.assertEqual(document["specimen_records"][0], bound.specimen_records(SP02).to_dict())
        reopened = load_draft(path, ROOT, self.fixtures)
        self.assertEqual(reopened, bound)
        self.assertEqual(reopened.document_bytes(), path.read_bytes())

    def test_v1_and_v2_drafts_open_with_nothing_bound(self):
        draft = self.physical_pair().with_question(CALIBRATION).with_tau_mf(0.02)
        for schema in (DRAFT_SCHEMA_V1, DRAFT_SCHEMA_V2):
            with self.subTest(schema=schema):
                document = draft.document()
                document["schema"] = schema
                document.pop("specimen_records")
                if schema == DRAFT_SCHEMA_V1:
                    document["declared"] = {k: document["declared"][k] for k in ("scientific_question", "tau_mf")}
                reopened = draft_from_document(document, ROOT, self.fixtures)
                self.assertEqual(reopened, draft)
                self.assertEqual(reopened.records, ())  # never inferred
                carrying = dict(document, specimen_records=[None, None])
                with self.assertRaises(CampaignDraftError):
                    draft_from_document(carrying, ROOT, self.fixtures)  # an old version cannot carry bound records

    def test_reopen_reverifies_paths_and_fingerprints(self):
        root = self.temporary_repository()
        fixtures = load_fixtures(root)
        draft = CampaignDraft().with_specimen(governed_specimen_input(root / SP02, root, fixtures))
        bound, _ = bind_specimen_records(draft, root, fixtures)
        document = bound.document()
        tampered = json.loads(json.dumps(document))
        tampered["specimen_records"][0]["solver_profile"]["canonical_sha256"] = "3" * 64
        with self.assertRaises(CampaignDraftError) as caught:
            draft_from_document(tampered, root, fixtures)
        self.assertIn("solver_profile", str(caught.exception))
        self.assertEqual(draft_from_document(document, root, fixtures), bound)
        self.edit_json(root / "docs/auto_id/solver_profiles/SP02.json",
                       lambda d: d.update(provenance=f"{d['provenance']} (altered content)"))  # still compatible
        with self.assertRaises(CampaignDraftError) as caught:
            draft_from_document(document, root, fixtures)
        self.assertIn("canonical SHA-256", str(caught.exception))
        shutil.copyfile(root / "docs/auto_id/solver_profiles/SP02.json", root / "docs/auto_id/solver_profiles/B.json")
        with self.assertRaises(CampaignDraftError) as caught:
            draft_from_document(document, root, fixtures)
        self.assertIn("can no longer be bound", str(caught.exception))


# ----------------------------------------------------------------------------- GUI

class GuiTests(_Records):
    def test_bind_button_shows_bound_and_refused_specimens(self):
        import material_identification_ui as ui

        application = d1.GuiTests.application(self)
        buttons = d1.GuiTests.buttons(application)
        self.assertIn("Bind Governed Specimen Records", buttons)
        buttons["Bind Governed Specimen Records"]()  # no draft yet
        self.assertIn("Create Campaign Draft... first", application.material_auto_id_draft_label.kwargs["text"])
        ui.create_campaign_draft(application)
        ui.add_draft_specimen(application, FORWARD / "SP02.physical.forward.json")
        ui.add_draft_specimen(application, FORWARD / "SP13.forward.json")  # legacy registration: refused
        rows = list(application.material_auto_id_draft_table.items.values())
        self.assertEqual(sum(r[3] == "NOT_BOUND" for r in rows), 2)
        buttons["Bind Governed Specimen Records"]()
        message = application.material_auto_id_draft_label.kwargs["text"]
        self.assertIn(f"Bound the four governed records of {SP02}", message)
        self.assertIn("Not bound (left unchanged)", message)
        self.assertIn("not a scientific readiness verdict", message)
        rows = list(application.material_auto_id_draft_table.items.values())
        bound = [r for r in rows if r[0] == "Bound records" and r[3] == "BOUND"]
        self.assertEqual({r[1] for r in bound}, {f"SP02 {name}" for name in FIELDS})
        self.assertIn(("Bound records", "SP13", "not bound (Bind Governed Specimen Records)", "NOT_BOUND"), rows)
        preview = json.loads(application.material_auto_id_draft_preview_label.kwargs["text"])
        self.assertEqual(preview["specimens"][0]["solver_profile"], RUN_A[SP02]["solver_profile"])
        path = ui.save_campaign_draft(application, self.out / "gui.json")
        ui.discard_campaign_draft(application)
        ui.open_campaign_draft(application, path)
        self.assertIsNotNone(application.auto_id_draft.specimen_records(SP02))

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
        ui.add_draft_specimen(application, FORWARD / "SP13.physical.forward.json")
        ui.bind_draft_specimen_records(application)
        root.update_idletasks()
        table = application.material_auto_id_draft_table
        items = [tuple(str(v) for v in table.item(k, "values")) for k in table.get_children()]
        bound = {row[1] for row in items if row[0] == "Bound records" and row[3] == "BOUND"}
        self.assertEqual(bound, {f"SP13 {name}" for name in FIELDS})
        self.assertIn("Bound the four governed records", application.material_auto_id_draft_label.cget("text"))


# ----------------------------------------------------------------------------- safety

class SafetyTests(_Records):
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
            ui.bind_draft_specimen_records(application)
            ui.save_campaign_draft(application, self.out / "draft.json")
        refuse.assert_not_called()
        self.assertEqual([d1._tree(p) for p in watched], before)
        for name, expected in d1.CAMPAIGN_HASHES.items():
            self.assertEqual(load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json").campaign_hash, expected)


if __name__ == "__main__":
    unittest.main()

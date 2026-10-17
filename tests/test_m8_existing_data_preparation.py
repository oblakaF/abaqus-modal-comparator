"""M8 existing data — accepted FIT / HOLDOUT observations in the campaign draft and the preparation review.

"Bind Accepted FIT / HOLDOUT Observations" binds the strict rows of a specimen's accepted strict freeze exactly as
recorded (roles, families, MAC), only for record-bound specimens whose P11 observation record counts them; nothing is
paired, chosen or entered by hand. Drafts are saved as auto-id/campaign-draft/v5 and the observations are re-verified
on reopening; v1 - v4 drafts open with none. "Review Draft Preparation" reports the SPEC v1.2 §8 counting conditions,
the k = 9 diagnostic, numerical availability (never PASS), the historical result and the parser's finalisation. No
Abaqus, no FE, no LM.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain.modal_input_source import ModalInputSource  # noqa: E402
from services import campaign_observations as observations_service  # noqa: E402
from services.campaign_draft import (  # noqa: E402
    DRAFT_SCHEMA,
    DRAFT_SCHEMA_V4,
    CampaignDraft,
    CampaignDraftError,
    ROWS_NOT_BOUND,
    bind_draft_observations,
    bind_specimen_records,
    draft_from_document,
    governed_specimen_input,
    load_draft,
    write_draft,
)
from services.campaign_observations import (  # noqa: E402
    BOUND,
    INCOMPLETE,
    REFUSED,
    SpecimenObservations,
    bind_specimen_observations,
    draft_preparation_review,
)
from services.archived_sensitivity_evidence import accepted_physical_freeze  # noqa: E402
from services.observation_readiness import (  # noqa: E402
    DataStatus,
    GovernanceItem,
    ReadinessEvidence,
    build_observation_readiness,
    modal_input_item,
)
import test_m8_d1_campaign_draft as d1  # noqa: E402

FORWARD, CAMPAIGNS = d1.FORWARD, d1.CAMPAIGNS
MATERIAL, CALIBRATION = "MATERIAL_IDENTIFICATION", "SPECIMEN_ENGINEERING_CALIBRATION"
SP02 = "docs/auto_id/forward_models/SP02.physical.forward.json"
SP13 = "docs/auto_id/forward_models/SP13.physical.forward.json"
SP02_LEGACY = "docs/auto_id/forward_models/SP02.forward.json"
RUN_A = {s["forward_model"]: s for s in json.loads((CAMPAIGNS / "M7_RUN_A.campaign.json").read_text(encoding="utf-8"))
         ["specimens"]}


class _Observations(d1._Draft):
    def draft(self, *forward_models, question=MATERIAL, run_type="RUN_A", root=ROOT, fixtures=None):
        fixtures = fixtures or self.fixtures
        draft = CampaignDraft().with_question(question).with_run_type(run_type).with_tau_mf(0.01)
        for forward_model in forward_models:
            draft = draft.with_specimen(governed_specimen_input(Path(root) / forward_model, root, fixtures))
        draft, _ = bind_specimen_records(draft, root, fixtures)
        return draft

    def observed(self, *forward_models, **kwargs):
        draft = self.draft(*forward_models, **kwargs)
        bound, outcomes = bind_draft_observations(draft, kwargs.get("root", ROOT), self.fixtures)
        self.assertEqual([o.status for o in outcomes], [BOUND] * len(forward_models),
                         [o.reasons for o in outcomes])
        return bound

    def temporary_repository(self) -> Path:
        root = Path(tempfile.mkdtemp(prefix="m8_existing_repo_"))
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        shutil.copytree(ROOT / "docs", root / "docs")
        return root


# ----------------------------------------------------------------------------- accepted observations


class BindingTests(_Observations):
    def test_sp02_and_sp13_bind_exactly_the_frozen_rows_of_the_accepted_run_a(self):
        draft = self.observed(SP02, SP13)
        for forward_model in (SP02, SP13):
            with self.subTest(forward_model=forward_model):
                bound = draft.specimen_observations(forward_model)
                self.assertEqual(bound.campaign_rows(), RUN_A[forward_model]["rows"])
                freeze = accepted_physical_freeze(bound.fixture_id).freeze
                self.assertEqual([(r.row_id, r.family, r.mac, r.relative_frequency_error) for r in bound.rows],
                                 [(p["row_id"], p["family"], p["mac"], p["relative_frequency_error"])
                                  for p in freeze["strict_pairs"]])  # as frozen: nothing re-paired or rounded
                self.assertEqual([r.row_id for r in bound.rows if r.role == "HOLDOUT"],
                                 freeze["holdouts"]["holdout_row_ids"])  # the freeze's own split
                self.assertEqual([m for m, _ in bound.excluded], [e["experimental_mode"] for e in freeze["excluded"]])
                self.assertEqual(bound.registration_hash, governed_specimen_input(
                    ROOT / forward_model, ROOT, self.fixtures).registration_hash)
        preview = draft.intended_definition()["specimens"]
        self.assertEqual([s["rows"] for s in preview], [RUN_A[SP02]["rows"], RUN_A[SP13]["rows"]])
        self.assertNotIn("specimens[0].rows", [g.field for g in draft.gaps()])

    def test_table_shows_roles_families_mac_frozen_pair_ids_and_exclusions(self):
        from services.campaign_draft import draft_rows

        rows = [r for r in draft_rows(self.observed(SP02)) if r[0] == "Observations"]
        statuses = [r[3] for r in rows]
        self.assertEqual(statuses.count("FIT"), 2)
        self.assertEqual(statuses.count("HOLDOUT"), 1)
        self.assertIn("EXCLUDED", statuses)
        text = " ".join(r[2] for r in rows)
        for expected in ("frozen pair SP02:R1", "family Px:E|Py:E|nx:0|ny:2", "MAC 0.918", "PHYSICAL registration",
                         "SP02_registration_reevaluation.json", "MAC below the policy minimum"):
            self.assertIn(expected, text)

    def test_legacy_registration_is_refused_and_nothing_bound(self):
        draft = self.draft(SP02_LEGACY, question=CALIBRATION)
        bound, outcomes = bind_draft_observations(draft, ROOT, self.fixtures)
        self.assertEqual(bound, draft)
        self.assertEqual(outcomes[0].status, REFUSED)
        reasons = " ".join(outcomes[0].reasons)
        self.assertIn("PREREQUISITE_NOT_GOVERNED", reasons)
        self.assertIn("LEGACY_REPLAY", reasons)
        self.assertIn(ROWS_NOT_BOUND, [g.reason for g in bound.gaps()])

    def test_observations_need_the_records_bound_to_the_draft(self):
        unbound = CampaignDraft().with_specimen(governed_specimen_input(ROOT / SP02, ROOT, self.fixtures))
        binding = bind_specimen_observations(SP02, ROOT, self.fixtures, None)
        self.assertEqual(binding.status, REFUSED)
        self.assertIn("Bind Governed Specimen Records first", binding.reasons[0])
        bound, outcomes = bind_draft_observations(unbound, ROOT, self.fixtures)
        self.assertEqual((bound, outcomes[0].status), (unbound, REFUSED))
        other = self.draft(SP13).specimen_records(SP13)  # another specimen's (valid) records
        mismatch = bind_specimen_observations(SP02, ROOT, self.fixtures, other)
        self.assertEqual(mismatch.status, REFUSED)
        self.assertIn("rests on other", mismatch.reasons[0])

    def test_no_row_can_be_entered_or_moved_by_hand(self):
        draft = self.observed(SP02, SP13)
        sp02 = draft.specimen_observations(SP02)
        with self.assertRaises(CampaignDraftError):
            draft.with_specimen_observations(SP02, sp02.campaign_rows())  # plain rows: refused
        with self.assertRaises(CampaignDraftError):
            draft.with_specimen_observations(SP13, sp02)  # another specimen's observations
        foreign = SpecimenObservations(**{**sp02.__dict__, "registration_evidence": ("x.json", "0" * 64)})
        with self.assertRaises(CampaignDraftError) as caught:
            draft.with_specimen_observations(SP02, foreign)  # another registration
        self.assertIn("registration evidence", str(caught.exception))

    def test_peak_derived_or_unverified_modes_never_become_observations(self):
        """SP-04 dataset-58 FRF peaks (PEAK_DERIVED) and unclassifiable sources are refused like any non-governed
        input: the P11 record does not count them, so nothing is bound."""
        record = observations_service.specimen_observation_readiness(SP02, 1, repo_root=ROOT, fixtures=self.fixtures)
        governed = {name: GovernanceItem(DataStatus(item["status"]), item["detail"])
                    for name, item in record.record["data_governance"].items()}
        for source in (ModalInputSource.PEAK_DERIVED, ModalInputSource.UNKNOWN):
            items = dict(governed, modal_input_source=modal_input_item(source, True, "dataset 58 FRF peaks"))
            evidence = ReadinessEvidence(specimen=record.record["specimen"], sources=record.record["sources"],
                                         items=items, registration_limited=False)
            peaks = build_observation_readiness(evidence, 1)
            with self.subTest(source=source), mock.patch.object(observations_service,
                                                                "specimen_observation_readiness",
                                                                return_value=peaks):
                binding = bind_specimen_observations(SP02, ROOT, self.fixtures,
                                                     self.draft(SP02).specimen_records(SP02))
                self.assertEqual(binding.status, REFUSED)
                self.assertIn("modal_input_source", " ".join(binding.reasons))

    def test_limited_registration_is_refused(self):
        record = observations_service.specimen_observation_readiness(SP02, 1, repo_root=ROOT, fixtures=self.fixtures)
        items = {name: GovernanceItem(DataStatus(item["status"]), item["detail"])
                 for name, item in record.record["data_governance"].items()}
        limited = build_observation_readiness(ReadinessEvidence(record.record["specimen"], record.record["sources"],
                                                                items, True), 1)
        with mock.patch.object(observations_service, "specimen_observation_readiness", return_value=limited):
            binding = bind_specimen_observations(SP02, ROOT, self.fixtures, self.draft(SP02).specimen_records(SP02))
        self.assertEqual(binding.status, REFUSED)
        self.assertIn("REGISTRATION_LIMITED", " ".join(binding.reasons))

    def test_rebinding_other_records_drops_the_observations_and_clearing_removes_them(self):
        draft = self.observed(SP02)
        same = draft.with_specimen_records(SP02, draft.specimen_records(SP02))
        self.assertIsNotNone(same.specimen_observations(SP02))  # the same records: kept
        other = self.draft(SP13).specimen_records(SP13)
        self.assertIsNone(draft.with_specimen_records(SP02, other).specimen_observations(SP02))
        self.assertEqual(draft.without_specimens().observations, ())


# ----------------------------------------------------------------------------- persistence


class PersistenceTests(_Observations):
    def test_v5_save_and_reopen(self):
        draft = self.observed(SP02, SP13).with_campaign_id("M8/existing-data").with_not_fitted("k_int", "OFF")
        path = write_draft(draft, self.out / "draft.json", (ROOT,))
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((document["schema"], DRAFT_SCHEMA), ("auto-id/campaign-draft/v5", "auto-id/campaign-draft/v5"))
        self.assertEqual(document["specimen_observations"][0], draft.specimen_observations(SP02).to_dict())
        reopened = load_draft(path, ROOT, self.fixtures)
        self.assertEqual(reopened, draft)
        self.assertEqual(reopened.document_bytes(), path.read_bytes())

    def test_tampered_observations_are_refused(self):
        document = self.observed(SP02, SP13).document()

        def add_unconfirmed_pair(d):
            row = dict(d["specimen_observations"][0]["rows"][0], row_id="R9", experimental_mode=3, fe_mode=9)
            d["specimen_observations"][0]["rows"].append(row)
            d["intended_campaign_definition"]["specimens"][0]["rows"].append(
                {"row_id": "R9", "experimental_mode": 3, "fe_mode": 9, "role": "FIT"})

        def promote_holdout(d):
            d["specimen_observations"][0]["rows"][2]["role"] = "FIT"
            d["intended_campaign_definition"]["specimens"][0]["rows"][2]["role"] = "FIT"

        for change, text in (
                (add_unconfirmed_pair, "rows"),
                (promote_holdout, "rows"),
                (lambda d: d["specimen_observations"][1]["rows"][0].update(mac=0.99), "rows"),
                (lambda d: d["specimen_observations"][1]["rows"][0].update(family="Px:E|Py:E|nx:0|ny:2"), "rows"),
                (lambda d: d["specimen_observations"][0]["strict_freeze"].update(canonical_sha256="0" * 64),
                 "strict_freeze"),
                (lambda d: d["specimen_observations"][0].update(registration_hash="f" * 64), "registration_hash"),
                (lambda d: d["specimen_observations"][0]["excluded"].clear(), "excluded"),
                (lambda d: d["specimen_observations"].pop(), "one entry"),
                (lambda d: d["intended_campaign_definition"]["specimens"][1]["rows"].pop(), "conflicting draft"),
        ):
            tampered = json.loads(json.dumps(document))
            change(tampered)
            with self.subTest(text=text), self.assertRaises(CampaignDraftError) as caught:
                draft_from_document(tampered, ROOT, self.fixtures)
            self.assertIn(text, str(caught.exception))
        self.assertEqual(draft_from_document(document, ROOT, self.fixtures), self.observed(SP02, SP13))

    def test_reopening_after_the_source_changed_is_refused(self):
        root = self.temporary_repository()
        fixtures = d1.load_fixtures(root)
        draft = self.draft(SP02, root=root, fixtures=fixtures)
        draft, outcomes = bind_draft_observations(draft, root, fixtures)
        self.assertEqual(outcomes[0].status, BOUND)
        path = write_draft(draft, self.out / "draft.json", (root,))
        freeze = root / "docs/auto_id/registration_evidence/SP02_registration_reevaluation.json"
        data = json.loads(freeze.read_text(encoding="utf-8"))
        data["results"]["PHYSICAL"]["holdouts"]["holdout_row_ids"] = ["R2"]  # the accepted split changed
        freeze.write_text(json.dumps(data, indent=2), encoding="utf-8")
        with self.assertRaises(CampaignDraftError) as caught:
            load_draft(path, root, fixtures)
        self.assertIn("never substituted", str(caught.exception))

    def test_v4_drafts_open_with_no_observations(self):
        draft = self.draft(SP02, SP13).with_not_fitted("k_int", "OFF")
        document = draft.document()
        document["schema"] = DRAFT_SCHEMA_V4
        document.pop("specimen_observations")
        reopened = draft_from_document(document, ROOT, self.fixtures)
        self.assertEqual((reopened, reopened.observations), (draft, ()))
        carrying = dict(document, specimen_observations=[None, None])
        with self.assertRaises(CampaignDraftError):
            draft_from_document(carrying, ROOT, self.fixtures)  # a v4 file cannot carry observations

    def test_diagnostic_or_historical_records_are_never_opened_as_drafts(self):
        for path in (CAMPAIGNS / "M7_RUN_A.result.json", CAMPAIGNS / "M7_RUN_A.campaign.json",
                     ROOT / "docs/registrations/SP13_physical_registration.json"):
            with self.subTest(path=path.name), self.assertRaises(CampaignDraftError) as caught:
                load_draft(path, ROOT, self.fixtures)
            self.assertIn("not a campaign draft", str(caught.exception))
        document = self.observed(SP02).document()
        document["labels"] = ["ACCEPTED_CALIBRATION"]
        with self.assertRaises(CampaignDraftError):
            draft_from_document(document, ROOT, self.fixtures)


# ----------------------------------------------------------------------------- preparation review


def _rows(review, section=None):
    return [r for r in review.rows if section is None or r[0] == section]


class ReviewTests(_Observations):
    def test_sp02_plus_sp13_material_identification(self):
        review = draft_preparation_review(self.observed(SP02, SP13), ROOT, self.fixtures)
        counts = {r[1]: r[3] for r in _rows(review, "§8 count")}
        self.assertEqual(counts["SP02 (k = 1)"], "COUNT_CONDITIONS_MET")
        self.assertEqual(counts["SP13 (k = 1)"], "COUNT_CONDITIONS_NOT_MET")
        self.assertEqual(counts["pooled (2 specimens, k = 1)"], "COUNT_CONDITIONS_MET")
        nine = {r[1]: r for r in _rows(review, "§8 count k = 9 (diagnostic)")}
        self.assertEqual({nine["SP02 (k = 9)"][3], nine["SP13 (k = 9)"][3]}, {"COUNT_CONDITIONS_NOT_MET"})
        self.assertIn("INSUFFICIENT_FIT_FAMILIES", nine["SP02 (k = 9)"][2])
        self.assertEqual(nine["Nine-constant identification"][3], "NOT_SUPPORTED")
        numerical = {r[1]: r[3] for r in _rows(review, "Numerical identifiability")}
        self.assertEqual(numerical["Practical rank (M5 RCOND)"], "NOT_ASSESSED")
        self.assertEqual(numerical["Full leave-one-FIT-family-out"], "NOT_ASSESSED")
        self.assertEqual(numerical["Family consistency (SPEC §13)"], "NOT_ASSESSED")
        self.assertEqual(numerical["Experimental covariance Σ_meas"], "NOT_AVAILABLE")
        self.assertEqual(numerical["SP02 numerical sensitivity"], "RECORDED_DIAGNOSTIC_ONLY")
        history = _rows(review, "History")
        self.assertEqual(history[0][3], "UNCHANGED")
        self.assertIn("NO_GLOBAL_PARAMETER_VALUE", history[0][2])
        self.assertEqual(review.verdict, INCOMPLETE)
        self.assertIn("required campaign input(s) missing", review.reasons[0])
        for row in review.rows:  # nothing is ever shown as passed, identified or released
            self.assertNotIn(row[3], ("PASS", "PASSED", "IDENTIFIED", "RELEASED", "READY"))

    def test_sp13_calibration_is_refused_for_insufficient_fit_families(self):
        review = draft_preparation_review(self.observed(SP13, question=CALIBRATION), ROOT, self.fixtures)
        self.assertEqual(review.verdict, INCOMPLETE)
        self.assertIn("SP13: §8 counting conditions not met for k = 1", review.reasons)
        self.assertIn("INSUFFICIENT_FIT_FAMILIES", {r[1]: r[2] for r in _rows(review, "§8 count")}["SP13 (k = 1)"])
        self.assertIn("BLOCKED", [r[3] for r in _rows(review, "Question")])

    def test_sp02_counting_conditions_are_met_but_nothing_is_declared_ready(self):
        review = draft_preparation_review(self.observed(SP02, question=CALIBRATION), ROOT, self.fixtures)
        self.assertEqual({r[1]: r[3] for r in _rows(review, "§8 count")}["SP02 (k = 1)"], "COUNT_CONDITIONS_MET")
        self.assertNotIn("SP02: §8 counting conditions not met for k = 1", review.reasons)
        self.assertEqual(review.verdict, INCOMPLETE)  # numerical inputs, Σ, budget ... are still missing
        self.assertIn("not identifiability", review.summary())

    def test_run_b_counts_two_parameters_and_an_undeclared_run_type_is_a_reason(self):
        review = draft_preparation_review(self.observed(SP02, SP13, run_type="RUN_B"), ROOT, self.fixtures)
        self.assertEqual({r[1]: r[3] for r in _rows(review, "§8 count")}["pooled (2 specimens, k = 2)"],
                         "COUNT_CONDITIONS_NOT_MET")
        draft = CampaignDraft().with_specimen(governed_specimen_input(ROOT / SP02, ROOT, self.fixtures))
        undeclared = draft_preparation_review(draft, ROOT, self.fixtures)
        self.assertIn("run type not declared: k is not determined", undeclared.reasons)

    def test_missing_inputs_are_listed_with_reasons_and_never_filled(self):
        draft = self.observed(SP02, SP13).with_campaign_id("M8/x").with_not_fitted("k_int", "OFF") \
            .with_not_fitted("t_face", "nominal FE geometry").with_not_fitted("k_core", "INP core constants")
        missing = {g.field: g.reason for g in draft.gaps()}
        self.assertEqual(sorted(missing), sorted(["abaqus_solve_budget", "archive_reuse", "bounds", "decision",
                                                  "engineering_plausibility", "fitted_parameters",
                                                  "fixed_parameters", "lm", "parameterisation", "practical_target",
                                                  "provenance", "run_b_gate", "sigma", "start"]))
        self.assertIn("never invented", missing["bounds"])
        self.assertIn("parser rule", missing["fitted_parameters"])
        intended = draft.intended_definition()
        for field in missing:
            self.assertNotIn(field, intended)
        review = draft_preparation_review(draft, ROOT, self.fixtures)
        self.assertEqual(review.verdict, INCOMPLETE)
        self.assertEqual(sum(r[0] == "Missing required inputs" for r in review.rows), len(missing))


# ----------------------------------------------------------------------------- GUI


class GuiTests(_Observations):
    def test_bind_and_review_through_the_setup_page(self):
        import material_identification_ui as ui

        application = d1.GuiTests.application(self)
        buttons = d1.GuiTests.buttons(application)
        for label in ("Bind Accepted FIT / HOLDOUT Observations", "Review Draft Preparation"):
            self.assertIn(label, buttons)
        buttons["Bind Accepted FIT / HOLDOUT Observations"]()  # no draft yet: refused, no crash
        self.assertIn("Create Campaign Draft... first", application.material_auto_id_draft_label.kwargs["text"])
        ui.create_campaign_draft(application)
        ui.declare_draft_question(application, MATERIAL)
        ui.declare_draft_run_type(application, "RUN_A")
        ui.add_draft_specimen(application, ROOT / SP02)
        ui.add_draft_specimen(application, ROOT / SP13)
        buttons["Bind Accepted FIT / HOLDOUT Observations"]()  # records not bound yet: refused
        self.assertIn("Bind Governed Specimen Records first", application.material_auto_id_draft_label.kwargs["text"])
        buttons["Bind Governed Specimen Records"]()
        buttons["Bind Accepted FIT / HOLDOUT Observations"]()
        self.assertIn("2 FIT + 1 HOLDOUT", application.material_auto_id_draft_label.kwargs["text"])
        table = list(application.material_auto_id_draft_table.items.values())
        self.assertEqual(sum(r[0] == "Observations" and r[3] == "FIT" for r in table), 3)
        buttons["Review Draft Preparation"]()
        review = application.material_auto_id_draft_review_label.kwargs["text"]
        self.assertIn("Preparation review: INCOMPLETE", review)
        self.assertTrue(application.material_auto_id_draft_review_table.items)
        ui.declare_draft_tolerance(application, "0.015")  # any change invalidates the review
        self.assertEqual(application.material_auto_id_draft_review_label.kwargs["text"], ui.AUTO_ID_DRAFT_NOT_REVIEWED)
        self.assertFalse(application.material_auto_id_draft_review_table.items)

    def test_review_never_crashes_and_cancelled_open_keeps_the_draft(self):
        import material_identification_ui as ui

        application = d1.GuiTests.application(self)
        ui.review_campaign_draft_preparation(application)  # no draft
        self.assertIn("Create Campaign Draft... first", application.material_auto_id_draft_label.kwargs["text"])
        ui.create_campaign_draft(application)
        draft = application.auto_id_draft
        with mock.patch.object(observations_service, "draft_preparation_review", side_effect=RuntimeError("boom")):
            ui.review_campaign_draft_preparation(application)
        self.assertIn("could not be reviewed (boom)", application.material_auto_id_draft_review_label.kwargs["text"])
        with mock.patch.object(ui.filedialog, "askopenfilename", return_value=""):
            ui.open_campaign_draft(application)
        self.assertIs(application.auto_id_draft, draft)
        self.assertIn("Open cancelled", application.material_auto_id_draft_label.kwargs["text"])


if __name__ == "__main__":
    unittest.main()

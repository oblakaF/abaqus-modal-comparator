"""M8-D2f — complete campaign configuration in the campaign draft (explicit values, no default; no run).

The remaining required fields are declared in five groups (material parameters, uncertainty and acceptance, LM,
budget and archive reuse, decision and provenance) plus the RUN_A "no RUN_B gate". Each value is validated by the
campaign-definition parser's own field validators; the archived M7 RUN_A definition is a reference whose settings may
be copied only by an explicit choice (never its decision, provenance or results). Finalisation is
parse_campaign_definition; a complete definition is neither identifiability nor an authorisation. No Abaqus, FE or LM.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from domain import campaign_definition as domain  # noqa: E402
from domain.campaign_definition import load_campaign_definition, parse_campaign_definition  # noqa: E402
from services import campaign_configuration as configuration  # noqa: E402
from services.campaign_configuration import (  # noqa: E402
    COPYABLE_GROUPS,
    FORM_FIELDS,
    copy_reference_texts,
    declare_configuration,
    reference_configuration,
    reference_source,
    values_from_text,
)
from services.campaign_draft import (  # noqa: E402
    CONFIGURATION_GROUPS,
    CONFIGURATION_KEYS,
    DRAFT_SCHEMA,
    DRAFT_SCHEMA_V5,
    RUN_B_GATE,
    CampaignDraft,
    CampaignDraftError,
    draft_from_document,
    load_draft,
    write_draft,
)
from services.campaign_observations import INCOMPLETE, READY_FOR_REVIEW, draft_preparation_review  # noqa: E402
import test_m8_existing_data_preparation as observed  # noqa: E402

SP02, SP13, MATERIAL, CALIBRATION = observed.SP02, observed.SP13, observed.MATERIAL, observed.CALIBRATION
CAMPAIGNS = observed.CAMPAIGNS
REFERENCE = reference_configuration(ROOT)
PROVENANCE = {"decision": "SUPERVISOR M8-D2f test decision", "provenance": "test entry one\ntest entry two"}


def _rows(review, section):
    return {r[1]: r for r in review.rows if r[0] == section}


class _Configuration(observed._Observations):
    def configured(self, *forward_models, question=MATERIAL, run_type="RUN_A", groups=tuple(CONFIGURATION_GROUPS)):
        draft = self.observed(*forward_models, question=question, run_type=run_type)
        draft = draft.with_campaign_id("M8/D2f/test")
        for key, value in (("t_face", "nominal FE geometry"), ("k_core", "INP core constants"), ("k_int", "OFF")):
            draft = draft.with_not_fitted(key, value)
        for group in groups:
            texts = PROVENANCE if group == "provenance" else copy_reference_texts(group, REFERENCE)
            draft = declare_configuration(draft, group, texts, ROOT, "declared by the test" if group == "provenance"
                                          else reference_source(REFERENCE, edited=False))
        return draft


# ----------------------------------------------------------------------------- one rule: the parser's validators


class ParserRuleTests(_Configuration):
    def test_the_parser_validates_through_the_declared_field_validators(self):
        source = inspect.getsource(parse_campaign_definition)
        for name in ("declared_decision", "declared_parameterisation", "declared_material_parameters",
                     "declared_practical_target", "declared_sigma", "declared_lm", "declared_solve_budget",
                     "declared_run_b_gate", "declared_archive_reuse", "declared_provenance"):
            self.assertIn(f"{name}(", source)
            self.assertTrue(callable(getattr(domain, name)))

    def test_historical_campaign_identities_are_unchanged(self):
        closure = json.loads((CAMPAIGNS / "M7_CLOSURE.json").read_text(encoding="utf-8"))
        for name in ("M7_RUN_A", "M7_RUN_B"):
            definition = load_campaign_definition(CAMPAIGNS / f"{name}.campaign.json")
            result = json.loads((CAMPAIGNS / f"{name}.result.json").read_text(encoding="utf-8"))
            self.assertEqual(result["campaign_hash"], definition.campaign_hash)
        self.assertIn("run_a", closure)

    def test_draft_and_parser_refuse_the_same_values_with_the_same_message(self):
        complete = self.configured(SP02, SP13).with_run_b_gate_none()
        definition = complete.intended_definition()
        parse_campaign_definition(definition)  # the complete definition is accepted
        for group, key, change, text in (
                ("material", "bounds", lambda v: v["bounds"].update(E_in_plane_mpa=[60000.0, 104000.0]),
                 "lies outside the search bounds"),
                ("material", "fitted_parameters", lambda v: v.update(fitted_parameters=["E_in_plane_mpa", "G12_mpa"],
                                                                     fixed_parameters={}), "RUN_A fits"),
                ("material", "parameterisation", lambda v: v.update(parameterisation="carbon/v9"),
                 "unknown parameterisation"),
                ("uncertainty", "practical_target", lambda v: v["practical_target"].update(
                    preferred_max_abs_relative_error=0.2), "preferred ≤ acceptable"),
                ("uncertainty", "sigma", lambda v: v["sigma"]["measurement"].update(status="MEASURED"),
                 "only NOT_AVAILABLE"),
                ("algorithm", "lm", lambda v: v["lm"].update(max_iterations=2.5), "positive integer"),
                ("budget", "abaqus_solve_budget", lambda v: v.update(abaqus_solve_budget=0), "positive integer"),
                ("budget", "archive_reuse", lambda v: v.update(archive_reuse="C:/abs/plan.json"), "POSIX path"),
                ("provenance", "provenance", lambda v: v.update(provenance=[]), "non-empty list")):
            values = {k: json.loads(json.dumps(definition[k])) for k in CONFIGURATION_GROUPS[group]}
            change(values)
            with self.subTest(field=key):
                with self.assertRaises(CampaignDraftError) as draft_refusal:
                    complete.with_configuration(group, values, "test")
                with self.assertRaises(domain.CampaignDefinitionError) as parser_refusal:
                    parse_campaign_definition({**definition, **values})
                self.assertIn(text, str(parser_refusal.exception))
                self.assertIn(str(parser_refusal.exception), str(draft_refusal.exception))


# ----------------------------------------------------------------------------- explicit entry, no default


class EntryTests(_Configuration):
    def test_empty_or_malformed_fields_are_refused_and_nothing_is_filled_in(self):
        for group, fields in FORM_FIELDS.items():
            empty = {field: "" for field, _, _ in fields}
            with self.subTest(group=group), self.assertRaises(CampaignDraftError) as caught:
                values_from_text(group, empty)
            self.assertIn("no default", str(caught.exception))
        texts = dict(copy_reference_texts("algorithm", REFERENCE), **{"lm.max_iterations": "5.0"})
        with self.assertRaisesRegex(CampaignDraftError, "whole number"):
            values_from_text("algorithm", texts)
        texts = dict(copy_reference_texts("material", REFERENCE), start="E_in_plane_mpa=fast")
        with self.assertRaisesRegex(CampaignDraftError, "not a number"):
            values_from_text("material", texts)
        with self.assertRaisesRegex(CampaignDraftError, "every field"):
            values_from_text("budget", {"abaqus_solve_budget": "16"})
        texts = dict(copy_reference_texts("material", REFERENCE), engineering_plausibility="none")
        self.assertEqual(values_from_text("material", texts)["engineering_plausibility"], {})  # explicit "none"

    def test_measurement_uncertainty_is_never_a_number(self):
        values = values_from_text("uncertainty", copy_reference_texts("uncertainty", REFERENCE))
        self.assertEqual(values["sigma"]["measurement"], {"status": "NOT_AVAILABLE",
                                                          "source": REFERENCE["values"]["uncertainty"]["sigma"]
                                                          ["measurement"]["source"]})
        self.assertNotIn("sigma.measurement.status", {f for f, _, _ in FORM_FIELDS["uncertainty"]})

    def test_material_parameters_follow_the_run_type_and_need_it(self):
        draft = self.observed(SP02, SP13, run_type="RUN_A")
        with self.assertRaisesRegex(CampaignDraftError, "declare the run type first"):
            declare_configuration(draft.__class__(specimens=draft.specimens), "material",
                                  copy_reference_texts("material", REFERENCE), ROOT, "test")
        run_b = dict(copy_reference_texts("material", REFERENCE), fitted_parameters="E_in_plane_mpa, G12_mpa",
                     fixed_parameters="none=1", start="E_in_plane_mpa=52000; G12_mpa=4500",
                     bounds="E_in_plane_mpa=26000..104000; G12_mpa=2250..9000")
        with self.assertRaisesRegex(CampaignDraftError, "RUN_A fits E_in_plane_mpa only"):
            declare_configuration(draft, "material", dict(run_b, fixed_parameters="none"), ROOT, "test")
        rb = self.observed(SP02, SP13, run_type="RUN_B")
        with self.assertRaisesRegex(CampaignDraftError, "fix exactly"):
            declare_configuration(rb, "material", run_b, ROOT, "test")  # nothing may be fixed for RUN_B

    def test_run_b_gate_is_none_for_run_a_only_and_never_authorised_by_a_draft(self):
        run_a = self.configured(SP02, SP13, groups=("material",))
        self.assertIn(RUN_B_GATE, run_a.with_run_b_gate_none().configured())
        with self.assertRaisesRegex(CampaignDraftError, "never set by a draft"):
            self.observed(SP02, SP13, run_type="RUN_B").with_run_b_gate_none()
        with self.assertRaisesRegex(CampaignDraftError, "run_b_gate is declared"):
            run_a.without_configuration("material").with_run_b_gate_none().with_run_type("RUN_B")
        with self.assertRaisesRegex(CampaignDraftError, "re-declare the material parameters"):
            run_a.with_run_type("RUN_B")  # RUN_A material parameters do not hold for RUN_B
        gaps = {g.field: g.reason for g in self.observed(SP02, SP13, run_type="RUN_B").gaps()}
        self.assertIn("never set by a draft", gaps[RUN_B_GATE])

    def test_only_settings_are_copied_and_the_copy_is_recorded(self):
        self.assertEqual(COPYABLE_GROUPS, ("material", "uncertainty", "algorithm", "budget"))
        with self.assertRaisesRegex(CampaignDraftError, "never copied"):
            copy_reference_texts("provenance", REFERENCE)
        self.assertIn("copied by an explicit user choice", reference_source(REFERENCE, edited=False))
        self.assertIn("no M7 result carried over", reference_source(REFERENCE, edited=False))
        self.assertIn("edited after an explicit copy", reference_source(REFERENCE, edited=True))
        self.assertNotIn("result.json", inspect.getsource(configuration))  # the reference never reads results


# ----------------------------------------------------------------------------- complete definitions


class DefinitionTests(_Configuration):
    def test_sp02_plus_sp13_material_identification_is_complete_and_accepted_by_the_parser(self):
        draft = self.configured(SP02, SP13).with_run_b_gate_none()
        self.assertEqual(draft.gaps(), ())
        definition = draft.finalise()
        self.assertEqual((definition.schema, definition.scientific_question, definition.run_type),
                         ("auto-id/identification-campaign/v1.2", MATERIAL, "RUN_A"))
        m7 = load_campaign_definition(CAMPAIGNS / "M7_RUN_A.campaign.json")
        self.assertNotEqual(definition.campaign_hash, m7.campaign_hash)  # a new identity, nothing carried over
        self.assertEqual([s.rows for s in definition.specimens], [s.rows for s in m7.specimens])
        review = draft_preparation_review(draft, ROOT, self.fixtures)
        self.assertEqual(review.verdict, READY_FOR_REVIEW)
        definition_rows = _rows(review, "Definition")
        self.assertEqual(definition_rows["Execution"][3], "NOT_AUTHORISED")
        self.assertIn("not identifiability", definition_rows["Execution"][2])
        self.assertIn(definition.campaign_hash, definition_rows["New campaign identity"][2])
        for row in review.rows:
            self.assertNotIn(row[3], ("PASS", "IDENTIFIED", "RELEASED", "AUTHORISED", "EXECUTED"))

    def test_sp13_alone_is_refused_by_the_count_and_the_archive_plan(self):
        draft = self.configured(SP13, question=CALIBRATION, groups=("material", "uncertainty", "algorithm",
                                                                    "provenance"))
        with self.assertRaisesRegex(CampaignDraftError, "names specimens \\['SP02'\\]"):
            declare_configuration(draft, "budget", copy_reference_texts("budget", REFERENCE), ROOT, "test")
        review = draft_preparation_review(draft.with_run_b_gate_none(), ROOT, self.fixtures)
        self.assertEqual(review.verdict, INCOMPLETE)
        self.assertIn("SP13: §8 counting conditions not met for k = 1", review.reasons)
        self.assertEqual(sorted(r[1] for r in review.rows if r[0] == "Missing required inputs"),
                         ["abaqus_solve_budget", "archive_reuse"])

    def test_sp02_alone_meets_the_count_but_has_no_single_specimen_archive_plan(self):
        draft = self.configured(SP02, question=CALIBRATION, groups=("material", "uncertainty", "algorithm",
                                                                    "provenance")).with_run_b_gate_none()
        review = draft_preparation_review(draft, ROOT, self.fixtures)
        self.assertEqual(_rows(review, "§8 count")["SP02 (k = 1)"][3], "COUNT_CONDITIONS_MET")
        self.assertEqual(review.verdict, INCOMPLETE)
        self.assertIn("BLOCKED", [r[3] for r in review.rows if r[0] == "Question"])

    def test_parameterisation_must_be_that_of_every_forward_model(self):
        draft = self.configured(SP02, SP13)

        class Other:
            class parameterisation:
                parameterisation_id = "other/v1"

        with mock.patch.object(configuration, "load_forward_model_manifest", return_value=Other):
            problems = configuration.configuration_problems(draft, ROOT)
        self.assertTrue(any("is not the parameterisation other/v1" in p for p in problems))


# ----------------------------------------------------------------------------- persistence


class PersistenceTests(_Configuration):
    def test_v6_save_and_reopen(self):
        draft = self.configured(SP02, SP13).with_run_b_gate_none()
        path = write_draft(draft, self.out / "draft.json", (ROOT,))
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual((document["schema"], DRAFT_SCHEMA), ("auto-id/campaign-draft/v6",) * 2)
        self.assertEqual(set(document["declared"]["configuration"]), set(CONFIGURATION_KEYS))
        self.assertEqual(document["status"], "COMPLETE_NOT_FINALISED")
        reopened = load_draft(path, ROOT, self.fixtures)
        self.assertEqual(reopened, draft)
        self.assertEqual(reopened.document_bytes(), path.read_bytes())
        self.assertEqual(reopened.finalise().campaign_hash, draft.finalise().campaign_hash)

    def test_tampered_configuration_is_refused(self):
        document = self.configured(SP02, SP13).with_run_b_gate_none().document()

        def edit(path, value):
            def change(d):
                target = d["declared"]["configuration"]
                for key in path[:-1]:
                    target = target[key]
                target[path[-1]] = value
            return change

        for change, text in (
                (edit(("bounds", "value", "E_in_plane_mpa"), [60000.0, 70000.0]), "outside the search bounds"),
                (edit((RUN_B_GATE, "value"), "D-999"), "never carries a RUN_B gate value"),
                (edit(("lm",), None), "incomplete"),
                (lambda d: d["declared"]["configuration_sources"].update(material=None), "incomplete"),
                (edit(("archive_reuse", "value"), "docs/auto_id/campaigns/missing.archive-reuse.json"),
                 "no such file"),
                (lambda d: d["declared"]["configuration"].pop("lm"), "every configuration field"),
                (lambda d: d["intended_campaign_definition"].update(abaqus_solve_budget=99), "conflicting draft"),
        ):
            tampered = json.loads(json.dumps(document))
            change(tampered)
            with self.subTest(text=text), self.assertRaises(CampaignDraftError) as caught:
                draft_from_document(tampered, ROOT, self.fixtures)
            self.assertIn(text, str(caught.exception))

    def test_v5_drafts_open_with_no_configuration(self):
        draft = self.observed(SP02, SP13)
        document = draft.document()
        document["schema"] = DRAFT_SCHEMA_V5
        document["declared"].pop("configuration")
        document["declared"].pop("configuration_sources")
        reopened = draft_from_document(document, ROOT, self.fixtures)
        self.assertEqual((reopened, reopened.configuration), (draft, ()))
        carrying = json.loads(json.dumps(self.configured(SP02, SP13).document()))
        carrying["schema"] = DRAFT_SCHEMA_V5
        with self.assertRaises(CampaignDraftError):
            draft_from_document(carrying, ROOT, self.fixtures)  # a v5 file cannot carry a configuration


# ----------------------------------------------------------------------------- GUI


class GuiTests(_Configuration):
    def test_configuration_through_the_setup_page(self):
        import material_identification_ui as ui
        import test_m8_d1_campaign_draft as d1

        application = d1.GuiTests.application(self)
        buttons = d1.GuiTests.buttons(application)
        for label in ("Declare Material parameters...", "run_b_gate: none (RUN_A)",
                      "Show archived M7 RUN_A settings (reference)"):
            self.assertIn(label, buttons)
        buttons["Show archived M7 RUN_A settings (reference)"]()
        reference = list(application.material_auto_id_reference_table.items.values())
        self.assertTrue(reference and all(r[3] == "REFERENCE_ONLY" for r in reference))
        application.auto_id_draft = self.configured(SP02, SP13, groups=())
        self.assertFalse(ui.declare_draft_configuration(application, "algorithm",
                                                        {f: "" for f, _, _ in FORM_FIELDS["algorithm"]}, "user"))
        self.assertIn("no default", application.material_auto_id_draft_label.kwargs["text"])
        for group in CONFIGURATION_GROUPS:
            texts = PROVENANCE if group == "provenance" else copy_reference_texts(group, REFERENCE)
            self.assertTrue(ui.declare_draft_configuration(application, group, texts, "declared by the user"))
        buttons["run_b_gate: none (RUN_A)"]()
        self.assertEqual(application.auto_id_draft.gaps(), ())
        self.assertIn("accepted by the campaign-definition parser",
                      application.material_auto_id_draft_finalisation_label.kwargs["text"])
        buttons["Review Draft Preparation"]()
        self.assertIn(READY_FOR_REVIEW, application.material_auto_id_draft_review_label.kwargs["text"])
        buttons["Clear Numerical algorithm (LM)"]()
        self.assertEqual([g.field for g in application.auto_id_draft.gaps()], ["lm"])
        self.assertEqual(application.material_auto_id_draft_review_label.kwargs["text"], ui.AUTO_ID_DRAFT_NOT_REVIEWED)


if __name__ == "__main__":
    unittest.main()

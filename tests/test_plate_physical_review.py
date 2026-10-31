"""PRIORITY-9: the Physical Evidence Review of a single plate (services.plate_physical_review) and tab C of the Plate
Study page. Nothing here runs Abaqus, a solver, an LM or Auto-ID; the real-file test is skipped where the verified
copies of the plate's inputs are not on this computer."""

from __future__ import annotations

import csv
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from services import generic_plate_offline_study as off  # noqa: E402
from services import generic_plate_workbench as wb  # noqa: E402
from services import plate_physical_review as pr  # noqa: E402
from services import plate_registration_readiness as rr  # noqa: E402
from services import plate_study as ps  # noqa: E402
from services import research_results_reader as rrr  # noqa: E402

DEMO = ROOT / "docs" / "examples" / "generic_single_plate_demo"
EXP = (18.6307, 54.6193, 63.495, 66.8467, 74.2149, 112.2655, 145.9357, 157.8508, 169.1849, 180.1363, 191.6019)
FE = (19.07217, 59.87416, 62.00917, 71.84985, 72.18999, 116.58043, 167.49026, 168.60799, 174.7977, 179.9016,
      213.19948, 213.95276, 295.77551, 327.90103)
UNV_SHA = "76db80aed1b4ba7062c0bf914cae85b55ea2665d80cb643c8cd54ba6c8bedc4d"
MANIFEST_SHA = "354966dae2126d11610b9fdb56804006b56b40aea1cf7a180278ef375893b4c7"
INP_SHA = "962f75f2fd5d9e6d97578df828599bc150b9777648392b29e8c856546af81df3"
SP13_SHA = "8abf951dba4b8a942922cb4af96074fc1ce8fce2a3f0de8ce082bc5820eeda10"
SIX = ("scanned_face", "grid_plus_v_edge", "scan_window_offsets_mm", "scan_metric_geometry", "fe_origin_corner",
       "fe_normal_face")


def m11_inputs(facts=None, documents=None, **changes) -> pr.ReviewInputs:
    """The M11-261027 review inputs with the recorded identities. No file is read: ``on_disk_sha256`` stands for the
    SHA-256 hashed on disk now (PRIORITY-9-F1: a recorded SHA-256 alone is never a verification)."""
    docs = documents if documents is not None else (
        pr.SourceDocument(pr.EXPERIMENTAL, "", UNV_SHA, 421096, "test", "records", UNV_SHA),
        pr.SourceDocument(pr.FE_MANIFEST, "", MANIFEST_SHA, 1, "test", "FE modes", MANIFEST_SHA))
    inputs = pr.ReviewInputs(pr.M11_261027, tuple(docs), wb.PHYSICAL, "Polymax_bravo",
                             tuple({"number": i + 1, "hz": f, "admissible": True} for i, f in enumerate(EXP)),
                             tuple({"number": i + 7, "hz": f} for i, f in enumerate(FE)), (3, 4, 5, 6), (), "Z",
                             (301.0, 300.0), rr.real_261027_evidence() if facts is None else tuple(facts),
                             pr.APPLICABILITY_261027)
    return replace(inputs, **changes)


def with_fact(facts, key, **changes):
    return tuple(replace(f, **changes) if f.key == key else f for f in facts)


def rows_of(record, fact):
    return [r for r in record["evidence"]["rows"] if r["fact"] == fact]


def demo_study() -> wb.Study:
    study = wb.open_study(DEMO / "DEMO_STUDY.json")
    study = wb.set_diagnostics(study, wb.load_synthetic_inputs(DEMO / "DEMO_SYNTHETIC_INPUTS.json", study))
    return off.with_sensitivities(study, DEMO / "DEMO_SENSITIVITIES.json")


def drop_created(record):
    return {k: v for k, v in record.items() if k != "created"}


def tree_digest(folder: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(folder)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


class IdentityTests(unittest.TestCase):
    def test_the_exact_identities_of_plate_261027_and_m11(self):
        p = pr.M11_261027
        self.assertEqual((p.specimen, p.series, p.modal_set), ("PLATE-300x300x1mm",
                                                               "NEXP29/PLATE300-1MM/S261027-ROTATED", "Polymax_bravo"))
        self.assertEqual((p.experimental_sha256, p.fe_manifest_sha256, p.inp_sha256), (UNV_SHA, MANIFEST_SHA, INP_SHA))
        self.assertEqual((p.records, p.fe_elastic), (11, 14))
        self.assertIn("S4R_0875_BASELINE", p.fe_model)
        record = pr.build_review(m11_inputs())
        self.assertEqual(record["identity"]["experimental_sha256"], UNV_SHA)
        self.assertEqual(record["identity"]["fe_manifest_sha256"], MANIFEST_SHA)
        self.assertEqual(record["states"], {"sources": pr.SOURCES_VERIFIED, "registration": rr.REGISTRATION_NOT_VERIFIED,
                                            "mode_pairs": pr.MODE_PAIRS_NOT_CONFIRMED, "identification": pr.NOT_READY,
                                            "review_package": pr.READY_FOR_OWNER_REVIEW})

    def test_a_foreign_unv_or_fe_manifest_is_refused(self):
        exp = {"sha256": SP13_SHA, "path": "sp13.unv", "size": 1}
        fe = {"sha256": MANIFEST_SHA, "path": "manifest.json", "size": 1}
        for exp_id, fe_id, word in ((exp, fe, "experimental"), ({**exp, "sha256": UNV_SHA}, {**fe, "sha256": "0" * 64},
                                                                 "FE manifest")):
            with self.subTest(word=word), self.assertRaises(pr.ReviewRefused) as caught:
                pr.inputs_from_workspace(object(), fe_id, object(), exp_id, 0)
            self.assertEqual(caught.exception.state, pr.SOURCE_NOT_VERIFIED)
            self.assertIn(word, str(caught.exception))
        foreign = (pr.SourceDocument(pr.EXPERIMENTAL, "", SP13_SHA, 1, "test", "x", SP13_SHA),
                   pr.SourceDocument(pr.FE_MANIFEST, "", MANIFEST_SHA, 1, "test", "y", MANIFEST_SHA))
        with self.assertRaises(pr.ReviewRefused):
            pr.build_review(m11_inputs(documents=foreign))
        with self.assertRaises(pr.ReviewRefused):  # another modal set
            pr.build_review(m11_inputs(modal_set="another"))

    def test_exp1_and_fe7_are_kept_unpaired(self):
        record = pr.build_review(m11_inputs())
        modal = record["modal_evidence"]
        self.assertEqual((modal["experimental_records"], modal["fe_elastic_modes"]), (11, 14))
        exp1 = next(r for r in modal["rows"] if r["record"] == "EXP1")
        fe7 = next(r for r in modal["rows"] if r["record"] == "FE7")
        self.assertEqual((exp1["frequency_hz"], fe7["frequency_hz"]), (18.6307, 19.07217))
        self.assertEqual(exp1["difference_percent"], 2.37)
        self.assertEqual(exp1["diagnostic"], pr.PROXIMITY_ONLY)
        self.assertTrue(exp1["pair"].startswith("NONE"))
        self.assertTrue(any("+2.37 %: FREQUENCY_ONLY_DIAGNOSTIC — not a confirmed pair" in s
                            for s in modal["statements"]))

    def test_261016_and_261027_are_kept_apart(self):
        record = pr.build_review(m11_inputs())
        roles = {(c["series"], c["item"]): c for c in record["test_conditions"]}
        self.assertEqual(roles[("261016", "role")]["status"], ps.HISTORY_ONLY)
        self.assertEqual(roles[("261027", "role")]["status"], ps.PRIMARY_EXPERIMENT)
        self.assertEqual(roles[("261016", "suspension")]["value"], "four rubber bands")
        self.assertEqual(roles[("261027", "suspension")]["value"], "two rubber bands")
        frequencies = [r["frequency_hz"] for r in record["modal_evidence"]["rows"]]
        self.assertNotIn(33.4491, frequencies)  # never a fitting target, never a record of this review
        self.assertTrue(any("Σ_setup repeat" in x for x in record["not_established"]))


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.record = pr.build_review(m11_inputs())

    def test_the_six_open_facts_stay_open(self):
        self.assertEqual(sorted(self.record["evidence"]["open_facts"]), sorted(SIX))
        for fact in ("grid_plus_u_edge", "rotation_reference", "scan_scale", "measured_dof", "fe_x_along_edges"):
            self.assertEqual(rows_of(self.record, fact)[0]["status"], "ESTABLISHED", fact)

    def test_a_relative_side_never_answers_the_absolute_side(self):
        same = rows_of(self.record, "same_face_as_261016")[0]
        self.assertEqual((same["provenance"], same["chain"]), (rr.HUMAN_CONFIRMED, pr.SUPPORTING))
        face = rows_of(self.record, "scanned_face")[0]
        self.assertEqual((face["status"], face["provenance"]), ("OPEN", rr.DERIVED))
        self.assertIn("scanned_face_261016 (CANDIDATE)", face["blocking_reason"])
        ids = [q["id"] for q in self.record["owner_evidence_request"]["questions"]]
        self.assertIn("A1", ids)
        # the ABSOLUTE 261016 face confirmed by the owner closes it through the relative statement (and +v with it)
        facts = with_fact(rr.real_261027_evidence(), "scanned_face_261016", provenance=rr.HUMAN_CONFIRMED)
        closed = pr.build_review(m11_inputs(facts=facts))
        self.assertEqual(sorted(closed["evidence"]["open_facts"]),
                         sorted(set(SIX) - {"scanned_face", "grid_plus_v_edge"}))
        self.assertNotIn("A1", [q["id"] for q in closed["owner_evidence_request"]["questions"]])

    def test_the_unv_grid_is_never_the_physical_window(self):
        grid = rows_of(self.record, "unv_grid_261027")[0]
        self.assertIn("277.7 × 277.0 mm", grid["value"])
        self.assertTrue(grid["status"].startswith("REPRESENTATION"))
        for fact in ("scan_window_offsets_mm", "scan_metric_geometry"):
            self.assertEqual(rows_of(self.record, fact)[0]["status"], "OPEN")
        self.assertIn("B1", [q["id"] for q in self.record["owner_evidence_request"]["questions"]])

    def test_derived_and_candidate_provenance(self):
        face = rows_of(self.record, "scanned_face")[0]
        self.assertEqual(face["dependencies"], "same_face_as_261016, scanned_face_261016")
        candidate = rows_of(self.record, "scanned_face_261016")[0]
        self.assertEqual(candidate["provenance"], rr.CANDIDATE)
        self.assertIn("not evidence by itself", candidate["status"])
        window = rows_of(self.record, "scan_window_offsets_mm")[0]
        self.assertIn("window_offsets_261016 (CANDIDATE)", window["blocking_reason"])
        self.assertTrue(rows_of(self.record, "scan_geometry_261027")[0]["source_sha256"].endswith(UNV_SHA))
        self.assertTrue(rows_of(self.record, "fe_origin_corner")[0]["source_sha256"].endswith(INP_SHA))
        self.assertTrue(rows_of(self.record, "top_edge_261016")[0]["source_sha256"].startswith(pr.NOT_AVAILABLE))

    def test_a_convention_is_never_promoted(self):
        facts = with_fact(rr.real_261027_evidence(), "fe_origin_corner", value=(3, 4), provenance=rr.CONVENTION_ONLY,
                          source="a SUPERVISOR convention (picture D)")
        facts = with_fact(facts, "fe_normal_face", value="marked", provenance=rr.CONVENTION_ONLY, source="convention")
        record = pr.build_review(m11_inputs(facts=facts))
        corner = rows_of(record, "fe_origin_corner")[0]
        self.assertEqual(corner["status"], "OPEN")
        self.assertIn("convention is not physical evidence", corner["blocking_reason"])
        self.assertEqual(record["states"]["registration"], rr.REGISTRATION_NOT_VERIFIED)
        self.assertIn("C2", [q["id"] for q in record["owner_evidence_request"]["questions"]])

    def test_the_owner_questions_are_concrete_and_unanswered(self):
        questions = self.record["owner_evidence_request"]["questions"]
        self.assertEqual([q["id"] for q in questions], ["A1", "A2", "B1", "C1", "C2", "D1", "D2", "D3", "D4"])
        self.assertIn("with the marking or the face without it", questions[0]["question"])
        self.assertIn("300by300_plate_only_1mm_ROTATED_261027.svd", questions[2]["question"])
        self.assertIn("CONVENTION_ONLY", questions[4]["question"])
        for q in questions:
            self.assertIsNone(q["answer"])
            self.assertIsNone(q["evidence_document"])
        self.assertTrue(all("never derived from a measured or FE frequency" in q["acceptable_evidence"]
                            for q in questions if q["group"].startswith("D.")))
        text = pr.owner_request_markdown(self.record)
        self.assertIn("- Answer: \n", text)
        recorded = replace(m11_inputs(), applicability=tuple(a[:5] + ("RECORDED",) for a in pr.APPLICABILITY_261027))
        self.assertFalse([q for q in pr.build_review(recorded)["owner_evidence_request"]["questions"]
                          if q["group"].startswith("D.")])


class ModalAndObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.record = pr.build_review(m11_inputs())

    def test_no_mac_and_no_confirmed_pair(self):
        modal = self.record["modal_evidence"]
        self.assertEqual((modal["pairs"], modal["mac"], modal["fit_holdout"]), ([], "NOT_COMPUTED", "NOT_DECLARED"))
        self.assertTrue(all(r["pair"].startswith("NONE") for r in modal["rows"]))
        researched = [r["research_mac"] for r in modal["rows"] if r["kind"] == "EXP"]
        self.assertTrue(all(m.endswith(pr.RESEARCH_MAC) for m in researched))
        self.assertIn("FE7 0.905", researched[0])
        self.assertNotIn("MATCH_CONFIRMED", json.dumps(self.record))

    def test_fe_only_rank_is_kept_apart_from_experimental_identifiability(self):
        observe = self.record["observability"]
        ranks = {r["parameters"]: (r["rank"], r["of"], r["condition"]) for r in observe["fe_only"]}
        self.assertEqual(ranks["E1 / E2 / G12"], (3, 3, 1.83))
        self.assertEqual(ranks["E (E1 = E2) / G12"], (2, 2, 2.35))
        self.assertTrue(all(r["status"] == pr.FE_ONLY for r in observe["fe_only"]))
        self.assertEqual(observe["experimental"]["status"], "NOT_ASSESSED — NO_ADMISSIBLE_MODAL_OBSERVATIONS")
        self.assertIn("does not say that the experiment determines them", observe["fe_only_statement"])

    def test_the_archived_s4_results_and_branch_loss(self):
        reuse = self.record["sensitivity_reuse"]
        s4 = [r for r in reuse if r["existing_result"].startswith("PRIORITY-2 M11_S4_")]
        self.assertEqual(len(s4), 6)
        plus = next(r for r in s4 if "E1_PLUS" in r["existing_result"])
        self.assertIn("lost: FE8, FE9, FE20", plus["branch_tracking"])
        self.assertIn("FE10→FE11", plus["branch_tracking"])
        g12 = next(r for r in s4 if "G12_MINUS" in r["existing_result"])
        self.assertTrue(g12["branch_tracking"].startswith("14 of 14"))
        joint = next(r for r in reuse if r["existing_result"].startswith("s_E (E1 = E2)"))
        self.assertTrue(joint["reuse_status"].startswith("CONDITIONAL"))
        self.assertIn("not an independently solved E1 = E2 perturbation", joint["reuse_status"])
        fe8 = next(r for r in self.record["modal_evidence"]["rows"] if r["record"] == "FE8")
        self.assertIn("identity lost", fe8["history"])
        self.assertIn({"pair": "FE15 / FE16", "status": "CONFIRMED cluster (one term, mean ln f)"},
                      self.record["modal_evidence"]["archived_clusters"])
        self.assertTrue(any(r["reuse_status"].startswith(pr.NOT_AVAILABLE) for r in reuse
                            if r["existing_result"].startswith("±2.5 %")))

    def test_no_transfer_of_sensitivities_to_another_fe_model(self):
        docs = m11_inputs().documents + (pr.SourceDocument(pr.FE_INP, "", "d" * 64, 1, "test", "INP", "d" * 64),)
        with self.assertRaises(pr.ReviewRefused) as caught:  # PRIORITY-9-F1: a foreign INP refuses the M11 review
            pr.build_review(m11_inputs(documents=docs))
        self.assertIn("FOREIGN", str(caught.exception))
        s4 = [r for r in pr.sensitivity_reuse(m11_inputs(documents=docs), False)
              if r["existing_result"].startswith("PRIORITY-2 M11_S4_")]
        self.assertTrue(all("not applicable" in r["reuse_status"] for r in s4))
        observe = pr.observability(m11_inputs(documents=docs), rrr.load_snapshot(ROOT), False)
        self.assertTrue(all("NOT the current FE model" in r["valid_for"] for r in observe["fe_only"]))

    def test_s0_h1_h2_stay_hypotheses(self):
        hypotheses = {h["scenario"]: h for h in self.record["observability"]["hypotheses"]}
        self.assertEqual(sorted(hypotheses), ["H1", "H2", "S0"])
        self.assertEqual(hypotheses["H1"]["E1_MPa"], 43467.0)
        self.assertTrue(all(h["status"] == pr.HYPOTHESIS_LABELS for h in hypotheses.values()))
        self.assertNotIn("material_values", self.record)

    def test_the_fe_applicability_plan_is_only_a_plan(self):
        plan = self.record["fe_applicability_plan"]
        self.assertEqual(plan["status"], pr.PLAN_ONLY)
        self.assertEqual([v["variant"][0] for v in plan["variants"]], ["A", "B", "C", "D", "E"])
        self.assertIn("history only", plan["variants"][2]["scientific_purpose"])
        self.assertTrue(all(job["authorisation"] == pr.AUTHORISATION and job["run_order"] is False
                            for job in plan["jobs"]))
        self.assertEqual(len(plan["jobs"]), 6)  # B ×2, C ×2 (history), D, E
        self.assertEqual([s["stage"][0] for s in plan["stages"]], ["1", "2", "3", "4", "5"])
        self.assertIn("G12 0 (reuse)", plan["stages"][1]["new_fe_runs"])


class DossierTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)

    def test_the_seven_documents_are_reproducible(self):
        first, second = pr.build_review(m11_inputs()), pr.build_review(m11_inputs())
        self.assertEqual(drop_created(first), drop_created(second))
        one, two = pr.documents(first), pr.documents(second)
        for name in pr.REQUIRED_DOCUMENTS:
            self.assertIn(name, one)
            if name != "physical_readiness.json":
                self.assertEqual(one[name], two[name], name)
        for name in ("evidence_matrix.csv", "modal_observations.csv", "sensitivity_reuse.csv"):
            rows = list(csv.DictReader(io.StringIO(one[name])))
            self.assertTrue(rows, name)
            self.assertTrue(all(r["specimen"] == "PLATE-300x300x1mm" and r["experimental_sha256"] == UNV_SHA
                                and r["fe_manifest_sha256"] == MANIFEST_SHA for r in rows), name)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(one["modal_observations.csv"])))), 25)
        plan = json.loads(one["fe_applicability_plan.json"])
        self.assertEqual(plan["status"], pr.PLAN_ONLY)
        self.assertIn("NOT_ASSESSED — NO_ADMISSIBLE_MODAL_OBSERVATIONS", one["PHYSICAL_READINESS_REPORT.md"])

    def test_the_export_is_atomic_outside_the_program_and_writes_no_fe_file(self):
        record = pr.build_review(m11_inputs())
        with mock.patch("subprocess.Popen") as popen, mock.patch("subprocess.run") as run, \
                mock.patch("services.identification_step.run_bounded_lm", side_effect=AssertionError("no LM")):
            written = pr.export_dossier(record, self.dir)
            popen.assert_not_called()
            run.assert_not_called()
        names = sorted(p.name for p in written)
        self.assertEqual(names, sorted(pr.REQUIRED_DOCUMENTS + ("owner_evidence_request.json",)))
        self.assertFalse([p for p in self.dir.rglob("*") if p.suffix.lower() in (".inp", ".odb", ".dat", ".unv")])
        self.assertEqual(len([p for p in self.dir.iterdir()]), 1)  # one new folder, no temporary left
        again = pr.export_dossier(record, self.dir)
        self.assertNotEqual(again[0].parent, written[0].parent)  # never overwritten
        with self.assertRaises(pr.ExportRefused):
            pr.export_dossier(record, ROOT / "docs")

    def test_a_changed_source_refuses_the_export_and_a_reopened_review(self):
        document = self.dir / "photo.txt"
        document.write_text("marked face visible", encoding="utf-8")
        doc = pr.document(pr.OWNER_DOCUMENT, document, "test", pr.CLAIM_TYPES[0])
        record = pr.build_review(pr.with_document(m11_inputs(), doc))
        audit = {r["role"]: r for r in record["sources"]["audit"]}
        self.assertEqual(audit[pr.OWNER_DOCUMENT]["state"], pr.RECORDED)
        self.assertEqual(record["evidence"]["open_facts"], pr.build_review(m11_inputs())["evidence"]["open_facts"])
        saved = pr.save_review(record, self.dir / "review.json")
        reopened = pr.reopened_state(pr.open_review(saved))
        self.assertEqual(reopened["checks"], [(pr.OWNER_DOCUMENT, str(document), pr.VERIFIED)])
        self.assertFalse(reopened["current"])  # the test sources have no file: never current when reopened
        document.write_text("changed", encoding="utf-8")
        out = self.dir / "out"
        out.mkdir()
        with self.assertRaises(pr.ExportRefused):
            pr.export_dossier(record, out)
        self.assertEqual(list(out.iterdir()), [])
        reopened = pr.reopened_state(pr.open_review(saved))
        self.assertFalse(reopened["current"])
        self.assertIn(pr.SOURCE_NOT_VERIFIED, reopened["state"])
        self.assertIn(f"{pr.OWNER_DOCUMENT} {document}: {pr.CHANGED}", reopened["reasons"])
        self.assertEqual(pr.review_state(record, pr.fingerprint(m11_inputs())), "STALE")
        self.assertEqual(pr.review_state(record, record["fingerprint"]), "CURRENT")
        with self.assertRaises(pr.ExportRefused):
            pr.export_dossier(record, out, current_fingerprint=pr.fingerprint(m11_inputs()))

    def test_the_registrations_and_the_archive_are_unchanged(self):
        before = tree_digest(ROOT / "docs" / "registrations")
        record = pr.build_review(m11_inputs())
        pr.export_dossier(record, self.dir)
        self.assertEqual(tree_digest(ROOT / "docs" / "registrations"), before)
        self.assertTrue(all(row[2] != "CHANGED — not used" and row[2] != pr.MISSING for row in pr.archive_check()))
        self.assertFalse(record["evidence"]["checks"] and any(c["state"] == "FROZEN" for c in record["evidence"]["checks"]))

    def test_another_plate_through_the_generic_contracts(self):
        record = pr.build_review(pr.inputs_from_study(demo_study()))
        text = json.dumps(record, ensure_ascii=False)
        for word in ("M11", "261027", "PLATE-300x300x1mm", "S4R_0875"):
            self.assertNotIn(word, text)
        self.assertEqual(record["identity"]["specimen"], "DEMO-SPB-420x260")
        self.assertEqual(record["states"]["review_package"], pr.SYNTHETIC_ONLY)
        self.assertEqual(record["states"]["mode_pairs"], pr.MODE_PAIRS_NOT_CONFIRMED)
        self.assertIn(wb.SYNTHETIC_LABEL, record["labels"])
        self.assertEqual(record["observability"]["fe_only"][0]["rank"], 2)
        self.assertEqual(record["observability"]["experimental"]["status"], pr.NOT_ASSESSED)
        self.assertEqual(record["modal_evidence"]["experimental_records"], 12)
        written = pr.export_dossier(record, self.dir)
        self.assertEqual(len(written), 8)
        with self.assertRaises(pr.ReviewRefused):
            pr.inputs_from_study(wb.new_study())


# ----------------------------------------------------------------------------- PRIORITY-9-F1: sources and saved dossiers

def physical_study(folder: Path, experimental=True, fe=True, other_set=False) -> wb.Study:
    """A physical study of another plate whose two linked files are real files of ``folder`` (hashed now), with
    diagnostics computed for them and its modal set (``other_set``: the diagnostics belong to another modal set)."""
    sources = {}
    for role, on in (("experimental", experimental), ("fe", fe)):
        if on:
            path = folder / f"{role}.dat"
            path.write_text(f"{role} file of PLATE-Z", encoding="utf-8")
            sources[role] = wb.SourceRecord(role, str(path), hashlib.sha256(path.read_bytes()).hexdigest(),
                                            path.stat().st_size)
    study = wb.new_study()
    study = replace(study, passport=replace(study.passport, physical_specimen_id="PLATE-Z-400x250",
                                            test_run_id="RUN-Z1"),
                    sources=sources, modal_set={"names": ["Set Z", "set-z"], "records": 3})
    diagnostics = wb.modal_diagnostics([{"number": i + 1, "hz": hz} for i, hz in enumerate((20.0, 55.0, 80.0))],
                                       [{"number": i + 7, "hz": hz} for i, hz in enumerate((21.0, 57.0, 83.0))])
    if other_set:
        study = wb.set_diagnostics(replace(study, modal_set={"names": ["Set Y", "set-y"], "records": 3}), diagnostics)
        return replace(study, modal_set={"names": ["Set Z", "set-z"], "records": 3})
    return wb.set_diagnostics(study, diagnostics)


class F1SourceTests(unittest.TestCase):
    """PRIORITY-9-F1: exactly one experimental source and one FE manifest, hashed on disk now, are required."""

    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.dir = Path(folder.name)

    def test_1_only_the_unv_is_not_verified(self):
        record = pr.build_review(pr.inputs_from_study(physical_study(self.dir, fe=False)))
        self.assertEqual(record["states"]["sources"], pr.SOURCE_NOT_VERIFIED)
        self.assertNotEqual(record["states"]["review_package"], pr.READY_FOR_OWNER_REVIEW)
        self.assertIn(f"no {pr.FE_MANIFEST} is linked: exactly one is required", record["sources"]["reasons"])
        with self.assertRaises(pr.ExportRefused):
            pr.export_dossier(record, self.dir)
        with self.assertRaises(pr.ReviewRefused) as caught:  # the M11 review is refused outright
            pr.build_review(m11_inputs(documents=m11_inputs().documents[:1]))
        self.assertEqual(caught.exception.state, pr.SOURCE_NOT_VERIFIED)

    def test_2_only_the_fe_manifest_is_not_verified(self):
        record = pr.build_review(pr.inputs_from_study(physical_study(self.dir, experimental=False)))
        self.assertEqual(record["states"]["sources"], pr.SOURCE_NOT_VERIFIED)
        self.assertIn(f"no {pr.EXPERIMENTAL} is linked: exactly one is required", record["sources"]["reasons"])
        with self.assertRaises(pr.ReviewRefused):
            pr.build_review(m11_inputs(documents=m11_inputs().documents[1:]))
        audit = [r for r in pr.audit_sources(m11_inputs()) if r["role"] == pr.EXPERIMENTAL]
        self.assertEqual(pr.sources_state(audit, wb.PHYSICAL), pr.SOURCE_NOT_VERIFIED)  # an audit without the FE row

    def test_3_both_correct_sources_are_verified(self):
        record = pr.build_review(pr.inputs_from_study(physical_study(self.dir)))
        self.assertEqual(record["states"]["sources"], pr.SOURCES_VERIFIED)
        self.assertEqual(record["states"]["review_package"], pr.READY_FOR_OWNER_REVIEW)
        self.assertEqual(record["sources"]["reasons"], [])
        self.assertEqual(pr.build_review(m11_inputs())["states"]["sources"], pr.SOURCES_VERIFIED)
        # a recorded SHA-256 that was not hashed on disk now is never a verification
        unread = (replace(m11_inputs().documents[0], on_disk_sha256=None), m11_inputs().documents[1])
        with self.assertRaises(pr.ReviewRefused) as caught:
            pr.build_review(m11_inputs(documents=unread))
        self.assertIn(pr.NOT_READ, str(caught.exception))

    def test_4_duplicated_or_contradictory_sources_are_refused(self):
        docs = m11_inputs().documents
        with self.assertRaises(pr.ReviewRefused) as caught:
            pr.build_review(m11_inputs(documents=docs + (docs[0],)))
        self.assertIn("exactly one is required", str(caught.exception))
        study = physical_study(self.dir)
        inputs = pr.inputs_from_study(study)
        with self.assertRaises(pr.ReviewRefused):
            pr.build_review(replace(inputs, documents=inputs.documents + (inputs.documents[1],)))
        changed = (replace(docs[0], on_disk_sha256="0" * 64), docs[1])  # another content at the path now
        with self.assertRaises(pr.ReviewRefused):
            pr.build_review(m11_inputs(documents=changed))
        # the file read in the Workspace is not the file whose SHA-256 was recorded
        exp_preview = mock.Mock(source_path=str(self.dir / "a.unv"))
        fe_preview = mock.Mock(manifest_path=str(self.dir / "manifest.json"))
        with self.assertRaises(pr.ReviewRefused) as caught:
            pr.inputs_from_workspace(fe_preview, {"sha256": MANIFEST_SHA, "path": str(self.dir / "manifest.json")},
                                     exp_preview, {"sha256": UNV_SHA, "path": str(self.dir / "b.unv")}, 0)
        self.assertIn("is not the file whose SHA-256 was recorded", str(caught.exception))

    def test_5_diagnostics_of_another_modal_set_are_not_current(self):
        record = pr.build_review(pr.inputs_from_study(physical_study(self.dir, other_set=True)))
        self.assertEqual(record["states"]["sources"], pr.SOURCE_NOT_VERIFIED)
        self.assertNotEqual(record["states"]["review_package"], pr.READY_FOR_OWNER_REVIEW)
        self.assertTrue(any("computed for other inputs (modal_set)" in r for r in record["sources"]["reasons"]))
        with self.assertRaises(pr.ExportRefused):
            pr.export_dossier(record, self.dir)

    def test_6_a_saved_dossier_with_one_source_is_not_current(self):
        one = pr.build_review(pr.inputs_from_study(physical_study(self.dir, fe=False)))
        state = pr.reopened_state(pr.open_review(pr.save_review(one, self.dir / "one.json")))
        self.assertFalse(state["current"])
        self.assertTrue(state["state"].startswith(pr.NOT_CURRENT))
        self.assertTrue(any("0 recorded with a path" in r for r in state["reasons"]))
        (self.dir / "both").mkdir()
        both = pr.build_review(pr.inputs_from_study(physical_study(self.dir / "both")))
        state = pr.reopened_state(both)
        self.assertEqual(state["state"], pr.NOT_REVALIDATED)  # both verify, but the statuses are the stored ones
        self.assertFalse(state["current"])
        stripped = pr.with_integrity({**both, "sources": {**both["sources"], "audit": [
            r for r in both["sources"]["audit"] if r["role"] != pr.FE_MANIFEST]}})
        self.assertFalse(pr.reopened_state(stripped)["current"])
        self.assertTrue(pr.reopened_state(stripped)["state"].startswith(pr.NOT_CURRENT))

    def test_7_a_manual_status_edit_is_detected(self):
        record = pr.build_review(pr.inputs_from_study(physical_study(self.dir, fe=False)))
        saved = pr.save_review(record, self.dir / "review.json")
        data = json.loads(saved.read_text(encoding="utf-8"))
        data["states"]["sources"] = pr.SOURCES_VERIFIED
        data["states"]["review_package"] = pr.READY_FOR_OWNER_REVIEW
        saved.write_text(json.dumps(data), encoding="utf-8")
        state = pr.reopened_state(pr.open_review(saved))
        self.assertEqual(state["integrity"], pr.MODIFIED)
        self.assertFalse(state["current"])
        self.assertIn(pr.MODIFIED, state["state"])
        with self.assertRaises(pr.ExportRefused):
            pr.export_dossier(data, self.dir)
        # a dossier without an integrity record (RC4) is never more than RECORD_NOT_REVALIDATED
        old = {k: v for k, v in pr.build_review(pr.inputs_from_study(physical_study(self.dir))).items()
               if k != "integrity"}
        state = pr.reopened_state(old)
        self.assertEqual((state["integrity"], state["state"], state["current"]), (pr.NO_INTEGRITY, pr.NOT_REVALIDATED,
                                                                                 False))
        # a recomputation that differs from the stored statuses is NOT_CURRENT (even with a fresh integrity record)
        stored = pr.with_integrity({**pr.build_review(m11_inputs()), "states": {
            **pr.build_review(m11_inputs())["states"], "registration": rr.COMPLETE}})
        check = pr.revalidate(stored, m11_inputs())
        self.assertFalse(check["current"])
        self.assertIn("states", check["reasons"][0])
        self.assertEqual(pr.revalidate(pr.build_review(m11_inputs()), m11_inputs())["state"], pr.REVALIDATED)

    def test_9_the_synthetic_demonstration_keeps_its_own_status(self):
        record = pr.build_review(pr.inputs_from_study(demo_study()))
        self.assertEqual(record["states"]["sources"], "SYNTHETIC_INPUTS")
        self.assertEqual(record["states"]["review_package"], pr.SYNTHETIC_ONLY)
        self.assertEqual(pr.integrity_state(record), pr.INTACT)
        state = pr.reopened_state(record)
        self.assertEqual(state["state"], pr.NOT_REVALIDATED)
        self.assertFalse(state["current"])

    def test_10_no_registration_mac_or_pair_is_created(self):
        before = tree_digest(ROOT / "docs" / "registrations")
        for record in (pr.build_review(m11_inputs()), pr.build_review(pr.inputs_from_study(physical_study(self.dir)))):
            modal = record["modal_evidence"]
            self.assertEqual((modal["pairs"], modal["mac"], modal["fit_holdout"]), ([], "NOT_COMPUTED", "NOT_DECLARED"))
            self.assertNotEqual(record["states"]["registration"], "FROZEN")
            self.assertEqual(record["states"]["mode_pairs"], pr.MODE_PAIRS_NOT_CONFIRMED)
            pr.reopened_state(record)
        self.assertEqual(tree_digest(ROOT / "docs" / "registrations"), before)


# ----------------------------------------------------------------------------- tab C in the window

try:
    from PySide6.QtWidgets import QApplication, QLabel  # noqa: F401
    HAVE_QT = True
except ImportError:  # pragma: no cover
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT or os.environ.get("NEW_GUI_REQUIRE_QT") == "1", "PySide6 is not installed")
class _ReviewWindow(unittest.TestCase):
    def setUp(self):
        from new_gui import window as wm

        self.wm = wm
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        patch = mock.patch.dict(os.environ, {"LOCALAPPDATA": directory.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.app = QApplication.instance() or wm.create_application([])
        self.window = wm.MainWindow(ask_path=lambda kind, start: "")
        self.window.resize(1366, 768)
        self.window.show()
        self.addCleanup(self.window.close)
        self.panel = self.window.review


@unittest.skipUnless(HAVE_QT or os.environ.get("NEW_GUI_REQUIRE_QT") == "1", "PySide6 is not installed")
class PanelTests(_ReviewWindow):
    def test_tab_c_keeps_a_and_b_and_shows_nothing_before_use(self):
        tabs = self.window.plate_tabs
        self.assertEqual([tabs.tabText(i) for i in range(3)], ["A. Current PLATE Study", "B. New Single Plate",
                                                               "C. Physical Readiness"])
        self.assertEqual(tabs.tabToolTip(2), "C. Physical Readiness Review")
        # the smoke found "7. Report _export": "&" is doubled, so it is shown and never a mnemonic
        self.assertEqual(self.panel.step_buttons.button(6).text(), "7. Report && export")
        # the smoke found a page scroll bar at 900 × 680: the claim list never sizes itself to its longest item
        from PySide6.QtWidgets import QComboBox

        combo = self.panel.claim_choice
        self.assertEqual(combo.sizeAdjustPolicy(), QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.assertLessEqual(combo.minimumContentsLength(), 14)
        self.assertTrue(all(label.wordWrap() for label in self.panel.findChildren(QLabel)))
        self.assertFalse(self.panel.export_button.isEnabled())
        self.assertFalse(self.panel.build_from_workspace())  # nothing read in the Workspace
        self.assertIn("SOURCE_NOT_VERIFIED", " ".join(w.text() for w in self.panel.findChildren(QLabel)))
        self.assertFalse(self.panel.export(str(self.dir)))

    def test_a_study_b_review_goes_stale_when_the_study_changes(self):
        with mock.patch("subprocess.Popen") as popen, mock.patch("subprocess.run") as run:
            self.window.workbench.study = demo_study()
            self.assertTrue(self.panel.build_from_study())
            self.assertTrue(self.panel.wait_idle())
            popen.assert_not_called()
            run.assert_not_called()
        self.assertEqual(self.panel.freshness()[0], "CURRENT")
        self.assertEqual(self.panel.tables["modal"].rowCount(), 12 + len(demo_study().diagnostics["fe_elastic"]))
        self.assertIn("questions", self.panel.tables)
        self.assertTrue(self.panel.save_review(str(self.dir / "review.json")))
        self.assertTrue(self.panel.export(str(self.dir)))
        self.assertTrue(self.panel.wait_idle())
        self.assertEqual(len(self.panel.last_export), 8)
        study = self.window.workbench.study
        thicker = tuple(replace(r, thickness=replace(r.thickness, value=r.thickness.value + 0.1))
                        for r in study.passport.thickness)
        self.window.workbench.study = replace(study, passport=replace(study.passport, thickness=thicker))
        self.panel._refresh()
        self.assertEqual(self.panel.freshness()[0], "STALE")
        self.assertNotIn("modal", self.panel.tables)
        self.assertFalse(self.panel.export_button.isEnabled())
        self.assertFalse(self.panel.export(str(self.dir)))
        self.assertTrue(self.panel.open_review(str(self.dir / "review.json")))
        self.assertTrue(self.panel.wait_idle())
        # PRIORITY-9-F1: a reopened synthetic review is shown but its statuses are the stored ones (no recomputation)
        self.assertEqual(self.panel.freshness()[0], pr.NOT_REVALIDATED)
        self.assertIn("modal", self.panel.tables)
        self.assertFalse(self.panel.export_button.isEnabled())
        self.assertIn("(stored, not revalidated)", self.panel.state_labels["review_package"][1].text())


@unittest.skipUnless(HAVE_QT or os.environ.get("NEW_GUI_REQUIRE_QT") == "1", "PySide6 is not installed")
class F1PanelTests(_ReviewWindow):
    def test_incomplete_sources_are_shown_with_their_reason_and_never_exported(self):
        folder = self.dir / "inputs"
        folder.mkdir()
        self.window.workbench.study = physical_study(folder, fe=False)
        self.assertTrue(self.panel.build_from_study())
        self.assertTrue(self.panel.wait_idle())
        labels = {k: label.text() for k, (_caption, label) in self.panel.state_labels.items()}
        self.assertEqual(labels["sources"], f"Sources: {pr.SOURCE_NOT_VERIFIED}")
        self.assertNotIn(pr.READY_FOR_OWNER_REVIEW, labels["review_package"])
        self.assertFalse(self.panel.reasons_line.isHidden())
        self.assertIn(f"no {pr.FE_MANIFEST} is linked", self.panel.reasons_line.text())
        self.assertTrue(self.panel.export(str(self.dir)))  # started; refused in the background, nothing written
        self.assertTrue(self.panel.wait_idle())
        self.assertIn("Not exported (nothing written)", self.panel.export_label.text())
        self.assertEqual([p for p in self.dir.iterdir() if p.name.startswith("physical_readiness")], [])
        # a refused build keeps the review shown before (never lost)
        shown = self.panel.record
        self.window.workbench.study = replace(self.window.workbench.study, passport=replace(
            self.window.workbench.study.passport, physical_specimen_id=""))
        self.assertTrue(self.panel.build_from_study())
        self.assertTrue(self.panel.wait_idle())
        self.assertIs(self.panel.record, shown)
        self.assertEqual(self.panel.freshness()[0], "STALE")
        self.assertIn("Not built", self.panel.message.text())


REAL = Path(r"D:\git\abaqus-modal-comparator-work\research\INTEGRATION_RC1_REVIEW\moved inputs")
REAL_UNV = REAL / "EXP delivery copy" / "SPname_files_ROTATED_261028" / "300by300_plate_only_1mm_ROTATED_Polytec_261027.unv"
REAL_FE = REAL / "FE package copy" / "manifest.json"


@unittest.skipUnless(REAL_UNV.is_file() and REAL_FE.is_file() and HAVE_QT, "the verified copies of the plate's inputs "
                     "are not on this computer")
class RealInputsTests(unittest.TestCase):
    def test_the_review_of_the_real_261027_and_m11_copies(self):
        from new_gui import preview_model as pm
        from new_gui import workspace_state as ws

        fe = pm.read_preview(ws.FE, REAL_FE)
        exp = pm.read_preview(ws.EXPERIMENTAL, REAL_UNV)
        inputs = pr.inputs_from_workspace(fe, pm.file_identity(REAL_FE), exp, pm.file_identity(REAL_UNV), 0)
        record = pr.build_review(inputs)
        self.assertEqual(record["states"]["sources"], pr.SOURCES_VERIFIED)
        self.assertEqual(sorted(record["evidence"]["open_facts"]), sorted(SIX))
        self.assertEqual(record["modal_evidence"]["experimental_records"], 11)
        self.assertEqual(record["modal_evidence"]["fe_elastic_modes"], 14)
        self.assertAlmostEqual(record["modal_evidence"]["rows"][0]["frequency_hz"], 18.6307, places=4)
        fe7 = next(r for r in record["modal_evidence"]["rows"] if r["record"] == "FE7")
        self.assertAlmostEqual(fe7["frequency_hz"], 19.07217, places=4)
        # PRIORITY-9-F1 (8): saved and reopened, it is recomputed from its two verified files and equals the stored one
        with tempfile.TemporaryDirectory() as folder:
            saved = pr.save_review(record, Path(folder) / "review.json")
            reopened = pr.open_review(saved)
            state = pr.reopened_state(reopened)
            self.assertTrue(state["revalidable"], state)
            kinds = {pr.EXPERIMENTAL: ws.EXPERIMENTAL, pr.FE_MANIFEST: ws.FE}
            again = pr.revalidation_inputs(reopened, lambda role, path, cancel: pm.read_preview(kinds[role], path, cancel),
                                           lambda path, cancel: pm.file_identity(path, cancel))
            self.assertEqual(pr.revalidate(reopened, again)["state"], pr.REVALIDATED)


if __name__ == "__main__":
    unittest.main()

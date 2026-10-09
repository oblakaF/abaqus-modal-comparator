"""SPEC v1.2 normative promotion (D-078) — documentation / policy checks only.

``SPEC_V1_2.md`` must be the governing, normative contract whose rule sections are exactly the reviewed final policy
(PR #41 head 62903ef); the policy history must be kept unchanged apart from its superseded notice; SPEC v1.1,
DECISIONS history and the M7 records must stay unchanged; and no v1.2 implementation may have entered ``src`` yet
(implementation status POLICY_ACCEPTED, IMPLEMENTATION_NOT_STARTED).
"""

from __future__ import annotations

import hashlib
import itertools
import json
from pathlib import Path
import re
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from domain.identification_run import canonical_hash


DOCS = ROOT / "docs" / "auto_id"
REVIEWED_HEAD = "62903ef899122de9a3585d6cf6551d03442b97e5"  # PR #41
MERGE_COMMIT = "edb3070d2ed5b385f7152b3041ca3e297bdc8423"
# LF-normalised content hashes of the reviewed final policy (PR #41 head) and of the pre-D-078 history
REVIEWED_DRAFT_SHA256 = "1719c592305bcdad3f257a638280d7ccff194c581ff85af635cb302b05f86e4d"
REVIEWED_REVIEW_SHA256 = "0a1d0d36d0b55d62846833eda33ed7268e6050a076f8f6aecdbf8a8afd75f905"
REVIEWED_OPTIONS_CANONICAL_SHA256 = "4ea4dc92ce0e24f9e22625d44b7380ddb2ace2c52d039cf956997bcf3d2af003"
DECISIONS_BEFORE_D078_SHA256 = "257b84a83e156211fe00e5d0f2d69428e0acadc11bc3dfd817536151c574ba10"
SPEC_V1_1_CONTENT_SHA256 = "62f206176a73c224f6f8fea0b2aed84c8154b9eb30bee87240d2c0b808ebb665"
SUPERSEDED = "> **SUPERSEDED_BY_NORMATIVE_SPEC_V1_2**"
# Implemented V12 steps: schema (I1) and τ_mf-aware pattern / holdout test (I2); confined there by the I1 tests.
V12_MODULES = ("domain/campaign_definition.py", "services/identification_uncertainty.py",
               "services/identification_verdict.py", "services/identification_campaign_run.py")


def _text(name: str) -> str:
    return (DOCS / name).read_text(encoding="utf-8").replace("\r\n", "\n")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _without_notice(text: str) -> str:
    assert text.startswith(SUPERSEDED)
    return text.split("\n\n", 1)[1]


def _sections(text: str) -> dict:
    parts = re.split(r"^## (\d+)\. .*$", text, flags=re.MULTILINE)
    return {int(number): body for number, body in zip(parts[1::2], parts[2::2])}


class NormativeSpecTests(unittest.TestCase):
    def setUp(self):
        self.spec = _text("SPEC_V1_2.md")

    def test_spec_v1_2_has_normative_status(self):
        header = self.spec.split("**Freeze rule.**", 1)[0]
        for row in ("| Version | 1.2 |", "| Status | **NORMATIVE.**", "| Accepted | SUPERVISOR, 2026-10-09 |",
                    "| Decision | D-078 |", "| Normative predecessor | [SPEC_V1_1.md](SPEC_V1_1.md)",
                    "| Scientific origin | External audit iteration 2", "IMPLEMENTATION_NOT_STARTED"):
            self.assertIn(row, header)
        self.assertIn(REVIEWED_HEAD, header)
        self.assertIn(MERGE_COMMIT, header)
        for forbidden in ("DRAFT", "PROPOSED", "AWAITING ACCEPTANCE", "NOT NORMATIVE"):
            self.assertNotIn(forbidden, self.spec.upper())

    def test_accepted_rules_equal_the_reviewed_final_policy(self):
        reviewed = _without_notice(_text("SPEC_V1_2_DRAFT.md"))
        self.assertEqual(_sha256(reviewed), REVIEWED_DRAFT_SHA256)
        normative_sections, reviewed_sections = _sections(self.spec), _sections(reviewed)
        self.assertEqual(sorted(normative_sections), list(range(1, 14)))
        self.assertEqual(sorted(reviewed_sections), list(range(1, 14)))
        for number in range(1, 14):
            with self.subTest(section=number):
                self.assertEqual(normative_sections[number], reviewed_sections[number])
        freeze = reviewed[reviewed.index("**Freeze rule.**"):reviewed.index("## 1. ")]
        self.assertIn(freeze, self.spec)
        for rule in ("τ_mf ≤ **0.02**", "**No automatic fallback.**",
                     "calibration precision gate: conservative_uncertainty ≤ 0.08",
                     "τ_mf can never convert family_consistency FAIL into PASS"):
            self.assertIn(rule, " ".join(self.spec.split()))

    def test_policy_history_is_kept_unchanged_apart_from_the_superseded_notice(self):
        self.assertEqual(_sha256(_without_notice(_text("SPEC_V1_2_POLICY_REVIEW.md"))), REVIEWED_REVIEW_SHA256)
        options = json.loads(_text("SPEC_V1_2_POLICY_OPTIONS.json"))
        self.assertEqual(options["historical_status"], "SUPERSEDED_BY_NORMATIVE_SPEC_V1_2")
        self.assertEqual(options["superseded_by"]["decision"], "D-078")
        reviewed = {k: v for k, v in options.items()
                    if k not in ("historical_status", "superseded_by", "historical_note")}
        self.assertEqual(canonical_hash(reviewed), REVIEWED_OPTIONS_CANONICAL_SHA256)

    def test_spec_v1_1_and_decision_history_are_unchanged(self):
        self.assertEqual(_sha256(_text("SPEC_V1_1.md")), SPEC_V1_1_CONTENT_SHA256)
        decisions = _text("DECISIONS.md")
        before, d078 = decisions.split("\n## D-078", 1)
        self.assertEqual(_sha256(before), DECISIONS_BEFORE_D078_SHA256)
        self.assertNotIn("\n## D-", d078)  # D-078 is the last entry
        for phrase in ("SPEC v1.2 is accepted as normative", "SPEC v1.1 remains archived and immutable",
                       "No automatic fallback", "τ_mf maximum 0.02", "Production implementation is NOT part of D-078",
                       "No Abaqus was run"):
            self.assertIn(phrase, " ".join(d078.split()))

    def test_governance_points_to_spec_v1_2_without_claiming_implementation(self):
        status = json.loads(_text("STATUS.json"))
        self.assertEqual(status["governing_spec"], "docs/auto_id/SPEC_V1_2.md")
        self.assertIn("IMPLEMENTATION_INCOMPLETE", status["spec_v1_2_policy"]["implementation_status"])
        track = status["spec_v1_2_implementation"]
        self.assertEqual(track["status"], "IN_PROGRESS")
        self.assertEqual(sorted(track["steps"]), [f"V12-I{i}" for i in range(1, 7)])
        # Roadmap order: an ACCEPTED prefix, then at most one step under work (never self-ACCEPTED), the rest TODO.
        states = [track["steps"][f"V12-I{i}"]["status"] for i in range(1, 7)]
        accepted = len(states) - len(list(itertools.dropwhile(lambda s: s == "ACCEPTED", states)))
        rest = states[accepted:]
        self.assertTrue(rest and all(s == "TODO" for s in rest[1:]), states)
        self.assertIn(rest[0], ("TODO", "IN_PROGRESS", "REVIEW_READY", "REWORK"))
        self.assertEqual((status["m8"]["status"], status["m8"]["parked_branch"]["commit"]),
                         ("NOT_STARTED", "193db8dd4dd31c88ea1eae0a905f372e8a00c31d"))
        self.assertIn("| [SPEC_V1_2.md](SPEC_V1_2.md) | Governing scientific contract (normative, D-078)",
                      _text("README.md"))
        for agent_doc in ("CLAUDE.md", "AGENTS.md"):
            text = (ROOT / agent_doc).read_text(encoding="utf-8")
            with self.subTest(document=agent_doc):
                self.assertIn("1. `docs/auto_id/SPEC_V1_2.md`: governing scientific contract", text)

    def test_no_v1_2_implementation_in_src_and_m7_records_unchanged(self):
        for path in (ROOT / "src").rglob("*.py"):
            if path.relative_to(ROOT / "src").as_posix() in V12_MODULES:
                continue  # V12-I1 schema / V12-I2 pattern test (tests/test_v12_i1_campaign_question.py)
            text = path.read_text(encoding="utf-8")
            with self.subTest(module=path.name):
                # (the M7b label DIAGNOSTIC_OPTIMIZER_CANDIDATE_NOT_RELEASED predates v1.2 and is not a marker)
                for token in ("tau_mf", "SPECIMEN_ENGINEERING_CALIBRATION",
                              "UNCERTAINTY_CONDITIONAL_ON_AVAILABLE_COVARIANCE"):
                    self.assertNotIn(token, text)
        closure = json.loads(_text("campaigns/M7_CLOSURE.json"))
        for key, name in (("run_a", "M7_RUN_A.result.json"), ("run_b", "M7_RUN_B.result.json")):
            record = json.loads(_text(f"campaigns/{name}"))
            with self.subTest(run=key):
                self.assertEqual(canonical_hash(record), closure[key]["result_record"]["canonical_content_sha256"])


if __name__ == "__main__":
    unittest.main()

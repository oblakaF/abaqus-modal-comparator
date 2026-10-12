"""G2 frequency precision fix: extracted ODB frequencies come from the EIGFREQ history when identity is unambiguous.

The Windows GUI smoke test (SP-02, a34dd17) showed that the frame frequency of an Abaqus frequency step is reported
with 5-6 significant digits (mode 13: 207.43 Hz) while the accepted records carry the solver's single-precision value
(207.4272918701172 Hz). The unchanged G2c mode-identity check (relative 1e-6) therefore refused the R3 HOLDOUT row.
The loader now takes the EIGFREQ history value, matched by mode number only, when it is consistent with the frame
frequency and with EIGVAL; otherwise the frame frequency stays. The SP-02 what-if refuses a partial FIT/HOLDOUT preview.
"""

from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from abaqus_bridge import (  # noqa: E402
    FREQUENCY_SOURCE_FRAME,
    FREQUENCY_SOURCE_HISTORY,
    history_frequencies,
    load_extracted_odb,
)
from services import archived_sensitivity_evidence as ev  # noqa: E402
from services import sensitivity_what_if as wi  # noqa: E402
from test_g2d2_e_what_if import predicted, recorded_sp02_evidence  # noqa: E402

# The real SP-02 values of the smoke-test extraction (frame frequency as reported, EIGFREQ as stored).
FRAME = {8: 75.241, 10: 89.327, 13: 207.43}
EIGFREQ = {1: 0.0, 7: 23.572078704833984, 8: 75.24107360839844, 9: 78.25013732910156, 10: 89.32708740234375,
           11: 90.54397583007812, 12: 144.1766815185547, 13: 207.4272918701172, 14: 210.8242645263672}
SMOKE_MANIFEST = Path(r"D:\git\abaqus-modal-comparator-work\scratch\smoke_g2d2\output\analysis_b291fe42c50749d0"
                      r"\abaqus\manifest.json")


def history(name, values, order=sorted):
    return {"region": "Assembly ASSEMBLY", "name": name, "description": name,
            "data": [[float(mode), value] for mode, value in ((m, values[m]) for m in order(values))]}


def eigval(values):
    return {mode: (2.0 * math.pi * f) ** 2 for mode, f in values.items()}


def manifest(histories, frames=FRAME):
    return {"modes": [{"mode": m, "frequency_hz": f} for m, f in frames.items()], "history": histories}


class HistoryMappingTests(unittest.TestCase):
    def test_full_precision_matched_by_mode_number_not_by_order(self):
        for order in (sorted, lambda values: sorted(values, reverse=True)):
            accepted, kept = history_frequencies(
                manifest([history("EIGFREQ", EIGFREQ, order), history("EIGVAL", eigval(EIGFREQ), order)]), FRAME)
            self.assertEqual(accepted, {8: EIGFREQ[8], 10: EIGFREQ[10], 13: EIGFREQ[13]})
            self.assertEqual(kept, {})

    def test_eigval_is_optional(self):
        accepted, _ = history_frequencies(manifest([history("EIGFREQ", EIGFREQ)]), FRAME)
        self.assertEqual(set(accepted), {8, 10, 13})

    def test_missing_history_or_mode_keeps_the_frame_frequency(self):
        accepted, kept = history_frequencies(manifest([]), FRAME)
        self.assertEqual((accepted, set(kept)), ({}, {8, 10, 13}))
        self.assertIn("no EIGFREQ history", kept[13])
        partial = {m: v for m, v in EIGFREQ.items() if m != 13}
        accepted, kept = history_frequencies(manifest([history("EIGFREQ", partial)]), FRAME)
        self.assertEqual(set(accepted), {8, 10})
        self.assertIn("not in the EIGFREQ history", kept[13])

    def test_duplicate_or_multiple_or_malformed_histories_are_not_used(self):
        duplicate = history("EIGFREQ", EIGFREQ)
        duplicate["data"].append([13.0, 207.4272918701172])
        malformed = history("EIGFREQ", EIGFREQ)
        malformed["data"][0] = [1.5, 0.0]
        cases = {
            "repeats mode 13": [duplicate],
            "2 EIGFREQ histories": [history("EIGFREQ", EIGFREQ), history("EIGFREQ", EIGFREQ)],
            "not (mode number": [malformed],
            "list different modes": [history("EIGFREQ", EIGFREQ),
                                      history("EIGVAL", eigval({m: v for m, v in EIGFREQ.items() if m != 9}))],
        }
        for reason, histories in cases.items():
            with self.subTest(reason=reason):
                accepted, kept = history_frequencies(manifest(histories), FRAME)
                self.assertEqual(accepted, {})
                self.assertIn(reason, kept[13])

    def test_contradictory_history_is_never_substituted(self):
        contradictory = {**EIGFREQ, 13: 210.82}  # e.g. a shifted / reordered history
        accepted, kept = history_frequencies(manifest([history("EIGFREQ", contradictory)]), FRAME)
        self.assertEqual(set(accepted), {8, 10})
        self.assertIn("contradicts the frame frequency", kept[13])
        wrong_eigval = eigval(EIGFREQ)
        wrong_eigval[10] *= 1.001
        accepted, kept = history_frequencies(
            manifest([history("EIGFREQ", EIGFREQ), history("EIGVAL", wrong_eigval)]), FRAME)
        self.assertEqual(set(accepted), {8, 13})
        self.assertIn("EIGVAL of mode 10 contradicts", kept[10])

    def test_ambiguous_frame_frequency_keeps_the_frame_value(self):
        close = {**EIGFREQ, 14: 207.4268}  # also rounds to the reported 207.43
        accepted, kept = history_frequencies(manifest([history("EIGFREQ", close)]), FRAME)
        self.assertNotIn(13, accepted)
        self.assertIn("also matches another EIGFREQ mode", kept[13])


def _write_package(root: Path, histories) -> Path:
    (root / "geometry.csv").write_text("instance,node_label,x,y,z\nPART-1,1,0,0,0\nPART-1,2,1,0,0\n",
                                       encoding="utf-8")
    entries = []
    for mode, frame in FRAME.items():
        name = f"mode_{mode:04d}.csv"
        (root / name).write_text("instance,node_label,u1_real,u2_real,u3_real,u1_imag,u2_imag,u3_imag\n"
                                 f"PART-1,1,0,0,{mode},0,0,0\nPART-1,2,0,0,-1,0,0,0\n", encoding="utf-8")
        entries.append({"mode": mode, "frequency_hz": frame, "file": name, "frame_index": mode,
                        "description": f"Mode {mode}: Freq = {frame}"})
    path = root / "manifest.json"
    path.write_text(json.dumps({"format_version": 2, "geometry_file": "geometry.csv", "step_name": "Modal",
                                "start_mode": 8, "end_mode": 13, "modes": entries, "history": histories}),
                    encoding="utf-8")
    return path


class LoaderTests(unittest.TestCase):
    def test_loader_uses_history_frequencies_and_keeps_the_frame_value(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = load_extracted_odb(_write_package(Path(directory), [history("EIGFREQ", EIGFREQ),
                                                                          history("EIGVAL", eigval(EIGFREQ))]))
        by_number = {mode.number: mode for mode in dataset.modes}
        for number, frame in FRAME.items():
            self.assertEqual(by_number[number].frequency_hz, EIGFREQ[number])
            self.assertEqual(by_number[number].metadata["frame_frequency_hz"], frame)
            self.assertEqual(by_number[number].metadata["frequency_source"], FREQUENCY_SOURCE_HISTORY)
        self.assertEqual(dataset.metadata["frequency_sources"], {"history_modes": [8, 10, 13], "frame_modes": {}})

    def test_manifest_without_history_keeps_existing_behaviour(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = load_extracted_odb(_write_package(Path(directory), []))
        for mode in dataset.modes:
            self.assertEqual(mode.frequency_hz, FRAME[mode.number])  # exactly the frame value, as before
            self.assertEqual(mode.metadata["frequency_source"], FREQUENCY_SOURCE_FRAME)
            self.assertEqual(mode.metadata["frequency_history_note"], "no EIGFREQ history")


class G2cIdentityTests(unittest.TestCase):
    def test_strict_identity_tolerance_is_unchanged(self):
        self.assertEqual(ev.FREQUENCY_IDENTITY_RELATIVE, 1.0e-6)
        recorded = EIGFREQ[13]
        self.assertFalse(ev._same_frequency(FRAME[13], recorded))  # the rounded frame value is still refused
        self.assertTrue(ev._same_frequency(EIGFREQ[13], recorded))  # the full-precision history value passes
        for mode in (8, 10):
            self.assertTrue(ev._same_frequency(EIGFREQ[mode], EIGFREQ[mode]))


class WhatIfCompletenessTests(unittest.TestCase):
    def test_r3_holdout_prediction_with_complete_evidence(self):
        evidence = recorded_sp02_evidence()
        for change, expected in ((0.0, EIGFREQ[13]), (-0.02, EIGFREQ[13] * 0.98 ** 0.4837071900148189),
                                 (0.02, EIGFREQ[13] * 1.02 ** 0.4837071900148189)):
            result = wi.e_what_if(evidence, change)
            self.assertEqual(result.status, wi.AVAILABLE)
            r3 = predicted(result)["R3"]
            self.assertEqual(r3.role, "HOLDOUT")
            self.assertAlmostEqual(r3.trial_hz, expected, places=10)

    def test_partial_strict_evidence_is_incomplete_not_a_preview(self):
        complete = recorded_sp02_evidence()
        for missing in ("R3", "R1"):
            with self.subTest(missing=missing):
                evidence = replace(complete, rows=tuple(
                    replace(row, applicable=False, s_e=None, s_g12=None,
                            reason="FE mode 13 of the comparison is missing or not the recorded mode (207.4273 Hz).")
                    if row.row_id == missing else row for row in complete.rows))
                result = wi.e_what_if(evidence, 0.02)
                self.assertEqual(result.status, wi.INCOMPLETE)
                self.assertEqual(result.rows, ())  # no partial FIT/HOLDOUT preview
                self.assertIsNone(result.e_trial_mpa)
                self.assertIn(f"{missing} (", result.reason)
                self.assertIn("a partial FIT/HOLDOUT preview is not shown", result.reason)
                self.assertIn(wi.INCOMPLETE, wi.summary_text(result))
                self.assertFalse(result.mixed)

    def assertIncomplete(self, rows, text: str) -> None:
        result = wi.e_what_if(replace(recorded_sp02_evidence(), rows=tuple(rows)), 0.02)
        self.assertEqual(result.status, wi.INCOMPLETE)
        self.assertEqual(result.rows, ())  # no predicted row at all
        self.assertIsNone(result.e_trial_mpa)
        self.assertIn(text, result.reason)

    def test_absent_strict_rows_are_incomplete(self):
        # PR #75 review: an accepted strict row missing entirely from the evidence is not a complete preview
        rows = recorded_sp02_evidence().rows
        for absent, role in wi.REQUIRED_STRICT_ROWS.items():
            with self.subTest(absent=absent):
                self.assertIncomplete([row for row in rows if row.row_id != absent], f"{absent} ({role}) is absent")

    def test_duplicated_misclassified_or_unexpected_strict_rows_are_incomplete(self):
        rows = recorded_sp02_evidence().rows
        r2 = next(row for row in rows if row.row_id == "R2")
        self.assertIncomplete(list(rows) + [r2], "R2 appears 2 times")
        for row_id, wrong in (("R3", "FIT"), ("R1", "HOLDOUT")):
            with self.subTest(row_id=row_id):
                self.assertIncomplete([replace(row, role=wrong) if row.row_id == row_id else row for row in rows],
                                      f"{row_id} is {wrong}, the accepted role is "
                                      f"{wi.REQUIRED_STRICT_ROWS[row_id]}")
        self.assertIncomplete(list(rows) + [replace(r2, row_id="R4")], "unexpected strict row R4 (FIT)")

    def test_complete_accepted_rows_stay_available_with_the_same_frequencies(self):
        evidence = recorded_sp02_evidence()
        recorded = {row.row_id: row for row in evidence.rows if row.role != "NO_STRICT_ROW"}
        self.assertEqual({row_id: row.role for row_id, row in recorded.items()}, wi.REQUIRED_STRICT_ROWS)
        for change in (0.0, -0.02, 0.02):
            result = wi.e_what_if(evidence, change)
            self.assertEqual(result.status, wi.AVAILABLE)
            for row_id, row in predicted(result).items():
                self.assertEqual(row.trial_hz, recorded[row_id].fe_hz * (1.0 + change) ** recorded[row_id].s_e)

    def test_required_rows_are_the_accepted_sp02_strict_freeze(self):
        physical = json.loads((ROOT / "docs/auto_id/registration_evidence/SP02_registration_reevaluation.json")
                              .read_text(encoding="utf-8"))["results"]["PHYSICAL"]
        holdouts = set(physical["holdouts"]["holdout_row_ids"])
        self.assertEqual({row["row_id"]: "HOLDOUT" if row["row_id"] in holdouts else "FIT"
                          for row in physical["strict_pairs"]}, wi.REQUIRED_STRICT_ROWS)


class CachedSmokeManifestTests(unittest.TestCase):
    """The real SP-02 smoke-test extraction (a34dd17), read from its manifest only; no Abaqus is started."""

    def test_recorded_strict_frequencies_are_recovered(self):
        if not SMOKE_MANIFEST.is_file():
            self.skipTest("the SP-02 smoke-test extraction cache is not available")
        data = json.loads(SMOKE_MANIFEST.read_text(encoding="utf-8"))
        frames = {int(entry["mode"]): float(entry["frequency_hz"]) for entry in data["modes"]}
        accepted, kept = history_frequencies(data, frames)
        self.assertEqual(kept, {})
        record = json.loads((ROOT / "docs/auto_id/registration_evidence/SP02_registration_reevaluation.json")
                            .read_text(encoding="utf-8"))["results"]["PHYSICAL"]
        for row in record["strict_pairs"]:
            self.assertEqual(accepted[row["fe_mode"]], row["fe_hz"])  # exactly the accepted strict-pair value
            self.assertTrue(ev._same_frequency(accepted[row["fe_mode"]], row["fe_hz"]))
        self.assertFalse(ev._same_frequency(frames[13], 207.4272918701172))  # why R3 was refused before the fix


if __name__ == "__main__":
    unittest.main()

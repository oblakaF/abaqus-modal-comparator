"""A useful comparison for a new ODB whose automatic orientation is ambiguous (normal ODB / UNV comparator).

When the automatic geometry registration finds several equally plausible orientations, the analysis is no longer
discarded:

- a new ODB with exactly the FE geometry identity of an accepted physical registration, the accepted PolyMAX source
  and modal set reuses that frozen mapping; its own frequencies and shapes are compared, it is not assumed to be the
  accepted baseline ODB, and archived sensitivities apply only when 11. Scaling verifies the baseline ODB by SHA-256;
- otherwise a FREQUENCY_ONLY_DIAGNOSTIC shows both frequency lists and nearest-frequency differences, without an
  orientation choice, MAC or mode pairs.

Synthetic data (the G2c / G2d-1 world); no Abaqus.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from modal_core import ModalDataset, ModeShape  # noqa: E402
from reviewed_core import GeometryOrientationAmbiguousError  # noqa: E402
from services import archived_sensitivity_evidence as ev  # noqa: E402
from services import new_odb_comparison as new  # noqa: E402
from test_g2c_archived_sensitivity_evidence import World  # noqa: E402
from test_g2d1_governed_registration import experimental_dataset, fe_dataset  # noqa: E402

NEW_HZ = {7: 21.0, 8: 69.0, 9: 76.0, 10: 87.0, 11: 93.0, 12: 139.0, 13: 198.0}  # another FE result, same mesh


def new_odb_dataset(path: Path, base: ModalDataset, shift: float = 0.0, scale: float = 1.0) -> ModalDataset:
    """Another ODB's modes on the same (or, with ``shift`` / ``scale``, another) FE geometry."""
    modes = []
    for mode in base.sorted_modes():
        coordinates = mode.coordinates * scale + np.array([shift, 0.0, 0.0])
        modes.append(ModeShape(mode.number, NEW_HZ[mode.number], mode.node_ids, coordinates, -1.5 * mode.vectors))
    return ModalDataset("FE", path, modes)


def ambiguity(count: int = 8) -> GeometryOrientationAmbiguousError:
    return GeometryOrientationAmbiguousError(f"{count} physically distinct orientation/registration candidates",
                                             [{"candidate_id": f"geometry-{k}"} for k in range(count)])


class _Case(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.world = World(directory.name)
        self.odb, self.unv = self.world.files["SP02"]
        self.baseline = fe_dataset(self.odb)
        self.experimental = experimental_dataset(self.unv, self.baseline)
        self.new_odb = Path(directory.name) / "data" / "SP02_new_model.odb"
        self.new_odb.write_bytes(b"another FE result with the accepted mesh " * 4000)
        self.new = new_odb_dataset(self.new_odb, self.baseline)

    def bind(self, abaqus=None, experimental=None, unv=None):
        with self.world.pins():
            return new.bind_registration_by_fe_geometry(unv or self.unv, abaqus or self.new,
                                                        experimental or self.experimental, repo_root=self.world.root)


# ----------------------------------------------------------------------------- the binding

class BindingTests(_Case):
    def test_same_verified_geometry_reuses_the_physical_mapping(self):
        bound = self.bind()
        self.assertEqual(bound.specimen, "SP02")
        self.assertEqual(bound.registration.registration_hash, self.world.registrations["SP02"].registration_hash)
        provenance = bound.provenance()
        self.assertEqual(provenance["source"], new.GEOMETRY_REUSE_SOURCE)
        self.assertEqual(provenance["fe_geometry_sha256"], bound.registration.fe_geometry_identity["sha256"])
        self.assertIn("this ODB is not assumed to be the accepted baseline ODB (its content is not hashed by this "
                      "reuse)", provenance["limits"])
        # CORE-E2E T1b: the reused path may load the accepted baseline ODB itself, which 11. Scaling then verifies;
        # the warning must not claim that archived sensitivities never apply
        self.assertIn("archived sensitivities apply only if 11. Scaling verifies this ODB", bound.warning())
        self.assertNotIn("archived sensitivities do not apply", bound.warning())
        self.assertEqual(len(bound.checks), 4)

    def test_different_geometry_is_never_reused(self):
        for label, dataset in (("moved", new_odb_dataset(self.new_odb, self.baseline, shift=0.5)),
                               ("rescaled", new_odb_dataset(self.new_odb, self.baseline, scale=1.001))):
            with self.subTest(label), self.assertRaises(new.GeometryReuseRefusal) as caught:
                self.bind(abaqus=dataset)
            self.assertIn("is not the accepted SP02 FE geometry", str(caught.exception))
        fewer = ModalDataset("FE", self.new_odb, [ModeShape(m.number, m.frequency_hz, m.node_ids[:11],
                                                            m.coordinates[:11], m.vectors[:11])
                                                  for m in self.new.sorted_modes()])
        with self.assertRaises(new.GeometryReuseRefusal):
            self.bind(abaqus=fewer)

    def test_wrong_experimental_file_or_modal_set_is_never_reused(self):
        other = self.unv.with_name("other.unv")
        other.write_bytes(self.unv.read_bytes() + b" edited")
        with self.assertRaises(new.GeometryReuseRefusal) as caught:
            self.bind(unv=other)
        self.assertIn("is not the PolyMAX source of an accepted physical registration", str(caught.exception))
        wrong_set = experimental_dataset(self.unv, self.baseline)
        wrong_set.metadata.update(modal_set_key="set-b", available_modal_sets=[{"key": "set-a"}, {"key": "set-b"}])
        with self.assertRaises(new.GeometryReuseRefusal) as caught:
            self.bind(experimental=wrong_set)
        self.assertIn("modal_set", str(caught.exception))
        fewer_modes = ModalDataset("PolyMAX", self.unv, self.experimental.sorted_modes()[:3],
                                   metadata=dict(self.experimental.metadata))
        with self.assertRaises(new.GeometryReuseRefusal):
            self.bind(experimental=fewer_modes)

    def test_unverifiable_registration_is_never_reused(self):
        path = self.world.root / next(item for item in self.world.fixtures["fixtures"]
                                      if item["fixture_id"] == "SP02/bravo-1-physical")["registration"]["path"]
        document = json.loads(path.read_text(encoding="utf-8"))
        document["mapped_fe_node_ids"][0] = "PLATE-TOP:12"  # the seal no longer matches
        path.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(new.GeometryReuseRefusal) as caught:
            self.bind()
        self.assertIn("SP02/bravo-1-physical", str(caught.exception))


# ----------------------------------------------------------------------------- the frequency-only diagnostic

class FrequencyOnlyTests(_Case):
    def test_frequencies_and_nearest_differences_without_mac_or_pairs(self):
        diagnostic = new.frequency_only_diagnostic(self.new, self.experimental, "reuse refused: geometry differs")
        self.assertEqual(diagnostic.status, new.FREQUENCY_ONLY)
        self.assertEqual(diagnostic.fe_modes, tuple(NEW_HZ.items()))
        self.assertEqual([n for n, _ in diagnostic.experimental_modes], [1, 2, 3, 4])
        first = diagnostic.rows[0]  # experimental 24 Hz: FE 7 (21 Hz) is nearest, FE 8 (69 Hz) next
        self.assertEqual((first.nearest_fe_mode, first.next_fe_mode), (7, 8))
        self.assertAlmostEqual(first.nearest_difference_percent, (21.0 - 24.0) / 24.0 * 100.0)
        document = diagnostic.to_dict()
        self.assertEqual(document["mac"], "NOT_COMPUTED")
        self.assertTrue(document["mode_pairs"].startswith("NONE"))
        self.assertNotIn("mac", json.dumps(document["nearest_frequency_rows"]).lower())
        text = "\n".join(diagnostic.text_lines())
        self.assertIn("MAC and the physical modal correspondence are NOT verified", text)
        self.assertIn("NOT mode pairs", text)
        for row in new.frequency_only_table_rows(diagnostic):
            self.assertEqual(row[5], "not computed")
            self.assertTrue(row[8].startswith("FREQUENCY ONLY — not a pair"))  # + a range note when outside
            self.assertTrue(row[0].endswith("(nearest)"))

    def test_frequencies_outside_the_extracted_fe_range_are_marked(self):
        # CORE-E2E T4 (SP-04): FRF peaks at 9.7 / 15.6 Hz lie below FE mode 7 (58.15 Hz) and peaks up to 977 Hz above
        # FE mode 25 (678 Hz); their "nearest" differences (+500 %, -31 %) describe the mode range, not the model
        m = self.baseline.sorted_modes()[0]

        def modes(pairs):
            return [ModeShape(n, hz, m.node_ids, m.coordinates, m.vectors) for n, hz in pairs]

        fe = ModalDataset("FE", self.new_odb, modes(((7, 60.0), (8, 140.0))))
        experimental = ModalDataset("EXP", self.unv, modes(((1, 9.7), (2, 61.0), (3, 900.0))))
        diagnostic = new.frequency_only_diagnostic(fe, experimental, "x")
        statuses = [row[8] for row in new.frequency_only_table_rows(diagnostic)]
        self.assertEqual(statuses[0], "FREQUENCY ONLY — not a pair; below the lowest extracted FE mode (60.00 Hz)")
        self.assertEqual(statuses[1], "FREQUENCY ONLY — not a pair")
        self.assertTrue(statuses[2].endswith("above the highest extracted FE mode (140.00 Hz); extend the Abaqus "
                                             "mode range"))
        self.assertIn("below the lowest extracted FE mode", "\n".join(diagnostic.text_lines()))
        self.assertEqual(diagnostic.to_dict()["mac"], "NOT_COMPUTED")

    def test_no_fe_frequency(self):
        empty = ModalDataset("FE", self.new_odb, [])
        diagnostic = new.frequency_only_diagnostic(empty, self.experimental, "x")
        self.assertTrue(all(row.nearest_fe_mode is None for row in diagnostic.rows))
        self.assertIn("no FE frequency", "\n".join(diagnostic.text_lines()))


# ----------------------------------------------------------------------------- the analysis worker

class WorkerTests(_Case):
    def run_worker(self, abaqus, unv=None, *, ambiguous=True, selection=None, governed=False):
        import main
        import runtime_hardening

        calls, failures, completed = [], [], []
        real = main.app.compare_modal_datasets

        def compare(*args, **kwargs):
            calls.append(kwargs)
            if "frozen_registration" not in kwargs:
                if ambiguous:
                    raise ambiguity()
                return SimpleNamespace(metadata={}, warnings=[], pairs=[])  # a unique automatic orientation
            return real(*args, **kwargs)

        class Root:
            @staticmethod
            def after(_delay, callback):
                callback()

        application = SimpleNamespace(
            root=Root(), _analysis_cancel_event=threading.Event(), _owned_analysis_process=None,
            _set_analysis_stage=lambda *_: None, _failed=failures.append, _complete=completed.append,
            _orientation_ambiguous=failures.append, _governed_registration_requested=governed,
            _active_orientation_selection=selection, _write_summary=lambda *_: None)
        bind = functools.partial(new.bind_registration_by_fe_geometry, repo_root=self.world.root)
        with tempfile.TemporaryDirectory() as directory, self.world.pins(), \
                mock.patch.object(runtime_hardening, "bind_registration_by_fe_geometry", bind), \
                mock.patch.object(main.app, "load_or_extract_odb", return_value=abaqus), \
                mock.patch.object(runtime_hardening, "load_universal_modal_file", return_value=self.experimental), \
                mock.patch.object(main.app, "compare_modal_datasets", side_effect=compare), \
                mock.patch.object(main.app, "render_mac_matrix", side_effect=RuntimeError("stop after comparison")):
            workspace = Path(directory)
            main.app.ModalComparatorApp._worker(application, abaqus.source_path, unv or self.unv, workspace,
                                                7, 13, "abaqus", 1.0, "set-a")
            written = {path.name: path.read_text(encoding="utf-8") for path in workspace.rglob("*.json")}
        return calls, failures, written

    def test_same_geometry_new_odb_is_compared_with_the_reused_registration(self):
        calls, failures, _ = self.run_worker(self.new)
        self.assertEqual([set(kwargs) for kwargs in calls], [{"coordinate_scale_override"}, {"frozen_registration"}])
        self.assertEqual(calls[1]["frozen_registration"].registration_hash,
                         self.world.registrations["SP02"].registration_hash)
        self.assertEqual(str(failures[0]), "stop after comparison")  # the comparison itself completed

    def test_reused_result_compares_the_new_odb_and_is_never_the_baseline(self):
        import main
        import runtime_hardening

        results = []
        original = main.app.compare_modal_datasets

        def keep(*args, **kwargs):
            if "frozen_registration" not in kwargs:
                raise ambiguity()
            result = original(*args, **kwargs)
            results.append(result)
            return result

        class Root:
            @staticmethod
            def after(_delay, callback):
                callback()

        failures = []
        application = SimpleNamespace(root=Root(), _analysis_cancel_event=threading.Event(),
                                      _owned_analysis_process=None, _set_analysis_stage=lambda *_: None,
                                      _failed=failures.append, _governed_registration_requested=False,
                                      _active_orientation_selection=None)
        bind = functools.partial(new.bind_registration_by_fe_geometry, repo_root=self.world.root)
        with tempfile.TemporaryDirectory() as directory, self.world.pins(), \
                mock.patch.object(runtime_hardening, "bind_registration_by_fe_geometry", bind), \
                mock.patch.object(main.app, "load_or_extract_odb", return_value=self.new), \
                mock.patch.object(runtime_hardening, "load_universal_modal_file", return_value=self.experimental), \
                mock.patch.object(main.app, "compare_modal_datasets", side_effect=keep), \
                mock.patch.object(main.app, "render_mac_matrix", side_effect=RuntimeError("stop")):
            main.app.ModalComparatorApp._worker(application, self.new_odb, self.unv, Path(directory), 7, 13,
                                                "abaqus", 1.0, "set-a")
        (result,) = results
        self.assertEqual(result.metadata["geometry_verified_registration"]["source"], new.GEOMETRY_REUSE_SOURCE)
        self.assertTrue(result.warnings[0].startswith("Physical registration reused by FE geometry identity"))
        self.assertNotIn("governed_registration", result.metadata)  # not the G2d-1 accepted-reference run
        self.assertEqual({p.abaqus_mode: p.abaqus_frequency_hz for p in result.pairs},
                         {p.abaqus_mode: NEW_HZ[p.abaqus_mode] for p in result.pairs})  # the new ODB's own modes
        self.assertTrue(result.pairs)
        evidence = self.world.check(result)  # archived sensitivities are bound to the baseline ODB only
        self.assertEqual(evidence.status, ev.NOT_APPLICABLE)
        self.assertIn("is not an accepted baseline ODB", " ".join(evidence.reasons))

    def test_different_geometry_gives_the_frequency_only_diagnostic(self):
        moved = new_odb_dataset(self.new_odb, self.baseline, shift=0.5)
        calls, failures, written = self.run_worker(moved)
        self.assertEqual([set(kwargs) for kwargs in calls], [{"coordinate_scale_override"}])  # no reuse
        (error,) = failures
        self.assertIsInstance(error, GeometryOrientationAmbiguousError)
        diagnostic = error.frequency_only_diagnostic
        self.assertEqual(diagnostic.status, new.FREQUENCY_ONLY)
        self.assertIn("8 physically distinct orientations", diagnostic.reason)
        self.assertIn("is not the accepted SP02 FE geometry", diagnostic.reason)
        self.assertEqual(json.loads(written["frequency_only_diagnostic.json"])["mac"], "NOT_COMPUTED")

    def test_wrong_unv_gives_the_frequency_only_diagnostic(self):
        other = self.unv.with_name("other.unv")
        other.write_bytes(self.unv.read_bytes() + b" edited")
        calls, failures, _ = self.run_worker(self.new, unv=other)
        self.assertEqual(len(calls), 1)
        self.assertIn("not the PolyMAX source", failures[0].frequency_only_diagnostic.reason)

    def test_confirmed_orientation_or_unambiguous_geometry_is_unchanged(self):
        calls, failures, _ = self.run_worker(self.new, selection={"candidate_id": "geometry-x"})
        self.assertEqual(len(calls), 1)  # a user-confirmed orientation is never replaced
        self.assertIsInstance(failures[0], GeometryOrientationAmbiguousError)
        self.assertIsNone(getattr(failures[0], "frequency_only_diagnostic", None))
        with mock.patch.object(new, "bind_registration_by_fe_geometry") as bind:
            calls, failures, _ = self.run_worker(self.new, ambiguous=False)
        bind.assert_not_called()
        self.assertEqual([set(kwargs) for kwargs in calls], [{"coordinate_scale_override"}])


# ----------------------------------------------------------------------------- the GUI

class TkTests(_Case):
    def application(self):
        try:
            import tkinter as tk

            root = tk.Tk()
        except Exception as error:  # noqa: BLE001
            self.skipTest(f"Tk is unavailable: {error}")
        self.addCleanup(root.destroy)
        self.addCleanup(lambda: [root.after_cancel(job) for job in root.tk.splitlist(root.tk.call("after", "info"))])
        root.withdraw()
        import main
        import ui_workflow

        disabled = {"autosave_enabled": False, "restore_on_startup": False, "show_recovery_notice": False}
        with mock.patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), \
                mock.patch.object(ui_workflow, "discover_abaqus_installations", return_value=()):
            application = main.app.ModalComparatorApp(root)
        application._show_orientation_ambiguity_dialog = lambda _error: None
        return root, application

    def test_frequency_only_results_are_shown_instead_of_cleared(self):
        root, application = self.application()
        error = ambiguity()
        error.frequency_only_diagnostic = new.frequency_only_diagnostic(self.new, self.experimental, "geometry differs")
        application._failed(error)
        root.update_idletasks()
        table = application.table
        rows = [tuple(str(v) for v in table.item(k, "values")) for k in table.get_children()]
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row[5] == "not computed" and row[8].startswith("FREQUENCY ONLY — not a pair")
                            for row in rows))
        self.assertEqual(application.item_to_pair, {})  # nothing selectable as a pair
        self.assertEqual(application.metric_mac.cget("text"), "not computed")
        details = application.details.get("1.0", "end")
        self.assertIn("FREQUENCY_ONLY_DIAGNOSTIC", details)
        self.assertIn("FE mode 13: 198.0000 Hz", details)
        self.assertIn("FREQUENCY_ONLY_DIAGNOSTIC", application.status.get())

    def test_ambiguity_without_diagnostic_is_unchanged(self):
        root, application = self.application()
        application._failed(ambiguity())
        root.update_idletasks()
        self.assertIn("orientation ambiguous: physical provenance required", application.status.get())
        rows = [application.table.item(k, "values") for k in application.table.get_children()]
        self.assertEqual(len(rows), 1)  # the empty-state row only


if __name__ == "__main__":
    unittest.main()

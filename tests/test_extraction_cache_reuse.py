"""CORE-E2E: an Abaqus extraction is reused across analysis folders of one workspace (no process, no Abaqus).

The FE extraction depends only on the ODB (path, size, mtime), the Abaqus command and the mode range
(``abaqus_bridge._source_signature``). A user-confirmed orientation, another modal set or another experimental file
starts a new analysis folder (its results never mix), but must not run Abaqus again on the same ODB. A changed ODB or
mode range still extracts again.
"""

from __future__ import annotations

import json
import os
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

from modal_core import ModalDataset, ModeShape  # noqa: E402


class _Stop(RuntimeError):
    pass


def _fe(odb: Path) -> ModalDataset:
    ids = np.array([f"PLATE-1.{i}" for i in range(1, 5)], dtype=object)
    xyz = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [1.0, 1.0, 0.0]])
    return ModalDataset("fake ODB", odb, [ModeShape(7, 10.0, ids, xyz, np.ones((4, 3)))])


class ExtractionCacheReuseTests(unittest.TestCase):
    def setUp(self) -> None:
        import main  # noqa: F401  (all layers: runtime_hardening owns _worker)

        self.main = main
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.workspace = self.folder / "workspace"
        self.odb = self.folder / "plate.odb"
        self.odb.write_bytes(b"synthetic ODB stand-in; never opened")
        self.unv = self.folder / "test.unv"
        self.unv.write_text("synthetic experimental stand-in", encoding="utf-8")
        self.extractions: list[Path] = []
        patcher = mock.patch("subprocess.Popen", side_effect=AssertionError("no process may start"))
        patcher.start()
        self.addCleanup(patcher.stop)

    def fake_extraction(self, odb_path, output_directory, abaqus_command, start_mode, end_mode, **_kwargs):
        output = Path(output_directory)
        self.extractions.append(output)
        (output / "mode_0007.csv").write_text("synthetic", encoding="utf-8")
        manifest = output / "manifest.json"
        manifest.write_text(json.dumps({"modes": [{"mode": 7, "file": "mode_0007.csv"}]}), encoding="utf-8")
        return manifest

    def run_worker(self, start=7, end=13, modal_set="set-a", orientation=None, experiment=None):
        import abaqus_bridge
        import runtime_hardening

        class Root:
            @staticmethod
            def after(_delay, callback):
                callback()

        failures = []
        application = SimpleNamespace(root=Root(), _analysis_cancel_event=threading.Event(),
                                      _owned_analysis_process=None, _set_analysis_stage=lambda *_: None,
                                      _failed=failures.append, _governed_registration_requested=False,
                                      _active_orientation_selection=orientation)
        with mock.patch.object(abaqus_bridge, "run_abaqus_extraction", side_effect=self.fake_extraction), \
                mock.patch.object(abaqus_bridge, "load_extracted_odb", side_effect=lambda path, **_: _fe(self.odb)), \
                mock.patch.object(runtime_hardening, "load_universal_modal_file", return_value=_fe(self.unv)), \
                mock.patch.object(self.main.app, "compare_modal_datasets", side_effect=_Stop("stop after extraction")):
            self.main.app.ModalComparatorApp._worker(application, self.odb, experiment or self.unv, self.workspace,
                                                     start, end, "abaqus", 1.0, modal_set)
        self.assertIsInstance(failures[0], _Stop)  # stopped where this test stops it, after the extraction

    def analysis_folders(self) -> set[str]:
        return {path.name for path in self.workspace.glob("analysis_*")}

    def test_a_confirmed_orientation_reuses_the_extraction(self):
        self.run_worker()
        self.run_worker(orientation={"candidate_id": "geometry-3"})
        self.assertEqual(len(self.extractions), 1)
        self.assertEqual(len(self.analysis_folders()), 2)  # results of the two runs stay apart

    def test_another_modal_set_or_experimental_file_reuses_the_extraction(self):
        other = self.folder / "other.unv"
        other.write_text("another experimental stand-in", encoding="utf-8")
        self.run_worker()
        self.run_worker(modal_set="set-b")
        self.run_worker(experiment=other)
        self.assertEqual(len(self.extractions), 1)
        self.assertEqual(len(self.analysis_folders()), 3)

    def test_another_mode_range_extracts_again(self):
        self.run_worker()
        self.run_worker(start=7, end=20)
        self.assertEqual(len(self.extractions), 2)

    def test_a_changed_odb_extracts_again(self):
        self.run_worker()
        stat = self.odb.stat()
        os.utime(self.odb, ns=(stat.st_atime_ns, stat.st_mtime_ns + 10 ** 9))
        self.run_worker(orientation={"candidate_id": "geometry-3"})
        self.assertEqual(len(self.extractions), 2)

    def test_a_refused_licence_is_reported_and_never_cached(self):
        import abaqus_bridge
        import runtime_hardening

        def refused(*_args, **_kwargs):
            raise abaqus_bridge.AbaqusExtractionError(
                "Abaqus could not extract the ODB results.\n\nLicense server does not support this feature")

        class Root:
            @staticmethod
            def after(_delay, callback):
                callback()

        failures = []
        application = SimpleNamespace(root=Root(), _analysis_cancel_event=threading.Event(),
                                      _owned_analysis_process=None, _set_analysis_stage=lambda *_: None,
                                      _failed=failures.append, _governed_registration_requested=False,
                                      _active_orientation_selection=None)
        with mock.patch.object(abaqus_bridge, "run_abaqus_extraction", side_effect=refused), \
                mock.patch.object(runtime_hardening, "load_universal_modal_file", return_value=_fe(self.unv)):
            self.main.app.ModalComparatorApp._worker(application, self.odb, self.unv, self.workspace, 7, 13,
                                                     "abaqus", 1.0, "set-a")
        self.assertIsInstance(failures[0], abaqus_bridge.AbaqusExtractionError)
        self.assertIn("License", str(failures[0]))
        self.assertFalse(list(self.workspace.glob("analysis_*/abaqus/extraction_signature.json")))
        self.run_worker()  # the next run extracts again: a refusal is never a cached result
        self.assertEqual(len(self.extractions), 1)

    def test_an_incomplete_extraction_is_never_reused(self):
        self.run_worker()
        (self.extractions[0] / "mode_0007.csv").unlink()  # interrupted or damaged extraction
        self.run_worker(orientation={"candidate_id": "geometry-3"})
        self.assertEqual(len(self.extractions), 2)


if __name__ == "__main__":
    unittest.main()

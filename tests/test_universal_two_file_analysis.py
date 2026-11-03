"""UNIVERSAL-UI-1: two files, one Analyze button, for any geometry (Qt ``offscreen``, a fake runner, no Abaqus).

The FE side is written by a fake runner with the bridge's signature; the experimental side is a real dataset 15 + 55
file read by the real importer. The diagnostic and the registration check are the real services: nothing in these
synthetic files matches an accepted registration, so the result must be REGISTRATION_REQUIRED. The verified path is
shown with the checks replaced, to prove that pairs and MAC come only from them.
"""

from __future__ import annotations

import ast
from dataclasses import replace
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest import mock

import numpy as np

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    from PySide6.QtWidgets import QApplication, QBoxLayout, QPushButton
except ImportError as error:  # pragma: no cover - depends on the environment
    if os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
        raise
    raise unittest.SkipTest(f"PySide6 is not installed ({error})")

from abaqus_bridge import AbaqusExtractionError, AnalysisCancelled  # noqa: E402
from new_gui import analyze_model as am  # noqa: E402
from new_gui import comparison_model as cm  # noqa: E402
from new_gui import registration_check_model as rm  # noqa: E402
from new_gui import shape_model as sm  # noqa: E402
from new_gui import production_window  # noqa: E402
from new_gui import window as window_module  # noqa: E402
from new_gui.analyze_panel import AnalyzePanel, BLOCKED, DONE, IDLE, NEED_SET, RUNNING  # noqa: E402
from new_gui.workspace_state import EXPERIMENTAL, FE  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
from test_local_fe_preview import write_shape_package  # noqa: E402
from test_odb_import_service import FOUND, NONE  # noqa: E402

RIGID = 6
ELASTIC_BASE_HZ = 20.0


def plate_nodes():
    return [(i * 5 + j + 1, 0.1 * i, 0.05 * j, 0.0) for i in range(5) for j in range(5)]


def beam_nodes():
    return [(i + 1, 0.1 * i, 0.0, 0.0) for i in range(15)]


def arbitrary_nodes():
    points = np.random.default_rng(3).uniform(-1.0, 1.0, (30, 3))
    return [(i + 1, float(x), float(y), float(z)) for i, (x, y, z) in enumerate(points)]


def rigid_shape(nodes, index):
    xyz = np.array([n[1:] for n in nodes])
    if index < 3:
        vectors = np.zeros_like(xyz)
        vectors[:, index] = 1.0
        return vectors
    return np.cross(np.eye(3)[index - 3], xyz - xyz.mean(axis=0))


def elastic_shape(nodes, number):
    rng = np.random.default_rng(number)  # no rigid-body combination, whatever the geometry
    return rng.standard_normal((len(nodes), 3))


def rigid_shapes(nodes):
    """The rigid-body shapes the nodes can show: on one line, a rotation about that line moves nothing."""
    return [shape for shape in (rigid_shape(nodes, i) for i in range(RIGID)) if np.abs(shape).max() > 0.0]


def fe_modes(nodes, count=25):
    rigid = rigid_shapes(nodes)
    modes = [(i + 1, 0.0011 + 0.0001 * i, shape) for i, shape in enumerate(rigid)]
    first = len(rigid) + 1
    modes += [(n, ELASTIC_BASE_HZ * (n - len(rigid)), elastic_shape(nodes, n)) for n in range(first, count + 1)]
    return modes


class Runner:
    """The bridge's signature; writes a package clipped to the requested range, as the extractor does."""

    def __init__(self, nodes, modes=None, *, wait_for_cancel=False, error=None, frame_value_fallback=()):
        self.nodes, self.modes = nodes, modes or fe_modes(nodes)
        self.fallback = frame_value_fallback  # modes written as the extractor writes a zero-frequency frame
        self.calls = []
        self.wait_for_cancel, self.error = wait_for_cancel, error
        self.started = threading.Event()

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        self.started.set()
        folder = Path(kwargs["output_directory"])
        if self.wait_for_cancel:
            end = time.monotonic() + 30
            while not kwargs["cancel_event"].is_set() and time.monotonic() < end:
                time.sleep(0.01)
            raise AnalysisCancelled("Analysis stopped by user.")
        if self.error:
            raise AbaqusExtractionError(self.error)
        (folder / "abaqus_extraction.log").write_text("OUTPUT\nPROGRESS: modes available 1-25; requested\n",
                                                      encoding="utf-8")
        chosen = [m for m in self.modes if kwargs["start_mode"] <= m[0] <= kwargs["end_mode"]]
        manifest = write_shape_package(folder, self.nodes, chosen)
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for entry in data["modes"]:
            if entry["mode"] in self.fallback:
                entry["frequency_hz"] = float(entry["mode"])
                entry["description"] = f"Mode {entry['mode']}: Value = 0.0 Freq = 0.0000 (cycles/time)"
        manifest.write_text(json.dumps(data), encoding="utf-8")
        return manifest


def write_unv(path: Path, nodes, frequencies, sets=None) -> Path:
    """Dataset 15 + 55 of real fitted-mode form, on the given nodes."""
    import pyuff

    path.parent.mkdir(parents=True, exist_ok=True)
    labels = np.array([n[0] for n in nodes])
    x, y, z = (np.array([n[i] for n in nodes]) for i in (1, 2, 3))
    uff = pyuff.UFF(str(path))
    count = len(labels)
    uff.write_sets(pyuff.prepare_15(node_nums=labels, def_cs=np.zeros(count, dtype=int),
                                    disp_cs=np.zeros(count, dtype=int), color=np.ones(count, dtype=int),
                                    x=x, y=y, z=z), "add")
    for name, values in sets or (("Fitted", frequencies),):
        for k, f in enumerate(values):
            zeta = 0.003
            w = 2 * math.pi * f / math.sqrt(1 - zeta ** 2)
            eig = -zeta * w + 1j * w * math.sqrt(1 - zeta ** 2)
            shape = np.random.default_rng(100 + k).standard_normal(count).astype(complex)
            data = pyuff.prepare_55(id1=name, id2="synthetic", id3="x", id4="x", id5="x", model_type=1,
                                    analysis_type=3, data_ch=2, spec_data_type=11, data_type=5, n_data_per_node=3,
                                    load_case=1, mode_n=k + 1, eig=eig, modal_a=1 + 0j, modal_b=1 + 0j,
                                    node_nums=labels, r1=np.zeros(count, complex), r2=np.zeros(count, complex), r3=shape,
                                    return_full_dict=True)
            uff.write_sets(data, "add")
    path.write_text(path.read_text().replace("        11         5         6", "        11         5         3"))
    return path


def sha(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class _Case(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or window_module.create_application([])

    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.root = Path(work.name).resolve()
        self.inputs = self.root / "my inputs"
        self.inputs.mkdir()
        self.odb = self.inputs / "any model.odb"
        self.odb.write_bytes(b"synthetic odb; never opened " * 40)
        self.consents = []
        self.consent_answer = True
        for patcher in (mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "cache")}),
                        mock.patch.object(registry, "default_store",
                                          return_value=self.root / "profile" / registry.STORE_NAME),
                        mock.patch("subprocess.Popen", side_effect=AssertionError("no process in these tests"))):
            patcher.start()
            self.addCleanup(patcher.stop)

    def consent(self, text):
        self.consents.append(text)
        return self.consent_answer

    def panel(self, runner=None, discover=FOUND, nodes=None, experimental=None):
        self.runner = runner or Runner(nodes or plate_nodes())
        panel = AnalyzePanel(runner=self.runner, discover=discover, consent=self.consent)
        self.addCleanup(panel.deleteLater)
        self.addCleanup(panel.shutdown)
        self.addCleanup(self.wait, panel)
        panel.resize(1100, 800)
        panel.choose_file(FE, str(self.odb))
        panel.choose_file(EXPERIMENTAL, str(experimental or self.unv(nodes or plate_nodes())))
        return panel

    def unv(self, nodes, frequencies=(20.5, 41.0, 62.0), name="exp data.unv", sets=None):
        return write_unv(self.inputs / name, nodes, frequencies, sets)

    def wait(self, panel, timeout=120.0):
        end = time.monotonic() + timeout
        while panel.busy() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.app.processEvents()
        self.assertFalse(panel.busy())

    def run_analysis(self, panel):
        self.assertTrue(panel.analyze())
        self.wait(panel)


class GeometryTests(_Case):
    """Plate, beam and arbitrary geometry through the same route, with no specimen knowledge."""

    def check(self, nodes):
        panel = self.panel(nodes=nodes)
        self.run_analysis(panel)
        self.assertEqual(panel.state, DONE, panel.message.text())
        analysis = panel.analysis
        self.assertEqual(analysis.status, am.REGISTRATION_REQUIRED)
        self.assertEqual(panel.status_label.text(), am.REGISTRATION_REQUIRED)
        self.assertEqual((self.runner.calls[0]["start_mode"], self.runner.calls[0]["end_mode"]), (1, 20))
        self.assertEqual([row[0] for row in analysis.fe_rows], [str(n) for n in range(1, 21)])
        rigid = len(rigid_shapes(nodes))
        self.assertEqual(analysis.rigid_modes, tuple(range(1, rigid + 1)))
        self.assertEqual(analysis.first_elastic, str(rigid + 1))
        self.assertEqual([row[2] for row in analysis.fe_rows], ["rigid-body"] * rigid + ["elastic"] * (20 - rigid))
        self.assertEqual([row[0] for row in analysis.experimental_rows], ["EXP1", "EXP2", "EXP3"])
        self.assertEqual(analysis.nearest_rows[0][:6], ("EXP1", "1", "20.5000", str(rigid + 1), "20.0000", "-2.44"))
        return panel

    def test_a_plate(self):
        panel = self.check(plate_nodes())
        self.assertEqual(panel.shape_panels[FE].slot.state, sm.SHOWN)
        self.assertEqual(panel.shape_panels[EXPERIMENTAL].slot.state, sm.SHOWN)

    def test_a_beam_any_geometry_without_a_plane(self):
        panel = self.check(beam_nodes())
        self.assertEqual(panel.shape_panels[FE].slot.state, sm.SHOWN)

    def test_arbitrary_geometry(self):
        panel = self.check(arbitrary_nodes())
        self.assertEqual(panel.shape_panels[FE].slot.state, sm.SHOWN)

    def test_a_row_shows_that_records_shapes_side_by_side(self):
        panel = self.check(plate_nodes())
        self.assertEqual(panel.shapes_layout.direction(), QBoxLayout.Direction.LeftToRight)
        self.assertTrue(panel.log.isHidden())  # the progress lines go after a finished analysis
        self.assertTrue(panel.show_candidate(2))
        self.wait(panel)
        self.assertEqual(panel.shape_panels[EXPERIMENTAL].chosen_index(), 2)
        chosen = panel.inputs.fe.modes[panel.shape_panels[FE].chosen_index()]
        self.assertEqual(str(chosen.number), panel.analysis.nearest_rows[2][3])
        self.assertEqual(panel.shape_panels[FE].slot.state, sm.SHOWN)


class FirstTwentyTests(_Case):
    def test_only_the_first_twenty_fe_modes_are_requested_when_the_odb_holds_more(self):
        panel = self.panel()
        self.run_analysis(panel)
        self.assertEqual(len(panel.inputs.fe.modes), 20)
        self.assertIn("requested modes 1-20, loaded 20 (1-20)", panel.analysis.facts[0])

    def test_a_longer_experimental_set_keeps_exp1_and_shows_the_first_twenty(self):
        values = [20.5 + 10 * k for k in range(25)]
        panel = self.panel(experimental=self.unv(plate_nodes(), values))
        self.run_analysis(panel)
        rows = panel.analysis.experimental_rows
        self.assertEqual(len(rows), 20)
        self.assertEqual(rows[0][:3], ("EXP1", "1", "20.5000"))
        self.assertEqual(rows[-1][0], "EXP20")
        self.assertIn("20 of 25 record(s) analyzed", panel.analysis.facts[1])
        self.assertEqual(len(panel.inputs.full_experimental.sets[0].records), 25)  # the read data are not changed

    def test_a_short_odb_is_analysed_with_what_it_holds(self):
        nodes = plate_nodes()
        panel = self.panel(runner=Runner(nodes, fe_modes(nodes, count=9)))
        self.run_analysis(panel)
        self.assertEqual(panel.state, DONE)
        self.assertIn("loaded 9 (1-9)", panel.analysis.facts[0])


class LoaderRuleTests(_Case):
    def test_a_mode_the_loader_refuses_is_stated_and_the_first_elastic_mode_stays(self):
        nodes = plate_nodes()
        panel = self.panel(runner=Runner(nodes, frame_value_fallback=(1, 2)))
        self.run_analysis(panel)
        self.assertEqual(panel.state, DONE, panel.message.text())
        self.assertEqual([row[0] for row in panel.analysis.fe_rows], [str(n) for n in range(3, 21)])
        self.assertEqual(panel.analysis.first_elastic, "7")
        self.assertEqual(panel.analysis.nearest_rows[0][3], "7")
        self.assertTrue(any(note.startswith("Mode 1 not loaded") for note in panel.analysis.notes))


class RegistrationTests(_Case):
    def assert_frequency_only(self, panel):
        self.assertEqual(panel.analysis.status, am.REGISTRATION_REQUIRED)
        self.assertIsNone(panel.analysis.comparison)
        self.assertNotIn("pairs", panel.tables)
        self.assertNotIn("mac", panel.tables)
        table = panel.tables["nearest"]
        headers = [table.horizontalHeaderItem(c).text() for c in range(table.columnCount())]
        self.assertNotIn("MAC", headers)

    def test_no_registration_means_frequency_only_with_the_real_check(self):
        panel = self.panel()
        with mock.patch.object(cm, "run_compare", side_effect=AssertionError("no comparison")):
            self.run_analysis(panel)
        self.assert_frequency_only(panel)
        self.assertTrue(panel.analysis.registration_reason)

    def test_a_failed_check_is_never_a_verified_one(self):
        panel = self.panel()
        failed = rm.RegistrationOutcome(0, error="The check could not be completed.")
        with mock.patch.object(rm, "run_check", return_value=failed), \
                mock.patch.object(cm, "run_compare", side_effect=AssertionError("no comparison")):
            self.run_analysis(panel)
        self.assert_frequency_only(panel)

    def verified(self):
        return rm.RegistrationOutcome(0, view=SimpleNamespace(registration="hash-1"))

    def test_a_refused_comparison_after_a_verified_check_shows_no_pair(self):
        panel = self.panel()
        with mock.patch.object(rm, "run_check", return_value=self.verified()), \
                mock.patch.object(cm, "run_compare",
                                  return_value=cm.ComparisonOutcome(0, refusal="the file changed since it was read")):
            self.run_analysis(panel)
        self.assert_frequency_only(panel)
        self.assertIn("changed", panel.analysis.registration_reason)

    def test_pairs_and_mac_come_only_from_the_verified_comparison(self):
        panel = self.panel()
        row = SimpleNamespace(cells=("7", "20.0000", "1", "1", "20.5000", "-2.44", "0.981", "PASS") + ("x",) * 6)
        view = SimpleNamespace(status=cm.PAIRS_FOUND, pair_rows=(row,), mac_cells=(("0.981",),), mac_fe_modes=(7,),
                               mac_experimental_modes=(1,), warnings=("the comparator's warning",))
        with mock.patch.object(rm, "run_check", return_value=self.verified()) as check, \
                mock.patch.object(cm, "run_compare", return_value=cm.ComparisonOutcome(0, view=view)) as compare:
            self.run_analysis(panel)
        check.assert_called_once()
        self.assertEqual(compare.call_args.args[3], "hash-1")
        self.assertIs(compare.call_args.args[6], panel.inputs.identities)  # the read files are confirmed again
        self.assertEqual(panel.status_label.text(), cm.PAIRS_FOUND)
        self.assertEqual(panel.tables["pairs"].item(0, 6).text(), "0.981")
        self.assertEqual(panel.tables["mac"].item(0, 1).text(), "0.981")

    def test_no_admissible_pair_is_shown_as_a_result(self):
        panel = self.panel()
        view = SimpleNamespace(status=cm.NO_PAIR, pair_rows=(), mac_cells=(), mac_fe_modes=(),
                               mac_experimental_modes=(), warnings=())
        with mock.patch.object(rm, "run_check", return_value=self.verified()), \
                mock.patch.object(cm, "run_compare", return_value=cm.ComparisonOutcome(0, view=view)):
            self.run_analysis(panel)
        self.assertEqual(panel.status_label.text(), cm.NO_PAIR)
        self.assertNotIn("pairs", panel.tables)


class ConsentAndPackageTests(_Case):
    def test_refused_consent_starts_nothing(self):
        self.consent_answer = False
        panel = self.panel()
        self.run_analysis(panel)
        self.assertEqual(len(self.consents), 1)
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(panel.state, IDLE)
        self.assertIsNone(panel.analysis)
        self.assertIn("not confirmed", panel.message.text())

    def test_consent_names_what_runs_and_where(self):
        panel = self.panel()
        self.run_analysis(panel)
        text = self.consents[0]
        for expected in ("read-only", "modes 1-20", "No analysis is solved", str(am.package_folder(self.odb))):
            self.assertIn(expected, text)

    def test_the_package_is_found_again_by_content_without_abaqus_or_consent(self):
        panel = self.panel()
        self.run_analysis(panel)
        self.run_analysis(panel)
        self.assertEqual(len(self.runner.calls), 1)
        self.assertEqual(len(self.consents), 1)
        self.assertEqual(panel.state, DONE)

    def test_changed_odb_content_on_the_same_path_is_extracted_again(self):
        panel = self.panel()
        self.run_analysis(panel)
        self.odb.write_bytes(b"another solution " * 50)
        self.run_analysis(panel)
        self.assertEqual(len(self.runner.calls), 2)
        self.assertEqual(len(self.consents), 2)
        self.assertEqual(len(list(am.package_folder(self.odb).iterdir())), 2)

    def test_manifest_json_and_other_types_are_not_accepted(self):
        panel = self.panel()
        manifest = self.inputs / "manifest.json"
        manifest.write_text("{}", encoding="utf-8")
        self.assertIn(".odb", panel.choose_file(FE, str(manifest)))
        self.assertEqual(panel.paths[FE], self.odb.resolve())
        self.assertIn(".unv", panel.choose_file(EXPERIMENTAL, str(self.odb)))
        self.assertNotIn("manifest", am.FILTERS[FE])
        self.assertTrue(panel.file_error.text())

    def test_upper_case_suffixes_are_accepted(self):
        for kind, name in ((FE, "M.ODB"), (EXPERIMENTAL, "E.UFF")):
            path = self.root / name
            path.write_bytes(b"x")
            self.assertEqual(am.file_problem(kind, path), "")

    def test_a_chosen_extraction_folder_is_used(self):
        panel = self.panel()
        folder = self.root / "extraction folder"
        self.assertTrue(panel.choose_folder(str(folder)))
        self.run_analysis(panel)
        self.assertEqual(Path(self.runner.calls[0]["output_directory"]).parent, folder)


class FailureTests(_Case):
    def test_missing_abaqus_explains_and_offers_a_launcher(self):
        panel = self.panel(discover=NONE)
        self.run_analysis(panel)
        self.assertEqual(panel.state, BLOCKED)
        self.assertIn("No Abaqus launcher was found", panel.message.text())
        self.assertIn("Install Abaqus", panel.message.text())
        self.assertEqual(self.consents, [])
        self.assertEqual(self.runner.calls, [])
        self.assertFalse(panel.launcher_button.isHidden())
        launcher = self.root / "abaqus.bat"
        launcher.write_text("@echo off\n", encoding="utf-8")
        os.chmod(launcher, 0o755)
        self.assertTrue(panel.choose_launcher(str(launcher)))
        self.run_analysis(panel)
        self.assertEqual(panel.state, DONE, panel.message.text())

    def extract_range(self, start, end, nodes=None):
        """A package of this ODB in its usual folder, as an extraction of that requested range leaves it."""
        nodes = nodes or plate_nodes()
        plan = am.make_plan(self.odb, "", None, FOUND)
        plan = replace(plan, start_mode=start, end_mode=end)
        return am.extract(plan, threading.Event(), None, Runner(nodes))

    def test_a_wider_extraction_is_reused_within_the_first_twenty(self):
        manifest = self.extract_range(1, 30)
        panel = self.panel(discover=NONE)
        self.run_analysis(panel)
        self.assertEqual(panel.state, DONE, panel.message.text())
        self.assertEqual(self.consents, [])
        self.assertEqual(self.runner.calls, [])
        self.assertEqual(Path(panel.inputs.full_fe.manifest_path), manifest)
        self.assertEqual(len(panel.inputs.full_fe.modes), 25)
        self.assertEqual([row[0] for row in panel.analysis.fe_rows], [str(n) for n in range(1, 21)])

    def test_the_exact_range_is_preferred_to_a_wider_one(self):
        self.extract_range(1, 30)
        exact = self.extract_range(1, 20)
        panel = self.panel(discover=NONE)
        self.run_analysis(panel)
        self.assertEqual(Path(panel.inputs.full_fe.manifest_path), exact)

    def test_a_narrower_or_later_extraction_is_not_reused(self):
        for start, end in ((1, 10), (7, 30)):
            with self.subTest(start=start, end=end):
                self.extract_range(start, end)
                panel = self.panel(discover=NONE)
                self.run_analysis(panel)
                self.assertEqual(panel.state, BLOCKED)
                self.assertIn("No Abaqus launcher was found", panel.message.text())

    def test_a_wider_extraction_of_another_odb_is_not_reused(self):
        self.extract_range(1, 30)
        self.odb.write_bytes(self.odb.read_bytes() + b"changed")
        panel = self.panel(discover=NONE)
        self.run_analysis(panel)
        self.assertEqual(panel.state, BLOCKED)

    def test_a_package_already_extracted_works_without_abaqus(self):
        first = self.panel()
        self.run_analysis(first)
        panel = self.panel(discover=NONE)
        self.run_analysis(panel)
        self.assertEqual(panel.state, DONE, panel.message.text())
        self.assertEqual(self.runner.calls, [])

    def test_an_abaqus_failure_is_a_message(self):
        nodes = plate_nodes()
        panel = self.panel(runner=Runner(nodes, error="Abaqus could not extract the ODB results."))
        self.run_analysis(panel)
        self.assertEqual(panel.state, BLOCKED)
        self.assertIn("could not extract", panel.message.text())
        self.assertIsNone(panel.analysis)
        self.assertFalse(panel.folder_button.isHidden())

    def test_a_damaged_experimental_file_is_a_message(self):
        bad = self.inputs / "bad.unv"
        bad.write_text("not a universal file\n", encoding="utf-8")
        panel = self.panel(experimental=bad)
        self.run_analysis(panel)
        self.assertEqual(panel.state, BLOCKED)
        self.assertTrue(panel.message.text())
        self.assertIsNone(panel.analysis)

    def test_a_removed_file_is_noticed_at_analyze(self):
        panel = self.panel()
        self.odb.unlink()
        self.assertFalse(panel.analyze())
        self.assertIn("not found", panel.file_error.text())

    def test_cancel_stops_the_extraction_and_marks_the_folder(self):
        nodes = plate_nodes()
        panel = self.panel(runner=Runner(nodes, wait_for_cancel=True))
        self.assertTrue(panel.analyze())
        end = time.monotonic() + 30
        while not self.runner.started.is_set() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        self.assertEqual(panel.state, RUNNING)
        self.assertFalse(panel.cancel_button.isHidden())
        panel.cancel()
        self.wait(panel)
        self.assertEqual(panel.state, IDLE)
        self.assertIn("Cancelled", panel.message.text())
        self.assertIsNone(panel.analysis)
        marked = list(am.package_folder(self.odb).rglob("INCOMPLETE.txt"))
        self.assertEqual(len(marked), 1)
        self.assertEqual(panel.discarded, 1)

    def test_an_incomplete_folder_is_not_reused(self):
        nodes = plate_nodes()
        panel = self.panel(runner=Runner(nodes, wait_for_cancel=True))
        self.assertTrue(panel.analyze())
        end = time.monotonic() + 30
        while not self.runner.started.is_set() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        panel.cancel()
        self.wait(panel)
        panel._runner = Runner(nodes)
        self.run_analysis(panel)
        self.assertEqual(panel.state, DONE)
        self.assertEqual(len(panel._runner.calls), 1)


class SourceReplacementTests(_Case):
    def test_replacing_the_experimental_file_removes_the_result(self):
        panel = self.panel()
        self.run_analysis(panel)
        self.assertIsNotNone(panel.analysis)
        other = self.unv(plate_nodes(), (100.5,), name="other.uff")
        panel.choose_file(EXPERIMENTAL, str(other))
        self.assertIsNone(panel.analysis)
        self.assertIsNone(panel.status_label)
        self.assertEqual(panel.tables, {})
        self.run_analysis(panel)
        self.assertEqual(panel.analysis.experimental_rows[0][2], "100.5000")
        self.assertEqual(len(self.runner.calls), 1)

    def test_replacing_the_odb_during_a_run_discards_the_old_run(self):
        nodes = plate_nodes()
        panel = self.panel(runner=Runner(nodes, wait_for_cancel=True))
        self.assertTrue(panel.analyze())
        end = time.monotonic() + 30
        while not self.runner.started.is_set() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        other = self.inputs / "other model.odb"
        other.write_bytes(b"other solution " * 30)
        panel.choose_file(FE, str(other))
        self.assertEqual(panel.state, IDLE)
        self.wait(panel)
        self.assertEqual(panel.state, IDLE)
        self.assertIsNone(panel.analysis)
        self.assertEqual(panel.discarded, 1)
        panel._runner = Runner(nodes)
        self.run_analysis(panel)
        self.assertEqual(Path(panel._runner.calls[0]["odb_path"]), other.resolve())
        self.assertTrue(str(panel._runner.calls[0]["output_directory"]).startswith(str(am.package_folder(other))))

    def test_the_folder_chosen_for_one_odb_does_not_follow_another(self):
        panel = self.panel()
        panel.choose_folder(str(self.root / "chosen"))
        other = self.inputs / "other model.odb"
        other.write_bytes(b"x")
        panel.choose_file(FE, str(other))
        self.assertIsNone(panel.folder)


class ModalSetTests(_Case):
    def sets_file(self):
        return self.unv(plate_nodes(), (), sets=(("First set", (20.5, 41.0)), ("Second set", (22.0, 44.0, 66.0))))

    def test_several_sets_ask_once_and_the_choice_continues_without_a_new_read(self):
        panel = self.panel(experimental=self.sets_file())
        self.run_analysis(panel)
        self.assertEqual(panel.state, NEED_SET)
        self.assertIsNone(panel.analysis)
        self.assertFalse(panel.set_row.isHidden())
        self.assertEqual(panel.set_combo.count(), 3)
        inputs = panel.inputs
        self.assertTrue(panel.choose_set(1))
        self.wait(panel)
        self.assertEqual(panel.state, DONE)
        self.assertEqual(len(panel.analysis.experimental_rows), 3)
        self.assertIs(panel.inputs, inputs)
        self.assertTrue(panel.choose_set(0))
        self.wait(panel)
        self.assertEqual(len(panel.analysis.experimental_rows), 2)
        self.assertEqual(panel.shape_panels[EXPERIMENTAL].set_combo.currentData(), 0)

    def test_one_set_never_asks(self):
        panel = self.panel()
        self.run_analysis(panel)
        self.assertEqual(panel.state, DONE)
        self.assertTrue(panel.set_row.isHidden())


class IntegrityTests(_Case):
    def test_the_original_files_are_unchanged_and_only_the_package_folder_is_new(self):
        experimental = self.unv(plate_nodes())
        before = {p.name: sha(p) for p in self.inputs.iterdir()}
        panel = self.panel(experimental=experimental)
        self.run_analysis(panel)
        self.assertEqual({p.name: sha(p) for p in self.inputs.iterdir() if p.is_file()}, before)
        self.assertEqual([p.name for p in self.inputs.iterdir() if p.is_dir()], ["any model_modal_packages"])


class WindowTests(_Case):
    def window(self, kind=production_window.ProductionWindow):
        window = kind(analyze_options={"runner": Runner(plate_nodes()), "discover": FOUND, "consent": self.consent})
        self.addCleanup(window.deleteLater)
        self.addCleanup(window.close)
        return window

    def test_the_program_starts_on_analyze(self):
        source = (ROOT / "src" / "new_gui" / "__main__.py").read_text(encoding="utf-8")
        self.assertIn("ProductionWindow()", source)
        window = self.window()
        self.assertIs(window.stack.currentWidget().widget().findChild(AnalyzePanel), window.analyze)

    def test_the_earlier_window_puts_the_workflow_first_and_keeps_the_research_pages_separately(self):
        window = self.window(window_module.MainWindow)
        names = [b.text() for b in window.sidebar.findChildren(QPushButton) if b.isCheckable()]
        self.assertEqual(names[:2], ["Analyze", "Materials"])
        self.assertEqual(set(names[2:]), {"Workspace", "Analysis", "Status", "Plate Study", "Research Results"})

    def test_the_known_sources_shortcut_left_the_file_menu(self):
        window = self.window(window_module.MainWindow)
        file_menu = [a.text() for a in window.menuBar().actions()[0].menu().actions()]
        self.assertNotIn(window_module.KNOWN_SOURCES, file_menu)
        research = next(a.menu() for a in window.menuBar().actions() if a.text() == "&Research")
        self.assertEqual([a.text() for a in research.actions()], [window_module.KNOWN_SOURCES])

    def test_closing_the_window_stops_a_running_analysis(self):
        window = self.window()
        runner = Runner(plate_nodes(), wait_for_cancel=True)
        window.analyze._runner = runner
        window.analyze.choose_file(FE, str(self.odb))
        window.analyze.choose_file(EXPERIMENTAL, str(self.unv(plate_nodes())))
        self.assertTrue(window.analyze.analyze())
        end = time.monotonic() + 30
        while not runner.started.is_set() and time.monotonic() < end:
            self.app.processEvents()
            time.sleep(0.01)
        window.close()
        self.wait(window.analyze)
        self.assertEqual(window.analyze.state, IDLE)


class PrimaryWorkflowTextTests(unittest.TestCase):
    """No specimen, no research shortcut and no plate-specific wording in the primary workflow."""

    FILES = ("analyze_model.py", "analyze_panel.py", "production_window.py", "materials_status_panel.py", "theme.py",
             "registration_dialog.py", "confirmation_dialog.py")

    def test_no_specimen_or_plate_wording(self):
        pattern = re.compile(r"SP-?\d|M11|PLATE|plate|Plate|specimen|Specimen|known_sources|research_results")
        for name in self.FILES:
            text = (ROOT / "src" / "new_gui" / name).read_text(encoding="utf-8")
            self.assertEqual(pattern.findall(text), [], name)

    def test_no_machine_path(self):
        for name in self.FILES:
            text = (ROOT / "src" / "new_gui" / name).read_text(encoding="utf-8")
            self.assertIsNone(re.search(r"[A-Za-z]:[\\/]", text), name)

    def test_no_solver_or_auto_id_module(self):
        forbidden = ("forward_solver", "auto_id", "subprocess", "abaqus_bridge")
        for name in self.FILES:
            tree = ast.parse((ROOT / "src" / "new_gui" / name).read_text(encoding="utf-8"))
            imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
            imported |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
            for item in imported:
                self.assertFalse(any(word in item for word in forbidden), item)


if __name__ == "__main__":
    unittest.main()

"""PLATE-ONLY-R1: the Plate Study page in the PySide6 window (Qt ``offscreen``).

The page runs only on the plate's working source and a member of its FE family, both recognised by the SHA-256
recorded when Inspect file read them. On a synthetic plate family (temporary files whose SHA-256 stand for the working
source and the family members): the study shows every experimental record, the frequency-only table (never a pair),
the FE sensitivities, the design studies and NOT_IDENTIFIABLE outcomes; the iteration gate stays disabled; a replaced
file removes the result; the report is written only into the chosen folder. Another experimental file (for example
the M11 session) is refused with the reason.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

try:
    from PySide6.QtWidgets import QApplication, QPushButton
except ImportError as error:  # pragma: no cover - depends on the environment
    if os.environ.get("NEW_GUI_REQUIRE_QT") == "1":
        raise
    raise unittest.SkipTest(f"PySide6 is not installed ({error})")

from new_gui import plate_study_model as psm  # noqa: E402
from new_gui import preview_model as pm  # noqa: E402
from new_gui import window as window_module  # noqa: E402
from new_gui import workspace_state as ws  # noqa: E402
from services import local_input_registry as registry  # noqa: E402
from services import plate_study as ps  # noqa: E402
from test_new_gui5_registration import experimental_preview, fe_preview  # noqa: E402
from test_plate_study import BASE, plate_dataset  # noqa: E402


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class _PlateWindow(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "cache").mkdir()
        self.reports = self.root / "reports"
        self.reports.mkdir()
        files = {}
        for name, text in (("plate.unv", "working source"), ("m11.unv", "M11 history"),
                           ("base/manifest.json", "baseline"), ("e1/manifest.json", "E1"), ("e2/manifest.json", "E2"),
                           ("g/manifest.json", "G12"), ("base.inp", "inp")):
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            files[name] = path
        self.files = files
        datasets = {"base": plate_dataset(**BASE),
                    "e1": plate_dataset(BASE["D11"] * 0.9, BASE["D22"], BASE["D66"]),
                    "e2": plate_dataset(BASE["D11"], BASE["D22"] * 0.9, BASE["D66"]),
                    "g": plate_dataset(BASE["D11"], BASE["D22"], BASE["D66"] * 2.0)}
        experiment = plate_dataset(BASE["D11"] * 1.05, BASE["D22"] * 0.97, BASE["D66"] * 1.2, "experiment")

        def member(member_id, manifest, changed=None, value=None):
            parameters = dict(ps.PLATE_FE_FAMILY[0].parameters)
            if changed:
                parameters[changed] = parameters[changed] * value
            return ps.FEMember(member_id, member_id, "synthetic", parameters,
                               ps.FEFile("base.inp", _sha(files["base.inp"])),
                               ps.FEFile(manifest, _sha(files[manifest])),
                               variant_of="S4R_0875_BASELINE" if changed else None, changed=changed)

        family = (member("S4R_0875_BASELINE", "base/manifest.json"), member("V_E1", "e1/manifest.json", "E1", 0.9),
                  member("V_E2", "e2/manifest.json", "E2", 0.9), member("V_G", "g/manifest.json", "G12", 2.0))

        def read(kind, path, cancel_event=None):
            path = Path(path)
            if path.name == "manifest.json":
                return fe_preview(path, datasets[path.parent.name])
            return experimental_preview(path, [experiment])

        for patcher in (mock.patch.object(pm, "read_preview", side_effect=read),
                        mock.patch.object(ps, "WORKING_SOURCE_SHA256", _sha(files["plate.unv"])),
                        mock.patch.object(ps, "PLATE_FE_FAMILY", family),
                        mock.patch.dict(os.environ, {"LOCALAPPDATA": str(self.root / "cache")}),
                        mock.patch.object(registry, "default_store", return_value=self.root / registry.STORE_NAME)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.app = QApplication.instance() or window_module.create_application([])
        self.window = window_module.MainWindow(ask_path=lambda kind, start: "", ask_folder=lambda: str(self.reports),
                                               plate_family_root=self.root)
        self.window.resize(1366, 768)
        self.window.show()
        self.window.show_page(window_module.PLATE_PAGE)
        self.panel = self.window.plate
        self.addCleanup(self._close)

    def _close(self):
        self.window.close()
        self.window.wait_for_reads(60)
        self.window.deleteLater()
        self.app.processEvents()

    def read(self, experiment="plate.unv"):
        for kind, name in ((ws.FE, "base/manifest.json"), (ws.EXPERIMENTAL, experiment)):
            self.assertEqual(self.window.choose_file(kind, str(self.files[name])), "")
            self.assertTrue(self.window.inspect_file(kind))
        self.assertTrue(self.window.wait_for_reads(120))
        self.window.diagnostic.set_combo.setCurrentIndex(1)
        self.app.processEvents()


class PlateStudyPageTests(_PlateWindow):
    def test_nothing_runs_without_the_plate_data_and_the_gate_is_never_enabled(self):
        self.assertFalse(self.panel.run_button.isEnabled())
        self.assertIn("working source", self.panel.why.text())
        self.assertFalse(self.panel.gate_button.isEnabled())
        self.assertFalse(self.panel.export_button.isEnabled())

    def test_the_study_runs_on_the_plate_data_and_produces_no_material_value(self):
        self.read()
        self.assertTrue(self.panel.run_button.isEnabled(), self.panel.why.text())
        self.assertTrue(self.panel.run())
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        view = self.panel.view
        self.assertIsNotNone(view, self.panel.status.text())
        self.assertEqual(view.status, f"{ps.FREQUENCY_ONLY} / {ps.NOT_READY}")
        self.assertEqual(self.panel.tables["experiment"].rowCount(), 9)  # every record, record 1 included
        self.assertEqual(self.panel.tables["experiment"].item(0, 0).text(), "1")
        frequency = self.panel.tables["frequency"]
        self.assertEqual({frequency.item(r, 6).text() for r in range(frequency.rowCount())}, {"NOT a mode pair"})
        self.assertGreater(self.panel.tables["sensitivity"].rowCount(), 0)
        self.assertEqual({o[1] for o in view.outcome_rows}, {ps.NOT_IDENTIFIABLE})
        self.assertTrue(view.registration.startswith(ps.NOT_VERIFIED))
        self.assertFalse(self.panel.gate_button.isEnabled())
        texts = " ".join(label.text() for label in self.panel.findChildren(type(self.panel.why)))
        for forbidden in ("SP-02", "SP-13", "SP02/", "SP13/", "NO_GLOBAL_PARAMETER_VALUE"):
            self.assertNotIn(forbidden, texts)  # no other specimen's material result on this page
        self.assertTrue(self.panel.export())
        self.assertEqual(sorted(p.suffix for p in self.reports.iterdir()), [".json", ".md"])

    def test_the_m11_session_is_refused_as_the_experiment(self):
        self.read("m11.unv")
        self.assertFalse(self.panel.run_button.isEnabled())
        self.assertIn(ps.UNKNOWN_SOURCE, self.panel.why.text())

    def test_a_replaced_file_removes_the_result(self):
        self.read()
        self.panel.run()
        self.assertTrue(self.window.wait_for_reads(120))
        self.app.processEvents()
        self.assertIsNotNone(self.panel.view)
        self.window.choose_file(ws.EXPERIMENTAL, str(self.files["m11.unv"]))
        self.app.processEvents()
        self.assertIsNone(self.panel.view)
        self.assertFalse(self.panel.result_card.isVisible())

    def test_the_page_has_no_working_iteration_command(self):
        page = self.window.stack.widget(window_module.PLATE_PAGE).widget()
        enabled = [b.text() for b in page.findChildren(QPushButton) if b.isEnabled()]
        self.assertNotIn(psm.GATE, enabled)
        with self.assertRaises(ps.IterationNotAuthorised):
            ps.request_iteration()


if __name__ == "__main__":
    unittest.main()

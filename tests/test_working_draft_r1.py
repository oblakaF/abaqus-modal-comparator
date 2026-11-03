"""WORKING-DRAFT-R1: defects found by running the real window on real files."""

from __future__ import annotations

from pathlib import Path
import threading
import unittest

import test_universal_reg1_registration as reg1
import test_universal_two_file_analysis as base

from new_gui import analyze_model as am
from new_gui import confirmation_dialog as confirm
from new_gui.workspace_state import EXPERIMENTAL, FE

ROOT = Path(__file__).resolve().parents[1]


class ModalSetLabelTests(base._Case):
    def test_the_record_count_is_written_once(self):
        nodes = base.plate_nodes()
        unv = self.unv(nodes, sets=(("Fitted A", (20.5, 41.0)), ("Fitted B", (20.6, 41.1, 62.0))))
        panel = self.panel(nodes=nodes, experimental=unv)
        self.run_analysis(panel)
        for row in (1, 2):
            self.assertEqual(panel.set_combo.itemText(row).count("record"), 1, panel.set_combo.itemText(row))


class MeasuredPartFormTests(base._Case):
    """The dialog asks for the measured part only when the FE data hold several, and the statement is saved."""

    def package(self, labels):
        nodes = [("%s" % n[0], n[1], n[2], n[3]) for n in base.plate_nodes()]
        self.assertEqual(len(nodes), len(labels))
        import numpy as np

        points = np.array([n[1:4] for n in nodes], dtype=float)
        fe = reg1.fe_dataset(points, labels)
        experimental = reg1.experimental_dataset(reg1.in_metres(points))
        return fe, experimental

    def test_the_field_appears_only_with_several_parts(self):
        panel = self.panel()
        self.run_analysis(panel)
        dialog = panel.open_registration()
        self.assertTrue(dialog.instance.isHidden())
        self.assertEqual(dialog.evidence()[0].measured_instance, "")

    def test_the_part_is_listed_and_kept_with_the_evidence(self):
        labels = [f"TOP:{k}" for k in range(1, 14)] + [f"CORE:{k}" for k in range(14, 26)]
        fe, _experimental = self.package(labels)
        from services import generic_registration as gr

        self.assertEqual(gr.fe_instances(fe), ("CORE", "TOP"))
        stated = reg1.evidence(measured_instance="TOP")
        self.assertIn("measured_instance", stated.__dataclass_fields__)
        self.assertNotEqual(stated.evidence_hash, reg1.evidence().evidence_hash)

    def test_the_confirmation_shows_the_measured_part(self):
        panel = self.panel()
        self.run_analysis(panel)
        draft = {"evidence": {"axes": ["+X", "+Y", "+Z"], "landmarks": [], "fe_unit": "mm", "experimental_unit": "m",
                              "measured_side": "+Z", "measured_dofs": ["z"], "source": "s", "measured_instance": "TOP"},
                 "result": {"axes_in_fe": ["+X", "+Y", "+Z"], "warnings": [], "checks": []},
                 "sources": {"experimental": {"sha256": "a"}, "fe": {"package_sha256": "b"}},
                 "modal_set": {"display_name": "d", "key": "k", "record_count": 1},
                 "fe_geometry_sha256": "c", "experimental_geometry_sha256": "d"}
        lines = [line for _title, group in confirm.facts_of(draft) for line in group]
        self.assertIn("Measured FE part: TOP", lines)


class LauncherTests(unittest.TestCase):
    def test_the_launcher_opens_the_program_window(self):
        text = (ROOT / "RUN_NEW_GUI.cmd").read_text(encoding="utf-8")
        self.assertIn("-m new_gui", text)
        self.assertNotIn("--research", text)
        self.assertNotIn("preview", text)
        source = (ROOT / "src" / "new_gui" / "__main__.py").read_text(encoding="utf-8")
        self.assertIn("ProductionWindow()", source)


class ThinStructureModelTests(base._Case):
    def test_the_first_twenty_scope_is_unchanged_by_the_measured_part(self):
        panel = self.panel()
        self.run_analysis(panel)
        analysis = am.analyse(panel.inputs, 0, threading.Event())
        self.assertEqual(len(analysis.fe_rows), 20)
        self.assertEqual(analysis.status, am.REGISTRATION_REQUIRED)
        self.assertEqual(analysis.experimental_rows[0][:2], ("EXP1", "1"))
        self.assertEqual(panel.paths[FE], self.odb.resolve())
        self.assertIsNotNone(panel.paths[EXPERIMENTAL])


if __name__ == "__main__":
    unittest.main()

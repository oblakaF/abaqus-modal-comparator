"""G2d-2 — SP-02 E_in what-if on the archived local sensitivities (display only; never a recommended E).

f_trial = f_FE * (E_trial / 52 000 MPa) ** S_E with G12 fixed at 4 500 MPa, E_in change within the archived ±5 %. Enabled
only by G2c ARCHIVED_SENSITIVITY_EVIDENCE_VERIFIED for SP-02. The arithmetic tests use the real recorded SP-02 strict
pairs and sensitivities from the repository; the store-gated test runs the whole chain on real archived shapes.
"""

from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from services import archived_sensitivity_evidence as ev  # noqa: E402
from services import sensitivity_what_if as wi  # noqa: E402

SP02 = next(spec for spec in ev.SPECIMENS if spec.specimen == "SP02")


def recorded_sp02_evidence(status: str = ev.VERIFIED, specimen: str = "SP02") -> ev.SensitivityEvidence:
    """A G2c evidence object holding exactly the recorded SP-02 strict pairs, sensitivities and outliers."""
    physical = json.loads((ROOT / SP02.reevaluation_path).read_text(encoding="utf-8"))["results"]["PHYSICAL"]
    holdouts = set(physical["holdouts"]["holdout_row_ids"])
    rows = []
    for pair in physical["strict_pairs"]:
        s = physical["sensitivities_carbon5a"][pair["row_id"]]
        rows.append(ev.SensitivityRow(pair["row_id"], "HOLDOUT" if pair["row_id"] in holdouts else "FIT",
                                      pair["experimental_mode"], pair["fe_mode"], pair["experimental_hz"],
                                      pair["fe_hz"], pair["relative_frequency_error"], pair["mac"], pair["mac"],
                                      s["S_E"], s["S_G12"], "RESOLVED", True, "accepted strict pair"))
    for excluded in physical["excluded"]:
        rows.append(ev.SensitivityRow("—", "NO_STRICT_ROW", excluded["experimental_mode"], None, 28.0, None, None,
                                      None, None, None, None, "not applicable", False, excluded["reason"]))
    return ev.SensitivityEvidence(status, specimen, (), tuple(rows),
                                  baseline={"E_in_plane_mpa": 52000.0, "G12_mpa": 4500.0},
                                  perturbations={"E_in_plane_mpa+": 54600.0, "E_in_plane_mpa-": 49400.0,
                                                 "G12_mpa+": 4725.0, "G12_mpa-": 4275.0},
                                  source=f"{SP02.reevaluation_path} (results.PHYSICAL); CARBON-5A ±5 %")


def predicted(what_if) -> dict:
    return {row.row_id: row for row in what_if.rows if row.trial_hz is not None}


class ArithmeticTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evidence = recorded_sp02_evidence()
        self.recorded = {row.row_id: row for row in self.evidence.rows if row.role != "NO_STRICT_ROW"}

    def test_zero_change_reproduces_the_baseline_exactly(self):
        result = wi.e_what_if(self.evidence, 0.0)
        self.assertEqual(result.status, wi.AVAILABLE)
        self.assertEqual(result.e_trial_mpa, 52000.0)
        rows = predicted(result)
        self.assertEqual(set(rows), {"R1", "R2", "R3"})
        for row_id, row in rows.items():
            self.assertEqual(row.trial_hz, self.recorded[row_id].fe_hz)  # exactly, not approximately
            self.assertEqual(row.error_after, row.error_before)
            self.assertEqual(row.effect, wi.UNCHANGED)
            self.assertAlmostEqual(row.error_before, self.recorded[row_id].relative_frequency_error, places=15)

    def test_positive_and_negative_changes_follow_the_recorded_sensitivities(self):
        for change in (0.05, 0.02, -0.013, -0.05):
            with self.subTest(change=change):
                result = wi.e_what_if(self.evidence, change)
                self.assertEqual(result.e_trial_mpa, 52000.0 * (1.0 + change))
                for row_id, row in predicted(result).items():
                    recorded = self.recorded[row_id]
                    self.assertEqual(row.trial_hz, recorded.fe_hz * (1.0 + change) ** recorded.s_e)
                    self.assertEqual(row.s_e, recorded.s_e)
                    self.assertAlmostEqual(row.error_after, (row.trial_hz - recorded.experimental_hz)
                                           / recorded.experimental_hz, places=15)
                    self.assertEqual(math.copysign(1.0, row.trial_hz - recorded.fe_hz), math.copysign(1.0, change))

    def test_r1_and_r2_opposite_directions_stay_visible(self):
        up, down = wi.e_what_if(self.evidence, 0.02), wi.e_what_if(self.evidence, -0.02)
        self.assertEqual((predicted(up)["R1"].effect, predicted(up)["R2"].effect), (wi.WORSENS, wi.IMPROVES))
        self.assertEqual((predicted(down)["R1"].effect, predicted(down)["R2"].effect), (wi.IMPROVES, wi.WORSENS))
        for result in (up, down):
            self.assertTrue(result.mixed)
            self.assertIn("improves one FIT mode and worsens another", result.fit_summary)
            self.assertIn("MIXED", wi.summary_text(result))

    def test_holdout_stays_separate(self):
        result = wi.e_what_if(self.evidence, -0.02)
        self.assertEqual(predicted(result)["R3"].role, "HOLDOUT")
        self.assertNotIn("R3", result.fit_summary)
        self.assertIn("R3", result.holdout_summary)
        self.assertTrue(result.holdout_summary.startswith("1 HOLDOUT row(s)"))

    def test_outliers_and_identities_are_preserved(self):
        result = wi.e_what_if(self.evidence, 0.03)
        self.assertEqual([(r.row_id, r.experimental_mode, r.fe_mode) for r in result.rows],
                         [(r.row_id, r.experimental_mode, r.fe_mode) for r in self.evidence.rows])
        outliers = [row for row in result.rows if row.role == "NO_STRICT_ROW"]
        self.assertEqual(len(outliers), 6)
        self.assertTrue(all(row.trial_hz is None and row.effect == "not predicted" for row in outliers))
        unsupported = replace(self.evidence, rows=tuple(
            replace(row, applicable=False, s_e=None, reason="not paired") if row.row_id == "R2" else row
            for row in self.evidence.rows))
        self.assertNotIn("R2", predicted(wi.e_what_if(unsupported, 0.03)))

    def test_bounds_and_labels(self):
        self.assertEqual(wi.e_what_if(self.evidence, 0.05).status, wi.AVAILABLE)
        self.assertEqual(wi.e_what_if(self.evidence, -0.05).status, wi.AVAILABLE)
        for change in (0.0501, -0.051, 0.1, float("nan"), float("inf"), True, "0.01"):
            with self.subTest(change=change):
                result = wi.e_what_if(self.evidence, change)
                self.assertEqual(result.status, wi.BLOCKED)
                self.assertEqual(result.rows, ())
        self.assertIn("not extrapolated", wi.e_what_if(self.evidence, 0.06).reason)
        self.assertIn("NOT_A_RECOMMENDED_E", wi.LABELS)
        self.assertIn("NOT_AN_IDENTIFIED_MATERIAL_PROPERTY", wi.LABELS)
        fields = set(wi.EWhatIf.__dataclass_fields__) | set(wi.WhatIfRow.__dataclass_fields__)
        self.assertFalse(fields & {"recommended_e", "best_e", "optimum", "g12_trial", "calibration"})


class BlockingTests(unittest.TestCase):
    def test_only_verified_sp02_evidence_enables_the_preview(self):
        cases = {
            "REFERENCE_ONLY": recorded_sp02_evidence(ev.REFERENCE_ONLY),
            "NOT_APPLICABLE": ev.not_applicable("wrong ODB"),
            "no evidence": None,
            "unsupported specimen": recorded_sp02_evidence(ev.VERIFIED, specimen="SP05"),
        }
        for name, evidence in cases.items():
            with self.subTest(name=name):
                result = wi.e_what_if(evidence, 0.02)
                self.assertEqual(result.status, wi.BLOCKED)
                self.assertEqual(result.rows, ())
                self.assertIsNone(result.e_trial_mpa)
        # G2d-3: SP-13 is supported, but SP-02 rows relabelled SP13 are not SP-13 evidence (no preview at all)
        spoofed = wi.e_what_if(recorded_sp02_evidence(ev.VERIFIED, specimen="SP13"), 0.02)
        self.assertEqual(spoofed.status, wi.INCOMPLETE)
        self.assertEqual(spoofed.rows, ())
        self.assertIsNone(spoofed.e_trial_mpa)
        self.assertIn(ev.REFERENCE_ONLY, wi.e_what_if(cases["REFERENCE_ONLY"], 0.0).reason)
        other_baseline = replace(recorded_sp02_evidence(), baseline={"E_in_plane_mpa": 55593.0, "G12_mpa": 4500.0})
        self.assertEqual(wi.e_what_if(other_baseline, 0.0).status, wi.BLOCKED)


def _pump(root, seconds: float = 0.2) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        root.update()
        time.sleep(0.01)


class TkTests(unittest.TestCase):
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
        import test_core
        import ui_workflow

        disabled = {"autosave_enabled": False, "restore_on_startup": False, "show_recovery_notice": False}
        with mock.patch.object(ui_workflow, "load_recovery_preferences", return_value=disabled), \
                mock.patch.object(ui_workflow, "discover_abaqus_installations", return_value=()):
            application = main.app.ModalComparatorApp(root)
            application._show_expert()  # APP-UI.1: the window opens on Home; these are expert-tab checks
        result = test_core.ModalCoreTests("test_export_excel_base_writes_the_documented_sheets_and_values").synthetic_result()
        with tempfile.TemporaryDirectory() as directory:
            application.cache = Path(directory)
            application.result = result
            application._populate(result)
        return root, application

    def show(self, application, evidence) -> None:
        application._show_sensitivity_evidence(evidence, application.result, application._sensitivity_generation,
                                               threading.Event())

    def table(self, application):
        return [tuple(str(v) for v in application.what_if_table.item(k, "values"))
                for k in application.what_if_table.get_children()]

    def test_preview_follows_verified_evidence_and_is_invalidated(self):
        root, application = self.application()
        self.assertEqual(str(application.what_if_spinbox.cget("state")), "disabled")
        self.assertIn(wi.BLOCKED, application.what_if_status.cget("text"))
        evidence = recorded_sp02_evidence()
        self.show(application, evidence)
        self.assertEqual(str(application.what_if_spinbox.cget("state")), "normal")
        self.assertEqual(self.table(application), [tuple(r) for r in wi.table_rows(wi.e_what_if(evidence, 0.0))])
        application.what_if_change.set("2")
        self.assertEqual(self.table(application), [tuple(r) for r in wi.table_rows(wi.e_what_if(evidence, 0.02))])
        self.assertIn("MIXED", application.what_if_status.cget("text"))
        application.what_if_change.set("7")  # outside the archived interval: refused, never extrapolated
        self.assertEqual(self.table(application), [])
        self.assertIn("not extrapolated", application.what_if_details.get("1.0", "end"))
        application.what_if_change.set("2")

        application.abaqus_path.set(str(Path(tempfile.gettempdir()) / "another.odb"))  # input change
        self.assertEqual(self.table(application), [])
        self.assertEqual(str(application.what_if_spinbox.cget("state")), "disabled")
        self.assertEqual(application.what_if_change.get(), "0.0")

        self.show(application, evidence)
        application.what_if_change.set("-3")
        self.assertTrue(self.table(application))
        application._populate(application.result)  # a new comparison result
        self.assertEqual(self.table(application), [])
        self.show(application, evidence)
        application._clear_result_presentation("Analysis is running")
        self.assertEqual(self.table(application), [])

    def test_reference_only_and_not_applicable_block_the_preview(self):
        root, application = self.application()
        for evidence in (recorded_sp02_evidence(ev.REFERENCE_ONLY), ev.not_applicable("wrong ODB")):
            with self.subTest(status=evidence.status):
                self.show(application, evidence)
                self.assertEqual(str(application.what_if_spinbox.cget("state")), "disabled")
                application.what_if_change.set("2")
                self.assertEqual(self.table(application), [])
                self.assertIn(wi.BLOCKED, application.what_if_status.cget("text"))

    def test_layout_keeps_every_table_reachable_at_the_minimum_window_size(self):
        root, application = self.application()
        from ui_policy import MINIMUM_WINDOW_SIZE

        self.show(application, recorded_sp02_evidence())
        application.tabs.select(application.scaling_tab)
        for width, height in ((1160, 720), MINIMUM_WINDOW_SIZE):
            with self.subTest(width=width, height=height):
                root.geometry(f"{width}x{height}+0+0")
                root.deiconify()
                _pump(root)
                for widget in (application.scaling_table, application.sensitivity_table, application.what_if_table,
                               application.what_if_spinbox, application.what_if_xscroll, application.what_if_status,
                               application.sensitivity_button):
                    self.assertTrue(widget.winfo_ismapped(), str(widget))
                table = application.what_if_table
                table.xview_moveto(1.0)
                _pump(root)
                self.assertTrue(table.bbox(table.get_children()[0], "note"))


class RealArchivedShapeTests(unittest.TestCase):
    """SP-02 on real archived data (store-gated; no Abaqus): real UNV, identity-verified archived FE geometry and the
    ARCHIVED CARBON-4C baseline shapes, compared on the accepted physical registration; G2c is VERIFIED and the what-if
    follows the recorded S_E. Not exercised: Abaqus extraction from the ODB and the GUI worker."""

    def test_real_sp02_chain(self):
        from domain.experiment_fixture import fixture_roots_from_environment, load_experiment_fixture_manifest

        roots = fixture_roots_from_environment()
        missing = [store for store in ("snadwich", "carbon-project-archive") if store not in roots]
        if missing:
            self.skipTest(f"data stores {missing} not configured")
        import numpy as np

        from domain.specimen_manifest import load_specimen_manifest
        from modal_core import ModalDataset, ModeShape, compare_modal_datasets
        from services.fe_shape_pack import load_shape_pack, load_shape_pack_record
        from services.physical_registration import load_fe_geometry
        from universal_reader import load_universal_modal_file

        fixture = load_experiment_fixture_manifest(ROOT / ev.FIXTURE_MANIFEST).fixture(SP02.fixture_id)
        odb = roots["carbon-project-archive"] / "carbon4c/run_sp02/SP02_f3e592281bebce66.odb"
        unv = roots["snadwich"] / "SP-02/SP02_polymax_retry_260803.unv"
        if not odb.is_file() or not unv.is_file():
            self.skipTest("SP02 archive files are not available")
        experimental = load_universal_modal_file(unv, modal_set=fixture.modal_set.name)
        fe = load_fe_geometry(load_specimen_manifest(ROOT / "docs/auto_id/specimens/SP02.physical.specimen.json"), roots)
        pack = load_shape_pack(load_shape_pack_record(ROOT / "docs/auto_id/fe_shapes/SP02_f3e592281bebce66.shape-pack.json"),
                               roots)
        ids = np.asarray(fe.node_ids, dtype=object)
        index = {node: i for i, node in enumerate(ids.tolist())}
        rows = np.array([index[str(node)] for node in pack.node_ids])
        modes = []
        for k, (number, hz) in enumerate(zip(pack.mode_numbers, pack.frequencies_hz)):
            if number > 17:
                continue
            vectors = np.zeros((len(ids), 3), dtype=np.float32)
            vectors[rows] = pack.displacements[k]
            modes.append(ModeShape(number, hz, ids, fe.coordinates, vectors))
        abaqus = ModalDataset("archived shape pack", odb, modes)
        governed = ev.bind_accepted_reference(odb, unv, abaqus, experimental)
        result = compare_modal_datasets(abaqus, experimental, frozen_registration=governed.registration)
        result.metadata["comparison_inputs"] = ev.comparison_input_record(odb, unv, fixture.modal_set.name)
        evidence = ev.check_archived_sensitivity_evidence(result)
        self.assertEqual(evidence.status, ev.VERIFIED, evidence.reasons)
        recorded = recorded_sp02_evidence()
        expected = predicted(wi.e_what_if(recorded, 0.05))
        live = predicted(wi.e_what_if(evidence, 0.05))
        self.assertEqual(set(live), {"R1", "R2", "R3"})
        for row_id, row in live.items():
            self.assertAlmostEqual(row.trial_hz, expected[row_id].trial_hz, places=9)
            self.assertEqual(row.effect, expected[row_id].effect)


if __name__ == "__main__":
    unittest.main()

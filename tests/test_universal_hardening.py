from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import universal_hardening  # noqa: E402
import universal_reader  # noqa: E402
from reviewed_core import _inferred_measurement_mask
from universal_hardening import (
    POSITIONAL_2414_LAYOUT,
    _local_coordinate_diagnostics,
    _positional_2414_fields,
    _postprocess_measurement_masks,
    _safe_mode_55,
    _safe_mode_2414,
    _scalar,
)

NODES_2414 = np.array([11, 12, 13])
COORDINATES_2414 = np.array([[0.0, 0.0, 0.0], [0.125, 0.0, 0.0], [0.25, 0.0625, 0.0]])


def shape_values(mode: int, complex_values: bool = True, dof: int = 3):
    """Per-node record-15 values that %.5e reproduces exactly: X, Y, Z (and rotations) as (real, imaginary)."""
    rows = []
    for k in range(1, 4):
        components = [0.125 * k, -0.0625 * k, 0.5 * k + mode] + [0.03125 * k] * (dof - 3)
        if complex_values:
            rows.append(np.array([value for c in components for value in (c, -c / 8.0)]))
        else:
            rows.append(np.array(components))
    return rows


def write_2414_unv(path: Path, records) -> Path:
    """A real UNV written by pyuff 2.5.x: dataset 2411 nodes and dataset 2414 records.

    ``records`` holds dicts with analysis_type, mode, frequency and optional overrides. Analysis type 5 is written in
    pyuff's named frequency-response layout; every other type in pyuff's positional layout (records 10-13 by field
    position, record 15 as data_at_node), which is what pyuff.UFF.read_sets() returns for them.
    """
    import pyuff

    path = Path(path)
    path.unlink(missing_ok=True)
    uff = pyuff.UFF(str(path))
    uff.write_sets(pyuff.prepare_2411(node_nums=NODES_2414, def_cs=np.zeros(3, dtype=int),
                                      disp_cs=np.zeros(3, dtype=int), color=np.ones(3, dtype=int),
                                      x=COORDINATES_2414[:, 0], y=COORDINATES_2414[:, 1], z=COORDINATES_2414[:, 2]),
                   "add")
    for spec in records:
        analysis_type, mode, frequency = spec["analysis_type"], spec["mode"], spec["frequency"]
        record = {"type": 2414, "analysis_dataset_label": spec.get("label", mode),
                  "analysis_dataset_name": spec.get("name", f"Mode {mode}"), "dataset_location": 1,
                  "id1": "synthetic", "id2": "x", "id3": "x", "id4": "x", "id5": "x", "model_type": 1,
                  "analysis_type": analysis_type, "data_characteristic": spec.get("data_characteristic", 2),
                  "result_type": 8, "data_type": spec.get("data_type", 5),
                  "number_of_data_values_for_the_data_component": spec.get("count", 3), "node_nums": NODES_2414}
        if analysis_type == 5:
            record.update(design_set_id=1, iteration_number=0, solution_set_id=1, boundary_condition=0, load_set=1,
                          mode_number=0, time_step_number=0, frequency_number=mode, creation_option=1,
                          number_retained=1, time=0.0, frequency=frequency, eigenvalue=0.0, modal_mass=0.0,
                          viscous_damping=0.0, hysteretic_damping=0.0, real_part_eigenvalue=0.0,
                          imaginary_part_eigenvalue=0.0, real_part_of_modal_A_or_modal_mass=0.0,
                          imaginary_part_of_modal_A_or_modal_mass=0.0, real_part_of_modal_B_or_modal_mass=0.0,
                          imaginary_part_of_modal_B_or_modal_mass=0.0, x=np.full(3, 0.5 + 0j),
                          y=np.zeros(3, complex), z=np.full(3, 0.25 + 0j))
        else:
            record.update({f"record10_field{i}": v for i, v in enumerate((1, 0, 1, 0, 1, mode, 0, 0), 1)})
            record.update(record11_field1=0, record11_field2=0)
            record.update({f"record12_field{i}": v for i, v in enumerate(
                (0.0, frequency, (2 * np.pi * frequency) ** 2, spec.get("modal_mass", 1.5), 0.0125, 0.0), 1)})
            record.update({f"record13_field{i}": 0.0 for i in range(1, 7)})
            record["data_at_node"] = spec.get("values", shape_values(mode, spec.get("data_type", 5) in (5, 6),
                                                                     spec.get("count", 3)))
        uff.write_sets(record, "add")
    return path


class UniversalHardeningTests(unittest.TestCase):
    def setUp(self):
        self.geometry = {
            1: np.array([0.0, 0.0, 0.0]),
            2: np.array([1.0, 0.0, 0.0]),
            3: np.array([0.0, 1.0, 0.0]),
        }

    def test_scalar_accepts_numpy_arrays(self):
        self.assertEqual(_scalar(np.array([7.0])), 7.0)
        self.assertIsNone(_scalar(np.array([]), None))

    def test_dataset_55_array_scalars_and_single_axis_mask(self):
        dataset = {
            "type": np.array([55]),
            "node_nums": np.array([1, 2, 3]),
            "r3": np.array([1.0, -0.5, 0.2]),
            "mode_n": np.array([4]),
            "freq": np.array([123.4]),
            "modal_damp_vis": np.array([0.012]),
            "modal_m": np.array([2.5]),
        }
        mode = _safe_mode_55(dataset, self.geometry, 1)
        self.assertEqual(mode.number, 4)
        self.assertAlmostEqual(mode.frequency_hz, 123.4)
        self.assertTrue(np.all(mode.measured_dofs[:, 2]))
        self.assertFalse(np.any(mode.measured_dofs[:, :2]))

    @staticmethod
    def dataset_55(r1, r2, r3, mode=1):
        return {
            "type": np.array([55]),
            "node_nums": np.array([1, 2, 3]),
            "r1": np.asarray(r1, dtype=complex),
            "r2": np.asarray(r2, dtype=complex),
            "r3": np.asarray(r3, dtype=complex),
            "mode_n": np.array([mode]),
            "freq": np.array([100.0 + mode]),
        }

    def test_dataset_55_zero_filled_in_plane_arrays_are_not_measured(self):
        # A 1D vibrometer export carries r1/r2 arrays that are structurally zero.
        mode = _safe_mode_55(
            self.dataset_55([0.0] * 3, [0.0] * 3, [1.0, -0.5, 0.2 + 0.1j]), self.geometry, 1
        )
        np.testing.assert_array_equal(mode.measured_dofs, [[False, False, True]] * 3)

    def test_dataset_55_genuinely_active_components_remain_measured(self):
        mode = _safe_mode_55(
            self.dataset_55([1.0e-3, 0.0, -2.0e-3], [0.3, -0.2, 0.1], [1.0, -0.5, 0.2]),
            self.geometry, 1,
        )
        np.testing.assert_array_equal(mode.measured_dofs, [[True, True, True]] * 3)

    def test_dataset_55_component_rule_matches_reviewed_core_inference(self):
        # Below the reviewed-core relative norm (1e-6 of the mode norm) a
        # component is round-off, exactly as _inferred_measurement_mask decides.
        mode = _safe_mode_55(
            self.dataset_55([1.0e-9, 0.0, 0.0], [0.0] * 3, [1.0, -0.5, 0.2]), self.geometry, 1
        )
        np.testing.assert_array_equal(
            mode.measured_dofs, _inferred_measurement_mask(mode.vectors)
        )
        np.testing.assert_array_equal(mode.measured_dofs, [[False, False, True]] * 3)

    def test_dataset_55_masks_are_per_mode_without_cross_mode_borrowing(self):
        in_plane = _safe_mode_55(
            self.dataset_55([0.4, 0.1, -0.2], [0.0] * 3, [1.0, -0.5, 0.2], mode=1), self.geometry, 1
        )
        out_of_plane = _safe_mode_55(
            self.dataset_55([0.0] * 3, [0.0] * 3, [0.3, 0.9, -0.4], mode=2), self.geometry, 2
        )
        modes = [in_plane, out_of_plane]
        _postprocess_measurement_masks(modes)
        np.testing.assert_array_equal(in_plane.measured_dofs, [[True, False, True]] * 3)
        np.testing.assert_array_equal(out_of_plane.measured_dofs, [[False, False, True]] * 3)

    def test_dataset_2414_key_variants(self):
        dataset = {
            "type": np.array([2414]),
            "node_numbers": np.array([1, 2, 3]),
            "d1": np.array([0.1, 0.2, 0.3]),
            "d2": np.array([0.4, 0.5, 0.6]),
            "mode_n": np.array([8]),
            "freq": np.array([88.0]),
            "damping": np.array([0.02]),
            "mass": np.array([1.7]),
        }
        mode = _safe_mode_2414(dataset, self.geometry, 1)
        self.assertEqual(mode.number, 8)
        self.assertAlmostEqual(mode.frequency_hz, 88.0)
        self.assertTrue(np.all(mode.measured_dofs[:, :2]))
        self.assertFalse(np.any(mode.measured_dofs[:, 2]))

    def test_local_coordinate_system_warning_detection(self):
        diagnostics = _local_coordinate_diagnostics(
            [
                {
                    "type": 2411,
                    "def_cs": np.array([0, 7, 7]),
                    "disp_cs": np.array([0, 0, 0]),
                },
                {"type": 2420},
            ]
        )
        self.assertTrue(diagnostics["coordinate_system_dataset_2420_present"])
        self.assertIn(7, diagnostics["non_default_coordinate_system_ids"])


class RealPyuffDataset2414Tests(unittest.TestCase):
    """APP-IMPORT-2414: dataset-2414 files on disk written and read by pyuff (positional record layout)."""

    @classmethod
    def setUpClass(cls) -> None:
        universal_hardening.install_universal_hardening()  # the importer as the application installs it

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="app_import_2414_"))
        self.addCleanup(shutil.rmtree, self.folder, True)

    def load(self, name, records):
        path = write_2414_unv(self.folder / name, records)
        return universal_reader.load_universal_modal_file(path)

    def test_pyuff_returns_the_positional_layout_for_normal_modes(self):
        import pyuff

        path = write_2414_unv(self.folder / "layout.unv", [{"analysis_type": 2, "mode": 7, "frequency": 23.5}])
        record = next(item for item in pyuff.UFF(str(path)).read_sets() if item.get("type") == 2414)
        self.assertNotIn("mode_number", record)
        self.assertNotIn("frequency", record)
        self.assertEqual((record["record10_field6"], record["record12_field2"]), (7, 23.5))
        self.assertEqual(len(record["data_at_node"]), 3)

    def test_normal_modes_from_a_real_file(self):
        dataset = self.load("normal.unv", [{"analysis_type": 2, "mode": 7, "frequency": 23.5, "label": 1},
                                           {"analysis_type": 2, "mode": 9, "frequency": 47.25, "label": 2,
                                            "modal_mass": 2.25}])
        self.assertEqual([(m.number, m.frequency_hz) for m in dataset.modes], [(7, 23.5), (9, 47.25)])
        for mode in dataset.modes:
            expected = np.array([row[0::2] + 1j * row[1::2] for row in shape_values(mode.number)])
            np.testing.assert_array_equal(mode.vectors, expected)  # exact components, nothing rescaled
            self.assertTrue(np.all(mode.measured_dofs))
            np.testing.assert_array_equal(mode.coordinates, COORDINATES_2414)
            self.assertEqual(list(mode.node_ids), [11, 12, 13])
            self.assertEqual(mode.damping_ratio, 0.0125)
            self.assertEqual(mode.metadata["dataset_2414_layout"], POSITIONAL_2414_LAYOUT)
            self.assertEqual(mode.metadata["record_classification"], "physical")
        self.assertEqual([m.modal_mass for m in dataset.modes], [1.5, 2.25])
        self.assertEqual(dataset.metadata["import_warnings"], [])

    def test_real_valued_and_six_dof_records(self):
        dataset = self.load("variants.unv", [{"analysis_type": 2, "mode": 3, "frequency": 12.0, "data_type": 2},
                                             {"analysis_type": 2, "mode": 4, "frequency": 18.0,
                                              "data_characteristic": 3, "count": 6}])
        real, six = dataset.modes
        np.testing.assert_array_equal(real.vectors, np.array(shape_values(3, complex_values=False)))
        full = np.array([row[0::2] + 1j * row[1::2] for row in shape_values(4, dof=6)])
        np.testing.assert_array_equal(six.vectors, full[:, :3])  # translations X, Y, Z; rotations not used

    def test_components_written_as_zeros_are_not_measured_dofs(self):
        z_only = [np.array([0.0, 0.0, 0.0, 0.0, 0.5 * k, -0.0625 * k]) for k in (1, 2, 3)]
        dataset = self.load("z_only.unv", [{"analysis_type": 2, "mode": 2, "frequency": 14.0, "values": z_only}])
        mode, = dataset.modes
        np.testing.assert_array_equal(mode.vectors[:, :2], np.zeros((3, 2)))  # the zeros stay as written
        np.testing.assert_array_equal(mode.measured_dofs, np.array([[False, False, True]] * 3))
        np.testing.assert_array_equal(mode.measured_dofs, _inferred_measurement_mask(mode.vectors))  # the 55 rule

    def test_complex_eigenvalue_records_are_refused_without_a_derived_frequency(self):
        dataset = self.load("complex.unv", [{"analysis_type": 2, "mode": 1, "frequency": 10.0},
                                            {"analysis_type": 3, "mode": 2, "frequency": 20.0},
                                            {"analysis_type": 7, "mode": 3, "frequency": 30.0}])
        self.assertEqual([m.number for m in dataset.modes], [1])
        warnings = dataset.metadata["import_warnings"]
        for analysis_type in (3, 7):
            self.assertTrue(any(f"(analysis type {analysis_type}): complex eigenvalue data define no frequency" in w
                                for w in warnings), warnings)
        self.assertEqual([item["classification"] for item in dataset.metadata["dataset_2414_record_classifications"]],
                         ["physical", "physical", "physical"])  # the classification is unchanged
        with self.assertRaisesRegex(ValueError, "No experimental modal vectors"):
            self.load("complex_only.unv", [{"analysis_type": 3, "mode": 2, "frequency": 20.0}])

    def test_inconsistent_or_empty_records_are_refused(self):
        zero = [np.zeros(6)] * 3
        short = [np.array([0.5, 0.0, 0.25])] * 3  # complex data type with 3 values per node instead of 6
        cases = {
            "zero shape": ({"values": zero}, "translational shape is zero at every node"),
            "value count": ({"values": short}, "has 3 values; 6 finite values are required"),
            "characteristic": ({"data_characteristic": 3}, "data characteristic 3 with 3 values per node"),
            "mode number": ({"mode": 0}, "record 10 field 6 (mode number) is 0"),
            "frequency": ({"frequency": 0.0}, "record 12 field 2 (frequency) is 0.0"),
        }
        for name, (override, message) in cases.items():
            with self.subTest(case=name):
                spec = {"analysis_type": 2, "mode": 5, "frequency": 15.0, "label": 2, **override}
                dataset = self.load(f"{name}.unv", [{"analysis_type": 2, "mode": 1, "frequency": 10.0}, spec])
                self.assertEqual([m.number for m in dataset.modes], [1])  # nothing invented for the bad record
                self.assertTrue(any(message in w for w in dataset.metadata["import_warnings"]),
                                dataset.metadata["import_warnings"])

    def test_non_modal_and_ambiguous_classification_is_kept(self):
        dataset = self.load("classes.unv", [{"analysis_type": 2, "mode": 1, "frequency": 10.0},
                                            {"analysis_type": 5, "mode": 2, "frequency": 25.0},
                                            {"analysis_type": 0, "mode": 3, "frequency": 35.0}])
        audits = dataset.metadata["dataset_2414_record_classifications"]
        self.assertEqual([(a["classification"], a["included"]) for a in audits],
                         [("physical", True), ("non_modal", False), ("ambiguous", True)])
        self.assertEqual([m.number for m in dataset.modes], [1])

    def test_direct_unit_rules(self):
        record = {"analysis_type": 2, "dataset_location": 2, "data_type": 5, "data_characteristic": 2,
                  "number_of_data_values_for_the_data_component": 3, "node_nums": np.array([1]),
                  "data_at_node": [np.ones(6)], "record10_field6": 1, "record12_field2": 5.0}
        with self.assertRaisesRegex(ValueError, "not data at nodes"):
            _positional_2414_fields(record)
        with self.assertRaisesRegex(ValueError, "data type 1 is not a real or complex"):
            _positional_2414_fields({**record, "dataset_location": 1, "data_type": 1})
        named = {"node_nums": np.array([1, 2, 3]), "z": np.array([1.0, 2.0, 3.0]), "mode_number": 4,
                 "frequency": 9.0, "data_at_node": [np.ones(6)] * 3, "record10_field6": 99, "record12_field2": 1.0}
        geometry = {node: np.array([0.1 * node, 0.0, 0.0]) for node in (1, 2, 3)}
        mode = _safe_mode_2414(named, geometry, 1)  # named fields win; the positional reading is not applied
        self.assertEqual((mode.number, mode.frequency_hz), (4, 9.0))
        self.assertNotIn("dataset_2414_layout", mode.metadata)


if __name__ == "__main__":
    unittest.main()

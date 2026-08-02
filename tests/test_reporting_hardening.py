from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import reporting
import reporting_hardening as target
from modal_core import ModePairResult
from test_core import ModalCoreTests


class ReportingHardeningTests(unittest.TestCase):
    def setUp(self):
        self._original_installed = target._INSTALLED
        self._original_functions = {
            name: getattr(reporting, name)
            for name in (
                "render_mode_shape",
                "render_overlay",
                "render_pair_images",
                "render_mac_matrix",
                "render_frequency_comparison",
            )
        }
        target._INSTALLED = False

    def tearDown(self):
        target._INSTALLED = self._original_installed
        for name, value in self._original_functions.items():
            setattr(reporting, name, value)

    def test_plane_projection_flags_a_flat_grid_as_planar(self):
        x, y = np.meshgrid(np.linspace(0.0, 1.0, 5), np.linspace(0.0, 2.0, 4))
        coordinates = np.column_stack((x.ravel(), y.ravel(), np.zeros(x.size)))

        projected_x, projected_y, planar = target._plane_projection(coordinates)

        self.assertTrue(planar)
        self.assertEqual(len(projected_x), len(coordinates))
        self.assertEqual(len(projected_y), len(coordinates))

    def test_plane_projection_flags_a_scattered_cloud_as_not_planar(self):
        rng = np.random.default_rng(0)
        coordinates = rng.uniform(-1.0, 1.0, size=(30, 3))

        _, _, planar = target._plane_projection(coordinates)

        self.assertFalse(planar)

    def test_pair_measured_values_uses_measured_mask_and_aligns_phase_to_experiment_reference(self):
        shape = np.array([1.0, -1.0, 0.5, -0.5])
        coordinates = np.column_stack(
            (np.arange(len(shape), dtype=float), np.zeros(len(shape)), np.zeros(len(shape)))
        )
        abaqus_vector = np.zeros((len(shape), 3), dtype=complex)
        abaqus_vector[:, 2] = shape * 2.0
        phase = 0.7
        experimental_vector = np.zeros((len(shape), 3), dtype=complex)
        experimental_vector[:, 2] = shape * 3.0 * np.exp(1j * phase)
        # Component 0 (X) is unmeasured and deliberately full of garbage values
        # that must be excluded by the mask, not just by the finite check.
        abaqus_vector[:, 0] = 999.0
        experimental_vector[:, 0] = 999.0
        mask = np.zeros((len(shape), 3), dtype=bool)
        mask[:, 2] = True

        pair = ModePairResult(
            abaqus_mode=1,
            experimental_mode=1,
            abaqus_frequency_hz=10.0,
            experimental_frequency_hz=10.0,
            frequency_error_percent=0.0,
            mac=1.0,
            status="ok",
            order_changed=False,
            mapped_points=len(shape),
            abaqus_vector=abaqus_vector,
            experimental_vector=experimental_vector,
            coordinates=coordinates,
        )
        pair.measured_dof_mask = mask

        abaqus_real, experiment_real = target._pair_measured_values(pair)

        # The reference used for phase alignment is experiment's own
        # largest-magnitude measured entry, so experiment always comes back
        # purely real at its original magnitude once re-referenced to itself.
        np.testing.assert_allclose(experiment_real, shape * 3.0, atol=1e-10)
        np.testing.assert_allclose(abaqus_real, shape * 2.0 * np.cos(phase), atol=1e-10)

    def test_render_functions_produce_files_for_the_full_pipeline(self):
        result = ModalCoreTests().synthetic_result()
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            shape_path = target.render_mode_shape(
                result.pairs[0].coordinates,
                result.pairs[0].abaqus_vector,
                "Abaqus mode 1",
                directory / "shape.png",
            )
            overlay_path = target.render_overlay(result.pairs[0], directory / "overlay.png")
            pair_paths = target.render_pair_images(result.pairs[0], directory / "pair")
            mac_path = target.render_mac_matrix(result, directory / "mac.png")
            frequency_path = target.render_frequency_comparison(result, directory / "frequency.png")

            for path in (shape_path, overlay_path, mac_path, frequency_path, *pair_paths.values()):
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 1000)

    def test_install_reporting_hardening_patches_reporting_and_is_idempotent(self):
        target.install_reporting_hardening()
        wrapped = {
            name: getattr(reporting, name) for name in self._original_functions
        }
        self.assertIs(wrapped["render_mode_shape"], target.render_mode_shape)
        self.assertIs(wrapped["render_overlay"], target.render_overlay)
        self.assertIs(wrapped["render_pair_images"], target.render_pair_images)
        self.assertIs(wrapped["render_mac_matrix"], target.render_mac_matrix)
        self.assertIs(wrapped["render_frequency_comparison"], target.render_frequency_comparison)

        target.install_reporting_hardening()
        for name, value in wrapped.items():
            self.assertIs(getattr(reporting, name), value)


if __name__ == "__main__":
    unittest.main()

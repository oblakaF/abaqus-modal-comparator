from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

import amplitude_correlation as target
import reporting
from test_core import ModalCoreTests


class FakeMaster:
    def __init__(self):
        self.text = None

    def configure(self, **kwargs):
        self.text = kwargs.get("text", self.text)


class FakeLabel:
    def __init__(self):
        self.master = FakeMaster()


def _make_fake_app_module():
    """Fresh, unwrapped ModalComparatorApp-alike class per call.

    install_correlation_ui mutates the class attribute in place, so reusing
    one module-level class across tests would leak the wrap from whichever
    test ran first.
    """

    class FakeApp:
        def _build_shapes(self):
            self.shape_labels = [FakeLabel(), FakeLabel(), FakeLabel()]

    class FakeAppModule:
        ModalComparatorApp = FakeApp

    return FakeAppModule


class AmplitudeCorrelationTests(unittest.TestCase):
    def setUp(self):
        self._original_installed = target._INSTALLED
        self._original_ui_installed = target._UI_INSTALLED
        self._original_render_overlay = reporting.render_overlay
        self._original_render_pair_images = reporting.render_pair_images
        target._INSTALLED = False
        target._UI_INSTALLED = False

    def tearDown(self):
        target._INSTALLED = self._original_installed
        target._UI_INSTALLED = self._original_ui_installed
        reporting.render_overlay = self._original_render_overlay
        reporting.render_pair_images = self._original_render_pair_images

    def make_pair(self, mac):
        result = ModalCoreTests().synthetic_result()
        pair = result.pairs[0]
        if mac is None:
            pair.mac = None
        return pair

    def test_render_amplitude_correlation_creates_a_file_with_and_without_mac(self):
        for mac in (0.95, None):
            with self.subTest(mac=mac):
                pair = self.make_pair(mac)
                with tempfile.TemporaryDirectory() as directory:
                    output_path = Path(directory) / "correlation.png"
                    result_path = target.render_amplitude_correlation(pair, output_path)
                    self.assertTrue(result_path.exists())
                    self.assertGreater(result_path.stat().st_size, 1000)

    def test_render_pair_images_returns_three_existing_files(self):
        pair = self.make_pair(0.9)
        with tempfile.TemporaryDirectory() as directory:
            paths = target.render_pair_images(pair, Path(directory))
            self.assertEqual(set(paths), {"abaqus", "experimental", "overlay"})
            for path in paths.values():
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 1000)

    def test_install_amplitude_correlation_patches_reporting_and_is_idempotent(self):
        target.install_amplitude_correlation()
        self.assertIs(reporting.render_overlay, target.render_amplitude_correlation)
        self.assertIs(reporting.render_pair_images, target.render_pair_images)

        target.install_amplitude_correlation()
        self.assertIs(reporting.render_overlay, target.render_amplitude_correlation)
        self.assertIs(reporting.render_pair_images, target.render_pair_images)

    def test_install_correlation_ui_relabels_third_shape_tab(self):
        fake_module = _make_fake_app_module()
        target.install_correlation_ui(fake_module)
        app = fake_module.ModalComparatorApp()
        app._build_shapes()
        self.assertEqual(app.shape_labels[2].master.text, "Amplitude correlation")

    def test_install_correlation_ui_is_idempotent(self):
        fake_module = _make_fake_app_module()
        target.install_correlation_ui(fake_module)
        wrapped_once = fake_module.ModalComparatorApp._build_shapes

        target.install_correlation_ui(fake_module)

        self.assertIs(fake_module.ModalComparatorApp._build_shapes, wrapped_once)


if __name__ == "__main__":
    unittest.main()

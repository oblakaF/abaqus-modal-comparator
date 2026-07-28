from pathlib import Path
import sys
import tempfile
import unittest

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from advanced_metrics import (
    render_abaqus_automac,
    render_comac_map,
    render_experimental_automac,
)
from metrics_normalization import install_metrics_normalization
from test_core import ModalCoreTests


class FigureExportTests(unittest.TestCase):
    def test_individual_automac_and_comac_figures_are_large_and_readable(self):
        install_metrics_normalization()
        result = ModalCoreTests().synthetic_result()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            paths = [
                render_abaqus_automac(result, output / "abaqus_automac.png"),
                render_experimental_automac(result, output / "experimental_automac.png"),
                render_comac_map(result, output / "comac_map.png"),
            ]
            for path in paths:
                self.assertGreater(path.stat().st_size, 10_000)
                with Image.open(path) as image:
                    self.assertGreaterEqual(image.width, 1200)
                    self.assertGreaterEqual(image.height, 1000)


if __name__ == "__main__":
    unittest.main()

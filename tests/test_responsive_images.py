import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from responsive_images import fit_image_size


class ResponsiveImageSizingTests(unittest.TestCase):
    def test_landscape_image_fits_width(self):
        self.assertEqual(fit_image_size((1600, 900), (400, 300)), (400, 225))

    def test_portrait_image_fits_height(self):
        self.assertEqual(fit_image_size((800, 1200), (500, 500)), (333, 500))

    def test_image_can_expand_to_fill_available_space(self):
        self.assertEqual(fit_image_size((100, 50), (400, 300)), (400, 200))

    def test_invalid_dimensions_are_rejected(self):
        with self.assertRaises(ValueError):
            fit_image_size((0, 100), (400, 300))
        with self.assertRaises(ValueError):
            fit_image_size((100, 100), (0, 300))


if __name__ == "__main__":
    unittest.main()

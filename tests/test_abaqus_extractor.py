from pathlib import Path
import importlib.util
import sys
import types
import unittest

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "abaqus_scripts" / "extract_odb.py"

fake_odb_access = types.ModuleType("odbAccess")
fake_odb_access.openOdb = lambda *args, **kwargs: None
sys.modules.setdefault("odbAccess", fake_odb_access)

spec = importlib.util.spec_from_file_location("extract_odb_for_test", SCRIPT)
extractor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(extractor)


class FakeValue:
    def __init__(self, data, conjugate_data=None):
        self.data = data
        self.conjugateData = conjugate_data


class AbaqusExtractorTests(unittest.TestCase):
    def test_numpy_vector_data_does_not_use_boolean_truth(self):
        value = FakeValue(
            np.array([1.0, 2.0, 3.0]),
            np.array([0.1, 0.2, 0.3]),
        )
        real, imaginary = extractor.vector_parts(value)
        self.assertEqual(real, [1.0, 2.0, 3.0])
        self.assertEqual(imaginary, [0.1, 0.2, 0.3])

    def test_missing_conjugate_data_is_zero_filled(self):
        value = FakeValue((4.0, 5.0), None)
        real, imaginary = extractor.vector_parts(value)
        self.assertEqual(real, [4.0, 5.0, 0.0])
        self.assertEqual(imaginary, [0.0, 0.0, 0.0])

    def test_scalar_data_is_supported(self):
        value = FakeValue(7.0, None)
        real, imaginary = extractor.vector_parts(value)
        self.assertEqual(real, [7.0, 0.0, 0.0])
        self.assertEqual(imaginary, [0.0, 0.0, 0.0])


if __name__ == "__main__":
    unittest.main()

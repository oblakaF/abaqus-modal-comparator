"""Shared helper for the M7b corrective tests: record equality that is exact for structure and text and
tolerant only to the last floating-point digits (different numpy / BLAS builds, e.g. Windows vs Linux CI)."""

from __future__ import annotations

import math


def assert_records_close(test, actual, expected, rel: float = 1e-9, path: str = "$") -> None:
    if isinstance(expected, dict):
        test.assertIsInstance(actual, dict, path)
        test.assertEqual(sorted(actual), sorted(expected), path)
        for key in expected:
            assert_records_close(test, actual[key], expected[key], rel, f"{path}.{key}")
    elif isinstance(expected, (list, tuple)):
        test.assertIsInstance(actual, (list, tuple), path)
        test.assertEqual(len(actual), len(expected), path)
        for index, (a, e) in enumerate(zip(actual, expected)):
            assert_records_close(test, a, e, rel, f"{path}[{index}]")
    elif isinstance(expected, float) and not isinstance(expected, bool):
        test.assertIsInstance(actual, (int, float), path)
        test.assertTrue(math.isclose(actual, expected, rel_tol=rel, abs_tol=1e-300), f"{path}: {actual} != {expected}")
    else:
        test.assertEqual(actual, expected, path)

"""Orientation-candidate completeness before the ambiguity gate (CARBON-3C-R2).

A slightly rectangular planar scan on a slightly rectangular plate is matched
almost equally well with and without a 90-degree axis swap. Both families must
reach ``_select_unambiguous_geometry``; a runtime candidate cap must never hide
one of them before the physical-orientation decision.
"""

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape
from performance_tuning import install_performance_tuning
from reviewed_core import (
    GeometryOrientationAmbiguousError,
    _candidate_summary,
    compare_modal_datasets,
    geometry_alignment_candidates,
)


def _plate() -> np.ndarray:
    # 30 x 31 plate, 1.0 mesh pitch, single (exterior) plane.
    return np.array([[x, y, 0.0] for x in range(31) for y in range(32)], dtype=float)


def _scan() -> np.ndarray:
    # 11 x 11 scan, slightly rectangular (20.3 x 20.7), incommensurate with the mesh.
    return np.array(
        [[2.03 * i, 2.07 * j, -1.0] for i in range(11) for j in range(11)], dtype=float
    )


def _datasets():
    plate, scan = _plate(), _scan()
    fe_vectors = np.zeros_like(plate)
    fe_vectors[:, 2] = np.sin(plate[:, 0] / 7.0) + np.cos(plate[:, 1] / 5.0)
    exp_vectors = np.zeros_like(scan)
    exp_vectors[:, 2] = np.sin(scan[:, 0] / 7.0) + np.cos(scan[:, 1] / 5.0)
    fe = ModalDataset(
        "Abaqus", Path("plate.odb"),
        [ModeShape(7, 100.0, np.arange(1, len(plate) + 1), plate, fe_vectors)],
    )
    experiment = ModalDataset(
        "Experiment", Path("scan.unv"),
        [ModeShape(1, 100.2, np.arange(1, len(scan) + 1), scan, exp_vectors)],
    )
    return fe, experiment


def _families(candidates):
    return {tuple(candidate["axis_permutation"][:2]) for candidate in candidates}


class OrientationCandidateCompletenessTests(unittest.TestCase):
    def test_runtime_path_exposes_swapped_and_unswapped_families(self):
        install_performance_tuning()  # the production runtime layer from main.py
        fe, experiment = _datasets()
        with self.assertRaises(GeometryOrientationAmbiguousError) as raised:
            compare_modal_datasets(fe, experiment, coordinate_scale_override=1.0)
        candidates = raised.exception.ambiguous_candidates
        self.assertEqual(_families(candidates), {(0, 1), (1, 0)})
        # Four in-plane mappings per family on a doubly symmetric plate/scan.
        self.assertEqual(len(candidates), 8)
        for candidate in candidates:
            self.assertNotIn("mac", candidate)

    def test_both_families_are_geometrically_plausible(self):
        fe, experiment = _datasets()
        plausible = geometry_alignment_candidates(
            fe.modes[0].coordinates, experiment.modes[0].coordinates,
            coordinate_scale_override=1.0,
        )
        rms = {}
        for candidate in plausible:
            family = tuple(_candidate_summary(candidate)["axis_permutation"][:2])
            rms.setdefault(family, []).append(candidate.normalized_rms_distance)
        self.assertEqual(set(rms), {(0, 1), (1, 0)})
        # Every planar z-sign duplicate is kept: 8 per family.
        self.assertEqual(sum(len(values) for values in rms.values()), 16)
        ratio = max(min(values) for values in rms.values()) / min(min(values) for values in rms.values())
        self.assertLess(ratio, 1.5)

    def test_performance_tuning_does_not_change_the_candidate_set(self):
        fe, experiment = _datasets()

        def candidate_ids():
            return [
                _candidate_summary(candidate)["candidate_id"]
                for candidate in geometry_alignment_candidates(
                    fe.modes[0].coordinates, experiment.modes[0].coordinates,
                    coordinate_scale_override=1.0,
                )
            ]

        before = candidate_ids()
        install_performance_tuning()
        self.assertEqual(candidate_ids(), before)

    def test_candidate_order_is_deterministic(self):
        fe, experiment = _datasets()

        def ordered():
            return [
                _candidate_summary(candidate)["candidate_id"]
                for candidate in geometry_alignment_candidates(
                    fe.modes[0].coordinates, experiment.modes[0].coordinates,
                    coordinate_scale_override=1.0,
                )
            ]

        self.assertEqual(ordered(), ordered())


if __name__ == "__main__":
    unittest.main()

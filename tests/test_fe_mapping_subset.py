"""Explicit FE mapping-node subset for geometry registration (CARBON-3C-R1).

A planar scan measures one exterior face of a layered (sandwich) model.  The
full-model nearest-node search can land on core or inner-interface nodes, so a
caller may restrict the geometry search to an explicit FE node subset while the
FE dataset, its identity and its full-model mode vectors stay unchanged.
"""

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from modal_core import ModalDataset, ModeShape
from modal_core import compare_modal_datasets as facade_compare
from reviewed_core import (
    GeometryOrientationAmbiguousError,
    compare_modal_datasets,
    geometry_alignment_candidates,
)
from scientific_state import modal_dataset_geometry_identity


BOTTOM_EXTERIOR_Z = 0.0
BOTTOM_INTERFACE_Z = 0.45
CORE_Z = 1.45
TOP_INTERFACE_Z = 2.45
TOP_EXTERIOR_Z = 2.9


def _grid(step: float) -> np.ndarray:
    xs = np.arange(0.0, 6.0 + 1.0e-9, step)
    ys = np.arange(0.0, 4.0 + 1.0e-9, step)
    return np.array([[x, y] for x in xs for y in ys])


def _layer(prefix: str, z: float, step: float):
    plan = _grid(step)
    ids = [f"{prefix}:{index + 1}" for index in range(len(plan))]
    coordinates = np.column_stack((plan, np.full(len(plan), z)))
    return ids, coordinates


def _shape(coordinates: np.ndarray) -> np.ndarray:
    vectors = np.zeros((len(coordinates), 3))
    vectors[:, 2] = np.sin(np.pi * coordinates[:, 0] / 6.0) * np.cos(np.pi * coordinates[:, 1] / 8.0)
    return vectors


def sandwich_model() -> tuple[ModalDataset, dict[str, list[str]]]:
    """Core first, exterior faces last, so subset-local indices differ from full ones."""
    layers = {
        "CORE": _layer("CORE", CORE_Z, 0.5),
        "BOT_IN": _layer("BOTIN", BOTTOM_INTERFACE_Z, 1.0),
        "TOP_IN": _layer("TOPIN", TOP_INTERFACE_Z, 1.0),
        "BOT_EXT": _layer("BOTEXT", BOTTOM_EXTERIOR_Z, 1.0),
        "TOP_EXT": _layer("TOPEXT", TOP_EXTERIOR_Z, 1.0),
    }
    node_ids = np.array([node for ids, _ in layers.values() for node in ids], dtype=object)
    coordinates = np.vstack([coords for _, coords in layers.values()])
    mode = ModeShape(7, 100.0, node_ids, coordinates, _shape(coordinates))
    dataset = ModalDataset("Abaqus", Path("sandwich.odb"), [mode])
    return dataset, {name: ids for name, (ids, _) in layers.items()}


def planar_scan() -> ModalDataset:
    plan = _grid(1.0)
    coordinates = np.column_stack((plan, np.full(len(plan), -1.0)))
    node_ids = np.arange(1, len(plan) + 1)
    return ModalDataset(
        "Experiment",
        Path("scan.unv"),
        [ModeShape(1, 100.5, node_ids, coordinates, _shape(coordinates))],
    )


def _identity_candidate(candidates):
    for candidate in candidates:
        if np.allclose(candidate["rotation"], np.eye(3)):
            return candidate
    raise AssertionError("identity orientation candidate missing")


class FeMappingSubsetTests(unittest.TestCase):
    def setUp(self):
        self.fe, self.layers = sandwich_model()
        self.experiment = planar_scan()
        self.reference = self.fe.modes[0]

    def _compare(self, subset, *, compare=compare_modal_datasets):
        with self.assertRaises(GeometryOrientationAmbiguousError) as raised:
            compare(self.fe, self.experiment, coordinate_scale_override=1.0,
                    fe_mapping_node_ids=subset)
        candidate = _identity_candidate(raised.exception.ambiguous_candidates)
        return compare(
            self.fe,
            self.experiment,
            coordinate_scale_override=1.0,
            fe_mapping_node_ids=subset,
            orientation_selection=candidate,
        )

    def _mapped_ids(self, result):
        return [str(value) for value in self.reference.node_ids[result.geometry.experimental_to_abaqus]]

    def test_full_model_mapping_hits_internal_core_nodes(self):
        # Characterisation of the defect: without a subset the centred planar
        # scan lands on the model mid-thickness, i.e. on core nodes.
        candidate = geometry_alignment_candidates(
            self.reference.coordinates,
            self.experiment.modes[0].coordinates,
            coordinate_scale_override=1.0,
        )[0]
        mapped = self.reference.node_ids[candidate.experimental_to_abaqus]
        self.assertTrue(all(str(node).startswith("CORE:") for node in mapped))

    def test_top_exterior_subset_maps_only_top_exterior_nodes(self):
        result = self._compare(self.layers["TOP_EXT"])
        mapped = self._mapped_ids(result)
        self.assertTrue(all(node.startswith("TOPEXT:") for node in mapped))
        self.assertEqual(len(set(mapped)), len(mapped))
        z = self.reference.coordinates[result.geometry.experimental_to_abaqus][:, 2]
        np.testing.assert_allclose(z, TOP_EXTERIOR_Z)
        self.assertLess(result.metadata["mapping_max_residual_in_abaqus_units"], 1.0e-9)

    def test_bottom_exterior_subset_can_be_selected_explicitly(self):
        result = self._compare(self.layers["BOT_EXT"])
        mapped = self._mapped_ids(result)
        self.assertTrue(all(node.startswith("BOTEXT:") for node in mapped))
        z = self.reference.coordinates[result.geometry.experimental_to_abaqus][:, 2]
        np.testing.assert_allclose(z, BOTTOM_EXTERIOR_Z)

    def test_mapping_indices_reference_the_full_fe_arrays(self):
        result = self._compare(self.layers["TOP_EXT"])
        indices = np.asarray(result.geometry.experimental_to_abaqus)
        top_start = len(self.reference.node_ids) - len(self.layers["TOP_EXT"])
        # Subset-local indices would all be < len(subset); full indices are not.
        self.assertTrue(np.all(indices >= top_start))
        np.testing.assert_allclose(
            self.reference.coordinates[indices][:, :2],
            self.experiment.modes[0].coordinates[:, :2],
        )

    def test_fe_dataset_and_geometry_identity_remain_full_model(self):
        before = modal_dataset_geometry_identity(self.fe)
        result = self._compare(self.layers["TOP_EXT"])
        self.assertEqual(modal_dataset_geometry_identity(result.abaqus), before)
        self.assertEqual(before["node_count"], len(self.reference.node_ids))
        returned = result.abaqus.modes[0]
        self.assertEqual(len(returned.node_ids), len(self.reference.node_ids))
        self.assertEqual(returned.vectors.shape, self.reference.vectors.shape)

    def test_subset_is_recorded_and_changes_candidate_identity(self):
        full_ids = set()
        try:
            compare_modal_datasets(self.fe, self.experiment, coordinate_scale_override=1.0)
        except GeometryOrientationAmbiguousError as error:
            full_ids = {item["candidate_id"] for item in error.ambiguous_candidates}
        with self.assertRaises(GeometryOrientationAmbiguousError) as raised:
            compare_modal_datasets(self.fe, self.experiment, coordinate_scale_override=1.0,
                                   fe_mapping_node_ids=self.layers["TOP_EXT"])
        subset_ids = {item["candidate_id"] for item in raised.exception.ambiguous_candidates}
        self.assertTrue(full_ids)
        self.assertFalse(full_ids & subset_ids)
        for item in raised.exception.ambiguous_candidates:
            self.assertEqual(item["fe_mapping_node_subset"]["node_count"], len(self.layers["TOP_EXT"]))

        result = self._compare(self.layers["TOP_EXT"])
        recorded = result.metadata["fe_mapping_node_subset"]
        self.assertEqual(recorded["node_count"], len(self.layers["TOP_EXT"]))
        self.assertEqual(len(recorded["sha256"]), 64)

    def test_without_subset_candidate_summary_is_unchanged(self):
        with self.assertRaises(GeometryOrientationAmbiguousError) as raised:
            compare_modal_datasets(self.fe, self.experiment, coordinate_scale_override=1.0)
        for item in raised.exception.ambiguous_candidates:
            self.assertNotIn("fe_mapping_node_subset", item)

    def test_orientation_ambiguity_policy_is_unchanged_with_a_subset(self):
        with self.assertRaises(GeometryOrientationAmbiguousError) as raised:
            compare_modal_datasets(self.fe, self.experiment, coordinate_scale_override=1.0,
                                   fe_mapping_node_ids=self.layers["TOP_EXT"])
        self.assertGreaterEqual(len(raised.exception.ambiguous_candidates), 2)
        for candidate in raised.exception.ambiguous_candidates:
            self.assertNotIn("mac", candidate)
        with self.assertRaises(GeometryOrientationAmbiguousError):
            compare_modal_datasets(
                self.fe, self.experiment, coordinate_scale_override=1.0,
                fe_mapping_node_ids=self.layers["TOP_EXT"],
                orientation_selection={"candidate_id": "geometry-obsolete"},
            )

    def test_quality_control_facade_passes_the_subset_through(self):
        result = self._compare(self.layers["TOP_EXT"], compare=facade_compare)
        self.assertTrue(all(node.startswith("TOPEXT:") for node in self._mapped_ids(result)))

    def test_unknown_duplicate_or_too_small_subsets_are_refused(self):
        cases = (
            self.layers["TOP_EXT"] + ["NOPE:1"],
            self.layers["TOP_EXT"] + self.layers["TOP_EXT"][:1],
            self.layers["TOP_EXT"][:2],
        )
        for subset in cases:
            with self.subTest(size=len(subset)):
                with self.assertRaises(ValueError):
                    compare_modal_datasets(self.fe, self.experiment, coordinate_scale_override=1.0,
                                           fe_mapping_node_ids=subset)


if __name__ == "__main__":
    unittest.main()

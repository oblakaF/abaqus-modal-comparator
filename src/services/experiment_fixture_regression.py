"""Regression check of one real experiment fixture (Auto-ID M0.3).

Verifies, for a record of the M0.2 fixture manifest, that the current code still
reproduces the accepted identities of a real experiment:

- the experimental source resolves through its configured store root with the
  pinned size and SHA-256;
- the PolyMAX import selects the pinned modal set from the pinned source type and
  yields the pinned mode and point counts;
- the FrozenRegistration is hash-sealed, carries the pinned registration hash,
  source identity, modal set and FE geometry identity, and replays exactly on the
  imported nodes and measured-DOF contract.

The check only calls the existing reader, registration and measurement-mask code.
It never repairs, substitutes or regenerates anything: every difference raises.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Callable, Mapping

import numpy as np

from domain.experiment_fixture import ExperimentFixture, resolve_external_file
from domain.registration import REGISTRATION_DOF_COMPONENTS, FrozenRegistration
from modal_core import ModalDataset
from reviewed_core import experimental_measurement_masks
from universal_reader import load_universal_modal_file


# Manifest source type -> the reader's declared mode source.  A peak-derived or any
# other mode source never satisfies a curve-fitted fixture.
SOURCE_TYPE_MODE_SOURCES = {
    "polymax-curve-fitted-dataset-55": "curve-fitted dataset 55",
}

ModalLoader = Callable[..., ModalDataset]


class FixtureRegressionError(ValueError):
    """The current code or data no longer reproduces a pinned fixture identity."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field


@dataclass(frozen=True)
class FixtureRegressionReport:
    fixture_id: str
    modal_set_key: str
    mode_source: str
    mode_count: int
    point_count: int
    measured_dofs: tuple[str, ...]
    registration_hash: str
    fe_geometry_sha256: str


def _require(condition: bool, field: str, message: str) -> None:
    if not condition:
        raise FixtureRegressionError(field, message)


def _load_registration(fixture: ExperimentFixture, repo_root: Path) -> FrozenRegistration:
    path = Path(repo_root) / fixture.registration.path
    try:
        with open(path, encoding="utf-8") as handle:
            # from_dict recomputes the content hash and rejects any edited field.
            return FrozenRegistration.from_dict(json.load(handle))
    except (OSError, TypeError, ValueError) as exc:
        raise FixtureRegressionError("registration", f"cannot restore {fixture.registration.path}: {exc}") from exc


def _check_registration(fixture: ExperimentFixture, registration: FrozenRegistration) -> None:
    pinned = fixture.registration
    _require(
        registration.registration_hash == pinned.registration_hash,
        "registration.registration_hash",
        f"{registration.registration_hash} differs from the pinned {pinned.registration_hash}.",
    )
    _require(
        registration.registration_schema_version == pinned.schema_version,
        "registration.schema_version",
        f"{registration.registration_schema_version!r} differs from the pinned {pinned.schema_version!r}.",
    )
    source = registration.experimental_source_identity
    _require(
        source.get("sha256") == fixture.experimental_source.sha256
        and source.get("size") == fixture.experimental_source.size_bytes,
        "registration.experimental_source_identity",
        "the registration is bound to a different experimental source than the fixture.",
    )
    _require(
        registration.experimental_modal_set_identity == fixture.modal_set.name,
        "registration.experimental_modal_set_identity",
        f"{registration.experimental_modal_set_identity!r} differs from the pinned modal set "
        f"{fixture.modal_set.name!r}.",
    )
    geometry = registration.fe_geometry_identity
    expected = fixture.fe.geometry_identity
    _require(
        geometry.get("sha256") == expected.sha256
        and geometry.get("node_count") == expected.node_count
        and geometry.get("schema_version") == expected.schema_version,
        "fe.geometry_identity",
        "the registration's FE geometry identity differs from the pinned FE identity.",
    )


def _contract_dofs(registration: FrozenRegistration) -> tuple[str, ...]:
    frozen = np.asarray(registration.measured_dof_contract, dtype=bool)
    measured = frozen.all(axis=0)
    _require(
        np.array_equal(measured, frozen.any(axis=0)),
        "registration.measured_dof_contract",
        "the frozen contract is not uniform across points; it cannot be summarised as a DOF set.",
    )
    return tuple(name for name, flag in zip(REGISTRATION_DOF_COMPONENTS, measured) if flag)


def _node_list(node_ids: object) -> list:
    return [item.item() if isinstance(item, np.generic) else item for item in np.asarray(node_ids, dtype=object).reshape(-1)]


def verify_experiment_fixture(
    fixture: ExperimentFixture,
    roots: Mapping[str, Path],
    *,
    repo_root: Path,
    load_modal_dataset: ModalLoader = load_universal_modal_file,
) -> FixtureRegressionReport:
    """Return a report if every pinned identity is reproduced; otherwise raise.

    Raises ``FixtureSourceUnavailableError`` / ``FixtureSourceMismatchError`` for the
    experimental source and ``FixtureRegressionError`` for everything else.
    """

    source_path = resolve_external_file(fixture.experimental_source, roots)

    registration = _load_registration(fixture, repo_root)
    _check_registration(fixture, registration)

    pinned = fixture.modal_set
    expected_mode_source = SOURCE_TYPE_MODE_SOURCES.get(pinned.source_type)
    _require(
        expected_mode_source is not None,
        "modal_set.source_type",
        f"{pinned.source_type!r} has no registered reader mode source.",
    )
    dataset = load_modal_dataset(source_path, modal_set=pinned.name)
    metadata = dataset.metadata
    _require(
        metadata.get("mode_source") == expected_mode_source,
        "modal_set.source_type",
        f"the reader produced {metadata.get('mode_source')!r} modes, not {expected_mode_source!r}.",
    )
    available = [item.get("key") for item in metadata.get("available_modal_sets", [])]
    _require(
        pinned.name in available and metadata.get("modal_set_key") == pinned.name,
        "modal_set.name",
        f"selected {metadata.get('modal_set_key')!r}; available {available}; pinned {pinned.name!r}.",
    )

    modes = dataset.sorted_modes()
    _require(
        len(modes) == pinned.mode_count,
        "modal_set.mode_count",
        f"imported {len(modes)} modes; the fixture pins {pinned.mode_count}.",
    )
    node_ids = _node_list(modes[0].node_ids)
    _require(
        all(_node_list(mode.node_ids) == node_ids for mode in modes),
        "modal_set.measurement_point_count",
        "modes of the set do not share one measurement point list.",
    )
    _require(
        len(node_ids) == pinned.measurement_point_count,
        "modal_set.measurement_point_count",
        f"imported {len(node_ids)} points; the fixture pins {pinned.measurement_point_count}.",
    )

    _require(
        node_ids == list(registration.experimental_node_ids),
        "registration.experimental_node_ids",
        "the imported measurement points differ from the frozen registration's points.",
    )
    _require(
        len(registration.mapped_fe_node_ids) == pinned.measurement_point_count,
        "registration.mapped_fe_node_ids",
        "the registration does not map one FE node per measurement point.",
    )

    contract_dofs = _contract_dofs(registration)
    _require(
        contract_dofs == pinned.measured_dofs,
        "modal_set.measured_dofs",
        f"the frozen contract measures {contract_dofs}; the fixture pins {pinned.measured_dofs}.",
    )
    frozen = np.asarray(registration.measured_dof_contract, dtype=bool)
    for mode, mask in zip(modes, experimental_measurement_masks(modes, modes[0].node_ids)):
        _require(
            np.array_equal(np.asarray(mask, dtype=bool), frozen),
            "measured_dof_contract",
            f"mode {mode.number} measured-DOF mask differs from the frozen measurement contract.",
        )

    return FixtureRegressionReport(
        fixture_id=fixture.fixture_id,
        modal_set_key=metadata["modal_set_key"],
        mode_source=metadata["mode_source"],
        mode_count=len(modes),
        point_count=len(node_ids),
        measured_dofs=contract_dofs,
        registration_hash=registration.registration_hash,
        fe_geometry_sha256=registration.fe_geometry_identity["sha256"],
    )

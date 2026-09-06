from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, Mapping, Tuple, TypeVar

from .modal_observation import (
    InclusionStatus,
    ModalCluster,
    ModalObservation,
    ObservationUncertainty,
)
from .parameter_model import (
    IdentificationParameter,
    ParameterPrior,
    ParameterResultStatus,
    ParameterRole,
    ParameterScope,
)
from .specimen import (
    CoreFamily,
    Design,
    FaceSectionFamily,
    InterfaceFamily,
    PhysicalSpecimen,
    PrimaryMeasurement,
    TestRun,
    require_identifier,
)


T = TypeVar("T")


def _index_unique(items: Iterable[T], attribute: str) -> Dict[str, T]:
    output: Dict[str, T] = {}
    for item in items:
        identifier = str(getattr(item, attribute))
        if identifier in output:
            raise ValueError(f"Duplicate {attribute}: {identifier!r}.")
        output[identifier] = item
    return output


def _json_value(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


@dataclass
class IdentificationCampaign:
    """A multi-specimen identification campaign and its validated references."""

    campaign_id: str
    face_section_families: Tuple[FaceSectionFamily, ...] = ()
    core_families: Tuple[CoreFamily, ...] = ()
    interface_families: Tuple[InterfaceFamily, ...] = ()
    designs: Tuple[Design, ...] = ()
    physical_specimens: Tuple[PhysicalSpecimen, ...] = ()
    test_runs: Tuple[TestRun, ...] = ()
    parameters: Tuple[IdentificationParameter, ...] = ()
    observations: Tuple[ModalObservation, ...] = ()
    modal_clusters: Tuple[ModalCluster, ...] = ()
    active_global_parameter_ids_by_specimen: Mapping[str, Tuple[str, ...]] = field(
        default_factory=dict
    )
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        require_identifier(self.campaign_id, "campaign_id")
        for name in (
            "face_section_families",
            "core_families",
            "interface_families",
            "designs",
            "physical_specimens",
            "test_runs",
            "parameters",
            "observations",
            "modal_clusters",
        ):
            setattr(self, name, tuple(getattr(self, name)))
        self.active_global_parameter_ids_by_specimen = {
            specimen_id: tuple(parameter_ids)
            for specimen_id, parameter_ids in self.active_global_parameter_ids_by_specimen.items()
        }
        self.validate()

    def validate(self) -> None:
        face_families = _index_unique(
            self.face_section_families, "face_section_family_id"
        )
        core_families = _index_unique(self.core_families, "core_family_id")
        interface_families = _index_unique(
            self.interface_families, "interface_family_id"
        )
        designs = _index_unique(self.designs, "design_id")
        specimens = _index_unique(self.physical_specimens, "physical_specimen_id")
        test_runs = _index_unique(self.test_runs, "test_run_id")
        parameters = _index_unique(self.parameters, "parameter_id")
        observations = _index_unique(self.observations, "observation_id")
        clusters = _index_unique(self.modal_clusters, "cluster_id")

        for design in designs.values():
            if design.face_section_family_id not in face_families:
                raise ValueError(
                    f"Design {design.design_id!r} references unknown face section family "
                    f"{design.face_section_family_id!r}."
                )
            if design.core_family_id is not None and design.core_family_id not in core_families:
                raise ValueError(
                    f"Design {design.design_id!r} references unknown core family "
                    f"{design.core_family_id!r}."
                )
            if (
                design.interface_family_id is not None
                and design.interface_family_id not in interface_families
            ):
                raise ValueError(
                    f"Design {design.design_id!r} references unknown interface family "
                    f"{design.interface_family_id!r}."
                )
        for specimen in specimens.values():
            if specimen.design_id not in designs:
                raise ValueError(
                    f"Physical specimen {specimen.physical_specimen_id!r} references "
                    f"unknown design {specimen.design_id!r}."
                )
        for test_run in test_runs.values():
            if test_run.physical_specimen_id not in specimens:
                raise ValueError(
                    f"Test run {test_run.test_run_id!r} references unknown physical "
                    f"specimen {test_run.physical_specimen_id!r}."
                )
        for parameter in parameters.values():
            if (
                parameter.scope == ParameterScope.SPECIMEN
                and parameter.physical_specimen_id not in specimens
            ):
                raise ValueError(
                    f"Parameter {parameter.parameter_id!r} references unknown physical "
                    f"specimen {parameter.physical_specimen_id!r}."
                )
        for observation in observations.values():
            self._validate_test_identity(
                observation.observation_id,
                observation.physical_specimen_id,
                observation.test_run_id,
                specimens,
                test_runs,
            )

        clustered_observations = set()
        for cluster in clusters.values():
            self._validate_test_identity(
                cluster.cluster_id,
                cluster.physical_specimen_id,
                cluster.test_run_id,
                specimens,
                test_runs,
            )
            for observation_id in cluster.observation_ids:
                if observation_id not in observations:
                    raise ValueError(
                        f"Modal cluster {cluster.cluster_id!r} references unknown "
                        f"observation {observation_id!r}."
                    )
                observation = observations[observation_id]
                if (
                    observation.physical_specimen_id != cluster.physical_specimen_id
                    or observation.test_run_id != cluster.test_run_id
                ):
                    raise ValueError(
                        f"Modal cluster {cluster.cluster_id!r} mixes specimen or test identities."
                    )
                if observation_id in clustered_observations:
                    raise ValueError(
                        f"Modal observation {observation_id!r} belongs to more than one cluster."
                    )
                clustered_observations.add(observation_id)

        mapping_specimens = set(self.active_global_parameter_ids_by_specimen)
        specimen_ids = set(specimens)
        if mapping_specimens != specimen_ids:
            missing = sorted(specimen_ids - mapping_specimens)
            unknown = sorted(mapping_specimens - specimen_ids)
            raise ValueError(
                "Global parameter mapping must contain exactly the campaign specimens; "
                f"missing={missing}, unknown={unknown}."
            )
        global_parameter_ids = {
            parameter.parameter_id
            for parameter in parameters.values()
            if parameter.scope == ParameterScope.GLOBAL
        }
        for specimen_id, parameter_ids in self.active_global_parameter_ids_by_specimen.items():
            if len(parameter_ids) != len(set(parameter_ids)):
                raise ValueError(
                    f"Specimen {specimen_id!r} has duplicate active global parameter IDs."
                )
            unknown = sorted(set(parameter_ids) - global_parameter_ids)
            if unknown:
                raise ValueError(
                    f"Specimen {specimen_id!r} maps unknown or non-global parameters: {unknown}."
                )

    @staticmethod
    def _validate_test_identity(
        record_id: str,
        physical_specimen_id: str,
        test_run_id: str,
        specimens: Mapping[str, PhysicalSpecimen],
        test_runs: Mapping[str, TestRun],
    ) -> None:
        if physical_specimen_id not in specimens:
            raise ValueError(
                f"Record {record_id!r} references unknown physical specimen "
                f"{physical_specimen_id!r}."
            )
        if test_run_id not in test_runs:
            raise ValueError(f"Record {record_id!r} references unknown test run {test_run_id!r}.")
        if test_runs[test_run_id].physical_specimen_id != physical_specimen_id:
            raise ValueError(
                f"Record {record_id!r} conflates test run {test_run_id!r} with physical "
                f"specimen {physical_specimen_id!r}."
            )

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-compatible representation for project persistence."""

        return _json_value(asdict(self))

    def active_global_parameters_for(
        self, physical_specimen_id: str
    ) -> Tuple[IdentificationParameter, ...]:
        """Resolve the shared parameter subset active for one specimen."""

        if physical_specimen_id not in self.active_global_parameter_ids_by_specimen:
            raise ValueError(
                f"Unknown physical specimen {physical_specimen_id!r} in campaign."
            )
        parameters = {parameter.parameter_id: parameter for parameter in self.parameters}
        return tuple(
            parameters[parameter_id]
            for parameter_id in self.active_global_parameter_ids_by_specimen[
                physical_specimen_id
            ]
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IdentificationCampaign":
        def uncertainty(value: Mapping[str, Any]) -> ObservationUncertainty:
            return ObservationUncertainty(**dict(value))

        specimens = []
        for value in payload.get("physical_specimens", []):
            item = dict(value)
            item["primary_measurements"] = tuple(
                PrimaryMeasurement(**measurement)
                for measurement in item.get("primary_measurements", [])
            )
            specimens.append(PhysicalSpecimen(**item))

        parameters = []
        for value in payload.get("parameters", []):
            item = dict(value)
            item["scope"] = ParameterScope(item["scope"])
            item["role"] = ParameterRole(item["role"])
            if item.get("prior") is not None:
                item["prior"] = ParameterPrior(**item["prior"])
            if item.get("result_status") is not None:
                item["result_status"] = ParameterResultStatus(item["result_status"])
            parameters.append(IdentificationParameter(**item))

        observations = []
        for value in payload.get("observations", []):
            item = dict(value)
            item["inclusion_status"] = InclusionStatus(item["inclusion_status"])
            item["uncertainty"] = uncertainty(item.get("uncertainty", {}))
            observations.append(ModalObservation(**item))

        clusters = []
        for value in payload.get("modal_clusters", []):
            item = dict(value)
            item["observation_ids"] = tuple(item["observation_ids"])
            item["inclusion_status"] = InclusionStatus(item["inclusion_status"])
            item["uncertainty"] = uncertainty(item.get("uncertainty", {}))
            clusters.append(ModalCluster(**item))

        return cls(
            campaign_id=str(payload["campaign_id"]),
            face_section_families=tuple(
                FaceSectionFamily(**item)
                for item in payload.get("face_section_families", [])
            ),
            core_families=tuple(
                CoreFamily(**item) for item in payload.get("core_families", [])
            ),
            interface_families=tuple(
                InterfaceFamily(**item)
                for item in payload.get("interface_families", [])
            ),
            designs=tuple(Design(**item) for item in payload.get("designs", [])),
            physical_specimens=tuple(specimens),
            test_runs=tuple(TestRun(**item) for item in payload.get("test_runs", [])),
            parameters=tuple(parameters),
            observations=tuple(observations),
            modal_clusters=tuple(clusters),
            active_global_parameter_ids_by_specimen={
                str(specimen_id): tuple(parameter_ids)
                for specimen_id, parameter_ids in payload.get(
                    "active_global_parameter_ids_by_specimen", {}
                ).items()
            },
            metadata=dict(payload.get("metadata", {})),
        )

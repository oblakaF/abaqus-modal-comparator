"""Domain contracts for multi-specimen inverse identification."""

from .evidence import (
    EvidenceProvenance,
    EvidenceRecord,
    EvidenceSourceIdentity,
    IdentificationEvidence,
    IdentifiabilityEvidence,
    SensitivityEvidence,
    ValidationEvidence,
    evidence_content_hash,
    evidence_from_dict,
    evidence_from_json,
)
from .identification_campaign import IdentificationCampaign
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
from .registration import (
    FROZEN_REGISTRATION_SCHEMA,
    REGISTRATION_DOF_COMPONENTS,
    FrozenRegistration,
    RegistrationMismatchError,
)
from .specimen import (
    CoreFamily,
    Design,
    FaceSectionFamily,
    InterfaceFamily,
    PhysicalSpecimen,
    PrimaryMeasurement,
    TestRun,
)

__all__ = [
    "CoreFamily",
    "Design",
    "EvidenceProvenance",
    "EvidenceRecord",
    "EvidenceSourceIdentity",
    "FaceSectionFamily",
    "FROZEN_REGISTRATION_SCHEMA",
    "FrozenRegistration",
    "IdentificationCampaign",
    "IdentificationEvidence",
    "IdentificationParameter",
    "IdentifiabilityEvidence",
    "InclusionStatus",
    "InterfaceFamily",
    "ModalCluster",
    "ModalObservation",
    "ObservationUncertainty",
    "ParameterPrior",
    "ParameterResultStatus",
    "ParameterRole",
    "ParameterScope",
    "PhysicalSpecimen",
    "PrimaryMeasurement",
    "REGISTRATION_DOF_COMPONENTS",
    "RegistrationMismatchError",
    "SensitivityEvidence",
    "TestRun",
    "ValidationEvidence",
    "evidence_content_hash",
    "evidence_from_dict",
    "evidence_from_json",
]

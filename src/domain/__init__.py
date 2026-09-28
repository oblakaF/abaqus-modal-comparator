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
    "SensitivityEvidence",
    "TestRun",
    "ValidationEvidence",
    "evidence_content_hash",
    "evidence_from_dict",
    "evidence_from_json",
]

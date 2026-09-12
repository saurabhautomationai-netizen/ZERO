"""ZERO Deep Discovery and Continuation Planning Subsystem."""

from zero_core.engineering.discovery.boundary import (
    BoundaryViolation,
    ProjectBoundaryValidator,
)
from zero_core.engineering.discovery.capability import (
    CapabilityAssessment,
    CapabilityAssessmentEngine,
)
from zero_core.engineering.discovery.contradiction import (
    ContradictionDetector,
    ContradictionRecord,
)
from zero_core.engineering.discovery.decisions import (
    EngineeringDecision,
    EngineeringDecisionEngine,
)
from zero_core.engineering.discovery.evidence import (
    CanonicalArtifact,
    EvidenceLedger,
    EvidenceStatus,
    EvidenceType,
    FeatureEvidence,
    VerificationLevel,
)
from zero_core.engineering.discovery.multi_worker_planner import (
    MultiWorkerPlanningCoordinator,
    ReconciledContinuationPlan,
)
from zero_core.engineering.discovery.planner import (
    DiscoveryPlanner,
    DiscoveryTaskPlan,
    ReadOnlyDiscoveryDAG,
)
from zero_core.engineering.discovery.policy import (
    ExecutionMode,
    ProhibitedOperationError,
    ReadOnlyPolicyEnforcer,
)
from zero_core.engineering.discovery.quality_gate import (
    QualityGateResult,
    SynthesisQualityGate,
)
from zero_core.engineering.discovery.section_classifier import (
    SectionCategory,
    SectionIntentClassifier,
)
from zero_core.engineering.discovery.synthesis import DiscoverySynthesisEngine

__all__ = [
    "CanonicalArtifact",
    "VerificationLevel",
    "EvidenceLedger",
    "EvidenceStatus",
    "EvidenceType",
    "FeatureEvidence",
    "ContradictionDetector",
    "ContradictionRecord",
    "ProjectBoundaryValidator",
    "BoundaryViolation",
    "CapabilityAssessmentEngine",
    "CapabilityAssessment",
    "EngineeringDecisionEngine",
    "EngineeringDecision",
    "SectionIntentClassifier",
    "SectionCategory",
    "SynthesisQualityGate",
    "QualityGateResult",
    "MultiWorkerPlanningCoordinator",
    "ReconciledContinuationPlan",
    "DiscoveryPlanner",
    "DiscoveryTaskPlan",
    "ReadOnlyDiscoveryDAG",
    "ExecutionMode",
    "ProhibitedOperationError",
    "ReadOnlyPolicyEnforcer",
    "DiscoverySynthesisEngine",
]

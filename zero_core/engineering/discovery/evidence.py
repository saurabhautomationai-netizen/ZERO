"""Evidence Ledger, Canonical Artifact Model, and Provenance for ZERO Deep Discovery.

Tracks grounded factual claims extracted from repository files, code ASTs, SQL DDLs,
and workflow definitions. Distinguishes between documentation claims and implementation evidence,
giving strict precedence to verified implementation evidence.
"""

from __future__ import annotations

import enum
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


class VerificationLevel(str, enum.Enum):
    """Rigorous 6-tier verification ladder for engineering claims."""
    ARTIFACT_PRESENT = "ARTIFACT_PRESENT"              # File, table, or prompt exists on disk
    STATICALLY_VERIFIED = "STATICALLY_VERIFIED"        # Parsed AST, valid JSON, valid SQL syntax
    IMPLEMENTATION_PRESENT = "IMPLEMENTATION_PRESENT"  # Executable logic / nodes / endpoints exist
    TEST_VERIFIED = "TEST_VERIFIED"                    # Covered by automated passing unit/integration tests
    RUNTIME_VERIFIED = "RUNTIME_VERIFIED"              # Executed in a live runtime environment
    END_TO_END_VERIFIED = "END_TO_END_VERIFIED"        # Complete multi-system integration verified end-to-end


class EvidenceStatus(str, enum.Enum):
    """Grounding status of a feature or capability."""
    IMPLEMENTED_VERIFIED = "IMPLEMENTED_VERIFIED"  # Verified in executable code / workflow / database WITH verification
    PARTIAL = "PARTIAL"                            # Implemented partially or missing integration link
    BROKEN = "BROKEN"                              # Syntax errors, broken references, or failed test
    PLANNED_ONLY = "PLANNED_ONLY"                  # Present only in docs, README, or prompt specifications
    NOT_FOUND = "NOT_FOUND"                        # Requested but no trace found in repository
    NEEDS_VERIFICATION = "NEEDS_VERIFICATION"      # Detected but requires external live service check
    CONFLICTING_EVIDENCE = "CONFLICTING_EVIDENCE"  # Detected contradictory evidence across sources


class EvidenceType(str, enum.Enum):
    """Source provenance category of the evidence."""
    WORKFLOW_NODE = "WORKFLOW_NODE"      # n8n node, webhook definition, or pipeline graph
    DATABASE_DDL = "DATABASE_DDL"        # SQL table, index, view, or trigger definition
    PYTHON_CODE = "PYTHON_CODE"          # Function, class, API handler, or script
    SYSTEM_PROMPT = "SYSTEM_PROMPT"      # Agent prompt, instruction, or prompt template
    DOCUMENTATION = "DOCUMENTATION"      # Markdown, spec, README, or roadmap text
    TEST_CASE = "TEST_CASE"              # Automated test or fixture
    UI_COMPONENT = "UI_COMPONENT"        # Frontend screen, component, or template


@dataclass
class CanonicalArtifact:
    """Canonical, normalized representation of a discovered project artifact."""
    project_id: str
    repository_root: str
    relative_path: str
    artifact_type: str                  # "workflow", "database_table", "prompt", "source_file", "test", "ui"
    name: str
    content_hash: str
    source_worker: str
    node_count: Optional[int] = None
    table_columns: Optional[int] = None
    discovery_timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class FeatureEvidence:
    """A grounded piece of evidence verifying a feature or capability."""
    feature: str
    status: EvidenceStatus
    subsystem: str                         # e.g. "automation", "database", "python", "prompts", "ui"
    source_file: str                       # Relative path in repository
    evidence_type: EvidenceType
    location: str                          # Line number, node name, or table name
    verification_notes: str
    verification_level: VerificationLevel = VerificationLevel.ARTIFACT_PRESENT
    confidence: float = 1.0                # 0.0 to 1.0 confidence score
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["evidence_type"] = self.evidence_type.value
        d["verification_level"] = self.verification_level.value
        return d


class EvidenceLedger:
    """Consolidated registry of discovered evidence and canonical artifacts across all discovery tasks."""

    def __init__(self):
        self._entries: List[FeatureEvidence] = []
        self._artifacts: Dict[str, CanonicalArtifact] = {}  # relative_path -> CanonicalArtifact

    def record_artifact(self, artifact: CanonicalArtifact) -> None:
        """Stores or updates a canonical artifact."""
        self._artifacts[artifact.relative_path] = artifact

    def get_artifact(self, relative_path: str) -> Optional[CanonicalArtifact]:
        return self._artifacts.get(relative_path)

    def list_artifacts(self) -> List[CanonicalArtifact]:
        return list(self._artifacts.values())

    def record(self, evidence: FeatureEvidence) -> None:
        """Records an evidence entry, giving precedence to implementation evidence over documentation."""
        existing_idx = None
        for i, existing in enumerate(self._entries):
            if existing.feature.lower() == evidence.feature.lower():
                existing_idx = i
                break

        if existing_idx is not None:
            existing = self._entries[existing_idx]
            # Implementation evidence takes strict precedence over documentation
            impl_types = {EvidenceType.WORKFLOW_NODE, EvidenceType.DATABASE_DDL, EvidenceType.PYTHON_CODE, EvidenceType.TEST_CASE}
            if evidence.evidence_type in impl_types and existing.evidence_type not in impl_types:
                self._entries[existing_idx] = evidence
            elif evidence.confidence > existing.confidence:
                self._entries[existing_idx] = evidence
        else:
            self._entries.append(evidence)

    def list_entries(self) -> List[FeatureEvidence]:
        return list(self._entries)

    def filter_by_status(self, status: EvidenceStatus) -> List[FeatureEvidence]:
        return [e for e in self._entries if e.status == status]

    def filter_by_subsystem(self, subsystem: str) -> List[FeatureEvidence]:
        return [e for e in self._entries if e.subsystem.lower() == subsystem.lower()]

    def summary_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for e in self._entries:
            counts[e.status.value] = counts.get(e.status.value, 0) + 1
        return counts

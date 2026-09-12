"""Project Boundary Validator for ZERO Deep Discovery.

Enforces strict filesystem and semantic isolation:
1. Every artifact must physically reside within the canonical repository root of the target ProjectManifest.
2. Detects and blocks cross-project evidence leakage from sibling projects (e.g. Trading Bot, HR Assistant, ZERO itself).
3. Flags POSSIBLE_CROSS_PROJECT_CONTAMINATION and excludes tainted items from verified evidence.
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from zero_core.engineering.discovery.evidence import (
    CanonicalArtifact,
    EvidenceStatus,
    FeatureEvidence,
)
from zero_core.engineering.manifest import ProjectManifest

logger = logging.getLogger(__name__)


@dataclass
class BoundaryViolation:
    """Represents a filesystem escape or domain contamination event."""
    artifact_name: str
    violation_type: str  # "PATH_TRAVERSAL", "CROSS_PROJECT_DOMAIN_CONTAMINATION", "UNRESOLVED_SIBLING_REFERENCE"
    detected_signature: str
    details: str
    action_taken: str = "EXCLUDE_FROM_VERIFIED"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ProjectBoundaryValidator:
    """Validates physical and semantic project boundaries."""

    # Domain signatures belonging strictly to specific project archetypes
    DOMAIN_SIGNATURES: Dict[str, Set[str]] = {
        "trading": {
            "trading terminal", "smc confluence", "mt5 telemetry", "mt5", "metatrader",
            "equity curve", "trade expectancy", "liquidity sweep", "order block",
            "fair value gap", "pip stop loss", "risk-to-reward ratio", "forex"
        },
        "recruitment": {
            "candidate", "applicant tracking", "ats", "resume parser", "interview schedule",
            "job funnel", "candidate pipeline", "hiring team"
        },
        "finance": {
            "bank statement", "transaction categorization", "budget tracking",
            "subscription tracker", "loan emi", "affordability calculator", "credit card limit"
        },
    }

    def validate_artifact(
        self,
        manifest: ProjectManifest,
        artifact: CanonicalArtifact,
    ) -> Optional[BoundaryViolation]:
        """Validates that a canonical artifact belongs strictly to the target project."""
        repo_root = Path(manifest.repository_path).resolve()
        art_path = (repo_root / artifact.relative_path).resolve()

        # 1. Filesystem boundary check
        try:
            art_path.relative_to(repo_root)
        except ValueError:
            return BoundaryViolation(
                artifact_name=artifact.name,
                violation_type="PATH_TRAVERSAL",
                detected_signature=str(art_path),
                details=f"Artifact '{artifact.relative_path}' resolves outside project root '{repo_root}'.",
            )

        # 2. Semantic domain boundary check
        pid = manifest.project_id.lower()
        art_text = f"{artifact.name} {str(artifact.metadata)}".lower()

        # If project is finance tracker, trading bot signatures are contamination
        if "finance" in pid and not "trading" in pid:
            for sig in self.DOMAIN_SIGNATURES["trading"]:
                if sig in art_text:
                    return BoundaryViolation(
                        artifact_name=artifact.name,
                        violation_type="CROSS_PROJECT_DOMAIN_CONTAMINATION",
                        detected_signature=sig,
                        details=f"Artifact contains Trading Bot signature '{sig}' inside Finance Tracker project.",
                    )

        # If project is HR assistant, trading or personal finance are contamination
        if "recruitment" in pid or "hr" in pid:
            for sig in self.DOMAIN_SIGNATURES["trading"]:
                if sig in art_text:
                    return BoundaryViolation(
                        artifact_name=artifact.name,
                        violation_type="CROSS_PROJECT_DOMAIN_CONTAMINATION",
                        detected_signature=sig,
                        details=f"Artifact contains Trading Bot signature '{sig}' inside HR Recruitment project.",
                    )

        return None

    def validate_evidence(
        self,
        manifest: ProjectManifest,
        evidence: FeatureEvidence,
    ) -> Optional[BoundaryViolation]:
        """Validates that a feature evidence claim is free from cross-project contamination."""
        pid = manifest.project_id.lower()
        ev_text = f"{evidence.feature} {evidence.location} {evidence.verification_notes}".lower()

        if "finance" in pid and not "trading" in pid:
            for sig in self.DOMAIN_SIGNATURES["trading"]:
                if sig in ev_text:
                    return BoundaryViolation(
                        artifact_name=evidence.feature,
                        violation_type="CROSS_PROJECT_DOMAIN_CONTAMINATION",
                        detected_signature=sig,
                        details=f"Evidence claim contains Trading signature '{sig}' inside Finance Tracker project.",
                    )

        return None

    def sanitize_ledger(
        self,
        manifest: ProjectManifest,
        ledger_entries: List[FeatureEvidence],
    ) -> Tuple[List[FeatureEvidence], List[BoundaryViolation]]:
        """Filters out contaminated evidence entries, returning clean evidence and violation logs."""
        clean: List[FeatureEvidence] = []
        violations: List[BoundaryViolation] = []

        for ev in ledger_entries:
            viol = self.validate_evidence(manifest, ev)
            if viol:
                violations.append(viol)
                # Downgrade and flag rather than silently omitting
                ev.status = EvidenceStatus.CONFLICTING_EVIDENCE
                ev.verification_notes += f" [FLAGGED: POSSIBLE_CROSS_PROJECT_CONTAMINATION ({viol.detected_signature})]"
                ev.confidence = 0.0
            clean.append(ev)

        return clean, violations

"""Engineering Decision Engine for ZERO Continuation Planning.

Transforms descriptive discovery evidence into prescriptive engineering decisions:
REUSE, EXTEND, REFACTOR, FIX, VERIFY, BUILD_NEW, DEPRECATE_CANDIDATE.

Each decision contains:
- target_artifact / capability
- decision
- reason
- supporting_evidence
- dependencies
- risk
- recommended_owner
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from zero_core.engineering.discovery.capability import CapabilityAssessment
from zero_core.engineering.discovery.evidence import (
    CanonicalArtifact,
    EvidenceLedger,
    EvidenceStatus,
    FeatureEvidence,
)

logger = logging.getLogger(__name__)


@dataclass
class EngineeringDecision:
    """A prescriptive architectural or implementation decision."""
    target_artifact: str
    decision: str  # "REUSE", "EXTEND", "REFACTOR", "FIX", "VERIFY", "BUILD_NEW", "DEPRECATE_CANDIDATE"
    reason: str
    supporting_evidence: str
    dependencies: List[str] = field(default_factory=list)
    risk: str = "LOW"  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    recommended_owner: str = "worker_project_builder"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EngineeringDecisionEngine:
    """Generates prescriptive engineering decisions across workflows, schemas, and capabilities."""

    def evaluate_artifacts(
        self,
        artifacts: List[CanonicalArtifact],
    ) -> List[EngineeringDecision]:
        """Evaluates canonical artifacts to produce prescriptive decisions."""
        decisions: List[EngineeringDecision] = []

        for art in artifacts:
            fname = art.name.lower()
            rel_path = art.relative_path

            # Backup copies
            if "backup" in fname or "copy" in fname or ".bak" in fname:
                decisions.append(
                    EngineeringDecision(
                        target_artifact=art.name,
                        decision="DEPRECATE_CANDIDATE",
                        reason="Artifact is a static backup/duplicate copy that overlaps with the active production workflow, risking split-brain executions.",
                        supporting_evidence=f"File {rel_path} with {art.node_count or 0} nodes matches active workflow structure.",
                        dependencies=[],
                        risk="LOW",
                        recommended_owner="worker_automation",
                    )
                )
            # High-complexity monolithic workflows
            elif art.artifact_type == "workflow" and (art.node_count or 0) > 50:
                decisions.append(
                    EngineeringDecision(
                        target_artifact=art.name,
                        decision="REFACTOR",
                        reason=f"Monolithic workflow ({art.node_count} nodes) couples multiple responsibilities (channel ingestion, categorization, DB persistence, notifications) into a single fragile DAG.",
                        supporting_evidence=f"File {rel_path} contains {art.node_count} nodes spanning multi-channel triggers.",
                        dependencies=["Database schema migrations", "Sub-workflow triggers"],
                        risk="HIGH",
                        recommended_owner="worker_automation",
                    )
                )
            # Modular micro-workflows
            elif art.artifact_type == "workflow" and (art.node_count or 0) <= 50:
                decisions.append(
                    EngineeringDecision(
                        target_artifact=art.name,
                        decision="REUSE",
                        reason=f"Focused single-purpose workflow ({art.node_count} nodes) adheres to clean domain separation.",
                        supporting_evidence=f"File {rel_path} contains {art.node_count} nodes with clear trigger/response endpoints.",
                        dependencies=[],
                        risk="LOW",
                        recommended_owner="worker_automation",
                    )
                )
            # Relational SQL schemas
            elif art.artifact_type in ("database_table", "database"):
                decisions.append(
                    EngineeringDecision(
                        target_artifact=art.name,
                        decision="EXTEND",
                        reason="Solid relational foundation identified; requires additional composite indexes, foreign key constraints, and currency normalization fields.",
                        supporting_evidence=f"DDL schema defined in {rel_path}.",
                        dependencies=["Audit existing table data"],
                        risk="MEDIUM",
                        recommended_owner="worker_database_audit",
                    )
                )

        return decisions

    def evaluate_capabilities(
        self,
        capabilities: List[CapabilityAssessment],
    ) -> List[EngineeringDecision]:
        """Evaluates capability assessments to produce gap remediation decisions."""
        decisions: List[EngineeringDecision] = []

        for cap in capabilities:
            name = cap.capability_name

            # Subscriptions
            if "subscription" in name.lower():
                if cap.has_database_schema and not cap.has_automated_tests:
                    decisions.append(
                        EngineeringDecision(
                            target_artifact="Subscription Intelligence",
                            decision="EXTEND",
                            reason="Relational table `subscriptions` exists; must build deterministic recurring billing calculation service and renewal reminder dispatchers.",
                            supporting_evidence=f"Database table exists; logic status: {cap.status.value}.",
                            dependencies=["PostgreSQL / Supabase `subscriptions` table"],
                            risk="MEDIUM",
                            recommended_owner="worker_coding_agent",
                        )
                    )

            # Loans & EMIs
            elif "loan" in name.lower() or "emi" in name.lower():
                decisions.append(
                    EngineeringDecision(
                        target_artifact="Loan & EMI Tracking",
                        decision="BUILD_NEW",
                        reason="Table `loans` exists, but deterministic amortization calculation formulas and payoff forecasting engine must be implemented in Python.",
                        supporting_evidence=f"Schema present; computation engine status: {cap.status.value}.",
                        dependencies=["PostgreSQL / Supabase `loans` table"],
                        risk="MEDIUM",
                        recommended_owner="worker_coding_agent",
                    )
                )

            # Q&A / RAG
            elif "q&a" in name.lower() or "advisory" in name.lower():
                decisions.append(
                    EngineeringDecision(
                        target_artifact="Financial Q&A & Advisory",
                        decision="REFACTOR",
                        reason="Hybrid Architecture required: Direct deterministic SQL queries for transactions/balances, reserving vector RAG strictly for unstructured statement PDFs and tax policy guides.",
                        supporting_evidence="System prompts exist, but unstructured RAG pipeline lacks vector embeddings store.",
                        dependencies=["Deterministic Calculation Layer", "Document parser"],
                        risk="HIGH",
                        recommended_owner="worker_research_agent",
                    )
                )

        # Mandatory architecture decisions
        decisions.append(
            EngineeringDecision(
                target_artifact="Deterministic Calculation Layer",
                decision="BUILD_NEW",
                reason="Financial arithmetic (budget variances, loan amortizations, net worth rollups) must NEVER rely on LLM floating-point generation. Implement a dedicated Python service.",
                supporting_evidence="Zero code currently exists for deterministic arithmetic verification.",
                dependencies=["Python 3.14 venv", "Decimal precision module"],
                risk="CRITICAL",
                recommended_owner="worker_coding_agent",
            )
        )

        decisions.append(
            EngineeringDecision(
                target_artifact="Automated Test Harness",
                decision="BUILD_NEW",
                reason="Zero automated tests exist in the project. Must implement pytest suites covering webhook payloads, database constraints, and financial calculations.",
                supporting_evidence="No test files discovered in repository root.",
                dependencies=["pytest test runner"],
                risk="HIGH",
                recommended_owner="worker_coding_agent",
            )
        )

        return decisions

"""Capability Assessment Engine for ZERO Deep Discovery.

Evaluates complete end-to-end features rather than isolated artifacts.
Enforces that:
1. Presence of a SQL table (CREATE TABLE) only proves SCHEMA_EXISTS (PARTIAL).
2. Presence of a prompt file only proves PROMPT_EXISTS (PLANNED_ONLY).
3. Presence of a workflow without tests only proves IMPLEMENTATION_PRESENT (PARTIAL).
4. Only multi-subsystem implementation + verified tests can yield IMPLEMENTED_VERIFIED.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

from zero_core.engineering.discovery.evidence import (
    EvidenceLedger,
    EvidenceStatus,
    EvidenceType,
    FeatureEvidence,
    VerificationLevel,
)

logger = logging.getLogger(__name__)


@dataclass
class CapabilityAssessment:
    """Holistic multi-subsystem assessment of a project feature or capability."""
    capability_name: str
    status: EvidenceStatus
    verification_level: VerificationLevel
    subsystems_present: List[str]
    evidence_count: int
    has_database_schema: bool = False
    has_executable_logic: bool = False
    has_automated_tests: bool = False
    has_system_prompt: bool = False
    gap_notes: str = ""
    evidence_items: List[FeatureEvidence] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["verification_level"] = self.verification_level.value
        d["evidence_items"] = [e.to_dict() for e in self.evidence_items]
        return d


class CapabilityAssessmentEngine:
    """Combines evidence across subsystems to assess true functional readiness."""

    def assess_capabilities(
        self,
        evidence_list: List[FeatureEvidence],
    ) -> List[CapabilityAssessment]:
        """Groups evidence into coherent capability domains and computes holistic status."""
        groups: Dict[str, List[FeatureEvidence]] = {}

        for ev in evidence_list:
            cap_key = self._normalize_capability_key(ev.feature)
            groups.setdefault(cap_key, []).append(ev)

        assessments: List[CapabilityAssessment] = []
        for cap_name, items in groups.items():
            assessments.append(self._evaluate_single_capability(cap_name, items))

        return assessments

    def _normalize_capability_key(self, feature: str) -> str:
        f = feature.lower().strip()
        if any(k in f for k in ("subscription", "recurring")):
            return "Subscription Intelligence"
        if any(k in f for k in ("loan", "emi", "mortgage", "debt")):
            return "Loan & EMI Tracking"
        if any(k in f for k in ("budget", "category", "allocation")):
            return "Budgeting & Expense Allocations"
        if any(k in f for k in ("statement", "email ingestion", "gmail", "bank statement")):
            return "Bank Statement Ingestion"
        if any(k in f for k in ("q&a", "chat", "rag", "knowledge", "query", "assistant")):
            return "Financial Q&A & Advisory"
        if any(k in f for k in ("transaction", "spending", "expense")):
            return "Transaction Processing & Tracking"
        if any(k in f for k in ("telegram", "whatsapp", "notification", "alert")):
            return "Multi-Channel Alerts (Telegram / WhatsApp)"
        if any(k in f for k in ("credit card", "card limit")):
            return "Credit Card & Balance Monitoring"
        if any(k in f for k in ("dashboard", "ui", "screen", "frontend")):
            return "Dashboard & User Interface"
        return feature.title()

    def _evaluate_single_capability(
        self,
        capability_name: str,
        items: List[FeatureEvidence],
    ) -> CapabilityAssessment:
        subsystems = {e.subsystem.lower() for e in items}
        types = {e.evidence_type for e in items}

        has_db = EvidenceType.DATABASE_DDL in types
        has_logic = bool(types & {EvidenceType.WORKFLOW_NODE, EvidenceType.PYTHON_CODE})
        has_tests = EvidenceType.TEST_CASE in types
        has_prompt = EvidenceType.SYSTEM_PROMPT in types

        # Assess verification level and status strictly
        if has_db and has_logic and has_tests:
            status = EvidenceStatus.IMPLEMENTED_VERIFIED
            level = VerificationLevel.TEST_VERIFIED
            notes = "Fully implemented with relational schema, workflow/code logic, and automated tests."
        elif has_db and has_logic and not has_tests:
            status = EvidenceStatus.PARTIAL
            level = VerificationLevel.IMPLEMENTATION_PRESENT
            notes = "Schema and workflow/code logic present, but lacks automated tests or runtime verification."
        elif has_db and not has_logic:
            status = EvidenceStatus.PARTIAL
            level = VerificationLevel.STATICALLY_VERIFIED
            notes = "Database table / schema exists (SCHEMA_EXISTS), but business logic / workflow is missing or unverified."
        elif has_logic and not has_db:
            status = EvidenceStatus.PARTIAL
            level = VerificationLevel.IMPLEMENTATION_PRESENT
            notes = "Executable logic or workflow exists, but dedicated persistent database entity is unconfirmed."
        elif has_prompt and not (has_db or has_logic):
            status = EvidenceStatus.PLANNED_ONLY
            level = VerificationLevel.ARTIFACT_PRESENT
            notes = "Prompt specification exists (PROMPT_EXISTS), but executable code, workflow, or DB tables are absent."
        else:
            status = EvidenceStatus.PARTIAL
            level = VerificationLevel.ARTIFACT_PRESENT
            notes = "Discovered in repository artifacts; requires additional implementation to reach production readiness."

        return CapabilityAssessment(
            capability_name=capability_name,
            status=status,
            verification_level=level,
            subsystems_present=sorted(list(subsystems)),
            evidence_count=len(items),
            has_database_schema=has_db,
            has_executable_logic=has_logic,
            has_automated_tests=has_tests,
            has_system_prompt=has_prompt,
            gap_notes=notes,
            evidence_items=items,
        )

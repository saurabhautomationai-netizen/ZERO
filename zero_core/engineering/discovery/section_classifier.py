"""Section Intent Classifier for ZERO Continuation Planning & Deep Discovery.

Classifies requested report headings into discrete semantic categories:
- FACTUAL_DISCOVERY
- FEATURE_ASSESSMENT
- ARCHITECTURAL_DECISION
- DECISION_MATRIX
- MIGRATION_PLAN
- IMPLEMENTATION_PLAN
- TEST_PLAN
- SECURITY_PLAN
- RISK_ANALYSIS
- HITL_GATE

Prevents semantic mismatches (e.g. migration sections receiving UI/UX evidence,
or RAG decisions receiving generic repository file listings).
"""

from __future__ import annotations

import enum
import re
from typing import Dict, List, Tuple


class SectionCategory(str, enum.Enum):
    """Semantic category of a requested output section."""
    FACTUAL_DISCOVERY = "FACTUAL_DISCOVERY"
    FEATURE_ASSESSMENT = "FEATURE_ASSESSMENT"
    ARCHITECTURAL_DECISION = "ARCHITECTURAL_DECISION"
    DECISION_MATRIX = "DECISION_MATRIX"
    MIGRATION_PLAN = "MIGRATION_PLAN"
    IMPLEMENTATION_PLAN = "IMPLEMENTATION_PLAN"
    TEST_PLAN = "TEST_PLAN"
    SECURITY_PLAN = "SECURITY_PLAN"
    RISK_ANALYSIS = "RISK_ANALYSIS"
    HITL_GATE = "HITL_GATE"
    GENERIC = "GENERIC"


class SectionIntentClassifier:
    """Classifies section titles into semantic categories."""

    def classify(self, title: str) -> SectionCategory:
        t = title.lower().strip()

        # HITL Gate
        if any(k in t for k in ("hitl", "gate", "stop", "approval")):
            return SectionCategory.HITL_GATE

        # Decision Matrix
        if any(k in t for k in ("reuse", "extend", "fix", "build", "matrix", "workflows to keep", "workflows to modify", "workflows to split", "workflows to merge", "workflows to retire")):
            return SectionCategory.DECISION_MATRIX

        # Migration Plan (database, n8n refactor, schema evolution)
        if any(k in t for k in ("migration", "database completion", "n8n refactoring plan", "refactoring plan")):
            return SectionCategory.MIGRATION_PLAN

        # Architectural Decision
        if any(k in t for k in ("target architecture", "architecture diagram", "responsibility boundary", "finance agent architecture", "deterministic calculation layer", "rag decision", "system design", "boundary")):
            return SectionCategory.ARCHITECTURAL_DECISION

        # Test Plan & Verification
        if any(k in t for k in ("testing strategy", "acceptance criteria", "definition of done", "test plan", "validation strategy")):
            return SectionCategory.TEST_PLAN

        # Security Architecture
        if any(k in t for k in ("security architecture", "secret", "rbac", "permissions", "security")):
            return SectionCategory.SECURITY_PLAN

        # Risk Analysis & Tech Debt
        if any(k in t for k in ("risks", "technical debt", "code smells", "risk analysis")):
            return SectionCategory.RISK_ANALYSIS

        # Implementation Plan & Sequencing
        if any(k in t for k in ("milestone", "implementation sequence", "tasks inside", "worker assignment", "department assignment", "roadmap", "sequence")):
            return SectionCategory.IMPLEMENTATION_PLAN

        # Feature Assessment (matrices, capabilities)
        if any(k in t for k in ("feature matrix", "subscription intelligence", "loan intelligence", "affordability", "forecasting", "q&a", "whatsapp", "dashboard/ui roadmap")):
            return SectionCategory.FEATURE_ASSESSMENT

        # Factual Discovery
        if any(k in t for k in ("factual discovery", "factual", "verified current state", "current state", "discovered repository state", "discovered state", "actual implemented features", "n8n architecture", "database", "channels", "triggers", "evidence", "inventory")):
            return SectionCategory.FACTUAL_DISCOVERY

        return SectionCategory.GENERIC

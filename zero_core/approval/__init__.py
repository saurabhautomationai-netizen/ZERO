"""Approval System package for ZERO (Milestone M6)."""

from zero_core.approval.engine import ApprovalPolicyEngine
from zero_core.approval.models import (
    ApprovalRequest,
    ApprovalStatus,
    RiskLevel,
)


def build_default_approval_engine() -> ApprovalPolicyEngine:
    """Factory returning default configured ApprovalPolicyEngine."""
    return ApprovalPolicyEngine()


__all__ = [
    "ApprovalPolicyEngine",
    "ApprovalRequest",
    "ApprovalStatus",
    "RiskLevel",
    "build_default_approval_engine",
]

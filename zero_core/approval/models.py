"""Data models for the ZERO Approval System (Milestone M6)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


class RiskLevel(str, Enum):
    LOW = "low"            # Read-only actions, safe inspections -> Auto-approved
    MEDIUM = "medium"      # State-mutating, non-destructive -> Logged & Auto/Prompt
    HIGH = "high"          # Destructive operations, financial writes -> Manual approval required


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass
class ApprovalRequest:
    """Represents an action submitted for security evaluation."""
    action_type: str
    target: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW
    status: ApprovalStatus = ApprovalStatus.PENDING
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    decision_reason: Optional[str] = None
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None

    def approve(self, approver: str = "user", reason: Optional[str] = None) -> None:
        self.status = ApprovalStatus.APPROVED
        self.decided_by = approver
        self.decision_reason = reason
        self.decided_at = datetime.now(timezone.utc).isoformat()

    def reject(self, approver: str = "user", reason: Optional[str] = None) -> None:
        self.status = ApprovalStatus.REJECTED
        self.decided_by = approver
        self.decision_reason = reason
        self.decided_at = datetime.now(timezone.utc).isoformat()

    @property
    def is_approved(self) -> bool:
        return self.status == ApprovalStatus.APPROVED

    @property
    def is_pending(self) -> bool:
        return self.status == ApprovalStatus.PENDING

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action_type": self.action_type,
            "target": self.target,
            "parameters": self.parameters,
            "risk_level": self.risk_level.value,
            "status": self.status.value,
            "created_at": self.created_at,
            "decision_reason": self.decision_reason,
            "decided_by": self.decided_by,
            "decided_at": self.decided_at,
        }

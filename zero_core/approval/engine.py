"""Policy and evaluation engine for ZERO Approval System."""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional
from zero_core.approval.models import ApprovalRequest, ApprovalStatus, RiskLevel


class ApprovalPolicyEngine:
    """Evaluates requested actions against security policies and manages approval workflows."""

    def __init__(self):
        self._requests: Dict[str, ApprovalRequest] = {}
        self._custom_evaluators: List[Callable[[str, str, Dict[str, Any], RiskLevel], Optional[RiskLevel]]] = []

    def register_risk_evaluator(
        self,
        evaluator: Callable[[str, str, Dict[str, Any], RiskLevel], Optional[RiskLevel]],
    ) -> None:
        """Registers a custom evaluator to dynamically determine risk level."""
        self._custom_evaluators.append(evaluator)

    def evaluate(
        self,
        action_type: str,
        target: str,
        parameters: Optional[Dict[str, Any]] = None,
        declared_risk: RiskLevel = RiskLevel.LOW,
    ) -> ApprovalRequest:
        """Evaluates an action and returns an ApprovalRequest."""
        params = parameters or {}
        effective_risk = declared_risk

        # Allow custom evaluators to escalate or refine risk level
        for evaluator in self._custom_evaluators:
            override = evaluator(action_type, target, params, effective_risk)
            if override is not None:
                effective_risk = override

        req = ApprovalRequest(
            action_type=action_type,
            target=target,
            parameters=params,
            risk_level=effective_risk,
        )

        # Auto-approve LOW risk actions immediately
        if effective_risk == RiskLevel.LOW:
            req.approve(approver="system:auto_policy", reason="Auto-approved low risk action")

        self._requests[req.request_id] = req
        return req

    def get_request(self, request_id: str) -> Optional[ApprovalRequest]:
        return self._requests.get(request_id)

    def get_pending_requests(self) -> List[ApprovalRequest]:
        return [r for r in self._requests.values() if r.is_pending]

    def approve(self, request_id: str, approver: str = "user", reason: Optional[str] = None) -> bool:
        req = self.get_request(request_id)
        if req is None or not req.is_pending:
            return False
        req.approve(approver=approver, reason=reason)
        return True

    def reject(self, request_id: str, approver: str = "user", reason: Optional[str] = None) -> bool:
        req = self.get_request(request_id)
        if req is None or not req.is_pending:
            return False
        req.reject(approver=approver, reason=reason)
        return True

    def is_action_permitted(self, request_id: str) -> bool:
        req = self.get_request(request_id)
        return req is not None and req.is_approved

from __future__ import annotations

from zero_core.approval import (
    ApprovalPolicyEngine,
    ApprovalRequest,
    ApprovalStatus,
    RiskLevel,
    build_default_approval_engine,
)


def test_approval_request_model():
    req = ApprovalRequest(
        action_type="file_mutation",
        target="delete_file",
        parameters={"path": "/tmp/test.txt"},
        risk_level=RiskLevel.HIGH,
    )
    assert req.status == ApprovalStatus.PENDING
    assert req.is_pending is True
    assert req.is_approved is False

    req.approve(approver="admin_user", reason="Confirmed safe")
    assert req.status == ApprovalStatus.APPROVED
    assert req.is_approved is True
    assert req.decided_by == "admin_user"
    assert req.decision_reason == "Confirmed safe"


def test_engine_auto_approves_low_risk():
    engine = ApprovalPolicyEngine()
    req = engine.evaluate(
        action_type="tool_execution",
        target="read_file",
        parameters={"file_path": "README.md"},
        declared_risk=RiskLevel.LOW,
    )
    assert req.is_approved is True
    assert engine.is_action_permitted(req.request_id) is True
    assert req.decided_by == "system:auto_policy"


def test_engine_holds_high_risk_for_approval():
    engine = ApprovalPolicyEngine()
    req = engine.evaluate(
        action_type="tool_execution",
        target="write_file",
        parameters={"file_path": "config.py"},
        declared_risk=RiskLevel.HIGH,
    )
    assert req.is_pending is True
    assert engine.is_action_permitted(req.request_id) is False

    pending = engine.get_pending_requests()
    assert len(pending) == 1
    assert pending[0].request_id == req.request_id

    # Approve
    success = engine.approve(req.request_id, approver="user", reason="Manual override")
    assert success is True
    assert engine.is_action_permitted(req.request_id) is True
    assert len(engine.get_pending_requests()) == 0


def test_engine_reject_request():
    engine = ApprovalPolicyEngine()
    req = engine.evaluate(
        action_type="tool_execution",
        target="drop_database",
        declared_risk=RiskLevel.HIGH,
    )
    success = engine.reject(req.request_id, approver="security_audit", reason="Forbidden operation")
    assert success is True
    assert req.status == ApprovalStatus.REJECTED
    assert engine.is_action_permitted(req.request_id) is False


def test_engine_custom_risk_evaluator_escalation():
    engine = ApprovalPolicyEngine()

    # Register an evaluator that escalates any delete action to HIGH risk
    def escalate_delete(action_type, target, params, current_risk):
        if "delete" in target.lower():
            return RiskLevel.HIGH
        return None

    engine.register_risk_evaluator(escalate_delete)

    req = engine.evaluate(
        action_type="tool_execution",
        target="delete_user_record",
        declared_risk=RiskLevel.LOW,  # Declared low, but evaluator should escalate to HIGH
    )
    assert req.risk_level == RiskLevel.HIGH
    assert req.is_pending is True
    assert engine.is_action_permitted(req.request_id) is False


def test_default_approval_engine_factory():
    engine = build_default_approval_engine()
    assert isinstance(engine, ApprovalPolicyEngine)

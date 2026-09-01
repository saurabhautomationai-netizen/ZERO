"""Unit tests for ZERO Autonomous Project Patrol Worker & HITL Approval System."""

import tempfile
from pathlib import Path
import pytest

from zero_core.approval.engine import ApprovalPolicyEngine
from zero_core.approval.models import RiskLevel
from zero_core.patrol import ProjectPatrolWorker, Finding
from zero_core.interfaces.web import handlers


def test_patrol_worker_discovery_and_audit():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        
        # Create a mock project
        mock_proj = tmp_path / "MockApp"
        mock_proj.mkdir()
        
        # 1. Add active .env without .gitignore
        (mock_proj / ".env").write_text("API_KEY=test_123456\n", encoding="utf-8")
        
        # 2. Add an oversized log file (>2MB)
        large_log = mock_proj / "debug.log"
        large_log.write_bytes(b"0" * (3 * 1024 * 1024))
        
        # 3. Add a valid python file
        (mock_proj / "main.py").write_text("print('hello')\n", encoding="utf-8")
        
        engine = ApprovalPolicyEngine()
        worker = ProjectPatrolWorker(projects_root=tmp_path, approval_engine=engine)
        
        # Test discovery
        projects = worker.discover_projects()
        assert len(projects) == 1
        assert projects[0].name == "MockApp"
        
        # Test sweep
        status = worker.run_patrol_sweep()
        assert status["projects_count"] == 1
        assert status["total_findings"] >= 2  # Missing gitignore + oversized log
        assert status["pending_approvals_count"] >= 2
        
        # Test HITL Approval
        pending = engine.get_pending_requests()
        assert len(pending) >= 2
        
        req = pending[0]
        assert req.is_pending is True
        assert req.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH)
        
        # Approve first request
        engine.approve(req.request_id, approver="test_user")
        assert req.is_approved is True


def test_handlers_patrol_and_approval_endpoints():
    status = handlers.handle_patrol_status()
    assert "is_running" in status
    assert "projects_count" in status
    
    approvals = handlers.handle_list_pending_approvals()
    assert "approvals" in approvals
    assert "count" in approvals

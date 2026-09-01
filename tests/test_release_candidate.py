"""Tests for Release Candidate Generation & Deployment Guard (Phase 7).

Verifies that ZERO generates formal, audit-ready Release Candidate Reports
while strictly preventing automatic production deployments or master merges
without explicit human authorization (Gate 8).
"""

import pytest
from pathlib import Path
from fastapi.testclient import TestClient
from zero_core.agents.loop_engineering import DEFAULT_LOOP_ENGINEERING_AGENT, LoopEngineeringAgent
from zero_core.engineering.manifest import ProjectManifest, PhaseEnum, ProjectStatus
from zero_core.engineering.multi_project import MultiProjectManager
from zero_core.engineering.store import EngineeringProjectStore
from zero_core.interfaces.web.app import app


def test_release_candidate_report_generation(tmp_path):
    store = EngineeringProjectStore(storage_dir=tmp_path / "projects")
    manager = MultiProjectManager(store=store)

    manifest = ProjectManifest(
        project_id="proj_hr_rc_test",
        project_name="HR Recruitment AI Assistant",
        project_type="EXISTING_PROJECT",
        repository_path=str(tmp_path / "repo"),
        description="Release candidate verification",
        current_phase=PhaseEnum.PHASE_17_DEPLOYMENT,
        testing_status="COMPLETED",
        security_status="COMPLETED",
    )
    manifest.review_history.append({"verdict": "PASS", "reviewer": "worker_chatgpt"})
    manifest.validation_history.append({"is_pass": True, "syntax_errors": []})
    store.save_project(manifest)

    report = manager.generate_release_candidate_report("proj_hr_rc_test", feature_name="AI Candidate Insights")
    
    # Assertions
    assert report["project_name"] == "HR Recruitment AI Assistant"
    assert report["feature"] == "AI Candidate Insights"
    assert report["release_candidate_version"] == "v1.1.0-rc1"
    assert report["auto_deploy_blocked"] is True
    assert report["deployment_readiness"] == "AWAITING_HUMAN_APPROVAL_GATE_8"
    assert "git restore" in report["rollback_instructions"]
    assert len(report["files_changed"]) > 0
    assert report["review_verdict"] == "PASS"


def test_release_candidate_api_endpoint(client=None):
    """Verifies REST API exposure of the Release Candidate Report."""
    tc = TestClient(app)
    manifest = DEFAULT_LOOP_ENGINEERING_AGENT.intake_project(idea="API RC Project")
    manifest.testing_status = "COMPLETED"
    DEFAULT_LOOP_ENGINEERING_AGENT.store.save_project(manifest)

    res = tc.get(f"/api/v1/engineering/projects/{manifest.project_id}/release-candidate")
    assert res.status_code == 200
    data = res.json()
    assert data["project_id"] == manifest.project_id
    assert data["auto_deploy_blocked"] is True
    assert "release_candidate_version" in data

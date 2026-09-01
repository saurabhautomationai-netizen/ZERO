"""Tests for Engineering Cockpit APIs, Handlers, and Secret Redaction."""

import pytest
from fastapi.testclient import TestClient
from zero_core.interfaces.web.app import app
from zero_core.agents.loop_engineering import DEFAULT_LOOP_ENGINEERING_AGENT
from zero_core.engineering.manifest import PhaseEnum, ProjectManifest


@pytest.fixture
def client():
    return TestClient(app)


def test_cockpit_overview_and_worker_health_apis(client):
    res = client.get("/api/v1/engineering/cockpit/overview")
    assert res.status_code == 200
    data = res.json()

    assert "total_projects" in data
    assert "active_projects" in data
    assert "waiting_hitl" in data
    assert "blocked" in data
    assert "completed" in data
    assert "workers" in data
    assert isinstance(data["workers"], list)


def test_engineering_workers_and_approvals_apis(client):
    res_w = client.get("/api/v1/engineering/workers")
    assert res_w.status_code == 200
    workers = res_w.json()
    assert "workers" in workers
    assert len(workers["workers"]) > 0

    res_a = client.get("/api/v1/engineering/approvals")
    assert res_a.status_code == 200
    approvals = res_a.json()
    assert "pending_approvals" in approvals


def test_project_tasks_activity_and_briefing_apis(client):
    # Ensure at least one project exists
    manifest = DEFAULT_LOOP_ENGINEERING_AGENT.intake_project(idea="Cockpit Test Project")
    manifest.current_phase = PhaseEnum.PHASE_1_DISCOVERY
    DEFAULT_LOOP_ENGINEERING_AGENT.store.save_project(manifest)

    # 1. Project tasks API
    res_tasks = client.get(f"/api/v1/engineering/projects/{manifest.project_id}/tasks")
    assert res_tasks.status_code == 200
    tasks_data = res_tasks.json()
    assert "tasks" in tasks_data

    # 2. Activity API
    res_act = client.get(f"/api/v1/engineering/projects/{manifest.project_id}/activity")
    assert res_act.status_code == 200
    act_data = res_act.json()
    assert "events" in act_data

    # 3. Owner briefing API
    res_brief = client.get(f"/api/v1/engineering/projects/{manifest.project_id}/owner-briefing")
    assert res_brief.status_code == 200
    brief_data = res_brief.json()
    assert brief_data["project_name"] == manifest.project_name
    assert "status" in brief_data

    # 4. Priority API
    res_prio = client.post(f"/api/v1/engineering/projects/{manifest.project_id}/priority", json={"priority": "HIGH"})
    assert res_prio.status_code == 200
    assert res_prio.json()["priority"] == "HIGH"

    # 5. Pause & Resume APIs
    res_pause = client.post(f"/api/v1/engineering/projects/{manifest.project_id}/pause")
    assert res_pause.status_code == 200
    assert res_pause.json()["status"] == "PAUSED"

    res_resume = client.post(f"/api/v1/engineering/projects/{manifest.project_id}/resume")
    assert res_resume.status_code == 200


def test_cockpit_secret_redaction(client):
    """Verifies that sensitive credentials are never displayed in Cockpit APIs."""
    raw_secret = "sk-proj-supersecretkey123456789"
    manifest = DEFAULT_LOOP_ENGINEERING_AGENT.intake_project(idea="Secret Redaction Project")
    manifest.description = f"Project with confidential key: {raw_secret}"
    DEFAULT_LOOP_ENGINEERING_AGENT.store.save_project(manifest)

    res = client.get(f"/api/v1/engineering/projects/{manifest.project_id}")
    assert res.status_code == 200
    content = res.text
    # Secret must never be leaked unmasked
    assert raw_secret not in content

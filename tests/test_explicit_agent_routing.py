"""Comprehensive regression suite for Explicit Agent Routing & @Mention Overrides.

Tests:
1. TEST 1: @Loop Engineering Agent -> Loop Engineering Agent
2. TEST 2: @Loop Engineering Agent with 'n8n workflows' -> Loop Engineering Agent (overrides Automation Agent)
3. TEST 3: @Automation Agent with 'Finance Tracker' -> Automation Agent
4. TEST 4: @Git Agent with 'Continue development' -> Git Agent (overrides Loop Engineering)
5. TEST 5: No explicit target + 'Continue development of my Personal Finance Tracker' -> Loop Engineering Agent
6. TEST 6: No explicit target + 'Show connected n8n workflows' -> Automation Agent
7. TEST 7: @Nonexistent Agent -> AGENT_NOT_FOUND error (no silent fallback)
8. Structured agent_slug parameter in TaskRequest -> Deterministic direct dispatch
9. Invalid structured agent_slug in TaskRequest -> AGENT_NOT_FOUND error
10. Various mention formats (@Slug, @Name, @Name:, newline)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from zero_core.interfaces.web.app import app
from zero_core.interfaces.web.handlers import build_orchestrator, handle_task


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def orchestrator():
    return build_orchestrator()


def test_test1_loop_engineering_explicit_mention(orchestrator, client):
    """TEST 1: @Loop Engineering Agent explicitly resumes Personal Finance Tracker."""
    prompt = "@Loop Engineering Agent\nResume my Personal Finance Tracker project."
    decision = orchestrator.run(prompt)
    assert decision.selected is not None
    assert decision.selected.slug == "native/loop-engineering-agent"
    assert decision.selected.name == "Loop Engineering Agent"

    res = client.post("/api/task", json={"task": prompt})
    assert res.status_code == 200
    assert res.json()["selected"]["slug"] == "native/loop-engineering-agent"


def test_test2_loop_engineering_overrides_automation_keywords(orchestrator, client):
    """TEST 2: @Loop Engineering Agent with 'n8n workflows' must route to Loop Engineering, NOT Automation Agent."""
    prompt = "@Loop Engineering Agent\nInspect my n8n workflows."
    decision = orchestrator.run(prompt)
    assert decision.selected is not None
    assert decision.selected.slug == "native/loop-engineering-agent"
    assert decision.selected.name == "Loop Engineering Agent"
    assert decision.selected.slug != "native/automation-agent"

    res = client.post("/api/task", json={"task": prompt})
    assert res.status_code == 200
    assert res.json()["selected"]["slug"] == "native/loop-engineering-agent"


def test_test3_automation_agent_explicit_mention(orchestrator, client):
    """TEST 3: @Automation Agent explicitly inspects Finance Tracker n8n workflows."""
    prompt = "@Automation Agent\nInspect my Finance Tracker n8n workflows."
    decision = orchestrator.run(prompt)
    assert decision.selected is not None
    assert decision.selected.slug == "native/automation-agent"
    assert decision.selected.name == "Automation Agent"

    res = client.post("/api/task", json={"task": prompt})
    assert res.status_code == 200
    assert res.json()["selected"]["slug"] == "native/automation-agent"


def test_test4_git_agent_overrides_lifecycle_keywords(orchestrator, client):
    """TEST 4: @Git Agent with 'Continue development' must route to Git Agent, NOT Loop Engineering."""
    prompt = "@Git Agent\nContinue development of my repository."
    decision = orchestrator.run(prompt)
    assert decision.selected is not None
    assert decision.selected.slug == "native/git-agent"
    assert decision.selected.name == "Git Agent"
    assert decision.selected.slug != "native/loop-engineering-agent"

    res = client.post("/api/task", json={"task": prompt})
    assert res.status_code == 200
    assert res.json()["selected"]["slug"] == "native/git-agent"


def test_test5_automatic_lifecycle_routing_without_mention(orchestrator, client):
    """TEST 5: No explicit target: 'Continue development of my Personal Finance Tracker.' -> Loop Engineering Agent."""
    prompt = "Continue development of my Personal Finance Tracker."
    decision = orchestrator.run(prompt)
    assert decision.selected is not None
    assert decision.selected.slug == "native/loop-engineering-agent"
    assert decision.selected.name == "Loop Engineering Agent"

    res = client.post("/api/task", json={"task": prompt})
    assert res.status_code == 200
    assert res.json()["selected"]["slug"] == "native/loop-engineering-agent"


def test_test6_automatic_domain_routing_without_mention(orchestrator, client):
    """TEST 6: No explicit target: 'Show connected n8n workflows.' -> Automation Agent."""
    prompt = "Show connected n8n workflows."
    decision = orchestrator.run(prompt)
    assert decision.selected is not None
    assert decision.selected.slug == "native/automation-agent"
    assert decision.selected.name == "Automation Agent"

    res = client.post("/api/task", json={"task": prompt})
    assert res.status_code == 200
    assert res.json()["selected"]["slug"] == "native/automation-agent"


def test_test7_nonexistent_agent_returns_agent_not_found(orchestrator, client):
    """TEST 7: @Nonexistent Agent -> AGENT_NOT_FOUND error without silent fallback."""
    prompt = "@Nonexistent Agent\nDo something."
    decision = orchestrator.run(prompt)
    assert decision.selected is None
    assert decision.error == "AGENT_NOT_FOUND"
    assert decision.target_requested == "Nonexistent Agent"
    assert len(decision.alternatives) > 0  # close match suggestions provided

    # Execute orchestrator
    exec_res = orchestrator.execute(prompt)
    assert exec_res.spec is None
    assert "AGENT_NOT_FOUND" in exec_res.answer
    assert "@Nonexistent Agent" in exec_res.answer

    # Web handler test
    res = client.post("/api/task", json={"task": prompt})
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "AGENT_NOT_FOUND"
    assert data.get("selected") is None
    assert "AGENT_NOT_FOUND" in data.get("answer", "")


def test_structured_agent_slug_in_task_request(client):
    """TaskRequest with explicit agent_slug parameter bypasses competition directly."""
    res = client.post("/api/task", json={
        "task": "Perform audit on n8n workflows",
        "agent_slug": "native/loop-engineering-agent",
    })
    assert res.status_code == 200
    data = res.json()
    assert data["selected"]["slug"] == "native/loop-engineering-agent"


def test_structured_invalid_agent_slug_returns_agent_not_found(client):
    """TaskRequest with invalid agent_slug returns AGENT_NOT_FOUND."""
    res = client.post("/api/task", json={
        "task": "Perform task",
        "agent_slug": "native/bogus-ghost-agent",
    })
    assert res.status_code == 200
    data = res.json()
    assert data.get("status") == "AGENT_NOT_FOUND"
    assert data.get("selected") is None


def test_mention_variations(orchestrator):
    """Validates mention parsing across colon, short slug, full slug, and lowercase."""
    variations = [
        ("@Loop Engineering Agent: Run diagnostics", "native/loop-engineering-agent"),
        ("@loop-engineering-agent\nRun diagnostics", "native/loop-engineering-agent"),
        ("@native/loop-engineering-agent Run diagnostics", "native/loop-engineering-agent"),
        ("@git-agent: inspect status", "native/git-agent"),
        ("@Git Agent inspect status", "native/git-agent"),
    ]
    for prompt, expected_slug in variations:
        decision = orchestrator.run(prompt)
        assert decision.selected is not None, f"Failed on variation: {prompt}"
        assert decision.selected.slug == expected_slug, f"Failed on {prompt}: got {decision.selected.slug}"

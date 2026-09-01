"""Regression test suite for Command Center Runtime Bug & Routing Hardening.

Covers:
1. JSON Parse Failure & Provider Error Handling:
   - Worker returns 'Internal Server Error' or 'Internal Service unavailable' instead of WorkerResult JSON.
   - Proves ZERO produces structured FAILED result, avoids uncaught exceptions, and logs structured events.
2. Long Multiline Prompt Transport Integrity:
   - Tests FastAPI endpoint with multi-line markdown, quotes, apostrophes, colons, bullets, and special chars.
   - Confirms zero prompt truncation, zero corruption, and valid JSON response.
3. Intent-Aware Routing:
   - 'Check git status of ZERO' -> Git Agent.
   - 'How much did I spend this month?' -> Finance Agent.
   - 'Continue my HR Recruitment project' -> Loop Engineering Agent.
   - Long Personal Finance Tracker continuation instructions -> Loop Engineering Agent (not Git or Finance Agent).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from zero_core.engineering.workers.external import ChatGPTWorker
from zero_core.engineering.workers.transport import ManualTransportManager
from zero_core.interfaces.web.app import app
from zero_core.interfaces.web.handlers import build_orchestrator, handle_task
from zero_core.observability import DEFAULT_LOGGER


@pytest.fixture
def client():
    return TestClient(app)


# -----------------------------------------------------------------------------
# 1. JSON PARSE FAILURE & PROVIDER ERROR HANDLING
# -----------------------------------------------------------------------------

def test_manual_transport_rejects_internal_server_error_safely():
    """Confirms 'Internal Server Error' is handled gracefully as a structured failure."""
    raw_error_text = "Internal Server Error: 500 downstream service failure"
    result = ManualTransportManager.import_result(
        raw_text=raw_error_text,
        task_id="task_debug_001",
        worker_id="worker_antigravity",
    )

    assert result.status == "FAILED"
    assert result.requires_human is True
    assert "Provider returned error response" in result.summary
    assert result.execution_metadata.get("error_category") == "WORKER_RESPONSE_PARSE_FAILED"
    assert result.execution_metadata.get("stage") == "Response Parsing"
    assert "WorkerResult JSON" in result.execution_metadata.get("expected")

    # Verify structured event was logged safely
    events = [e for e in DEFAULT_LOGGER.get_events() if e["event_type"] == "worker_response_parse_failed"]
    assert len(events) > 0
    assert events[-1]["metadata"]["worker_id"] == "worker_antigravity"


def test_chatgpt_worker_normalizes_provider_service_unavailable_safely():
    """Confirms ChatGPTWorker returns structured failure on provider 503 error."""
    worker = ChatGPTWorker()
    raw_provider_error = "Internal Service unavailable: Cloudflare gateway timeout (504)"

    result = worker._normalize_response(
        raw_text=raw_provider_error,
        task_id="task_debug_002",
        exec_id="exec_999",
        criteria=["Acceptance criteria 1"],
    )

    assert result.status == "FAILED"
    assert result.requires_human is True
    assert "ChatGPT API returned provider error" in result.summary
    assert result.execution_metadata.get("error_category") == "WORKER_RESPONSE_PARSE_FAILED"


def test_handle_task_never_crashes_on_failing_executor(monkeypatch):
    """Confirms handle_task catches internal executor errors and returns valid JSON response."""
    from zero_core.orchestrator import Orchestrator
    
    def mock_broken_execute(self, *args, **kwargs):
        raise RuntimeError("Simulated internal subsystem crash: DB connection dropped")

    monkeypatch.setattr(Orchestrator, "execute", mock_broken_execute)

    res = handle_task("Arbitrary engineering instruction")
    assert isinstance(res, dict)
    assert res.get("status") == "ERROR"
    assert "Simulated internal subsystem crash" in res.get("answer", "")
    assert res.get("selected", {}).get("name") == "ZERO Core"


# -----------------------------------------------------------------------------
# 2. LONG PROMPT INTEGRITY & FASTAPI ENDPOINT TRANSPORT
# -----------------------------------------------------------------------------

def test_long_multiline_prompt_payload_integrity(client):
    """Sends a complex multiline prompt with markdown, quotes, bullets, and special chars via /api/task."""
    long_engineering_prompt = (
        "# SYSTEM DIRECTIVE: Personal Finance Tracker V2 Continuation\n"
        "ZERO, continue development of my EXISTING Personal Finance Tracker V2:\n"
        "- Repository Path: `F:\\AI Automation\\Projects\\Smart Finance AI Tracker`\n"
        "- Action: \"Perform read-only discovery, recover project state, identify remaining work\"\n"
        "- Git State: Current branch is 'main'; working tree status is 'clean'\n"
        "- Safety Constraint: 'Do not modify codebase or execute destructive migrations'\n"
        "- Checkpoint Directive: Recover last valid snapshot and stop at continuation HITL gate.\n"
        "\n"
        "Please provide an executive readout with next actionable steps."
    )

    response = client.post("/api/task", json={"task": long_engineering_prompt})
    assert response.status_code == 200
    data = response.json()

    # Assert prompt payload arrived 100% intact without truncation
    assert data["task"] == long_engineering_prompt
    assert len(data["task"]) == len(long_engineering_prompt)

    # Assert correct routing to Loop Engineering Agent
    assert data["selected"]["slug"] == "native/loop-engineering-agent"
    assert data["selected"]["name"] == "Loop Engineering Agent"
    assert "Project State Recovered" in data["answer"] or "Halted at Continuation HITL Gate" in data["answer"]


# -----------------------------------------------------------------------------
# 3. INTENT-AWARE ROUTING ACCURACY
# -----------------------------------------------------------------------------

def test_routing_git_status():
    """'Check git status of ZERO' must route to Git Agent, not Project Builder."""
    orch = build_orchestrator()
    decision = orch.run("Check git status of ZERO.")
    assert decision.selected is not None
    assert decision.selected.slug == "native/git-agent"
    assert decision.selected.name == "Git Agent"


def test_routing_finance_spending_query():
    """'How much did I spend this month?' must route to Finance Agent, not FinOps or Loop Engineering."""
    orch = build_orchestrator()
    decision = orch.run("How much did I spend this month?")
    assert decision.selected is not None
    assert decision.selected.slug == "native/finance-agent"
    assert decision.selected.name == "Finance Agent"


def test_routing_hr_project_continuation():
    """'Continue my HR Recruitment project' must route to Loop Engineering Agent."""
    orch = build_orchestrator()
    decision = orch.run("Continue my HR Recruitment project")
    assert decision.selected is not None
    assert decision.selected.slug == "native/loop-engineering-agent"
    assert decision.selected.name == "Loop Engineering Agent"


def test_routing_personal_finance_tracker_long_engineering_prompt():
    """Realistic long engineering prompt with Finance Tracker in title must route to Loop Engineering."""
    orch = build_orchestrator()
    prompt = (
        "ZERO, continue development of my EXISTING Personal Finance Tracker V2. "
        "Perform read-only discovery, recover project state, identify remaining work, "
        "and stop at the continuation HITL gate."
    )
    decision = orch.run(prompt)
    assert decision.selected is not None
    assert decision.selected.slug == "native/loop-engineering-agent"
    assert decision.selected.name == "Loop Engineering Agent"
    # Ensure it did NOT route to Git Agent or Finance Agent
    assert decision.selected.slug != "native/git-agent"
    assert decision.selected.slug != "native/finance-agent"


def test_read_only_discovery_execution_stops_at_hitl_gate():
    """Verifies that read-only discovery executes safely and halts at the continuation gate."""
    orch = build_orchestrator()
    prompt = (
        "ZERO, inspect the existing Personal Finance Tracker project in READ-ONLY mode, "
        "recover its last checkpoint, identify remaining work, and stop at the continuation HITL gate."
    )
    outcome = orch.execute(prompt)
    assert outcome.needs_llm is False
    assert outcome.answer is not None
    assert "Halted at Continuation HITL Gate" in outcome.answer
    assert "GATE 1 (Feature Scope Approval)" in outcome.answer

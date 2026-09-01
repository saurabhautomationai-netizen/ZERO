"""Unit and integration tests for ChatGPTWorker."""

import json
from pathlib import Path
import pytest

from zero_core.engineering.context_builder import DEFAULT_CONTEXT_BUILDER
from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.workers.base import (
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
)
from zero_core.engineering.workers.external import ChatGPTWorker


class FakeLLMClient:
    """Deterministic mock client returning pre-canned responses for test verification."""

    def __init__(self, canned_response: str):
        self.canned_response = canned_response
        self.last_system = ""
        self.last_user = ""

    def generate(self, system_prompt: str, user_prompt: str, model=None) -> str:
        self.last_system = system_prompt
        self.last_user = user_prompt
        return self.canned_response


def test_chatgpt_worker_capabilities():
    worker = ChatGPTWorker(api_key="fake-key")
    assert worker.worker_id == "worker_chatgpt"
    assert worker.has_capability(WorkerCapability.ARCHITECTURE_REVIEW)
    assert worker.has_capability(WorkerCapability.SRS)
    assert worker.has_capability(WorkerCapability.PLANNING)
    assert worker.has_capability(WorkerCapability.CODE_REVIEW)
    assert worker.has_capability(WorkerCapability.RESEARCH)
    assert worker.health_check() == WorkerStatus.AVAILABLE


def test_chatgpt_worker_not_configured(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    worker = ChatGPTWorker(api_key="")
    assert worker.health_check() == WorkerStatus.NOT_CONFIGURED

    context = ProjectContextPackage(
        task_id="t_cg_unconf",
        project_id="p_unconf",
        project_name="Unconfigured Project",
        current_phase="PHASE_2_SRS",
        task_title="Review SRS",
        task_description="Review system requirements",
    )
    result = worker.run_task(context)
    assert result.status == "NEEDS_REVIEW"
    assert result.requires_human is True
    assert result.execution_metadata["transport"] == "MANUAL_TRANSPORT"
    assert "OpenAI API not configured" in result.summary


def test_chatgpt_worker_structured_task_success(tmp_path):
    canned = json.dumps({
        "summary": "Architecture assessment complete. Clean separation of concerns.",
        "status": "SUCCESS",
        "analysis": "Layered domain models are robust.",
        "decisions": [{"title": "ADR-01", "decision": "Adopt PostgreSQL", "rationale": "ACID compliance"}],
        "acceptance_criteria_results": {"Domain separation enforced": True},
        "recommended_next_action": "Proceed to database schema design",
    })
    mock_client = FakeLLMClient(canned)
    worker = ChatGPTWorker(api_key="fake-key", llm_client=mock_client)
    worker.artifacts_dir = tmp_path

    context = ProjectContextPackage(
        task_id="t_cg_01",
        project_id="p_chatgpt",
        project_name="Recruitment Platform",
        current_phase="PHASE_3_ARCHITECTURE",
        task_title="Assess Architecture",
        task_description="Evaluate domain structure",
        acceptance_criteria=["Domain separation enforced"],
    )
    result = worker.run_task(context)
    assert isinstance(result, WorkerResult)
    assert result.is_success
    assert "Clean separation of concerns" in result.summary
    assert len(result.decisions) == 1
    assert result.acceptance_criteria_results["Domain separation enforced"] is True


def test_chatgpt_worker_review_pass(tmp_path):
    canned = json.dumps({
        "verdict": "PASS",
        "score": 95,
        "summary": "Implementation satisfies all acceptance criteria with zero regressions.",
        "findings": [],
        "correction_plan": [],
        "acceptance_criteria_results": {"Tests pass": True},
    })
    mock_client = FakeLLMClient(canned)
    worker = ChatGPTWorker(api_key="fake-key", llm_client=mock_client)
    worker.artifacts_dir = tmp_path

    context = ProjectContextPackage(
        task_id="t_rev_pass",
        project_id="p_rev",
        project_name="Trading Engine",
        current_phase="PHASE_13_TESTING",
        task_title="Review SMC Signal Generator",
        task_description="Validate SMC logic",
        acceptance_criteria=["Tests pass"],
    )
    result = worker.review(context, diff="+ def smc_signal(): return True", test_evidence="pytest passed")
    assert result.is_success
    assert result.execution_metadata["verdict"] == "PASS"
    assert result.execution_metadata["score"] == 95


def test_chatgpt_worker_review_needs_correction(tmp_path):
    canned = json.dumps({
        "verdict": "NEEDS_CORRECTION",
        "score": 65,
        "summary": "Missing error handling for rate limits.",
        "findings": ["Rate limit handling omitted on line 42"],
        "correction_plan": ["Wrap API call in try/except HTTPError"],
        "acceptance_criteria_results": {"Error handling complete": False},
    })
    mock_client = FakeLLMClient(canned)
    worker = ChatGPTWorker(api_key="fake-key", llm_client=mock_client)
    worker.artifacts_dir = tmp_path

    context = ProjectContextPackage(
        task_id="t_rev_corr",
        project_id="p_rev",
        project_name="Trading Engine",
        current_phase="PHASE_13_TESTING",
        task_title="Review Gateway",
        task_description="Validate Gateway",
        acceptance_criteria=["Error handling complete"],
    )
    result = worker.review(context, diff="+ call_api()", test_evidence="Tests passed partially")
    assert result.status == "NEEDS_REVIEW"
    assert result.execution_metadata["verdict"] == "NEEDS_CORRECTION"
    assert len(result.execution_metadata["correction_plan"]) == 1


def test_chatgpt_worker_uses_sanitized_context(tmp_path):
    repo = tmp_path / "secret_repo"
    repo.mkdir()
    (repo / ".env").write_text("OPENAI_API_KEY=sk-proj-actualsecret99999\n", encoding="utf-8")
    (repo / "db.py").write_text("DB_URL = 'postgresql://admin:super_secret_pwd@localhost:5432/main'\n", encoding="utf-8")

    manifest = ProjectManifest(
        project_id="p_sec_cg",
        project_name="Secured Project",
        description="Verify sanitization before ChatGPT dispatch",
        repository_path=str(repo),
    )
    task = TaskItem(
        task_id="t_sec_01",
        milestone_id="m1",
        title="Architecture Review",
        description="Review database connection layer",
    )

    context = DEFAULT_CONTEXT_BUILDER.build_context(
        manifest, task, worker=ChatGPTWorker(api_key="key"), target_files=["db.py"]
    )
    mock_client = FakeLLMClient(json.dumps({"status": "SUCCESS", "summary": "Review complete"}))
    worker = ChatGPTWorker(api_key="fake-key", llm_client=mock_client)
    worker.artifacts_dir = tmp_path

    result = worker.run_task(context)
    assert result.is_success

    # Verify prompt sent to mock client has NO raw secrets
    assert "super_secret_pwd" not in mock_client.last_user
    assert "sk-proj-actualsecret99999" not in mock_client.last_user
    assert "[REDACTED" in mock_client.last_user

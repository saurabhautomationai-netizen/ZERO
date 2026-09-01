"""Unit and integration tests for AntigravityWorker."""

import json
from pathlib import Path
import pytest

from zero_core.engineering.workers.base import (
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
)
from zero_core.engineering.workers.external import AntigravityWorker


def test_antigravity_worker_capabilities():
    worker = AntigravityWorker(cli_path="agy")
    assert worker.worker_id == "worker_antigravity"
    assert worker.has_capability(WorkerCapability.CODE_GENERATION)
    assert worker.has_capability(WorkerCapability.CODE_REFACTOR)
    assert worker.has_capability(WorkerCapability.TESTING)
    assert worker.has_capability(WorkerCapability.DOCUMENTATION)


def test_antigravity_worker_not_configured():
    # Pass nonexistent path
    worker = AntigravityWorker(cli_path="/nonexistent/path/agy.exe")
    assert worker.health_check() == WorkerStatus.NOT_CONFIGURED

    context = ProjectContextPackage(
        task_id="t_ag_unconf",
        project_id="p_unconf",
        project_name="Unconfigured AG",
        current_phase="PHASE_10_BACKEND",
        task_title="Implement API endpoint",
        task_description="Build candidate search",
    )
    result = worker.run_task(context)
    assert result.status == "NEEDS_REVIEW"
    assert result.requires_human is True
    assert result.execution_metadata["transport"] == "MANUAL_TRANSPORT"
    assert "Antigravity CLI not configured" in result.summary


def test_antigravity_repository_scope_enforcement(tmp_path):
    repo = tmp_path / "target_project"
    repo.mkdir()
    worker = AntigravityWorker(cli_path="agy")

    # 1. Valid paths inside repository
    valid, violations = worker.validate_repository_scope(
        str(repo),
        ["src/app.py", "tests/test_app.py", "docs/SRS.md"],
    )
    assert valid is True
    assert len(violations) == 0

    # 2. Path traversal escape outside repository
    invalid_escape, escape_violations = worker.validate_repository_scope(
        str(repo),
        ["src/app.py", "../../secret_folder/token.txt"],
    )
    assert invalid_escape is False
    assert any("Escape Violation" in v for v in escape_violations)

    # 3. Forbidden file (.env, credentials.json)
    invalid_forbidden, forbidden_violations = worker.validate_repository_scope(
        str(repo),
        ["src/app.py", ".env", "secrets.json"],
    )
    assert invalid_forbidden is False
    assert any("Forbidden File" in v for v in forbidden_violations)


def test_antigravity_worker_rejects_scope_violations(tmp_path):
    repo = tmp_path / "scoped_project"
    repo.mkdir()
    worker = AntigravityWorker(cli_path="agy")

    context = ProjectContextPackage(
        task_id="t_ag_scope",
        project_id=str(repo),
        project_name="Scoped Project",
        current_phase="PHASE_10_BACKEND",
        task_title="Build service",
        task_description="Build service with illegal paths",
        relevant_files={
            "src/main.py": "print('ok')",
            ".env": "ILLEGAL_ENV_KEY=1234",
        },
    )
    result = worker.run_task(context)
    assert result.status == "BLOCKED"
    assert result.requires_human is True
    assert "Security boundary violation" in result.summary


def test_antigravity_execution_normalization(tmp_path):
    repo = tmp_path / "valid_project"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('hello')", encoding="utf-8")

    def mock_executor(cmd, cwd):
        return json.dumps({
            "status": "SUCCESS",
            "summary": "Implemented Candidate Search endpoint",
            "files_created": ["src/search.py"],
            "files_modified": ["src/app.py"],
            "diff": "+ def search_candidates(): pass",
            "acceptance_criteria_results": {"Endpoint returns 200": True},
            "recommended_next_action": "Run pytest suite",
        })

    worker = AntigravityWorker(
        cli_path="agy",
        executor_override=mock_executor,
    )
    worker.artifacts_dir = tmp_path

    context = ProjectContextPackage(
        task_id="t_ag_exec",
        project_id=str(repo),
        project_name="Valid Project",
        current_phase="PHASE_10_BACKEND",
        task_title="Implement Candidate Search",
        task_description="Implement endpoint in FastAPI",
        acceptance_criteria=["Endpoint returns 200"],
        relevant_files={"src/app.py": "print('hello')"},
    )
    result = worker.run_task(context)
    assert isinstance(result, WorkerResult)
    assert result.is_success
    assert "Implemented Candidate Search endpoint" in result.summary
    assert "src/search.py" in result.files_created
    assert "src/app.py" in result.files_modified
    assert "+ def search_candidates(): pass" in result.diff
    assert result.acceptance_criteria_results["Endpoint returns 200"] is True

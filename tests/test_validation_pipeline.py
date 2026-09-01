"""Unit and integration tests for Objective Validation Pipeline."""

import pytest

from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.reviewer import ReviewFinding, ReviewResult, ReviewVerdict
from zero_core.engineering.validator import (
    DEFAULT_PHASE_VALIDATOR,
    PhaseValidator,
    ValidationResult,
    ValidationStatus,
)
from zero_core.engineering.workers.base import WorkerResult


def test_validation_syntax_clean(tmp_path):
    repo = tmp_path / "valid_repo"
    repo.mkdir()
    valid_file = repo / "app.py"
    valid_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    manifest = ProjectManifest(project_id="p1", project_name="Test", description="Test project", repository_path=str(repo))
    task = TaskItem(task_id="t1", milestone_id="m1", title="Build hello", description="app.py")
    res = WorkerResult(task_id="t1", worker_id="w1", status="SUCCESS", summary="Clean", files_created=["app.py"])

    validator = PhaseValidator()
    val_res = validator.validate_task_execution(manifest, task, res)
    assert isinstance(val_res, ValidationResult)
    assert val_res.status == ValidationStatus.PASS
    assert val_res.is_pass
    assert len(val_res.syntax_errors) == 0


def test_validation_syntax_error(tmp_path):
    repo = tmp_path / "syntax_err_repo"
    repo.mkdir()
    err_file = repo / "broken.py"
    err_file.write_text("def broken(:\n    pass\n", encoding="utf-8")

    manifest = ProjectManifest(project_id="p1", project_name="Test", description="Test project", repository_path=str(repo))
    task = TaskItem(task_id="t1", milestone_id="m1", title="Build broken", description="broken.py")
    res = WorkerResult(task_id="t1", worker_id="w1", status="SUCCESS", summary="Broken syntax", files_created=["broken.py"])

    validator = PhaseValidator()
    val_res = validator.validate_task_execution(manifest, task, res)
    assert val_res.status == ValidationStatus.FAIL
    assert not val_res.is_pass
    assert len(val_res.syntax_errors) > 0


def test_validation_forbidden_file_rejection(tmp_path):
    repo = tmp_path / "sec_repo"
    repo.mkdir()

    manifest = ProjectManifest(project_id="p1", project_name="Test", description="Test project", repository_path=str(repo))
    task = TaskItem(task_id="t1", milestone_id="m1", title="Touch env", description="env")
    res = WorkerResult(task_id="t1", worker_id="w1", status="SUCCESS", summary="Touch env", files_created=[".env"])

    validator = PhaseValidator()
    val_res = validator.validate_task_execution(manifest, task, res)
    assert val_res.status == ValidationStatus.FAIL
    assert len(val_res.forbidden_change_findings) > 0


def test_critical_rule_tests_override_false_reviewer_pass():
    """CRITICAL RULE: A Reviewer saying 'PASS' cannot override objective failing validation."""
    review_res = ReviewResult(
        task_id="t_crit_01",
        reviewer_id="worker_chatgpt",
        subject_worker_id="worker_antigravity",
        verdict=ReviewVerdict.PASS,
        score=95,
        summary="Reviewer thinks code is great",
    )
    val_res = ValidationResult(
        task_id="t_crit_01",
        status=ValidationStatus.FAIL,
        checks_failed=["Automated pytest suite failed with 2 errors"],
        failure_summary="Pytest exit code 1",
    )

    # Engineering completion condition: Both must be PASS
    is_completed = review_res.is_pass and val_res.is_pass
    assert is_completed is False, "A reviewer PASS must NOT complete a task when objective validation fails!"


def test_critical_rule_architecture_violation_overrides_passing_tests():
    """CRITICAL RULE: Passing tests cannot override a severe architecture violation."""
    review_res = ReviewResult(
        task_id="t_crit_02",
        reviewer_id="worker_chatgpt",
        subject_worker_id="worker_antigravity",
        verdict=ReviewVerdict.NEEDS_CORRECTION,
        score=50,
        summary="Architecture violation: Direct DB access from UI layer",
        findings=[
            ReviewFinding(
                category="ARCHITECTURE",
                severity="HIGH",
                description="Direct DB access from UI violates layered architecture",
                recommendation="Introduce service layer",
                blocking=True,
            )
        ],
    )
    val_res = ValidationResult(
        task_id="t_crit_02",
        status=ValidationStatus.PASS,
        checks_passed=["Tests passed cleanly"],
    )

    # Engineering completion condition
    is_completed = review_res.is_pass and val_res.is_pass
    assert is_completed is False, "Passing tests must NOT complete a task when architecture review fails!"

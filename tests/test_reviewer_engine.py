"""Unit and integration tests for ReviewerEngine."""

import pytest

from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.reviewer import (
    DEFAULT_REVIEWER_ENGINE,
    ReviewFinding,
    ReviewResult,
    ReviewVerdict,
    ReviewerEngine,
)
from zero_core.engineering.workers.base import WorkerResult
from zero_core.engineering.workers.registry import WorkerRegistry, bootstrap_all_workers


@pytest.fixture
def clean_reviewer():
    reg = WorkerRegistry()
    bootstrap_all_workers(reg)
    return ReviewerEngine(worker_registry=reg)


def test_reviewer_independence_selection(clean_reviewer):
    rev = clean_reviewer
    # Implementation workers reviewed by ChatGPT
    assert rev.select_independent_reviewer("worker_antigravity") == "worker_chatgpt"
    assert rev.select_independent_reviewer("worker_coding_agent") == "worker_chatgpt"
    assert rev.select_independent_reviewer("worker_project_builder") == "worker_chatgpt"

    # ChatGPT reviewed by CodingAgent
    assert rev.select_independent_reviewer("worker_chatgpt") == "worker_coding_agent"


def test_reviewer_independence_violation_raises(clean_reviewer):
    rev = clean_reviewer
    manifest = ProjectManifest(project_id="p1", project_name="Test", description="Test project", repository_path=".")
    task = TaskItem(task_id="t1", milestone_id="m1", title="Task 1", description="Desc")
    res = WorkerResult(task_id="t1", worker_id="worker_chatgpt", status="SUCCESS", summary="Review target")

    with pytest.raises(ValueError, match="Reviewer Independence Violation"):
        rev.review_task_execution(manifest, task, res, reviewer_id="worker_chatgpt")


def test_native_review_pass(clean_reviewer):
    rev = clean_reviewer
    manifest = ProjectManifest(project_id="p1", project_name="Test", description="Test project", repository_path=".")
    task = TaskItem(task_id="t1", milestone_id="m1", title="Task 1", description="Desc")
    res = WorkerResult(task_id="t1", worker_id="worker_chatgpt", status="SUCCESS", summary="Architecture complete")

    # When ChatGPT is the subject, Coding Agent reviews natively
    result = rev.review_task_execution(manifest, task, res)
    assert isinstance(result, ReviewResult)
    assert result.verdict == ReviewVerdict.PASS
    assert result.is_pass
    assert result.score >= 90


def test_native_review_needs_correction_on_errors(clean_reviewer):
    rev = clean_reviewer
    manifest = ProjectManifest(project_id="p1", project_name="Test", description="Test project", repository_path=".")
    task = TaskItem(task_id="t1", milestone_id="m1", title="Task 1", description="Desc")
    res = WorkerResult(
        task_id="t1",
        worker_id="worker_chatgpt",
        status="FAILURE",
        summary="Failed architecture task",
        errors=["Missing required schema model"],
    )

    result = rev.review_task_execution(manifest, task, res)
    assert result.verdict == ReviewVerdict.NEEDS_CORRECTION
    assert not result.is_pass
    assert len(result.findings) == 1
    assert result.findings[0].description == "Missing required schema model"

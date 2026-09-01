"""Unit and integration tests for Autonomous Repair Loop."""

import pytest

from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.repair import (
    DEFAULT_REPAIR_LOOP,
    MAX_REPAIR_ATTEMPTS,
    RepairLoop,
    RepairTask,
)
from zero_core.engineering.reviewer import ReviewFinding, ReviewResult, ReviewVerdict
from zero_core.engineering.validator import ValidationResult, ValidationStatus
from zero_core.engineering.workers.registry import WorkerRegistry, bootstrap_all_workers


@pytest.fixture
def clean_repair_loop():
    reg = WorkerRegistry()
    bootstrap_all_workers(reg)
    return RepairLoop(worker_registry=reg, max_attempts=3)


def test_repair_task_generation(clean_repair_loop):
    loop = clean_repair_loop
    task = TaskItem(task_id="t_rep_01", milestone_id="m1", title="Build API", description="API endpoint")

    rev = ReviewResult(
        task_id="t_rep_01",
        reviewer_id="worker_chatgpt",
        subject_worker_id="worker_antigravity",
        verdict=ReviewVerdict.NEEDS_CORRECTION,
        score=65,
        summary="Missing error handling",
        findings=[ReviewFinding(category="CODE", severity="HIGH", description="Add try/except", recommendation="Wrap calls", blocking=True)],
        recommended_corrections=["Wrap database query in try/except"],
    )
    val = ValidationResult(
        task_id="t_rep_01",
        status=ValidationStatus.FAIL,
        checks_failed=["pytest exit code 1"],
        failure_summary="ConnectionTimeout not caught",
    )

    repair_task = loop.create_repair_task(
        original_task=task,
        original_worker_id="worker_antigravity",
        review_result=rev,
        validation_result=val,
    )
    assert isinstance(repair_task, RepairTask)
    assert repair_task.attempt_number == 1
    assert repair_task.original_task_id == "t_rep_01"
    assert "Missing error handling" in repair_task.review_findings or "Add try/except" in repair_task.review_findings
    assert "Wrap database query in try/except" in repair_task.correction_plan

    # Scope protection check
    assert any("Do NOT expand scope" in c for c in repair_task.repair_constraints)


def test_max_repair_attempts_bounded(clean_repair_loop):
    loop = clean_repair_loop
    task = TaskItem(task_id="t_bound_01", milestone_id="m1", title="Faulty Task", description="Fails repeatedly")

    rev = ReviewResult(task_id="t_bound_01", reviewer_id="w", subject_worker_id="w", verdict=ReviewVerdict.NEEDS_CORRECTION, score=50, summary="Bad")
    val = ValidationResult(task_id="t_bound_01", status=ValidationStatus.FAIL, failure_summary="Fail")

    # Attempt 1
    rep1 = loop.create_repair_task(task, "worker_coding_agent", rev, val)
    assert rep1 is not None
    assert rep1.attempt_number == 1

    # Attempt 2
    rep2 = loop.create_repair_task(task, "worker_coding_agent", rev, val)
    assert rep2 is not None
    assert rep2.attempt_number == 2

    # Attempt 3
    rep3 = loop.create_repair_task(task, "worker_coding_agent", rev, val)
    assert rep3 is not None
    assert rep3.attempt_number == 3

    # Attempt 4: MUST RETURN NONE (escalate to HITL)
    rep4 = loop.create_repair_task(task, "worker_coding_agent", rev, val)
    assert rep4 is None, "Repair loop MUST NOT create an attempt beyond MAX_REPAIR_ATTEMPTS!"


def test_repair_worker_selection(clean_repair_loop):
    loop = clean_repair_loop
    # Antigravity worker failures route to Antigravity (if healthy) or CodingAgent
    worker = loop.select_repair_worker("worker_antigravity")
    assert worker in ("worker_antigravity", "worker_coding_agent")

    # CodingAgent failures route to CodingAgent
    worker_ca = loop.select_repair_worker("worker_coding_agent")
    assert worker_ca == "worker_coding_agent"

"""Unit and integration tests for Intelligent Task Router."""

import pytest

from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.router import (
    DEFAULT_TASK_ROUTER,
    EngineeringTaskType,
    RoutingDecision,
    TaskRouter,
)
from zero_core.engineering.workers.base import (
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
    WorkerType,
)
from zero_core.engineering.workers.registry import WorkerRegistry, bootstrap_all_workers


@pytest.fixture
def clean_router():
    registry = WorkerRegistry()
    bootstrap_all_workers(registry)
    return TaskRouter(worker_registry=registry)


def test_task_classification(clean_router):
    router = clean_router
    assert router.classify_task("Draft SRS document", "Functional requirements") == EngineeringTaskType.SRS
    assert router.classify_task("Review Architecture for Trading Bot", "ADR critique") == EngineeringTaskType.ARCHITECTURE_REVIEW
    assert router.classify_task("Build Candidate UI", "Design system and wireframes") == EngineeringTaskType.UIUX
    assert router.classify_task("Run pytest suite", "Unit tests for auth") == EngineeringTaskType.TESTING
    assert router.classify_task("Implement REST endpoints", "FastAPI candidate search") == EngineeringTaskType.CODE_GENERATION
    assert router.classify_task("Refactor database models", "Clean up schema") == EngineeringTaskType.CODE_REFACTOR
    assert router.classify_task("Conduct research on LLM latency", "Benchmarking") == EngineeringTaskType.RESEARCH


def test_srs_routes_to_project_builder(clean_router):
    router = clean_router
    task = TaskItem(task_id="t_srs_01", milestone_id="m1", title="Formulate SRS", description="System requirements")
    decision = router.route_task(task)
    assert isinstance(decision, RoutingDecision)
    assert decision.task_type == EngineeringTaskType.SRS
    assert decision.selected_worker == "worker_project_builder"
    assert "ProjectBuilderWorker" in decision.selection_reasons[0]


def test_uiux_routes_to_uiux_coordinator(clean_router):
    router = clean_router
    task = TaskItem(task_id="t_ui_01", milestone_id="m1", title="Design Candidate Dashboard", description="UI UX theme")
    decision = router.route_task(task)
    assert decision.task_type == EngineeringTaskType.UIUX
    assert decision.selected_worker == "worker_uiux_designer"


def test_architecture_review_routes_to_chatgpt(clean_router):
    router = clean_router
    # Set api_key so health check is AVAILABLE
    cg = router.worker_registry.get("worker_chatgpt")
    if cg:
        cg.api_key = "fake-test-key"
    task = TaskItem(task_id="t_rev_01", milestone_id="m1", title="Review Architecture Specification", description="Critique ADRs")
    decision = router.route_task(task)
    assert decision.task_type == EngineeringTaskType.ARCHITECTURE_REVIEW
    assert decision.selected_worker == "worker_chatgpt"


def test_unhealthy_worker_triggers_fallback():
    reg = WorkerRegistry()
    bootstrap_all_workers(reg)

    # Make antigravity unconfigured
    ag = reg.get("worker_antigravity")
    if ag:
        ag.cli_path = "/nonexistent/agy.exe"

    router = TaskRouter(worker_registry=reg)
    task = TaskItem(task_id="t_code_01", milestone_id="m1", title="Implement Service Layer", description="Write code")
    decision = router.route_task(task)

    # Should fall back to CodingAgentWorker
    assert decision.selected_worker == "worker_coding_agent"
    assert any("CodingAgentWorker" in r or "fell back" in r for r in decision.selection_reasons)


def test_explainable_routing_decision(clean_router):
    router = clean_router
    task = TaskItem(task_id="t_exp_01", milestone_id="m1", title="Run regression tests", description="Pytest runner")
    decision = router.route_task(task)
    assert len(decision.selection_reasons) > 0
    assert decision.department in ("engineering", "qa")
    assert decision.task_id == "t_exp_01"


def test_performance_recording(clean_router):
    router = clean_router
    router.record_performance("worker_coding_agent", "TESTING", True, execution_seconds=1.2)
    router.record_performance("worker_coding_agent", "TESTING", False, execution_seconds=0.8)

    rec = router.performance_history.get("worker_coding_agent")
    assert rec is not None
    assert rec["tasks_attempted"] == 2
    assert rec["tasks_passed"] == 1
    assert rec["failures"] == 1

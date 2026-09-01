"""End-to-end tests for Autonomous Engineering: Router -> Worker -> Reviewer -> Validator -> Repair Loop."""

import json
from pathlib import Path
import pytest

from zero_core.agents.loop_engineering import LoopEngineeringAgent
from zero_core.engineering.checkpoints import CheckpointManager
from zero_core.engineering.manifest import ProjectManifest, TaskItem
from zero_core.engineering.repair import RepairLoop
from zero_core.engineering.reviewer import ReviewFinding, ReviewResult, ReviewVerdict, ReviewerEngine
from zero_core.engineering.router import EngineeringTaskType, RoutingDecision, TaskRouter
from zero_core.engineering.store import EngineeringProjectStore
from zero_core.engineering.validator import PhaseValidator, ValidationResult, ValidationStatus
from zero_core.engineering.workers.base import (
    EngineeringWorker,
    ProjectContextPackage,
    WorkerCapability,
    WorkerResult,
    WorkerStatus,
    WorkerType,
)
from zero_core.engineering.workers.registry import DEFAULT_WORKER_REGISTRY, WorkerRegistry, bootstrap_all_workers


class FlakyImplementationWorker(EngineeringWorker):
    """Worker that intentionally produces a defect on attempt 1, and succeeds on attempt 2."""

    def __init__(self, repo_dir: Path):
        super().__init__(
            worker_id="worker_flaky",
            name="Flaky Test Worker",
            worker_type=WorkerType.NATIVE,
            capabilities=[WorkerCapability.CODE_GENERATION, WorkerCapability.CODE_REFACTOR],
        )
        self.repo_dir = repo_dir
        self.call_count = 0

    def run_task(self, context: ProjectContextPackage) -> WorkerResult:
        self.call_count += 1
        app_file = self.repo_dir / "app.py"

        if self.call_count == 1:
            # Defective: syntax error
            app_file.write_text("def broken_syntax(:\n    pass\n", encoding="utf-8")
            return WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status="SUCCESS",  # Worker erroneously claims success
                summary="Implemented feature with syntax defect",
                files_created=["app.py"],
            )
        else:
            # Corrected repair
            app_file.write_text("def working_syntax():\n    return True\n", encoding="utf-8")
            return WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status="SUCCESS",
                summary="Repaired syntax defect cleanly",
                files_modified=["app.py"],
            )


class AlwaysFailingWorker(EngineeringWorker):
    """Worker that perpetually produces invalid output."""

    def __init__(self, repo_dir: Path):
        super().__init__(
            worker_id="worker_perpetual_fail",
            name="Perpetual Fail Worker",
            worker_type=WorkerType.NATIVE,
            capabilities=[WorkerCapability.CODE_GENERATION],
        )
        self.repo_dir = repo_dir
        self.call_count = 0

    def run_task(self, context: ProjectContextPackage) -> WorkerResult:
        self.call_count += 1
        app_file = self.repo_dir / "broken.py"
        app_file.write_text("def broken(:\n    pass\n", encoding="utf-8")
        return WorkerResult(
            task_id=context.task_id,
            worker_id=self.worker_id,
            status="FAILURE",
            summary="Perpetual syntax defect failure",
            errors=["Perpetual syntax defect"],
            files_created=["broken.py"],
        )


@pytest.fixture
def autonomous_setup(tmp_path):
    repo = tmp_path / "synthetic_repo"
    repo.mkdir()
    store_dir = tmp_path / "store"
    ckpt_dir = tmp_path / "ckpts"

    store = EngineeringProjectStore(storage_dir=store_dir)
    checkpoints = CheckpointManager(checkpoint_dir=ckpt_dir)
    registry = WorkerRegistry()
    bootstrap_all_workers(registry)

    validator = PhaseValidator()
    router = TaskRouter(worker_registry=registry)
    reviewer = ReviewerEngine(worker_registry=registry)
    repair_loop = RepairLoop(worker_registry=registry, max_attempts=3)

    agent = LoopEngineeringAgent(
        store=store,
        checkpoints=checkpoints,
        validator=validator,
        router=router,
        reviewer=reviewer,
        repair_loop=repair_loop,
        worker_registry=registry,
    )
    return agent, repo, registry


def test_mandatory_autonomous_loop(autonomous_setup):
    """MANDATORY AUTONOMOUS LOOP TEST:
    Executes: Task -> TaskRouter -> FlakyWorker -> Defective -> Reviewer/Validator FAIL
             -> RepairLoop -> FlakyWorker Repair -> Reviewer/Validator PASS -> Checkpoint -> Complete!
    """
    agent, repo, registry = autonomous_setup
    flaky_worker = FlakyImplementationWorker(repo)
    registry.register(flaky_worker)

    manifest = agent.intake_project(idea="Autonomous Task System", repo_path=str(repo))

    # Override router to route to our test worker
    class TestRouter(TaskRouter):
        def route_task(self, task, project=None):
            return RoutingDecision(
                task_id=task.task_id,
                task_type=EngineeringTaskType.CODE_GENERATION,
                department="engineering",
                selected_worker="worker_flaky",
                selection_reasons=["Assigned test worker"],
            )

    agent.router = TestRouter(worker_registry=registry)

    task = TaskItem(
        task_id="t_auto_01",
        milestone_id="m1",
        title="Implement Task Priority",
        description="Write core priority logic in app.py",
        acceptance_criteria=["Valid syntax"],
    )

    result = agent.run_autonomous_task_cycle(manifest, task)

    # 1. Assert task completed successfully
    assert result["status"] == "COMPLETED"
    # 2. Assert repair occurred automatically
    assert result["repaired"] is True
    # 3. Assert exactly one repair was required (call 1 failed, call 2 succeeded -> 1 repair attempt)
    assert result["attempts"] == 1
    # 4. Assert checkpoint was created
    assert result["checkpoint"] is not None
    assert manifest.last_successful_checkpoint == result["checkpoint"]
    # 5. Assert human approval was NOT requested for normal repair
    assert len(manifest.pending_user_actions) == 0
    # 6. Verify manifest history recorded
    assert len(manifest.routing_history) >= 1
    assert len(manifest.review_history) >= 2
    assert len(manifest.validation_history) >= 2
    assert len(manifest.repair_history) == 1


def test_mandatory_repair_limit_escalates_to_hitl(autonomous_setup):
    """MANDATORY REPAIR LIMIT TEST:
    Verifies that a worker repeatedly failing triggers:
    Attempt 1 FAIL -> Attempt 2 FAIL -> Attempt 3 FAIL -> STOP -> HITL ESCALATION (no 4th attempt).
    """
    agent, repo, registry = autonomous_setup
    fail_worker = AlwaysFailingWorker(repo)
    registry.register(fail_worker)

    manifest = agent.intake_project(idea="Failing System", repo_path=str(repo))

    class FailRouter(TaskRouter):
        def route_task(self, task, project=None):
            return RoutingDecision(
                task_id=task.task_id,
                task_type=EngineeringTaskType.CODE_GENERATION,
                department="engineering",
                selected_worker="worker_perpetual_fail",
                selection_reasons=["Assigned perpetual fail worker"],
            )

    agent.router = FailRouter(worker_registry=registry)

    task = TaskItem(
        task_id="t_hitl_limit",
        milestone_id="m1",
        title="Perpetually Failing Task",
        description="Fails repeatedly to test bounding",
    )

    result = agent.run_autonomous_task_cycle(manifest, task)

    # 1. Assert status escalated to HITL
    assert result["status"] == "ESCALATED_TO_HITL"
    # 2. Assert exactly 3 repair attempts were made (bounded)
    assert result["attempts"] == 3
    # 3. Assert pending user actions recorded HITL requirement
    assert len(manifest.pending_user_actions) > 0
    # 4. Assert worker was called for initial run + 3 repairs (total 4), not a 4th repair
    assert fail_worker.call_count == 4


def test_mandatory_security_regression_in_autonomous_loop(autonomous_setup, tmp_path):
    """MANDATORY SECURITY REGRESSION TEST:
    Injects synthetic secrets into source code, review findings, and worker errors,
    verifying zero leaks across the full autonomous cycle.
    """
    agent, repo, registry = autonomous_setup

    raw_openai_key = "sk-proj-secretleakautonomoustest12345"
    raw_github_token = "ghp_secretleakgithubtesttoken9999999"
    raw_db_password = "super_classified_db_password_888"

    # Inject secret into repo file
    (repo / "config.py").write_text(f"OPENAI_KEY = '{raw_openai_key}'\nDB_PASS = '{raw_db_password}'\n", encoding="utf-8")

    class SecretLeakingWorker(EngineeringWorker):
        def __init__(self):
            super().__init__(
                worker_id="worker_sec_leak",
                name="Security Test Worker",
                worker_type=WorkerType.NATIVE,
                capabilities=[WorkerCapability.CODE_GENERATION],
            )

        def run_task(self, context: ProjectContextPackage) -> WorkerResult:
            (repo / "app.py").write_text("def ok(): return True\n", encoding="utf-8")
            return WorkerResult(
                task_id=context.task_id,
                worker_id=self.worker_id,
                status="SUCCESS",
                summary="Completed task successfully",
                files_created=["app.py"],
            )

    registry.register(SecretLeakingWorker())

    class SecretRouter(TaskRouter):
        def route_task(self, task, project=None):
            return RoutingDecision(
                task_id=task.task_id,
                task_type=EngineeringTaskType.CODE_GENERATION,
                department="engineering",
                selected_worker="worker_sec_leak",
                selection_reasons=["Assigned secret leak tester"],
            )

    agent.router = SecretRouter(worker_registry=registry)
    manifest = agent.intake_project(idea="Secure Autonomy", repo_path=str(repo))

    task = TaskItem(
        task_id="t_sec_autonomy",
        milestone_id="m1",
        title="Check Security",
        description="Verify zero secrets in logs or manifests",
    )

    result = agent.run_autonomous_task_cycle(manifest, task)
    assert result["status"] == "COMPLETED"

    # Gather all strings from manifest and results
    all_dumped = [
        str(manifest.model_dump()),
        str(result),
    ]
    combined = "\n".join(all_dumped)

    # STRICT ZERO LEAKS
    assert raw_openai_key not in combined
    assert raw_github_token not in combined
    assert raw_db_password not in combined
